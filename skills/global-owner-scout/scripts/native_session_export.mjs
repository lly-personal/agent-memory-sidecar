/** Mechanically export the current Pi SDK session; no filesystem or project discovery. */
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
