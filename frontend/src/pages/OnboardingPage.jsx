import { useState, useEffect, useMemo, useRef, lazy, Suspense } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  CheckCircle2,
  Circle,
  Clock,
  ArrowLeft,
  GitBranch,
  FolderTree,
  RefreshCw,
  FileCode,
  CheckCheck,
  ChevronDown,
  ExternalLink,
  CircleDot,
  Info,
  AlertTriangle,
  LifeBuoy,
} from 'lucide-react';
import {
  getOnboardingTasks,
  updateOnboardingTask,
  getRepositoryById,
  syncRepositoryIssues,
  getIssueSyncStatus,
} from '../services/api';
import LoadingState from '../components/LoadingState';
import Button from '../components/Button';
const DimensionalProgressRing = lazy(() => import('../components/3d/DimensionalProgressRing'));
import { showToast } from '../utils/toast';
import './OnboardingPage.css';

const SYNC_POLL_MS = 2000;
const SYNC_POLL_MAX = 45; // about 90 seconds

const NEXT_STATUS = { pending: 'in-progress', 'in-progress': 'completed', completed: 'pending' };
const NEXT_LABEL = {
  pending: 'Mark as in progress',
  'in-progress': 'Mark as complete',
  completed: 'Mark as not started',
};

const SOURCE_FILTERS = [
  { id: 'ALL', label: 'All' },
  { id: 'issue', label: 'GitHub issues' },
  { id: 'generated', label: 'Orientation' },
];

/** What went wrong with the issue sync, and what the person can do about it. */
function troubleshootingFor(sync, hasIssueTasks) {
  const tips = [];
  if (sync.status === 'failed') {
    tips.push(
      `The last issue sync failed${sync.message ? `: ${sync.message}` : '.'}`,
      'Private repository? Sign out and sign in with GitHub again so the app has a valid token, then press "Sync issues".',
      'GitHub rate limits: if the message mentions a limit, wait a few minutes and try again.',
      'Check that the repository still exists and that issues are enabled in its GitHub settings.'
    );
  } else if (sync.status === 'never') {
    tips.push('Issues have not been fetched yet. Press "Sync issues" to look for beginner-friendly ones.');
  } else if (sync.status === 'ok' && !hasIssueTasks) {
    tips.push(
      'No open issue suits a newcomer (they are assigned, locked or marked hard, or none carries a beginner label such as "good first issue"). The orientation tasks below are your starting point. Ask the maintainers to label a few easy issues.'
    );
  }
  return tips;
}

/**
 * Page: your first-week plan. Beginner-friendly GitHub issues for this repository (easiest first) plus orientation
 * tasks built from the repository's own analysis, with progress saved on the server.
 */
function OnboardingJourney({ repoId }) {
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [repo, setRepo] = useState(null);
  const [plan, setPlan] = useState(null); // { tasks, sync, notes, fallbackUsed, eligibleIssues }
  const [tasks, setTasks] = useState([]);
  const [statusFilter, setStatusFilter] = useState('ALL'); // 'ALL' | 'PENDING' | 'COMPLETED'
  const [sourceFilter, setSourceFilter] = useState('ALL');
  const [expandedTaskId, setExpandedTaskId] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [guiding, setGuiding] = useState(false);
  const savingRef = useRef(new Set()); // task ids with a save in flight (ignore double clicks)
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;
    async function loadData() {
      try {
        const [repoRes, planRes] = await Promise.all([getRepositoryById(repoId), getOnboardingTasks(repoId)]);
        if (!isMounted) return;
        if (repoRes.success) setRepo(repoRes.repository);
        setPlan(planRes);
        setTasks(planRes.tasks);
        setLoadError(null);
      } catch (err) {
        if (isMounted) setLoadError(err.message || 'Could not load the onboarding plan.');
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadData();
    return () => {
      isMounted = false;
    };
  }, [repoId, reloadKey]);

  // Fetch issues from GitHub in the background, then reload the plan when the sync finishes
  const handleSync = async () => {
    if (syncing) return;
    setSyncing(true);
    try {
      let sync = await syncRepositoryIssues(repoId).catch(async (err) => {
        if (err.status === 409) return getIssueSyncStatus(repoId); // already running: just wait for it
        throw err;
      });
      for (let i = 0; i < SYNC_POLL_MAX && aliveRef.current && ['queued', 'syncing'].includes(sync.status); i += 1) {
        await new Promise((resolve) => setTimeout(resolve, SYNC_POLL_MS));
        sync = await getIssueSyncStatus(repoId);
      }
      if (!aliveRef.current) return;
      if (sync.status === 'ok') {
        showToast(sync.fetched ? `Fetched ${sync.fetched} open issues.` : 'Sync finished. No open issues found.', 'success');
      } else if (sync.status === 'failed') {
        showToast(`Issue sync failed: ${sync.message || 'unknown error'}`, 'error');
      } else {
        showToast('The sync is still running. Refresh in a moment.', 'info');
      }
      setReloadKey((k) => k + 1);
    } catch (err) {
      if (aliveRef.current) showToast(err.message || 'Could not start the issue sync.', 'error');
    } finally {
      if (aliveRef.current) setSyncing(false);
    }
  };

  // Ask the LLM for a short guide per issue task (the plan itself works without it). Keeps the saved statuses as they are.
  const handleWriteGuides = async () => {
    if (guiding) return;
    setGuiding(true);
    try {
      const res = await getOnboardingTasks(repoId, { explain: true });
      if (!aliveRef.current) return;
      const guides = new Map(res.tasks.filter((t) => t.guide).map((t) => [t.id, t.guide]));
      setTasks((prev) => prev.map((t) => (guides.has(t.id) ? { ...t, guide: guides.get(t.id) } : t)));
      showToast(guides.size ? 'Guides added. Expand a task to read it.' : 'No guides were written for these tasks.', 'info');
    } catch (err) {
      if (aliveRef.current) {
        showToast(
          err.status === 503 ? 'Guides need an LLM key on the server (LLM_API_KEY).' : err.message || 'Could not write guides.',
          'error'
        );
      }
    } finally {
      if (aliveRef.current) setGuiding(false);
    }
  };

  // pending -> in progress -> completed -> pending. Saved on the server; reverted if the save fails.
  const handleCycleTask = async (taskId) => {
    const task = tasks.find((t) => t.id === taskId);
    if (!task || savingRef.current.has(taskId)) return;
    const previous = task.status;
    const next = NEXT_STATUS[previous] || 'pending';

    savingRef.current.add(taskId);
    setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, status: next } : t)));
    try {
      await updateOnboardingTask(repoId, taskId, next);
    } catch {
      setTasks((prev) => prev.map((t) => (t.id === taskId ? { ...t, status: previous } : t)));
      showToast('Could not save your progress. Please try again.', 'error');
    } finally {
      savingRef.current.delete(taskId);
    }
  };

  const totalTasks = tasks.length;
  const completedCount = tasks.filter((t) => t.status === 'completed').length;
  const inProgressCount = tasks.filter((t) => t.status === 'in-progress').length;
  const pendingCount = totalTasks - completedCount - inProgressCount;
  const progressPercent = totalTasks > 0 ? Math.round((completedCount / totalTasks) * 100) : 0;

  const filteredTasks = useMemo(
    () =>
      tasks.filter((task) => {
        const matchesStatus =
          statusFilter === 'ALL' ||
          (statusFilter === 'COMPLETED' && task.status === 'completed') ||
          (statusFilter === 'PENDING' && task.status !== 'completed');
        const matchesSource = sourceFilter === 'ALL' || task.source === sourceFilter;
        return matchesStatus && matchesSource;
      }),
    [tasks, statusFilter, sourceFilter]
  );

  if (loading) {
    return <LoadingState message="Building your first-week plan..." fullPage />;
  }

  const effectiveRepo = repo || { id: repoId, name: `Repository ${repoId}`, owner: 'GitHub', branch: 'main' };
  const sync = plan?.sync || { status: 'never', message: null, fetched: 0 };
  const hasIssueTasks = tasks.some((t) => t.source === 'issue');
  const tips = troubleshootingFor(sync, hasIssueTasks);
  const howToRun = repo?.summary?.how_to_run && repo.summary.how_to_run !== 'n/a' ? repo.summary.how_to_run : null;
  const syncBusy = syncing || ['queued', 'syncing'].includes(sync.status);

  return (
    <div className="cv-onboarding-page">
      {/* Page Header */}
      <header className="cv-onboarding-header">
        <div className="cv-onboarding-header__main">
          <button
            type="button"
            className="cv-onboarding-back-btn"
            onClick={() => navigate(`/repository/${repoId}`)}
            title="Back to Repository Overview"
          >
            <ArrowLeft size={16} />
          </button>
          <div>
            <div className="cv-onboarding-title-row">
              <span className="cv-onboarding-owner">{effectiveRepo.owner} /</span>
              <h1 className="cv-onboarding-name">{effectiveRepo.name}</h1>
              <span className="cv-onboarding-branch-chip">
                <GitBranch size={12} /> {effectiveRepo.branch}
              </span>
            </div>
            <p className="cv-onboarding-subtitle">Your first-week plan for this repository</p>
          </div>
        </div>

        <div className="cv-onboarding-header__actions">
          <Button
            variant="secondary"
            size="md"
            icon={<FolderTree size={15} />}
            onClick={() => navigate(`/explorer/${repoId}`)}
          >
            Code Explorer
          </Button>

          <Button
            variant="primary"
            size="md"
            icon={<RefreshCw size={15} />}
            onClick={handleSync}
            disabled={syncBusy}
          >
            {syncBusy ? 'Syncing issues...' : 'Sync issues'}
          </Button>
        </div>
      </header>

      {loadError && (
        <div className="cv-onboarding-notice cv-onboarding-notice--error" role="alert">
          <AlertTriangle size={16} />
          <div>
            <strong>Could not load your plan.</strong> {loadError}
            <div>
              <Button variant="secondary" size="sm" onClick={() => { setLoading(true); setReloadKey((k) => k + 1); }}>
                Try again
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Messages from the backend (sync state, fallback explanation) */}
      {!loadError &&
        (plan?.notes || []).map((note) => (
          <div
            key={note}
            className={`cv-onboarding-notice ${note.toLowerCase().includes('failed') ? 'cv-onboarding-notice--warn' : ''}`}
            role="status"
          >
            <Info size={16} />
            <span>{note}</span>
          </div>
        ))}

      {/* Progress & Milestone Overview Banner */}
      <section className="cv-onboarding-summary-strip">
        <div className="cv-onboarding-progress-card">
          <div className="cv-onboarding-progress-header">
            <div className="cv-onboarding-progress-info">
              <span className="cv-onboarding-progress-label">FIRST-WEEK PROGRESS</span>
              <h3 className="cv-onboarding-progress-headline">
                {completedCount} of {totalTasks} tasks completed
              </h3>
              <p className="cv-onboarding-progress-sub">
                {hasIssueTasks
                  ? 'Real beginner-friendly issues from GitHub, easiest first. Your progress is saved to your account.'
                  : 'Orientation tasks built from this repository. Your progress is saved to your account.'}
              </p>
            </div>
            <div className="cv-onboarding-progress-3d-wrap">
              <Suspense fallback={<div style={{ width: 114, height: 114 }} />}>
                <DimensionalProgressRing
                  progressPercent={progressPercent}
                  totalTasks={totalTasks}
                  completedCount={completedCount}
                  size={114}
                />
              </Suspense>
            </div>
          </div>

          <div className="cv-onboarding-bar-track">
            <div
              className="cv-onboarding-bar-fill"
              style={{ width: `${progressPercent}%` }}
              role="progressbar"
              aria-label="First-week progress"
              aria-valuenow={progressPercent}
              aria-valuemin="0"
              aria-valuemax="100"
            />
          </div>

          <div className="cv-onboarding-stat-pills">
            <span className="cv-onboarding-pill">
              <CheckCheck size={14} style={{ color: 'var(--status-success)' }} />
              <span>{completedCount} Completed</span>
            </span>
            <span className="cv-onboarding-pill">
              <Clock size={14} style={{ color: 'var(--status-warning)' }} />
              <span>{inProgressCount} In Progress</span>
            </span>
            <span className="cv-onboarding-pill">
              <Circle size={14} style={{ color: 'var(--text-muted)' }} />
              <span>{pendingCount} Not started</span>
            </span>
            <span className="cv-onboarding-pill cv-onboarding-pill--time">
              <CircleDot size={14} />
              <span>
                {sync.status === 'ok' && sync.syncedAt
                  ? `Issues synced ${new Date(sync.syncedAt).toLocaleDateString()}`
                  : sync.status === 'failed'
                  ? 'Last issue sync failed'
                  : sync.status === 'never'
                  ? 'Issues not synced yet'
                  : 'Syncing issues...'}
              </span>
            </span>
          </div>
        </div>
      </section>

      {/* Setup & troubleshooting */}
      <section className="cv-onboarding-help">
        <button
          type="button"
          className="cv-onboarding-help__toggle"
          onClick={() => setHelpOpen((o) => !o)}
          aria-expanded={helpOpen}
        >
          <LifeBuoy size={16} />
          <span>Setup &amp; troubleshooting</span>
          {tips.length > 0 && <span className="cv-onboarding-help__badge">{tips.length}</span>}
          <ChevronDown
            size={16}
            style={{ marginLeft: 'auto', transform: helpOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s ease' }}
          />
        </button>
        {helpOpen && (
          <div className="cv-onboarding-help__body">
            <h4>Getting set up</h4>
            <ol>
              <li>Clone the repository and open it in your editor.</li>
              {howToRun ? (
                <li>
                  Run it as the project describes: <em>{howToRun}</em>
                </li>
              ) : (
                <li>Read the README for the install and run steps (this repository has no run summary yet).</li>
              )}
              <li>Pick a task below. Open its related files in the Code Explorer to see where to start.</li>
              <li>
                Create a branch for your change (<code>git checkout -b my-first-change</code>), push it, and open a pull
                request. Never push straight to the main branch.
              </li>
            </ol>
            {tips.length > 0 && (
              <>
                <h4>Something not working?</h4>
                <ul>
                  {tips.map((tip) => (
                    <li key={tip}>{tip}</li>
                  ))}
                </ul>
              </>
            )}
            <p className="cv-onboarding-help__foot">
              Task rankings come from issue labels, how clear the description is and how recently it was updated. They
              are a suggestion, so check an issue with the maintainers before you start.
            </p>
          </div>
        )}
      </section>

      {/* Filter and Tab Bar */}
      <section className="cv-onboarding-controls">
        <div className="cv-onboarding-status-tabs" role="group" aria-label="Filter tasks by status">
          <button
            type="button"
            className={`cv-onboarding-tab ${statusFilter === 'ALL' ? 'cv-onboarding-tab--active' : ''}`}
            aria-pressed={statusFilter === 'ALL'}
            onClick={() => setStatusFilter('ALL')}
          >
            All Tasks ({totalTasks})
          </button>
          <button
            type="button"
            className={`cv-onboarding-tab ${statusFilter === 'PENDING' ? 'cv-onboarding-tab--active' : ''}`}
            aria-pressed={statusFilter === 'PENDING'}
            onClick={() => setStatusFilter('PENDING')}
          >
            To do ({totalTasks - completedCount})
          </button>
          <button
            type="button"
            className={`cv-onboarding-tab ${statusFilter === 'COMPLETED' ? 'cv-onboarding-tab--active' : ''}`}
            aria-pressed={statusFilter === 'COMPLETED'}
            onClick={() => setStatusFilter('COMPLETED')}
          >
            Completed ({completedCount})
          </button>
        </div>

        <div className="cv-onboarding-category-pills" role="group" aria-label="Filter tasks by source">
          {SOURCE_FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`cv-onboarding-cat-chip ${sourceFilter === f.id ? 'cv-onboarding-cat-chip--active' : ''}`}
              aria-pressed={sourceFilter === f.id}
              onClick={() => setSourceFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </section>

      {/* Task List */}
      <div className="cv-onboarding-list">
        {totalTasks === 0 && !loadError ? (
          <div className="cv-onboarding-empty">
            <CircleDot size={36} />
            <h3>No tasks yet</h3>
            <p>
              Sync this repository&apos;s GitHub issues to find beginner-friendly ones. If it has none, you will get
              orientation tasks instead.
            </p>
            <Button variant="primary" size="sm" onClick={handleSync} disabled={syncBusy}>
              {syncBusy ? 'Syncing issues...' : 'Sync issues'}
            </Button>
          </div>
        ) : filteredTasks.length === 0 ? (
          <div className="cv-onboarding-empty">
            <CheckCircle2 size={36} style={{ color: 'var(--status-success)' }} />
            <h3>No tasks match the active filter</h3>
            <p>Try another filter to see the rest of your plan.</p>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setStatusFilter('ALL');
                setSourceFilter('ALL');
              }}
            >
              Reset Filters
            </Button>
          </div>
        ) : (
          filteredTasks.map((task) => {
            const isCompleted = task.status === 'completed';
            const isInProgress = task.status === 'in-progress';
            const isExpanded = expandedTaskId === task.id;

            return (
              <article
                key={task.id}
                className={`cv-onboarding-card ${isCompleted ? 'cv-onboarding-card--completed' : ''}`}
              >
                <div className="cv-onboarding-card__head">
                  <button
                    type="button"
                    className={`cv-onboarding-checkbox ${isCompleted ? 'cv-onboarding-checkbox--checked' : ''}`}
                    onClick={() => handleCycleTask(task.id)}
                    aria-label={NEXT_LABEL[task.status] || NEXT_LABEL.pending}
                    title={NEXT_LABEL[task.status] || NEXT_LABEL.pending}
                  >
                    {isCompleted ? <CheckCircle2 size={20} /> : isInProgress ? <Clock size={20} /> : <Circle size={20} />}
                  </button>

                  <div className="cv-onboarding-card__info" onClick={() => setExpandedTaskId(isExpanded ? null : task.id)}>
                    <div className="cv-onboarding-card__tags">
                      <span className={`cv-onboarding-diff cv-onboarding-diff--${task.difficulty}`}>{task.difficulty}</span>
                      <span className="cv-onboarding-cat-tag">
                        {task.source === 'issue' ? `GitHub issue #${task.number}` : 'Orientation'}
                      </span>
                      {isInProgress && <span className="cv-onboarding-cat-tag">In progress</span>}
                      <span className="cv-onboarding-time-tag">Day {task.suggestedDay}</span>
                    </div>

                    <h2 className={`cv-onboarding-card__title ${isCompleted ? 'cv-onboarding-card__title--done' : ''}`}>
                      {task.title}
                    </h2>
                  </div>

                  <button
                    type="button"
                    className="cv-onboarding-card__expand"
                    onClick={() => setExpandedTaskId(isExpanded ? null : task.id)}
                    aria-label={isExpanded ? 'Collapse task details' : 'Expand task details'}
                    aria-expanded={isExpanded}
                  >
                    <ChevronDown
                      size={18}
                      style={{ transform: isExpanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s ease' }}
                    />
                  </button>
                </div>

                {task.description && <p className="cv-onboarding-card__desc">{task.description}</p>}

                {task.labels.length > 0 && (
                  <div className="cv-onboarding-labels">
                    {task.labels.map((label) => (
                      <span key={label} className="cv-onboarding-label-chip">
                        {label}
                      </span>
                    ))}
                  </div>
                )}

                {task.targetFiles.length > 0 && (
                  <div className="cv-onboarding-card__files">
                    <span className="cv-onboarding-files-label">Relevant Files:</span>
                    <div className="cv-onboarding-files-list">
                      {task.targetFiles.map((file) => (
                        <button
                          key={file}
                          type="button"
                          className="cv-onboarding-file-btn"
                          onClick={() => navigate(`/explorer/${repoId}?file=${encodeURIComponent(file)}`)}
                          title={`Open ${file} in Code Explorer`}
                        >
                          <FileCode size={13} />
                          <code>{file}</code>
                          <ExternalLink size={11} className="cv-onboarding-file-ext" />
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {isExpanded && (
                  <div className="cv-onboarding-card__drawer">
                    {task.guide ? (
                      <>
                        <h4 className="cv-onboarding-drawer-title">How to approach it</h4>
                        <ul className="cv-onboarding-checklist">
                          <li className="cv-onboarding-check-item">
                            <span className="cv-onboarding-check-bullet" />
                            <span>
                              <strong>What to do:</strong> {task.guide.whatToDo}
                            </span>
                          </li>
                          <li className="cv-onboarding-check-item">
                            <span className="cv-onboarding-check-bullet" />
                            <span>
                              <strong>Where to start:</strong> {task.guide.whereToStart}
                            </span>
                          </li>
                          <li className="cv-onboarding-check-item">
                            <span className="cv-onboarding-check-bullet" />
                            <span>
                              <strong>Done when:</strong> {task.guide.doneWhen}
                            </span>
                          </li>
                        </ul>
                      </>
                    ) : null}
                    {task.reasons.length > 0 && (
                      <>
                        <h4 className="cv-onboarding-drawer-title">Why this task</h4>
                        <ul className="cv-onboarding-checklist">
                          {task.reasons.map((reason) => (
                            <li key={reason} className="cv-onboarding-check-item">
                              <span className="cv-onboarding-check-bullet" />
                              <span>{reason}</span>
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                    {task.source === 'issue' && !task.guide && (
                      <Button variant="secondary" size="sm" onClick={handleWriteGuides} disabled={guiding}>
                        {guiding ? 'Writing guides...' : 'Write a short guide for these issues'}
                      </Button>
                    )}
                    {task.url && (
                      <a className="cv-onboarding-issue-link" href={task.url} target="_blank" rel="noopener noreferrer">
                        <CircleDot size={14} /> Open issue #{task.number} on GitHub <ExternalLink size={11} />
                      </a>
                    )}
                  </div>
                )}
              </article>
            );
          })
        )}
      </div>
    </div>
  );
}

export default function OnboardingPage() {
  const { repoId } = useParams();
  // keyed by repository so switching repositories starts from a clean state
  return <OnboardingJourney key={repoId} repoId={repoId} />;
}
