import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  GitBranch,
  Layers,
  Box,
  CheckCircle,
  Plus,
  Check,
  Clock,
  Circle,
  Filter,
  RefreshCw,
} from 'lucide-react';
import StatCard from '../components/StatCard';
import RepositoryCard from '../components/RepositoryCard';
import SearchInput from '../components/SearchInput';
import EmptyState from '../components/EmptyState';
import LoadingState from '../components/LoadingState';
import Button from '../components/Button';
import { getRepositories } from '../services/api';
import { generateOnboardingTasks, saveTaskStatus } from '../services/adapters';
import { useAuth } from '../context/useAuth';
import { showToast } from '../utils/toast';
import './DashboardPage.css';

/**
 * Page 2: Main Dashboard
 * Information-dense developer workspace displaying connected repositories,
 * onboarding progress, and architectural metrics loaded directly from FastAPI backend.
 */
export default function DashboardPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [repos, setRepos] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [tasks, setTasks] = useState([]);
  const [taskRepo, setTaskRepo] = useState(null);   // the repository the milestones belong to
  const [isRefreshing, setIsRefreshing] = useState(false);

  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    let isMounted = true;
    async function loadDashboardRepos() {
      try {
        const res = await getRepositories();
        if (!isMounted) return;
        if (res.success) {
          setRepos(res.repositories || []);

          // Milestones come from the first ready repository (else the first one); none without repositories
          const list = res.repositories || [];
          const source = list.find((r) => r.rawStatus === 'ready') || list[0] || null;
          setTaskRepo(source);
          setTasks(source ? generateOnboardingTasks(source) : []);
        }
      } catch (err) {
        if (!isMounted) return;
        console.warn('Could not load repositories:', err.message);
        if (err.status !== 401) {      // a 401 already sends the user back to sign in
          showToast(err.message || 'Could not load your repositories.', 'error');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
          setIsRefreshing(false);
        }
      }
    }

    loadDashboardRepos();
    return () => {
      isMounted = false;
    };
  }, [refreshTrigger]);

  const handleManualRefresh = () => {
    setIsRefreshing(true);
    setRefreshTrigger((v) => v + 1);
  };

  const handleToggleTask = (taskId) => {
    setTasks((prev) =>
      prev.map((t) => {
        if (t.id === taskId) {
          const nextStatus =
            t.status === 'completed'
              ? 'in-progress'
              : t.status === 'in-progress'
              ? 'pending'
              : 'completed';

          if (taskRepo) {
            saveTaskStatus(taskRepo.id, taskId, nextStatus);
          }
          return { ...t, status: nextStatus };
        }
        return t;
      })
    );
    showToast('Task status updated.', 'info');
  };

  const activeRepos = repos;

  const filteredRepos = useMemo(() => {
    return activeRepos.filter((repo) => {
      const matchesSearch =
        repo.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        repo.owner.toLowerCase().includes(searchQuery.toLowerCase()) ||
        repo.language.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesStatus = statusFilter === 'all' || repo.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [activeRepos, searchQuery, statusFilter]);

  // Aggregate stats dynamically across active repositories
  const totalFiles = useMemo(() => {
    return activeRepos.reduce((acc, r) => acc + (r.stats?.files || 0), 0);
  }, [activeRepos]);

  const totalModules = useMemo(() => {
    return activeRepos.reduce((acc, r) => acc + (r.stats?.modules || 0), 0);
  }, [activeRepos]);

  const totalFunctions = useMemo(() => {
    return activeRepos.reduce((acc, r) => acc + (r.stats?.functions || 0), 0);
  }, [activeRepos]);

  const completedCount = tasks.filter((t) => t.status === 'completed').length;
  const progressPercent =
    tasks.length > 0 ? Math.round((completedCount / tasks.length) * 100) : 0;

  if (loading) {
    return <LoadingState message="Loading dashboard..." fullPage />;
  }

  return (
    <div className="cv-dashboard">
      {/* Top Header & Primary Action */}
      <section className="cv-dashboard-header">
        <div className="cv-dashboard-header__left">
          <div className="cv-dashboard-header__copy">
            <div className="cv-dashboard-header__title-row">
              <h1 className="cv-dashboard-title">Dashboard</h1>
              <span className="cv-dashboard-user-pill">
                {user?.name}{user?.githubUsername ? ` · @${user.githubUsername}` : ''}
              </span>
            </div>
            <p className="cv-dashboard-subtitle">
              Overview of connected repositories, AST analysis status, and onboarding milestones.
            </p>
          </div>
        </div>

        <div className="cv-dashboard-header__actions">
          <Button
            variant="secondary"
            size="md"
            icon={<RefreshCw size={14} className={isRefreshing ? 'cv-icon-spin' : ''} />}
            onClick={handleManualRefresh}
            title="Reload your repositories"
          >
            Refresh
          </Button>

          <Button
            variant="primary"
            size="md"
            icon={<Plus size={16} />}
            onClick={() => navigate('/connect')}
          >
            Connect Repository
          </Button>
        </div>
      </section>

      {/* Metric Cards Ribbon */}
      <section className="cv-dashboard-stats" aria-label="Summary Statistics">
        <StatCard
          icon={<GitBranch size={18} />}
          label="Connected Repositories"
          value={activeRepos.length}
          sublabel={`${activeRepos.filter((r) => r.status === 'analyzed').length} fully analyzed`}
        />
        <StatCard
          icon={<Layers size={18} />}
          label="Mapped Modules"
          value={totalModules}
          sublabel="Across active repositories"
        />
        <StatCard
          icon={<Box size={18} />}
          label="Indexed Symbols"
          value={totalFunctions || totalFiles}
          sublabel="AST syntax nodes in database"
        />
        <StatCard
          icon={<CheckCircle size={18} />}
          label="Onboarding Progress"
          value={`${progressPercent}%`}
          sublabel={`${completedCount} of ${tasks.length} tasks ready`}
        />
      </section>

      {/* Content Split: Repositories (Left) & Onboarding (Right) */}
      <div className="cv-dashboard-layout">
        {/* Left: Repositories */}
        <section className="cv-dashboard-repos" aria-label="Repository List">
          <div className="cv-dashboard-section-head">
            <div>
              <h2 className="cv-section-title">Repositories</h2>
              <p className="cv-section-desc">Select a repository to explore structure and dependency paths.</p>
            </div>

            {activeRepos.length > 0 && (
              <div className="cv-dashboard-controls">
                <SearchInput
                  value={searchQuery}
                  onChange={setSearchQuery}
                  placeholder="Filter repos..."
                  className="cv-dashboard-search-box"
                />

                <div className="cv-dashboard-filter-select">
                  <Filter size={13} className="cv-dashboard-filter-icon" />
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    aria-label="Filter repositories by status"
                  >
                    <option value="all">All</option>
                    <option value="analyzed">Analyzed</option>
                    <option value="analyzing">Analyzing</option>
                    <option value="pending">Queued</option>
                  </select>
                </div>
              </div>
            )}
          </div>

          {filteredRepos.length === 0 ? (
            <EmptyState
              title={activeRepos.length === 0 ? 'No Repositories Connected' : 'No matching repositories'}
              description={
                activeRepos.length === 0
                  ? 'Connect your first GitHub repository to parse directory hierarchies and generate onboarding paths.'
                  : `No repositories matched "${searchQuery}". Clear your search query to see all repositories.`
              }
              actionLabel={activeRepos.length === 0 ? 'Connect Repository' : 'Clear Filter'}
              onAction={() => (activeRepos.length === 0 ? navigate('/connect') : setSearchQuery(''))}
            />
          ) : (
            <div className="cv-dashboard-repo-cards">
              {filteredRepos.map((repo) => (
                <RepositoryCard key={repo.id} repo={repo} />
              ))}
            </div>
          )}
        </section>

        {/* Right: Onboarding Roadmap */}
        <section className="cv-dashboard-sidebar-panel" aria-label="Onboarding Roadmap">
          <div className="cv-dashboard-section-head">
            <div>
              <h2 className="cv-section-title">Onboarding Journey</h2>
              <p className="cv-section-desc">Recommended milestones for unfamiliar code.</p>
            </div>
          </div>

          <div className="cv-onboarding-card">
            <div className="cv-onboarding-progress-block">
              <div className="cv-onboarding-progress-row">
                <span className="cv-onboarding-progress-label">Completion</span>
                <span className="cv-onboarding-progress-value">{progressPercent}%</span>
              </div>
              <div className="cv-progress-track">
                <div
                  className="cv-progress-fill"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <span className="cv-onboarding-milestone-text">
                {completedCount} of {tasks.length} milestones complete
              </span>
            </div>

            {tasks.length === 0 && (
              <p className="cv-section-desc" style={{ padding: '0.75rem 0' }}>
                Connect a repository to get a first-week onboarding checklist for it.
              </p>
            )}

            <div className="cv-onboarding-task-list">
              {tasks.map((task) => {
                const isDone = task.status === 'completed';
                const isInProg = task.status === 'in-progress';
                return (
                  <div
                    key={task.id}
                    className={`cv-task-row cv-task-row--${task.status}`}
                    onClick={() => handleToggleTask(task.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && handleToggleTask(task.id)}
                    title="Click to cycle status"
                  >
                    <div className="cv-task-row__status" aria-hidden="true">
                      {isDone ? (
                        <Check size={12} />
                      ) : isInProg ? (
                        <Clock size={11} />
                      ) : (
                        <Circle size={10} />
                      )}
                    </div>
                    <div className="cv-task-row__body">
                      <span className="cv-task-row__title">{task.title}</span>
                      <div className="cv-task-row__meta">
                        <span className="cv-task-row__category">{task.category}</span>
                        <span className={`cv-diff-chip cv-diff-chip--${task.difficulty}`}>
                          {task.difficulty}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {tasks.length > 0 && (
              <div className="cv-onboarding-tip">
                <span>Tip: Click any task to toggle status between completed, in-progress, and pending.</span>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
