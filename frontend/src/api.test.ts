import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, setTokenProvider } from "./api";

function reply(status: number, body: unknown) {
  // A new Response for every call: a body can only be read once
  return vi.fn().mockImplementation(async () =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  setTokenProvider(null);
});

describe("api", () => {
  it("leaves document_id out of the request when no document is chosen", async () => {
    const fetchMock = reply(200, []);
    vi.stubGlobal("fetch", fetchMock);
    await api.search("usb", 5);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/search$/);
    expect(JSON.parse(init.body)).toEqual({ query: "usb", top_k: 5 });
  });

  it("sends document_id when one is chosen", async () => {
    const fetchMock = reply(200, { answer: "x", found: true, sources: [] });
    vi.stubGlobal("fetch", fetchMock);
    await api.ask("q?", 10, "doc1");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      question: "q?",
      top_k: 10,
      document_id: "doc1",
    });
  });

  it("uploads the file as form data", async () => {
    const fetchMock = reply(201, { id: "d1" });
    vi.stubGlobal("fetch", fetchMock);
    await api.uploadDocument(new File(["x"], "a.docx"));
    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.get("file")).toBeInstanceOf(File);
  });

  it("uses the server's message when a request is refused", async () => {
    vi.stubGlobal("fetch", reply(502, { detail: "Embedding rate limit reached." }));
    await expect(api.ask("q", 5)).rejects.toMatchObject({
      message: "Embedding rate limit reached.",
      status: 502,
    });
  });

  it("joins validation problems into one readable message", async () => {
    vi.stubGlobal("fetch", reply(422, { detail: [{ msg: "String should have at least 1 character" }] }));
    await expect(api.ask("", 5)).rejects.toThrow("at least 1 character");
  });

  it("explains when the backend cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await api.listDocuments().catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(0);
    expect(error.message).toContain("Start the backend");
  });

  it("treats a 204 reply as success with nothing to read", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.deleteDocument("d1")).resolves.toBeUndefined();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/documents\/d1$/);
    expect(init.method).toBe("DELETE");
  });

  it("sends the sign-in token with every request once signed in", async () => {
    const fetchMock = reply(200, []);
    vi.stubGlobal("fetch", fetchMock);
    setTokenProvider(async () => "token-123");
    await api.listDocuments();
    await api.search("usb", 5);
    for (const call of fetchMock.mock.calls) {
      expect(new Headers(call[1].headers).get("Authorization")).toBe("Bearer token-123");
    }
  });

  it("keeps the JSON content type when it adds the token", async () => {
    const fetchMock = reply(200, []);
    vi.stubGlobal("fetch", fetchMock);
    setTokenProvider(async () => "token-123");
    await api.search("usb", 5);
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get("Content-Type")).toBe(
      "application/json",
    );
  });

  it("sends no Authorization header when nobody is signed in", async () => {
    const fetchMock = reply(200, []);
    vi.stubGlobal("fetch", fetchMock);
    await api.listDocuments();
    expect(new Headers(fetchMock.mock.calls[0][1].headers).has("Authorization")).toBe(false);
  });

  it("tells the person their session ended when the server refuses the token", async () => {
    vi.stubGlobal("fetch", reply(401, { detail: "The sign-in token is not valid." }));
    setTokenProvider(async () => "stale");
    await expect(api.listDocuments()).rejects.toMatchObject({
      message: "Your session has expired. Sign in again.",
      status: 401,
    });
  });

  it("does not ask for a token when it cannot be had", async () => {
    vi.stubGlobal("fetch", reply(200, []));
    setTokenProvider(async () => null);
    await expect(api.listDocuments()).resolves.toEqual([]);
  });
});
