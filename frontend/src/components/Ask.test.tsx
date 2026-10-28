import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Ask } from "./Ask";
import type { AskOut, DocumentOut } from "../types";

// The real API client runs here; only the network underneath it is faked.
function respond(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const sentBody = (fetchMock: ReturnType<typeof respond>) =>
  JSON.parse(fetchMock.mock.calls[0][1].body);

const docs = [
  { id: "d1", filename: "audit.docx", status: "indexed" },
  { id: "d2", filename: "scan.pdf", status: "needs_ocr" },
] as DocumentOut[];

const answer: AskOut = {
  answer: "Yes, personal USB drives are allowed [1], with no encryption [2].",
  found: true,
  sources: [
    {
      number: 1,
      document_id: "d1",
      filename: "audit.docx",
      label: "Document",
      page_number: 1,
      chunk_index: 6,
      content: "Section 6.5 says staff may use personal USB drives.",
    },
    {
      number: 2,
      document_id: "d1",
      filename: "audit.docx",
      label: "Page 2",
      page_number: 2,
      chunk_index: 7,
      content: "There is no encryption requirement.",
    },
  ],
};

async function ask(text = "Can staff use USB drives?") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Your question"), text);
  await user.click(screen.getByRole("button", { name: "Ask" }));
  return user;
}

afterEach(() => vi.unstubAllGlobals());

describe("Ask", () => {
  it("shows the answer with citations, and a click marks the matching passage", async () => {
    const fetchMock = respond(answer);
    render(<Ask docs={docs} loaded />);
    const user = await ask();

    expect(await screen.findByText(/personal USB drives are allowed/)).toBeInTheDocument();
    expect(sentBody(fetchMock)).toEqual({ question: "Can staff use USB drives?", top_k: 5 });

    expect(screen.getByText("There is no encryption requirement.")).not.toHaveClass("marked");
    await user.click(screen.getByRole("button", { name: "Show source 2" }));
    expect(screen.getByText("There is no encryption requirement.")).toHaveClass("marked");
    expect(
      screen.getByText("Section 6.5 says staff may use personal USB drives."),
    ).not.toHaveClass("marked");
  });

  it("shows the location only when it says something", async () => {
    respond(answer);
    render(<Ask docs={docs} loaded />);
    await ask();
    await screen.findByText(/personal USB drives are allowed/);
    expect(screen.getByText("Page 2")).toBeInTheDocument();
    expect(screen.queryByText("Document")).not.toBeInTheDocument();
  });

  it("explains when nothing was found and shows no sources", async () => {
    respond({
      answer: "I could not find the answer to this in your documents.",
      found: false,
      sources: [],
    });
    render(<Ask docs={docs} loaded />);
    await ask("What is the vacation policy?");
    expect(await screen.findByText(/could not find the answer/)).toBeInTheDocument();
    expect(screen.getByText(/Each answer links to the passages/)).toBeInTheDocument();
  });

  it("limits the question to the chosen document and checks more passages when asked", async () => {
    const fetchMock = respond(answer);
    render(<Ask docs={docs} loaded />);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Look in"), "d1");
    await user.click(screen.getByLabelText("Check more passages"));
    await user.type(screen.getByLabelText("Your question"), "Which controls failed?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText(/personal USB drives are allowed/);
    expect(sentBody(fetchMock)).toEqual({
      question: "Which controls failed?",
      top_k: 10,
      document_id: "d1",
    });
  });

  it("offers only documents that are ready", () => {
    render(<Ask docs={docs} loaded />);
    expect(screen.getByRole("option", { name: "audit.docx" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "scan.pdf" })).not.toBeInTheDocument();
  });

  it("shows the server's message when the question fails", async () => {
    respond({ detail: "Answer rate limit reached." }, 502);
    render(<Ask docs={docs} loaded />);
    await ask();
    expect(await screen.findByRole("alert")).toHaveTextContent("Answer rate limit reached.");
  });

  it("points to Documents when nothing is ready", () => {
    render(<Ask docs={[]} loaded />);
    expect(screen.getByRole("link", { name: "Add one" })).toHaveAttribute("href", "#documents");
  });

  it("does not ask an empty question", () => {
    render(<Ask docs={docs} loaded />);
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
  });
});
