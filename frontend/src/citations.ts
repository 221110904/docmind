export type Piece = { kind: "text"; text: string } | { kind: "cite"; number: number };

/**
 * Split an answer into plain text and citation marks like [2].
 * A mark only counts as a citation when it points at a source that exists;
 * anything else stays as ordinary text.
 */
export function splitCitations(answer: string, valid: ReadonlySet<number>): Piece[] {
  const pieces: Piece[] = [];
  const push = (text: string) => {
    if (!text) return;
    const last = pieces[pieces.length - 1];
    if (last?.kind === "text") last.text += text;
    else pieces.push({ kind: "text", text });
  };

  let cursor = 0;
  for (const match of answer.matchAll(/\[(\d+)\]/g)) {
    const number = Number(match[1]);
    const start = match.index ?? 0;
    push(answer.slice(cursor, start));
    if (valid.has(number)) pieces.push({ kind: "cite", number });
    else push(match[0]);
    cursor = start + match[0].length;
  }
  push(answer.slice(cursor));
  return pieces;
}

/** "Page 3" and "Slide 2" help a reader find the place; "Document" says nothing. */
export function locationLabel(label: string): string | null {
  return label === "Document" || label === "Image" || !label ? null : label;
}

const STATUS_TEXT: Record<string, string> = {
  uploaded: "Waiting to be read",
  processing: "Reading",
  extracted: "Read, not searchable yet",
  indexed: "Ready",
  needs_ocr: "Needs text recognition",
  failed: "Could not be read",
};

export function statusText(status: string): string {
  return STATUS_TEXT[status] ?? status;
}

export type Tone = "ok" | "warn" | "bad" | "idle";

export function statusTone(status: string): Tone {
  if (status === "indexed") return "ok";
  if (status === "failed") return "bad";
  if (status === "processing" || status === "needs_ocr" || status === "extracted") return "warn";
  return "idle";
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
