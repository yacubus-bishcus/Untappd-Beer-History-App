type IconName =
  | "archive"
  | "chart"
  | "chevron"
  | "history"
  | "location"
  | "logout"
  | "search"
  | "sparkle"
  | "upload";

const paths: Record<IconName, React.ReactNode> = {
  archive: (
    <>
      <path d="M4 7h16M5 7l1 13h12l1-13M3 3h18v4H3zM9 11h6" />
    </>
  ),
  chart: <path d="M4 19V9m6 10V5m6 14v-7m4 7H2" />,
  chevron: <path d="m9 18 6-6-6-6" />,
  history: (
    <>
      <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
      <path d="M3 3v5h5M12 7v5l3 2" />
    </>
  ),
  location: (
    <>
      <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" />
      <circle cx="12" cy="10" r="2.5" />
    </>
  ),
  logout: (
    <>
      <path d="M10 5H5v14h5M14 8l4 4-4 4M18 12H9" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m16 16 4 4" />
    </>
  ),
  sparkle: (
    <>
      <path d="m12 2 1.4 4.6L18 8l-4.6 1.4L12 14l-1.4-4.6L6 8l4.6-1.4L12 2Z" />
      <path d="m18.5 14 .7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7.7-2.3Z" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V3M7 8l5-5 5 5M4 14v6h16v-6" />
    </>
  ),
};

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
    >
      {paths[name]}
    </svg>
  );
}
