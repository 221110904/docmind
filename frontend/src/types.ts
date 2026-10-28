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
