import { useEffect, useState } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  GitBranch,
  FolderTree,
  Boxes,
  CheckSquare,
  MessageSquare,
  Settings,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Sparkles,
  ExternalLink,
} from 'lucide-react';
import { getRepositories } from '../services/api';
import './Sidebar.css';

/**
 * Reusable Codeverse Sidebar with collapsed and mobile overlay modes.
 * Features clean graphite surface, restrained dark-orange active tint,
 * and Lucide icons with consistent 18px stroke weight.
 */
export default function Sidebar({
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onCloseMobile,
  onLogoutRequest,
}) {
  const navigate = useNavigate();
  const location = useLocation();

  // The repository the repo-specific links point at: the one in the URL, else the last one opened,
  // else the first ready one. Only the user's own repositories are considered (GET /repos).
  const [repos, setRepos] = useState([]);
  useEffect(() => {
    let alive = true;
    getRepositories()
      .then((res) => { if (alive) setRepos(res.repositories || []); })
      .catch(() => { if (alive) setRepos([]); });
    return () => { alive = false; };
  }, [location.pathname]);

  const urlRepoId = location.pathname.match(
    /\/(?:repository|explorer|dependencies|onboarding|qa)\/([^/?]+)/
  )?.[1];
  let lastRepoId = null;
  try {
    lastRepoId = localStorage.getItem('codeverse_last_repo_id');
  } catch {
    // ignore storage access errors
  }
  const byId = (id) => repos.find((r) => String(r.id) === String(id));
  const activeRepo =
    byId(urlRepoId) || byId(lastRepoId) || repos.find((r) => r.rawStatus === 'ready') || repos[0] || null;
  const activeRepoId = activeRepo ? activeRepo.id : null;

  useEffect(() => {
    if (!activeRepoId) return;
    try {
      localStorage.setItem('codeverse_last_repo_id', String(activeRepoId));
    } catch {
      // ignore storage access errors
    }
  }, [activeRepoId]);

  // With no repository yet, the repo links lead to the connect page instead of a broken /explorer/1.
  const repoLink = (section) => (activeRepoId ? `/${section}/${activeRepoId}` : '/connect');

  const navItems = [
    { to: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard size={18} strokeWidth={1.8} /> },
    { to: '/connect', label: 'Connect Repo', icon: <GitBranch size={18} strokeWidth={1.8} /> },
    { to: repoLink('explorer'), label: 'Code Explorer', icon: <FolderTree size={18} strokeWidth={1.8} /> },
    { to: repoLink('dependencies'), label: 'Module Map', icon: <Boxes size={18} strokeWidth={1.8} /> },
    { to: repoLink('onboarding'), label: 'Onboarding', icon: <CheckSquare size={18} strokeWidth={1.8} /> },
    { to: repoLink('qa'), label: 'Codebase Q&A', icon: <MessageSquare size={18} strokeWidth={1.8} /> },
    { to: '/settings', label: 'Settings', icon: <Settings size={18} strokeWidth={1.8} /> },
  ];

  const handleNavClick = () => {
    if (mobileOpen) {
      onCloseMobile();
    }
  };

  return (
    <>
      {mobileOpen && (
        <div
          className="cv-sidebar-backdrop"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        className={`cv-sidebar ${collapsed ? 'cv-sidebar--collapsed' : ''} ${mobileOpen ? 'cv-sidebar--mobile-open' : ''}`}
        aria-label="Application Navigation"
      >
        <div className="cv-sidebar__brand-box">
          <button
            type="button"
            className="cv-sidebar__brand-btn"
            onClick={() => { navigate('/dashboard'); handleNavClick(); }}
            title="CODEVERSE — Home"
          >
            <div className="cv-sidebar__logo-icon" aria-hidden="true">
              <Sparkles size={17} strokeWidth={2} />
            </div>
            {!collapsed && (
              <div className="cv-sidebar__brand-text">
                <span className="cv-sidebar__brand-title">CODEVERSE</span>
                <span className="cv-sidebar__brand-tag">Explore Codebase</span>
              </div>
            )}
          </button>
        </div>

        <nav className="cv-sidebar__nav">
          <span className="cv-sidebar__section-title">
            {!collapsed ? 'Navigation' : '•••'}
          </span>
          {navItems.map((item) => (
            <NavLink
              key={item.label}
              to={item.to}
              onClick={handleNavClick}
              className={({ isActive }) =>
                `cv-sidebar__link ${isActive ? 'cv-sidebar__link--active' : ''}`
              }
              title={collapsed ? item.label : undefined}
            >
              <span className="cv-sidebar__icon" aria-hidden="true">{item.icon}</span>
              {!collapsed && <span className="cv-sidebar__label">{item.label}</span>}
              {!collapsed && item.badge && (
                <span className="cv-sidebar__badge">{item.badge}</span>
              )}
            </NavLink>
          ))}
        </nav>

        {!collapsed && activeRepo && (
          <div className="cv-sidebar__repo-shortcut">
            <div className="cv-sidebar__shortcut-card">
              <span className="cv-sidebar__shortcut-badge">ACTIVE REPO</span>
              <p className="cv-sidebar__shortcut-name" title={`${activeRepo.owner}/${activeRepo.name}`}>
                {activeRepo.name}
              </p>
              <button
                type="button"
                className="cv-sidebar__shortcut-btn"
                onClick={() => { navigate(`/repository/${activeRepoId}`); handleNavClick(); }}
              >
                <span>View Details</span>
                <ExternalLink size={12} strokeWidth={1.8} />
              </button>
            </div>
          </div>
        )}

        <div className="cv-sidebar__footer">
          <button
            type="button"
            className="cv-sidebar__link cv-sidebar__logout-btn"
            onClick={() => { onLogoutRequest(); handleNavClick(); }}
            title={collapsed ? 'Log Out' : undefined}
          >
            <span className="cv-sidebar__icon" aria-hidden="true">
              <LogOut size={18} strokeWidth={1.8} />
            </span>
            {!collapsed && <span className="cv-sidebar__label">Log Out</span>}
          </button>

          <button
            type="button"
            className="cv-sidebar__collapse-btn"
            onClick={onToggleCollapse}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? (
              <ChevronRight size={18} strokeWidth={1.8} />
            ) : (
              <ChevronLeft size={18} strokeWidth={1.8} />
            )}
          </button>
        </div>
      </aside>
    </>
  );
}
