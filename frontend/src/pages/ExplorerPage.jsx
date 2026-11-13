import { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  ArrowLeft,
  Info,
  Copy,
  Check,
  FileCode,
  FileJson,
  FileText,
  Braces,
  Share2,
  ShieldAlert,
  Zap,
  Palette,
} from 'lucide-react';
import SearchInput from '../components/SearchInput';
import Button from '../components/Button';
import LoadingState from '../components/LoadingState';
import ExplanationCard from '../components/ExplanationCard';
import ImpactReport from '../components/ImpactReport';
import {
  getRepositoryById,
  getFileTree,
  getFileDetails,
  getFileContent,
  getImpactAnalysis,
} from '../services/api';
import { showToast } from '../utils/toast';
import './ExplorerPage.css';

const CODE_TOKEN_PATTERN = /(\/\/.*|#.*|\/\*.*?\*\/|"[^"]*"|'[^']*'|`[^`]*`|<\/?[A-Za-z][\w.-]*|\b\d+(?:\.\d+)?\b|\b(?:const|let|var|function|return|if|else|for|while|class|extends|new|this|import|from|export|default|async|await|try|catch|throw|def|lambda|pass|yield|with|as|in|is|not|and|or|None|True|False|null|undefined|interface|type|enum|implements|public|private|static|void|int|string|boolean)\b|[A-Za-z_$][\w$]*)/g;

function highlightLine(line) {
  const parts = [];
  let cursor = 0;
  let previousWord = '';
  for (const match of line.matchAll(CODE_TOKEN_PATTERN)) {
    const token = match[0];
    const index = match.index;
    if (index > cursor) parts.push(line.slice(cursor, index));
    let kind = '';
    if (/^(\/\/|#|\/\*)/.test(token)) kind = 'comment';
    else if (/^("|'|`)/.test(token)) kind = 'string';
    else if (/^<\/?[A-Za-z]/.test(token)) kind = 'tag';
    else if (/^\d/.test(token)) kind = 'number';
    else if (/^(const|let|var|function|return|if|else|for|while|class|extends|new|this|import|from|export|default|async|await|try|catch|throw|def|lambda|pass|yield|with|as|in|is|not|and|or|None|True|False|null|undefined|interface|type|enum|implements|public|private|static|void|int|string|boolean)$/.test(token)) kind = 'keyword';
    else if (/^[A-Za-z_$][\w$]*$/.test(token) && ['class', 'interface', 'type', 'enum'].includes(previousWord)) kind = 'class';
    else if (/^[A-Za-z_$][\w$]*$/.test(token) && /\($/.test(line.slice(index + token.length).match(/^\s*\(/)?.[0] || '')) kind = 'function';
    if (kind) parts.push(<span key={index} className={`cv-token cv-token--${kind}`}>{token}</span>);
    else parts.push(token);
    if (/^[A-Za-z_$][\w$]*$/.test(token)) previousWord = token;
    else if (!/^\s*$/.test(token)) previousWord = '';
    cursor = index + token.length;
  }
  if (cursor < line.length) parts.push(line.slice(cursor));
  return parts;
}

/**
 * Page 5: Codebase Structure Explorer
 * Professional IDE-style layout with tree browser, source editor viewport,
 * and secondary architectural insights inspector connected to real backend AST.
 */
export default function ExplorerPage() {
  const { repoId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const targetLine = Number(searchParams.get('line')) || null;
  const targetEndLine = Number(searchParams.get('end')) || targetLine;

  const [loading, setLoading] = useState(true);
  const [repo, setRepo] = useState(null);
  const [tree, setTree] = useState([]);
  const [selectedFileId, setSelectedFileId] = useState('');
  const [expandedFolders, setExpandedFolders] = useState(new Set());
  const [treeSearch, setTreeSearch] = useState('');
  const [detailsPanelOpen, setDetailsPanelOpen] = useState(true);
  const [mobileTreeOpen, setMobileTreeOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [editorTheme, setEditorTheme] = useState(() => localStorage.getItem('codeverse_editor_theme') || 'dark-plus');

  const [currentFileContent, setCurrentFileContent] = useState('');
  const [fileContentLoading, setFileContentLoading] = useState(false);
  const [fileContentError, setFileContentError] = useState('');
  const [currentFileDetails, setCurrentFileDetails] = useState(null);
  const [impactData, setImpactData] = useState(null);
  const [analyzingImpact, setAnalyzingImpact] = useState(false);
  // Function picked for a plain-English explanation. Tied to the file it was picked in, so it resets on file change.
  const [explainPick, setExplainPick] = useState(null); // { file, uid }

  useEffect(() => {
    localStorage.setItem('codeverse_editor_theme', editorTheme);
  }, [editorTheme]);

  // 1. Initial Load: Repository specifications & File tree
  useEffect(() => {
    let isMounted = true;
    async function loadExplorerData() {
      setLoading(true);
      try {
        const [repoRes, treeRes] = await Promise.all([
          getRepositoryById(repoId),
          getFileTree(repoId),
        ]);

        if (!isMounted) return;

        if (repoRes.success) {
          setRepo(repoRes.repository);
        }

        if (treeRes.success && treeRes.tree) {
          setTree(treeRes.tree);

          // Auto-expand top 2 levels of folders
          const initialExpanded = new Set();
          treeRes.tree.forEach((node) => {
            if (node.type === 'folder') {
              initialExpanded.add(node.id);
              (node.children || []).forEach((c) => {
                if (c.type === 'folder') initialExpanded.add(c.id);
              });
            }
          });
          setExpandedFolders(initialExpanded);

          // Select file: from query param, or repo default file, or first file in tree
          const queryFile = searchParams.get('file');
          if (queryFile) {
            setSelectedFileId(queryFile);
          } else if (repoRes.repository?.defaultFile) {
            setSelectedFileId(repoRes.repository.defaultFile);
          } else if (treeRes.files?.[0]?.path) {
            setSelectedFileId(treeRes.files[0].path);
          }
        }
      } catch (err) {
        console.error('Explorer load failed:', err);
        showToast(err.message || 'Failed to load file tree from backend.', 'error');
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    loadExplorerData();
    return () => {
      isMounted = false;
    };
  }, [repoId, searchParams]);

  // 2. Load File Details & Content when selected file changes
  useEffect(() => {
    if (!selectedFileId) return;
    let isMounted = true;

    async function loadFileDetails() {
      setCurrentFileContent('');
      setFileContentError('');
      setFileContentLoading(true);
      try {
        const [detailsResult, contentResult] = await Promise.allSettled([
          getFileDetails(repoId, selectedFileId),
          getFileContent(repoId, selectedFileId),
        ]);

        if (!isMounted) return;
        setImpactData(null);

        if (detailsResult.status === 'fulfilled' && detailsResult.value.success) {
          setCurrentFileDetails(detailsResult.value.details);
        } else if (detailsResult.status === 'rejected') {
          console.warn('Failed to load file details:', detailsResult.reason?.message);
        }

        if (contentResult.status === 'fulfilled' && contentResult.value.success) {
          setCurrentFileContent(contentResult.value.content);
        } else {
          const error = contentResult.status === 'rejected' ? contentResult.reason : null;
          setFileContentError(error?.message || 'The source file could not be retrieved.');
        }
      } catch (err) {
        if (!isMounted) return;
        setFileContentError(err.message || 'Unable to retrieve this source file.');
        console.warn('Failed to load file details:', err.message);
      } finally {
        if (isMounted) setFileContentLoading(false);
      }
    }

    loadFileDetails();

    return () => {
      isMounted = false;
    };
  }, [repoId, selectedFileId]);

  useEffect(() => {
    if (!targetLine) return;
    document.getElementById(`cv-source-line-${targetLine}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [targetLine, targetEndLine, selectedFileId, currentFileContent]);

  const handleRunImpact = useCallback(async () => {
    if (!selectedFileId || analyzingImpact) return;
    setAnalyzingImpact(true);
    try {
      let res;
      try {
        res = await getImpactAnalysis(repoId, { file: selectedFileId, depth: 3, explain: true });
      } catch {
        // No LLM key (503) or the LLM call failed (502): the structured report is still a complete answer
        res = await getImpactAnalysis(repoId, { file: selectedFileId, depth: 3 });
      }
      if (res.success) {
        setImpactData(res);
        showToast(`Impact analysis complete: ${res.affectedFiles?.length || 0} files affected.`, 'info');
      }
    } catch (err) {
      showToast(err.message || 'Impact analysis could not be completed.', 'error');
    } finally {
      setAnalyzingImpact(false);
    }
  }, [repoId, selectedFileId, analyzingImpact]);

  const toggleFolder = (id) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const getFileIcon = (fileName = '') => {
    if (fileName.endsWith('.jsx') || fileName.endsWith('.tsx')) {
      return <FileCode size={14} className="cv-icon--jsx" />;
    }
    if (fileName.endsWith('.js') || fileName.endsWith('.ts')) {
      return <Braces size={14} className="cv-icon--js" />;
    }
    if (fileName.endsWith('.json')) {
      return <FileJson size={14} className="cv-icon--json" />;
    }
    if (fileName.endsWith('.css')) {
      return <FileText size={14} className="cv-icon--css" />;
    }
    if (fileName.endsWith('.md')) {
      return <FileText size={14} className="cv-icon--md" />;
    }
    return <FileText size={14} className="cv-icon--generic" />;
  };

  const visibleNodes = useMemo(() => {
    const flattenTree = (nodes, depth = 0) => {
      const flat = [];
      for (const node of nodes) {
        flat.push({ ...node, depth });
        if (node.type === 'folder' && expandedFolders.has(node.id) && node.children) {
          flat.push(...flattenTree(node.children, depth + 1));
        }
      }
      return flat;
    };

    const flat = flattenTree(tree);
    if (!treeSearch.trim()) return flat;
    const query = treeSearch.toLowerCase();
    return flat.filter((n) => n.name.toLowerCase().includes(query));
  }, [tree, expandedFolders, treeSearch]);

  const handleCopyCode = () => {
    navigator.clipboard?.writeText(currentFileContent);
    setCopied(true);
    showToast('Source copied to clipboard.', 'success', 2000);
    setTimeout(() => setCopied(false), 1800);
  };

  if (loading) {
    return <LoadingState message="Loading Codebase Explorer..." fullPage />;
  }

  const effectiveRepo = repo || {
    id: repoId,
    name: 'repository',
    branch: 'main',
  };

  const codeLines = (currentFileContent || '').split('\n');

  return (
    <div className="cv-explorer">
      {/* Action Header */}
      <div className="cv-explorer-topbar">
        <div className="cv-explorer-topbar__left">
          <Button
            variant="ghost"
            size="sm"
            icon={<ArrowLeft size={14} />}
            onClick={() => navigate(`/repository/${effectiveRepo.id}`)}
          >
            Overview
          </Button>

          <span className="cv-explorer-topbar__sep">/</span>
          <span className="cv-explorer-topbar__reponame">{effectiveRepo.name}</span>

          <span className="cv-explorer-topbar__sep">/</span>
          <code className="cv-explorer-topbar__filepath">{selectedFileId || 'Select a file'}</code>
        </div>

        <div className="cv-explorer-topbar__right">
          <Button
            variant="secondary"
            size="sm"
            icon={<Zap size={13} />}
            onClick={handleRunImpact}
            loading={analyzingImpact}
            disabled={!selectedFileId || analyzingImpact}
            title="Perform reverse dependency blast radius impact analysis"
          >
            Impact Analysis
          </Button>

          <Button
            variant="secondary"
            size="sm"
            className="cv-explorer-mobile-toggle-btn"
            onClick={() => setMobileTreeOpen(!mobileTreeOpen)}
          >
            Files
          </Button>

          <Button
            variant={detailsPanelOpen ? 'primary' : 'secondary'}
            size="sm"
            icon={<Info size={13} />}
            onClick={() => setDetailsPanelOpen(!detailsPanelOpen)}
          >
            {detailsPanelOpen ? 'Hide Details' : 'View Details'}
          </Button>
        </div>
      </div>

      {/* 3-Pane Workspace */}
      <div className="cv-explorer-workspace">
        {/* Pane 1: File Tree (Left) */}
        <aside
          className={`cv-explorer-tree-pane ${mobileTreeOpen ? 'cv-explorer-tree-pane--mobile-open' : ''}`}
          aria-label="Repository File Tree"
        >
          <div className="cv-explorer-tree-head">
            <span className="cv-explorer-tree-title">FILES</span>
            <span className="cv-explorer-branch-tag">{effectiveRepo.branch}</span>
          </div>

          <div className="cv-explorer-tree-search-box">
            <SearchInput
              value={treeSearch}
              onChange={setTreeSearch}
              placeholder="Search files..."
            />
          </div>

          <div className="cv-tree-scroll" role="tree">
            {visibleNodes.length > 0 ? (
              visibleNodes.map((node) => {
                const isFolder = node.type === 'folder';
                const isExpanded = expandedFolders.has(node.id);
                const isSelected = selectedFileId === node.id;

                return (
                  <div
                    key={node.id}
                    className={`cv-tree-node ${isSelected ? 'cv-tree-node--selected' : ''}`}
                    style={{ paddingLeft: `${node.depth * 14 + 10}px` }}
                    role="treeitem"
                    tabIndex={0}
                    aria-expanded={isFolder ? isExpanded : undefined}
                    onClick={() => {
                      if (isFolder) {
                        toggleFolder(node.id);
                      } else {
                        setSelectedFileId(node.id);
                        setMobileTreeOpen(false);
                      }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        if (isFolder) toggleFolder(node.id);
                        else setSelectedFileId(node.id);
                      }
                    }}
                  >
                    <span className="cv-tree-node__toggle-icon" aria-hidden="true">
                      {isFolder ? (
                        isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />
                      ) : null}
                    </span>

                    <span className="cv-tree-node__type-icon" aria-hidden="true">
                      {isFolder ? (
                        isExpanded ? (
                          <FolderOpen size={14} className="cv-icon--folder" />
                        ) : (
                          <Folder size={14} className="cv-icon--folder" />
                        )
                      ) : (
                        getFileIcon(node.name)
                      )}
                    </span>

                    <span className="cv-tree-node__name" title={node.name}>
                      {node.name}
                    </span>

                    {!isFolder && node.size && (
                      <span className="cv-tree-node__size">{node.size}</span>
                    )}
                  </div>
                );
              })
            ) : (
              <p style={{ color: 'var(--cv-text-muted)', padding: '1.5rem', fontSize: '0.8125rem' }}>
                No files found matching filter.
              </p>
            )}
          </div>
        </aside>

        {/* Pane 2: Code Viewer (Center) */}
        <main className="cv-explorer-code-pane" data-editor-theme={editorTheme} aria-label="Source Code Viewer">
          <div className="cv-code-head">
            <div className="cv-code-head__meta">
              {getFileIcon(selectedFileId)}
              <span className="cv-code-head__path">{selectedFileId || 'No file selected'}</span>
              <span className="cv-code-head__lines">{codeLines.length} lines</span>
              <span className="cv-code-spatial-pill">
                <span className="cv-code-spatial-dot" />
                Indexed source
              </span>
              {targetLine && <span className="cv-code-spatial-pill" title="Citation location in the indexed source">
                Citation: lines {targetLine}{targetEndLine && targetEndLine !== targetLine ? `-${targetEndLine}` : ''}
              </span>}
            </div>

            <div className="cv-code-head__actions">
              <label className="cv-editor-theme-control" title="Choose code editor theme">
                <Palette size={14} aria-hidden="true" />
                <select aria-label="Code editor theme" value={editorTheme} onChange={(e) => setEditorTheme(e.target.value)}>
                  <option value="dark-plus">VS Code Dark+</option>
                  <option value="monokai">Monokai</option>
                  <option value="dracula">Dracula</option>
                  <option value="github-light">GitHub Light</option>
                </select>
              </label>
              <button
                type="button"
                className="cv-code-copy-btn"
                onClick={handleCopyCode}
                title="Copy source code"
              >
                {copied ? <Check size={13} /> : <Copy size={13} />}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
          </div>

          <div className="cv-code-viewport">
            <div className="cv-code-line-numbers" aria-hidden="true">
              {codeLines.map((_, i) => (
                <span key={i}>{i + 1}</span>
              ))}
            </div>

            <pre className="cv-code-syntax">
              <code>{codeLines.map((line, index) => {
                const lineNumber = index + 1;
                const isCitationLine = targetLine && lineNumber >= targetLine && lineNumber <= (targetEndLine || targetLine);
                return <span id={`cv-source-line-${lineNumber}`} key={lineNumber}
                  className={isCitationLine ? 'cv-source-line cv-source-line--citation' : 'cv-source-line'}>{highlightLine(line)}{'\n'}</span>;
              })}</code>
              <code>{fileContentLoading ? 'Loading source code…' : fileContentError ? `Unable to load source: ${fileContentError}` : currentFileContent || 'No source content is available for this file.'}</code>
            </pre>
          </div>

          <div className="cv-code-footer-banner">
            <span>
              Source is fetched on demand from the indexed GitHub revision; the backend retains AST excerpts and metadata.
              {fileContentLoading ? 'Retrieving source at indexed commit…' : fileContentError ? 'Source retrieval failed' : 'Source retrieved from the exact indexed GitHub commit'}
            </span>
          </div>
        </main>

        {/* Pane 3: Architectural Details & Module Relationships (Right) */}
        {detailsPanelOpen && (
          <aside className="cv-explorer-details-pane" aria-label="Module Insights">
            <div className="cv-details-head">
              <span className="cv-details-title">MODULE DETAILS</span>
              <span className="cv-details-sub">Architectural Role &amp; Dependencies</span>
            </div>

            {currentFileDetails ? (
              <div className="cv-details-body">
                {/* Sensitive Badge if flagged */}
                {currentFileDetails.sensitive && (
                  <div
                    style={{
                      padding: '0.75rem',
                      background: 'rgba(235, 87, 87, 0.12)',
                      border: '1px solid rgba(235, 87, 87, 0.35)',
                      borderRadius: 'var(--cv-radius-sm)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                    }}
                  >
                    <ShieldAlert size={16} style={{ color: 'var(--cv-error)' }} />
                    <span style={{ fontSize: '0.8125rem', color: 'var(--cv-error)', fontWeight: 600 }}>
                      Sensitive File (Secrets Redacted)
                    </span>
                  </div>
                )}

                {/* Purpose */}
                <div className="cv-detail-card">
                  <h4 className="cv-detail-label">Purpose</h4>
                  <p className="cv-detail-text">{currentFileDetails.purpose}</p>
                </div>

                {/* Plain-English explanation of the file (and of a function picked below) */}
                <ExplanationCard
                  key={`file:${selectedFileId}`}
                  repoId={repoId}
                  kind="file"
                  target={selectedFileId}
                  onOpenFile={(path) => path && setSelectedFileId(path)}
                  onSelectSymbol={(uid) => setExplainPick({ file: selectedFileId, uid })}
                />
                {explainPick && explainPick.file === selectedFileId && (
                  <ExplanationCard
                    key={`symbol:${explainPick.uid}`}
                    repoId={repoId}
                    kind="symbol"
                    target={explainPick.uid}
                    autoLoad
                    onOpenFile={(path) => path && setSelectedFileId(path)}
                  />
                )}

                {/* Status Badges */}
                <div className="cv-detail-card cv-detail-card--row">
                  <div>
                    <h4 className="cv-detail-label">Importance</h4>
                    <span
                      className={`cv-badge cv-badge--${
                        currentFileDetails.importance === 'critical'
                          ? 'error'
                          : currentFileDetails.importance === 'high'
                          ? 'analyzing'
                          : 'analyzed'
                      }`}
                    >
                      {currentFileDetails.importance}
                    </span>
                  </div>
                  <div>
                    <h4 className="cv-detail-label">Complexity</h4>
                    <span
                      className={`cv-badge cv-badge--${
                        currentFileDetails.complexity === 'high' ? 'error' : 'connected'
                      }`}
                    >
                      {currentFileDetails.complexity}
                    </span>
                  </div>
                </div>

                {/* Impact Analysis Results (if triggered) */}
                {impactData && (
                  <div className="cv-detail-card" style={{ border: '1px solid var(--cv-primary)' }}>
                    <h4 className="cv-detail-label" style={{ color: 'var(--cv-primary)' }}>
                      Impact Analysis (Depth {impactData.depth})
                    </h4>
                    <p style={{ fontSize: '0.8125rem', color: 'var(--cv-text-secondary)', marginBottom: '0.5rem', whiteSpace: 'pre-line' }}>
                      {impactData.explanation ||
                        (impactData.report?.summary ? impactData.report.summary.split('\n')[0] : impactData.caveat)}
                    </p>
                    <span style={{ fontSize: '0.75rem', color: 'var(--cv-text-muted)' }}>
                      Affected Files: {impactData.affectedFiles?.length || 0} · Affected Symbols:{' '}
                      {impactData.affectedSymbols?.length || 0}
                    </span>
                    {impactData.report && (
                      <ImpactReport report={impactData.report} onOpenFile={(path) => path && setSelectedFileId(path)} />
                    )}
                  </div>
                )}

                {/* Module Relationships Diagram */}
                <div className="cv-detail-card">
                  <div className="cv-detail-card__header">
                    <h4 className="cv-detail-label">Direct Import Dependencies</h4>
                    <Share2 size={12} className="cv-detail-card__icon" />
                  </div>

                  <div className="cv-rel-flow-graph">
                    {currentFileDetails.dependencies && currentFileDetails.dependencies.length > 0 ? (
                      <div className="cv-rel-fallback">
                        <ul className="cv-rel-fallback-list">
                          {currentFileDetails.dependencies.map((dep) => (
                            <li key={dep}>
                              <span>•</span> <code>{dep}</code>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <span style={{ fontSize: '0.8125rem', color: 'var(--cv-text-muted)' }}>
                        No internal imports detected.
                      </span>
                    )}
                  </div>
                </div>

                {/* Referenced By */}
                <div className="cv-detail-card">
                  <h4 className="cv-detail-label">Used By (Dependents)</h4>
                  <div className="cv-dep-chips">
                    {currentFileDetails.dependents && currentFileDetails.dependents.length > 0 ? (
                      currentFileDetails.dependents.map((dep) => (
                        <span key={dep} className="cv-dep-chip">
                          <code>{dep}</code>
                        </span>
                      ))
                    ) : (
                      <span style={{ fontSize: '0.8125rem', color: 'var(--cv-text-muted)' }}>
                        No incoming imports detected.
                      </span>
                    )}
                  </div>
                </div>

                {/* Exported Signatures & Symbols */}
                <div className="cv-detail-card">
                  <h4 className="cv-detail-label">
                    Detected Symbols ({currentFileDetails.symbols?.length || 0})
                  </h4>
                  <div className="cv-dep-chips">
                    {currentFileDetails.symbols && currentFileDetails.symbols.length > 0 ? (
                      currentFileDetails.symbols.map((sym) => (
                        <button
                          type="button"
                          key={sym.uid || sym.name}
                          className="cv-dep-chip cv-dep-chip--export cv-expl__chip"
                          onClick={() => sym.uid && setExplainPick({ file: selectedFileId, uid: sym.uid })}
                          title={`${sym.kind} at lines ${sym.start_line}-${sym.end_line}: ${sym.signature || sym.name}. Click for a plain-English explanation.`}
                        >
                          <code>{sym.signature || sym.qualname || sym.name}</code>
                        </button>
                      ))
                    ) : (
                      <span style={{ fontSize: '0.8125rem', color: 'var(--cv-text-muted)' }}>
                        No symbols extracted for this file.
                      </span>
                    )}
                  </div>
                </div>

                {/* Suggestions */}
                {currentFileDetails.suggestions && currentFileDetails.suggestions.length > 0 && (
                  <div className="cv-detail-card">
                    <h4 className="cv-detail-label">Onboarding &amp; Refactor Notes</h4>
                    <ul className="cv-tips-list">
                      {currentFileDetails.suggestions.map((s, idx) => (
                        <li key={idx}>{s}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div style={{ padding: '2rem 1rem', textAlign: 'center', color: 'var(--cv-text-muted)' }}>
                Select a file to inspect AST symbols and dependency relations.
              </div>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
