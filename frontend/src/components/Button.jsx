
import './Button.css';

/**
 * Reusable Button Component with design system variants.
 *
 * @param {Object} props
 * @param {'primary'|'secondary'|'ghost'|'danger'|'outline'} [props.variant='primary']
 * @param {'sm'|'md'|'lg'} [props.size='md']
 * @param {boolean} [props.loading=false]
 * @param {boolean} [props.disabled=false]
 * @param {React.ReactNode} [props.icon]
 * @param {React.ReactNode} [props.children]
 * @param {string} [props.className='']
 * @param {string} [props.type='button']
 * @param {Function} [props.onClick]
 */
export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  icon,
  children,
  className = '',
  type = 'button',
  onClick,
  ...rest
}) {
  return (
    <button
      type={type}
      className={`cv-btn cv-btn--${variant} cv-btn--${size} ${loading ? 'cv-btn--loading' : ''} ${className}`}
      disabled={disabled || loading}
      onClick={onClick}
      {...rest}
    >
      {loading ? (
        <span className="cv-btn__spinner" aria-hidden="true" />
      ) : (
        icon && <span className="cv-btn__icon" aria-hidden="true">{icon}</span>
      )}
      {children && <span className="cv-btn__text">{children}</span>}
    </button>
  );
}
