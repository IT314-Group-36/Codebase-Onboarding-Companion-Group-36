import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  FolderTree,
  ArrowRight,
  GitBranch,
  Search,
  ArrowLeft,
  FileCode,
  Compass,
  X,
  Maximize,
  Minimize,
  RefreshCw,
  Plus,
  Minus,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react';
import { getDependencyGraph, getRepositoryById } from '../services/api';
import LoadingState from '../components/LoadingState';
import EmptyState from '../components/EmptyState';
import Button from '../components/Button';
import CodebaseGraph from '../components/graph/CodebaseGraph';
import { normalizeGraphData } from '../components/graph/graphAdapter';
import './DependencyMapPage.css';

/**
 * Page: Codebase Dependency Graph
 *
 * Professional, interactive, animated codebase dependency graph
 * built with @xyflow/react, Dagre hierarchical layout, and data-driven
 * branch expansion/collapse.
 *
 * Strictly adheres to the final 4-colour brand palette:
 * - Classic Black: #000000
 * - Golden Pitch: #3D3A2B
 * - Power Orange: #FF4E08
 * - Off White: #E6E5C7
 */
export default function DependencyMapPage() {
  const { repoId } = useParams();
  const navigate = useNavigate();
  const graphRef = useRef(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [repo, setRepo] = useState(null);
  const [rawGraphData, setRawGraphData] = useState(null);
  const [reloadTrigger, setReloadTrigger] = useState(0);

  // Interaction states
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [expandedNodeIds, setExpandedNodeIds] = useState(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedLayer, setSelectedLayer] = useState('ALL');
  const [isInspectorOpen, setIsInspectorOpen] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Load backend data asynchronously without synchronous effect setState
  useEffect(() => {
    let isMounted = true;
    async function executeLoad() {
      try {
        const [repoRes, graphRes] = await Promise.all([
          getRepositoryById(repoId),
          getDependencyGraph(repoId),
        ]);

        if (!isMounted) return;

        if (repoRes && repoRes.success) {
          setRepo(repoRes.repository);
        }

        if (graphRes && (graphRes.graph || graphRes.nodes || graphRes.data)) {
          const normalized = normalizeGraphData(graphRes);
          setRawGraphData(graphRes);
          if (normalized.rootNodeIds.length > 0) {
            setExpandedNodeIds(new Set(normalized.rootNodeIds));
            setSelectedNodeId(normalized.rootNodeIds[0]);
          }
        } else {
          throw new Error('Invalid graph data format returned by server.');
        }
      } catch (err) {
        if (!isMounted) return;
        console.error('Failed to load dependency graph:', err);
        setError(err.message || 'Failed to communicate with codebase analysis backend.');
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    executeLoad();

    return () => {
      isMounted = false;
    };
  }, [repoId, reloadTrigger]);

  const handleRetry = useCallback(() => {
    setLoading(true);
    setError(null);
    setReloadTrigger((v) => v + 1);
  }, []);

  // Normalize raw backend payload into indexed model
  const graphModel = useMemo(() => {
    return normalizeGraphData(rawGraphData);
  }, [rawGraphData]);

  // Escape key exits fullscreen
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isFullscreen) {
        setIsFullscreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen]);

  // Branch expand / collapse handler
  const handleToggleExpand = useCallback((nodeId) => {
    setExpandedNodeIds((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  }, []);

  // Expand all branches
  const handleExpandAll = useCallback(() => {
    const allExpandable = new Set();
    for (const [id, children] of graphModel.outEdgesMap.entries()) {
      if (children.length > 0) {
        allExpandable.add(id);
      }
    }
    setExpandedNodeIds(allExpandable);
  }, [graphModel.outEdgesMap]);

  // Collapse all branches back to root seeds
  const handleCollapseAll = useCallback(() => {
    setExpandedNodeIds(new Set(graphModel.rootNodeIds));
  }, [graphModel.rootNodeIds]);

  // Node selection & camera focus
  const handleSelectNode = useCallback((nodeId) => {
    setSelectedNodeId(nodeId);
    if (nodeId) {
      setIsInspectorOpen(true);
    }
  }, []);

  const handleSelectAndFocusNode = useCallback((nodeId) => {
    setSelectedNodeId(nodeId);
    setIsInspectorOpen(true);
    if (graphRef.current) {
      graphRef.current.focusNode(nodeId);
    }
  }, []);

  // Open file in Code Explorer
  const handleOpenInExplorer = useCallback(
    (filePath) => {
      navigate(`/explorer/${repoId}?file=${encodeURIComponent(filePath)}`);
    },
    [navigate, repoId]
  );

  // Selected node details object
  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return graphModel.nodesMap.get(selectedNodeId) || null;
  }, [selectedNodeId, graphModel.nodesMap]);

  // Connected incoming (dependents) and outgoing (dependencies)
  const connectedLists = useMemo(() => {
    if (!selectedNodeId) return { incoming: [], outgoing: [] };
    const incoming = graphModel.inEdgesMap.get(selectedNodeId) || [];
    const outgoing = graphModel.outEdgesMap.get(selectedNodeId) || [];
    return { incoming, outgoing };
  }, [selectedNodeId, graphModel.inEdgesMap, graphModel.outEdgesMap]);

  if (loading) {
    return <LoadingState message="Synthesizing module dependency graph via AST analysis..." fullPage />;
  }

  if (error) {
    return (
      <div className="cv-depmap-error-view">
        <div className="cv-depmap-error-card">
          <AlertTriangle size={38} className="cv-depmap-error-icon" />
          <h2 className="cv-depmap-error-title">Codebase Graph Unavailable</h2>
          <p className="cv-depmap-error-desc">{error}</p>
          <div className="cv-depmap-error-actions">
            <Button variant="primary" icon={<RefreshCw size={15} />} onClick={handleRetry}>
              Retry Analysis
            </Button>
            <Button variant="secondary" onClick={() => navigate(`/repository/${repoId}`)}>
              Back to Repository
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (graphModel.nodesMap.size === 0) {
    return (
      <div className="cv-depmap-empty-view">
        <EmptyState
          icon={<FolderTree size={40} />}
          title="No Module Dependencies Found"
          description="The repository does not currently expose detectable import or call relationships."
          actionLabel="Return to Repository"
          onAction={() => navigate(`/repository/${repoId}`)}
        />
      </div>
    );
  }

  const effectiveRepo = repo || {
    id: repoId,
    name: `Repository ${repoId}`,
    owner: 'GitHub',
    branch: 'main',
  };

  return (
    <div className={`cv-depmap-page ${isFullscreen ? 'cv-depmap-page--fullscreen' : ''}`}>
      {/* Top Application Toolbar */}
      <header className="cv-depmap-header">
        <div className="cv-depmap-header__left">
          <button
            type="button"
            className="cv-depmap-back-btn"
            onClick={() => navigate(`/repository/${repoId}`)}
            title="Back to Repository Overview"
            aria-label="Back to Repository Overview"
          >
            <ArrowLeft size={16} />
          </button>

          <div className="cv-depmap-header__title-box">
            <div className="cv-depmap-header__repo-line">
              <span className="cv-depmap-owner">{effectiveRepo.owner} /</span>
              <h1 className="cv-depmap-repo-name">{effectiveRepo.name}</h1>
              <span className="cv-depmap-branch-chip">
                <GitBranch size={12} /> {effectiveRepo.branch}
              </span>
            </div>
            <p className="cv-depmap-subtitle">
              Interactive Animated Codebase Dependency Graph & AST Call Pathways
            </p>
          </div>
        </div>

        {/* Graph Telemetry Stats */}
        <div className="cv-depmap-header__stats">
          <div className="cv-depmap-stat-pill" title="Total Analyzed Modules">
            <span className="cv-depmap-stat-num">{graphModel.stats.totalNodes}</span>
            <span className="cv-depmap-stat-label">Modules</span>
          </div>
          <div className="cv-depmap-stat-pill" title="Total Dependency Edges">
            <span className="cv-depmap-stat-num">{graphModel.stats.totalEdges}</span>
            <span className="cv-depmap-stat-label">Edges</span>
          </div>
          <div className="cv-depmap-stat-pill" title="Circular Dependencies Detected">
            <span className="cv-depmap-stat-num cv-depmap-stat-num--cycles">
              {graphModel.stats.circularDependencies}
            </span>
            <span className="cv-depmap-stat-label">Cycles</span>
          </div>
          <div className="cv-depmap-stat-pill" title="Maximum Hierarchy Depth">
            <span className="cv-depmap-stat-num">{graphModel.stats.maxDepth}</span>
            <span className="cv-depmap-stat-label">Max Depth</span>
          </div>

          <Button
            variant="secondary"
            size="sm"
            icon={<FolderTree size={14} />}
            onClick={() => navigate(`/explorer/${repoId}`)}
            className="cv-depmap-explorer-nav-btn"
          >
            Code Explorer
          </Button>

          {isFullscreen && (
            <button
              type="button"
              className="cv-depmap-exit-fs-btn"
              onClick={() => setIsFullscreen(false)}
              title="Exit Fullscreen (Esc)"
            >
              <Minimize size={14} />
              <span>Exit Fullscreen</span>
            </button>
          )}
        </div>
      </header>

      {/* Interactive Controls & Filters Bar */}
      <section className="cv-depmap-controls">
        {/* Search Input */}
        <div className="cv-depmap-controls__search">
          <Search size={14} className="cv-depmap-search-icon" />
          <input
            type="text"
            className="cv-depmap-search-input"
            placeholder="Search module or symbol..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search module or symbol"
          />
          {searchQuery && (
            <button
              type="button"
              className="cv-depmap-clear-search"
              onClick={() => setSearchQuery('')}
              aria-label="Clear search"
            >
              <X size={13} />
            </button>
          )}
        </div>

        {/* Architectural Layer Filter Chips */}
        <div className="cv-depmap-filters" role="tablist" aria-label="Module Layer Filter">
          <button
            type="button"
            className={`cv-depmap-filter-chip ${selectedLayer === 'ALL' ? 'cv-depmap-filter-chip--active' : ''}`}
            onClick={() => setSelectedLayer('ALL')}
          >
            All Modules
          </button>
          <button
            type="button"
            className={`cv-depmap-filter-chip ${selectedLayer === 'entrypoint' ? 'cv-depmap-filter-chip--active' : ''}`}
            onClick={() => setSelectedLayer('entrypoint')}
          >
            Entrypoint
          </button>
          <button
            type="button"
            className={`cv-depmap-filter-chip ${selectedLayer === 'component' ? 'cv-depmap-filter-chip--active' : ''}`}
            onClick={() => setSelectedLayer('component')}
          >
            UI Components
          </button>
          <button
            type="button"
            className={`cv-depmap-filter-chip ${selectedLayer === 'hook' ? 'cv-depmap-filter-chip--active' : ''}`}
            onClick={() => setSelectedLayer('hook')}
          >
            Hooks & Context
          </button>
          <button
            type="button"
            className={`cv-depmap-filter-chip ${selectedLayer === 'api' ? 'cv-depmap-filter-chip--active' : ''}`}
            onClick={() => setSelectedLayer('api')}
          >
            Networking & API
          </button>
          <button
            type="button"
            className={`cv-depmap-filter-chip ${selectedLayer === 'util' ? 'cv-depmap-filter-chip--active' : ''}`}
            onClick={() => setSelectedLayer('util')}
          >
            Utilities
          </button>
        </div>

        {/* Viewport & Hierarchy Tools */}
        <div className="cv-depmap-viewport-tools">
          <button
            type="button"
            className="cv-depmap-tool-btn"
            onClick={handleExpandAll}
            title="Expand All Module Branches"
            aria-label="Expand all module branches"
          >
            <Plus size={15} />
            <span className="cv-depmap-tool-btn-text">Expand All</span>
          </button>

          <button
            type="button"
            className="cv-depmap-tool-btn"
            onClick={handleCollapseAll}
            title="Collapse to Root Seeds"
            aria-label="Collapse to root seeds"
          >
            <Minus size={15} />
            <span className="cv-depmap-tool-btn-text">Collapse All</span>
          </button>

          <div className="cv-depmap-tools-divider" />

          <button
            type="button"
            className="cv-depmap-tool-btn"
            onClick={() => graphRef.current?.zoomIn()}
            title="Zoom In"
            aria-label="Zoom in"
          >
            <ZoomIn size={15} />
          </button>

          <button
            type="button"
            className="cv-depmap-tool-btn"
            onClick={() => graphRef.current?.zoomOut()}
            title="Zoom Out"
            aria-label="Zoom out"
          >
            <ZoomOut size={15} />
          </button>

          <button
            type="button"
            className="cv-depmap-tool-btn"
            onClick={() => graphRef.current?.fitView()}
            title="Fit Graph to Viewport"
            aria-label="Fit graph to viewport"
          >
            <Maximize2 size={15} />
          </button>

          <button
            type="button"
            className="cv-depmap-tool-btn"
            onClick={() => graphRef.current?.resetView()}
            title="Reset Camera"
            aria-label="Reset camera"
          >
            <RotateCcw size={14} />
          </button>

          <div className="cv-depmap-tools-divider" />

          <button
            type="button"
            className={`cv-depmap-tool-btn ${isFullscreen ? 'cv-depmap-tool-btn--active' : ''}`}
            onClick={() => setIsFullscreen(!isFullscreen)}
            title={isFullscreen ? 'Exit Fullscreen' : 'Full-Screen Graph Mode'}
            aria-label="Toggle fullscreen mode"
          >
            {isFullscreen ? <Minimize size={15} /> : <Maximize size={15} />}
          </button>
        </div>
      </section>

      {/* Main Workspace Canvas Area */}
      <div className="cv-depmap-workspace">
        <CodebaseGraph
          ref={graphRef}
          graphModel={graphModel}
          expandedNodeIds={expandedNodeIds}
          selectedNodeId={selectedNodeId}
          searchQuery={searchQuery}
          selectedLayer={selectedLayer}
          onSelectNode={handleSelectNode}
          onToggleExpand={handleToggleExpand}
          isFullscreen={isFullscreen}
        />

        {/* Quick HUD Legend (Bottom Left) */}
        <div className="cv-depmap-hud-legend">
          <div className="cv-depmap-hud-item">
            <span className="cv-depmap-hud-dot cv-depmap-hud-dot--active" />
            <span>Active Dependency Flow (Power Orange)</span>
          </div>
          <div className="cv-depmap-hud-item">
            <span className="cv-depmap-hud-dot cv-depmap-hud-dot--inactive" />
            <span>Static Dependency (Golden Pitch)</span>
          </div>
          <div className="cv-depmap-hud-item cv-depmap-hud-hint">
            <span>Click node to inspect · Click [+N] to expand branches</span>
          </div>
        </div>

        {/* Module Details Inspector Drawer (Right Side) */}
        {isInspectorOpen && selectedNode && (
          <aside className="cv-depmap-inspector" aria-label="Module Details Inspector">
            <div className="cv-depmap-inspector__header">
              <div className="cv-depmap-inspector__title-box">
                <FileCode size={18} className="cv-depmap-inspector__icon" />
                <div>
                  <h3 className="cv-depmap-inspector__name">{selectedNode.name}</h3>
                  <code className="cv-depmap-inspector__path">{selectedNode.path}</code>
                </div>
              </div>
              <button
                type="button"
                className="cv-depmap-inspector__close"
                onClick={() => setIsInspectorOpen(false)}
                title="Close Inspector"
                aria-label="Close inspector"
              >
                <X size={16} />
              </button>
            </div>

            <div className="cv-depmap-inspector__content">
              {/* Layer & Complexity Strip */}
              <div className="cv-depmap-inspector__meta-grid">
                <div className="cv-depmap-inspector__meta-item">
                  <span className="cv-depmap-inspector__meta-label">Module Layer</span>
                  <span className="cv-depmap-inspector__meta-val">{selectedNode.layer}</span>
                </div>
                <div className="cv-depmap-inspector__meta-item">
                  <span className="cv-depmap-inspector__meta-label">Lines of Code</span>
                  <span className="cv-depmap-inspector__meta-val">
                    {selectedNode.lines > 0 ? `${selectedNode.lines} LOC` : 'N/A'}
                  </span>
                </div>
                <div className="cv-depmap-inspector__meta-item">
                  <span className="cv-depmap-inspector__meta-label">Dependencies</span>
                  <span className="cv-depmap-inspector__meta-val">{connectedLists.outgoing.length}</span>
                </div>
                <div className="cv-depmap-inspector__meta-item">
                  <span className="cv-depmap-inspector__meta-label">Dependents</span>
                  <span className="cv-depmap-inspector__meta-val">{connectedLists.incoming.length}</span>
                </div>
              </div>

              {/* Action Button: Open in Code Explorer */}
              <div className="cv-depmap-inspector__cta">
                <Button
                  variant="primary"
                  size="md"
                  icon={<FolderTree size={16} />}
                  onClick={() => handleOpenInExplorer(selectedNode.path)}
                  className="cv-depmap-open-explorer-btn"
                >
                  Open in Code Explorer
                </Button>
              </div>

              {/* Upstream Dependents (Imported by) */}
              <div className="cv-depmap-inspector__section">
                <h4 className="cv-depmap-inspector__section-title">
                  <span className="cv-depmap-section-dot cv-depmap-section-dot--incoming" />
                  Imported By ({connectedLists.incoming.length})
                </h4>
                {connectedLists.incoming.length === 0 ? (
                  <p className="cv-depmap-empty-hint">None (Root entrypoint or top-level provider)</p>
                ) : (
                  <div className="cv-depmap-pill-list">
                    {connectedLists.incoming.map((edge) => (
                      <button
                        key={`incoming-${edge.source}`}
                        type="button"
                        className="cv-depmap-rel-chip cv-depmap-rel-chip--incoming"
                        onClick={() => handleSelectAndFocusNode(edge.source)}
                        title={`Select & focus ${edge.source}`}
                      >
                        <span className="cv-depmap-rel-chip__name">{edge.source}</span>
                        {edge.label && <span className="cv-depmap-rel-chip__rel">{edge.label}</span>}
                        <ArrowRight size={11} />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Downstream Dependencies (Imports) */}
              <div className="cv-depmap-inspector__section">
                <h4 className="cv-depmap-inspector__section-title">
                  <span className="cv-depmap-section-dot cv-depmap-section-dot--outgoing" />
                  Imports / Depends On ({connectedLists.outgoing.length})
                </h4>
                {connectedLists.outgoing.length === 0 ? (
                  <p className="cv-depmap-empty-hint">None (Leaf module or standalone helper)</p>
                ) : (
                  <div className="cv-depmap-pill-list">
                    {connectedLists.outgoing.map((edge) => (
                      <button
                        key={`outgoing-${edge.target}`}
                        type="button"
                        className="cv-depmap-rel-chip cv-depmap-rel-chip--outgoing"
                        onClick={() => handleSelectAndFocusNode(edge.target)}
                        title={`Select & focus ${edge.target}`}
                      >
                        <span className="cv-depmap-rel-chip__name">{edge.target}</span>
                        {edge.label && <span className="cv-depmap-rel-chip__rel">{edge.label}</span>}
                        <ArrowRight size={11} />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Architectural Insight / Purpose */}
              <div className="cv-depmap-inspector__section cv-depmap-inspector__box">
                <div className="cv-depmap-inspector__box-head">
                  <Compass size={14} className="cv-depmap-compass-icon" />
                  <span>Architectural Purpose</span>
                </div>
                <p className="cv-depmap-inspector__box-text">
                  {selectedNode.purpose ||
                    (selectedNode.type === 'entrypoint' &&
                      'Primary application bootstrap orchestrating routing cascades, context providers, and global layout boundaries.') ||
                    (selectedNode.type === 'page' &&
                      'Routed view encapsulating page-level telemetry widgets, data fetch triggers, and interactive tables.') ||
                    (selectedNode.type === 'component' &&
                      'Reusable atomic UI presentation module rendered within view parents with parameterized props.') ||
                    (selectedNode.type === 'hook' &&
                      'Encapsulated reactive state hook managing asynchronous lifecycles, authentication credentials, and session caches.') ||
                    (selectedNode.type === 'api' &&
                      'Low-level networking utility providing normalized HTTP requests, header injection, and network error classification.') ||
                    (selectedNode.type === 'util' &&
                      'Specialized algorithm and transformation helper maintaining pure deterministic computations.') ||
                    'Core codebase module participating in system architecture and execution flow.'}
                </p>
              </div>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
