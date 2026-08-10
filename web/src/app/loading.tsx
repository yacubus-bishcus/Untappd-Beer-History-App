export default function Loading() {
  return (
    <main className="loading-screen" aria-live="polite">
      <div className="loading-mark" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <p>Pouring your history…</p>
    </main>
  );
}
