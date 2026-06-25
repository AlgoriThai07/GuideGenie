/**
 * Small inline loading spinner.
 *
 * Pairs an animated ring with an accessible label. Used for page-level
 * loading states (dashboard, trip detail) and inside submit buttons.
 */

interface SpinnerProps {
  /** Visible text shown next to the spinner. Also used as the aria-label. */
  label?: string;
  /** Render white instead of dark — for use on a dark button. */
  light?: boolean;
}

export default function Spinner({ label, light = false }: SpinnerProps) {
  const ringColor = light
    ? "border-white/40 border-t-white"
    : "border-gray-300 border-t-gray-900";

  return (
    <span
      role="status"
      aria-label={label ?? "Loading"}
      className="inline-flex items-center gap-2"
    >
      <span
        aria-hidden="true"
        className={`h-4 w-4 animate-spin rounded-full border-2 ${ringColor}`}
      />
      {label && (
        <span className={light ? "text-white" : "text-gray-600"}>{label}</span>
      )}
    </span>
  );
}
