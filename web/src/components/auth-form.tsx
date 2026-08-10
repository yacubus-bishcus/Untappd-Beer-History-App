"use client";

import { useActionState, useState } from "react";

import {
  login,
  signup,
  type AuthState,
} from "@/app/login/actions";

const initialAuthState: AuthState = {
  status: "idle",
  message: "",
};

function SubmitButton({ mode, pending }: { mode: "login" | "signup"; pending: boolean }) {
  return (
    <button className="auth-submit" disabled={pending} type="submit">
      {pending
        ? mode === "login"
          ? "Signing in…"
          : "Creating account…"
        : mode === "login"
          ? "Open my archive"
          : "Create my archive"}
      <span aria-hidden="true">→</span>
    </button>
  );
}

export function AuthForm({ initialNotice }: { initialNotice?: string }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [loginState, loginAction, loginPending] = useActionState<AuthState, FormData>(
    login,
    initialAuthState,
  );
  const [signupState, signupAction, signupPending] = useActionState<AuthState, FormData>(
    signup,
    initialAuthState,
  );
  const state = mode === "login" ? loginState : signupState;
  const notice =
    initialNotice === "confirmation-failed"
      ? "That confirmation link could not be verified. Try signing in or create a fresh account."
      : initialNotice === "confirmed"
        ? "Your email is confirmed. Sign in to continue."
        : "";

  return (
    <div className="auth-panel">
      <div className="auth-tabs" role="tablist" aria-label="Account action">
        <button
          aria-selected={mode === "login"}
          className={mode === "login" ? "active" : ""}
          onClick={() => setMode("login")}
          role="tab"
          type="button"
        >
          Sign in
        </button>
        <button
          aria-selected={mode === "signup"}
          className={mode === "signup" ? "active" : ""}
          onClick={() => setMode("signup")}
          role="tab"
          type="button"
        >
          Create account
        </button>
      </div>

      <div className="auth-heading">
        <span className="eyebrow">Private by default</span>
        <h1>{mode === "login" ? "Welcome back." : "Start your archive."}</h1>
        <p>
          {mode === "login"
            ? "Your taps, ratings, and favorite places are ready when you are."
            : "One secure account keeps your beer history synced across every screen."}
        </p>
      </div>

      <form action={mode === "login" ? loginAction : signupAction} className="auth-form">
        <label>
          <span>Email address</span>
          <input
            autoComplete="email"
            name="email"
            placeholder="you@example.com"
            required
            type="email"
          />
        </label>
        <label>
          <span>Password</span>
          <input
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            minLength={8}
            name="password"
            placeholder="At least 8 characters"
            required
            type="password"
          />
        </label>

        {state.message || notice ? (
          <p
            className={`form-message ${
              state.status === "success" || initialNotice === "confirmed"
                ? "success"
                : "error"
            }`}
            role="status"
          >
            {state.message || notice}
          </p>
        ) : null}

        <SubmitButton
          mode={mode}
          pending={mode === "login" ? loginPending : signupPending}
        />
      </form>

      <p className="auth-footnote">
        This independent project is not affiliated with or endorsed by Untappd.
      </p>
    </div>
  );
}
