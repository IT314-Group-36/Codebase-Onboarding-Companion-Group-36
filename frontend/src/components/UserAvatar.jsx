import { useState } from 'react';
import './UserAvatar.css';

/** Up to two initials from a display name or login ("Aaryan Modi" -> "AM"). */
function initialsOf(user) {
  const source = (user?.name || user?.githubUsername || '?').trim();
  return source
    .split(/\s+/)
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

/**
 * The signed-in user's GitHub profile picture, with initials as the fallback
 * (no picture on the account, or the image failed to load).
 */
export default function UserAvatar({ user, className = '' }) {
  const [failedUrl, setFailedUrl] = useState(null);
  const url = user?.avatarUrl;
  const showImage = Boolean(url) && failedUrl !== url;

  return (
    <div className={`cv-user-avatar ${className}`} aria-hidden="true">
      {showImage ? (
        <img
          className="cv-user-avatar__img"
          src={url}
          alt=""
          referrerPolicy="no-referrer"
          onError={() => setFailedUrl(url)}
        />
      ) : (
        initialsOf(user)
      )}
    </div>
  );
}
