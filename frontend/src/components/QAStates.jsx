import { Sparkles } from 'lucide-react';
import ErrorState from './ErrorState';
import './QAStates.css';

/** Shown after a question is sent, until the first words of the answer arrive. */
export function TypingIndicator() {
  return (
    <div className="cv-qa-msg cv-qa-msg--assistant">
      <div className="cv-qa-msg__avatar">
        <Sparkles size={15} aria-hidden="true" />
      </div>
      <div className="cv-qa-msg__content">
        <div className="cv-qa-msg__bubble cv-qa-msg__bubble--typing">
          <span className="cv-qa-typing-dots" aria-hidden="true">
            <span className="cv-qa-typing-dot" />
            <span className="cv-qa-typing-dot" />
            <span className="cv-qa-typing-dot" />
          </span>
          <span className="cv-qa-typing-label">Searching the codebase…</span>
        </div>
      </div>
    </div>
  );
}

/** Small label under an answer that is still being written. */
export function StreamingLabel() {
  return <span className="cv-qa-streaming">Generating answer…</span>;
}

/** Failure inside an assistant bubble: plain words plus one clear next step. */
export function AnswerError({ kind, message, onRetry, onUseSearch }) {
  if (kind === 'llm-unconfigured') {
    return (
      <ErrorState
        compact
        title="AI answers are not set up"
        message="The backend has no LLM key (LLM_API_KEY in backend/.env), so it cannot write answers. Code Search still works without it."
        actionLabel="Switch to Code Search"
        onAction={onUseSearch}
      />
    );
  }
  return (
    <ErrorState
      compact
      title="Couldn't get an answer"
      message={message}
      actionLabel="Try again"
      onAction={onRetry}
    />
  );
}

/** Invisible status line for screen readers: announces start, finish and failure, not every word. */
export function QAAnnouncer({ text }) {
  return (
    <div className="cv-sr-only" role="status" aria-live="polite">
      {text}
    </div>
  );
}
