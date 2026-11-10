from __future__ import annotations

import copy
import hashlib
import errno
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/global-owner-scout/scripts'
sys.path.insert(0, str(SCRIPTS))
from history_import import import_history
import history_import
from validate_output import ContractError, describe_input, PROJECT_INPUT_KEYS, REVIEW_INPUT_KEYS


class NativeHistoryImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / 'project'; self.project.mkdir()
        self.output = self.root / 'granted-output'; self.output.mkdir()
        self.page = dict(schemaVersion=1, thread=dict(id='source-chat', kind='codex', cwd=str(self.project)),
                         page=dict(nextCursor='older-page', hasMore=True),
                         turns=[dict(id='turn', items=[dict(id='native-item', type='commandExecution',
                             text='中文原始证据 😀', outputTruncated=True, exitCode=1)])])

    def save(self, value=None, **kwargs):
        return import_history(self.page if value is None else value, project_root=self.project,
                              session_id=kwargs.get('session_id', 'source-chat'),
                              artifact_dir=kwargs.get('artifact_dir', self.output), protected_roots=[self.project])

    def test_native_page_is_written_once_with_exact_payload_identity_and_truncation(self):
        wrapped=dict(content=[dict(type='text', text=json.dumps(self.page, ensure_ascii=False))], isError=False)
        first=self.save(wrapped); second=self.save()
        self.assertEqual(first['status'], 'imported'); self.assertEqual(second['status'], 'reused')
        raw=Path(first['native_file']).read_bytes()
        self.assertEqual(json.loads(raw), self.page)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), first['sha256'])
        self.assertEqual(first['page'], self.page['page'])
        self.assertEqual(first['truncation_paths'], ['$.turns[0].items[0].outputTruncated'])
        self.assertEqual(len(list(self.output.iterdir())), 2)
        changed=copy.deepcopy(self.page); changed['turns'][0]['items'][0]['text']='new observation'
        self.assertNotEqual(self.save(changed)['sha256'], first['sha256'])
        self.assertEqual(Path(first['native_file']).read_bytes(), raw)

    def test_wrong_identity_corrupt_payload_and_project_output_are_rejected_before_write(self):
        bad=copy.deepcopy(self.page); bad['thread']['cwd']=str(self.output)
        for value,kwargs in [(self.page,dict(session_id='wrong')), (bad,{}),
                             (dict(content=[dict(type='text',text='broken')]),{}),
                             (dict(self.page,schemaVersion=99),{}),
                             (self.page,dict(artifact_dir=self.project))]:
            with self.subTest(kwargs=kwargs), self.assertRaises((ContractError, ValueError)):
                self.save(value, **kwargs)
        self.assertFalse(list(self.output.iterdir())); self.assertFalse(list(self.project.iterdir()))

    def test_alias_target_and_tampered_existing_artifact_are_rejected(self):
        first=self.save(); file=Path(first['native_file'])
        file.chmod(0o600); file.write_text('tampered',encoding='utf-8')
        with self.assertRaises(ContractError): self.save()
        file.unlink(); target=self.root/'other.json'; target.write_text('private',encoding='utf-8')
        try: file.symlink_to(target)
        except OSError: self.skipTest('symlink creation unavailable')
        with self.assertRaises((ContractError, OSError)) as rejected: self.save()
        if isinstance(rejected.exception, OSError):
            self.assertEqual(rejected.exception.errno, errno.ELOOP)
        self.assertEqual(target.read_text(encoding='utf-8'), 'private')

    def test_concurrent_parent_replacement_cannot_write_into_protected_project(self):
        original=history_import.write_native_artifact
        attempted=[]
        def race(root, descriptor, name, data):
            if not attempted:
                attempted.append(True)
                try:
                    self.output.rename(self.root/'retained-original-output')
                except PermissionError:
                    # Windows directory handles forbid delete/rename during both writes.
                    self.assertEqual(sys.platform,'win32')
                else:
                    self.output.symlink_to(self.project,target_is_directory=True)
            return original(root,descriptor,name,data)
        with mock.patch.object(history_import,'write_native_artifact',side_effect=race):
            if sys.platform=='win32':
                self.assertEqual(self.save()['status'],'imported')
            else:
                with self.assertRaises(ContractError): self.save()
        self.assertTrue(attempted)
        self.assertFalse(list(self.project.iterdir()))

    @unittest.skipUnless(sys.platform == 'win32', 'Windows native sharing contract')
    def test_pinned_directory_refuses_write_handle_for_in_place_reparse_mutation(self):
        import ctypes
        from ctypes import wintypes
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        create=api.CreateFileW
        create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        create.restype=wintypes.HANDLE
        close=api.CloseHandle; close.argtypes=[wintypes.HANDLE]
        original=history_import.write_native_artifact
        def try_mutation(root, descriptor, name, data):
            handle=create(str(root),0x40000000,0x1|0x2|0x4,None,3,0x02000000|0x00200000,None)
            if handle!=ctypes.c_void_p(-1).value:
                close(handle)
                self.fail('pinned history directory admitted GENERIC_WRITE for reparse mutation')
            self.assertEqual(ctypes.get_last_error(),32)
            return original(root,descriptor,name,data)
        with mock.patch.object(history_import,'write_native_artifact',side_effect=try_mutation):
            self.assertEqual(self.save()['status'],'imported')
        self.assertFalse(list(self.project.iterdir()))

    def test_packaged_cli_consumes_file_and_shared_input_contract_without_transcribing(self):
        input_file=self.root/'tool-response.json'; input_file.write_text(json.dumps(self.page),encoding='utf-8')
        args=[sys.executable,'-B',str(SCRIPTS/'scout.py'),'import-history','--input-file',str(input_file),
              '--project-root',str(self.project),'--session-id','source-chat','--artifact-dir',str(self.output),
              '--protected-root',str(self.project)]
        result=subprocess.run(args,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['session_id'],'source-chat')
        help_result=subprocess.run([sys.executable,'-B',str(SCRIPTS/'scout.py'),'describe-input','review'],
                                   capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(help_result.returncode,0,help_result.stderr)
        self.assertEqual(json.loads(help_result.stdout)['required_keys'],sorted(REVIEW_INPUT_KEYS))
        self.assertEqual(set(describe_input('project')['required_keys']),PROJECT_INPUT_KEYS|{'purpose','project_map'})
        invalid=self.root/'invalid.json'; invalid.write_text('{}',encoding='utf-8')
        failed=subprocess.run([sys.executable,'-B',str(SCRIPTS/'scout.py'),'validate-project','--input-file',str(invalid)],
                              capture_output=True,text=True,encoding='utf-8')
        self.assertNotEqual(failed.returncode,0); self.assertIn('$',failed.stderr)

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS native directory mapping')
    def test_os_owned_top_level_temp_mapping_keeps_host_granted_output_usable(self):
        lexical=Path(tempfile.gettempdir())/self.root.name/'granted-output'
        self.assertEqual(lexical.resolve(),self.output)
        self.assertEqual(self.save(artifact_dir=lexical)['status'],'imported')


if __name__ == '__main__':
    unittest.main()
