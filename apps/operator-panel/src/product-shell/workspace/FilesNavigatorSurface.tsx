import { FileCode2, FileText, FolderLock, RefreshCw, Search } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { artifactBridge } from '../../artifact-workspace/artifactBridge';
import type { ArtifactDescriptor } from '../../artifact-workspace/artifactContracts';

export function FilesNavigatorSurface({
  onOpenArtifact,
}: {
  onOpenArtifact: (artifactId: string) => void;
}) {
  const [items, setItems] = useState<ArtifactDescriptor[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const result = await artifactBridge.list({ limit: 100 });
      setItems(result.items);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Governed artifact catalog is unavailable.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return items;
    return items.filter((item) => (
      item.title.toLocaleLowerCase().includes(needle)
      || item.artifactId.toLocaleLowerCase().includes(needle)
      || item.kind.toLocaleLowerCase().includes(needle)
    ));
  }, [items, query]);

  return (
    <section className="files-navigator-surface" aria-label="Governed files navigator">
      <header>
        <div>
          <strong><FolderLock size={16} />Files</strong>
          <span>Governed artifact library</span>
        </div>
        <button type="button" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={14} />{loading ? 'Loading…' : 'Refresh'}
        </button>
      </header>
      <label className="files-navigator-search">
        <Search size={14} />
        <span className="sr-only">Search governed files</span>
        <input
          type="search"
          aria-label="Search governed files"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search artifacts"
        />
      </label>
      {error ? <p role="alert">{error}</p> : null}
      <div className="files-navigator-list">
        {filtered.map((item) => {
          const ItemIcon = item.kind === 'code' ? FileCode2 : FileText;
          return (
            <button
              type="button"
              key={item.artifactId}
              onClick={() => onOpenArtifact(item.artifactId)}
              aria-label={`${item.title}, ${item.kind}, ${item.status}`}
            >
              <ItemIcon size={16} />
              <span><strong>{item.title}</strong><small>{item.kind} · {item.status}</small></span>
              <time dateTime={item.updatedAtUtc}>{new Date(item.updatedAtUtc).toLocaleString()}</time>
            </button>
          );
        })}
        {!loading && !error && filtered.length === 0 ? <p>No governed artifacts match this filter.</p> : null}
      </div>
      <p className="native-policy-note">
        This navigator exposes only canonical artifacts. Arbitrary project filesystem access is not enabled without a registered safe read capability.
      </p>
    </section>
  );
}
