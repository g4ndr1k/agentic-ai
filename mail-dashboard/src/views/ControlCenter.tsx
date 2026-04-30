import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { MailActionApproval, useApi } from '../api/mail';

const STATUS_OPTIONS = ['pending', 'approved', 'executed', 'blocked', 'failed', 'rejected', 'expired'];
const EXECUTION_OPTIONS = ['', 'not_requested', 'started', 'stuck', 'executed', 'blocked', 'failed', 'expired', 'rejected'];
const RISK_OPTIONS = ['', 'safe_readonly', 'safe_reversible', 'caution', 'dangerous_blocked', 'unsupported_blocked'];
const UNSUPPORTED_ACTIONS = new Set([
  'send_imessage',
  'reply',
  'auto_reply',
  'forward',
  'delete',
  'expunge',
  'unsubscribe',
  'webhook',
  'external_webhook',
  'notify_dashboard',
]);

function label(value: string | null | undefined) {
  return (value || 'none').replace(/_/g, ' ');
}

function fmt(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : 'n/a';
}

function shortJson(value: any) {
  if (value == null) return 'none';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function stateClass(state: string | undefined) {
  if (state === 'executed') return 'bg-green-900/30 text-green-300';
  if (state === 'blocked') return 'bg-yellow-900/30 text-yellow-300';
  if (state === 'failed' || state === 'stuck') return 'bg-red-900/30 text-red-300';
  if (state === 'started' || state === 'approved') return 'bg-indigo-900/30 text-indigo-300';
  if (state === 'pending' || state === 'not_requested') return 'bg-amber-900/30 text-amber-300';
  return 'bg-gray-800 text-gray-400';
}

function riskClass(risk: string | undefined) {
  if (risk === 'safe_readonly') return 'bg-emerald-950/50 text-emerald-300';
  if (risk === 'safe_reversible') return 'bg-teal-950/50 text-teal-300';
  if (risk === 'caution') return 'bg-amber-950/50 text-amber-300';
  if (risk === 'dangerous_blocked') return 'bg-red-950/60 text-red-300';
  if (risk === 'unsupported_blocked') return 'bg-gray-800 text-gray-300';
  return 'bg-gray-800 text-gray-400';
}

function gateClass(gate: string | undefined) {
  if (gate === 'ready') return 'bg-green-950/50 text-green-300';
  if (gate === 'dry_run') return 'bg-sky-950/50 text-sky-300';
  if (gate === 'mutation_disabled' || gate === 'mode_blocked') return 'bg-amber-950/50 text-amber-300';
  if (gate === 'unsupported' || gate === 'expired' || gate === 'rejected' || gate === 'manual_review_required') return 'bg-red-950/50 text-red-300';
  if (gate === 'terminal') return 'bg-gray-800 text-gray-300';
  return 'bg-gray-800 text-gray-400';
}

function gateLabel(approval: MailActionApproval) {
  const gate = approval.current_gate_preview?.gate;
  if (gate === 'dry_run') return 'Dry-run only';
  if (gate === 'mutation_disabled' || gate === 'mode_blocked') return 'Blocked by config';
  if (gate === 'unsupported') return 'Unsupported action';
  if (gate === 'ready') return approval.current_gate_preview?.capability === 'unknown' ? 'Ready, capability unknown' : 'Ready for gated attempt';
  if (gate === 'manual_review_required') return 'Manual review required';
  if (gate === 'terminal') return 'Already terminal';
  return label(gate || approval.execution_state || approval.status);
}

function nextStep(approval: MailActionApproval) {
  const state = approval.execution_state;
  if (approval.status === 'pending') return 'Review the proposed action. Approval allows one gated attempt.';
  if (state === 'started') return 'Execution started. Wait for a terminal audit event.';
  if (state === 'stuck') return 'Execution started but did not finish. Manual review required.';
  if (state === 'blocked') return 'Blocked by safety gate. No mailbox change was made.';
  if (state === 'failed') return 'Execution failed unexpectedly. Review the error before retry planning.';
  if (state === 'executed') return 'Execution completed and was audited.';
  if (state === 'expired') return 'Expired before execution. Create a fresh suggestion if still needed.';
  if (state === 'rejected') return 'Rejected by operator. No execution attempt is allowed.';
  return 'No execution attempt has been requested.';
}

function supportLabel(actionType: string) {
  if (UNSUPPORTED_ACTIONS.has(actionType)) return 'Blocked in Phase 4D.2';
  if (actionType === 'add_to_needs_reply') return 'Operator action';
  return 'Gate checked at execution';
}

function isTerminal(approval: MailActionApproval) {
  return ['executed', 'blocked', 'failed', 'rejected', 'expired'].includes(approval.status);
}

export default function ControlCenter() {
  const {
    listApprovals,
    getApproval,
    approveApproval,
    rejectApproval,
    executeApproval,
    expireApproval,
    markApprovalFailed,
    previewApprovalCleanup,
    cleanupApprovals,
    archiveApproval,
    unarchiveApproval,
    exportApprovals,
  } = useApi();
  const [viewMode, setViewMode] = useState<'active' | 'history'>('active');
  const [status, setStatus] = useState('pending');
  const [executionState, setExecutionState] = useState('');
  const [riskLevel, setRiskLevel] = useState('');
  const [includeArchived, setIncludeArchived] = useState(false);
  const [approvals, setApprovals] = useState<MailActionApproval[]>([]);
  const [selected, setSelected] = useState<MailActionApproval | null>(null);
  const [cleanupPreview, setCleanupPreview] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Record<string, string>>({});

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listApprovals({
        status,
        execution_state: executionState || undefined,
        risk_level: riskLevel || undefined,
        include_archived: viewMode === 'history' && includeArchived,
        limit: 50,
      });
      setApprovals(rows);
      setCleanupPreview(await previewApprovalCleanup());
      if (selected && rows.some((row) => row.approval_id === selected.approval_id)) {
        setSelected(await getApproval(selected.approval_id));
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, [status, executionState, riskLevel, includeArchived, viewMode]);

  const run = async (approvalId: string, action: string, fn: () => Promise<MailActionApproval>) => {
    setBusy((state) => ({ ...state, [approvalId]: action }));
    setError(null);
    try {
      const updated = await fn();
      setSelected(await getApproval(updated.approval_id));
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy((state) => {
        const next = { ...state };
        delete next[approvalId];
        return next;
      });
    }
  };

  const openDetail = async (approvalId: string) => {
    setError(null);
    try {
      setSelected(await getApproval(approvalId));
    } catch (e: any) {
      setError(e.message);
    }
  };

  const runCleanup = async () => {
    if (!window.confirm('Run explicit approval cleanup? Audit retained. Started/stuck approvals are excluded.')) return;
    setError(null);
    try {
      await cleanupApprovals(true);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const exportJson = async () => {
    setError(null);
    try {
      const payload = await exportApprovals({
        status,
        execution_state: executionState || undefined,
        include_archived: viewMode === 'history' && includeArchived,
        limit: 500,
        include_events: true,
      });
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `approval-audit-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Control Center</h2>
          <p className="text-xs text-gray-500 mt-1 max-w-3xl">
            Approval allows one gated attempt. Blocked, dry-run, failed, and stuck results are audit outcomes, not autonomous action.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg border border-gray-800 bg-gray-950 p-1">
            {(['active', 'history'] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => {
                  setViewMode(mode);
                  if (mode === 'active') setIncludeArchived(false);
                }}
                className={`px-3 py-1.5 rounded-md text-xs font-medium ${viewMode === mode ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-gray-200'}`}
              >
                {label(mode)}
              </button>
            ))}
          </div>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200"
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>{label(option)}</option>
            ))}
          </select>
          <select
            value={executionState}
            onChange={(e) => setExecutionState(e.target.value)}
            className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200"
          >
            {EXECUTION_OPTIONS.map((option) => (
              <option key={option || 'all'} value={option}>{option ? label(option) : 'any execution'}</option>
            ))}
          </select>
          <select
            value={riskLevel}
            onChange={(e) => setRiskLevel(e.target.value)}
            className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200"
          >
            {RISK_OPTIONS.map((option) => (
              <option key={option || 'all'} value={option}>{option ? label(option) : 'any risk'}</option>
            ))}
          </select>
          {viewMode === 'history' && (
            <label className="flex items-center gap-2 text-xs text-gray-400">
              <input type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)} />
              Include archived
            </label>
          )}
          <button onClick={exportJson} className="px-3 py-2 bg-gray-800 text-gray-300 rounded-lg text-sm font-medium hover:bg-gray-700">
            Export JSON
          </button>
          <button onClick={refresh} className="px-3 py-2 bg-gray-800 text-gray-300 rounded-lg text-sm font-medium hover:bg-gray-700">
            Refresh
          </button>
        </div>
      </div>

      {error && <div className="bg-red-900/20 border border-red-900/50 p-3 rounded-lg text-red-400 text-sm">{error}</div>}

      {cleanupPreview && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-gray-500">Cleanup preview is read-only</div>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-300">
                <span>{cleanupPreview.would_expire_pending} pending would expire</span>
                <span>{cleanupPreview.would_archive_terminal} terminal would archive</span>
                <span>{cleanupPreview.would_hard_delete} hard delete</span>
                <span>{cleanupPreview.stuck_or_started_excluded} started/stuck excluded</span>
              </div>
              <div className="text-[11px] text-gray-500 mt-1">
                cleanup {cleanupPreview.cleanup_enabled ? 'enabled' : 'disabled'} / archive after {cleanupPreview.archive_terminal_after_days}d / audit retained {cleanupPreview.retain_audit_days}d
              </div>
            </div>
            <SmallButton muted busy={busy.__cleanup === 'running'} disabled={Boolean(busy.__cleanup)} onClick={() => {
              setBusy((state) => ({ ...state, __cleanup: 'running' }));
              runCleanup().finally(() => setBusy((state) => {
                const next = { ...state };
                delete next.__cleanup;
                return next;
              }));
            }}>
              Run explicit cleanup
            </SmallButton>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-4">
        <div className="space-y-3">
          {loading ? (
            <div className="text-gray-500 text-sm">Loading approvals...</div>
          ) : approvals.length === 0 ? (
            <div className="border border-dashed border-gray-800 rounded-lg p-8 text-center text-sm text-gray-500">
              No {label(status)} approvals
            </div>
          ) : approvals.map((approval) => (
            <ApprovalRow
              key={approval.approval_id}
              approval={approval}
              busy={busy[approval.approval_id]}
              selected={selected?.approval_id === approval.approval_id}
              onOpen={() => openDetail(approval.approval_id)}
              run={run}
              approveApproval={approveApproval}
              rejectApproval={rejectApproval}
              executeApproval={executeApproval}
              expireApproval={expireApproval}
              archiveApproval={archiveApproval}
              unarchiveApproval={unarchiveApproval}
            />
          ))}
        </div>

        <ApprovalDetail
          approval={selected}
          busy={selected ? busy[selected.approval_id] : undefined}
          onClose={() => setSelected(null)}
          onMarkFailed={
            selected
              ? () => run(
                  selected.approval_id,
                  'marking_failed',
                  () => markApprovalFailed(selected.approval_id, 'Marked failed from Control Center after stale started review'),
                )
              : undefined
          }
          onArchive={
            selected
              ? () => run(selected.approval_id, 'archiving', () => archiveApproval(selected.approval_id))
              : undefined
          }
          onUnarchive={
            selected
              ? () => run(selected.approval_id, 'unarchiving', () => unarchiveApproval(selected.approval_id))
              : undefined
          }
        />
      </div>
    </div>
  );
}

function ApprovalRow({
  approval,
  busy,
  selected,
  onOpen,
  run,
  approveApproval,
  rejectApproval,
  executeApproval,
  expireApproval,
  archiveApproval,
  unarchiveApproval,
}: {
  approval: MailActionApproval;
  busy?: string;
  selected: boolean;
  onOpen: () => void;
  run: (approvalId: string, action: string, fn: () => Promise<MailActionApproval>) => Promise<void>;
  approveApproval: (approvalId: string, decision_note?: string) => Promise<MailActionApproval>;
  rejectApproval: (approvalId: string, decision_note?: string) => Promise<MailActionApproval>;
  executeApproval: (approvalId: string) => Promise<MailActionApproval>;
  expireApproval: (approvalId: string) => Promise<MailActionApproval>;
  archiveApproval: (approvalId: string) => Promise<MailActionApproval>;
  unarchiveApproval: (approvalId: string) => Promise<MailActionApproval>;
}) {
  const actionType = approval.action_type || approval.proposed_action_type;
  const state = approval.execution_state || 'not_requested';
  const reason = approval.blocked_reason || approval.execution_error;
  const message = approval.message_context || {};
  const gate = approval.current_gate_preview?.gate;
  const target = approval.target || approval.proposed_target;

  return (
    <div className={`bg-gray-900 border rounded-lg p-4 ${selected ? 'border-indigo-700' : 'border-gray-800'}`}>
      <button className="w-full text-left" onClick={onOpen}>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${stateClass(approval.status)}`}>{label(approval.status)}</span>
          <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${stateClass(state)}`}>{label(state)}</span>
          <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${riskClass(approval.risk_level)}`}>{label(approval.risk_level)}</span>
          <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${gateClass(gate)}`}>{gateLabel(approval)}</span>
          {approval.is_archived && <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-gray-800 text-gray-300">Audit retained</span>}
          <span className="text-xs text-gray-500">{supportLabel(actionType)}</span>
        </div>
        <div className="mt-2 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-sm font-semibold text-gray-100 truncate" title={approval.preview_title || approval.subject || ''}>{approval.preview_title || approval.subject || approval.message_key || approval.approval_id}</h3>
          <span className="text-xs text-gray-500">{message.account_label || approval.account_id || 'no account'}{message.folder || approval.folder ? ` / ${message.folder || approval.folder}` : ''}</span>
        </div>
        <div className="mt-2 grid gap-1 text-xs text-gray-400 sm:grid-cols-2">
          <div className="truncate" title={message.sender || approval.sender || ''}>{message.sender || approval.sender || 'unknown sender'}</div>
          <div className="truncate sm:text-right" title={message.subject || approval.subject || ''}>{message.subject || approval.subject || 'no subject'}</div>
        </div>
        <div className="mt-2 text-sm text-gray-300">
          {label(actionType)}{target ? <span className="text-gray-500"> -&gt; {target}</span> : null}
          <span className="text-xs text-gray-500"> / {message.folder || approval.folder || 'folder ?'} UID {message.imap_uid || approval.imap_uid || '?'}</span>
        </div>
        <div className="mt-2 text-xs text-gray-500">
          {approval.operator_guidance || nextStep(approval)}
          {reason ? <span className="text-gray-400"> Reason: {reason}</span> : null}
        </div>
      </button>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {approval.status === 'pending' && (
          <>
            <SmallButton busy={busy === 'approving'} disabled={Boolean(busy)} onClick={() => run(approval.approval_id, 'approving', () => approveApproval(approval.approval_id, 'Approved from Control Center'))}>
              Approve attempt
            </SmallButton>
            <SmallButton danger busy={busy === 'rejecting'} disabled={Boolean(busy)} onClick={() => run(approval.approval_id, 'rejecting', () => rejectApproval(approval.approval_id, 'Rejected from Control Center'))}>
              Reject
            </SmallButton>
            <SmallButton muted busy={busy === 'expiring'} disabled={Boolean(busy)} onClick={() => run(approval.approval_id, 'expiring', () => expireApproval(approval.approval_id))}>
              Expire
            </SmallButton>
          </>
        )}
        {approval.status === 'approved' && approval.execution_state !== 'started' && approval.execution_state !== 'stuck' && (
          <SmallButton busy={busy === 'executing'} disabled={Boolean(busy)} onClick={() => run(approval.approval_id, 'executing', () => executeApproval(approval.approval_id))}>
            Run gated attempt
          </SmallButton>
        )}
        {isTerminal(approval) && !approval.is_archived && (
          <SmallButton muted busy={busy === 'archiving'} disabled={Boolean(busy)} onClick={() => run(approval.approval_id, 'archiving', () => archiveApproval(approval.approval_id))}>
            Archive from active view
          </SmallButton>
        )}
        {approval.is_archived && (
          <SmallButton muted busy={busy === 'unarchiving'} disabled={Boolean(busy)} onClick={() => run(approval.approval_id, 'unarchiving', () => unarchiveApproval(approval.approval_id))}>
            Unarchive
          </SmallButton>
        )}
      </div>
    </div>
  );
}

function ApprovalDetail({
  approval,
  busy,
  onClose,
  onMarkFailed,
  onArchive,
  onUnarchive,
}: {
  approval: MailActionApproval | null;
  busy?: string;
  onClose: () => void;
  onMarkFailed?: () => void;
  onArchive?: () => void;
  onUnarchive?: () => void;
}) {
  const timeline = useMemo(() => approval?.events || [], [approval]);
  if (!approval) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-sm text-gray-500">
        Select an approval to inspect the planned action, gate result, and audit trail.
      </div>
    );
  }
  const actionType = approval.action_type || approval.proposed_action_type;
  const state = approval.execution_state || 'not_requested';
  const message = approval.message_context || {};
  const gate = approval.current_gate_preview;
  const trigger = approval.trigger_context;
  const rule = approval.rule_context;
  const target = approval.target || approval.proposed_target;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-4 xl:sticky xl:top-4 self-start">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className={`inline-flex px-2 py-0.5 rounded text-[10px] font-medium ${stateClass(state)}`}>{label(state)}</div>
          {approval.is_archived && <div className="inline-flex ml-2 px-2 py-0.5 rounded text-[10px] font-medium bg-gray-800 text-gray-300">Audit retained</div>}
          <h3 className="text-sm font-semibold text-gray-100 mt-2">{approval.preview_title || 'Approval detail'}</h3>
          <p className="text-xs text-gray-500 mt-1">{approval.approval_id}</p>
        </div>
        <button onClick={onClose} className="text-xs text-gray-500 hover:text-gray-300">Close</button>
      </div>

      <Section title="Why this appeared">
        <Info label="Source" value={`${label(approval.source_type)}${approval.trigger_id ? ` / ${approval.trigger_id}` : ''}`} />
        <Info label="Explanation" value={trigger?.reason || rule?.rule_name || approval.reason || 'No trigger detail was stored.'} />
        <Info label="AI signal" value={`${message.classification_category || approval.ai_category || 'n/a'} / urgency ${message.urgency_score ?? approval.ai_urgency_score ?? 'n/a'} / confidence ${message.confidence ?? approval.ai_confidence ?? 'n/a'}`} />
      </Section>

      <Section title="Message context">
        <Info label="Sender" value={message.sender || approval.sender || 'n/a'} />
        <Info label="Subject" value={message.subject || approval.subject || approval.message_id || approval.message_key || 'n/a'} />
        <Info label="Received" value={fmt(message.received_at || approval.received_at)} />
        <Info label="Account / folder" value={`${message.account_label || approval.account_id || 'n/a'} / ${message.folder || approval.folder || 'n/a'}`} />
        <Info label="Mailbox reference" value={`UID ${message.imap_uid || approval.imap_uid || 'n/a'} / UIDVALIDITY ${message.uidvalidity || approval.uidvalidity || 'n/a'}`} />
      </Section>

      <Section title="Proposed action">
        <Info label="Action" value={`${label(actionType)}${target ? ` -> ${target}` : ''}`} />
        <Info label="Guidance" value={approval.operator_guidance || nextStep(approval)} />
        <JsonBlock title="Proposed value" value={approval.proposed_value} />
      </Section>

      <Section title="Safety preview">
        <div className="flex flex-wrap gap-2">
          <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${gateClass(gate?.gate)}`}>{gateLabel(approval)}</span>
          <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${gate?.would_execute_now ? 'bg-green-950/50 text-green-300' : 'bg-amber-950/50 text-amber-300'}`}>
            {gate?.would_execute_now ? 'Approval allows one gated attempt' : 'No mailbox change under current settings'}
          </span>
        </div>
        <Info label="Blocked reason" value={gate?.reason || approval.blocked_reason || 'n/a'} />
        <Info label="Config" value={`mode ${gate?.mode || 'n/a'} / mutations ${gate?.mutation_enabled ?? 'n/a'} / dry-run ${gate?.dry_run_default ?? 'n/a'} / capability ${gate?.capability || 'n/a'}`} />
        {gate?.notes?.length ? <Info label="Notes" value={gate.notes.join(' ')} /> : null}
      </Section>

      <Section title="Risk">
        <Info label="Risk level" value={label(approval.risk_level)} />
        <Info label="Reversibility" value={approval.reversibility || 'n/a'} />
        <Info label="Review before approval" value={(approval.risk_reasons || ['Review message context before approving.']).join(' ')} />
      </Section>

      <Section title="Lifecycle">
        <Info label="Decision" value={`${approval.decided_by || 'n/a'}${approval.decision_note ? ` / ${approval.decision_note}` : ''}`} />
        <Info label="Created / expires" value={`${fmt(approval.created_at)} / ${fmt(approval.expires_at)}`} />
        <Info label="Approved / started" value={`${fmt(approval.approved_at)} / ${fmt(approval.execution_started_at)}`} />
        <Info label="Finished" value={fmt(approval.execution_finished_at || approval.executed_at)} />
        <Info label="Archived" value={fmt(approval.archived_at)} />
      </Section>

      {(approval.blocked_reason || approval.execution_error) && (
        <div className="rounded-lg border border-red-900/40 bg-red-950/20 p-3">
          <div className="text-[10px] uppercase text-red-300">Manual review required</div>
          <div className="text-xs text-red-200 mt-1">{approval.blocked_reason || approval.execution_error}</div>
        </div>
      )}

      <JsonBlock title="Gate result" value={approval.gate_result || approval.execution_result} />
      <JsonBlock title="Trigger context" value={trigger} />
      <JsonBlock title="Rule context" value={rule} />

      {state === 'stuck' && onMarkFailed && (
        <SmallButton danger busy={busy === 'marking_failed'} disabled={Boolean(busy)} onClick={onMarkFailed}>
          Mark failed after review
        </SmallButton>
      )}

      {isTerminal(approval) && !approval.is_archived && onArchive && (
        <SmallButton muted busy={busy === 'archiving'} disabled={Boolean(busy)} onClick={onArchive}>
          Archive from active view
        </SmallButton>
      )}

      {approval.is_archived && onUnarchive && (
        <SmallButton muted busy={busy === 'unarchiving'} disabled={Boolean(busy)} onClick={onUnarchive}>
          Unarchive
        </SmallButton>
      )}

      <div>
        <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-2">Audit trail</div>
        <div className="space-y-2 max-h-72 overflow-auto pr-1">
          {timeline.length === 0 ? (
            <div className="text-xs text-gray-500">No audit events found.</div>
          ) : timeline.map((event) => (
            <div key={event.id} className="border border-gray-800 rounded-lg p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-gray-200">{label(event.event_type)}</span>
                <span className="text-[10px] text-gray-500">{fmt(event.created_at)}</span>
              </div>
              <div className="text-[10px] text-gray-500 mt-1">{label(event.outcome)} / event #{event.id}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="text-[10px] uppercase tracking-wider text-gray-500">{title}</div>
      <div className="space-y-2">
        {children}
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className="text-xs text-gray-200 mt-1 break-words">{value}</div>
    </div>
  );
}

function JsonBlock({ title, value }: { title: string; value: any }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">{title}</div>
      <pre className="max-h-36 overflow-auto rounded-lg border border-gray-800 bg-gray-950/60 p-2 text-[11px] text-gray-300 whitespace-pre-wrap break-words">
        {shortJson(value)}
      </pre>
    </div>
  );
}

function SmallButton({
  children,
  onClick,
  disabled,
  busy,
  danger,
  muted,
}: {
  children: string;
  onClick: () => void;
  disabled?: boolean;
  busy?: boolean;
  danger?: boolean;
  muted?: boolean;
}) {
  const color = danger
    ? 'bg-red-950/50 text-red-300 hover:bg-red-900/60'
    : muted
      ? 'bg-gray-800 text-gray-300 hover:bg-gray-700'
      : 'bg-indigo-600 text-white hover:bg-indigo-500';
  return (
    <button onClick={onClick} disabled={disabled} className={`px-3 py-2 rounded-lg text-sm font-medium disabled:opacity-50 ${color}`}>
      {busy ? 'Working...' : children}
    </button>
  );
}
