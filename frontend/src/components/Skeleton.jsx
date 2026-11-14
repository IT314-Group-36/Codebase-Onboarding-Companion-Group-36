import './Skeleton.css';

/** Placeholder lines/blocks while content loads. Decorative: hidden from screen readers (pair with a role="status" label). */
export default function Skeleton({ lines = 3, height = 14, className = '' }) {
  return (
    <div className={`cv-skeleton ${className}`} aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <span
          key={i}
          className="cv-skeleton__line"
          style={{ height, width: i === lines - 1 && lines > 1 ? '60%' : '100%' }}
        />
      ))}
    </div>
  );
}
