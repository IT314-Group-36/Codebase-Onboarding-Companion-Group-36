import { useState, useEffect, useCallback } from 'react';
import { Sparkles, RefreshCw, AlertTriangle, Link2 } from 'lucide-react';
import Button from './Button';
import { getFileExplanation, getSymbolExplanation } from '../services/api';
import './ExplanationCard.css';

// Remembers results for the browser session, so going back to a file does not call the backend again.
// (The backend also caches the generated text per repository and commit.)
const sessionCache = new Map();

const MAX_CHIPS = 8;

function fetchExplanation(repoId, kind, target, refresh = false) {
  return kind === 'file'
    ? getFileExplanation(repoId, target, { refresh })
    : getSymbolExplanation(repoId, target, { refresh });
}

function initialState(cacheKey, autoLoad) {
  if (sessionCache.has(cacheKey)) return { status: 'done', data: sessionCache.get(cacheKey) };
  return { status: autoLoad ? 'loading' : 'idle' };
}

/**
 * Plain-English explanation of one file or one function, plus how it relates to the rest of the code
 * ("this file uses X and is used by Y"). Data comes from GET /repos/{id}/explain.
 *
 * Render it with `key={target}` so the card resets when the selection changes.
 *
 * @param {string}  repoId
 * @param {'file'|'symbol'} kind
 * @param {string}  target        file path, or symbol uid
 * @param {boolean} [autoLoad]    fetch immediately instead of waiting for the button
 * @param {(path: string) => void} [onOpenFile]       called when a related file is clicked
 * @param {(uid: string) => void}  [onSelectSymbol]   called when a key function is clicked
 */
export default function ExplanationCard({ repoId, kind, target, autoLoad = false, onOpenFile, onSelectSymbol }) {
  const cacheKey = `${repoId}|${kind}|${target}`;
  const [state, setState] = useState(() => initialState(cacheKey, autoLoad));

  // Automatic first load (no synchronous setState here: the initial state is already "loading")
  useEffect(() => {
    if (!autoLoad || sessionCache.has(cacheKey)) return undefined;
    let cancelled = false;
    fetchExplanation(repoId, kind, target)
      .then((data) => {
        sessionCache.set(cacheKey, data);
        if (!cancelled) setState({ status: 'done', data });
      })
      .catch((err) => {
        if (!cancelled) setState({ status: 'error', message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [autoLoad, cacheKey, repoId, kind, target]);

  const load = useCallback(
    async (refresh = false) => {
      setState({ status: 'loading' });
      try {
        const data = await fetchExplanation(repoId, kind, target, refresh);
        sessionCache.set(cacheKey, data);
        setState({ status: 'done', data });
      } catch (err) {
        setState({ status: 'error', message: err.message });
      }
    },
    [cacheKey, repoId, kind, target]
  );

  const noun = kind === 'file' ? 'file' : 'function';

  if (state.status === 'idle') {
    return (
      <div className="cv-detail-card cv-expl">
        <div className="cv-expl__head">
          <h4 className="cv-detail-label cv-expl__label">
            <Sparkles size={12} /> Plain-English explanation
          </h4>
        </div>
        <p className="cv-detail-text">
          What this {noun} does, written for someone new to the codebase, and how it connects to the rest.
        </p>
        <Button variant="secondary" size="sm" icon={<Sparkles size={13} />} onClick={() => load()}>
          Explain this {noun}
        </Button>
      </div>
    );
  }

  if (state.status === 'loading') {
    return (
      <div className="cv-detail-card cv-expl" aria-busy="true">
        <h4 className="cv-detail-label cv-expl__label">
          <Sparkles size={12} /> Plain-English explanation
        </h4>
        <div className="cv-expl__loading">
          <span className="cv-btn__spinner" aria-hidden="true" />
          <span>Reading the code and its relationships...</span>
        </div>
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className="cv-detail-card cv-expl cv-expl--error" role="alert">
        <h4 className="cv-detail-label cv-expl__label">
          <AlertTriangle size={12} /> Could not explain this {noun}
        </h4>
        <p className="cv-detail-text">{state.message}</p>
        <Button variant="secondary" size="sm" icon={<RefreshCw size={13} />} onClick={() => load()}>
          Try again
        </Button>
      </div>
    );
  }

  const { data } = state;
  const ex = data.explanation;
  const rel = data.relationships || {};

  // Related items: files for a file, functions for a function. Clicking opens the file.
  const groups =
    kind === 'file'
      ? [
          { title: 'Uses', items: (rel.uses || []).map((p) => ({ key: p, label: p, path: p })), total: rel.uses_total },
          {
            title: 'Used by',
            items: (rel.used_by || []).map((p) => ({ key: p, label: p, path: p })),
            total: rel.used_by_total,
          },
        ]
      : [
          {
            title: 'Calls',
            items: (rel.calls || []).map((s) => ({ key: s.uid, label: s.qualname, path: s.file_path, hint: s.file_path })),
            total: rel.calls_total,
          },
          {
            title: 'Called by',
            items: (rel.called_by || []).map((s) => ({
              key: s.uid,
              label: s.qualname,
              path: s.file_path,
              hint: s.file_path,
            })),
            total: rel.called_by_total,
          },
        ];

  return (
    <div className="cv-detail-card cv-expl">
      <div className="cv-expl__head">
        <h4 className="cv-detail-label cv-expl__label">
          <Sparkles size={12} /> Plain-English explanation
        </h4>
        <div className="cv-expl__head-right">
          {data.source !== 'none' && (
            <span className="cv-expl__badge" title={data.source === 'cache' ? 'Saved earlier for this commit' : 'Generated just now'}>
              {data.source === 'cache' ? 'saved' : 'AI'}
            </span>
          )}
          {ex && (
            <button
              type="button"
              className="cv-expl__icon-btn"
              onClick={() => load(true)}
              title="Write this explanation again"
              aria-label="Regenerate explanation"
            >
              <RefreshCw size={12} />
            </button>
          )}
        </div>
      </div>

      {ex && <p className="cv-expl__summary">{ex.summary}</p>}

      {data.relationshipSummary && (
        <p className="cv-expl__relsentence">
          <Link2 size={12} aria-hidden="true" /> {data.relationshipSummary.replace(/`/g, '')}
        </p>
      )}

      {ex && (
        <>
          <p className="cv-detail-text cv-expl__body">{ex.explanation}</p>

          {ex.inputs_outputs && (
            <div className="cv-expl__block">
              <span className="cv-expl__block-title">Takes in / gives back</span>
              <p className="cv-detail-text">{ex.inputs_outputs}</p>
            </div>
          )}

          {kind === 'file' && ex.key_symbols?.length > 0 && (
            <div className="cv-expl__block">
              <span className="cv-expl__block-title">Key functions and classes</span>
              <ul className="cv-expl__keylist">
                {ex.key_symbols.map((s) => (
                  <li key={s.uid}>
                    <button
                      type="button"
                      className="cv-expl__link"
                      onClick={() => onSelectSymbol?.(s.uid)}
                      title={`Explain ${s.name} (line ${s.start_line})`}
                    >
                      <code>{s.name}</code>
                    </button>
                    <span> {s.note}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {ex.how_it_fits && (
            <div className="cv-expl__block">
              <span className="cv-expl__block-title">How it fits in</span>
              <p className="cv-detail-text">{ex.how_it_fits}</p>
            </div>
          )}
        </>
      )}

      {groups.map(
        (g) =>
          g.items.length > 0 && (
            <div className="cv-expl__block" key={g.title}>
              <span className="cv-expl__block-title">
                {g.title} ({g.total ?? g.items.length})
              </span>
              <div className="cv-dep-chips">
                {g.items.slice(0, MAX_CHIPS).map((it) => (
                  <button
                    key={it.key}
                    type="button"
                    className="cv-dep-chip cv-expl__chip"
                    onClick={() => onOpenFile?.(it.path)}
                    title={`Open ${it.path}`}
                  >
                    <code>{it.label}</code>
                  </button>
                ))}
                {(g.total ?? g.items.length) > Math.min(g.items.length, MAX_CHIPS) && (
                  <span className="cv-expl__more">
                    +{(g.total ?? g.items.length) - Math.min(g.items.length, MAX_CHIPS)} more
                  </span>
                )}
              </div>
            </div>
          )
      )}

      {data.warnings.map((w) => (
        <p className="cv-expl__warn" key={w}>
          <AlertTriangle size={12} aria-hidden="true" /> {w}
        </p>
      ))}
      {data.caveat && <p className="cv-expl__caveat">{data.caveat}</p>}
    </div>
  );
}
