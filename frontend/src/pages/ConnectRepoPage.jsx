import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  GitBranch,
  Link2,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Compass,
  RotateCcw,
  FileCode,
  KeyRound,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  FileWarning,
  Lock,
  Search,
} from 'lucide-react';
import GithubIcon from '../components/GithubIcon';
import Button from '../components/Button';
import {
  connectRepository,
  getRepositoryById,
  reindexRepository,
  listGitHubRepos,
  listGitHubBranches,
  loginWithGitHub,
} from '../services/api';
import { parseIndexingError } from '../services/adapters';
import { parseGitHubUrl, isValidBranch } from '../utils/github';
import { useAuth } from '../context/useAuth';
import { showToast } from '../utils/toast';
import './ConnectRepoPage.css';

const INDEXING_STEPS = [
  { id: 'cloning', label: 'Cloning repository tree & metadata' },
  { id: 'analyzing', label: 'Parsing AST, syntax nodes & import edges' },
  { id: 'embedding', label: 'Generating code chunk vector embeddings' },
  { id: 'saving', label: 'Committing atomic index transaction' },
  { id: 'describing', label: 'Synthesizing module map & architecture summary' },
];

const STAGE_ORDER = ['cloning', 'analyzing', 'embedding', 'saving', 'describing'];

/**
 * Page 3: Connect Repository
 * Clean, form-focused developer ingestion workflow with validation,
 * real-time stage progress polling from FastAPI backend, and clear next actions.
 */
export default function ConnectRepoPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [source, setSource] = useState('picker'); // 'picker' (my GitHub repos) | 'url' (paste a URL)
  const [repoUrl, setRepoUrl] = useState('');
  const [selectedBranch, setSelectedBranch] = useState(''); // '' = the repository's default branch
  const [accessToken, setAccessToken] = useState('');
  const [showTokenField, setShowTokenField] = useState(false);
  const [urlError, setUrlError] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [failedDetails, setFailedDetails] = useState(null);
  const [showTechDetails, setShowTechDetails] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [phase, setPhase] = useState('form'); // 'form' | 'analyzing' | 'success' | 'error'
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [embeddingProgress, setEmbeddingProgress] = useState(null);
  const [completedSteps, setCompletedSteps] = useState([]);
  const [connectedRepoId, setConnectedRepoId] = useState(null);

  // "My GitHub repos" picker: loaded page by page, filtered in the browser
  const [ghRepos, setGhRepos] = useState([]);
  const [ghPage, setGhPage] = useState(0);
  const [ghHasMore, setGhHasMore] = useState(false);
  const [ghLoadingMore, setGhLoadingMore] = useState(false);
  const [ghError, setGhError] = useState(null); // { message, reauth }
  const [ghFilter, setGhFilter] = useState('');

  // Real branches of the chosen repository
  const [branchInfo, setBranchInfo] = useState(null); // { fullName, defaultBranch, branches, truncated } | { fullName, failed, reauth }

  const pollIntervalRef = useRef(null);

  const parsedRepo = parseGitHubUrl(repoUrl);
  const fullName = parsedRepo ? parsedRepo.fullName : null;
  const branchesReady = branchInfo && branchInfo.fullName === fullName;       // result belongs to the current repo
  const branchesLoading = Boolean(fullName) && !branchesReady;

  const toGhError = (err) => ({
    message: err.message || 'Could not load your GitHub repositories.',
    reauth: err.code === 'github_reauth_required',
  });

  // First page of the picker (loaded when the picker is shown, and again after "Try again")
  useEffect(() => {
    if (source !== 'picker' || ghPage !== 0 || ghError) return undefined;
    let cancelled = false;
    listGitHubRepos({ page: 1 })
      .then((res) => {
        if (cancelled) return;
        setGhRepos(res.repos);
        setGhPage(res.page);
        setGhHasMore(res.hasMore);
      })
      .catch((err) => {
        if (!cancelled) setGhError(toGhError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [source, ghPage, ghError]);

  const loadMoreGitHubRepos = async () => {
    setGhLoadingMore(true);
    try {
      const res = await listGitHubRepos({ page: ghPage + 1 });
      setGhRepos((prev) => [...prev, ...res.repos]);
      setGhPage(res.page);
      setGhHasMore(res.hasMore);
    } catch (err) {
      setGhError(toGhError(err));
    } finally {
      setGhLoadingMore(false);
    }
  };
  const ghLoading = (source === 'picker' && ghPage === 0 && !ghError) || ghLoadingMore;

  // Branch list for the chosen repository (a pasted URL waits a moment until typing stops)
  useEffect(() => {
    if (!fullName) return undefined;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const res = await listGitHubBranches(fullName);
        if (!cancelled) setBranchInfo({ fullName, ...res });
      } catch (err) {
        if (!cancelled) {
          setBranchInfo({ fullName, failed: true, reauth: err.code === 'github_reauth_required' });
        }
      }
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [fullName]);

  const chooseRepo = (repo) => {
    setRepoUrl(repo.url);
    setSelectedBranch('');
    setUrlError('');
  };

  const filteredGhRepos = ghRepos.filter((r) => {
    const needle = ghFilter.trim().toLowerCase();
    return !needle || r.full_name.toLowerCase().includes(needle) || (r.description || '').toLowerCase().includes(needle);
  });

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  const validateUrl = (url) => {
    if (!url.trim()) {
      return 'Choose a repository or enter its URL.';
    }
    if (!parseGitHubUrl(url)) {
      return 'Use the form https://github.com/owner/repository (https only).';
    }
    return '';
  };

  const startPolling = useCallback(
    (repoId) => {
      stopPolling();
      let pollFailures = 0;
      const maxPollFailures = 8; // 8 * 1.5s = ~12s consecutive network failures

      pollIntervalRef.current = setInterval(async () => {
        try {
          const detailRes = await getRepositoryById(repoId);
          if (!detailRes.success || !detailRes.repository) {
            pollFailures += 1;
            if (pollFailures >= maxPollFailures) {
              stopPolling();
              setPhase('error');
              setFailedDetails({
                title: 'Connection Lost',
                message: 'Lost communication with backend server while polling repository status.',
                failingFile: null,
                isRetryable: true,
                advisory: 'Ensure FastAPI backend is running on http://localhost:8000.',
                technicalDetails: 'Multiple consecutive requests to GET /repos/{id} failed.',
              });
              showToast('Lost connection to backend server.', 'error');
            }
            return;
          }

          pollFailures = 0; // reset consecutive failures on successful response
          const current = detailRes.repository;
          const stage = current.stage;
          setEmbeddingProgress(current.indexReport?.embedding_progress || null);

          if (stage) {
            const stageIdx = STAGE_ORDER.indexOf(stage);
            if (stageIdx >= 0) {
              setCurrentStepIndex(stageIdx);
              const finished = [];
              for (let i = 0; i < stageIdx; i++) {
                finished.push(i);
              }
              setCompletedSteps(finished);
            }
          }

          if (current.rawStatus === 'ready') {
            stopPolling();
            setCompletedSteps([0, 1, 2, 3, 4]);
            setPhase('success');
            showToast('Repository successfully indexed and AST ready.', 'success');
          } else if (current.rawStatus === 'failed') {
            stopPolling();
            setPhase('error');
            const parsed = current.parsedError || parseIndexingError(current.error);
            setFailedDetails(parsed);
            setErrorMessage(current.error || 'Indexing failed in backend worker.');
            showToast('Indexing encountered an error.', 'error');
          }
        } catch (pollErr) {
          console.warn('Polling error during indexing:', pollErr.message);
          pollFailures += 1;
          if (pollFailures >= maxPollFailures) {
            stopPolling();
            setPhase('error');
            setFailedDetails({
              title: 'Polling Interrupted',
              message: 'Network error communicating with the FastAPI backend.',
              failingFile: null,
              isRetryable: true,
              advisory: 'Verify your backend container and network connection.',
              technicalDetails: pollErr.message,
            });
            showToast('Polling error: ' + pollErr.message, 'error');
          }
        }
      }, 1500);
    },
    [stopPolling]
  );

  const handleStartAnalysis = async () => {
    const error = validateUrl(repoUrl);
    if (error) {
      setUrlError(error);
      return;
    }
    if (!isValidBranch(selectedBranch)) {
      setUrlError('That branch name is not supported. Leave it empty to use the default branch.');
      return;
    }
    setUrlError('');
    setErrorMessage('');
    setFailedDetails(null);
    setShowTechDetails(false);
    setPhase('analyzing');
    setCurrentStepIndex(0);
    setEmbeddingProgress(null);
    setCompletedSteps([]);

    const cleanUrl = repoUrl.trim();
    const token = accessToken.trim() || null;

    try {
      const res = await connectRepository(cleanUrl, selectedBranch, token);

      if (!res.success || !res.repository) {
        throw new Error(res.error || 'Failed to register repository with backend.');
      }

      const repo = res.repository;
      setConnectedRepoId(repo.id);

      // If already ready (e.g. idempotent registration for already-indexed repo)
      if (repo.rawStatus === 'ready') {
        setCompletedSteps([0, 1, 2, 3, 4]);
        setPhase('success');
        showToast('Repository is already analyzed and ready.', 'success');
        return;
      }

      // If already failed (e.g. idempotent registration for repo that failed in worker)
      if (repo.rawStatus === 'failed') {
        stopPolling();
        setPhase('error');
        const parsed = repo.parsedError || parseIndexingError(repo.error);
        setFailedDetails(parsed);
        setErrorMessage(repo.error || 'Repository indexing previously failed.');
        showToast('Repository indexing previously failed.', 'error');
        return;
      }

      // Status is 'queued' or 'indexing' -> begin polling
      startPolling(repo.id);
    } catch (err) {
      stopPolling();
      setPhase('error');
      const parsed = parseIndexingError(err.message);
      setFailedDetails(parsed);
      setErrorMessage(err.message || 'Error communicating with backend service.');
      showToast(err.message || 'Connection error', 'error');
    }
  };

  const handleRetryIndexing = async () => {
    if (!connectedRepoId) {
      setPhase('form');
      return;
    }

    setIsRetrying(true);
    try {
      const res = await reindexRepository(connectedRepoId, accessToken.trim() || null);
      if (res.success) {
        showToast('Re-indexing job queued in backend worker.', 'info');
        setPhase('analyzing');
        setCurrentStepIndex(0);
        setEmbeddingProgress(null);
        setCompletedSteps([]);
        setShowTechDetails(false);
        startPolling(connectedRepoId);
      } else {
        throw new Error(res.error || 'Failed to trigger re-indexing.');
      }
    } catch (err) {
      if (err.message && err.message.includes('already in progress')) {
        showToast('Indexing is already active. Resuming monitoring.', 'info');
        setPhase('analyzing');
        startPolling(connectedRepoId);
      } else {
        showToast(err.message || 'Retry failed.', 'error');
      }
    } finally {
      setIsRetrying(false);
    }
  };

  return (
    <div className="cv-connect-page">
      <div className="cv-connect-header">
        <h1 className="cv-connect-title">Connect Repository</h1>
        <p className="cv-connect-desc">
          Pick one of your GitHub repositories (private ones included) or paste a URL to index its structure, dependencies and onboarding tasks.
        </p>
      </div>

      {/* GitHub account */}
      <div className="cv-connect-status-box">
        <div className="cv-connect-status-box__icon">
          <GithubIcon size={18} />
        </div>
        <div className="cv-connect-status-box__body">
          <div className="cv-connect-status-box__title-row">
            <span>{user?.githubUsername ? `Signed in as @${user.githubUsername}` : 'GitHub account'}</span>
            {user?.githubConnected ? (
              <span className="cv-status-pill cv-status-pill--ready">Private repos enabled</span>
            ) : (
              <span className="cv-status-pill">Sign in again</span>
            )}
          </div>
          <p className="cv-connect-status-box__note">
            Repositories your GitHub account can read are cloned with your sign-in. Your token is stored encrypted and is never shown in the browser.
          </p>
        </div>
      </div>

      {/* PHASE 1: Form Input */}
      {phase === 'form' && (
        <div className="cv-connect-card">
          <div className="cv-connect-tabs" role="tablist" aria-label="How to choose a repository">
            <button
              type="button"
              role="tab"
              aria-selected={source === 'picker'}
              className={`cv-connect-tab ${source === 'picker' ? 'cv-connect-tab--active' : ''}`}
              onClick={() => setSource('picker')}
            >
              My GitHub repositories
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={source === 'url'}
              className={`cv-connect-tab ${source === 'url' ? 'cv-connect-tab--active' : ''}`}
              onClick={() => setSource('url')}
            >
              Paste a URL
            </button>
          </div>

          {source === 'picker' ? (
            <div className="cv-connect-field">
              <label htmlFor="repo-filter-input" className="cv-connect-label">
                <span>Repository</span>
                <span className="cv-connect-req">*</span>
              </label>
              <div className="cv-connect-input-wrap">
                <Search size={16} className="cv-connect-input-icon" />
                <input
                  id="repo-filter-input"
                  type="text"
                  className="cv-connect-input"
                  placeholder="Filter loaded repositories..."
                  value={ghFilter}
                  onChange={(e) => setGhFilter(e.target.value)}
                  autoComplete="off"
                />
              </div>

              {ghError && (
                <div className="cv-connect-notice cv-connect-notice--error" role="alert">
                  <AlertCircle size={15} />
                  <div>
                    <p>{ghError.message}</p>
                    <div className="cv-connect-notice__actions">
                      {ghError.reauth && (
                        <Button variant="primary" size="sm" onClick={loginWithGitHub}>
                          Sign in with GitHub again
                        </Button>
                      )}
                      <Button variant="secondary" size="sm" onClick={() => { setGhError(null); setGhRepos([]); setGhPage(0); }}>
                        Try again
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {!ghError && (
                <div className="cv-connect-picker" role="listbox" aria-label="Your GitHub repositories">
                  {filteredGhRepos.map((r) => (
                    <button
                      key={r.full_name}
                      type="button"
                      role="option"
                      aria-selected={repoUrl === r.url}
                      className={`cv-connect-picker__item ${repoUrl === r.url ? 'cv-connect-picker__item--selected' : ''}`}
                      onClick={() => chooseRepo(r)}
                    >
                      <span className="cv-connect-picker__name">
                        {r.private && <Lock size={12} aria-label="Private" />}
                        {r.full_name}
                      </span>
                      {r.description && <span className="cv-connect-picker__desc">{r.description}</span>}
                      <span className="cv-connect-picker__meta">
                        {r.private ? 'Private' : 'Public'}
                        {r.language ? ` · ${r.language}` : ''}
                      </span>
                    </button>
                  ))}
                  {ghLoading && <p className="cv-connect-hint-text">Loading your repositories...</p>}
                  {!ghLoading && filteredGhRepos.length === 0 && (
                    <p className="cv-connect-hint-text">
                      {ghRepos.length === 0
                        ? 'No repositories found on your GitHub account.'
                        : 'No loaded repository matches that filter.'}
                    </p>
                  )}
                </div>
              )}

              {!ghError && ghHasMore && !ghLoading && (
                <button type="button" className="cv-connect-link-btn" onClick={loadMoreGitHubRepos}>
                  Load more repositories
                </button>
              )}
              {urlError ? (
                <p className="cv-connect-error-text">
                  <AlertCircle size={13} />
                  <span>{urlError}</span>
                </p>
              ) : (
                <p className="cv-connect-hint-text">
                  Can&apos;t find it? Load more, or use &quot;Paste a URL&quot; (organization repos may need an owner to approve this app on GitHub).
                </p>
              )}
            </div>
          ) : (
            <div className="cv-connect-field">
              <label htmlFor="repo-url-input" className="cv-connect-label">
                <span>Repository URL</span>
                <span className="cv-connect-req">*</span>
              </label>
              <div className="cv-connect-input-wrap">
                <Link2 size={16} className="cv-connect-input-icon" />
                <input
                  id="repo-url-input"
                  type="url"
                  className={`cv-connect-input ${urlError ? 'cv-connect-input--error' : ''}`}
                  placeholder="https://github.com/owner/repository"
                  value={repoUrl}
                  onChange={(e) => {
                    setRepoUrl(e.target.value);
                    setSelectedBranch('');
                    setUrlError('');
                  }}
                />
              </div>
              {urlError ? (
                <p className="cv-connect-error-text">
                  <AlertCircle size={13} />
                  <span>{urlError}</span>
                </p>
              ) : (
                <p className="cv-connect-hint-text">
                  Public repositories, or private ones your GitHub account can access.
                </p>
              )}
            </div>
          )}

          {/* Selected repository summary (picker mode) */}
          {source === 'picker' && parsedRepo && (
            <p className="cv-connect-hint-text">
              Selected: <code>{parsedRepo.fullName}</code>
            </p>
          )}

          <div className="cv-connect-field">
            <label htmlFor="branch-select" className="cv-connect-label">
              <span>Target Branch</span>
            </label>
            {branchesReady && branchInfo.failed ? (
              <>
                <div className="cv-connect-input-wrap">
                  <GitBranch size={16} className="cv-connect-input-icon" />
                  <input
                    id="branch-select"
                    type="text"
                    className="cv-connect-input"
                    placeholder="Default branch (leave empty)"
                    value={selectedBranch}
                    onChange={(e) => setSelectedBranch(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                {branchInfo.reauth ? (
                  <div className="cv-connect-notice cv-connect-notice--error" role="alert">
                    <AlertCircle size={15} />
                    <div>
                      <p>Your GitHub sign-in has expired, so branches cannot be listed.</p>
                      <div className="cv-connect-notice__actions">
                        <Button variant="primary" size="sm" onClick={loginWithGitHub}>
                          Sign in with GitHub again
                        </Button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="cv-connect-hint-text">
                    Branches could not be listed for this repository. Leave this empty to use its default branch.
                  </p>
                )}
              </>
            ) : (
              <>
                <div className="cv-connect-input-wrap">
                  <GitBranch size={16} className="cv-connect-input-icon" />
                  <select
                    id="branch-select"
                    className="cv-connect-select"
                    value={selectedBranch}
                    onChange={(e) => setSelectedBranch(e.target.value)}
                    disabled={!fullName || branchesLoading}
                  >
                    <option value="">
                      {!fullName
                        ? 'Choose a repository first'
                        : branchesLoading
                        ? 'Loading branches...'
                        : `Default branch${branchInfo?.defaultBranch ? ` (${branchInfo.defaultBranch})` : ''}`}
                    </option>
                    {branchesReady &&
                      branchInfo.branches
                        .filter((b) => isValidBranch(b))
                        .map((b) => (
                          <option key={b} value={b}>
                            {b}
                            {b === branchInfo.defaultBranch ? ' (default)' : ''}
                          </option>
                        ))}
                  </select>
                </div>
                {branchesReady && branchInfo.truncated && (
                  <p className="cv-connect-hint-text">Only the first 100 branches are listed.</p>
                )}
              </>
            )}
          </div>

          {/* Optional personal access token (fallback) */}
          <div className="cv-connect-field">
            <button
              type="button"
              className="cv-connect-link-btn"
              onClick={() => setShowTokenField(!showTokenField)}
              aria-expanded={showTokenField}
            >
              {showTokenField ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              <span>Use a personal access token instead (optional)</span>
            </button>
            {showTokenField && (
              <>
                <div className="cv-connect-input-wrap">
                  <KeyRound size={16} className="cv-connect-input-icon" />
                  <input
                    id="token-input"
                    type="password"
                    className="cv-connect-input"
                    placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                    value={accessToken}
                    onChange={(e) => setAccessToken(e.target.value)}
                    autoComplete="off"
                    aria-label="GitHub personal access token"
                  />
                </div>
                <p className="cv-connect-hint-text">
                  Only needed to use different credentials than your sign-in. It is used for this job and never saved.
                </p>
              </>
            )}
          </div>

          <div className="cv-connect-actions">
            <Button
              variant="primary"
              size="md"
              icon={<ArrowRight size={16} />}
              onClick={handleStartAnalysis}
            >
              Connect &amp; Analyze
            </Button>
          </div>
        </div>
      )}

      {/* PHASE 2: Restrained Step Progress */}
      {phase === 'analyzing' && (
        <div className="cv-connect-card">
          <div className="cv-connect-progress-head">
            <div className="cv-btn__spinner" />
            <div>
              <h3>{INDEXING_STEPS[currentStepIndex]?.label || 'Preparing Repository Index'}</h3>
              <p>
                {currentStepIndex === STAGE_ORDER.indexOf('embedding') && embeddingProgress?.total
                  ? `Embedding ${embeddingProgress.total.toLocaleString()} code chunks. This can take a few minutes for large repositories.`
                  : 'Analyzing AST definitions, imports, and component trees...'}
              </p>
            </div>
          </div>

          <div className="cv-connect-stepper">
            {INDEXING_STEPS.map((step, idx) => {
              const isCompleted = completedSteps.includes(idx);
              const isActive = currentStepIndex === idx && !isCompleted;
              return (
                <div
                  key={step.id}
                  className={`cv-step-row ${isCompleted ? 'cv-step-row--done' : ''} ${isActive ? 'cv-step-row--active' : ''}`}
                >
                  <div className="cv-step-indicator" aria-hidden="true">
                    {isCompleted ? (
                      <CheckCircle2 size={16} />
                    ) : isActive ? (
                      <div className="cv-step-spinner" />
                    ) : (
                      <span className="cv-step-dot" />
                    )}
                  </div>
                  <div className="cv-step-content">
                    <span className="cv-step-label">{step.label}</span>
                    {isActive && (
                      <span className="cv-step-status">
                        {step.id === 'embedding' && embeddingProgress?.total
                          ? `${embeddingProgress.completed.toLocaleString()} / ${embeddingProgress.total.toLocaleString()} chunks (${Math.floor((embeddingProgress.completed / embeddingProgress.total) * 100)}%)`
                          : 'Processing...'}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* PHASE 3: Success State */}
      {phase === 'success' && (
        <div className="cv-connect-card cv-connect-card--success">
          <div className="cv-connect-result-icon cv-connect-result-icon--success" aria-hidden="true">
            <CheckCircle2 size={36} />
          </div>
          <h2>Repository Connected</h2>
          <p className="cv-connect-result-desc">
            AST indexing is complete for <code>{parsedRepo ? parsedRepo.fullName : repoUrl}</code> on{' '}
            {selectedBranch ? <>branch <code>{selectedBranch}</code></> : 'its default branch'}.
            File hierarchy and dependency relations are ready.
          </p>

          <div className="cv-connect-result-buttons">
            <Button
              variant="primary"
              size="md"
              icon={<Compass size={16} />}
              onClick={() => navigate(`/repository/${connectedRepoId}`)}
            >
              Repository Overview
            </Button>

            <Button
              variant="secondary"
              size="md"
              icon={<FileCode size={16} />}
              onClick={() => navigate(`/explorer/${connectedRepoId}`)}
            >
              Codebase Explorer
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setPhase('form');
                setCompletedSteps([]);
                setRepoUrl('');
                setSelectedBranch('');
                setAccessToken('');
              }}
            >
              Connect Another
            </Button>
          </div>
        </div>
      )}

      {/* PHASE 4: Error State */}
      {phase === 'error' && (
        <div className="cv-connect-card cv-connect-card--error">
          <div className="cv-connect-result-icon cv-connect-result-icon--error" aria-hidden="true">
            <AlertCircle size={36} />
          </div>
          <h2>{failedDetails?.title || 'Indexing Failed'}</h2>
          <p className="cv-connect-result-desc">
            {failedDetails?.message || errorMessage || 'Background worker encountered an error while indexing this repository.'}
          </p>

          {/* Failing File banner if identified */}
          {failedDetails?.failingFile && (
            <div className="cv-connect-failed-file">
              <FileWarning size={15} className="cv-connect-failed-file__icon" />
              <span className="cv-connect-failed-file__label">Failing File:</span>
              <code className="cv-connect-failed-file__path">{failedDetails.failingFile}</code>
            </div>
          )}

          {/* Advisory banner */}
          {failedDetails?.advisory && (
            <div className="cv-connect-advisory-box">
              <AlertTriangle size={15} className="cv-connect-advisory-box__icon" />
              <p className="cv-connect-advisory-box__text">{failedDetails.advisory}</p>
            </div>
          )}

          {/sign in with github again/i.test(`${failedDetails?.message || ''} ${failedDetails?.technicalDetails || ''}`) && (
            <div className="cv-connect-result-buttons">
              <Button variant="primary" size="md" onClick={loginWithGitHub}>
                Sign in with GitHub again
              </Button>
            </div>
          )}

          {/* Collapsible Technical Details (prevents raw PostgreSQL traceback dump) */}
          {failedDetails?.technicalDetails && (
            <div className="cv-connect-tech-section">
              <button
                type="button"
                className="cv-connect-tech-toggle"
                onClick={() => setShowTechDetails(!showTechDetails)}
                aria-expanded={showTechDetails}
              >
                {showTechDetails ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                <span>{showTechDetails ? 'Hide Technical Details' : 'Show Technical Details'}</span>
              </button>
              {showTechDetails && (
                <div className="cv-connect-tech-wrapper">
                  <pre className="cv-connect-tech-pre">
                    {failedDetails.technicalDetails}
                  </pre>
                </div>
              )}
            </div>
          )}

          <div className="cv-connect-result-buttons">
            {connectedRepoId && failedDetails?.isRetryable !== false && (
              <Button
                variant="primary"
                size="md"
                icon={<RotateCcw size={16} />}
                onClick={handleRetryIndexing}
                disabled={isRetrying}
              >
                {isRetrying ? 'Triggering Re-index...' : 'Retry Indexing'}
              </Button>
            )}

            <Button
              variant={connectedRepoId && failedDetails?.isRetryable !== false ? 'secondary' : 'primary'}
              size="md"
              onClick={() => {
                setPhase('form');
                setCompletedSteps([]);
                setShowTechDetails(false);
              }}
            >
              Change URL / Branch
            </Button>

            <Button
              variant="ghost"
              size="md"
              onClick={() => navigate('/dashboard')}
            >
              Dashboard
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
