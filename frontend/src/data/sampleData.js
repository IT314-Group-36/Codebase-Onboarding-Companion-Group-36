// ============================================
// CODEVERSE — Sample / Demo Data Layer
// Provides realistic demo data for repositories, file structures,
// module relationship graphs, and user onboarding tasks.
// TODO: Replace with real API responses when backend is integrated.
// ============================================

export const sampleUser = {
  id: 'demo-user-001',
  name: 'Alex Rivera',
  email: 'alex.rivera@example.com',
  githubUsername: 'alexrivera',
  role: 'Software Engineer',
  joinedAt: '2026-09-15T10:00:00Z',
  plan: 'Developer Free (Demo)',
  avatarUrl: null, // Displays initials 'AR'
};

export const sampleRepositories = [
  {
    id: 'repo-001',
    name: 'react-dashboard',
    owner: 'alexrivera',
    fullName: 'alexrivera/react-dashboard',
    description: 'A modern React analytics dashboard with modular state management and D3 data visualizations.',
    language: 'JavaScript',
    languages: { JavaScript: 64, TypeScript: 20, CSS: 12, HTML: 4 },
    branch: 'main',
    branches: ['main', 'develop', 'feature/analytics-v2', 'hotfix/token-refresh'],
    stars: 342,
    forks: 58,
    status: 'analyzed',
    connectedAt: '2026-10-22T14:30:00Z',
    analyzedAt: '2026-10-22T14:34:10Z',
    stats: { files: 128, modules: 18, functions: 342, components: 45 },
    technologies: ['React 19', 'Vite', 'D3.js', 'TailwindCSS', 'Axios', 'Zustand'],
    defaultFile: 'src/App.jsx',
  },
  {
    id: 'repo-002',
    name: 'api-gateway',
    owner: 'techcorp',
    fullName: 'techcorp/api-gateway',
    description: 'High-performance microservices gateway featuring distributed rate-limiting and token verification.',
    language: 'Python',
    languages: { Python: 78, Shell: 12, Dockerfile: 6, YAML: 4 },
    branch: 'main',
    branches: ['main', 'staging', 'release/v2'],
    stars: 1205,
    forks: 312,
    status: 'analyzing',
    connectedAt: '2026-10-29T09:15:00Z',
    analyzedAt: null,
    stats: { files: 89, modules: 12, functions: 215, components: 0 },
    technologies: ['FastAPI', 'Redis', 'Docker', 'PostgreSQL', 'Pydantic'],
    defaultFile: 'gateway/main.py',
  },
  {
    id: 'repo-003',
    name: 'mobile-app',
    owner: 'alexrivera',
    fullName: 'alexrivera/mobile-app',
    description: 'Cross-platform mobile client for Codeverse notifications and repository alerts.',
    language: 'Dart',
    languages: { Dart: 86, Swift: 8, Kotlin: 4, YAML: 2 },
    branch: 'develop',
    branches: ['main', 'develop', 'feature/push-notifications'],
    stars: 89,
    forks: 14,
    status: 'connected',
    connectedAt: '2026-10-31T11:00:00Z',
    analyzedAt: null,
    stats: { files: 64, modules: 9, functions: 178, components: 32 },
    technologies: ['Flutter', 'Dart', 'Firebase', 'Provider', 'Bloc'],
    defaultFile: 'lib/main.dart',
  },
];

export const sampleFileTree = [
  {
    id: 'src',
    name: 'src',
    type: 'folder',
    children: [
      {
        id: 'src/components',
        name: 'components',
        type: 'folder',
        children: [
          { id: 'src/components/Header.jsx', name: 'Header.jsx', type: 'file', language: 'jsx', size: '2.4 KB', lines: 85 },
          { id: 'src/components/Sidebar.jsx', name: 'Sidebar.jsx', type: 'file', language: 'jsx', size: '3.1 KB', lines: 112 },
          { id: 'src/components/Chart.jsx', name: 'Chart.jsx', type: 'file', language: 'jsx', size: '4.7 KB', lines: 156 },
          { id: 'src/components/DataTable.jsx', name: 'DataTable.jsx', type: 'file', language: 'jsx', size: '5.2 KB', lines: 189 },
          { id: 'src/components/MetricCard.jsx', name: 'MetricCard.jsx', type: 'file', language: 'jsx', size: '1.9 KB', lines: 68 },
        ],
      },
      {
        id: 'src/pages',
        name: 'pages',
        type: 'folder',
        children: [
          { id: 'src/pages/Dashboard.jsx', name: 'Dashboard.jsx', type: 'file', language: 'jsx', size: '6.8 KB', lines: 234 },
          { id: 'src/pages/Analytics.jsx', name: 'Analytics.jsx', type: 'file', language: 'jsx', size: '4.3 KB', lines: 145 },
          { id: 'src/pages/Settings.jsx', name: 'Settings.jsx', type: 'file', language: 'jsx', size: '3.9 KB', lines: 130 },
        ],
      },
      {
        id: 'src/hooks',
        name: 'hooks',
        type: 'folder',
        children: [
          { id: 'src/hooks/useAuth.js', name: 'useAuth.js', type: 'file', language: 'js', size: '1.8 KB', lines: 62 },
          { id: 'src/hooks/useData.js', name: 'useData.js', type: 'file', language: 'js', size: '2.1 KB', lines: 74 },
        ],
      },
      {
        id: 'src/utils',
        name: 'utils',
        type: 'folder',
        children: [
          { id: 'src/utils/api.js', name: 'api.js', type: 'file', language: 'js', size: '3.4 KB', lines: 118 },
          { id: 'src/utils/helpers.js', name: 'helpers.js', type: 'file', language: 'js', size: '1.2 KB', lines: 45 },
          { id: 'src/utils/constants.js', name: 'constants.js', type: 'file', language: 'js', size: '0.8 KB', lines: 28 },
        ],
      },
      { id: 'src/App.jsx', name: 'App.jsx', type: 'file', language: 'jsx', size: '1.5 KB', lines: 52 },
      { id: 'src/main.jsx', name: 'main.jsx', type: 'file', language: 'jsx', size: '0.4 KB', lines: 12 },
      { id: 'src/index.css', name: 'index.css', type: 'file', language: 'css', size: '2.8 KB', lines: 96 },
    ],
  },
  {
    id: 'public',
    name: 'public',
    type: 'folder',
    children: [
      { id: 'public/index.html', name: 'index.html', type: 'file', language: 'html', size: '0.8 KB', lines: 22 },
      { id: 'public/favicon.svg', name: 'favicon.svg', type: 'file', language: 'svg', size: '1.2 KB', lines: 18 },
    ],
  },
  { id: 'package.json', name: 'package.json', type: 'file', language: 'json', size: '1.1 KB', lines: 36 },
  { id: 'vite.config.js', name: 'vite.config.js', type: 'file', language: 'js', size: '0.6 KB', lines: 18 },
  { id: 'README.md', name: 'README.md', type: 'file', language: 'md', size: '2.3 KB', lines: 68 },
  { id: '.gitignore', name: '.gitignore', type: 'file', language: 'other', size: '0.3 KB', lines: 14 },
];

export const sampleFileContent = {
  'src/App.jsx': `import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';
import { AuthProvider } from './hooks/useAuth';

/**
 * App Root Component
 * Handles client routing, authentication context provider,
 * and standard application layout.
 */
export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app-container">
          <Sidebar />
          <div className="main-wrapper">
            <Header title="Analytics Studio" />
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </div>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}`,
  'src/components/Header.jsx': `import React from 'react';
import { useAuth } from '../hooks/useAuth';
import './Header.css';

/**
 * Header component — displays the top navigation bar
 * with user profile, notifications, and search.
 *
 * @param {Object} props
 * @param {string} props.title - Current page title
 * @param {Function} props.onMenuToggle - Sidebar toggle handler
 */
export default function Header({ title, onMenuToggle }) {
  const { user, logout } = useAuth();

  return (
    <header className="app-header">
      <button className="menu-toggle" onClick={onMenuToggle} aria-label="Toggle navigation">
        ☰
      </button>
      <h1 className="page-title">{title}</h1>
      <div className="header-actions">
        <input type="search" placeholder="Search analytics..." className="search-bar" />
        <button className="icon-btn" aria-label="Notifications">
          <span className="badge">3</span>
          🔔
        </button>
        <div className="user-pill">
          <span className="user-avatar">{user?.name ? user.name[0] : 'U'}</span>
          <span className="user-name">{user?.name || 'Guest'}</span>
          <button onClick={logout} className="logout-btn">Exit</button>
        </div>
      </div>
    </header>
  );
}`,
  'src/utils/api.js': `/**
 * API utility — centralises HTTP requests with
 * error handling, auth headers, and base URL config.
 *
 * TODO: Replace hardcoded URL with environment config.
 */
const BASE_URL = import.meta.env.VITE_API_URL || 'https://api.example.com/v1';

async function request(endpoint, options = {}) {
  const token = localStorage.getItem('auth_token');
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: \`Bearer \${token}\` } : {}),
    ...options.headers,
  };

  const response = await fetch(\`\${BASE_URL}\${endpoint}\`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.message || \`HTTP error! status: \${response.status}\`);
  }

  return response.json();
}

export const api = {
  get: (endpoint) => request(endpoint, { method: 'GET' }),
  post: (endpoint, body) => request(endpoint, { method: 'POST', body: JSON.stringify(body) }),
  put: (endpoint, body) => request(endpoint, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (endpoint) => request(endpoint, { method: 'DELETE' }),
};`,
  'src/hooks/useAuth.js': `import React, { useState, useContext, createContext, useCallback } from 'react';

/**
 * Authentication Context & Hook
 * Provides session lifecycle: login, logout, and token refresh.
 */
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState({ name: 'Alex Rivera', role: 'admin' });
  const [loading, setLoading] = useState(false);

  const login = useCallback(async (credentials) => {
    setLoading(true);
    // Simulated token exchange
    await new Promise((r) => setTimeout(r, 800));
    setUser({ name: 'Alex Rivera', role: 'admin' });
    setLoading(false);
  }, []);

  const logout = useCallback(() => {
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}`,
  'src/components/Chart.jsx': `import React from 'react';

/**
 * SVG-based Chart Component
 * Renders time-series telemetry trends with gradient fills.
 */
export default function Chart({ data = [20, 45, 28, 80, 99, 43, 65] }) {
  const max = Math.max(...data);
  const points = data
    .map((val, idx) => \`\${(idx / (data.length - 1)) * 300},\${120 - (val / max) * 100}\`)
    .join(' ');

  return (
    <div className="chart-container">
      <svg viewBox="0 0 300 130" className="chart-svg">
        <defs>
          <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#FFAD66" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#F47B45" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        <polyline
          fill="none"
          stroke="#FFAD66"
          strokeWidth="3"
          points={points}
        />
      </svg>
    </div>
  );
}`,
  'src/pages/Dashboard.jsx': `import React from 'react';
import Chart from '../components/Chart';
import DataTable from '../components/DataTable';
import MetricCard from '../components/MetricCard';

export default function Dashboard() {
  return (
    <div className="dashboard-content">
      <div className="metrics-row">
        <MetricCard label="Total Requests" value="1.24M" change="+14.2%" />
        <MetricCard label="Avg Response Time" value="48ms" change="-6.1%" />
        <MetricCard label="Active Sessions" value="8,490" change="+22.8%" />
      </div>
      <div className="charts-section">
        <h2>Live Throughput</h2>
        <Chart />
      </div>
      <DataTable />
    </div>
  );
}`,
  'package.json': `{
  "name": "react-dashboard",
  "private": true,
  "version": "1.4.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "lint": "eslint ."
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.1.0",
    "lucide-react": "^0.460.0",
    "zustand": "^5.0.0"
  }
}`,
  'README.md': `# React Analytics Dashboard

A modern, responsive analytics dashboard designed for fast developer onboarding.

## Quickstart

\`\`\`bash
npm install
npm run dev
\`\`\`

## Architecture Highlights
- **State Management**: Zustand lightweight stores.
- **Routing**: React Router declarative routes.
- **Telemetry UI**: Custom SVG-driven sparklines & charts.
`,
};

export const sampleFileDetails = {
  'src/App.jsx': {
    purpose: 'Central application orchestrator that registers client routes, initializes top-level providers (AuthProvider), and mounts the main navigation shell.',
    importance: 'critical',
    dependencies: ['react-router-dom', 'Header', 'Sidebar', 'Dashboard', 'Analytics', 'Settings', 'useAuth'],
    dependents: ['main.jsx'],
    exports: ['App (default)'],
    complexity: 'medium',
    suggestions: [
      'Implement code splitting / React.lazy for route components to optimize bundle size',
      'Wrap routes in an ErrorBoundary for graceful fallback rendering',
    ],
  },
  'src/components/Header.jsx': {
    purpose: 'Main navigation header containing title display, global search, notification count bell, and user avatar session control.',
    importance: 'high',
    dependencies: ['useAuth hook', 'Header.css'],
    dependents: ['App.jsx'],
    exports: ['Header (default)'],
    complexity: 'medium',
    suggestions: [
      'Extract search bar into reusable SearchInput component',
      'Add keyboard trap and ARIA expanded attributes to user dropdown',
    ],
  },
  'src/utils/api.js': {
    purpose: 'Standardized HTTP fetch wrapper handling base URL configuration, JWT Authorization header injection, and consistent HTTP error normalization.',
    importance: 'critical',
    dependencies: ['Fetch API', 'localStorage (auth token)'],
    dependents: ['useAuth.js', 'useData.js', 'Dashboard.jsx', 'Analytics.jsx'],
    exports: ['api.get', 'api.post', 'api.put', 'api.delete'],
    complexity: 'low',
    suggestions: [
      'Add automatic 401 token refresh interceptor',
      'Include exponential backoff retry for network timeouts',
    ],
  },
  'src/hooks/useAuth.js': {
    purpose: 'React context provider and consumer hook managing user authentication state, credentials persistence, and session lifecycle.',
    importance: 'critical',
    dependencies: ['React Context API', 'useState', 'useCallback'],
    dependents: ['App.jsx', 'Header.jsx', 'Settings.jsx'],
    exports: ['AuthProvider', 'useAuth'],
    complexity: 'medium',
    suggestions: [
      'Migrate token storage from plain localStorage to HttpOnly cookie backend session',
      'Implement inactivity session timeout',
    ],
  },
  'src/components/Chart.jsx': {
    purpose: 'Lightweight SVG chart renderer utilizing cubic polyline coordinates and cyan linear gradients for trend visualization.',
    importance: 'medium',
    dependencies: ['SVG standards', 'React'],
    dependents: ['Dashboard.jsx', 'Analytics.jsx'],
    exports: ['Chart (default)'],
    complexity: 'medium',
    suggestions: [
      'Add animated SVG dasharray entrance transition',
      'Add hover tooltip support for exact coordinate inspection',
    ],
  },
  'src/pages/Dashboard.jsx': {
    purpose: 'Primary landing view aggregating system metrics, recent performance charts, and tabular transaction records.',
    importance: 'high',
    dependencies: ['Chart.jsx', 'DataTable.jsx', 'MetricCard.jsx'],
    dependents: ['App.jsx'],
    exports: ['Dashboard (default)'],
    complexity: 'medium',
    suggestions: [
      'Add pull-to-refresh / polling interval toggle',
      'Support customizable widget reordering',
    ],
  },
  'package.json': {
    purpose: 'Manifest declaring runtime dependencies (React, React Router, Lucide Icons) and build tooling scripts.',
    importance: 'high',
    dependencies: ['NPM ecosystem'],
    dependents: ['Project build pipelines'],
    exports: ['Project metadata'],
    complexity: 'low',
    suggestions: [
      'Keep dependency versions locked via package-lock.json',
      'Audit bundle size using rollup-plugin-visualizer',
    ],
  },
  'README.md': {
    purpose: 'Primary developer onboarding document providing architectural philosophy, installation commands, and system prerequisites.',
    importance: 'medium',
    dependencies: ['Markdown'],
    dependents: ['New developer onboarding'],
    exports: ['Documentation'],
    complexity: 'low',
    suggestions: [
      'Add architecture flow diagram link',
      'Document environment variable configurations (.env.example)',
    ],
  },
};

export const sampleModuleRelationships = [
  { from: 'App.jsx', to: 'Header.jsx', label: 'renders' },
  { from: 'App.jsx', to: 'Sidebar.jsx', label: 'renders' },
  { from: 'App.jsx', to: 'Dashboard.jsx', label: 'routes to' },
  { from: 'App.jsx', to: 'Analytics.jsx', label: 'routes to' },
  { from: 'App.jsx', to: 'useAuth.js', label: 'wraps with' },
  { from: 'Dashboard.jsx', to: 'Chart.jsx', label: 'embeds' },
  { from: 'Dashboard.jsx', to: 'DataTable.jsx', label: 'embeds' },
  { from: 'Header.jsx', to: 'useAuth.js', label: 'consumes' },
  { from: 'useAuth.js', to: 'api.js', label: 'invokes' },
  { from: 'useData.js', to: 'api.js', label: 'queries' },
  { from: 'Analytics.jsx', to: 'Chart.jsx', label: 'embeds' },
];

export const sampleOnboardingTasks = [
  { id: 't1', title: 'Understand overall project structure & entrypoint', status: 'completed', difficulty: 'easy', category: 'Architecture' },
  { id: 't2', title: 'Review authentication lifecycle in useAuth hook', status: 'completed', difficulty: 'medium', category: 'Security' },
  { id: 't3', title: 'Trace request flow through api.js utility layer', status: 'in-progress', difficulty: 'easy', category: 'Networking' },
  { id: 't4', title: 'Inspect Dashboard telemetry and SVG chart calculations', status: 'pending', difficulty: 'medium', category: 'UI Components' },
  { id: 't5', title: 'Examine module dependency relationships in Explorer', status: 'pending', difficulty: 'easy', category: 'Exploration' },
  { id: 't6', title: 'Formulate your first codebase PR or feature branch', status: 'pending', difficulty: 'hard', category: 'Contribution' },
];

export const sampleAnalysisSteps = [
  { id: 1, label: 'Validating GitHub repository access', duration: 900 },
  { id: 2, label: 'Cloning tree structure & metadata', duration: 1400 },
  { id: 3, label: 'Parsing file ASTs & syntax nodes', duration: 1600 },
  { id: 4, label: 'Mapping module imports & dependencies', duration: 2000 },
  { id: 5, label: 'Extracting functions, classes & components', duration: 1800 },
  { id: 6, label: 'Generating onboarding roadmap & architecture digest', duration: 1300 },
];

export const dashboardStats = {
  connectedRepos: 3,
  analyzedRepos: 1,
  importantModules: 18,
  onboardingTasks: 6,
};
