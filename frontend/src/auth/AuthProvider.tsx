import {
  AuthError,
  InteractionRequiredAuthError,
  PublicClientApplication,
  type AccountInfo,
} from "@azure/msal-browser";
import { useEffect, useLayoutEffect, useMemo, useState, type ReactNode } from "react";
import { setTokenProvider } from "../api";
import { AuthContext, LOGIN_OFF, type Auth } from "./AuthContext";
import { entraSettings, msalConfig, type EntraSettings } from "./config";

/** Wraps the app. With VITE_AUTH=entra it signs people in with Microsoft Entra External ID. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const settings = useMemo(() => entraSettings(import.meta.env), []);
  if (!settings) {
    return <AuthContext.Provider value={LOGIN_OFF}>{children}</AuthContext.Provider>;
  }
  return <EntraAuth settings={settings}>{children}</EntraAuth>;
}

function EntraAuth({ settings, children }: { settings: EntraSettings; children: ReactNode }) {
  const msal = useMemo(
    () => new PublicClientApplication(msalConfig(settings, window.location.origin)),
    [settings],
  );
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await msal.initialize();
      // Finishes a sign-in that just came back from Microsoft's page
      await msal.handleRedirectPromise();
      const known = msal.getAllAccounts()[0] ?? null;
      if (known) msal.setActiveAccount(known);
      if (!cancelled) {
        setAccount(known);
        setReady(true);
      }
    })().catch((e) => {
      if (cancelled) return;
      setError(describe(e)); // show the sign-in screen, with the reason, so the person can try again
      setReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, [msal]);

  // A layout effect, so the token provider is in place before any child component's own
  // effect sends its first request (plain effects run children first, which left that
  // request without a token).
  useLayoutEffect(() => {
    if (!account) {
      setTokenProvider(null);
      return;
    }
    setTokenProvider(async () => {
      const request = { scopes: [settings.apiScope], account };
      try {
        return (await msal.acquireTokenSilent(request)).accessToken;
      } catch (error) {
        if (error instanceof InteractionRequiredAuthError) {
          await msal.acquireTokenRedirect(request); // leaves the page to sign in again
        }
        throw error;
      }
    });
    return () => setTokenProvider(null);
  }, [account, msal, settings.apiScope]);

  const value = useMemo<Auth>(
    () => ({
      enabled: true,
      status: !ready ? "loading" : account ? "signed-in" : "signed-out",
      name: account?.name || account?.username || null,
      error,
      signIn: () => {
        setError(null);
        msal.loginRedirect({ scopes: [settings.apiScope] }).catch((e) => setError(describe(e)));
      },
      signOut: () => {
        msal.logoutRedirect({ account: account ?? undefined }).catch((e) => setError(describe(e)));
      },
    }),
    [account, error, msal, ready, settings.apiScope],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** A short, readable reason for a failed sign-in (MSAL errors carry a code and a message). */
function describe(error: unknown): string {
  if (error instanceof AuthError) return `${error.errorCode}: ${error.errorMessage || "sign-in failed"}`;
  return error instanceof Error ? error.message : "Sign-in failed.";
}
