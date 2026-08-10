import Link from "next/link";
import { redirect } from "next/navigation";

import { Icon } from "@/components/icons";
import { Logo } from "@/components/logo";
import { createClient } from "@/lib/supabase/server";

const previewRows = [
  { beer: "Hazy Little Thing", style: "Hazy IPA", rating: "4.25" },
  { beer: "Kentucky Breakfast Stout", style: "Imperial Stout", rating: "4.50" },
  { beer: "Pivo Pils", style: "German Pilsner", rating: "4.00" },
];

export default async function Home() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();

  if (data?.claims?.sub) {
    redirect("/dashboard");
  }

  return (
    <main className="landing-page">
      <nav className="landing-nav">
        <Logo />
        <Link className="nav-sign-in" href="/login">
          Sign in <span aria-hidden="true">→</span>
        </Link>
      </nav>

      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow-row">
            <span className="eyebrow-dot" />
            Your personal beer archive
          </div>
          <h1>
            Remember every <em>great pour.</em>
          </h1>
          <p>
            Bring your Untappd history to a private, beautifully organized home.
            Explore the beers, breweries, styles, and places that shaped your taste.
          </p>
          <div className="hero-actions">
            <Link className="primary-button" href="/login">
              Open your archive <Icon name="chevron" size={18} />
            </Link>
            <span>No subscription required to get started</span>
          </div>
        </div>

        <div className="hero-visual" aria-label="Beer history dashboard preview">
          <div className="hero-glow" />
          <div className="preview-window">
            <div className="preview-window-top">
              <span className="mini-brand"><Logo compact /></span>
              <span className="preview-pill">This year</span>
            </div>
            <div className="preview-metrics">
              <div><small>Check-ins</small><strong>247</strong><span>↗ 18%</span></div>
              <div><small>Unique styles</small><strong>42</strong><span>New: 7</span></div>
              <div><small>Avg. rating</small><strong>4.08</strong><span>out of 5</span></div>
            </div>
            <div className="preview-chart-card">
              <div className="preview-card-title"><span>Drinking activity</span><small>Past 12 months</small></div>
              <div className="preview-chart">
                {[32, 48, 38, 61, 47, 78, 58, 72, 43, 64, 76, 92].map((value, index) => (
                  <i key={index} style={{ height: `${value}%` }} />
                ))}
              </div>
            </div>
            <div className="preview-list">
              {previewRows.map((row, index) => (
                <div key={row.beer}>
                  <span className="beer-avatar">{index + 1}</span>
                  <p><strong>{row.beer}</strong><small>{row.style}</small></p>
                  <b>★ {row.rating}</b>
                </div>
              ))}
            </div>
          </div>
          <div className="floating-note floating-note-one">
            <Icon name="sparkle" size={17} />
            <span><strong>Taste insight</strong>IPAs are your top style</span>
          </div>
          <div className="floating-note floating-note-two">
            <span className="rating-ring">4.2</span>
            <span><strong>Your average</strong>Across 1,284 check-ins</span>
          </div>
        </div>
      </section>

      <section className="benefit-strip" aria-label="Features">
        <div><Icon name="history" /><span><strong>Your complete history</strong>Search every check-in in seconds</span></div>
        <div><Icon name="chart" /><span><strong>Taste, visualized</strong>See your habits change over time</span></div>
        <div><Icon name="location" /><span><strong>Places remembered</strong>Revisit the venues behind each pour</span></div>
      </section>
    </main>
  );
}
