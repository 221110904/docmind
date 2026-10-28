import type { AskOut, DocumentOut, IndexOut, ProcessOut, SearchHit } from "./types";

export const API_URL: string = (
  import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** FastAPI sends `detail` as a string, or as a list of problems for invalid input. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => (typeof item?.msg === "string" ? item.msg : ""))
        .filter(Boolean);
      if (messages.length) return messages.join(" ");
    }
  } catch {
    // The body was not JSON; fall through to the generic message
  }
  return `The request failed (HTTP ${response.status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(
      `Can't reach the DocMind API at ${API_URL}. Start the backend and try again.`,
      0,
    );
  }
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  if (response.status === 204) return undefined as T; // success with no body
  return (await response.json()) as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  listDocuments: () => request<DocumentOut[]>("/documents"),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentOut>("/documents/upload", { method: "POST", body: form });
  },
  deleteDocument: (id: string) =>
    request<void>(`/documents/${encodeURIComponent(id)}`, { method: "DELETE" }),
  processDocument: (id: string) =>
    request<ProcessOut>(`/documents/${encodeURIComponent(id)}/process`, { method: "POST" }),
  indexDocument: (id: string) =>
    request<IndexOut>(`/documents/${encodeURIComponent(id)}/index`, { method: "POST" }),
  // document_id is left out entirely when no document is chosen
  search: (query: string, topK: number, documentId?: string) =>
    postJson<SearchHit[]>("/search", {
      query,
      top_k: topK,
      ...(documentId ? { document_id: documentId } : {}),
    }),
  ask: (question: string, topK: number, documentId?: string) =>
    postJson<AskOut>("/ask", {
      question,
      top_k: topK,
      ...(documentId ? { document_id: documentId } : {}),
    }),
};

export type Api = typeof api;
