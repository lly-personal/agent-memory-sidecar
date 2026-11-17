import {execFile, spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {constants} from 'node:fs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {promisify} from 'node:util';
const exec = promisify(execFile);
const digest = data => createHash('sha256').update(data).digest('hex');

export async function resolvePython(cwd, signal) {
  const windows = process.platform === 'win32';
  let workspace = await fs.realpath(cwd);
  for (;;) {
    try { await fs.lstat(path.join(workspace, '.git')); break; }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    const parent = path.dirname(workspace);
    if (parent === workspace) throw new Error('native_source_git_workspace_required');
    workspace = parent;
  }
  const outsideWorkspace = target => {
    const relative = path.relative(workspace, target);
    return Boolean(relative && (path.isAbsolute(relative) || relative === '..' || relative.startsWith('..' + path.sep)));
  };
  const isWindowsStoreStub = target => windows && target.toLowerCase().split(path.sep).includes('windowsapps');
  const launchers = windows ? [['python.exe', []], ['py.exe', ['-3']]] : [['python3', []]];
  const entries = (process.env.PATH ?? '').split(path.delimiter);
  for (const [binary, prefixArgs] of launchers) {
    for (const entry of entries) {
      const directory = windows ? entry.replace(/^"(.*)"$/, '$1') : entry;
      if (!path.isAbsolute(directory)) continue;
      let candidate;
      try { candidate = await fs.realpath(path.join(directory, binary)); }
      catch (error) { if (error.code === 'ENOENT' || error.code === 'ENOTDIR') continue; throw error; }
      if (!outsideWorkspace(candidate) || isWindowsStoreStub(candidate)) continue;
      try {
        if (!(await fs.stat(candidate)).isFile()) continue;
        await fs.access(candidate, constants.X_OK);
        const result = await exec(candidate, [...prefixArgs, '-I', '-B', '-c', 'import json,sys; print(json.dumps({"executable":sys.executable,"version":list(sys.version_info[:3])}))'], {windowsHide: true, signal});
        const meta = JSON.parse(result.stdout);
        if (meta.version[0] === 3 && meta.version[1] >= 11 && path.isAbsolute(meta.executable)) {
          const resolvedExe = await fs.realpath(meta.executable);
          if (!outsideWorkspace(resolvedExe) || isWindowsStoreStub(resolvedExe)) continue;
          meta.executable = resolvedExe;
          meta.sha256 = digest(await fs.readFile(resolvedExe));
          return meta;
        }
      } catch (error) {
        if (signal?.aborted || error?.name === 'AbortError') throw error;
        continue;
      }
    }
  }
  throw new Error('native_source_python_311_required');
}

export async function helper(python, args, input, ctx) {
  if (digest(await fs.readFile(python.executable)) !== python.sha256) throw new Error('native_source_python_identity_changed');
  return new Promise((resolve, reject) => {
    const child = spawn(python.executable, ['-E', '-s', '-B', '-X', 'utf8', fileURLToPath(new URL('./scout.py', import.meta.url)), ...args],
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
