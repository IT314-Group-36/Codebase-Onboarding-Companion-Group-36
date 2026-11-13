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

const MAX_FILE_OPTIONS = 500;

export default function HistoryPage() {
  const { repoId } = useParams();
  const navigate = useNavigate();
  const [meta, setMeta] = useState({ key: '', repo: null, files: [], error: '' });
  const [selectedPath, setSelectedPath] = useState('');
  const [reloadTick, setReloadTick] = useState(0);
  const [result, setResult] = useState({ key: '', data: null, error: '' });

  // Repository name + file list (for the path picker). A failure here never hides the history itself.
  useEffect(() => {
    let alive = true;
    Promise.all([getRepositoryById(repoId), getFileTree(repoId)])
      .then(([repoResult, fileResult]) => {
        if (alive) setMeta({ key: repoId, repo: repoResult.repository || null, files: fileResult.files || [], error: '' });
      })
      .catch((e) => {
        if (alive) setMeta({ key: repoId, repo: null, files: [], error: e.message || 'Could not load repository details.' });
      });
    return () => { alive = false; };
  }, [repoId]);

  // Commits for the selected path. `loading` is derived (the result belongs to an older request),
  // so no state is set synchronously inside the effect and a stale answer can never overwrite a newer one.
  const requestKey = `${repoId}|${selectedPath}|${reloadTick}`;
  useEffect(() => {
    let alive = true;
    getRepositoryHistory(repoId, { path: selectedPath })
      .then((data) => { if (alive) setResult({ key: requestKey, data, error: '' }); })
      .catch((e) => { if (alive) setResult({ key: requestKey, data: null, error: e.message || 'Could not load Git history.' }); });
    return () => { alive = false; };
  }, [repoId, selectedPath, requestKey]);

  const loading = result.key !== requestKey;
  const history = result.data;
  const error = loading ? '' : result.error;
  const repo = meta.key === repoId ? meta.repo : null;

  // Every folder (at any depth) and every file can be selected; the API accepts any path.
  const { folders, fileOptions, truncated } = useMemo(() => {
    const files = meta.key === repoId ? meta.files : [];
    const dirs = new Set();
    const list = [];
    for (const file of files) {
      const parts = file.path.split('/');
      for (let i = 1; i < parts.length; i += 1) dirs.add(parts.slice(0, i).join('/'));
      list.push(file.path);
    }
    list.sort((a, b) => a.localeCompare(b));
    return {
      folders: [...dirs].sort((a, b) => a.localeCompare(b)),
      fileOptions: list.slice(0, MAX_FILE_OPTIONS),
      truncated: list.length > MAX_FILE_OPTIONS,
    };
  }, [meta, repoId]);

  const retry = () => setReloadTick((t) => t + 1);

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
        <select id="history-path" value={selectedPath} onChange={(e) => setSelectedPath(e.target.value)}>
          <option value="">Entire repository</option>
          {folders.length > 0 && <optgroup label="Folders">
            {folders.map((path) => <option key={`d:${path}`} value={path}>{path}/</option>)}
          </optgroup>}
          {fileOptions.length > 0 && <optgroup label={truncated ? `Files (first ${MAX_FILE_OPTIONS})` : 'Files'}>
            {fileOptions.map((path) => <option key={`f:${path}`} value={path}>{path}</option>)}
          </optgroup>}
        </select>
        <span><GitBranch size={15} /> {history?.branch || repo?.branch || 'Default branch'}</span>
      </section>

      {meta.key === repoId && meta.error && <div className="cv-history-error" role="alert"><span>{meta.error}</span></div>}
      {error && <div className="cv-history-error" role="alert"><span>{error}</span><button type="button" onClick={retry}>Try again</button></div>}

      {history && <div style={loading ? { opacity: 0.6 } : undefined}>
        <div className="cv-history-grid">
          <section className="cv-history-card cv-history-contributors">
            <div className="cv-history-card-heading"><div><Users size={17} /><h2>Knowledge concentration</h2></div><span>{history.sample_size} commits sampled</span></div>
            <p className="cv-history-note">Contribution activity in the latest sampled commits. This is a historical activity signal, not a measure of current expertise.</p>
            {history.contributors.length ? <ol className="cv-contributor-list">
              {history.contributors.map((person) => <li key={`${person.login || ''}|${person.name}`}>
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
                  {commit.changed_files?.length > 0 && <div className="cv-commit-files" aria-label="Files changed in this commit">
                    <span>{commit.changed_files.length} changed files:</span>
                    {commit.changed_files.slice(0, 5).map((file) => <code key={file.path} title={`${file.status}: +${file.additions} / -${file.deletions}`}>{file.path}</code>)}
                    {commit.changed_files.length > 5 && <small>and {commit.changed_files.length - 5} more</small>}
                  </div>}
                </div>
              </li>)}
            </ol> : <p className="cv-history-empty">No commits were found for this selection.</p>}
          </section>
        </div>
        <p className="cv-history-footnote">History is loaded from GitHub when requested and is not retained in the app. Contributor percentages are based on the latest {history.sample_size} commits for this selection.</p>
      </div>}
    </main>
  );
}
