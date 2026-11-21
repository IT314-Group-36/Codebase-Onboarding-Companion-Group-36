import { useLocation, useNavigate } from 'react-router-dom';
import { GitBranch } from 'lucide-react';
import Button from '../components/Button';
import { SECTION_LABEL } from '../utils/navLabels';
import './RepoRequiredPage.css';

/**
 * Shown when a page that needs a repository is opened before any repository is connected.
 */
export default function RepoRequiredPage() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const label = SECTION_LABEL[pathname.split('/')[1]] || 'This page';

  return (
    <div className="cv-need-repo" role="status">
      <div className="cv-need-repo__icon" aria-hidden="true">
        <GitBranch size={28} />
      </div>
      <h1 className="cv-need-repo__title">Connect a repository first</h1>
      <p className="cv-need-repo__text">
        {label} needs a project to look at. Connect one from GitHub and it will be ready in a few minutes.
      </p>
      <Button variant="primary" size="lg" onClick={() => navigate('/connect')}>
        Connect a repository
      </Button>
    </div>
  );
}
