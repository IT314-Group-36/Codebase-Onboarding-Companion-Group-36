import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Filter, RefreshCw } from 'lucide-react';
import RepositoryCard from '../components/RepositoryCard';
import SearchInput from '../components/SearchInput';
import EmptyState from '../components/EmptyState';
import ErrorState from '../components/ErrorState';
import LoadingState from '../components/LoadingState';
import Button from '../components/Button';
import { getRepositories, getOnboardingTasks } from '../services/api';
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
  const [tasksNote, setTasksNote] = useState('');    // why there are no tasks to show, when that is the case
  const [isRefreshing, setIsRefreshing] = useState(false);

  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [loadError, setLoadError] = useState(null);

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

          // The first-week plan (real GitHub issues or orientation tasks) with the user's saved progress
          if (!source) {
            setTasks([]);
            setTasksNote('Connect a repository to get a first-week onboarding plan for it.');
          } else if (source.rawStatus !== 'ready') {
            setTasks([]);
            setTasksNote(`${source.name} is still being indexed. Its first-week plan appears when indexing finishes.`);
          } else {
            try {
              const plan = await getOnboardingTasks(source.id);
              if (!isMounted) return;
              setTasks(plan.tasks);
              setTasksNote(plan.tasks.length ? '' : 'No tasks yet. Open the full plan to sync this repository\'s issues.');
            } catch (err) {
              if (!isMounted) return;
              setTasks([]);
              setTasksNote(err.message || 'Could not load the first-week plan.');
            }
          }
        }
      } catch (err) {
        if (!isMounted) return;
        console.warn('Could not load repositories:', err.message);
        if (err.status !== 401) {      // a 401 already sends the user back to sign in
          showToast(err.message || 'Could not load your repositories.', 'error');
          setLoadError(err.message || 'Could not load your repositories.');
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

  const completedCount = tasks.filter((t) => t.status === 'completed').length;
  const progressPercent =
    tasks.length > 0 ? Math.round((completedCount / tasks.length) * 100) : 0;

  const firstName = (user?.name || '').split(' ')[0];
  const hasRepo = activeRepos.length > 0;
  const readyRepo = activeRepos.find((r) => r.rawStatus === 'ready') || null;
  const project = taskRepo || activeRepos[0] || null;
  const currentStepId = !hasRepo ? 'connect' : readyRepo ? 'overview' : null;

  // Steps that need a repository explain why they cannot open yet instead of doing nothing
  const openStep = (section) => () => {
    if (!hasRepo) {
      showToast('Connect a repository first. Then this step will open.', 'warning');
    } else if (!readyRepo) {
      showToast('Your project is still being analyzed. Try again in a few minutes.', 'info');
    } else {
      navigate(`/${section}/${readyRepo.id}`);
    }
  };

  const journey = [
    { id: 'connect', title: 'Connect a repository', text: 'Pick a project from GitHub. We read the code and get it ready in a few minutes.', cta: 'Connect a repository', onClick: () => navigate('/connect') },
    { id: 'overview', title: 'See the overview', text: 'A quick summary of what the project is, the languages it uses and how it is organized.', cta: 'Open the overview', onClick: openStep('repository') },
    { id: 'explore', title: 'Explore the code', text: 'Browse the files. Click any file to read it with a plain-English explanation.', cta: 'Explore the code', onClick: openStep('explorer') },
    { id: 'deps', title: 'See the Dependency Map', text: 'A picture of how the parts of the project connect to each other.', cta: 'Open the map', onClick: openStep('dependencies') },
    { id: 'ask', title: 'Ask a question', text: 'Ask in plain English, for example "How does login work?", and get an answer with the exact code.', cta: 'Ask a question', onClick: openStep('qa') },
    { id: 'tasks', title: 'Follow the first-week plan', text: 'A short list of tasks to get comfortable with the project. Your progress is saved.', cta: 'Open the plan', onClick: openStep('onboarding') },
    { id: 'history', title: 'Check the Git History', text: 'See who changed what and when, and which files change the most.', cta: 'Open Git History', onClick: openStep('history') },
  ];

  let projectStatus = 'Queued';
  if (project?.rawStatus === 'ready') projectStatus = 'Ready';
  else if (project?.status === 'analyzing') projectStatus = 'Analyzing…';
  const known = (v) => v && String(v).toLowerCase() !== 'unknown';
  const projectLine = project?.rawStatus === 'ready'
    ? ['Ready to explore', project.stats?.files ? `${project.stats.files} files read` : null, known(project.language) ? project.language : null].filter(Boolean).join(' · ')
    : 'Reading the code. This takes a few minutes.';

  if (loading) {
    return <LoadingState message="Loading your home page..." fullPage />;
  }

  return (
    <div className="cv-dashboard cv-home">
      <section className="cv-home-header">
        <div>
          <h1 className="cv-dashboard-title">{firstName ? `Welcome, ${firstName}` : 'Welcome'}</h1>
          <p className="cv-dashboard-subtitle">
            Follow these steps to understand any codebase. It takes about five minutes.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          icon={<RefreshCw size={14} className={isRefreshing ? 'cv-icon-spin' : ''} />}
          onClick={handleManualRefresh}
          title="Reload your repositories"
        >
          Refresh
        </Button>
      </section>

      {loadError && !hasRepo ? (
        <ErrorState
          title="Couldn't load your repositories"
          message={loadError}
          onAction={() => { setLoadError(null); setLoading(true); setRefreshTrigger((t) => t + 1); }}
        />
      ) : (
        <>
          {/* Start here: the whole journey, one short step at a time */}
          <section aria-labelledby="cv-home-start">
            <div className="cv-home-section-head">
              <h2 id="cv-home-start" className="cv-section-title">Start here</h2>
              <span className="cv-home-count">Follow the steps in order, or jump to any step once a repository is connected.</span>
            </div>
            <div className="cv-home-steps">
              {journey.map((step, i) => {
                const done = step.id === 'connect' && hasRepo;
                const isCurrent = step.id === currentStepId;
                return (
                  <article className="cv-home-step" key={step.id}>
                    <span className={`cv-home-step__num ${done ? 'is-done' : ''}`}>{done ? '✓' : i + 1}</span>
                    <h3 className="cv-home-step__title">{step.title}</h3>
                    <p className="cv-home-step__text">{step.text}</p>
                    {done ? (
                      <span className="cv-home-chip">Done · {project?.name} connected</span>
                    ) : (
                      <Button variant={isCurrent ? 'primary' : 'secondary'} onClick={step.onClick}>
                        {step.cta}
                      </Button>
                    )}
                  </article>
                );
              })}
            </div>
          </section>

          {/* The project being learned */}
          {project && (
            <section aria-labelledby="cv-home-project">
              <h2 id="cv-home-project" className="cv-section-title cv-home-spaced">Your project</h2>
              <div className="cv-home-project">
                <div className="cv-home-project__top">
                  <div>
                    <span className="cv-home-project__owner">{project.owner}</span>
                    <h3 className="cv-home-project__name">{project.name}</h3>
                    <p className="cv-home-project__line">{projectLine}</p>
                  </div>
                  <span className="cv-home-chip"><span className="cv-home-chip__dot" aria-hidden="true" /> {projectStatus}</span>
                </div>

                <div className="cv-home-plan">
                  <div className="cv-home-plan__row">
                    <span>First-week plan</span>
                    <span className="cv-home-count">
                      {tasks.length > 0 ? `${completedCount} of ${tasks.length} tasks done` : 'Not started'}
                    </span>
                  </div>
                  <div
                    className="cv-progress-track"
                    role="progressbar"
                    aria-label="First-week plan progress"
                    aria-valuenow={progressPercent}
                    aria-valuemin={0}
                    aria-valuemax={100}
                  >
                    <div className="cv-progress-fill" style={{ width: `${progressPercent}%` }} />
                  </div>
                  {tasks.length === 0 && tasksNote && <p className="cv-home-note">{tasksNote}</p>}
                </div>

                <div className="cv-home-actions">
                  <Button variant="secondary" disabled={!readyRepo} onClick={() => navigate(`/qa/${project.id}`)}>Ask a question</Button>
                  <Button variant="secondary" disabled={!readyRepo} onClick={() => navigate(`/explorer/${project.id}`)}>Explore code</Button>
                  <Button variant="secondary" disabled={!readyRepo} onClick={() => navigate(`/onboarding/${project.id}`)}>Open first-week plan</Button>
                </div>
              </div>
            </section>
          )}

          {/* Only when there is more than one project to choose from */}
          {activeRepos.length > 1 && (
            <section className="cv-dashboard-repos" aria-labelledby="cv-home-all">
              <div className="cv-dashboard-section-head">
                <div>
                  <h2 id="cv-home-all" className="cv-section-title">All repositories</h2>
                  <p className="cv-section-desc">Select a repository to open its overview.</p>
                </div>
                <div className="cv-dashboard-controls">
                  <SearchInput value={searchQuery} onChange={setSearchQuery} placeholder="Filter repos..." className="cv-dashboard-search-box" />
                  <div className="cv-dashboard-filter-select">
                    <Filter size={13} className="cv-dashboard-filter-icon" />
                    <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter repositories by status">
                      <option value="all">All</option>
                      <option value="analyzed">Ready</option>
                      <option value="analyzing">Analyzing</option>
                      <option value="pending">Queued</option>
                    </select>
                  </div>
                </div>
              </div>
              {filteredRepos.length === 0 ? (
                <EmptyState
                  title="No matching repositories"
                  description={`No repositories matched "${searchQuery}". Clear your search to see all repositories.`}
                  actionLabel="Clear Filter"
                  onAction={() => setSearchQuery('')}
                />
              ) : (
                <div className="cv-dashboard-repo-cards">
                  {filteredRepos.map((repo) => (
                    <RepositoryCard key={repo.id} repo={repo} />
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
