import { useId, useState } from 'react';
import { Info } from 'lucide-react';
import './StaticAnalysisBadge.css';

/**
 * Honest-uncertainty label for results that come from static analysis (impact, dependency graph).
 * Static analysis reads the code without running it, so it can miss dynamic behaviour. Never call these results "verified".
 *
 * @param {'impact'|'graph'} [props.kind]
 */
const COPY = {
  impact: 'Based on static analysis. It can miss calls made dynamically (reflection, callbacks, runtime imports), so treat this as a strong hint, not a guarantee.',
  graph: 'Built from static analysis of imports and calls. Runtime-only connections will not appear here.',
};

export default function StaticAnalysisBadge({ kind = 'impact', className = '' }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <div className={`cv-static-badge ${className}`}>
      <button
        type="button"
        className="cv-static-badge__btn"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        <Info size={12} aria-hidden="true" />
        <span>Static analysis · not verified at runtime</span>
      </button>
      {open && (
        <p id={panelId} className="cv-static-badge__panel">
          {COPY[kind] || COPY.impact}
        </p>
      )}
    </div>
  );
}
