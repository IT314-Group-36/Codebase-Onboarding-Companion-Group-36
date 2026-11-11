import { useNavigate } from 'react-router-dom';
import { Home, ArrowLeft, GitBranch, FolderTree, Compass } from 'lucide-react';
import Button from '../components/Button';
import './NotFoundPage.css';

/**
 * Polished 404 page styled with Liquid Chrome aesthetic and amber highlights.
 */
export default function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <div className="cv-notfound-page">
      <div className="cv-notfound-card">
        <div className="cv-notfound-badge">
          <Compass size={14} />
          <span>404 · Unresolved Symbol</span>
        </div>

        <h1 className="cv-notfound-code">404</h1>
        <h2 className="cv-notfound-title">Page or Codebase Target Not Found</h2>
        <p className="cv-notfound-desc">
          The requested coordinate does not exist in this CODEVERSE session or may have been unlinked.
        </p>

        <div className="cv-notfound-actions">
          <Button
            variant="secondary"
            size="md"
            icon={<ArrowLeft size={16} />}
            onClick={() => navigate(-1)}
          >
            Go Back
          </Button>

          <Button
            variant="primary"
            size="md"
            icon={<Home size={16} />}
            onClick={() => navigate('/dashboard')}
          >
            Return to Dashboard
          </Button>
        </div>

        <div className="cv-notfound-destinations">
          <span className="cv-notfound-destinations__title">Quick Navigations:</span>
          <div className="cv-notfound-destinations__links">
            <button
              type="button"
              className="cv-notfound-quicklink"
              onClick={() => navigate('/dashboard')}
            >
              <Home size={14} />
              <span>Dashboard</span>
            </button>
            <button
              type="button"
              className="cv-notfound-quicklink"
              onClick={() => navigate('/connect')}
            >
              <GitBranch size={14} />
              <span>Connect Repository</span>
            </button>
            <button
              type="button"
              className="cv-notfound-quicklink"
              onClick={() => navigate('/explorer/repo-001')}
            >
              <FolderTree size={14} />
              <span>Code Explorer</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
