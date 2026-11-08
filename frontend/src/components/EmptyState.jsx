
import { Sparkles } from 'lucide-react';
import Button from './Button';
import './EmptyState.css';

/**
 * Standard Empty State card.
 */
export default function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  onAction,
}) {
  return (
    <div className="cv-empty-state">
      <div className="cv-empty-state__icon" aria-hidden="true">
        {icon || <Sparkles size={40} />}
      </div>
      <h3 className="cv-empty-state__title">{title}</h3>
      {description && <p className="cv-empty-state__desc">{description}</p>}
      {actionLabel && onAction && (
        <Button variant="primary" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
