import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { AuthContext, LOGIN_OFF, type Auth } from "./auth/AuthContext";

function stubApi() {
  const fetchMock = vi.fn().mockImplementation(async () =>
    new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderWith(auth: Auth) {
  return render(
    <AuthContext.Provider value={auth}>
      <App />
    </AuthContext.Provider>,
  );
}

const entra = (patch: Partial<Auth>): Auth => ({
  enabled: true,
  status: "signed-out",
  name: null,
  error: null,
  signIn: vi.fn(),
  signOut: vi.fn(),
  ...patch,
});

afterEach(() => vi.unstubAllGlobals());

describe("App with login", () => {
  it("shows the sign-in screen, and nothing else, until someone signs in", async () => {
    const fetchMock = stubApi();
    const signIn = vi.fn();
    renderWith(entra({ signIn }));

    expect(screen.getByRole("heading", { name: "Sign in to DocMind" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.queryByText(/Backend/)).not.toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Sign in" }));
    expect(signIn).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled(); // no API call without a token
  });

  it("tells the person why a sign-in failed", () => {
    stubApi();
    renderWith(entra({ error: "endpoints_resolution_error: could not reach the tenant" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/endpoints_resolution_error/);
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("says so while the sign-in is being finished", () => {
    stubApi();
    renderWith(entra({ status: "loading" }));
    expect(screen.getByText("Signing you in…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("loads the app and shows who is signed in", async () => {
    const fetchMock = stubApi();
    const signOut = vi.fn();
    renderWith(entra({ status: "signed-in", name: "Faisal Alrabiah", signOut }));

    expect(await screen.findByText("Backend connected")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalled();
    expect(screen.getByText("Faisal Alrabiah")).toBeInTheDocument();
    expect(screen.getByRole("navigation")).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));
    expect(signOut).toHaveBeenCalledTimes(1);
  });
});

describe("App without login", () => {
  it("opens straight into the app, with no sign-in or sign-out", async () => {
    stubApi();
    renderWith(LOGIN_OFF);
    expect(await screen.findByText("Backend connected")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Sign in to DocMind" })).not.toBeInTheDocument();
  });
});
