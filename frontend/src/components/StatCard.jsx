
import './StatCard.css';

/**
 * Metric card showcasing key statistics with cosmic top-border accent.
 *
 * @param {Object} props
 * @param {React.ReactNode} props.icon
 * @param {string} props.label
 * @param {string|number} props.value
 * @param {string} [props.sublabel]
 * @param {'blue'|'cyan'|'indigo'|'green'} [props.accent='blue']
 */
export default function StatCard({
  icon,
  label,
  value,
  sublabel,
  accent = 'blue',
}) {
  return (
    <div className={`cv-stat-card cv-stat-card--${accent}`}>
      <div className="cv-stat-card__icon" aria-hidden="true">
        {icon}
      </div>
      <div className="cv-stat-card__content">
        <span className="cv-stat-card__value">{value}</span>
        <h4 className="cv-stat-card__label">{label}</h4>
        {sublabel && <span className="cv-stat-card__sublabel">{sublabel}</span>}
      </div>
    </div>
  );
}
