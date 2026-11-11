/** Mechanically export the current Pi SDK session; no filesystem or project discovery. */
import path from 'node:path';

export function exportPiSession(sessionManager) {
  const session = sessionManager.getHeader();
  if (!session || session.type !== 'session' || session.version !== 3) {
    throw new Error('native_session_header_unsupported');
  }
  if (session.id !== sessionManager.getSessionId() || session.cwd !== sessionManager.getCwd()) {
    throw new Error('native_session_context_mismatch');
  }
  return structuredClone({
    contract_version: 'global_owner_scout_native_session_v1',
    native_host: 'pi',
    session,
    entries: sessionManager.getEntries(),
  });
}

/** Read one explicitly scoped page through the host's official Claude SDK. */
export async function exportClaudeSessionPage(sdk, { project_root, session_id, offset, limit }) {
  if (!path.isAbsolute(project_root) || typeof session_id !== 'string' || !session_id
      || !Number.isInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit <= 0) {
    throw new Error('native_session_page_request_invalid');
  }
  const session = await sdk.getSessionInfo(session_id, { dir: project_root });
  const nativeRoot = session?.cwd && path.resolve(session.cwd);
  const expectedRoot = path.resolve(project_root);
  const sameRoot = process.platform === 'win32'
    ? nativeRoot?.toLowerCase() === expectedRoot.toLowerCase() : nativeRoot === expectedRoot;
  if (session?.sessionId !== session_id || !sameRoot) {
    throw new Error('native_session_context_mismatch');
  }
  const page_request = { offset, limit, includeSystemMessages: true };
  const messages = await sdk.getSessionMessages(session_id, { dir: project_root, ...page_request });
  return structuredClone({ contract_version: 'global_owner_scout_native_page_v1',
    native_host: 'claude', session, messages, page_request });
}
