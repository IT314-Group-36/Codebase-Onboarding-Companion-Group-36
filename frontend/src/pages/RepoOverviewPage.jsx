import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  FileText,
  Box,
  Boxes,
  Code2,
  GitBranch,
  Clock,
  FolderTree,
  MessageSquare,
  Layers,
  ArrowRight,
  FileCheck,
  CheckCircle2,
  RotateCcw,
  AlertTriangle,
} from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import Button from '../components/Button';
import LoadingState from '../components/LoadingState';
import AskQuestionsModal from '../components/AskQuestionsModal';
import { getRepositoryById, reindexRepository } from '../services/api';
import { showToast } from '../utils/toast';
import './RepoOverviewPage.css';

/**
 * Page 4: Repository Overview (Liquid Chrome & Amber)
 * Technical repository report detailing AST statistics, technology stack,
 * important entry files, architectural summary, and activity timeline.
 */
export default function RepoOverviewPage() {
  const { repoId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [reindexing, setReindexing] = useState(false);
  const [repo, setRepo] = useState(null);
  const [error, setError] = useState(null);
  const [askModalOpen, setAskModalOpen] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    let isMounted = true;
    async function loadRepo() {
      try {
        const res = await getRepositoryById(repoId);
        if (!isMounted) return;
        if (res.success && res.repository) {
          setRepo(res.repository);
        } else {
          setError('Repository specifications could not be loaded.');
        }
      } catch (err) {
        if (!isMounted) return;
        setError(err.message || 'Failed to fetch repository from backend.');
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }
    loadRepo();
    return () => {
      isMounted = false;
    };
  }, [repoId, refreshTrigger]);

  const handleReindex = async () => {
    if (!repo) return;
    setReindexing(true);
    try {
      const res = await reindexRepository(repo.id);
      if (res.success) {
        showToast('Repository re-indexing queued in background worker.', 'success');
        setRefreshTrigger((v) => v + 1);
      }
    } catch (err) {
      showToast(err.message || 'Re-index request failed.', 'error');
    } finally {
      setReindexing(false);
    }
  };

  const handleOpenFileInExplorer = (filePath) => {
    navigate(`/explorer/${repo.id}?file=${encodeURIComponent(filePath)}`);
  };

  // Dark Aurora accent palette for language distribution bar (warm amber, soft blue, electric blue, slate)
  const warmLangColors = ['#F5A524', '#4C9AFF', '#1F6FEB', '#C4845C', '#7B96B2'];

  const importantFilesList = useMemo(() => {
    if (!repo) return [];
    const entryFiles = (repo.moduleMap?.entry_points || []).map((e) => ({
      path: e.path,
      type: 'Entrypoint',
      summary: e.reason || 'Application bootstrap entrypoint identified by AST parser.',
    }));

    const keyFiles = (repo.summary?.key_files || []).map((path) => ({
      path,
      type: 'Key Module',
      summary: 'High-relevance module highlighted in repository architectural digest.',
    }));

    const combined = [
      ...entryFiles,
      ...keyFiles.filter((k) => !entryFiles.some((e) => e.path === k.path)),
    ];

    if (combined.length === 0 && repo.defaultFile) {
      combined.push({
        path: repo.defaultFile,
        type: 'Default File',
        summary: 'Primary detected entrypoint file.',
      });
    }

    return combined;
  }, [repo]);

  const recentTimeline = useMemo(() => {
    if (!repo) return [];
    const items = [];

    if (repo.rawStatus === 'ready') {
      items.push({
        label: `AST index verified (${repo.stats.functions} symbols, ${repo.stats.importEdges || 0} import edges)`,
        time: repo.analyzedAt ? new Date(repo.analyzedAt).toLocaleTimeString() : 'Recently',
        icon: <FileCheck size={14} />,
      });
      items.push({
        label: `Module dependency map generated (${repo.stats.modules} modules)`,
        time: repo.analyzedAt ? new Date(repo.analyzedAt).toLocaleTimeString() : 'Recently',
        icon: <Layers size={14} />,
      });
    }

    if (repo.commitSha) {
      items.push({
        label: `Synchronized commit SHA ${repo.commitSha.slice(0, 8)}`,
        time: 'Checked out',
        icon: <GitBranch size={14} />,
      });
    }

    items.push({
      label: `Repository registered on branch ${repo.branch}`,
      time: repo.connectedAt ? new Date(repo.connectedAt).toLocaleDateString() : 'Connected',
      icon: <CheckCircle2 size={14} />,
    });

    return items;
  }, [repo]);

  if (loading) {
    return <LoadingState message="Loading repository specifications..." fullPage />;
  }

  if (error || !repo) {
    return (
      <div className="cv-repo-not-found" style={{ padding: '4rem 2rem', textAlign: 'center' }}>
        <h2>Repository Not Found</h2>
        <p style={{ color: 'var(--cv-text-secondary)', marginBottom: '1.5rem' }}>
          {error || `Repository ${repoId} is not registered in the backend database.`}
        </p>
        <Button variant="primary" onClick={() => navigate('/dashboard')}>
          Back to Dashboard
        </Button>
      </div>
    );
  }

  return (
    <div className="cv-repo-overview">
      {/* Workspace Header */}
      <section className="cv-ro-header">
        <div className="cv-ro-header__main">
          <div className="cv-ro-header__title-row">
            <span className="cv-ro-owner">{repo.owner} /</span>
            <h1 className="cv-ro-name">{repo.name}</h1>
            <StatusBadge status={repo.status} />
          </div>
          <p className="cv-ro-desc">{repo.description}</p>
          <div className="cv-ro-meta">
            <span className="cv-ro-meta-item">
              <GitBranch size={13} /> <code>{repo.branch}</code>
            </span>
            {repo.commitSha && (
              <span className="cv-ro-meta-item">
                <code>{repo.commitSha.slice(0, 7)}</code>
              </span>
            )}
            <span className="cv-ro-meta-item">
              <Clock size={13} /> Connected {new Date(repo.connectedAt).toLocaleDateString()}
            </span>
          </div>
        </div>

        <div className="cv-ro-header__actions">
          <Button
            variant="secondary"
            size="md"
            icon={<RotateCcw size={14} />}
            onClick={handleReindex}
            loading={reindexing}
            title="Trigger full re-index in background worker"
          >
            Reindex
          </Button>

          <Button
            variant="secondary"
            size="md"
            icon={<Boxes size={15} />}
            onClick={() => navigate(`/dependencies/${repo.id}`)}
          >
            Module Map
          </Button>

          <Button
            variant="secondary"
            size="md"
            icon={<CheckCircle2 size={15} />}
            onClick={() => navigate(`/onboarding/${repo.id}`)}
          >
            Onboarding
          </Button>

          <Button
            variant="secondary"
            size="md"
            icon={<MessageSquare size={15} />}
            onClick={() => navigate(`/qa/${repo.id}`)}
          >
            Codebase Q&A
          </Button>

          <Button
            variant="primary"
            size="md"
            icon={<FolderTree size={15} />}
            onClick={() => navigate(`/explorer/${repo.id}`)}
          >
            Codebase Explorer
          </Button>
        </div>
      </section>

      {/* Warnings Banner if present from backend */}
      {repo.warnings && repo.warnings.length > 0 && (
        <div
          style={{
            margin: '1.25rem 0',
            padding: '0.875rem 1.25rem',
            background: 'rgba(231, 180, 90, 0.08)',
            border: '1px solid rgba(231, 180, 90, 0.3)',
            borderRadius: 'var(--cv-radius-md)',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '0.75rem',
          }}
        >
          <AlertTriangle size={18} style={{ color: 'var(--cv-warning)', flexShrink: 0, marginTop: '2px' }} />
          <div>
            <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--cv-warning)' }}>
              Indexer Notices:
            </span>
            <ul style={{ margin: '0.25rem 0 0 1rem', padding: 0, fontSize: '0.8125rem', color: 'var(--cv-text-secondary)' }}>
              {repo.warnings.map((w, idx) => (
                <li key={idx}>{w}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* Compact Metrics Strip */}
      <section className="cv-ro-metrics-strip" aria-label="AST Metrics">
        <div className="cv-ro-metric-cell">
          <div className="cv-ro-metric-cell__label">
            <FileText size={14} />
            <span>Files</span>
          </div>
          <span className="cv-ro-metric-cell__value">{repo.stats.files}</span>
        </div>

        <div className="cv-ro-metric-cell">
          <div className="cv-ro-metric-cell__label">
            <Box size={14} />
            <span>Modules</span>
          </div>
          <span className="cv-ro-metric-cell__value">{repo.stats.modules}</span>
        </div>

        <div className="cv-ro-metric-cell">
          <div className="cv-ro-metric-cell__label">
            <Code2 size={14} />
            <span>Symbols</span>
          </div>
          <span className="cv-ro-metric-cell__value">{repo.stats.functions}</span>
        </div>

        <div className="cv-ro-metric-cell">
          <div className="cv-ro-metric-cell__label">
            <Layers size={14} />
            <span>Call / Import Edges</span>
          </div>
          <span className="cv-ro-metric-cell__value">{repo.stats.components}</span>
        </div>
      </section>

      {/* Grid: Languages + Architecture Digest */}
      <div className="cv-ro-grid">
        {/* Languages & Detected Technologies (Warm Accent Distribution Bar) */}
        <div className="cv-ro-card">
          <h2 className="cv-ro-card__title">Languages &amp; Technologies</h2>
          <div className="cv-ro-lang-list">
            {Object.entries(repo.languages).map(([lang, pct], idx) => {
              const barColor = warmLangColors[idx % warmLangColors.length];
              return (
                <div key={lang} className="cv-ro-lang-item">
                  <div className="cv-ro-lang-item__head">
                    <span className="cv-ro-lang-item__name">
                      <span
                        className="cv-ro-lang-item__dot"
                        style={{ backgroundColor: barColor }}
                        aria-hidden="true"
                      />
                      {lang}
                    </span>
                    <span className="cv-ro-lang-item__pct">{pct}%</span>
                  </div>
                  <div className="cv-ro-lang-track">
                    <div
                      className="cv-ro-lang-fill"
                      style={{ width: `${pct}%`, backgroundColor: barColor }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="cv-ro-tech-chips">
            <span className="cv-ro-tech-label">Detected stack:</span>
            <div className="cv-ro-tech-tags">
              {repo.technologies.map((t) => (
                <span key={t} className="cv-ro-tech-tag">
                  {t}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Architecture Digest */}
        <div className="cv-ro-card">
          <h2 className="cv-ro-card__title">Architecture Summary</h2>
          <div className="cv-ro-arch-body">
            {repo.summary?.architecture ? (
              <p className="cv-ro-arch-para">{repo.summary.architecture}</p>
            ) : repo.summary?.description ? (
              <p className="cv-ro-arch-para">{repo.summary.description}</p>
            ) : (
              <p className="cv-ro-arch-para">
                Codebase structure indexed with {repo.stats.modules} primary modules and {repo.stats.functions} AST syntax symbols.
              </p>
            )}

            {repo.summary?.how_to_run && repo.summary.how_to_run !== 'n/a' && (
              <div style={{ marginTop: '0.875rem', padding: '0.75rem', background: 'rgba(255,255,255,0.03)', borderRadius: 'var(--cv-radius-sm)', border: '1px solid rgba(255,255,255,0.06)' }}>
                <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--cv-text-muted)', display: 'block', marginBottom: '0.25rem' }}>
                  Execution Setup:
                </span>
                <span style={{ fontSize: '0.875rem', color: 'var(--cv-text-secondary)', fontFamily: 'var(--cv-font-mono)' }}>
                  {repo.summary.how_to_run}
                </span>
              </div>
            )}

            <div className="cv-ro-ai-digest-badge" style={{ marginTop: '1rem' }}>
              <span>Verified AST Architecture · Grounded in static graph facts</span>
            </div>
          </div>
        </div>

        {/* Key Files & Entry Points */}
        <div className="cv-ro-card cv-ro-card--wide">
          <div className="cv-ro-card__head-row">
            <h2 className="cv-ro-card__title">Key Files &amp; Entry Points</h2>
            <span className="cv-ro-card__sublabel">Click any file to inspect in Codebase Explorer</span>
          </div>

          <div className="cv-ro-important-files">
            {importantFilesList.length > 0 ? (
              importantFilesList.map((f) => (
                <div
                  key={f.path}
                  className="cv-ro-file-row"
                  onClick={() => handleOpenFileInExplorer(f.path)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && handleOpenFileInExplorer(f.path)}
                >
                  <div className="cv-ro-file-row__title">
                    <FileText size={15} className="cv-ro-file-row__icon" />
                    <code>{f.path}</code>
                    <span className="cv-ro-file-badge">{f.type}</span>
                  </div>
                  <p className="cv-ro-file-row__desc">{f.summary}</p>
                  <div className="cv-ro-file-row__open" aria-hidden="true">
                    <span>Inspect</span>
                    <ArrowRight size={13} />
                  </div>
                </div>
              ))
            ) : (
              <p style={{ color: 'var(--cv-text-muted)', padding: '1rem' }}>
                No entrypoint files flagged during static analysis.
              </p>
            )}
          </div>
        </div>

        {/* Recent Activity Timeline */}
        <div className="cv-ro-card cv-ro-card--wide">
          <h2 className="cv-ro-card__title">Analysis &amp; Synchronization Timeline</h2>
          <div className="cv-ro-timeline">
            {recentTimeline.map((item, idx) => (
              <div key={idx} className="cv-ro-timeline__item">
                <div className="cv-ro-timeline__point" aria-hidden="true">
                  {item.icon}
                </div>
                <div className="cv-ro-timeline__content">
                  <span className="cv-ro-timeline__label">{item.label}</span>
                  <span className="cv-ro-timeline__time">{item.time}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Ask Questions Modal */}
      <AskQuestionsModal
        open={askModalOpen}
        onClose={() => setAskModalOpen(false)}
        repo={repo}
      />
    </div>
  );
}
