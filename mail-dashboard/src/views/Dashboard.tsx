import { useState } from 'react';
import { useApi } from '../api/mail';
import KpiCard from '../components/KpiCard';
import SourceSplit from '../components/SourceSplit';
import ClassificationList from '../components/ClassificationList';
import ActionsList from '../components/ActionsList';
import EmptyState from '../components/EmptyState';

export default function Dashboard() {
  const { summary, recent, loading, error, refresh, triggerRun, reprocessMessage } = useApi();
  const [reprocessState, setReprocessState] = useState<Record<string, string>>({});

  if (loading && !summary) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-gray-500">Loading...</div>
      </div>
    );
  }

  if (error && !summary) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center">
          <p className="text-red-400">Connection Error</p>
          <p className="text-gray-600 text-sm mt-2">{error}</p>
          <button
            onClick={refresh}
            className="mt-4 px-4 py-2 bg-gray-800 text-gray-300 rounded-lg text-sm hover:bg-gray-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const mode = summary?.mode || 'draft_only';
  const modeLabel =
    mode === 'observe'
      ? 'Observe Mode'
      : mode === 'live'
      ? 'Live Mode'
      : 'Draft-Only Mode';
  const modeColor =
    mode === 'observe'
      ? 'bg-yellow-900 text-yellow-300'
      : mode === 'live'
      ? 'bg-green-900 text-green-300'
      : 'bg-blue-900 text-blue-300';

  const sources = summary?.source_split || { gmail: 0, outlook: 0 };
  const activeSources = [
    sources.gmail > 0 ? 'Gmail' : null,
    sources.outlook > 0 ? 'Outlook' : null,
  ]
    .filter(Boolean)
    .join(' + ');

  const reprocess = async (messageId: string) => {
    setReprocessState((state) => ({ ...state, [messageId]: 'queueing' }));
    try {
      const result = await reprocessMessage(messageId);
      setReprocessState((state) => ({ ...state, [messageId]: result.status }));
      setTimeout(() => refresh(), 1500);
    } catch (e: any) {
      setReprocessState((state) => ({ ...state, [messageId]: e.message || 'failed' }));
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-gray-500 text-sm">
            Active sources: {activeSources || 'None configured'}
          </p>
        </div>
        <div 
          className="flex items-center gap-3"
          style={{ WebkitAppRegion: 'no-drag' } as any}
        >
          <span
            className={`px-3 py-1 rounded-full text-xs font-medium ${modeColor}`}
          >
            {modeLabel}
          </span>
          <button
            onClick={refresh}
            className="px-4 py-2 bg-gray-800 text-gray-300 rounded-lg text-sm hover:bg-gray-700 transition-colors"
          >
            Refresh
          </button>
          <button
            onClick={triggerRun}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-500 transition-colors"
          >
            Run Now
          </button>
        </div>
      </div>

      {/* Row 1 — Four KPI cards */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard
          icon="📧"
          label="Total Processed"
          value={summary?.total_processed || 0}
          subline={`${sources.gmail} Gmail · ${sources.outlook} Outlook`}
        />
        <KpiCard
          icon="🚨"
          label="Urgent"
          value={summary?.urgent_count || 0}
        />
        <KpiCard
          icon="📝"
          label="Drafts Created"
          value={summary?.drafts_created || 0}
        />
        <KpiCard
          icon="📊"
          label="Avg Priority"
          value={
            summary?.avg_priority !== undefined
              ? `${summary.avg_priority.toFixed(1)}/10`
              : '0/10'
          }
          subline="Mean AI priority score"
        />
      </div>

      {/* Row 2 — Three analytic cards */}
      <div className="grid grid-cols-3 gap-4">
        <SourceSplit gmail={sources.gmail} outlook={sources.outlook} />
        <ClassificationList
          classification={summary?.classification || {}}
        />
        <ActionsList actions={summary?.actions || {
          drafts_created: 0,
          labels_applied: 0,
          imessage_alerts: 0,
          important_count: 0,
          reply_needed_count: 0,
        }} />
      </div>

      {/* Row 3 — Activity / empty state */}
      {recent.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">
            Recent Activity
          </h3>
          <div className="space-y-2">
            {recent.map((email) => (
              <div
                key={email.bridge_id}
                className="py-3 border-b border-gray-800 last:border-0"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-200 truncate">
                      {email.summary || email.category}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {email.source} · {email.provider} ·{' '}
                      {new Date(email.processed_at).toLocaleString()}
                    </p>
                    <div className="mt-2 rounded-lg border border-gray-800 bg-gray-950/50 p-3">
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="text-gray-500">AI</span>
                        <span className="px-2 py-0.5 rounded bg-gray-800 text-gray-300">
                          {email.ai_status || 'Not analyzed'}
                        </span>
                        {email.ai_category && (
                          <span className="text-gray-400">{email.ai_category.replace(/_/g, ' ')}</span>
                        )}
                        {email.ai_urgency_score !== null && email.ai_urgency_score !== undefined && (
                          <span className="text-gray-400">urgency {email.ai_urgency_score}/10</span>
                        )}
                        {email.ai_confidence !== null && email.ai_confidence !== undefined && (
                          <span className="text-gray-400">confidence {Math.round(email.ai_confidence * 100)}%</span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 mt-1">
                        {email.ai_summary || email.ai_last_error || 'Not analyzed'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${
                        email.urgency === 'high'
                          ? 'bg-red-900 text-red-300'
                          : email.urgency === 'medium'
                          ? 'bg-yellow-900 text-yellow-300'
                          : 'bg-gray-800 text-gray-400'
                      }`}
                    >
                      {email.urgency}
                    </span>
                    <span className="text-xs text-gray-500">
                      {email.category.replace(/_/g, ' ')}
                    </span>
                    <button
                      onClick={() => reprocess(email.message_id || email.bridge_id)}
                      className="text-xs px-2 py-1 rounded bg-gray-800 text-gray-300 hover:bg-gray-700"
                    >
                      {reprocessState[email.message_id] || 'Reprocess'}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
