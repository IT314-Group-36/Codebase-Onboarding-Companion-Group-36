import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Send,
  Sparkles,
  ArrowLeft,
  GitBranch,
  FolderTree,
  FileCode,
  ExternalLink,
  Trash2,
  CheckCircle2,
  Search,
} from 'lucide-react';
import { askCodebaseQuestionStream, searchCode, getRepositoryById } from '../services/api';
import LoadingState from '../components/LoadingState';
import Button from '../components/Button';
import ImpactReport, { ImpactAnswerExtras } from '../components/ImpactReport';
import './QAPage.css';

const INITIAL_MESSAGES = [
  {
    id: 'msg-init',
    sender: 'assistant',
    text: "Hello! I am your Codebase Companion. I've indexed this repository's syntax tree and module dependency graph. Ask me anything about how the architecture is structured, where specific lifecycles are handled, or where to start onboarding.",
    citations: [],
    referencedFiles: [],
    timestamp: 'Just now',
  },
];

const SUGGESTED_QUESTIONS = [
  'Explain the overall project architecture',
  'Where are the main application entry points?',
  'What are the core modules and their responsibilities?',
  'How do modules communicate with each other?',
  'What would break if I change the authentication logic?',
  'Which files are affected if I modify the main entry point?',
];

/**
 * Page: Dedicated AI Codebase Q&A & Semantic Search Interface
 * Full-page intelligent codebase assistant connected to backend /ask and /search endpoints.
 */
export default function QAPage() {
  const { repoId } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [repo, setRepo] = useState(null);
  const [inputQuery, setInputQuery] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [messages, setMessages] = useState(INITIAL_MESSAGES);
  const [mode, setMode] = useState('ask'); // 'ask' | 'search'
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);

  const messagesEndRef = useRef(null);
  const messageSeqRef = useRef(1);

  useEffect(() => {
    let isMounted = true;
    async function loadRepo() {
      setLoading(true);
      try {
        const res = await getRepositoryById(repoId);
        if (isMounted && res.success) {
          setRepo(res.repository);
        }
      } catch (err) {
        console.error('Failed to load repo for QA:', err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadRepo();
    return () => {
      isMounted = false;
    };
  }, [repoId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isAsking]);

  const handleSend = useCallback(
    // hints: { symbol | file, label } when the user picked one of the candidates offered for an ambiguous question
    async (queryText, hints = null) => {
      const q = (queryText || inputQuery).trim();
      if (!q || isAsking) return;

      if (mode === 'search') {
        setSearching(true);
        try {
          const res = await searchCode(repoId, q, 8);
          setSearchResults(res.hits || []);
        } catch {
          setSearchResults([]);
        } finally {
          setSearching(false);
        }
        return;
      }

      messageSeqRef.current += 1;
      const currentSeq = messageSeqRef.current;
      const assistantId = `ai-${currentSeq}`;

      const userMsg = {
        id: `usr-${currentSeq}`,
        sender: 'user',
        text: hints?.label ? `Use ${hints.label}` : q,
        timestamp: 'Just now',
      };

      setMessages((prev) => [...prev, userMsg]);
      setMessages((prev) => [...prev, {
        id: assistantId, sender: 'assistant', text: '', citations: [], referencedFiles: [], timestamp: 'Just now',
      }]);
      setInputQuery('');
      setIsAsking(true);

      try {
        const history = messages.filter((m) => m.sender === 'user' || m.sender === 'assistant')
          .filter((m) => m.text).map((m) => ({ role: m.sender, content: m.text }));
        await askCodebaseQuestionStream(repoId, q, hints || {}, history, (event) => {
          if (event.type === 'token') {
            setMessages((prev) => prev.map((m) => m.id === assistantId ? { ...m, text: m.text + event.text } : m));
          } else if (event.type === 'sources') {
            setMessages((prev) => prev.map((m) => m.id === assistantId ? {
              ...m, citations: event.citations || [], referencedFiles: (event.citations || []).map((c) => c.path),
            } : m));
          } else if (event.type === 'result') {
            const res = event.payload || {};
            setMessages((prev) => prev.map((m) => m.id === assistantId ? {
              ...m, text: res.answer || '', citations: res.citations || [], intent: res.intent,
              impact: res.impact ? {
                target: res.impact.target, targetInfo: res.impact.target_info || {}, depth: res.impact.depth,
                totals: res.impact.totals || {}, affectedSymbols: res.impact.affected_symbols || [],
                affectedFiles: res.impact.affected_files || [], affectedTests: res.impact.affected_tests || [],
                dependencies: res.impact.dependencies || {}, summary: res.impact.summary || '',
              } : null,
              candidates: res.needs_clarification ? res.candidates : [], warnings: res.warnings || [],
              caveat: res.caveat || '', question: q,
            } : m));
          }
        });
      } catch (err) {
        const isLlmUnconfigured = err.message && err.message.includes('LLM is not configured');
        const errorText = isLlmUnconfigured
            ? 'The backend LLM is not configured (LLM_API_KEY is not set in backend/.env). You can switch to the "Code Search" tab above to perform hybrid vector and keyword search over all indexed chunks without an LLM!'
            : `Failed to query codebase assistant: ${err.message}`;
        setMessages((prev) => prev.map((m) => m.id === assistantId ? { ...m, text: errorText, isError: true } : m));
      } finally {
        setIsAsking(false);
      }
    },
    [inputQuery, isAsking, repoId, mode, messages]
  );

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClearChat = () => {
    setMessages([
      {
        id: 'msg-init-reset',
        sender: 'assistant',
        text: 'Conversation history cleared. How else can I assist your codebase exploration?',
        citations: [],
        referencedFiles: [],
        timestamp: 'Just now',
      },
    ]);
  };

  if (loading) {
    return <LoadingState message="Connecting to codebase intelligence assistant..." fullPage />;
  }

  const effectiveRepo = repo || {
    id: repoId,
    name: 'repository',
    owner: 'GitHub',
    branch: 'main',
  };

  return (
    <div className="cv-qa-page">
      {/* Top Header */}
      <header className="cv-qa-header">
        <div className="cv-qa-header__left">
          <button
            type="button"
            className="cv-qa-back-btn"
            onClick={() => navigate(`/repository/${repoId}`)}
            title="Back to Repository Overview"
          >
            <ArrowLeft size={16} />
          </button>
          <div>
            <div className="cv-qa-title-row">
              <span className="cv-qa-owner">{effectiveRepo.owner} /</span>
              <h1 className="cv-qa-name">{effectiveRepo.name}</h1>
              <span className="cv-qa-branch-chip">
                <GitBranch size={12} /> {effectiveRepo.branch}
              </span>
            </div>
            <p className="cv-qa-subtitle">Codebase Intelligence, Grounded Q&amp;A &amp; Hybrid Search</p>
          </div>
        </div>

        <div className="cv-qa-header__actions">
          {/* Mode Switch: AI Q&A vs Hybrid Search */}
          <div
            style={{
              display: 'inline-flex',
              background: 'rgba(255,255,255,0.04)',
              padding: '2px',
              borderRadius: 'var(--cv-radius-md)',
              border: '1px solid rgba(255,255,255,0.08)',
              marginRight: '0.5rem',
            }}
          >
            <button
              type="button"
              style={{
                padding: '6px 12px',
                fontSize: '0.8125rem',
                border: 'none',
                borderRadius: 'var(--cv-radius-sm)',
                background: mode === 'ask' ? 'var(--cv-primary)' : 'transparent',
                color: mode === 'ask' ? '#fff' : 'var(--cv-text-secondary)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
              onClick={() => setMode('ask')}
            >
              <Sparkles size={13} />
              <span>AI Q&amp;A</span>
            </button>
            <button
              type="button"
              style={{
                padding: '6px 12px',
                fontSize: '0.8125rem',
                border: 'none',
                borderRadius: 'var(--cv-radius-sm)',
                background: mode === 'search' ? 'var(--cv-primary)' : 'transparent',
                color: mode === 'search' ? '#fff' : 'var(--cv-text-secondary)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
              onClick={() => setMode('search')}
            >
              <Search size={13} />
              <span>Code Search</span>
            </button>
          </div>

          <Button
            variant="secondary"
            size="sm"
            icon={<Trash2 size={14} />}
            onClick={handleClearChat}
          >
            Clear
          </Button>

          <Button
            variant="primary"
            size="sm"
            icon={<FolderTree size={14} />}
            onClick={() => navigate(`/explorer/${repoId}`)}
          >
            Code Explorer
          </Button>
        </div>
      </header>

      {/* Main Container */}
      <div className="cv-qa-body">
        {mode === 'search' ? (
          /* CODE SEARCH VIEW */
          <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              <input
                type="text"
                className="cv-qa-input-field"
                placeholder="Search across all indexed code chunks (e.g. 'authentication', 'database', 'handler')..."
                value={inputQuery}
                onChange={(e) => setInputQuery(e.target.value)}
                onKeyDown={handleKeyDown}
              />
              <Button
                variant="primary"
                size="md"
                icon={<Search size={15} />}
                onClick={() => handleSend()}
                loading={searching}
                disabled={!inputQuery.trim() || searching}
              >
                Search
              </Button>
            </div>

            <div style={{ marginTop: '0.5rem' }}>
              <span style={{ fontSize: '0.8125rem', color: 'var(--cv-text-muted)' }}>
                Hybrid Reciprocal Rank Fusion Search (pgvector cosine + full-text TSVector). No LLM key required.
              </span>
            </div>

            {searchResults.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
                {searchResults.map((hit, idx) => (
                  <div
                    key={idx}
                    style={{
                      background: 'rgba(255, 255, 255, 0.03)',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      borderRadius: 'var(--cv-radius-md)',
                      padding: '1rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <button
                        type="button"
                        style={{
                          background: 'none',
                          border: 'none',
                          color: 'var(--cv-primary)',
                          fontFamily: 'var(--cv-font-mono)',
                          fontSize: '0.875rem',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                        }}
                        onClick={() => navigate(`/explorer/${repoId}?file=${encodeURIComponent(hit.file_path)}`)}
                      >
                        <FileCode size={14} />
                        <span>{hit.file_path}</span>
                        <span style={{ color: 'var(--cv-text-muted)', fontSize: '0.75rem' }}>
                          lines {hit.start_line}-{hit.end_line}
                        </span>
                      </button>

                      {hit.score && (
                        <span style={{ fontSize: '0.75rem', color: 'var(--cv-text-muted)', fontFamily: 'var(--cv-font-mono)' }}>
                          Score: {hit.score}
                        </span>
                      )}
                    </div>

                    <pre
                      style={{
                        margin: 0,
                        padding: '0.75rem',
                        background: 'rgba(0,0,0,0.4)',
                        borderRadius: 'var(--cv-radius-sm)',
                        fontFamily: 'var(--cv-font-mono)',
                        fontSize: '0.8125rem',
                        color: 'var(--cv-text-secondary)',
                        overflowX: 'auto',
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      <code>{hit.content}</code>
                    </pre>
                  </div>
                ))}
              </div>
            ) : inputQuery && !searching ? (
              <div style={{ padding: '3rem 1rem', textAlign: 'center', color: 'var(--cv-text-muted)' }}>
                No code chunks matched "{inputQuery}".
              </div>
            ) : null}
          </div>
        ) : (
          /* AI Q&A CHAT VIEW */
          <>
            {/* Suggested Prompt Chips */}
            <div className="cv-qa-suggestions">
              <span className="cv-qa-suggestions__title">
                <Sparkles size={13} />
                <span>Suggested Inquiries:</span>
              </span>
              <div className="cv-qa-suggestions__chips">
                {SUGGESTED_QUESTIONS.map((q, i) => (
                  <button
                    key={i}
                    type="button"
                    className="cv-qa-chip"
                    onClick={() => handleSend(q)}
                    disabled={isAsking}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>

            {/* Message Feed */}
            <div className="cv-qa-feed">
              {messages.map((msg) => {
                const isUser = msg.sender === 'user';

                return (
                  <div
                    key={msg.id}
                    className={`cv-qa-msg ${isUser ? 'cv-qa-msg--user' : 'cv-qa-msg--assistant'}`}
                  >
                    <div className="cv-qa-msg__avatar">
                      {isUser ? 'ME' : <Sparkles size={15} />}
                    </div>

                    <div className="cv-qa-msg__content">
                      <div className="cv-qa-msg__bubble" style={msg.isError ? { borderColor: 'rgba(235, 87, 87, 0.4)' } : undefined}>
                        <p className="cv-qa-msg__text" style={msg.impact ? { whiteSpace: 'pre-line' } : undefined}>
                          {/* Without an LLM the answer is the structured summary; the report below lists the same
                              items, so only its headline sentence is shown here. */}
                          {msg.impact && msg.text === msg.impact.summary ? msg.text.split('\n')[0] : msg.text}
                        </p>

                        {/* Impact analysis: affected functions/files/tests with reasons, or "which one do you mean?" */}
                        {msg.impact && (
                          <ImpactReport
                            report={msg.impact}
                            onOpenFile={(path) => path && navigate(`/explorer/${repoId}?file=${encodeURIComponent(path)}`)}
                          />
                        )}
                        {msg.intent === 'impact' && (
                          <ImpactAnswerExtras
                            candidates={msg.candidates}
                            warnings={msg.warnings}
                            caveat={msg.caveat}
                            disabled={isAsking}
                            onPickCandidate={(c) =>
                              handleSend(
                                msg.question,
                                c.uid
                                  ? { symbol: c.uid, label: c.qualname }
                                  : { file: c.path, label: c.path }
                              )
                            }
                          />
                        )}

                        {/* Citations with line numbers if returned */}
                        {msg.citations && msg.citations.length > 0 && (
                          <div style={{ marginTop: '0.75rem', paddingTop: '0.5rem', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--cv-text-muted)', display: 'block', marginBottom: '0.25rem' }}>
                              Validated Citations:
                            </span>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                              {msg.citations.map((c, i) => (
                                <button
                                  key={i}
                                  type="button"
                                  className="cv-qa-file-chip"
                                  onClick={() =>
                                    navigate(`/explorer/${repoId}?file=${encodeURIComponent(c.path)}&line=${c.start_line}&end=${c.end_line}`)
                                  }
                                  title={`Inspect ${c.path} lines ${c.start_line}-${c.end_line}`}
                                >
                                  <FileCode size={12} />
                                  <code>{c.path}:{c.start_line}-{c.end_line}</code>
                                  <ExternalLink size={10} />
                                </button>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Referenced Files Chips */}
                        {!msg.citations?.length && msg.referencedFiles && msg.referencedFiles.length > 0 && (
                          <div className="cv-qa-msg__files">
                            <span className="cv-qa-msg__files-label">Referenced Files:</span>
                            <div className="cv-qa-msg__files-list">
                              {msg.referencedFiles.map((file) => (
                                <button
                                  key={file}
                                  type="button"
                                  className="cv-qa-file-chip"
                                  onClick={() =>
                                    navigate(`/explorer/${repoId}?file=${encodeURIComponent(file)}`)
                                  }
                                  title={`Deep-link to ${file} in Code Explorer`}
                                >
                                  <FileCode size={12} />
                                  <code>{file}</code>
                                  <ExternalLink size={10} />
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="cv-qa-msg__meta">
                        <span className="cv-qa-msg__time">{msg.timestamp}</span>
                        {!isUser && !msg.isError && msg.citations && msg.citations.length > 0 && (
                          <span className="cv-qa-msg__conf">
                            <CheckCircle2 size={11} style={{ color: 'var(--cv-success)' }} />
                            <span>{msg.citations.length} Grounded Citations</span>
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}

              {/* Typing Indicator */}
              {isAsking && (
                <div className="cv-qa-msg cv-qa-msg--assistant">
                  <div className="cv-qa-msg__avatar">
                    <Sparkles size={15} />
                  </div>
                  <div className="cv-qa-msg__content">
                    <div className="cv-qa-msg__bubble cv-qa-msg__bubble--typing">
                      <span className="cv-qa-typing-dot" />
                      <span className="cv-qa-typing-dot" />
                      <span className="cv-qa-typing-dot" />
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input Bar */}
            <div className="cv-qa-input-strip">
              <form
                className="cv-qa-input-box"
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSend();
                }}
              >
                <input
                  type="text"
                  className="cv-qa-input-field"
                  placeholder="Ask about architecture, functions, hooks, state flow..."
                  value={inputQuery}
                  onChange={(e) => setInputQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={isAsking}
                />
                <Button
                  type="submit"
                  variant="primary"
                  size="md"
                  icon={<Send size={15} />}
                  disabled={!inputQuery.trim() || isAsking}
                >
                  Ask
                </Button>
              </form>
              <div className="cv-qa-input-footer">
                <span>
                  All responses grounded in pgvector code chunks. Citations validated against indexed files.
                </span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
