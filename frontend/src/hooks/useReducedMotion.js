import { useCallback, useEffect, useState } from 'react';

const KEY = 'cv-motion'; // 'reduce' | 'full' | null (follow the OS setting)

function osPrefersReduced() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

function readStored() {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function apply(reduce) {
  document.documentElement.dataset.motion = reduce ? 'reduce' : 'full';
}

/** Call once near the app root so the saved choice applies on every page. */
export function initMotionPreference() {
  const stored = readStored();
  apply(stored ? stored === 'reduce' : osPrefersReduced());
}

/**
 * Reduced-motion state: follows the OS setting unless the user picked one in the app.
 * Returns { reduced, setReduced }. Components can also rely on the CSS in styles/a11y.css.
 */
export default function useReducedMotion() {
  const [reduced, setReducedState] = useState(() => {
    const stored = readStored();
    return stored ? stored === 'reduce' : osPrefersReduced();
  });

  useEffect(() => {
    apply(reduced);
  }, [reduced]);

  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mq) return undefined;
    const onChange = (e) => {
      if (!readStored()) setReducedState(e.matches);
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  const setReduced = useCallback((value) => {
    try {
      localStorage.setItem(KEY, value ? 'reduce' : 'full');
    } catch {
      /* storage unavailable: the choice just lasts for this session */
    }
    setReducedState(value);
  }, []);

  return { reduced, setReduced };
}
