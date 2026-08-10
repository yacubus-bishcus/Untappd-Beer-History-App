import Link from "next/link";

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link className="brand" href="/" aria-label="Untappd Beer History home">
      <span className="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 42 42" role="img">
          <path d="M12.5 8.5h15l-1.8 24h-11.4l-1.8-24Z" />
          <path d="M13.5 13.5h13M15.5 28.5h9" />
          <path d="M27.5 14h3.2a5 5 0 0 1 0 10h-4.1" />
          <path d="M17 8.5V6.8c0-1.4 1.2-2.6 2.6-2.6h2.8c1.4 0 2.6 1.2 2.6 2.6v1.7" />
        </svg>
      </span>
      {!compact && (
        <span className="brand-copy">
          <strong>Beer History</strong>
          <small>Your tasting archive</small>
        </span>
      )}
    </Link>
  );
}
