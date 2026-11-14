import { Activity } from 'lucide-react';
import useReducedMotion from '../hooks/useReducedMotion';

/** Switch for "Reduce motion". Starts from the OS setting; the user's choice is remembered in this browser. */
export default function MotionToggle() {
  const { reduced, setReduced } = useReducedMotion();
  return (
    <button
      type="button"
      className="cv-topbar__icon-btn"
      role="switch"
      aria-checked={reduced}
      aria-label="Reduce motion"
      title={reduced ? 'Motion reduced (click to turn animations back on)' : 'Reduce motion'}
      onClick={() => setReduced(!reduced)}
      style={{ opacity: reduced ? 1 : 0.6 }}
    >
      <Activity size={18} aria-hidden="true" />
    </button>
  );
}
