import { useNavigate } from 'react-router-dom';
import { GitBranch, Star, GitFork, ArrowUpRight } from 'lucide-react';
import StatusBadge from './StatusBadge';
import './RepositoryCard.css';

/**
 * Card representing a connected/analyzed repository.
 *
 * @param {Object} props
 * @param {Object} props.repo
 */
export default function RepositoryCard({ repo }) {
  const navigate = useNavigate();

  const languagePills = {
    JavaScript: '#FF9B54', // Primary amber
    TypeScript: '#A58BEA', // Muted violet
    Python: '#E7B45A',     // Warning/gold
    Dart: '#E8853D',       // Deep amber-orange
    Rust: '#DE7C5A',       // Terracotta
    Go: '#34D399',         // Success sage
  };

  const handleOpen = () => {
    navigate(`/repository/${repo.id}`);
  };

  return (
    <div
      className="cv-repo-card"
      onClick={handleOpen}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleOpen()}
      tabIndex={0}
      role="button"
      aria-label={`View repository ${repo.fullName}`}
    >
      <div className="cv-repo-card__top">
        <div className="cv-repo-card__title-group">
          <span className="cv-repo-card__owner">{repo.owner} /</span>
          <h3 className="cv-repo-card__name">{repo.name}</h3>
        </div>
        <StatusBadge status={repo.status} />
      </div>

      <p className="cv-repo-card__desc">{repo.description}</p>

      <div className="cv-repo-card__meta">
        <div className="cv-repo-card__lang">
          <span
            className="cv-repo-card__lang-color"
            style={{ backgroundColor: languagePills[repo.language] || '#FF9B54' }}
            aria-hidden="true"
          />
          <span>{repo.language}</span>
        </div>

        <div className="cv-repo-card__stat">
          <GitBranch size={13} strokeWidth={1.8} aria-hidden="true" />
          <span>{repo.branch}</span>
        </div>

        {repo.stars > 0 && (
          <div className="cv-repo-card__stat">
            <Star size={13} strokeWidth={1.8} aria-hidden="true" />
            <span>{repo.stars.toLocaleString()}</span>
          </div>
        )}

        {repo.forks > 0 && (
          <div className="cv-repo-card__stat">
            <GitFork size={13} strokeWidth={1.8} aria-hidden="true" />
            <span>{repo.forks.toLocaleString()}</span>
          </div>
        )}

        <div className="cv-repo-card__arrow" aria-hidden="true">
          <ArrowUpRight size={15} strokeWidth={2} />
        </div>
      </div>
    </div>
  );
}
