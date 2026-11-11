import { useState } from 'react';
import { Sparkles, Send, X, FileText, CheckCircle2 } from 'lucide-react';
import Button from './Button';
import ImpactReport, { ImpactAnswerExtras } from './ImpactReport';
import { useNavigate } from 'react-router-dom';
import { askCodebaseQuestion } from '../services/api';
import './AskQuestionsModal.css';

/**
 * Ask Questions Modal — Codebase AI Companion interactive query interface.
 */
export default function AskQuestionsModal({ open, onClose, repo }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversation, setConversation] = useState([
    {
      sender: 'assistant',
      text: `Hello! I am your Codeverse Assistant for ${repo?.fullName || 'this repository'}. Ask me anything about file architecture, authentication flow, or where to begin onboarding!`,
    },
  ]);

  if (!open) return null;

  // hints: { symbol | file, label } when the user picked a candidate for an ambiguous impact question
  const ask = async (question, hints = null) => {
    if (!question || loading) return;
    setConversation((prev) => [...prev, { sender: 'user', text: hints?.label ? `Use ${hints.label}` : question }]);
    setLoading(true);

    try {
      const res = await askCodebaseQuestion(repo?.id, question, hints || {});
      if (res.success) {
        setConversation((prev) => [
          ...prev,
          {
            sender: 'assistant',
            text: res.answer,
            referencedFiles: res.referencedFiles,
            citations: res.citations,
            intent: res.intent,
            impact: res.impact,
            candidates: res.needsClarification ? res.candidates : [],
            warnings: res.warnings,
            caveat: res.intent === 'impact' ? res.caveat : '',
            question,
          },
        ]);
      }
    } catch (err) {
      setConversation((prev) => [
        ...prev,
        {
          sender: 'assistant',
          text: err.message || 'Error communicating with the backend Q&A service. If LLM_API_KEY is not configured in backend/.env, the LLM endpoint is unavailable.',
          isError: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleAsk = (e) => {
    e?.preventDefault();
    const userText = query.trim();
    if (!userText || loading) return;
    setQuery('');
    ask(userText);
  };

  const openFile = (path) => {
    if (!path || !repo?.id) return;
    onClose?.();
    navigate(`/explorer/${repo.id}?file=${encodeURIComponent(path)}`);
  };

  const samplePrompts = [
    'Explain the high-level architecture of this codebase',
    'Where is the main entry point where execution starts?',
    'What are the core modules and their responsibilities?',
    'What would break if I change the authentication logic?',
  ];

  return (
    <div className="cv-ask-overlay" onClick={onClose} role="presentation">
      <div
        className="cv-ask-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ask-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="cv-ask-modal__header">
          <div className="cv-ask-modal__title-box">
            <div className="cv-ask-modal__spark" aria-hidden="true">
              <Sparkles size={18} />
            </div>
            <div>
              <h3 id="ask-modal-title" className="cv-ask-modal__title">Ask CODEVERSE</h3>
              <p className="cv-ask-modal__sub">FastAPI Codebase Assistant · Verified Citations</p>
            </div>
          </div>
          <button
            type="button"
            className="cv-ask-modal__close"
            onClick={onClose}
            aria-label="Close dialog"
          >
            <X size={18} />
          </button>
        </div>

        <div className="cv-ask-modal__body">
          <div className="cv-ask-messages">
            {conversation.map((msg, idx) => (
              <div
                key={idx}
                className={`cv-ask-msg cv-ask-msg--${msg.sender}`}
              >
                <div className="cv-ask-msg__bubble" style={msg.isError ? { borderColor: 'rgba(235, 87, 87, 0.4)' } : undefined}>
                  <p style={msg.impact ? { whiteSpace: 'pre-line' } : undefined}>
                    {msg.impact && msg.text === msg.impact.summary ? msg.text.split('\n')[0] : msg.text}
                  </p>
                  {msg.impact && <ImpactReport report={msg.impact} onOpenFile={openFile} />}
                  {msg.intent === 'impact' && (
                    <ImpactAnswerExtras
                      candidates={msg.candidates}
                      warnings={msg.warnings}
                      caveat={msg.caveat}
                      disabled={loading}
                      onPickCandidate={(c) =>
                        ask(msg.question, c.uid ? { symbol: c.uid, label: c.qualname } : { file: c.path, label: c.path })
                      }
                    />
                  )}
                  {msg.referencedFiles && msg.referencedFiles.length > 0 && (
                    <div className="cv-ask-msg__refs">
                      <span className="cv-ask-msg__refs-title">
                        <CheckCircle2 size={11} style={{ color: 'var(--cv-success)', marginRight: '4px' }} />
                        Citations ({msg.referencedFiles.length}):
                      </span>
                      {msg.referencedFiles.map((file) => (
                        <span key={file} className="cv-ask-msg__file">
                          <FileText size={12} />
                          <code>{file}</code>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="cv-ask-msg cv-ask-msg--assistant">
                <div className="cv-ask-msg__bubble cv-ask-msg__loading">
                  <span className="cv-btn__spinner" />
                  <span>Retrieving code chunks &amp; querying LLM...</span>
                </div>
              </div>
            )}
          </div>

          <div className="cv-ask-prompts">
            <span className="cv-ask-prompts__label">Suggested queries:</span>
            <div className="cv-ask-prompts__list">
              {samplePrompts.map((p) => (
                <button
                  key={p}
                  type="button"
                  className="cv-ask-prompt-chip"
                  onClick={() => setQuery(p)}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </div>

        <form onSubmit={handleAsk} className="cv-ask-modal__footer">
          <input
            type="text"
            className="cv-ask-input"
            placeholder="Ask about project architecture, entrypoints, or functions..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={loading}
          />
          <Button
            type="submit"
            variant="primary"
            icon={<Send size={16} />}
            disabled={!query.trim() || loading}
            loading={loading}
          >
            Ask
          </Button>
        </form>
      </div>
    </div>
  );
}
