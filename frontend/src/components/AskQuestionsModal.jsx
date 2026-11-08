import { useState } from 'react';
import { Sparkles, Send, X, FileText, CheckCircle2 } from 'lucide-react';
import Button from './Button';
import { askCodebaseQuestion } from '../services/api';
import './AskQuestionsModal.css';

/**
 * Ask Questions Modal — Codebase AI Companion interactive query interface.
 */
export default function AskQuestionsModal({ open, onClose, repo }) {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversation, setConversation] = useState([
    {
      sender: 'assistant',
      text: `Hello! I am your Codeverse Assistant for ${repo?.fullName || 'this repository'}. Ask me anything about file architecture, authentication flow, or where to begin onboarding!`,
    },
  ]);

  if (!open) return null;

  const handleAsk = async (e) => {
    e?.preventDefault();
    if (!query.trim() || loading) return;

    const userText = query.trim();
    setQuery('');
    setConversation((prev) => [...prev, { sender: 'user', text: userText }]);
    setLoading(true);

    try {
      const res = await askCodebaseQuestion(repo?.id, userText);
      if (res.success) {
        setConversation((prev) => [
          ...prev,
          {
            sender: 'assistant',
            text: res.answer,
            referencedFiles: res.referencedFiles,
            citations: res.citations,
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

  const samplePrompts = [
    'Explain the high-level architecture of this codebase',
    'Where is the main entry point where execution starts?',
    'What are the core modules and their responsibilities?',
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
                  <p>{msg.text}</p>
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
