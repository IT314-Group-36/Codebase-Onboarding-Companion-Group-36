import { NAV, SECTION_LABEL } from '../utils/navLabels';
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
    const crumbs = [{ label: NAV.home, to: '/dashboard' }];
    const section = path.split('/')[1];

    if (path === '/connect') {
      crumbs.push({ label: NAV.connect, to: '/connect' });
    } else if (path === '/settings') {
      crumbs.push({ label: NAV.settings, to: '/settings' });
    } else if (SECTION_LABEL[section]) {
      // Same names as the sidebar. With a repository id the page sits under "Repositories".
      if (path.split('/').filter(Boolean).length > 1) crumbs.push({ label: 'Repositories', to: '/dashboard' });
      crumbs.push({ label: SECTION_LABEL[section], to: path });
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
                <span>{NAV.connect}</span>
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
