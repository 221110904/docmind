import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import { locationLabel, splitCitations } from "../citations";
import type { AskOut, DocumentOut } from "../types";
import { ScopeSelect } from "./ScopeSelect";

interface Props {
  docs: DocumentOut[];
  loaded: boolean;
}

export function Ask({ docs, loaded }: Props) {
  const questionId = useId();
  const [question, setQuestion] = useState("");
  const [scope, setScope] = useState("");
  const [thorough, setThorough] = useState(false);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<AskOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  // `tick` changes on every click so the marker sweeps again, even on the same source
  const [active, setActive] = useState<{ number: number; tick: number } | null>(null);
  const latest = useRef(0);

  const hasReadyDocs = docs.some((d) => d.status === "indexed");

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = question.trim();
    if (!text || pending) return;
    const id = ++latest.current;
    setPending(true);
    setError(null);
    setActive(null);
    try {
      const answer = await api.ask(text, thorough ? 10 : 5, scope || undefined);
      if (id === latest.current) setResult(answer);
    } catch (e) {
      if (id === latest.current) {
        setResult(null);
        setError(e instanceof ApiError ? e.message : "The question could not be answered.");
      }
    } finally {
      if (id === latest.current) setPending(false);
    }
  }

  const valid = useMemo(() => new Set(result?.sources.map((s) => s.number) ?? []), [result]);
  const pieces = useMemo(
    () => (result?.found ? splitCitations(result.answer, valid) : []),
    [result, valid],
  );

  useEffect(() => {
    if (!active) return;
    const element = document.getElementById(`source-${active.number}`);
    const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    element?.scrollIntoView?.({ block: "nearest", behavior: calm ? "auto" : "smooth" });
  }, [active]);

  return (
    <section className="ask" aria-labelledby="ask-title">
      <div className="ask-main">
        <h1 id="ask-title">Ask your documents</h1>

        {loaded && !hasReadyDocs && (
          <p className="empty">
            No document is ready yet. <a href="#documents">Add one</a> and come back with a
            question.
          </p>
        )}

        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor={questionId}>Your question</label>
            <textarea
              id={questionId}
              rows={3}
              value={question}
              dir="auto"
              placeholder="For example: can staff use personal USB drives?"
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) void submit();
              }}
            />
          </div>
          <div className="controls">
            <ScopeSelect docs={docs} value={scope} onChange={setScope} />
            <label className="check">
              <input
                type="checkbox"
                checked={thorough}
                onChange={(e) => setThorough(e.target.checked)}
              />
              Check more passages
            </label>
            <button type="submit" className="primary" disabled={pending || !question.trim()}>
              {pending ? "Asking…" : "Ask"}
            </button>
          </div>
        </form>

        <div className="result" aria-live="polite">
          {pending && <p className="muted">Reading your documents…</p>}
          {error && (
            <p className="notice" role="alert">
              {error}
            </p>
          )}
          {!pending && result?.found && (
            <div className="answer" dir="auto">
              {pieces.map((piece, index) =>
                piece.kind === "text" ? (
                  <span key={index}>{piece.text}</span>
                ) : (
                  <button
                    key={index}
                    type="button"
                    className="cite"
                    aria-label={`Show source ${piece.number}`}
                    onClick={() => setActive({ number: piece.number, tick: Date.now() })}
                  >
                    {piece.number}
                  </button>
                ),
              )}
            </div>
          )}
          {!pending && result && !result.found && (
            <div className="not-found">
              <p dir="auto">{result.answer}</p>
              <p className="muted">
                Try other words, or choose the document you expect the answer to be in.
              </p>
            </div>
          )}
        </div>
      </div>

      <aside className="evidence" aria-label="Sources">
        <h2>Sources</h2>
        {!result?.found || result.sources.length === 0 ? (
          <p className="muted">
            Each answer links to the passages it is built from, so you can check it.
          </p>
        ) : (
          <ol className="sources">
            {result.sources.map((source) => {
              const isActive = active?.number === source.number;
              const place = locationLabel(source.label);
              return (
                <li
                  key={source.number}
                  id={`source-${source.number}`}
                  className="source"
                  data-active={isActive}
                >
                  <div className="source-head">
                    <span className="source-num">{source.number}</span>
                    <span className="source-file">{source.filename}</span>
                    {place && <span className="source-place">{place}</span>}
                  </div>
                  <p className="passage" dir="auto">
                    <span
                      key={isActive ? active.tick : "idle"}
                      className={isActive ? "marked" : undefined}
                    >
                      {source.content}
                    </span>
                  </p>
                </li>
              );
            })}
          </ol>
        )}
      </aside>
    </section>
  );
}
