import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, GitCommit, GitBranch, Users, ExternalLink, RefreshCw } from 'lucide-react';
import { getRepositoryById, getFileTree, getRepositoryHistory } from '../services/api';
import LoadingState from '../components/LoadingState';
import './HistoryPage.css';

function formatDate(value) {
  if (!value) return 'Date unavailable';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleString();
}

export default function HistoryPage() {
  const { repoId } = useParams();
  const navigate = useNavigate();
  const [repo, setRepo] = useState(null);
  const [files, setFiles] = useState([]);
  const [history, setHistory] = useState(null);
  const [selectedPath, setSelectedPath] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    Promise.all([getRepositoryById(repoId), getFileTree(repoId)])
      .then(([repoResult, fileResult]) => {
        if (!alive) return;
        setRepo(repoResult.repository || null);
        setFiles(fileResult.files || []);
      })
      .catch((e) => { if (alive) setError(e.message || 'Could not load repository details.'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [repoId]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setHistory(null);
    setError('');
    getRepositoryHistory(repoId, { path: selectedPath })
      .then((data) => { if (alive) setHistory(data); })
      .catch((e) => { if (alive) setError(e.message || 'Could not load Git history.'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [repoId, selectedPath]);

  const paths = useMemo(() => {
    const folders = new Set();
    for (const file of files) {
      const parts = file.path.split('/');
      if (parts.length > 1) folders.add(parts[0]);
    }
    return [...folders].sort((a, b) => a.localeCompare(b));
  }, [files]);

  const retry = () => {
    setLoading(true);
    setError('');
    getRepositoryHistory(repoId, { path: selectedPath })
      .then(setHistory)
      .catch((e) => setError(e.message || 'Could not load Git history.'))
      .finally(() => setLoading(false));
  };

  if (loading && !history && !error) return <LoadingState message="Loading repository history…" />;

  return (
    <main className="cv-history-page">
      <header className="cv-history-header">
        <button type="button" className="cv-history-back" onClick={() => navigate(`/repository/${repoId}`)} aria-label="Back to repository"><ArrowLeft size={18} /></button>
        <div><p className="cv-history-eyebrow">REPOSITORY INSIGHTS</p><h1>Git history</h1>
          <p className="cv-history-subtitle">{repo?.fullName || repo?.name || history?.repository || 'Recent commits and contributor activity'}</p>
        </div>
        <button type="button" className="cv-history-refresh" onClick={retry} disabled={loading}><RefreshCw size={15} /> Refresh</button>
      </header>

      <section className="cv-history-toolbar">
        <label htmlFor="history-path">Explore history for</label>
        <select id="history-path" value={selectedPath} onChange={(e) => { setLoading(true); setSelectedPath(e.target.value); }}>
          <option value="">Entire repository</option>
          {paths.map((path) => <option key={path} value={path}>{path}/</option>)}
        </select>
        <span><GitBranch size={15} /> {history?.branch || repo?.branch || 'Default branch'}</span>
      </section>

      {error && <div className="cv-history-error" role="alert"><span>{error}</span><button onClick={retry}>Try again</button></div>}

      {history && <>
        <div className="cv-history-grid">
          <section className="cv-history-card cv-history-contributors">
            <div className="cv-history-card-heading"><div><Users size={17} /><h2>Knowledge concentration</h2></div><span>{history.sample_size} commits sampled</span></div>
            <p className="cv-history-note">Contribution activity in the latest sampled commits. This is a historical activity signal, not a measure of current expertise.</p>
            {history.contributors.length ? <ol className="cv-contributor-list">
              {history.contributors.map((person) => <li key={person.login || person.name}>
                <div className="cv-contributor-person">
                  {person.avatar_url ? <img src={person.avatar_url} alt="" /> : <span className="cv-contributor-avatar">{person.name?.slice(0, 1) || '?'}</span>}
                  <span><strong>{person.name}</strong><small>{person.login ? `@${person.login}` : 'Git author'}</small></span>
                </div>
                <div className="cv-contributor-count"><strong>{person.commits}</strong><span>{person.share}%</span><div className="cv-contributor-bar"><i style={{ width: `${person.share}%` }} /></div></div>
              </li>)}
            </ol> : <p className="cv-history-empty">No commits were found for this selection.</p>}
          </section>

          <section className="cv-history-card cv-history-timeline">
            <div className="cv-history-card-heading"><div><GitCommit size={17} /><h2>Code evolution</h2></div><span>Latest commits</span></div>
            {history.commits.length ? <ol className="cv-commit-list">
              {history.commits.map((commit) => <li key={commit.sha}>
                <span className="cv-commit-dot" />
                <div className="cv-commit-content">
                  <a href={commit.url} target="_blank" rel="noreferrer" className="cv-commit-message">{commit.message}<ExternalLink size={13} /></a>
                  <p><span>{commit.author.name}</span> · {formatDate(commit.date)} · <code>{commit.short_sha}</code></p>
                </div>
              </li>)}
            </ol> : <p className="cv-history-empty">No commits were found for this selection.</p>}
          </section>
        </div>
        <p className="cv-history-footnote">History is loaded from GitHub when requested and is not retained in the app. Contributor percentages are based on this page of recent commits (up to 50).</p>
      </>}
    </main>
  );
}
