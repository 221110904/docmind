// These mirror the response models in backend/app/main.py.

export interface DocumentOut {
  id: string;
  filename: string;
  blob_name: string;
  content_type: string;
  size_bytes: number;
  status: string;
  status_detail: string | null;
  created_at: string;
}

export interface ProcessOut {
  id: string;
  status: string;
  status_detail: string | null;
  segment_count: number;
}

export interface IndexOut {
  id: string;
  status: string;
  chunk_count: number;
}

export interface SearchHit {
  document_id: string;
  filename: string;
  label: string;
  page_number: number;
  chunk_index: number;
  content: string;
  score: number;
}

export interface Source {
  number: number;
  document_id: string;
  filename: string;
  label: string;
  page_number: number;
  chunk_index: number;
  content: string;
}

export interface AskOut {
  answer: string;
  found: boolean;
  sources: Source[];
}

export interface Candidate {
  title: string;
  url: string;
  domain: string;
  snippet: string;
}

export interface CandidatesOut {
  topic: string;
  queries: string[];
  candidates: Candidate[];
}

export interface BenchEvidence {
  page_number: number;
  label: string;
  content: string;
}

export interface BenchPeer {
  source: number;
  title: string;
  url: string;
  page: number | null;
}

export type BenchStatus = "covered" | "partial" | "missing";

export interface BenchItem {
  topic: string;
  status: BenchStatus;
  expected: string;
  gap: string;
  suggested_edit: string;
  your_evidence: BenchEvidence[];
  peers: BenchPeer[];
}

export interface BenchSource {
  number: number;
  title: string;
  url: string;
  status: "read" | "failed";
  detail: string | null;
  truncated: boolean;
}

export interface BenchmarkOut {
  summary: { covered: number; partial: number; missing: number; total: number };
  items: BenchItem[];
  sources: BenchSource[];
}
