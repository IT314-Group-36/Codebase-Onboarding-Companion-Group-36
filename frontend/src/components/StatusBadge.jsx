
import './StatusBadge.css';

/**
 * Status badge with cosmic glow states.
 *
 * @param {'connected'|'analyzing'|'analyzed'|'error'|'pending'} props.status
 */
export default function StatusBadge({ status = 'connected' }) {
  const statusLabels = {
    connected: 'Connected',
    analyzing: 'Analyzing',
    analyzed: 'Analyzed',
    error: 'Error',
    pending: 'Pending',
  };

  return (
    <span className={`cv-badge cv-badge--${status}`}>
      {status === 'analyzing' ? (
        <span className="cv-badge__pulse" aria-hidden="true" />
      ) : (
        <span className="cv-badge__dot" aria-hidden="true" />
      )}
      <span className="cv-badge__label">{statusLabels[status] || status}</span>
    </span>
  );
}
