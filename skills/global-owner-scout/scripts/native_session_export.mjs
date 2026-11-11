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

/** Capture current runtime metadata before reading any historical entries. */
export function exportPiContext(ctx) {
  const session = ctx.sessionManager.getHeader();
  if (session?.type !== 'session' || session.version !== 3
      || session.id !== ctx.sessionManager.getSessionId()
      || session.cwd !== ctx.sessionManager.getCwd() || session.cwd !== ctx.cwd) {
    throw new Error('native_session_context_mismatch');
  }
  return structuredClone({ contract_version: 'global_owner_scout_native_context_v1', native_host: 'pi',
    context: { cwd: ctx.cwd, session_id: session.id, session, mode: ctx.mode } });
}

export function exportClaudeContext(init) {
  if (init?.type !== 'system' || init.subtype !== 'init' || typeof init.session_id !== 'string' || !init.session_id
      || typeof init.cwd !== 'string' || !path.isAbsolute(init.cwd)) {
    throw new Error('native_session_context_mismatch');
  }
  return structuredClone({ contract_version: 'global_owner_scout_native_context_v1', native_host: 'claude', context: init });
}

/** A settled turn is not business success or termination of its chat. */
export function observePiTurn(before, events, after) {
  if (!before.sessionId || before.sessionId !== after.sessionId) throw new Error('native_turn_session_mismatch');
  const boundary = events.at(-1);
  const settled = boundary?.type === 'agent_settled' && typeof boundary.aborted === 'boolean';
  const idle = after.isStreaming === false && after.isCompacting === false && after.pendingMessageCount === 0;
  return { contract_version: 'global_owner_scout_native_turn_v1', native_host: 'pi', unit: 'native_turn',
    status: settled && idle ? boundary.aborted ? 'aborted' : 'settled' : 'open_or_unknown',
    business_success: 'unverified' };
}

export function observeClaudeTurn(init, events) {
  exportClaudeContext(init);
  if (events.some(e => e.session_id && e.session_id !== init.session_id)) throw new Error('native_turn_session_mismatch');
  const boundary = events.at(-1);
  return { contract_version: 'global_owner_scout_native_turn_v1', native_host: 'claude', unit: 'native_turn',
    status: boundary?.type === 'result' && !(boundary.queued_turn_count > 0)
      ? boundary.is_error === false && boundary.subtype === 'success' ? 'result_success'
        : boundary.is_error === true ? 'result_error' : 'open_or_unknown' : 'open_or_unknown',
    business_success: 'unverified' };
}
