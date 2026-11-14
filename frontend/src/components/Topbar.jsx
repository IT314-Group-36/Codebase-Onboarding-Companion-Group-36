import { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import {
  Menu,
  User,
  Sparkles,
  ChevronRight,
  LogOut,
} from 'lucide-react';
import { useAuth } from '../context/useAuth';
import UserAvatar from './UserAvatar';
import MotionToggle from './MotionToggle';
import './Topbar.css';

/**
 * Top navigation bar with dynamic breadcrumbs and the signed-in user's profile menu.
 */
export default function Topbar({ onToggleMobileMenu, onLogoutRequest }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { user: authUser } = useAuth();
  const currentUser = authUser || { name: 'User', email: '', githubUsername: '' };

  const [profileMenuOpen, setProfileMenuOpen] = useState(false);

  const getBreadcrumbs = () => {
    const path = location.pathname;
    const crumbs = [{ label: 'Dashboard', to: '/dashboard' }];

    if (path === '/connect') {
      crumbs.push({ label: 'Connect Repository', to: '/connect' });
    } else if (path.startsWith('/repository/')) {
      crumbs.push({ label: 'Repositories', to: '/dashboard' });
      crumbs.push({ label: 'Overview', to: path });
    } else if (path.startsWith('/explorer/')) {
      crumbs.push({ label: 'Repositories', to: '/dashboard' });
      crumbs.push({ label: 'Codebase Explorer', to: path });
    } else if (path.startsWith('/dependencies/')) {
      crumbs.push({ label: 'Repositories', to: '/dashboard' });
      crumbs.push({ label: 'Dependency Map', to: path });
    } else if (path.startsWith('/onboarding/')) {
      crumbs.push({ label: 'Repositories', to: '/dashboard' });
      crumbs.push({ label: 'Onboarding Journey', to: path });
    } else if (path.startsWith('/qa/')) {
      crumbs.push({ label: 'Repositories', to: '/dashboard' });
      crumbs.push({ label: 'Codebase Q&A', to: path });
    } else if (path === '/settings') {
      crumbs.push({ label: 'Account & Settings', to: '/settings' });
    }

    return crumbs;
  };

  const crumbs = getBreadcrumbs();

  return (
    <header className="cv-topbar" role="banner">
      <div className="cv-topbar__left">
        <button
          type="button"
          className="cv-topbar__menu-toggle"
          onClick={onToggleMobileMenu}
          aria-label="Open mobile navigation"
        >
          <Menu size={22} />
        </button>

        <nav aria-label="Breadcrumbs" className="cv-topbar__breadcrumbs">
          {crumbs.map((c, i) => {
            const isLast = i === crumbs.length - 1;
            return (
              <span key={c.label + i} className="cv-topbar__crumb-item">
                {i > 0 && <ChevronRight size={14} className="cv-topbar__crumb-sep" />}
                {isLast ? (
                  <span className="cv-topbar__crumb-current" aria-current="page">
                    {c.label}
                  </span>
                ) : (
                  <Link to={c.to} className="cv-topbar__crumb-link">
                    {c.label}
                  </Link>
                )}
              </span>
            );
          })}
        </nav>
      </div>

      <div className="cv-topbar__right">
        <MotionToggle />
        {/* User profile menu */}
        <div className="cv-topbar__action-wrapper">
          <button
            type="button"
            className="cv-topbar__profile-btn"
            onClick={() => setProfileMenuOpen(!profileMenuOpen)}
            aria-expanded={profileMenuOpen}
            aria-label="User profile menu"
          >
            <UserAvatar user={currentUser} className="cv-topbar__avatar" />
            <div className="cv-topbar__user-info">
              <span className="cv-topbar__user-name">{currentUser.name}</span>
              {currentUser.githubUsername && (
                <span className="cv-topbar__user-handle">@{currentUser.githubUsername}</span>
              )}
            </div>
          </button>

          {profileMenuOpen && (
            <div className="cv-topbar__dropdown cv-topbar__dropdown--profile">
              <div className="cv-topbar__profile-card">
                <p className="cv-topbar__profile-name">{currentUser.name}</p>
                {currentUser.email && <p className="cv-topbar__profile-email">{currentUser.email}</p>}
                <span className="cv-topbar__github-tag">@{currentUser.githubUsername || 'developer'}</span>
              </div>
              <div className="cv-topbar__dropdown-divider" />
              <button
                type="button"
                className="cv-topbar__menu-item"
                onClick={() => { setProfileMenuOpen(false); navigate('/settings'); }}
              >
                <User size={16} />
                <span>Account Settings</span>
              </button>
              <button
                type="button"
                className="cv-topbar__menu-item"
                onClick={() => { setProfileMenuOpen(false); navigate('/connect'); }}
              >
                <Sparkles size={16} />
                <span>Connect Repository</span>
              </button>
              <div className="cv-topbar__dropdown-divider" />
              <button
                type="button"
                className="cv-topbar__menu-item cv-topbar__menu-item--danger"
                onClick={() => { setProfileMenuOpen(false); onLogoutRequest(); }}
              >
                <LogOut size={16} />
                <span>Log Out</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
