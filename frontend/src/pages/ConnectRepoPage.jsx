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
} from 'lucide-react';
import GithubIcon from '../components/GithubIcon';
import Button from '../components/Button';
import { connectRepository, getRepositoryById, reindexRepository } from '../services/api';
import { parseIndexingError } from '../services/adapters';
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
  const [repoUrl, setRepoUrl] = useState('');
  const [selectedBranch, setSelectedBranch] = useState('main');
  const [accessToken, setAccessToken] = useState('');
  const [showTokenField, setShowTokenField] = useState(false);
  const [urlError, setUrlError] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [failedDetails, setFailedDetails] = useState(null);
  const [showTechDetails, setShowTechDetails] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [phase, setPhase] = useState('form'); // 'form' | 'analyzing' | 'success' | 'error'
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [completedSteps, setCompletedSteps] = useState([]);
  const [connectedRepoId, setConnectedRepoId] = useState(null);

  const pollIntervalRef = useRef(null);

  const sampleBranches = [
    'main',
    'master',
    'develop',
    'staging',
    'feature/onboarding-v1',
    'release/v2.4',
  ];

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
      return 'Repository URL is required.';
    }
    const githubRegex =
      /^https?:\/\/(?:www\.)?github\.com\/([a-zA-Z0-9_.-]+)\/([a-zA-Z0-9_.-]+)/;
    if (!githubRegex.test(url.trim())) {
      return 'Please enter a valid GitHub repository URL (e.g. https://github.com/facebook/react).';
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
    setUrlError('');
    setErrorMessage('');
    setFailedDetails(null);
    setShowTechDetails(false);
    setPhase('analyzing');
    setCurrentStepIndex(0);
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
          Enter a GitHub repository URL to index its directory structure, dependencies, and onboarding tasks.
        </p>
      </div>

      {/* GitHub Connection Status */}
      <div className="cv-connect-status-box">
        <div className="cv-connect-status-box__icon">
          <GithubIcon size={18} />
        </div>
        <div className="cv-connect-status-box__body">
          <div className="cv-connect-status-box__title-row">
            <span>FastAPI Ingestion Engine</span>
            <span className="cv-status-pill cv-status-pill--ready">Backend Connected</span>
          </div>
          <p className="cv-connect-status-box__note">
            Repositories are queued for background AST analysis, tree-sitter symbol extraction, and vector embedding.
          </p>
        </div>
      </div>

      {/* PHASE 1: Form Input */}
      {phase === 'form' && (
        <div className="cv-connect-card">
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
                Public repositories or authorized GitHub organizations.
              </p>
            )}
          </div>

          <div className="cv-connect-field">
            <label htmlFor="branch-select" className="cv-connect-label">
              <span>Target Branch</span>
            </label>
            <div className="cv-connect-input-wrap">
              <GitBranch size={16} className="cv-connect-input-icon" />
              <select
                id="branch-select"
                className="cv-connect-select"
                value={selectedBranch}
                onChange={(e) => setSelectedBranch(e.target.value)}
              >
                {sampleBranches.map((b) => (
                  <option key={b} value={b}>
                    {b} {b === 'main' || b === 'master' ? '(default)' : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Optional Private Repo Access Token */}
          <div className="cv-connect-field">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
              <label htmlFor="token-input" className="cv-connect-label" style={{ marginBottom: 0 }}>
                <span>Private Repository Token</span>
                <span style={{ fontSize: '0.75rem', color: 'var(--cv-text-muted)', marginLeft: '0.5rem' }}>
                  (Optional)
                </span>
              </label>
              <button
                type="button"
                style={{ background: 'none', border: 'none', color: 'var(--cv-primary)', fontSize: '0.8125rem', cursor: 'pointer' }}
                onClick={() => setShowTokenField(!showTokenField)}
              >
                {showTokenField ? 'Hide Token Field' : 'Add GitHub Token for Private Repo'}
              </button>
            </div>

            {showTokenField && (
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
                />
              </div>
            )}
            {showTokenField && (
              <p className="cv-connect-hint-text">
                Used only in memory for this cloning job; never saved to the database.
              </p>
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
              <h3>Parsing Repository Structure</h3>
              <p>Analyzing AST definitions, imports, and component trees...</p>
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
                    {isActive && <span className="cv-step-status">Processing...</span>}
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
            AST indexing is complete for <code>{repoUrl}</code> on branch <code>{selectedBranch}</code>.
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
