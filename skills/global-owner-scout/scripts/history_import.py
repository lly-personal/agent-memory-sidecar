"""Freeze one native tool page without model transcription or project writes."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from prepare_delivery import (is_reparse, safe_artifact_bytes, validate_output_root,
                              write_immutable_artifact)
from validate_output import ContractError


def require(value: bool, reason: str) -> None:
    if not value:
        raise ContractError(reason)


@contextmanager
def pinned_directory(root: Path):
    before = root.stat()
    handles = []
    descriptor = None
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                           wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close.restype = wintypes.BOOL
    try:
        if os.name == 'nt':
            # Deny WRITE and DELETE sharing: prevent rename and in-place reparse mutation.
            # must fail until both artifacts and readback are complete. No privilege change.
            for directory in reversed([root, *root.parents]):
                handle = create(str(directory), 0x80000000, 0x1, None, 3, 0x02000000 | 0x00200000, None)
                if handle == ctypes.c_void_p(-1).value:
                    raise ctypes.WinError(ctypes.get_last_error())
                handles.append(handle)
                observed = directory.lstat()
                require(stat.S_ISDIR(observed.st_mode) and not is_reparse(observed), 'history_output_changed')
        else:
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            opened = os.fstat(descriptor)
            require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino), 'history_output_changed')
        current = root.lstat()
        require(not is_reparse(current) and not stat.S_ISLNK(current.st_mode)
                and (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino), 'history_output_changed')
        require(root.resolve(strict=True) == root, 'history_output_ancestor_changed')
        yield descriptor
        current = root.lstat()
        require(not is_reparse(current) and not stat.S_ISLNK(current.st_mode)
                and (current.st_dev, current.st_ino) == (before.st_dev, before.st_ino), 'history_output_changed')
        require(root.resolve(strict=True) == root, 'history_output_ancestor_changed')
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if os.name == 'nt':
            for handle in reversed(handles):
                close(handle)


def write_native_artifact(root: Path, descriptor: int | None, name: str, data: bytes) -> None:
    if descriptor is None:
        write_immutable_artifact(root / name, data)
        return
    try:
        file = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=descriptor)
    except FileExistsError:
        file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        with os.fdopen(file, 'rb') as stream:
            observed = os.fstat(stream.fileno())
            require(stat.S_ISREG(observed.st_mode) and observed.st_nlink == 1
                    and stat.S_IMODE(observed.st_mode) & 0o222 == 0, 'history_artifact_not_immutable_regular')
            require(stream.read() == data, 'history_artifact_bytes_changed')
    else:
        with os.fdopen(file, 'w+b') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), 0o400)
            stream.seek(0)
            require(stream.read() == data and os.fstat(stream.fileno()).st_nlink == 1, 'history_artifact_readback_failed')


def import_history(value: Any, *, project_root: Path, session_id: str,
                   artifact_dir: Path, protected_roots: list[Path]) -> dict[str, Any]:
    root = validate_output_root(artifact_dir, [project_root, *protected_roots])
    # Reject aliased ancestors too: resolving a path must not silently change the grant.
    for ancestor in [artifact_dir, *artifact_dir.parents]:
        observed = ancestor.lstat()
        # Same existing L1 policy as Core file_security: OS-owned POSIX top-level
        # mappings are trusted; user-controlled links and Windows reparse points are not.
        trusted = (os.name == 'posix' and stat.S_ISLNK(observed.st_mode)
                   and observed.st_uid == 0 and ancestor.parent == Path(ancestor.anchor)
                   and ancestor != artifact_dir)
        require(trusted or not ancestor.is_symlink() and not is_reparse(observed), 'history_output_ancestor_alias')
    require(isinstance(value, dict), 'native_history_object_required')
    if 'content' in value:
        require(value.get('isError') is not True, 'native_history_tool_failed')
        require(isinstance(value['content'], list), 'native_history_content_array_required')
        texts = [c.get('text') for c in value['content'] if isinstance(c, dict) and c.get('type') == 'text']
        require(len(texts) == 1 and isinstance(texts[0], str), 'native_history_single_json_response_required')
        value = json.loads(texts[0])
    require(isinstance(value, dict), 'native_history_object_required')
    pi_source = value.get('contract_version') == 'global_owner_scout_native_session_v1'
    claude_source = value.get('contract_version') == 'global_owner_scout_native_page_v1'
    if pi_source:
        require(set(value) == {'contract_version', 'native_host', 'session', 'entries'}
                and value.get('native_host') == 'pi', 'native_history_source_unsupported')
        thread = value['session']
        require(isinstance(thread, dict) and thread.get('type') == 'session'
                and type(thread.get('version')) is int and thread['version'] == 3,
                'native_history_session_header_unsupported')
        entries = value['entries']
        require(isinstance(entries, list) and all(isinstance(entry, dict)
                and isinstance(entry.get('id'), str) and bool(entry['id'])
                and isinstance(entry.get('type'), str) and bool(entry['type']) for entry in entries),
                'native_history_entry_shape_invalid')
        require(len({entry['id'] for entry in entries}) == len(entries), 'native_history_duplicate_entry')
    elif claude_source:
        require(set(value) == {'contract_version', 'native_host', 'session', 'messages', 'page_request'}
                and value.get('native_host') == 'claude', 'native_history_source_unsupported')
        thread = value['session']
        require(isinstance(thread, dict), 'native_history_session_header_unsupported')
        messages = value['messages']
        require(isinstance(messages, list) and all(isinstance(message, dict)
                and message.get('type') in {'user', 'assistant', 'system'}
                and isinstance(message.get('uuid'), str) and bool(message['uuid'])
                and message.get('session_id') == session_id for message in messages),
                'native_history_message_shape_invalid')
        require(len({message['uuid'] for message in messages}) == len(messages), 'native_history_duplicate_message')
        page = value['page_request']
        require(isinstance(page, dict) and set(page) == {'offset', 'limit', 'includeSystemMessages'}
                and type(page['offset']) is int and page['offset'] >= 0
                and type(page['limit']) is int and page['limit'] > 0
                and page['includeSystemMessages'] is True, 'native_history_page_request_invalid')
    else:
        require(value.get('schemaVersion') == 1, 'native_history_schema_unsupported')
        thread = value.get('thread')
        require(isinstance(thread, dict) and thread.get('kind') == 'codex', 'native_history_thread_required')
        turns = value.get('turns')
        require(isinstance(turns, list), 'native_history_turns_required')
        require(all(isinstance(t, dict) and isinstance(t.get('items'), list) for t in turns),
                'native_history_turn_shape_invalid')
    require(thread.get('sessionId' if claude_source else 'id') == session_id and bool(session_id),
            'native_history_session_mismatch')
    require(isinstance(thread.get('cwd'), str) and bool(thread['cwd']), 'native_history_project_missing')
    require(Path(thread['cwd']).resolve(strict=True) == project_root.resolve(strict=True), 'native_history_project_mismatch')
    truncations: list[str] = []

    def visit(item: Any, location: str) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                here = f'{location}.{key}'
                if (key == 'truncated' or key.endswith('Truncated')) and child is True:
                    truncations.append(here)
                visit(child, here)
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f'{location}[{index}]')

    visit(value, '$')
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    digest = hashlib.sha256(data).hexdigest()
    native_file = root / f'native-history-{digest}.json'
    existed = native_file.exists()
    index = dict(native_file=str(native_file), sha256=digest, session_id=session_id,
                 project_root=thread['cwd'], truncation_paths=truncations,
                 serialization='canonical UTF-8 native payload; not transport wire bytes')
    if pi_source:
        index.update(contract_version='global_owner_scout_history_page_v2', native_host='pi',
                     entry_ids=[entry['id'] for entry in entries], record_count=len(entries),
                     evidence_scope='one Pi SDK session snapshot; project binding, project-history completeness, '
                                    'task termination and full Scout qualification remain unverified')
    elif claude_source:
        index.update(contract_version='global_owner_scout_history_page_v2', native_host='claude',
                     message_ids=[message['uuid'] for message in messages], record_count=len(messages),
                     page_request=value['page_request'],
                     evidence_scope='one scoped Claude SDK message page; project binding, history completeness, '
                                    'task termination, Desktop association and full Scout qualification remain unverified')
    else:
        index.update(contract_version='global_owner_scout_history_page_v1', page=value.get('page'),
                     turn_ids=[t.get('id') for t in turns], item_count=sum(len(t['items']) for t in turns),
                     evidence_scope='one acquired native page; not full-chat or comprehension proof')
    index_file = root / f'native-history-{digest}.index.json'
    with pinned_directory(root) as descriptor:
        write_native_artifact(root, descriptor, native_file.name, data)
        write_native_artifact(root, descriptor, index_file.name, json.dumps(index, ensure_ascii=False,
            sort_keys=True, separators=(',', ':')).encode('utf-8'))
        if descriptor is None:
            require(hashlib.sha256(safe_artifact_bytes(native_file)).hexdigest() == digest, 'native_history_readback_failed')
    return dict(index, status='reused' if existed else 'imported', index_path=str(index_file))
