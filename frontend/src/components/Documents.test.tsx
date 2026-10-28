import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Documents } from "./Documents";
import type { DocumentOut } from "../types";

const docs = [
  {
    id: "d1",
    filename: "audit.docx",
    size_bytes: 48213,
    status: "indexed",
    status_detail: null,
    created_at: "2026-10-28T12:00:00Z",
  },
  {
    id: "d2",
    filename: "lecture-scan.pdf",
    size_bytes: 2400000,
    status: "needs_ocr",
    status_detail: "This file needs OCR, which is not configured yet.",
    created_at: "2026-10-26T09:00:00Z",
  },
] as DocumentOut[];

afterEach(() => vi.unstubAllGlobals());

describe("Documents", () => {
  it("lists each document with its status in plain words", () => {
    render(<Documents docs={docs} onChange={vi.fn()} />);
    expect(screen.getByText("audit.docx")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Needs text recognition")).toBeInTheDocument();
    expect(screen.getByText(/needs OCR/)).toBeInTheDocument();
  });

  it("invites the first upload when there is nothing yet", () => {
    render(<Documents docs={[]} onChange={vi.fn()} />);
    expect(screen.getByText(/Nothing here yet/)).toBeInTheDocument();
  });

  it("asks before deleting, and Keep changes nothing", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const onChange = vi.fn();
    render(<Documents docs={docs} onChange={onChange} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Delete audit.docx" }));
    expect(screen.getByText("Delete this document and its search data?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Keep" }));

    expect(screen.queryByText("Delete this document and its search data?")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("deletes the confirmed document and refreshes the list", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const onChange = vi.fn();
    render(<Documents docs={docs} onChange={onChange} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Delete audit.docx" }));
    await user.click(screen.getByRole("button", { name: "Delete document" }));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/documents\/d1$/);
    expect(init.method).toBe("DELETE");
    await vi.waitFor(() => expect(onChange).toHaveBeenCalled());
  });

  it("shows why a delete failed and leaves the document in place", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Could not delete the stored file." }), {
          status: 502,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const onChange = vi.fn();
    render(<Documents docs={docs} onChange={onChange} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Delete audit.docx" }));
    await user.click(screen.getByRole("button", { name: "Delete document" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not delete the stored file.");
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByText("audit.docx")).toBeInTheDocument();
  });
});
