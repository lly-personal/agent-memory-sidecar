/** Ordinary Skill adapter: current native substitutions, scoped SDK, formal writer. */
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {resolvePython, helper} from './native_runtime.mjs';
import {exportClaudeSessionPage} from './native_session_export.mjs';
import {verifyRuntime} from './prepare_claude_runtime.mjs';

const skillRoot = fileURLToPath(new URL('../', import.meta.url));

export async function invokeClaude({operation, session_id, project_root, skill_dir, plugin_root,
  plugin_data, artifact_dir, source_session_id = session_id, offset = 0, limit = 100}, loadSdk = async entry => import(pathToFileURL(entry))) {
  if (!['context', 'capture'].includes(operation)) throw Error('claude_native_operation_invalid');
  if (typeof session_id !== 'string' || !session_id || session_id.includes('${')
      || [project_root, skill_dir, plugin_root].some(p => typeof p !== 'string' || !path.isAbsolute(p) || p.includes('${'))) {
    throw Error('claude_native_current_substitutions_required');
  }
  const native = {contract_version: 'global_owner_scout_native_context_v1', native_host: 'claude', context: {
    source_kind: 'claude_skill_substitution', cwd: process.cwd(), project_dir: project_root, session_id, skill_dir, plugin_root}};
  const python = await resolvePython(process.cwd());
  const execution = {cwd: process.cwd()};
  const binding = await helper(python, ['inspect-native'], native, execution);
  const result = {native_context: native, native_binding: binding, python};
  if (operation === 'context') return result;
  if (typeof artifact_dir !== 'string' || !path.isAbsolute(artifact_dir)) throw Error('native_source_current_authorized_artifact_dir_required');
  // Check every write boundary before loading the SDK or reading any messages.
  const protection = [binding.project_root, skillRoot, plugin_root, plugin_data].flatMap(p => ['--protected-root', p]);
  if (typeof plugin_data !== 'string' || !path.isAbsolute(plugin_data)) throw Error('claude_plugin_data_required');
  await helper(python, ['inspect-output', '--artifact-dir', artifact_dir, ...protection], undefined, execution);
  const runtime = await verifyRuntime(plugin_data);
  const sdk = await loadSdk(runtime.entry);
  // Caller and selected source are separate even when they happen to be equal.
  const caller = await sdk.getSessionInfo(session_id, {dir: project_root});
  const same = (a, b) => process.platform === 'win32' ? a.toLowerCase() === b.toLowerCase() : a === b;
  if (caller?.sessionId !== session_id || typeof caller.cwd !== 'string'
      || !same(path.resolve(caller.cwd), path.resolve(project_root))) throw Error('claude_native_caller_mismatch');
  const page = await exportClaudeSessionPage(sdk, {project_root,
    session_id: source_session_id, offset, limit});
  const captured = await helper(python, ['import-history', '--project-root', project_root,
    '--session-id', source_session_id, '--artifact-dir', artifact_dir, ...protection], page, execution);
  result.capture = Object.fromEntries(['contract_version', 'status', 'native_host', 'native_file',
    'sha256', 'index_path', 'record_count', 'evidence_scope'].map(k => [k, captured[k]]));
  result.runtime = runtime.receipt;
  result.source_session_id = source_session_id;
  return result;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const [operation, ...args] = process.argv.slice(2), options = {operation};
    const fields = new Set(['session-id','project-root','skill-dir','plugin-root','plugin-data','artifact-dir','source-session-id','offset','limit']);
    if (args.length % 2) throw Error('claude_native_argument_value_required');
    for (let i = 0; i < args.length; i += 2) {
      const field = args[i].replace(/^--/, '');
      if (!args[i].startsWith('--') || !fields.has(field)) throw Error('claude_native_argument_unknown:' + args[i]);
      const key = field.replaceAll('-', '_');
      if (key in options) throw Error('claude_native_argument_duplicate:' + field);
      options[key] = ['offset', 'limit'].includes(field) ? Number(args[i+1]) : args[i+1];
    }
    console.log(JSON.stringify(await invokeClaude(options)));
  } catch (e) { console.error(e.message); process.exitCode = 1; }
}
