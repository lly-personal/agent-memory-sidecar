/** Explicit deployment prerequisite. Ordinary Scout never runs npm. */
import {execFile} from 'node:child_process';
import {createHash} from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {promisify} from 'node:util';

const exec = promisify(execFile);
const source = fileURLToPath(new URL('../runtime/claude/', import.meta.url));
const hash = data => createHash('sha256').update(data).digest('hex');
const config = JSON.parse(await fs.readFile(path.join(source, 'package.json'), 'utf8'));
export const sdkVersion = config.dependencies['@anthropic-ai/claude-agent-sdk'];
const lock = await fs.readFile(path.join(source, 'package-lock.json'));

export function runtimePath(dataDir) {
  if (!path.isAbsolute(dataDir) || dataDir.includes('${')) throw Error('claude_plugin_data_required');
  return path.join(dataDir, 'scout-runtime', 'claude-sdk-' + sdkVersion);
}

async function physical(target) {
  let current = path.resolve(target);
  for (;;) {
    try { if ((await fs.lstat(current)).isSymbolicLink()) throw Error('claude_runtime_alias_rejected'); }
    catch (e) { if (e.code !== 'ENOENT') throw e; }
    const parent = path.dirname(current);
    if (parent === current) return;
    current = parent;
  }
}

async function identity(root) {
  await physical(root);
  const entry = path.join(root, 'node_modules/@anthropic-ai/claude-agent-sdk/sdk.mjs');
  await physical(entry);
  await physical(path.join(path.dirname(entry), 'package.json'));
  for (const name of ['package.json', 'package-lock.json', 'INSTALLATION.json']) await physical(path.join(root, name));
  const pkg = JSON.parse(await fs.readFile(path.join(path.dirname(entry), 'package.json'), 'utf8'));
  if (pkg.version !== sdkVersion || !lock.equals(await fs.readFile(path.join(root, 'package-lock.json')))
      || !(await fs.readFile(path.join(source, 'package.json'))).equals(await fs.readFile(path.join(root, 'package.json')))) {
    throw Error('claude_runtime_identity_mismatch');
  }
  return {contract_version: 'global_owner_scout_claude_runtime_v1', sdk_version: sdkVersion,
    lock_sha256: hash(lock), entry_sha256: hash(await fs.readFile(entry))};
}

export async function verifyRuntime(dataDir) {
  const root = runtimePath(dataDir);
  try {
    const actual = await identity(root);
    const receipt = JSON.parse(await fs.readFile(path.join(root, 'INSTALLATION.json'), 'utf8'));
    if (JSON.stringify(actual) !== JSON.stringify(receipt)) throw Error('claude_runtime_identity_mismatch');
    return {root, entry: path.join(root, 'node_modules/@anthropic-ai/claude-agent-sdk/sdk.mjs'), receipt};
  } catch (e) {
    if (e.code === 'ENOENT') {
      try { await fs.lstat(root); }
      catch (absent) {
        if (absent.code === 'ENOENT') throw Error('claude_runtime_not_prepared:run the reviewed deployment prerequisite for ' + root);
        throw absent;
      }
      throw Error('claude_runtime_incomplete:preserved ' + root + '; review the installation failure and recover this exact runtime before deployment; rerunning does not repair it');
    }
    throw e;
  }
}

export async function prepareRuntime(dataDir, npmCli) {
  const root = runtimePath(dataDir);
  await physical(root);
  if (!/^agent-memory-sidecar(?:-[A-Za-z0-9_-]+)?$/.test(path.basename(dataDir))
      || path.basename(path.dirname(dataDir)) !== 'data' || path.basename(path.dirname(path.dirname(dataDir))) !== 'plugins') {
    throw Error('claude_runtime_native_plugin_data_required');
  }
  // A dependency deployment must never become a write to a reviewed Git project.
  for (let parent = root; ; parent = path.dirname(parent)) {
    try { await fs.lstat(path.join(parent, '.git')); throw Error('claude_runtime_project_write_rejected'); }
    catch (e) { if (e.code !== 'ENOENT') throw e; }
    if (path.dirname(parent) === parent) break;
  }
  try {
    await fs.lstat(root);
    // A partial/unknown installation is preserved, never overwritten or deleted.
    return {status: 'unchanged', ...await verifyRuntime(dataDir)};
  } catch (e) { if (e.code !== 'ENOENT') throw e; }
  if (!path.isAbsolute(npmCli) || !(await fs.stat(npmCli)).isFile()) throw Error('claude_runtime_absolute_npm_cli_required');
  await fs.mkdir(path.dirname(root), {recursive: true});
  await fs.mkdir(root);
  await fs.copyFile(path.join(source, 'package.json'), path.join(root, 'package.json'));
  await fs.copyFile(path.join(source, 'package-lock.json'), path.join(root, 'package-lock.json'));
  await exec(process.execPath, [npmCli, 'ci', '--prefix', root, '--ignore-scripts', '--omit=optional',
    '--no-audit', '--no-fund', '--cache', path.join(root, 'npm-cache')],
    {cwd: path.toNamespacedPath(root), windowsHide: true, timeout: 120000});
  const receipt = await identity(root);
  await fs.writeFile(path.join(root, 'INSTALLATION.json'), JSON.stringify(receipt) + '\n', {flag: 'wx'});
  return {status: 'prepared', ...await verifyRuntime(dataDir)};
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const [dataDir, npmCli, ...extra] = process.argv.slice(2);
    if (!dataDir || !npmCli || extra.length) throw Error('usage: prepare_claude_runtime.mjs ABSOLUTE_PLUGIN_DATA ABSOLUTE_NPM_CLI');
    console.log(JSON.stringify(await prepareRuntime(dataDir, npmCli)));
  } catch (e) { console.error(e.message); process.exitCode = 1; }
}
