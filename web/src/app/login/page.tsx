import { redirect } from "next/navigation";

import { AuthForm } from "@/components/auth-form";
import { Logo } from "@/components/logo";
import { createClient } from "@/lib/supabase/server";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ notice?: string }>;
}) {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();

  if (data?.claims?.sub) {
    redirect("/dashboard");
  }

  const { notice } = await searchParams;

  return (
    <main className="auth-page">
      <section className="auth-story">
        <Logo />
        <div className="auth-story-copy">
          <span className="eyebrow light">Your history, on tap</span>
          <h2>Every pour tells a story.</h2>
          <p>
            Turn years of check-ins into a living archive you can search, filter,
            and revisit from anywhere.
          </p>
        </div>
        <div className="auth-stat-preview" aria-hidden="true">
          <span>12 month activity</span>
          <div className="preview-bars">
            {[36, 58, 43, 72, 51, 88, 64, 78, 48, 68, 82, 96].map((height, index) => (
              <i key={index} style={{ height: `${height}%` }} />
            ))}
          </div>
          <strong>365 days of good taste</strong>
        </div>
      </section>
      <section className="auth-form-side">
        <AuthForm initialNotice={notice} />
      </section>
    </main>
  );
}
