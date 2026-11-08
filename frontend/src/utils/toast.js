// ============================================
// CODEVERSE — Global Toast Event Dispatcher
// ============================================

let toastListeners = [];
let toastCounter = 0;

/**
 * Trigger global toast notification.
 *
 * @param {string} message
 * @param {'success'|'error'|'info'} [type='info']
 * @param {number} [duration=4000]
 */
export function showToast(message, type = 'info', duration = 4000) {
  const id = ++toastCounter;
  const item = { id, message, type, duration };
  toastListeners.forEach((fn) => fn(item));
}

export function subscribeToast(fn) {
  toastListeners.push(fn);
  return () => {
    toastListeners = toastListeners.filter((listener) => listener !== fn);
  };
}
