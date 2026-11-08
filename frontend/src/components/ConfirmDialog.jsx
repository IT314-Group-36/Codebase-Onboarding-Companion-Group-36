import { useEffect, useRef } from 'react';
import { AlertTriangle, AlertCircle } from 'lucide-react';
import Button from './Button';
import './ConfirmDialog.css';

/**
 * Accessible modal confirmation dialog.
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  loading = false,
  onConfirm,
  onCancel,
}) {
  const dialogRef = useRef(null);

  useEffect(() => {
    if (open) {
      dialogRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && open && !loading) {
        onCancel();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, loading, onCancel]);

  if (!open) return null;

  return (
    <div className="cv-dialog-overlay" onClick={onCancel} role="presentation">
      <div
        className="cv-dialog"
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        aria-describedby="dialog-desc"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={`cv-dialog__icon cv-dialog__icon--${variant}`} aria-hidden="true">
          {variant === 'danger' ? <AlertTriangle size={26} /> : <AlertCircle size={26} />}
        </div>
        <h3 id="dialog-title" className="cv-dialog__title">{title}</h3>
        <p id="dialog-desc" className="cv-dialog__desc">{message}</p>
        <div className="cv-dialog__actions">
          <Button variant="ghost" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button variant={variant} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
