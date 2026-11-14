import { useState } from 'react';
import { AlertTriangle, FileCode, FlaskConical, ArrowRight, ChevronDown, ChevronRight, Box } from 'lucide-react';
import StaticAnalysisBadge from './StaticAnalysisBadge';
import './ImpactReport.css';

const LIST_LIMIT = 8;

function pluralize(n, word) {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

function strip(text) {
  return String(text || '').replace(/`/g, '');
}

function SymbolRow({ s, onOpenFile }) {
  return (
    <li className="cv-impact__row">
      <button
        type="button"
        className="cv-impact__file-link"
        onClick={() => onOpenFile?.(s.path)}
        title={`Open ${s.path}`}
      >
        <code>{s.qualname}</code>
        <span className="cv-impact__loc">
          {s.path}:{s.start_line}
        </span>
      </button>
      <span className="cv-impact__reason">{strip(s.reason)}</span>
      {s.chain?.length > 2 && (
        <span className="cv-impact__chain" title="How the change reaches this function">
          {s.chain.map((c, i) => (
            <span key={`${c}-${i}`} className="cv-impact__chain-step">
              {i > 0 && <ArrowRight size={10} aria-hidden="true" />}
              <code>{c}</code>
            </span>
          ))}
        </span>
      )}
    </li>
  );
}

function Group({ title, count, children, defaultOpen = true, tone }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`cv-impact__group ${tone ? `cv-impact__group--${tone}` : ''}`}>
      <button type="button" className="cv-impact__group-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {open ? <ChevronDown size={13} aria-hidden="true" /> : <ChevronRight size={13} aria-hidden="true" />}
        <span>{title}</span>
        <span className="cv-impact__count">{count}</span>
      </button>
      {open && children}
    </div>
  );
}

function ShowMoreList({ items, render }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, LIST_LIMIT);
  return (
    <>
      <ul className="cv-impact__list">{shown.map(render)}</ul>
      {items.length > LIST_LIMIT && (
        <button type="button" className="cv-impact__more" onClick={() => setAll((v) => !v)}>
          {all ? 'Show fewer' : `Show ${items.length - LIST_LIMIT} more`}
        </button>
      )}
    </>
  );
}

/**
 * Structured "what would break?" report: affected functions (with the call chain and a reason), affected files,
 * tests that reach the target, and what the target itself depends on.
 *
 * @param {object} report   adapted impact report (see adaptImpactReport in services/api.js)
 * @param {(path: string) => void} [onOpenFile]
 */
export default function ImpactReport({ report, onOpenFile }) {
  if (!report) return null;
  const info = report.targetInfo || {};
  const symbols = report.affectedSymbols || [];
  const direct = symbols.filter((s) => s.distance === 1 && !s.is_test);
  const indirect = symbols.filter((s) => s.distance > 1 && !s.is_test);
  const testSymbols = symbols.filter((s) => s.is_test).length;
  const symbolFiles = new Set(symbols.map((s) => s.path));
  const otherFiles = (report.affectedFiles || []).filter((f) => !symbolFiles.has(f.path) && !f.is_test);
  const tests = report.affectedTests || [];
  const deps = report.dependencies || { calls: [], imports: [] };
  const targetLabel = info.kind === 'symbol' ? info.qualname : info.path;
  const nothing = symbols.length === 0 && (report.affectedFiles || []).length === 0;

  return (
    <div className="cv-impact" aria-label={`Impact of changing ${targetLabel}`}>
      <div className="cv-impact__head">
        <Box size={13} aria-hidden="true" />
        <span className="cv-impact__target">
          <code>{targetLabel}</code>
        </span>
        <span className="cv-impact__stats">
          {pluralize(report.totals.symbols, 'function')} · {pluralize(report.totals.files, 'file')} ·{' '}
          {pluralize(report.totals.tests, 'test file')} · depth {report.depth}
        </span>
      </div>

      <StaticAnalysisBadge kind="impact" />

      {nothing && <p className="cv-impact__empty">Nothing else in this repository depends on it, as far as the analysis can tell.</p>}

      {direct.length > 0 && (
        <Group title="Directly affected" count={direct.length} tone="direct">
          <ShowMoreList items={direct} render={(s) => <SymbolRow key={s.uid} s={s} onOpenFile={onOpenFile} />} />
        </Group>
      )}

      {indirect.length > 0 && (
        <Group title="Indirectly affected" count={indirect.length} defaultOpen={direct.length === 0} tone="indirect">
          <ShowMoreList items={indirect} render={(s) => <SymbolRow key={s.uid} s={s} onOpenFile={onOpenFile} />} />
        </Group>
      )}

      {testSymbols > 0 && (
        <p className="cv-impact__note">
          Plus {pluralize(testSymbols, 'test function')} (counted, not listed).
        </p>
      )}

      {otherFiles.length > 0 && (
        <Group title="Other files that import it" count={otherFiles.length}>
          <ShowMoreList
            items={otherFiles}
            render={(f) => (
              <li key={f.path} className="cv-impact__row">
                <button type="button" className="cv-impact__file-link" onClick={() => onOpenFile?.(f.path)}>
                  <FileCode size={12} aria-hidden="true" />
                  <code>{f.path}</code>
                </button>
                <span className="cv-impact__reason">{strip(f.reason)}</span>
              </li>
            )}
          />
        </Group>
      )}

      <Group title="Tests that reach it" count={tests.length} defaultOpen={tests.length > 0}>
        {tests.length > 0 ? (
          <ShowMoreList
            items={tests}
            render={(t) => (
              <li key={t.path} className="cv-impact__row">
                <button type="button" className="cv-impact__file-link" onClick={() => onOpenFile?.(t.path)}>
                  <FlaskConical size={12} aria-hidden="true" />
                  <code>{t.path}</code>
                </button>
              </li>
            )}
          />
        ) : (
          <p className="cv-impact__warn">
            <AlertTriangle size={12} aria-hidden="true" /> No test file reaches it, so check or add tests by hand.
          </p>
        )}
      </Group>

      {(deps.calls.length > 0 || deps.imports.length > 0) && (
        <Group title="What it depends on" count={deps.calls.length || deps.imports.length} defaultOpen={false}>
          <ul className="cv-impact__list">
            {deps.calls.length > 0
              ? deps.calls.slice(0, 12).map((c) => (
                  <li key={c.uid} className="cv-impact__row">
                    <button type="button" className="cv-impact__file-link" onClick={() => onOpenFile?.(c.file_path)}>
                      <code>{c.qualname}</code>
                      <span className="cv-impact__loc">{c.file_path}</span>
                    </button>
                  </li>
                ))
              : deps.imports.slice(0, 12).map((p) => (
                  <li key={p} className="cv-impact__row">
                    <button type="button" className="cv-impact__file-link" onClick={() => onOpenFile?.(p)}>
                      <FileCode size={12} aria-hidden="true" />
                      <code>{p}</code>
                    </button>
                  </li>
                ))}
          </ul>
        </Group>
      )}
    </div>
  );
}

/**
 * Extras shown under an impact answer: clarification choices (when the question named something ambiguous),
 * backend warnings (e.g. "no LLM key, showing the structured analysis") and the accuracy caveat.
 *
 * @param {Array}  candidates   [{uid, qualname, kind, file_path} | {path}]
 * @param {(candidate: object) => void} [onPickCandidate]   called with the chosen candidate
 */
export function ImpactAnswerExtras({ candidates = [], warnings = [], caveat = '', onPickCandidate, disabled = false }) {
  return (
    <>
      {candidates.length > 0 && (
        <div className="cv-impact-clarify" role="group" aria-label="Choose what you mean">
          {candidates.map((c) => (
            <button
              key={c.uid || c.path}
              type="button"
              className="cv-impact-clarify__btn"
              disabled={disabled}
              onClick={() => onPickCandidate?.(c)}
            >
              <span>{c.qualname || c.path}</span>
              {c.file_path && (
                <small>
                  {c.kind} in {c.file_path}
                </small>
              )}
            </button>
          ))}
        </div>
      )}
      {warnings.length > 0 && (
        <ul className="cv-impact-warnings">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {caveat && <p className="cv-impact-caveat">{caveat}</p>}
    </>
  );
}
