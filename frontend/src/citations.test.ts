import { describe, expect, it } from "vitest";
import { formatSize, locationLabel, splitCitations, statusText, statusTone } from "./citations";

describe("splitCitations", () => {
  it("turns [n] into a citation when the source exists", () => {
    const pieces = splitCitations("Allowed [1] but unencrypted [2].", new Set([1, 2]));
    expect(pieces).toEqual([
      { kind: "text", text: "Allowed " },
      { kind: "cite", number: 1 },
      { kind: "text", text: " but unencrypted " },
      { kind: "cite", number: 2 },
      { kind: "text", text: "." },
    ]);
  });

  it("keeps a mark as plain text when no such source exists", () => {
    const pieces = splitCitations("See [7] and [1].", new Set([1]));
    expect(pieces).toEqual([
      { kind: "text", text: "See [7] and " },
      { kind: "cite", number: 1 },
      { kind: "text", text: "." },
    ]);
  });

  it("handles adjacent marks and text without any marks", () => {
    expect(splitCitations("Both [1][2]", new Set([1, 2]))).toEqual([
      { kind: "text", text: "Both " },
      { kind: "cite", number: 1 },
      { kind: "cite", number: 2 },
    ]);
    expect(splitCitations("No marks here", new Set([1]))).toEqual([
      { kind: "text", text: "No marks here" },
    ]);
    expect(splitCitations("", new Set())).toEqual([]);
  });

  it("works on Arabic text", () => {
    const pieces = splitCitations("نعم، يسمح بذلك [1]", new Set([1]));
    expect(pieces[pieces.length - 1]).toEqual({ kind: "cite", number: 1 });
  });
});

describe("labels", () => {
  it("hides locations that say nothing", () => {
    expect(locationLabel("Document")).toBeNull();
    expect(locationLabel("Image")).toBeNull();
    expect(locationLabel("Page 3")).toBe("Page 3");
  });

  it("describes statuses in plain words", () => {
    expect(statusText("indexed")).toBe("Ready");
    expect(statusText("needs_ocr")).toBe("Needs text recognition");
    expect(statusText("something_new")).toBe("something_new");
    expect(statusTone("indexed")).toBe("ok");
    expect(statusTone("failed")).toBe("bad");
    expect(statusTone("uploaded")).toBe("idle");
  });

  it("formats sizes", () => {
    expect(formatSize(512)).toBe("512 B");
    expect(formatSize(2048)).toBe("2 KB");
    expect(formatSize(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});
