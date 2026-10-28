import type { DocumentOut, IndexOut, ProcessOut } from "./types";

export type Step = "uploading" | "reading" | "indexing";

export interface IngestOps {
  upload(file: File): Promise<DocumentOut>;
  process(id: string): Promise<ProcessOut>;
  index(id: string): Promise<IndexOut>;
}

export interface IngestResult {
  documentId: string;
  outcome: "ready" | "needs_ocr";
  detail: string | null;
}

/** Read the text of a document that is already uploaded, then make it searchable. */
export async function processExisting(
  documentId: string,
  ops: Pick<IngestOps, "process" | "index">,
  onStep: (step: Step) => void,
): Promise<IngestResult> {
  onStep("reading");
  const processed = await ops.process(documentId);
  if (processed.status === "needs_ocr") {
    return { documentId, outcome: "needs_ocr", detail: processed.status_detail };
  }
  if (processed.status !== "extracted") {
    throw new Error(processed.status_detail ?? "The document could not be read.");
  }
  onStep("indexing");
  await ops.index(documentId);
  return { documentId, outcome: "ready", detail: null };
}

/** Upload a file, read its text, and make it searchable, reporting each step. */
export async function ingest(
  file: File,
  ops: IngestOps,
  onStep: (step: Step) => void,
): Promise<IngestResult> {
  onStep("uploading");
  const document = await ops.upload(file);
  return processExisting(document.id, ops, onStep);
}
