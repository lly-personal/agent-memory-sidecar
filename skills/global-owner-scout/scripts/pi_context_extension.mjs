import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {exportPiContext, exportPiSession} from './native_session_export.mjs';
import {resolvePython, helper} from './native_runtime.mjs';
const skillRoot = fileURLToPath(new URL('../', import.meta.url));

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
