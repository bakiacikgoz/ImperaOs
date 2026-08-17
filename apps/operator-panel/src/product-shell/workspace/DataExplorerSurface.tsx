import { Activity, Database, FileText, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { fetchControlPlaneSnapshot, tailEvents } from '../../bridge';
import type { ControlPlaneSnapshot } from '../../control-plane/types';
import { loadSettings } from '../../settings';
import { productWorkspaceClient, type ProductTaskLink } from '../adapters/productWorkspaceClient';

type EventRow = {
  id: string;
  runId: string;
  kind: string;
  message: string;
  timestamp: string;
};

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : {};
}

function text(source: Record<string, unknown>, keys: string[], fallback: string): string {
  for (const key of keys) {
    if (typeof source[key] === 'string' && source[key]) return source[key];
  }
  return fallback;
}

function eventRow(value: unknown, runId: string, index: number): EventRow {
  const source = record(value);
  return {
    id: text(source, ['event_id', 'eventId', 'id'], `${runId}-${index}`),
    runId,
    kind: text(source, ['event_type', 'eventType', 'kind', 'type'], 'event'),
    message: text(source, ['message', 'summary', 'detail'], 'Governed event received'),
    timestamp: text(source, ['timestamp_utc', 'timestampUtc', 'timestamp', 'created_at_utc'], ''),
  };
}

export function DataExplorerSurface({ taskId }: { taskId: string }) {
  const [snapshot, setSnapshot] = useState<ControlPlaneSnapshot | null>(null);
  const [links, setLinks] = useState<ProductTaskLink[]>([]);
  const [events, setEvents] = useState<EventRow[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [settings] = useState(() => loadSettings());

  const load = useCallback(async () => {
    setLoading(true);
    setErrors([]);
    const [snapshotResult, linkResult] = await Promise.allSettled([
      fetchControlPlaneSnapshot(settings),
      productWorkspaceClient.listLinks(taskId),
    ]);
    const nextErrors: string[] = [];
    if (snapshotResult.status === 'fulfilled') {
      setSnapshot(snapshotResult.value);
    } else {
      setSnapshot(null);
      nextErrors.push(snapshotResult.reason instanceof Error ? snapshotResult.reason.message : 'Control-plane snapshot unavailable.');
    }
    if (linkResult.status === 'fulfilled') {
      setLinks(linkResult.value.links);
      const runIds = [...new Set(
        linkResult.value.links
          .filter((link) => link.targetType === 'run' || link.targetType === 'team_job')
          .map((link) => link.targetId),
      )].slice(0, 5);
      const eventResults = await Promise.allSettled(
        runIds.map(async (runId) => ({
          runId,
          stream: await tailEvents(settings, runId, 0, 64 * 1024, 100),
        })),
      );
      const nextEvents: EventRow[] = [];
      eventResults.forEach((result) => {
        if (result.status === 'fulfilled') {
          result.value.stream.events.forEach((event, index) => {
            nextEvents.push(eventRow(event, result.value.runId, index));
          });
        } else {
          nextErrors.push(result.reason instanceof Error ? result.reason.message : 'Linked run events unavailable.');
        }
      });
      setEvents(nextEvents.slice(0, 250));
    } else {
      setLinks([]);
      setEvents([]);
      nextErrors.push(linkResult.reason instanceof Error ? linkResult.reason.message : 'Task links unavailable.');
    }
    setErrors([...new Set(nextErrors)]);
    setLoading(false);
  }, [settings, taskId]);

  useEffect(() => { void load(); }, [load]);

  const runLinks = links.filter((link) => link.targetType === 'run' || link.targetType === 'team_job');
  const artifactLinks = links.filter((link) => link.targetType === 'artifact');
  const sourceMode = snapshot?.dataSource?.mode ?? 'unavailable';
  const logRows = snapshot?.logs?.slice(0, 50) ?? [];

  return (
    <section className="data-explorer-surface" aria-label="Governed data explorer">
      <header>
        <div><strong><Database size={16} />Data</strong><span>Task-scoped runtime projections</span></div>
        <button type="button" disabled={loading} onClick={() => void load()}>
          <RefreshCw size={14} />{loading ? 'Loading…' : 'Refresh'}
        </button>
      </header>
      {errors.length ? <p role="alert">{errors.join(' · ')}</p> : null}
      <div className="data-explorer-metrics" aria-label="Runtime data summary">
        <article><span>Source</span><strong>{sourceMode}</strong></article>
        <article><span>Runs</span><strong>{snapshot?.runs?.length ?? 0}</strong></article>
        <article><span>Approvals</span><strong>{snapshot?.approvals?.length ?? 0}</strong></article>
        <article><span>Evidence</span><strong>{snapshot?.evidencePacks?.length ?? 0}</strong></article>
        <article><span>Agents</span><strong>{snapshot?.agents?.length ?? 0}</strong></article>
      </div>
      <div className="data-explorer-grid">
        <article>
          <h3><Activity size={15} />Linked runs and events</h3>
          <div className="data-chip-row">
            {runLinks.map((link) => <span key={link.linkId}>{link.targetId}</span>)}
            {!runLinks.length ? <span>No linked run</span> : null}
          </div>
          <div className="data-table-wrap">
            <table>
              <thead><tr><th>Event</th><th>Run</th><th>Message</th><th>Time</th></tr></thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.id}>
                    <td>{event.kind}</td><td>{event.runId}</td><td>{event.message}</td>
                    <td>{event.timestamp ? new Date(event.timestamp).toLocaleString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!events.length && !loading ? <p>No bounded event rows are available for linked runs.</p> : null}
          </div>
        </article>
        <article>
          <h3><FileText size={15} />Snapshot and artifacts</h3>
          <p>{artifactLinks.length} linked artifact{artifactLinks.length === 1 ? '' : 's'}</p>
          <ul>
            {artifactLinks.map((link) => <li key={link.linkId}>{link.targetId}</li>)}
          </ul>
          <h4>Recent governed logs</h4>
          <ul className="data-log-list">
            {logRows.map((log) => (
              <li key={log.eventId}>
                <strong>{log.severity ?? 'info'}</strong>
                <span>{log.message}</span>
              </li>
            ))}
          </ul>
          {!logRows.length && !loading ? <p>No governed log rows are present in the snapshot.</p> : null}
        </article>
      </div>
      <p className="native-policy-note">
        Read-only projections only. Ad-hoc query execution stays unavailable until a governed query provider is registered.
      </p>
    </section>
  );
}
