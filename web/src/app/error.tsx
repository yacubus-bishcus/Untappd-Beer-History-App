"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="error-screen">
      <div className="error-card">
        <span className="eyebrow">Something went flat</span>
        <h1>We could not load your beer history.</h1>
        <p>The database may be waking up, or the connection may have dropped.</p>
        <button className="primary-button" onClick={reset} type="button">
          Try again
        </button>
      </div>
    </main>
  );
}
