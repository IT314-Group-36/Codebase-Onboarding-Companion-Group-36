import { useState } from 'react';
import { Check, MessageSquareWarning, Lock, Bot } from 'lucide-react';
import Button from './Button';
import Skeleton from './Skeleton';
import './ManagerWidgets.css';

/*
 * Presentational building blocks for the senior / manager views.
 * They take plain data and callbacks, so whoever wires up the backend only passes props.
 * Every widget handles its own loading and empty state.
 */

function Empty({ children }) {
  return <p className="cv-mgr-empty">{children}</p>;
}

function Bar({ percent, label }) {
  const value = Math.max(0, Math.min(100, Math.round(percent || 0)));
  return (
    <div className="cv-mgr-bar" role="progressbar" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <div className="cv-mgr-bar__fill" style={{ width: `${value}%` }} />
    </div>
  );
}

/**
 * Team-wide onboarding progress (numbers are aggregated, never per person).
 * @param {{memberCount:number, onboardedCount:number, averagePercent:number, byCategory?:{name:string, percent:number}[]}} [props.summary]
 */
export function TeamProgressSummary({ loading = false, summary }) {
  return (
    <section className="cv-mgr-card" aria-labelledby="cv-mgr-progress-title">
      <h3 id="cv-mgr-progress-title" className="cv-mgr-card__title">Team onboarding progress</h3>
      {loading ? (
        <Skeleton lines={4} />
      ) : !summary || summary.memberCount === 0 ? (
        <Empty>No one has started onboarding on this repository yet.</Empty>
      ) : (
        <>
          <p className="cv-mgr-big">
            {Math.round(summary.averagePercent)}%
            <span className="cv-mgr-big__sub"> average completion</span>
          </p>
          <Bar percent={summary.averagePercent} label="Average onboarding completion" />
          <p className="cv-mgr-muted">
            {summary.onboardedCount} of {summary.memberCount} people have finished onboarding.
          </p>
          {summary.byCategory?.length > 0 && (
            <ul className="cv-mgr-list">
              {summary.byCategory.map((c) => (
                <li key={c.name} className="cv-mgr-list__row">
                  <span className="cv-mgr-list__name">{c.name}</span>
                  <Bar percent={c.percent} label={`${c.name} completion`} />
                  <span className="cv-mgr-list__num">{Math.round(c.percent)}%</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

/**
 * Tasks where the team gets stuck.
 * @param {{id:string, title:string, stuckCount:number, memberCount:number, avgDays?:number}[]} [props.items]
 */
export function BottleneckList({ loading = false, items }) {
  const sorted = [...(items || [])].sort((a, b) => b.stuckCount / (b.memberCount || 1) - a.stuckCount / (a.memberCount || 1));
  return (
    <section className="cv-mgr-card" aria-labelledby="cv-mgr-bottleneck-title">
      <h3 id="cv-mgr-bottleneck-title" className="cv-mgr-card__title">Where the team gets stuck</h3>
      {loading ? (
        <Skeleton lines={4} />
      ) : sorted.length === 0 ? (
        <Empty>Nothing looks stuck right now.</Empty>
      ) : (
        <ul className="cv-mgr-list">
          {sorted.map((t) => (
            <li key={t.id} className="cv-mgr-list__row cv-mgr-list__row--stack">
              <span className="cv-mgr-list__name">{t.title}</span>
              <Bar percent={(t.stuckCount / (t.memberCount || 1)) * 100} label={`${t.title}: share of people stuck`} />
              <span className="cv-mgr-muted">
                {t.stuckCount} of {t.memberCount} stuck{t.avgDays ? ` · about ${t.avgDays} days` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="cv-mgr-note">Shows where tasks slow down across the team. It says nothing about any one person.</p>
    </section>
  );
}

/**
 * Topics people ask about, without exposing individual questions.
 * Topics asked by fewer than `minGroup` people are not shown.
 * @param {{topic:string, count:number}[]} [props.topics]
 */
export function QuestionTopics({ loading = false, topics, minGroup = 3 }) {
  const visible = (topics || []).filter((t) => t.count >= minGroup);
  return (
    <section className="cv-mgr-card" aria-labelledby="cv-mgr-topics-title">
      <h3 id="cv-mgr-topics-title" className="cv-mgr-card__title">What people ask about</h3>
      {loading ? (
        <Skeleton lines={3} />
      ) : visible.length === 0 ? (
        <Empty>Not enough questions yet to show topics.</Empty>
      ) : (
        <ul className="cv-mgr-chips">
          {visible.map((t) => (
            <li key={t.topic} className="cv-mgr-chip">
              {t.topic} <span className="cv-mgr-chip__count">{t.count}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="cv-mgr-note">
        <Lock size={12} aria-hidden="true" /> Individual questions are private. A topic appears only when at least {minGroup} people asked about it.
      </p>
    </section>
  );
}

const STATUS_LABEL = { pending: 'Waiting for review', approved: 'Approved', changes: 'Changes requested' };

/**
 * One AI-written explanation waiting for a person to approve it.
 * @param {{title:string, kind?:string, text:string, status:'pending'|'approved'|'changes', reviewer?:string, note?:string}} props.explanation
 * @param {() => void} [props.onApprove]
 * @param {(note:string) => void} [props.onRequestChanges]
 */
export function ExplanationReviewCard({ explanation, onApprove, onRequestChanges, busy = false }) {
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState('');
  const { title, kind, text, status, reviewer, note: savedNote } = explanation;

  return (
    <article className="cv-mgr-card">
      <header className="cv-mgr-review__head">
        <h3 className="cv-mgr-card__title">{title}</h3>
        {kind && <span className="cv-mgr-tag">{kind}</span>}
      </header>
      <span className="cv-mgr-ai">
        <Bot size={12} aria-hidden="true" /> AI-written draft. Check it against the code before approving.
      </span>
      <p className="cv-mgr-review__text">{text}</p>

      <p className={`cv-mgr-status cv-mgr-status--${status}`} role="status">
        {status === 'approved' && <Check size={13} aria-hidden="true" />}
        {status === 'changes' && <MessageSquareWarning size={13} aria-hidden="true" />}
        {STATUS_LABEL[status] || status}
        {reviewer && status !== 'pending' ? ` by ${reviewer}` : ''}
      </p>
      {savedNote && status === 'changes' && <p className="cv-mgr-muted">Note: {savedNote}</p>}

      {status === 'pending' && !asking && (
        <div className="cv-mgr-actions">
          <Button variant="primary" size="sm" disabled={busy} onClick={onApprove}>Approve</Button>
          <Button variant="secondary" size="sm" disabled={busy} onClick={() => setAsking(true)}>Request changes</Button>
        </div>
      )}
      {status === 'pending' && asking && (
        <div className="cv-mgr-ask">
          <label htmlFor="cv-mgr-note" className="cv-mgr-muted">What should be fixed?</label>
          <textarea id="cv-mgr-note" className="cv-mgr-textarea" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="cv-mgr-actions">
            <Button variant="primary" size="sm" disabled={busy || !note.trim()} onClick={() => onRequestChanges?.(note.trim())}>Send</Button>
            <Button variant="ghost" size="sm" onClick={() => setAsking(false)}>Cancel</Button>
          </div>
        </div>
      )}
    </article>
  );
}
