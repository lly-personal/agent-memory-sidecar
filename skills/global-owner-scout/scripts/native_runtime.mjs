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
