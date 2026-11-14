import { AlertTriangle } from 'lucide-react';
import Button from './Button';
import './ErrorState.css';

/**
 * Standard failure state: says what went wrong in plain words and offers a way forward.
 * role="alert" so screen readers announce it when it appears.
 */
export default function ErrorState({
  title = 'Something went wrong',
  message,
  actionLabel = 'Try again',
  onAction,
  compact = false,
}) {
  return (
    <div className={`cv-error-state ${compact ? 'cv-error-state--compact' : ''}`} role="alert">
      <AlertTriangle size={compact ? 16 : 32} aria-hidden="true" className="cv-error-state__icon" />
      <div className="cv-error-state__body">
        <h3 className="cv-error-state__title">{title}</h3>
        {message && <p className="cv-error-state__msg">{message}</p>}
        {onAction && (
          <Button variant="secondary" onClick={onAction}>
            {actionLabel}
          </Button>
        )}
      </div>
    </div>
  );
}
