import { render, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { useAuth } from "./AuthContext";
import { AuthProvider } from "./AuthProvider";

const account = { homeAccountId: "h", username: "a@b.c", name: "A B" };

vi.mock("@azure/msal-browser", () => {
  class PublicClientApplication {
    initialize = async () => {};
    handleRedirectPromise = async () => null;
    getAllAccounts = () => [account];
    setActiveAccount = () => {};
    acquireTokenSilent = async () => ({ accessToken: "tok-123" });
  }
  class AuthError extends Error {}
  class InteractionRequiredAuthError extends AuthError {}
  return { PublicClientApplication, AuthError, InteractionRequiredAuthError };
});

function Gate() {
  // Like App: nothing but the sign-in screen until the person is signed in.
  return useAuth().status === "signed-in" ? <FirstRequest /> : null;
}

function FirstRequest() {
  // Like the Documents list: asks the API as soon as it appears.
  useEffect(() => {
    void api.health();
  }, []);
  return null;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("AuthProvider", () => {
  it("sends the token with the very first request a child makes", async () => {
    vi.stubEnv("VITE_AUTH", "entra");
    vi.stubEnv("VITE_ENTRA_TENANT_ID", "tenant-1");
    vi.stubEnv("VITE_ENTRA_SUBDOMAIN", "docmindauth");
    vi.stubEnv("VITE_ENTRA_CLIENT_ID", "client-1");
    vi.stubEnv("VITE_API_SCOPE", "api://api-1/access_as_user");
    const fetchMock = vi.fn().mockImplementation(
      async () => new Response('{"status":"ok"}', { headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Gate />
      </AuthProvider>,
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const headers = new Headers(fetchMock.mock.calls[0][1].headers);
    expect(headers.get("Authorization")).toBe("Bearer tok-123");
  });
});
