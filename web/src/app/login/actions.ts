"use server";

import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

export type AuthState = {
  status: "idle" | "error" | "success";
  message: string;
};

function credentials(formData: FormData) {
  return {
    email: String(formData.get("email") ?? "").trim().toLowerCase(),
    password: String(formData.get("password") ?? ""),
  };
}

function validate(email: string, password: string) {
  if (!email || !email.includes("@")) {
    return "Enter a valid email address.";
  }

  if (password.length < 8) {
    return "Your password must be at least 8 characters.";
  }

  return null;
}

export async function login(
  _previousState: AuthState,
  formData: FormData,
): Promise<AuthState> {
  const { email, password } = credentials(formData);
  const validationError = validate(email, password);

  if (validationError) {
    return { status: "error", message: validationError };
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });

  if (error) {
    return {
      status: "error",
      message:
        error.message.toLowerCase().includes("invalid login")
          ? "That email and password combination was not recognized."
          : error.message,
    };
  }

  redirect("/dashboard");
}

export async function signup(
  _previousState: AuthState,
  formData: FormData,
): Promise<AuthState> {
  const { email, password } = credentials(formData);
  const validationError = validate(email, password);

  if (validationError) {
    return { status: "error", message: validationError };
  }

  const requestHeaders = await headers();
  const origin = requestHeaders.get("origin") ?? "http://localhost:3000";
  const supabase = await createClient();
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      emailRedirectTo: `${origin}/auth/callback`,
    },
  });

  if (error) {
    return { status: "error", message: error.message };
  }

  if (data.session) {
    redirect("/dashboard");
  }

  return {
    status: "success",
    message:
      "Check your inbox to confirm your account, then return here and sign in.",
  };
}

export async function logout() {
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/");
}
