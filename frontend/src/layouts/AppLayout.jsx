import { useState } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import Topbar from '../components/Topbar';
import CosmicBackground from '../components/CosmicBackground';
import ConfirmDialog from '../components/ConfirmDialog';
import { ToastContainer } from '../components/Toast';
import { useAuth } from '../context/useAuth';
import './AppLayout.css';

/**
 * Standard Application Shell Layout with cosmic ambient background,
 * responsive sidebar, dynamic topbar, and logout modal.
 */
export default function AppLayout() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [logoutModalOpen, setLogoutModalOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  const handleConfirmLogout = async () => {
    setLoggingOut(true);
    await logout();
    setLoggingOut(false);
    setLogoutModalOpen(false);
    navigate('/');
  };

  return (
    <div className={`cv-app-shell ${collapsed ? 'cv-app-shell--collapsed' : ''}`}>
      <CosmicBackground intensity="medium" />

      <Sidebar
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(!collapsed)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        onLogoutRequest={() => setLogoutModalOpen(true)}
      />

      <div className="cv-app-shell__body">
        <Topbar
          onToggleMobileMenu={() => setMobileOpen(!mobileOpen)}
          onLogoutRequest={() => setLogoutModalOpen(true)}
        />
        <main className="cv-app-shell__content">
          <Outlet />
        </main>
      </div>

      <ConfirmDialog
        open={logoutModalOpen}
        title="Sign Out"
        message="Are you sure you want to exit your demo session? You can sign back in at any time."
        confirmLabel="Log Out"
        variant="danger"
        loading={loggingOut}
        onConfirm={handleConfirmLogout}
        onCancel={() => setLogoutModalOpen(false)}
      />

      <ToastContainer />
    </div>
  );
}
