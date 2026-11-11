import {execFile, spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {constants} from 'node:fs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {promisify} from 'node:util';
import {exportPiContext, exportPiSession} from './native_session_export.mjs';

const exec = promisify(execFile);
const script = fileURLToPath(new URL('./scout.py', import.meta.url));
const skillRoot = fileURLToPath(new URL('../', import.meta.url));

const digest = data => createHash('sha256').update(data).digest('hex');

async function resolvePython(cwd, signal) {
  const windows = process.platform === 'win32';
  let workspace = await fs.realpath(cwd);
  for (;;) {
    try { await fs.lstat(path.join(workspace, '.git')); break; }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    const parent = path.dirname(workspace);
    if (parent === workspace) throw new Error('native_source_git_workspace_required');
    workspace = parent;
  }
  for (const entry of (process.env.PATH ?? '').split(path.delimiter)) {
    const directory = windows ? entry.replace(/^"(.*)"$/, '$1') : entry;
    if (!path.isAbsolute(directory)) continue;
    let candidate;
    try { candidate = await fs.realpath(path.join(directory, windows ? 'python.exe' : 'python3')); }
    catch (error) { if (error.code === 'ENOENT' || error.code === 'ENOTDIR') continue; throw error; }
    const relative = path.relative(workspace, candidate);
    if (!relative || !path.isAbsolute(relative) && relative !== '..' && !relative.startsWith('..' + path.sep)) continue;
    if (windows && path.basename(path.dirname(candidate)).toLowerCase() === 'windowsapps') continue;
    if (!(await fs.stat(candidate)).isFile()) continue;
    await fs.access(candidate, constants.X_OK);
    const result = await exec(candidate, ['-I', '-B', '-c', 'import json,sys; print(json.dumps({"executable":sys.executable,"version":list(sys.version_info[:3])}))'], {windowsHide: true, signal});
    const meta = JSON.parse(result.stdout);
    if (meta.version[0] === 3 && meta.version[1] >= 11 && path.isAbsolute(meta.executable)) {
      meta.executable = await fs.realpath(meta.executable);
      meta.sha256 = digest(await fs.readFile(meta.executable));
      return meta;
    }
  }
  throw new Error('native_source_python_311_required');
}

async function helper(python, args, input, ctx) {
  if (digest(await fs.readFile(python.executable)) !== python.sha256) throw new Error('native_source_python_identity_changed');
  return new Promise((resolve, reject) => {
    const child = spawn(python.executable, ['-E', '-s', '-B', '-X', 'utf8', script, ...args],
      {cwd: ctx.cwd, signal: ctx.signal, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe']});
    let stdout = '', stderr = '', failure;
    child.stdout.on('data', data => { stdout += data; });
    child.stderr.on('data', data => { stderr += data; });
    child.once('error', error => { failure = error; }); child.stdin.once('error', error => { failure = error; });
    child.once('close', code => {
      if (failure) return reject(failure);
      if (code !== 0) return reject(new Error(stderr.trim() || 'native_source_helper_failed'));
      try { resolve(JSON.parse(stdout)); } catch (error) { reject(error); }
    });
    child.stdin.end(input === undefined ? '' : JSON.stringify(input));
  });
}

/** Loading never starts Scout, changes a profile or submits a model request. */
export default function registerScoutContext(pi) {
  let python;
  pi.registerTool({
    name: 'global_owner_scout_context',
    label: 'Scout current native context',
    description: 'For an explicit Scout, read current native context or mechanically seal its current-session snapshot through the formal importer. capture_current requires an already authorized artifact_dir; it grants no access or full-history qualification.',
    parameters: {type: 'object', properties: {
      operation: {type: 'string', enum: ['context', 'capture_current']},
      artifact_dir: {type: 'string'},
    }, additionalProperties: false},
    async execute(_id, params, _signal, _onUpdate, ctx) {
      const native = exportPiContext(ctx);
      const details = {native_context: native,
        selected_model: ctx.model ? {provider: ctx.model.provider, id: ctx.model.id} : null,
        selected_reasoning: ctx.thinkingLevel ?? null};
      if (params.operation === 'capture_current') {
        if (typeof params.artifact_dir !== 'string' || !path.isAbsolute(params.artifact_dir)) {
          throw new Error('native_source_current_authorized_artifact_dir_required');
        }
        python ??= await resolvePython(ctx.cwd, _signal ?? ctx.signal);
        const execution = {cwd: ctx.cwd, signal: _signal ?? ctx.signal};
        const binding = await helper(python, ['inspect-native'], native, execution);
        const protection = ['--protected-root', binding.project_root, '--protected-root', skillRoot];
        await helper(python, ['inspect-output', '--artifact-dir', params.artifact_dir, ...protection], undefined, execution);
        if (ctx.sessionManager.getSessionId() !== native.context.session_id || ctx.sessionManager.getCwd() !== native.context.cwd) {
          throw new Error('native_session_changed_during_capture');
        }
        const captured = await helper(python, ['import-history', '--project-root', native.context.cwd,
          '--session-id', native.context.session_id, '--artifact-dir', params.artifact_dir, ...protection],
          exportPiSession(ctx.sessionManager), execution);
        // Full IDs remain in the immutable index; do not spend model context
        // retransmitting an unbounded ID list or the original conversation.
        details.capture = Object.fromEntries(['contract_version', 'status', 'native_host', 'native_file',
          'sha256', 'index_path', 'record_count', 'evidence_scope'].map(key => [key, captured[key]]));
        details.native_binding = binding;
        details.python = python;
        details.captured_at = new Date().toISOString();
      }
      return {content: [{type: 'text', text: JSON.stringify(details)}], details};
    },
  });
}
