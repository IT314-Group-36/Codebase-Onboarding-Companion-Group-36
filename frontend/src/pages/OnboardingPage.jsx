import { useState, useEffect, useMemo, useRef, lazy, Suspense } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  CheckCircle2,
  Circle,
  Clock,
  ArrowLeft,
  GitBranch,
  FolderTree,
  Plus,
  FileCode,
  Flame,
  CheckCheck,
  ChevronDown,
  ExternalLink,
} from 'lucide-react';
import { getOnboardingTasks, updateOnboardingTask, getRepositoryById } from '../services/api';
import LoadingState from '../components/LoadingState';
import Button from '../components/Button';
const DimensionalProgressRing = lazy(() => import('../components/3d/DimensionalProgressRing'));
import { showToast } from '../utils/toast';
import './OnboardingPage.css';

// Educational descriptions & checklist metadata mapped by task ID
const TASK_METADATA_MAP = {
  t1: {
    description:
      'Inspect how React Router is wired up in the root component, notice how layout components are scoped, and locate the initial route definitions.',
    targetFiles: ['src/App.jsx', 'package.json'],
    checklist: [
      'Verify client-side route declarations inside <Routes>',
      'Observe the global layout shell boundary',
      'Check package manifest for runtime dependencies',
    ],
    estimatedMinutes: 10,
  },
  t2: {
    description:
      'Analyze how user authentication state is managed, how token credentials are stored and retrieved, and how public vs protected pages are handled.',
    targetFiles: ['src/hooks/useAuth.js', 'src/App.jsx'],
    checklist: [
      'Locate AuthProvider context and exposed hooks',
      'Inspect localStorage token caching mechanism',
      'Understand login and logout dispatch flows',
    ],
    estimatedMinutes: 15,
  },
  t3: {
    description:
      'Understand how outgoing HTTP requests are centralized, how authorization headers are appended, and how errors are normalized.',
    targetFiles: ['src/utils/api.js'],
    checklist: [
      'Trace the centralized fetch wrapper function',
      'Verify Bearer token injection logic',
      'Review error normalization and status checking',
    ],
    estimatedMinutes: 12,
  },
  t4: {
    description:
      'Review the telemetry visualization component, cubic vector calculation, and responsive coordinate transforms.',
    targetFiles: ['src/components/Chart.jsx', 'src/pages/Dashboard.jsx'],
    checklist: [
      'Inspect SVG polyline coordinate generator',
      'Observe prop passed from parent dashboard',
      'Review color token consistency with theme standards',
    ],
    estimatedMinutes: 20,
  },
  t5: {
    description:
      'Inspect module import and export relationships to identify high-coupling hotspots and architectural boundaries.',
    targetFiles: ['src/components/Sidebar.jsx', 'src/components/Header.jsx'],
    checklist: [
      'Trace component import graph',
      'Identify circular dependency prevention strategies',
      'Review shared state hook consumption',
    ],
    estimatedMinutes: 15,
  },
  t6: {
    description:
      'Prepare your first pull request by checking out a feature branch, implementing a small improvement, and running static tests.',
    targetFiles: ['README.md', 'package.json'],
    checklist: [
      'Create a local git branch: git checkout -b feat/onboarding-milestone',
      'Make targeted improvements and run lint checks',
      'Submit PR with clear architectural summary',
    ],
    estimatedMinutes: 30,
  },
};

function enrichTask(task) {
  const extra = TASK_METADATA_MAP[task.id] || {
    description: 'Explore the declared source modules to gain architectural familiarity.',
    targetFiles: ['src/App.jsx'],
    checklist: ['Read code comments', 'Check test suites', 'Inspect dependencies'],
    estimatedMinutes: 15,
  };
  return { ...task, ...extra };
}

/**
 * Page: Dedicated Onboarding Journey & Milestone Task Management
 * Tracks onboarding progress, guided code tours, interactive completion checklists,
 * and deep links into code files.
 */
export default function OnboardingPage() {
  const { repoId } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [repo, setRepo] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [statusFilter, setStatusFilter] = useState('ALL'); // 'ALL' | 'PENDING' | 'COMPLETED'
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [expandedTaskId, setExpandedTaskId] = useState(null);

  // New task modal state
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [newTaskCategory, setNewTaskCategory] = useState('Architecture');
  const [newTaskDifficulty, setNewTaskDifficulty] = useState('medium');
  const [newTaskFile, setNewTaskFile] = useState('src/App.jsx');
  const taskCounterRef = useRef(100);

  useEffect(() => {
    let isMounted = true;
    async function loadData() {
      setLoading(true);
      try {
        const [repoRes, tasksRes] = await Promise.all([
          getRepositoryById(repoId),
          getOnboardingTasks(repoId),
        ]);

        if (isMounted) {
          if (repoRes.success) setRepo(repoRes.repository);
          if (tasksRes.success) {
            // Enhance mock tasks with rich educational descriptions & target files
            const enriched = (tasksRes.tasks || []).map(enrichTask);
            setTasks(enriched);
          }
        }
      } catch (err) {
        console.error('Failed to load onboarding tasks:', err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadData();
    return () => {
      isMounted = false;
    };
  }, [repoId]);

  // Toggle task status
  const handleToggleTask = async (taskId) => {
    const task = tasks.find((t) => t.id === taskId);
    if (!task) return;

    const newStatus = task.status === 'completed' ? 'pending' : 'completed';

    // Optimistic UI update
    setTasks((prev) =>
      prev.map((t) => (t.id === taskId ? { ...t, status: newStatus } : t))
    );

    try {
      await updateOnboardingTask(repoId, taskId, newStatus);
      showToast(
        newStatus === 'completed'
          ? `Milestone marked as complete: "${task.title}"`
          : `Milestone reverted to pending.`,
        'success'
      );
    } catch {
      // Revert if error
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, status: task.status } : t))
      );
      showToast('Failed to update task status.', 'error');
    }
  };

  // Add custom task
  const handleCreateTask = (e) => {
    e.preventDefault();
    if (!newTaskTitle.trim()) return;

    taskCounterRef.current += 1;
    const createdTask = {
      id: `task-custom-${taskCounterRef.current}`,
      title: newTaskTitle.trim(),
      status: 'pending',
      difficulty: newTaskDifficulty,
      category: newTaskCategory,
      description: 'Custom milestone task added by developer during onboarding review.',
      targetFiles: [newTaskFile.trim() || 'src/App.jsx'],
      checklist: ['Review relevant source file', 'Confirm functionality with teammates'],
      estimatedMinutes: 20,
    };

    setTasks((prev) => [createdTask, ...prev]);
    setIsAddModalOpen(false);
    setNewTaskTitle('');
    showToast('New milestone task added to your journey.', 'success');
  };

  // Progress metrics calculation
  const totalTasks = tasks.length;
  const completedCount = tasks.filter((t) => t.status === 'completed').length;
  const inProgressCount = tasks.filter((t) => t.status === 'in-progress').length;
  const pendingCount = tasks.filter((t) => t.status === 'pending').length;
  const progressPercent = totalTasks > 0 ? Math.round((completedCount / totalTasks) * 100) : 0;

  const totalRemainingMinutes = tasks
    .filter((t) => t.status !== 'completed')
    .reduce((acc, t) => acc + (t.estimatedMinutes || 15), 0);

  // Filtered task list
  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      const matchesStatus =
        statusFilter === 'ALL' ||
        (statusFilter === 'COMPLETED' && task.status === 'completed') ||
        (statusFilter === 'PENDING' && task.status !== 'completed');

      const matchesCat =
        categoryFilter === 'ALL' || task.category.toLowerCase() === categoryFilter.toLowerCase();

      return matchesStatus && matchesCat;
    });
  }, [tasks, statusFilter, categoryFilter]);

  if (loading) {
    return <LoadingState message="Loading onboarding journey roadmap..." fullPage />;
  }

  const effectiveRepo = repo || {
    id: repoId,
    name: `Repository ${repoId}`,
    owner: 'GitHub',
    branch: 'main',
  };

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
            <p className="cv-onboarding-subtitle">Guided Onboarding Journey & Architectural Milestones</p>
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
            icon={<Plus size={15} />}
            onClick={() => setIsAddModalOpen(true)}
          >
            Add Task
          </Button>
        </div>
      </header>

      {/* Progress & Milestone Overview Banner */}
      <section className="cv-onboarding-summary-strip">
        <div className="cv-onboarding-progress-card">
          <div className="cv-onboarding-progress-header">
            <div className="cv-onboarding-progress-info">
              <span className="cv-onboarding-progress-label">ONBOARDING READINESS</span>
              <h3 className="cv-onboarding-progress-headline">
                {completedCount} of {totalTasks} milestones completed
              </h3>
              <p className="cv-onboarding-progress-sub">
                Dimensional milestone tracker mapped directly to active codebase tasks.
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

          {/* Progress bar */}
          <div className="cv-onboarding-bar-track">
            <div
              className="cv-onboarding-bar-fill"
              style={{ width: `${progressPercent}%` }}
              role="progressbar"
              aria-valuenow={progressPercent}
              aria-valuemin="0"
              aria-valuemax="100"
            />
          </div>

          <div className="cv-onboarding-stat-pills">
            <span className="cv-onboarding-pill">
              <CheckCheck size={14} style={{ color: 'var(--cv-success)' }} />
              <span>{completedCount} Completed</span>
            </span>
            <span className="cv-onboarding-pill">
              <Clock size={14} style={{ color: 'var(--cv-warning)' }} />
              <span>{inProgressCount} In Progress</span>
            </span>
            <span className="cv-onboarding-pill">
              <Circle size={14} style={{ color: 'var(--cv-text-muted)' }} />
              <span>{pendingCount} Pending</span>
            </span>
            <span className="cv-onboarding-pill cv-onboarding-pill--time">
              <Flame size={14} style={{ color: 'var(--cv-accent-primary)' }} />
              <span>~{totalRemainingMinutes} mins remaining</span>
            </span>
          </div>
        </div>
      </section>

      {/* Filter and Tab Bar */}
      <section className="cv-onboarding-controls">
        <div className="cv-onboarding-status-tabs" role="tablist">
          <button
            type="button"
            className={`cv-onboarding-tab ${statusFilter === 'ALL' ? 'cv-onboarding-tab--active' : ''}`}
            onClick={() => setStatusFilter('ALL')}
          >
            All Milestones ({totalTasks})
          </button>
          <button
            type="button"
            className={`cv-onboarding-tab ${statusFilter === 'PENDING' ? 'cv-onboarding-tab--active' : ''}`}
            onClick={() => setStatusFilter('PENDING')}
          >
            Active & Pending ({totalTasks - completedCount})
          </button>
          <button
            type="button"
            className={`cv-onboarding-tab ${statusFilter === 'COMPLETED' ? 'cv-onboarding-tab--active' : ''}`}
            onClick={() => setStatusFilter('COMPLETED')}
          >
            Completed ({completedCount})
          </button>
        </div>

        <div className="cv-onboarding-category-pills">
          {['ALL', 'Architecture', 'Security', 'Networking', 'UI Components', 'Contribution'].map(
            (cat) => (
              <button
                key={cat}
                type="button"
                className={`cv-onboarding-cat-chip ${categoryFilter === cat ? 'cv-onboarding-cat-chip--active' : ''}`}
                onClick={() => setCategoryFilter(cat)}
              >
                {cat}
              </button>
            )
          )}
        </div>
      </section>

      {/* Task List */}
      <div className="cv-onboarding-list">
        {filteredTasks.length === 0 ? (
          <div className="cv-onboarding-empty">
            <CheckCircle2 size={36} style={{ color: 'var(--cv-success)' }} />
            <h3>No tasks match the active filter</h3>
            <p>Try switching to another category or clearing your search filters.</p>
            <Button variant="secondary" size="sm" onClick={() => { setStatusFilter('ALL'); setCategoryFilter('ALL'); }}>
              Reset Filters
            </Button>
          </div>
        ) : (
          filteredTasks.map((task) => {
            const isCompleted = task.status === 'completed';
            const isExpanded = expandedTaskId === task.id;

            return (
              <article
                key={task.id}
                className={`cv-onboarding-card ${isCompleted ? 'cv-onboarding-card--completed' : ''}`}
              >
                <div className="cv-onboarding-card__head">
                  {/* Completion Checkbox */}
                  <button
                    type="button"
                    className={`cv-onboarding-checkbox ${isCompleted ? 'cv-onboarding-checkbox--checked' : ''}`}
                    onClick={() => handleToggleTask(task.id)}
                    aria-label={isCompleted ? 'Mark as incomplete' : 'Mark as complete'}
                  >
                    {isCompleted ? <CheckCircle2 size={20} /> : <Circle size={20} />}
                  </button>

                  {/* Main Task Title & Badges */}
                  <div className="cv-onboarding-card__info" onClick={() => setExpandedTaskId(isExpanded ? null : task.id)}>
                    <div className="cv-onboarding-card__tags">
                      <span className={`cv-onboarding-diff cv-onboarding-diff--${task.difficulty}`}>
                        {task.difficulty}
                      </span>
                      <span className="cv-onboarding-cat-tag">{task.category}</span>
                      <span className="cv-onboarding-time-tag">
                        <Clock size={12} /> {task.estimatedMinutes} mins
                      </span>
                    </div>

                    <h2 className={`cv-onboarding-card__title ${isCompleted ? 'cv-onboarding-card__title--done' : ''}`}>
                      {task.title}
                    </h2>
                  </div>

                  {/* Expand toggle */}
                  <button
                    type="button"
                    className="cv-onboarding-card__expand"
                    onClick={() => setExpandedTaskId(isExpanded ? null : task.id)}
                    aria-label={isExpanded ? 'Collapse task details' : 'Expand task details'}
                  >
                    <ChevronDown
                      size={18}
                      style={{
                        transform: isExpanded ? 'rotate(180deg)' : 'none',
                        transition: 'transform 0.2s ease',
                      }}
                    />
                  </button>
                </div>

                {/* Description snippet always visible */}
                <p className="cv-onboarding-card__desc">{task.description}</p>

                {/* Target File Deep Links */}
                {task.targetFiles && task.targetFiles.length > 0 && (
                  <div className="cv-onboarding-card__files">
                    <span className="cv-onboarding-files-label">Relevant Files:</span>
                    <div className="cv-onboarding-files-list">
                      {task.targetFiles.map((file) => (
                        <button
                          key={file}
                          type="button"
                          className="cv-onboarding-file-btn"
                          onClick={() =>
                            navigate(`/explorer/${repoId}?file=${encodeURIComponent(file)}`)
                          }
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

                {/* Expanded Checklist */}
                {isExpanded && task.checklist && (
                  <div className="cv-onboarding-card__drawer">
                    <h4 className="cv-onboarding-drawer-title">Suggested Exploration Steps:</h4>
                    <ul className="cv-onboarding-checklist">
                      {task.checklist.map((item, i) => (
                        <li key={i} className="cv-onboarding-check-item">
                          <span className="cv-onboarding-check-bullet" />
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </article>
            );
          })
        )}
      </div>

      {/* Add Custom Task Modal */}
      {isAddModalOpen && (
        <div className="cv-onboarding-modal-overlay" onClick={() => setIsAddModalOpen(false)}>
          <div
            className="cv-onboarding-modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
          >
            <div className="cv-onboarding-modal__head">
              <h3>Create Onboarding Milestone</h3>
              <p>Add a new guided learning task to this repository.</p>
            </div>

            <form onSubmit={handleCreateTask} className="cv-onboarding-modal__form">
              <div className="cv-onboarding-form-group">
                <label htmlFor="task-title">Task Title</label>
                <input
                  id="task-title"
                  type="text"
                  placeholder="e.g. Inspect websocket synchronization loop"
                  value={newTaskTitle}
                  onChange={(e) => setNewTaskTitle(e.target.value)}
                  required
                />
              </div>

              <div className="cv-onboarding-form-row">
                <div className="cv-onboarding-form-group">
                  <label htmlFor="task-cat">Category</label>
                  <select
                    id="task-cat"
                    value={newTaskCategory}
                    onChange={(e) => setNewTaskCategory(e.target.value)}
                  >
                    <option value="Architecture">Architecture</option>
                    <option value="Security">Security</option>
                    <option value="Networking">Networking</option>
                    <option value="UI Components">UI Components</option>
                    <option value="Contribution">Contribution</option>
                  </select>
                </div>

                <div className="cv-onboarding-form-group">
                  <label htmlFor="task-diff">Difficulty</label>
                  <select
                    id="task-diff"
                    value={newTaskDifficulty}
                    onChange={(e) => setNewTaskDifficulty(e.target.value)}
                  >
                    <option value="easy">Easy (10-15m)</option>
                    <option value="medium">Medium (20-30m)</option>
                    <option value="hard">Hard (45m+)</option>
                  </select>
                </div>
              </div>

              <div className="cv-onboarding-form-group">
                <label htmlFor="task-file">Target File / Deep Link</label>
                <input
                  id="task-file"
                  type="text"
                  placeholder="e.g. src/hooks/useData.js"
                  value={newTaskFile}
                  onChange={(e) => setNewTaskFile(e.target.value)}
                />
              </div>

              <div className="cv-onboarding-modal__actions">
                <Button
                  type="button"
                  variant="secondary"
                  size="md"
                  onClick={() => setIsAddModalOpen(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" variant="primary" size="md">
                  Add Milestone
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
