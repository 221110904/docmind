import { useAuth } from "../auth/AuthContext";

export function SignIn() {
  const auth = useAuth();

  if (auth.status === "loading") {
    return (
      <section className="signin" aria-live="polite">
        <p className="muted">Signing you in…</p>
      </section>
    );
  }

  return (
    <section className="signin" aria-labelledby="signin-title">
      <h1 id="signin-title">Sign in to DocMind</h1>
      <p className="lede">
        Your documents and questions are private to your account. Nobody else can see them.
      </p>
      {auth.error && (
        <p className="notice" role="alert">
          Sign-in did not work. {auth.error}
        </p>
      )}
      <button type="button" className="primary" onClick={auth.signIn}>
        Sign in
      </button>
    </section>
  );
}
