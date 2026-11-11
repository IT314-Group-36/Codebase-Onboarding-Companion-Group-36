import './LoadingState.css';

/**
 * Loading state with clean developer-tool spinner.
 */
export default function LoadingState({ message = 'Loading...', fullPage = false }) {
  return (
    <div className={`cv-loading ${fullPage ? 'cv-loading--full' : ''}`} role="status">
      <div className="cv-loading__spinner" aria-hidden="true" />
      <p className="cv-loading__message">{message}</p>
    </div>
  );
}
