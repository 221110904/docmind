import { useId, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import { locationLabel } from "../citations";
import type { DocumentOut, SearchHit } from "../types";
import { ScopeSelect } from "./ScopeSelect";

interface Props {
  docs: DocumentOut[];
  loaded: boolean;
}

export function Search({ docs, loaded }: Props) {
  const queryId = useId();
  const countId = useId();
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState("");
  const [count, setCount] = useState(5);
  const [pending, setPending] = useState(false);
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hasReadyDocs = docs.some((d) => d.status === "indexed");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (!text || pending) return;
    setPending(true);
    setError(null);
    try {
      setHits(await api.search(text, count, scope || undefined));
    } catch (e) {
      setHits(null);
      setError(e instanceof ApiError ? e.message : "The search could not be run.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="search-title">
      <h1 id="search-title">Search</h1>
      <p className="lede">
        See the passages that match, best first, without a written answer. Useful for checking
        what the documents actually say.
      </p>

      {loaded && !hasReadyDocs && (
        <p className="empty">
          No document is ready yet. <a href="#documents">Add one</a> to search it.
        </p>
      )}

      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor={queryId}>Search for</label>
          <input
            id={queryId}
            type="search"
            dir="auto"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="controls">
          <ScopeSelect docs={docs} value={scope} onChange={setScope} />
          <div className="field">
            <label htmlFor={countId}>Show</label>
            <select id={countId} value={count} onChange={(e) => setCount(Number(e.target.value))}>
              <option value={5}>5 passages</option>
              <option value={10}>10 passages</option>
              <option value={20}>20 passages</option>
            </select>
          </div>
          <button type="submit" className="primary" disabled={pending || !query.trim()}>
            {pending ? "Searching…" : "Search"}
          </button>
        </div>
      </form>

      <div aria-live="polite">
        {error && (
          <p className="notice" role="alert">
            {error}
          </p>
        )}
        {hits && hits.length === 0 && (
          <p className="empty">
            No matches. Check that the document shows Ready on the Documents screen.
          </p>
        )}
        {hits && hits.length > 0 && (
          <ol className="sources results">
            {hits.map((hit, index) => {
              const place = locationLabel(hit.label);
              return (
                <li key={`${hit.document_id}-${hit.chunk_index}`} className="source">
                  <div className="source-head">
                    <span className="source-num">{index + 1}</span>
                    <span className="source-file">{hit.filename}</span>
                    {place && <span className="source-place">{place}</span>}
                  </div>
                  <p className="passage" dir="auto">
                    {hit.content}
                  </p>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </section>
  );
}
