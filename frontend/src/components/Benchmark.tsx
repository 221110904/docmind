import { useId, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import type { BenchmarkOut, CandidatesOut, DocumentOut } from "../types";

interface Props {
  docs: DocumentOut[];
  loaded: boolean;
}

const MAX_SOURCES = 4;
const LABELS = { missing: "Missing", partial: "Partly covered", covered: "Covered" } as const;

export function Benchmark({ docs, loaded }: Props) {
  const docId = useId();
  const addId = useId();
  const ready = docs.filter((d) => d.status === "indexed");
  const [documentId, setDocumentId] = useState("");
  const [found, setFound] = useState<CandidatesOut | null>(null);
  const [extra, setExtra] = useState<string[]>([]);
  const [chosen, setChosen] = useState<string[]>([]);
  const [addText, setAddText] = useState("");
  const [result, setResult] = useState<BenchmarkOut | null>(null);
  const [pending, setPending] = useState<"search" | "run" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  const selected = documentId || ready[0]?.id || "";

  function reset(id: string) {
    latest.current++; // ignore anything still on its way for the old document
    setDocumentId(id);
    setFound(null);
    setExtra([]);
    setChosen([]);
    setResult(null);
    setError(null);
    setPending(null);
  }

  async function findSources(event?: FormEvent) {
    event?.preventDefault();
    if (!selected || pending) return;
    const id = ++latest.current;
    setPending("search");
    setError(null);
    setResult(null);
    try {
      const out = await api.benchmarkCandidates(selected);
      if (id !== latest.current) return;
      setFound(out);
      setChosen([]);
      setExtra([]);
    } catch (e) {
      if (id === latest.current) {
        setFound(null);
        setError(e instanceof ApiError ? e.message : "The search failed.");
      }
    } finally {
      if (id === latest.current) setPending(null);
    }
  }

  function toggle(url: string) {
    setChosen((now) =>
      now.includes(url)
        ? now.filter((u) => u !== url)
        : now.length < MAX_SOURCES
          ? [...now, url]
          : now,
    );
  }

  function addOwn(event: FormEvent) {
    event.preventDefault();
    const url = addText.trim();
    if (!url) return;
    if (!/^https?:\/\//i.test(url)) {
      setError("Addresses must start with http:// or https://");
      return;
    }
    setError(null);
    setAddText("");
    const known = new Set([...(found?.candidates.map((c) => c.url) ?? []), ...extra]);
    if (!known.has(url)) setExtra((now) => [...now, url]);
    setChosen((now) => (now.includes(url) || now.length >= MAX_SOURCES ? now : [...now, url]));
  }

  async function run() {
    if (!selected || chosen.length === 0 || pending) return;
    const id = ++latest.current;
    setPending("run");
    setError(null);
    try {
      const out = await api.benchmarkRun(selected, chosen);
      if (id === latest.current) setResult(out);
    } catch (e) {
      if (id === latest.current) {
        setResult(null);
        setError(e instanceof ApiError ? e.message : "The comparison failed.");
      }
    } finally {
      if (id === latest.current) setPending(null);
    }
  }

  const rows = [
    ...(found?.candidates ?? []).map((c) => ({ url: c.url, title: c.title, note: `${c.domain} · ${c.snippet}` })),
    ...extra.map((u) => ({ url: u, title: u, note: "added by you" })),
  ];

  return (
    <section className="benchmark" aria-labelledby="bench-title">
      <h1 id="bench-title">Benchmark a document</h1>
      <p className="muted">
        Compare your document with similar ones published by other organisations, and see what
        is missing or weak. DocMind suggests pages; you choose which ones to compare against.
      </p>

      {loaded && ready.length === 0 && (
        <p className="empty">
          No document is ready yet. <a href="#documents">Add and index one</a> first.
        </p>
      )}

      {ready.length > 0 && (
        <>
          <form onSubmit={findSources}>
            <div className="field">
              <label htmlFor={docId}>1. Your document</label>
              <select id={docId} value={selected} onChange={(e) => reset(e.target.value)}>
                {ready.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename}
                  </option>
                ))}
              </select>
            </div>
            <div className="controls">
              <button type="submit" className="primary" disabled={pending !== null}>
                {pending === "search" ? "Searching…" : found ? "Search again" : "Find similar documents"}
              </button>
            </div>
          </form>

          {found && (
            <div className="bench-step">
              <h2>2. Choose up to {MAX_SOURCES} to compare against</h2>
              <p className="muted">
                Searched for: {found.queries.join(" · ")}. Open a page to check it is what you
                want. Pages that need a login or block automated reading cannot be used.
              </p>
              {rows.length === 0 && <p className="empty">No results. Add a web address below.</p>}
              <ul className="bench-candidates">
                {rows.map((row) => (
                  <li key={row.url}>
                    <label className="check">
                      <input
                        type="checkbox"
                        checked={chosen.includes(row.url)}
                        disabled={!chosen.includes(row.url) && chosen.length >= MAX_SOURCES}
                        onChange={() => toggle(row.url)}
                      />
                      <span>
                        <strong dir="auto">{row.title}</strong>
                        <br />
                        <span className="muted" dir="auto">{row.note}</span>
                      </span>
                    </label>{" "}
                    <a href={row.url} target="_blank" rel="noopener noreferrer">
                      Open
                    </a>
                  </li>
                ))}
              </ul>
              <form onSubmit={addOwn} className="controls">
                <div className="field">
                  <label htmlFor={addId}>Or add a web address</label>
                  <input
                    id={addId}
                    type="url"
                    value={addText}
                    placeholder="https://…"
                    onChange={(e) => setAddText(e.target.value)}
                  />
                </div>
                <button type="submit" disabled={!addText.trim()}>
                  Add
                </button>
              </form>
              <div className="controls">
                <button
                  type="button"
                  className="primary"
                  disabled={chosen.length === 0 || pending !== null}
                  onClick={() => void run()}
                >
                  {pending === "run" ? "Comparing…" : `Compare with ${chosen.length} selected`}
                </button>
              </div>
            </div>
          )}
        </>
      )}

      <div className="result" aria-live="polite">
        {pending === "run" && <p className="muted">Reading the pages and comparing. This can take a minute.</p>}
        {error && (
          <p className="notice" role="alert">
            {error}
          </p>
        )}
        {result && pending !== "run" && <Report out={result} />}
      </div>
    </section>
  );
}

function Report({ out }: { out: BenchmarkOut }) {
  const { summary } = out;
  return (
    <div className="bench-report">
      <h2>3. Result</h2>
      <p>
        <strong>{summary.missing}</strong> missing · <strong>{summary.partial}</strong> partly
        covered · <strong>{summary.covered}</strong> covered, out of {summary.total} points found
        in the chosen documents.
      </p>
      <p className="muted">
        This is guidance, not a verdict. Check each suggestion against the source before changing
        your document.
      </p>
      <table className="bench-table">
        <thead>
          <tr>
            <th>Status</th>
            <th>Topic</th>
            <th>What to change</th>
            <th>Seen in</th>
          </tr>
        </thead>
        <tbody>
          {out.items.map((item, index) => (
            <tr key={index} data-status={item.status}>
              <td>
                <span className="badge" data-status={item.status}>
                  {LABELS[item.status]}
                </span>
              </td>
              <td dir="auto">
                <strong>{item.topic}</strong>
                <br />
                <span className="muted">{item.expected}</span>
              </td>
              <td dir="auto">
                {item.status === "covered" ? (
                  <span className="muted">Nothing to change.</span>
                ) : (
                  <>
                    <p>{item.gap}</p>
                    {item.suggested_edit && (
                      <blockquote className="suggested">{item.suggested_edit}</blockquote>
                    )}
                  </>
                )}
                {item.your_evidence.length > 0 && (
                  <details>
                    <summary>Where your document says this</summary>
                    {item.your_evidence.map((e, i) => (
                      <p key={i} className="passage">
                        <span className="muted">Page {e.page_number}: </span>
                        {e.content}
                      </p>
                    ))}
                  </details>
                )}
              </td>
              <td>
                {item.peers.map((p, i) => (
                  <div key={i}>
                    <a href={p.url} target="_blank" rel="noopener noreferrer">
                      {p.title}
                    </a>
                    {p.page ? ` (p. ${p.page})` : ""}
                  </div>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Sources used</h3>
      <ul>
        {out.sources.map((s) => (
          <li key={s.number}>
            <a href={s.url} target="_blank" rel="noopener noreferrer">
              {s.title}
            </a>{" "}
            {s.status === "read" ? (
              <span className="muted">read{s.truncated ? " (long: only the first part was compared)" : ""}</span>
            ) : (
              <span className="notice-inline">could not be used: {s.detail}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
