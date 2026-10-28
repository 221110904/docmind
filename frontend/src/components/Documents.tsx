import { useRef, useState } from "react";
import { api } from "../api";
import { formatSize, statusText, statusTone } from "../citations";
import { ingest, processExisting, type Step } from "../pipeline";
import type { DocumentOut } from "../types";

const ALLOWED = [".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg"];
const MAX_MB = 25;

const STEP_TEXT: Record<Step, string> = {
  uploading: "Uploading",
  reading: "Reading the text",
  indexing: "Making it searchable",
};

interface Job {
  key: number;
  name: string;
  step: Step | null;
  error: string | null;
}

interface Props {
  docs: DocumentOut[];
  onChange: () => Promise<void> | void;
}

function problemWith(file: File): string | null {
  const dot = file.name.lastIndexOf(".");
  const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (!ALLOWED.includes(ext)) {
    return "Only PDF, Word, PowerPoint, Excel, PNG and JPG files can be added.";
  }
  if (file.size > MAX_MB * 1024 * 1024) return `This file is larger than ${MAX_MB} MB.`;
  return null;
}

export function Documents({ docs, onChange }: Props) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [dragging, setDragging] = useState(false);
  const nextKey = useRef(1);
  const input = useRef<HTMLInputElement>(null);

  const update = (key: number, patch: Partial<Job>) =>
    setJobs((all) => all.map((j) => (j.key === key ? { ...j, ...patch } : j)));
  const remove = (key: number) => setJobs((all) => all.filter((j) => j.key !== key));

  async function run(name: string, work: (onStep: (s: Step) => void) => Promise<unknown>) {
    const key = nextKey.current++;
    setJobs((all) => [...all, { key, name, step: null, error: null }]);
    try {
      await work((step) => update(key, { step }));
      remove(key);
    } catch (error) {
      update(key, {
        step: null,
        error: error instanceof Error ? error.message : "Something went wrong.",
      });
    }
    await onChange();
  }

  async function addFiles(files: File[]) {
    // One at a time keeps the free-tier OCR and embedding limits comfortable
    for (const file of files) {
      const problem = problemWith(file);
      if (problem) {
        const key = nextKey.current++;
        setJobs((all) => [...all, { key, name: file.name, step: null, error: problem }]);
        continue;
      }
      await run(file.name, (onStep) =>
        ingest(
          file,
          { upload: api.uploadDocument, process: api.processDocument, index: api.indexDocument },
          onStep,
        ),
      );
    }
  }

  const busy = new Set(jobs.filter((j) => !j.error).map((j) => j.name));

  return (
    <section aria-labelledby="documents-title">
      <h1 id="documents-title">Documents</h1>
      <p className="lede">
        Add files and they become searchable. Scans and photos are read with text recognition.
      </p>

      <label
        className="drop"
        data-dragging={dragging}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void addFiles(Array.from(e.dataTransfer.files));
        }}
      >
        <input
          ref={input}
          type="file"
          multiple
          accept={ALLOWED.join(",")}
          onChange={(e) => {
            void addFiles(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
        <span className="drop-title">Drop files here, or choose files</span>
        <span className="drop-note">
          PDF, Word, PowerPoint, Excel, PNG or JPG, up to {MAX_MB} MB each
        </span>
      </label>

      {jobs.length > 0 && (
        <ul className="rows" aria-label="In progress">
          {jobs.map((job) => (
            <li key={job.key} className="row">
              <div className="row-main">
                <span className="row-name">{job.name}</span>
                {job.error ? (
                  <span className="row-error" role="alert">
                    {job.error}
                  </span>
                ) : (
                  <span className="row-sub" role="status">
                    {job.step ? `${STEP_TEXT[job.step]}…` : "Waiting"}
                  </span>
                )}
              </div>
              {job.error && (
                <button type="button" className="text-button" onClick={() => remove(job.key)}>
                  Dismiss
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {docs.length === 0 && jobs.length === 0 ? (
        <p className="empty">
          Nothing here yet. Add a PDF, a Word file or a scan, and ask questions about it once it
          shows Ready.
        </p>
      ) : (
        <ul className="rows" aria-label="Your documents">
          {docs.map((doc) => (
            <li key={doc.id} className="row">
              <div className="row-main">
                <span className="row-name">{doc.filename}</span>
                <span className="row-sub">
                  {formatSize(doc.size_bytes)}, added{" "}
                  {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(
                    new Date(doc.created_at),
                  )}
                </span>
                {doc.status_detail && <span className="row-sub">{doc.status_detail}</span>}
              </div>
              <span className="status" data-tone={statusTone(doc.status)}>
                {statusText(doc.status)}
              </span>
              <button
                type="button"
                className="text-button"
                disabled={busy.has(doc.filename)}
                onClick={() =>
                  void run(doc.filename, (onStep) =>
                    processExisting(
                      doc.id,
                      { process: api.processDocument, index: api.indexDocument },
                      onStep,
                    ),
                  )
                }
              >
                Read again
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
