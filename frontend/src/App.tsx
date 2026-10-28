import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { useAuth } from "./auth/AuthContext";
import { Ask } from "./components/Ask";
import { Documents } from "./components/Documents";
import { Search } from "./components/Search";
import { SignIn } from "./components/SignIn";
import type { DocumentOut } from "./types";

type View = "ask" | "search" | "documents";

const VIEWS: { id: View; label: string }[] = [
  { id: "ask", label: "Ask" },
  { id: "search", label: "Search" },
  { id: "documents", label: "Documents" },
];

function viewFromHash(): View {
  const id = window.location.hash.replace("#", "");
  return VIEWS.some((v) => v.id === id) ? (id as View) : "ask";
}

function useView(): View {
  const [view, setView] = useState<View>(viewFromHash);
  useEffect(() => {
    const onChange = () => setView(viewFromHash());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return view;
}

export function App() {
  const auth = useAuth();
  const view = useView();
  const ready = auth.status === "signed-in";
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const reload = useCallback(async () => {
    try {
      setDocs(await api.listDocuments());
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof ApiError ? error.message : "Could not load documents.");
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (ready) void reload();
  }, [ready, reload]);

  const connection = !loaded ? "checking" : loadError ? "offline" : "online";

  return (
    <>
      <header className="bar">
        <div className="bar-inner">
          <a className="wordmark" href="#ask">
            DocMind
          </a>
          {ready && (
            <nav aria-label="Main">
              {VIEWS.map((v) => (
                <a
                  key={v.id}
                  href={`#${v.id}`}
                  aria-current={view === v.id ? "page" : undefined}
                >
                  {v.label}
                </a>
              ))}
            </nav>
          )}
          <div className="bar-end">
            {ready && (
              <span className="connection" data-state={connection}>
                {connection === "online"
                  ? "Backend connected"
                  : connection === "offline"
                    ? "Backend offline"
                    : "Connecting"}
              </span>
            )}
            {auth.enabled && ready && (
              <>
                {auth.name && <span className="user">{auth.name}</span>}
                <button type="button" className="text-button" onClick={auth.signOut}>
                  Sign out
                </button>
              </>
            )}
          </div>
        </div>
      </header>
      <main className="page">
        {!ready ? (
          <SignIn />
        ) : (
          <>
            {loadError && (
              <p className="notice" role="alert">
                {loadError}
              </p>
            )}
            {view === "ask" && <Ask docs={docs} loaded={loaded} />}
            {view === "search" && <Search docs={docs} loaded={loaded} />}
            {view === "documents" && <Documents docs={docs} onChange={reload} />}
          </>
        )}
      </main>
    </>
  );
}
