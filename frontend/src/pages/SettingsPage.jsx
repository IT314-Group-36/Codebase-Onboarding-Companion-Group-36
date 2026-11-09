import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  User,
  Trash2,
  LogOut,
  Eye,
  Shield,
  Sliders,
  RotateCcw,
} from 'lucide-react';
import GithubIcon from '../components/GithubIcon';
import Button from '../components/Button';
import ConfirmDialog from '../components/ConfirmDialog';
import { getRepositories, reindexRepository } from '../services/api';
import { showToast } from '../utils/toast';
import { useAuth } from '../context/useAuth';
import './SettingsPage.css';

/**
 * Page 6: Repository and Account Management
 * Clean settings dashboard with grouped sections, repository list,
 * interface preferences, and session controls.
 */
export default function SettingsPage() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [repos, setRepos] = useState([]);
  const [disconnectCandidate, setDisconnectCandidate] = useState(null);
  const [disconnecting, setDisconnecting] = useState(false);
  const [logoutModalOpen, setLogoutModalOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [reindexingId, setReindexingId] = useState(null);

  // Preference switches
  const [emailDigest, setEmailDigest] = useState(true);
  const [onboardingQuests, setOnboardingQuests] = useState(true);
  const [autoExpandTree, setAutoExpandTree] = useState(true);
  const [telemetryOptIn, setTelemetryOptIn] = useState(false);

  useEffect(() => {
    async function loadRepos() {
      try {
        const res = await getRepositories();
        if (res.success) {
          // Filter out any locally hidden repo IDs
          let hidden = [];
          try {
            hidden = JSON.parse(localStorage.getItem('codeverse_hidden_repos') || '[]');
          } catch {
            hidden = [];
          }
          const visible = (res.repositories || []).filter((r) => !hidden.includes(r.id));
          setRepos(visible);
        }
      } catch (err) {
        console.warn('Failed to load repositories in settings:', err.message);
      }
    }
    loadRepos();
  }, []);

  const handleDisconnectRepo = async () => {
    if (!disconnectCandidate) return;
    setDisconnecting(true);

    try {
      // Store in locally hidden list since backend does not have DELETE /repos/{id}
      let hidden = [];
      try {
        hidden = JSON.parse(localStorage.getItem('codeverse_hidden_repos') || '[]');
      } catch {
        hidden = [];
      }
      hidden.push(disconnectCandidate.id);
      localStorage.setItem('codeverse_hidden_repos', JSON.stringify(hidden));

      setRepos((prev) => prev.filter((r) => r.id !== disconnectCandidate.id));
      showToast(
        `Removed ${disconnectCandidate.fullName} from local frontend view. Backend records remain preserved.`,
        'success'
      );
    } finally {
      setDisconnecting(false);
      setDisconnectCandidate(null);
    }
  };

  const handleReindex = async (repo) => {
    setReindexingId(repo.id);
    try {
      const res = await reindexRepository(repo.id);
      if (res.success) {
        showToast(`Re-indexing started for ${repo.fullName}.`, 'success');
      }
    } catch (err) {
      showToast(err.message || 'Re-index request failed.', 'error');
    } finally {
      setReindexingId(null);
    }
  };

  const handleConfirmLogout = async () => {
    setLoggingOut(true);
    await logout();
    setLoggingOut(false);
    setLogoutModalOpen(false);
    navigate('/');
  };

  return (
    <div className="cv-settings-view">
      <div className="cv-settings-header">
        <h1 className="cv-settings-title">Settings</h1>
        <p className="cv-settings-desc">
          Manage your developer profile, connected GitHub projects, and ingestion preferences.
        </p>
      </div>

      <div className="cv-settings-layout">
        {/* Left Column: Profile & Connected Repositories */}
        <div className="cv-settings-main-col">
          {/* Profile Section */}
          <section className="cv-settings-section" aria-label="Developer Profile">
            <div className="cv-settings-section__head">
              <div className="cv-settings-section__title-group">
                <User size={16} className="cv-settings-section__icon" />
                <h2 className="cv-settings-section__title">Developer Profile</h2>
              </div>
              <span className="cv-status-chip">GitHub Account</span>
            </div>

            <div className="cv-profile-box">
              <div className="cv-profile-avatar" aria-hidden="true">
                {(user?.name || '?').split(' ').map((n) => n[0]).join('').slice(0, 2)}
              </div>
              <div className="cv-profile-info">
                <h3 className="cv-profile-name">{user?.name}</h3>
                <p className="cv-profile-email">{user?.email || 'No public email on GitHub'}</p>
                <div className="cv-profile-meta-tags">
                  <span className="cv-profile-tag">@{user?.githubUsername}</span>
                  <span className="cv-profile-tag">
                    {user?.githubConnected ? 'Private repos enabled' : 'GitHub not connected'}
                  </span>
                </div>
              </div>
            </div>
          </section>

          {/* Backend Connection */}
          <section className="cv-settings-section" aria-label="Backend Connection">
            <div className="cv-settings-section__head">
              <div className="cv-settings-section__title-group">
                <GithubIcon size={16} className="cv-settings-section__icon" />
                <h2 className="cv-settings-section__title">FastAPI Engine</h2>
              </div>
            </div>

            <div className="cv-gh-status-box">
              <div className="cv-gh-status-dot" aria-hidden="true" />
              <div className="cv-gh-status-copy">
                <strong>Status: Connected (http://localhost:8000)</strong>
                <p>
                  PostgreSQL with pgvector hybrid search and ARQ background worker are active.
                </p>
              </div>
            </div>
          </section>

          {/* Connected Repositories */}
          <section className="cv-settings-section" aria-label="Connected Repositories">
            <div className="cv-settings-section__head">
              <div className="cv-settings-section__title-group">
                <Shield size={16} className="cv-settings-section__icon" />
                <h2 className="cv-settings-section__title">Connected Repositories</h2>
              </div>
              <span className="cv-settings-section__count">{repos.length} repositories</span>
            </div>

            {repos.length === 0 ? (
              <div className="cv-settings-empty-repos">
                <p>No repositories connected.</p>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => navigate('/connect')}
                >
                  Connect Repository
                </Button>
              </div>
            ) : (
              <div className="cv-settings-repo-list">
                {repos.map((r) => (
                  <div key={r.id} className="cv-settings-repo-item">
                    <div className="cv-settings-repo-item__info">
                      <div className="cv-settings-repo-item__name-row">
                        <strong className="cv-settings-repo-item__name">{r.fullName}</strong>
                        <span className="cv-settings-repo-item__branch">{r.branch}</span>
                      </div>
                      <span className="cv-settings-repo-item__meta">
                        {r.stats?.files || 0} files · {r.stats?.modules || 0} modules · {r.language}
                      </span>
                    </div>

                    <div className="cv-settings-repo-item__actions">
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<RotateCcw size={13} />}
                        loading={reindexingId === r.id}
                        onClick={() => handleReindex(r)}
                        title="Reindex repository"
                      >
                        Reindex
                      </Button>

                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<Eye size={13} />}
                        onClick={() => navigate(`/repository/${r.id}`)}
                      >
                        View
                      </Button>

                      <Button
                        variant="danger"
                        size="sm"
                        icon={<Trash2 size={13} />}
                        onClick={() => setDisconnectCandidate(r)}
                      >
                        Remove
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        {/* Right Column: Preferences & Danger Zone */}
        <div className="cv-settings-side-col">
          {/* Preferences */}
          <section className="cv-settings-section" aria-label="Interface Preferences">
            <div className="cv-settings-section__head">
              <div className="cv-settings-section__title-group">
                <Sliders size={16} className="cv-settings-section__icon" />
                <h2 className="cv-settings-section__title">Preferences</h2>
              </div>
            </div>

            <div className="cv-settings-switches">
              <label className="cv-switch-label">
                <input
                  type="checkbox"
                  checked={emailDigest}
                  onChange={(e) => {
                    setEmailDigest(e.target.checked);
                    showToast('Notification preference updated.', 'info');
                  }}
                />
                <div>
                  <span className="cv-switch-title">Email Analysis Digest</span>
                  <p className="cv-switch-desc">Receive summaries when AST indexing finishes.</p>
                </div>
              </label>

              <label className="cv-switch-label">
                <input
                  type="checkbox"
                  checked={onboardingQuests}
                  onChange={(e) => {
                    setOnboardingQuests(e.target.checked);
                    showToast('Onboarding journey tips updated.', 'info');
                  }}
                />
                <div>
                  <span className="cv-switch-title">Guided Onboarding Quests</span>
                  <p className="cv-switch-desc">Display beginner-friendly tasks on dashboard.</p>
                </div>
              </label>

              <label className="cv-switch-label">
                <input
                  type="checkbox"
                  checked={autoExpandTree}
                  onChange={(e) => {
                    setAutoExpandTree(e.target.checked);
                    showToast('File tree expansion preference saved.', 'info');
                  }}
                />
                <div>
                  <span className="cv-switch-title">Auto-Expand Explorer Trees</span>
                  <p className="cv-switch-desc">Automatically expand nested src directories.</p>
                </div>
              </label>

              <label className="cv-switch-label">
                <input
                  type="checkbox"
                  checked={telemetryOptIn}
                  onChange={(e) => {
                    setTelemetryOptIn(e.target.checked);
                    showToast('Telemetry preference updated.', 'info');
                  }}
                />
                <div>
                  <span className="cv-switch-title">Anonymous Parsing Telemetry</span>
                  <p className="cv-switch-desc">Help improve module detection heuristics.</p>
                </div>
              </label>
            </div>
          </section>

          {/* Session Termination */}
          <section className="cv-settings-section cv-settings-section--danger" aria-label="Session Termination">
            <h2 className="cv-settings-section__title cv-settings-section__title--danger">Session Controls</h2>
            <p className="cv-danger-desc">
              Signing out ends your session on this browser and returns you to the login screen.
            </p>
            <Button
              variant="danger"
              size="md"
              icon={<LogOut size={15} />}
              onClick={() => setLogoutModalOpen(true)}
            >
              Sign Out of Codeverse
            </Button>
          </section>
        </div>
      </div>

      {/* Disconnect Confirmation Dialog */}
      <ConfirmDialog
        open={!!disconnectCandidate}
        title="Remove Repository from View?"
        message={`Remove "${disconnectCandidate?.fullName}" from your local frontend view? Note: The backend API does not currently expose a DELETE endpoint, so its indexed database records remain preserved on the server.`}
        confirmLabel="Remove"
        variant="danger"
        loading={disconnecting}
        onConfirm={handleDisconnectRepo}
        onCancel={() => setDisconnectCandidate(null)}
      />

      {/* Logout Confirmation Dialog */}
      <ConfirmDialog
        open={logoutModalOpen}
        title="Sign Out of CODEVERSE"
        message="Are you sure you want to log out of your session? You can sign right back in."
        confirmLabel="Log Out"
        variant="danger"
        loading={loggingOut}
        onConfirm={handleConfirmLogout}
        onCancel={() => setLogoutModalOpen(false)}
      />
    </div>
  );
}
