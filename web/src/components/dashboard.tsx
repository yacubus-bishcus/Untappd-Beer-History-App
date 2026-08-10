"use client";

import { useDeferredValue, useMemo, useState } from "react";

import { logout } from "@/app/login/actions";
import { Icon } from "@/components/icons";
import { ImportPanel } from "@/components/import-panel";
import { Logo } from "@/components/logo";
import type { BeerCheckin } from "@/lib/types";

type View = "overview" | "history" | "places";
type WindowKey = "all" | "ytd" | "365" | "30" | "7";

const windowLabels: Record<WindowKey, string> = {
  all: "All time",
  ytd: "Year to date",
  "365": "Past 12 months",
  "30": "Past 30 days",
  "7": "Past 7 days",
};

const numberFormat = new Intl.NumberFormat("en-US");
const shortDate = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});

function ratingFor(checkin: BeerCheckin) {
  return checkin.my_rating ?? checkin.global_rating;
}

function finiteRating(value: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function cutoffFor(windowKey: WindowKey) {
  const now = new Date();
  if (windowKey === "all") return null;
  if (windowKey === "ytd") return new Date(now.getFullYear(), 0, 1);
  const days = Number(windowKey);
  return new Date(now.valueOf() - days * 24 * 60 * 60 * 1000);
}

function activityMonths(checkins: BeerCheckin[]) {
  const now = new Date();
  const months = Array.from({ length: 12 }, (_, index) => {
    const date = new Date(now.getFullYear(), now.getMonth() - (11 - index), 1);
    return {
      key: `${date.getFullYear()}-${date.getMonth()}`,
      label: date.toLocaleDateString("en-US", { month: "short" }).slice(0, 1),
      longLabel: date.toLocaleDateString("en-US", { month: "short", year: "numeric" }),
      count: 0,
    };
  });
  const byKey = new Map(months.map((month) => [month.key, month]));

  checkins.forEach((checkin) => {
    if (!checkin.checked_in_at) return;
    const date = new Date(checkin.checked_in_at);
    const month = byKey.get(`${date.getFullYear()}-${date.getMonth()}`);
    if (month) month.count += 1;
  });

  return months;
}

function groupBy(
  checkins: BeerCheckin[],
  selector: (checkin: BeerCheckin) => string | null,
) {
  const groups = new Map<string, { name: string; count: number; ratings: number[] }>();
  checkins.forEach((checkin) => {
    const name = selector(checkin)?.trim();
    if (!name) return;
    const group = groups.get(name) ?? { name, count: 0, ratings: [] };
    group.count += 1;
    const rating = finiteRating(ratingFor(checkin));
    if (rating !== null) group.ratings.push(rating);
    groups.set(name, group);
  });

  return [...groups.values()]
    .map((group) => ({
      ...group,
      average:
        group.ratings.length > 0
          ? group.ratings.reduce((sum, value) => sum + value, 0) / group.ratings.length
          : null,
    }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

function MetricCard({
  label,
  value,
  detail,
  icon,
}: {
  label: string;
  value: string;
  detail: string;
  icon: "archive" | "chart" | "history" | "sparkle";
}) {
  return (
    <article className="metric-card">
      <div className="metric-card-top">
        <span>{label}</span>
        <i><Icon name={icon} size={18} /></i>
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function ActivityChart({ checkins }: { checkins: BeerCheckin[] }) {
  const months = activityMonths(checkins);
  const max = Math.max(...months.map((month) => month.count), 1);

  return (
    <div className="activity-chart" aria-label="Monthly check-ins for the past year">
      {months.map((month) => (
        <div className="activity-column" key={month.key} title={`${month.longLabel}: ${month.count}`}>
          <span className="bar-value">{month.count || ""}</span>
          <div className="bar-track">
            <i style={{ height: `${Math.max(4, (month.count / max) * 100)}%` }} />
          </div>
          <small>{month.label}</small>
        </div>
      ))}
    </div>
  );
}

function RatingDistribution({ checkins }: { checkins: BeerCheckin[] }) {
  const buckets = useMemo(() => {
    const values = new Map<number, number>();
    checkins.forEach((checkin) => {
      const rating = finiteRating(ratingFor(checkin));
      if (rating === null) return;
      const bucket = Math.max(0, Math.min(5, Math.round(rating * 2) / 2));
      values.set(bucket, (values.get(bucket) ?? 0) + 1);
    });
    return Array.from({ length: 11 }, (_, index) => ({
      rating: index / 2,
      count: values.get(index / 2) ?? 0,
    }));
  }, [checkins]);
  const max = Math.max(...buckets.map((bucket) => bucket.count), 1);

  return (
    <div className="rating-distribution">
      {buckets.map((bucket) => (
        <div key={bucket.rating} title={`${bucket.rating.toFixed(1)}: ${bucket.count} check-ins`}>
          <i style={{ height: `${Math.max(3, (bucket.count / max) * 100)}%` }} />
          <small>{bucket.rating % 1 === 0 ? bucket.rating : ""}</small>
        </div>
      ))}
    </div>
  );
}

function EmptyArchive({ onImport }: { onImport: () => void }) {
  return (
    <section className="empty-archive">
      <div className="empty-illustration" aria-hidden="true">
        <span className="empty-glass"><i /></span>
        <span className="empty-spark one">✦</span>
        <span className="empty-spark two">·</span>
      </div>
      <span className="eyebrow">Your first round</span>
      <h2>Bring your beer history home.</h2>
      <p>
        Run the desktop app to create <strong>data/my_beers.csv</strong>, then import it here.
        The same file can be synced again whenever you scrape new check-ins.
      </p>
      <button className="primary-button" onClick={onImport} type="button">
        <Icon name="upload" size={18} /> Import my history
      </button>
    </section>
  );
}

export function Dashboard({ checkins, email }: { checkins: BeerCheckin[]; email: string }) {
  const [view, setView] = useState<View>("overview");
  const [windowKey, setWindowKey] = useState<WindowKey>("all");
  const [query, setQuery] = useState("");
  const [style, setStyle] = useState("all");
  const [showImport, setShowImport] = useState(false);
  const [visibleRows, setVisibleRows] = useState(40);
  const deferredQuery = useDeferredValue(query);

  const styles = useMemo(
    () =>
      [...new Set(checkins.map((checkin) => checkin.beer_type).filter(Boolean) as string[])].sort(
        (a, b) => a.localeCompare(b),
      ),
    [checkins],
  );

  const filtered = useMemo(() => {
    const cutoff = cutoffFor(windowKey);
    const normalizedQuery = deferredQuery.trim().toLocaleLowerCase();
    return checkins.filter((checkin) => {
      if (cutoff) {
        if (!checkin.checked_in_at || new Date(checkin.checked_in_at) < cutoff) return false;
      }
      if (style !== "all" && checkin.beer_type !== style) return false;
      if (!normalizedQuery) return true;
      return [checkin.beer_name, checkin.producer, checkin.beer_type, checkin.consumed_location]
        .filter(Boolean)
        .some((value) => value!.toLocaleLowerCase().includes(normalizedQuery));
    });
  }, [checkins, deferredQuery, style, windowKey]);

  const summary = useMemo(() => {
    const ratings = filtered
      .map((checkin) => finiteRating(ratingFor(checkin)))
      .filter((value): value is number => value !== null);
    const average = ratings.length
      ? ratings.reduce((sum, rating) => sum + rating, 0) / ratings.length
      : null;
    const uniqueBeers = new Set(
      filtered.map((checkin) => `${checkin.beer_name.toLocaleLowerCase()}|${checkin.producer ?? ""}`),
    ).size;
    const breweries = new Set(filtered.map((checkin) => checkin.producer).filter(Boolean)).size;
    const styleCount = new Set(filtered.map((checkin) => checkin.beer_type).filter(Boolean)).size;
    return { average, uniqueBeers, breweries, styleCount };
  }, [filtered]);

  const topStyles = useMemo(() => groupBy(filtered, (checkin) => checkin.beer_type).slice(0, 6), [filtered]);
  const topBreweries = useMemo(() => groupBy(filtered, (checkin) => checkin.producer).slice(0, 6), [filtered]);
  const locations = useMemo(
    () => groupBy(filtered, (checkin) => checkin.consumed_location),
    [filtered],
  );
  const firstName = email.split("@")[0] || "Beer explorer";

  return (
    <div className="dashboard-shell">
      <aside className="sidebar">
        <Logo />
        <nav aria-label="Dashboard sections">
          <button className={view === "overview" ? "active" : ""} onClick={() => setView("overview")} type="button">
            <Icon name="chart" /> Overview
          </button>
          <button className={view === "history" ? "active" : ""} onClick={() => setView("history")} type="button">
            <Icon name="history" /> Beer history
          </button>
          <button className={view === "places" ? "active" : ""} onClick={() => setView("places")} type="button">
            <Icon name="location" /> Places
          </button>
        </nav>
        <div className="sidebar-import">
          <span><Icon name="upload" /></span>
          <strong>Fresh check-ins?</strong>
          <p>Sync the latest CSV from the desktop app.</p>
          <button onClick={() => setShowImport(true)} type="button">Import history</button>
        </div>
        <form action={logout} className="sidebar-user">
          <span>{firstName.slice(0, 2).toUpperCase()}</span>
          <p><strong>{firstName}</strong><small>{email}</small></p>
          <button aria-label="Sign out" title="Sign out" type="submit"><Icon name="logout" /></button>
        </form>
      </aside>

      <main className="dashboard-main">
        <header className="dashboard-header">
          <div>
            <span className="eyebrow">Your tasting archive</span>
            <h1>{view === "overview" ? "Good taste, documented." : view === "history" ? "Every pour, in one place." : "A map made of memories."}</h1>
            <p>{view === "overview" ? "The story behind your check-ins, from first sip to latest find." : view === "history" ? "Search and filter your complete imported history." : "The taprooms, bars, and cities behind your beer history."}</p>
          </div>
          <div className="header-actions">
            <div className="mobile-brand"><Logo compact /></div>
            <button className="secondary-button" onClick={() => setShowImport(true)} type="button"><Icon name="upload" size={17} /> Import CSV</button>
          </div>
        </header>

        <div className="mobile-nav" role="navigation" aria-label="Dashboard sections">
          {(["overview", "history", "places"] as View[]).map((item) => (
            <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">
              <Icon name={item === "overview" ? "chart" : item === "history" ? "history" : "location"} size={18} />
              {item === "overview" ? "Overview" : item === "history" ? "History" : "Places"}
            </button>
          ))}
        </div>

        {checkins.length === 0 ? (
          <EmptyArchive onImport={() => setShowImport(true)} />
        ) : (
          <>
            <section className="filter-bar" aria-label="Filter beer history">
              <label className="search-field">
                <Icon name="search" size={18} />
                <input aria-label="Search beer history" onChange={(event) => { setQuery(event.target.value); setVisibleRows(40); }} placeholder="Search beer, brewery, style…" value={query} />
              </label>
              <label>
                <span>Time period</span>
                <select value={windowKey} onChange={(event) => setWindowKey(event.target.value as WindowKey)}>
                  {(Object.keys(windowLabels) as WindowKey[]).map((key) => <option key={key} value={key}>{windowLabels[key]}</option>)}
                </select>
              </label>
              <label>
                <span>Beer style</span>
                <select value={style} onChange={(event) => setStyle(event.target.value)}>
                  <option value="all">All styles</option>
                  {styles.map((beerStyle) => <option key={beerStyle} value={beerStyle}>{beerStyle}</option>)}
                </select>
              </label>
            </section>

            {view === "overview" && (
              <div className="overview-grid">
                <section className="metric-grid">
                  <MetricCard label="Check-ins" value={numberFormat.format(filtered.length)} detail={`${numberFormat.format(summary.uniqueBeers)} unique beers`} icon="history" />
                  <MetricCard label="Average rating" value={summary.average === null ? "—" : summary.average.toFixed(2)} detail={summary.average === null ? "No ratings in this view" : "Your rating when available"} icon="sparkle" />
                  <MetricCard label="Breweries" value={numberFormat.format(summary.breweries)} detail="Producers explored" icon="archive" />
                  <MetricCard label="Beer styles" value={numberFormat.format(summary.styleCount)} detail="Styles in this view" icon="chart" />
                </section>

                <section className="dashboard-card activity-card">
                  <div className="card-heading"><div><span className="eyebrow">Cadence</span><h2>Drinking activity</h2></div><span className="card-badge">Past 12 months</span></div>
                  <ActivityChart checkins={filtered} />
                </section>

                <section className="dashboard-card ratings-card">
                  <div className="card-heading"><div><span className="eyebrow">Your grading curve</span><h2>Rating distribution</h2></div><span className="rating-legend">★ 0–5</span></div>
                  <RatingDistribution checkins={filtered} />
                </section>

                <section className="dashboard-card top-card">
                  <div className="card-heading"><div><span className="eyebrow">Most explored</span><h2>Top styles</h2></div></div>
                  <div className="rank-list">
                    {topStyles.length ? topStyles.map((item, index) => (
                      <div key={item.name}><b>{String(index + 1).padStart(2, "0")}</b><span><strong>{item.name}</strong><small>{item.average === null ? "No rating" : `★ ${item.average.toFixed(2)} avg.`}</small></span><em>{item.count}</em></div>
                    )) : <p className="empty-card-copy">No styles match these filters.</p>}
                  </div>
                </section>

                <section className="dashboard-card top-card">
                  <div className="card-heading"><div><span className="eyebrow">Frequent favorites</span><h2>Top breweries</h2></div></div>
                  <div className="rank-list">
                    {topBreweries.length ? topBreweries.map((item, index) => (
                      <div key={item.name}><b>{String(index + 1).padStart(2, "0")}</b><span><strong>{item.name}</strong><small>{item.average === null ? "No rating" : `★ ${item.average.toFixed(2)} avg.`}</small></span><em>{item.count}</em></div>
                    )) : <p className="empty-card-copy">No breweries match these filters.</p>}
                  </div>
                </section>
              </div>
            )}

            {view === "history" && (
              <section className="dashboard-card history-card">
                <div className="card-heading"><div><span className="eyebrow">The archive</span><h2>{numberFormat.format(filtered.length)} check-ins</h2></div><span className="card-badge">Newest first</span></div>
                <div className="table-scroll">
                  <table>
                    <thead><tr><th>Beer</th><th>Style</th><th>Rating</th><th>Location</th><th>Date</th></tr></thead>
                    <tbody>
                      {filtered.slice(0, visibleRows).map((checkin) => (
                        <tr key={checkin.id}>
                          <td><strong>{checkin.beer_name}</strong><small>{checkin.producer || "Unknown brewery"}</small></td>
                          <td><span className="table-tag">{checkin.beer_type || "Unknown"}</span></td>
                          <td><span className="table-rating">{ratingFor(checkin) === null ? "—" : `★ ${ratingFor(checkin)!.toFixed(2)}`}</span></td>
                          <td>{checkin.consumed_location || "—"}</td>
                          <td>{checkin.checked_in_at ? shortDate.format(new Date(checkin.checked_in_at)) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {filtered.length === 0 && <p className="empty-card-copy roomy">No check-ins match these filters.</p>}
                {visibleRows < filtered.length && <button className="load-more" onClick={() => setVisibleRows((count) => count + 40)} type="button">Show 40 more</button>}
              </section>
            )}

            {view === "places" && (
              <section className="places-layout">
                <div className="places-hero">
                  <span className="eyebrow light">Your beer trail</span>
                  <h2>{numberFormat.format(locations.length)} places, countless stories.</h2>
                  <p>Locations are pulled from each Untappd check-in. Import an updated CSV whenever your travels grow.</p>
                  <div className="places-orbit" aria-hidden="true"><i /><i /><i /><i /></div>
                </div>
                <div className="dashboard-card place-list-card">
                  <div className="card-heading"><div><span className="eyebrow">Most visited</span><h2>Top places</h2></div><span className="card-badge">{numberFormat.format(filtered.length)} pours</span></div>
                  <div className="place-list">
                    {locations.slice(0, 18).map((location, index) => (
                      <div key={location.name}><span><Icon name="location" size={18} /></span><p><strong>{location.name}</strong><small>{location.average === null ? "Ratings unavailable" : `★ ${location.average.toFixed(2)} average rating`}</small></p><b>{location.count}<small> check-ins</small></b><em>{index + 1}</em></div>
                    ))}
                    {locations.length === 0 && <p className="empty-card-copy roomy">No saved locations match these filters.</p>}
                  </div>
                </div>
              </section>
            )}
          </>
        )}
      </main>

      {showImport && <ImportPanel onClose={() => setShowImport(false)} />}
    </div>
  );
}
