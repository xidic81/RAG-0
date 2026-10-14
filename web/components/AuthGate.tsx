"use client";

import Link from "next/link";
import { FormEvent, ReactNode, useEffect, useState } from "react";
import Health from "@/components/Health";
import { ApiError, authSession, login, logout } from "@/lib/api";

type AuthState = "checking" | "unauthenticated" | "authenticated" | "error";

export default function AuthGate({ children }: { children: ReactNode }) {
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    function handleAuthExpired() {
      setError("Your session has expired. Please sign in again.");
      setAuthState("unauthenticated");
    }

    window.addEventListener("auth-expired", handleAuthExpired);
    return () => window.removeEventListener("auth-expired", handleAuthExpired);
  }, []);

  useEffect(() => {
    authSession()
      .then(() => setAuthState("authenticated"))
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) {
          setAuthState("unauthenticated");
        } else {
          setError(err instanceof Error ? err.message : "Unable to check login status");
          setAuthState("error");
        }
      });
  }, []);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    setSubmitting(true);
    setError(null);
    try {
      await login(username, password);
      setPassword("");
      setAuthState("authenticated");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLogout() {
    setError(null);
    try {
      await logout();
      setAuthState("unauthenticated");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Logout failed");
    }
  }

  if (authState === "checking") {
    return <p className="m-auto p-8 text-center text-sm text-gray-600">Checking login…</p>;
  }

  if (authState !== "authenticated") {
    return (
      <main className="mx-auto flex min-h-screen w-full max-w-sm items-center px-4 py-12">
        <form onSubmit={handleLogin} className="w-full space-y-5 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Sign in</h1>
            <p className="mt-1 text-sm text-gray-600">Sign in to access the RAG chatbot.</p>
          </div>
          {error && (
            <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </p>
          )}
          {authState === "error" ? (
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="w-full rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700"
            >
              Retry
            </button>
          ) : (
            <>
              <label className="block space-y-1 text-sm font-medium text-gray-700">
                Username
                <input
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  required
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 outline-none focus:border-gray-500 focus:ring-2 focus:ring-gray-200"
                />
              </label>
              <label className="block space-y-1 text-sm font-medium text-gray-700">
                Password
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 outline-none focus:border-gray-500 focus:ring-2 focus:ring-gray-200"
                />
              </label>
              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? "Signing in…" : "Sign in"}
              </button>
            </>
          )}
        </form>
      </main>
    );
  }

  return (
    <>
      <header className="border-b border-gray-200">
        <nav className="mx-auto flex max-w-3xl items-center gap-6 px-4 py-4">
          <Link href="/">Chat</Link>
          <Link href="/documents">Documents</Link>
          <div className="ml-auto flex items-center gap-5">
            <Health />
            <button
              type="button"
              onClick={() => void handleLogout()}
              className="text-sm text-gray-600 hover:text-gray-900"
            >
              Sign out
            </button>
          </div>
        </nav>
      </header>
      {error && (
        <p role="alert" className="mx-auto mt-3 max-w-3xl px-4 text-sm text-red-700">
          {error}
        </p>
      )}
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6">{children}</main>
    </>
  );
}
