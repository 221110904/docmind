import { describe, expect, it, vi } from "vitest";
import { ingest, processExisting, type Step } from "./pipeline";
import type { DocumentOut } from "./types";

const doc = { id: "d1", filename: "a.docx" } as DocumentOut;
const file = new File(["x"], "a.docx");

function ops(processStatus = "extracted", detail: string | null = null) {
  return {
    upload: vi.fn().mockResolvedValue(doc),
    process: vi
      .fn()
      .mockResolvedValue({ id: "d1", status: processStatus, status_detail: detail, segment_count: 1 }),
    index: vi.fn().mockResolvedValue({ id: "d1", status: "indexed", chunk_count: 3 }),
  };
}

describe("ingest", () => {
  it("uploads, reads, then indexes, reporting each step in order", async () => {
    const steps: Step[] = [];
    const o = ops();
    const result = await ingest(file, o, (s) => steps.push(s));
    expect(steps).toEqual(["uploading", "reading", "indexing"]);
    expect(o.process).toHaveBeenCalledWith("d1");
    expect(o.index).toHaveBeenCalledWith("d1");
    expect(result).toEqual({ documentId: "d1", outcome: "ready", detail: null });
  });

  it("stops without indexing when the file needs text recognition", async () => {
    const o = ops("needs_ocr", "This file needs OCR, which is not configured yet.");
    const result = await ingest(file, o, () => {});
    expect(o.index).not.toHaveBeenCalled();
    expect(result.outcome).toBe("needs_ocr");
    expect(result.detail).toContain("OCR");
  });

  it("raises the reason when reading fails", async () => {
    const o = ops("failed", "The file is corrupted.");
    await expect(ingest(file, o, () => {})).rejects.toThrow("The file is corrupted.");
    expect(o.index).not.toHaveBeenCalled();
  });

  it("does not read a file that failed to upload", async () => {
    const o = ops();
    o.upload.mockRejectedValue(new Error("File too large"));
    await expect(ingest(file, o, () => {})).rejects.toThrow("File too large");
    expect(o.process).not.toHaveBeenCalled();
  });
});

describe("processExisting", () => {
  it("skips the upload", async () => {
    const o = ops();
    const steps: Step[] = [];
    await processExisting("d1", o, (s) => steps.push(s));
    expect(o.upload).not.toHaveBeenCalled();
    expect(steps).toEqual(["reading", "indexing"]);
  });
});
