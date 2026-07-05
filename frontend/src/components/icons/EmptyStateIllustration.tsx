export default function EmptyStateIllustration() {
  return (
    <svg
      width="72"
      height="72"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      className="empty-illustration"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" strokeDasharray="2 3" opacity="0.5" />
      <circle cx="12" cy="12" r="5.5" opacity="0.7" />
      <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
      <path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21" strokeLinecap="round" />
    </svg>
  );
}
