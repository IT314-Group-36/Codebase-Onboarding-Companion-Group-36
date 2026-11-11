/**
 * CODEVERSE — API Client Layer
 *
 * Connects frontend views to the FastAPI backend at /api (proxied to http://localhost:8000).
 * Handles response normalization, robust error extraction for FastAPI Pydantic details,
 * and data adaptation.
 */

import {
  adaptRepository,
  buildFileTree,
  adaptFileDetails,
  generateOnboardingTasks,
  saveTaskStatus,
  adaptUser,
} from './adapters';
import { parseGitHubUrl, isValidBranch } from '../utils/github';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

/**
 * Extracts a readable error message from a FastAPI response
 */
async function parseError(response) {
  let detailMessage = '';
  let code = null;
  try {
    const errorBody = await response.json();
    if (errorBody && errorBody.detail) {
      if (typeof errorBody.detail === 'string') {
        detailMessage = errorBody.detail;
      } else if (Array.isArray(errorBody.detail)) {
        // Pydantic validation error list
        detailMessage = errorBody.detail
          .map((err) => `${err.loc ? err.loc.join('.') + ': ' : ''}${err.msg || 'Invalid field'}`)
          .join('; ');
      } else if (typeof errorBody.detail === 'object') {
        code = errorBody.detail.code || null;
        detailMessage =
          errorBody.detail.message || JSON.stringify(errorBody.detail);
      }
    } else if (errorBody && errorBody.message) {
      detailMessage = errorBody.message;
    }
  } catch {
    // If not JSON, try text
    detailMessage = await response.text().catch(() => '');
  }

  const fallbacks = {
    401: 'Your session has expired. Please sign in with GitHub again.',
    409: 'Repository is not ready for this operation or indexing is already in progress (HTTP 409).',
    404: 'Requested resource not found (HTTP 404).',
    422: 'Invalid request payload or URL format (HTTP 422).',
    429: 'GitHub rate limit reached. Please try again in a few minutes.',
    503: 'LLM is not configured on the backend (LLM_API_KEY). Code search, file explorer, and dependency maps are available without it.',
    502: 'The backend AI provider call failed (rate limit or timeout).',
  };
  const message =
    detailMessage ||
    fallbacks[response.status] ||
    `Backend request failed: ${response.status} ${response.statusText}`;

  // `status` and `code` let callers react (e.g. code "github_reauth_required" means: sign in with GitHub again)
  const error = new Error(message);
  error.status = response.status;
  error.code = code;
  return error;
}

/**
 * Core HTTP fetch wrapper
 */
export async function request(endpoint, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  const url = `${BASE_URL}${endpoint}`;

  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
      credentials: 'include', // send the session cookie
    });
  } catch (err) {
    throw new Error(
      `Unable to communicate with backend server at ${BASE_URL}. Ensure FastAPI is running on http://localhost:8000 (${err.message})`,
      { cause: err }
    );
  }

  if (!response.ok) {
    const error = await parseError(response);
    // Signed out (or the session expired): let the app send the user back to the login page.
    if (response.status === 401 && !endpoint.startsWith('/auth/')) {
      window.dispatchEvent(new Event('auth:expired'));
    }
    throw error;
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return null;
  }

  return response.json();
}

// ============================================
// HEALTH CHECK
// ============================================
export async function checkHealth() {
  return request('/health');
}

// ============================================
// AUTHENTICATION (GitHub OAuth, session cookie)
// ============================================
// The backend signs the user in with GitHub and keeps the session in an HttpOnly cookie,
// so the frontend never sees the GitHub token.

/** Whether the backend has GitHub sign-in configured. GET /auth/config */
export async function getAuthConfig() {
  try {
    return await request('/auth/config');
  } catch {
    return { github_login_enabled: false };
  }
}

/** Sends the browser to GitHub (full-page redirect). GET /auth/github/login */
export function loginWithGitHub() {
  window.location.assign(`${BASE_URL}/auth/github/login`);
}

/** POST /auth/logout: clears the session cookie. */
export async function logout() {
  await request('/auth/logout', { method: 'POST' });
  return { success: true };
}

/** The signed-in user. GET /auth/me (rejects with status 401 when signed out) */
export async function getUserProfile() {
  const raw = await request('/auth/me');
  return { success: true, user: adaptUser(raw) };
}

// ============================================
// REPOSITORIES
// ============================================

/**
 * Registers a new GitHub repository for indexing
 * POST /repos -> 202 Accepted
 */
export async function connectRepository(url, branch = '', accessToken = null) {
  // Same rules as the backend: https://github.com/<owner>/<repo> only
  const parsed = parseGitHubUrl(url);
  if (!parsed) {
    return {
      success: false,
      error:
        'Invalid GitHub URL. Must be in the format: https://github.com/owner/repository',
    };
  }
  if (!isValidBranch(branch)) {
    return { success: false, error: 'Invalid branch name.' };
  }

  try {
    const rawRepo = await request('/repos', {
      method: 'POST',
      body: JSON.stringify({
        url: parsed.url,
        branch: (branch || '').trim(),
        access_token: accessToken ? accessToken.trim() : null,
      }),
    });

    const adapted = adaptRepository(rawRepo);
    return {
      success: true,
      repository: adapted,
      raw: rawRepo,
    };
  } catch (err) {
    return {
      success: false,
      error: err.message,
    };
  }
}

/**
 * Lists all registered repositories from backend
 * GET /repos
 */
export async function getRepositories() {
  const rawList = await request('/repos');
  const adapted = (rawList || []).map(adaptRepository);
  return {
    success: true,
    repositories: adapted,
    raw: rawList,
  };
}

/**
 * Fetches repository detail by ID
 * GET /repos/{repo_id}
 */
export async function getRepositoryById(repoId) {
  const numericId = parseInt(repoId, 10);
  const targetId = Number.isNaN(numericId) ? repoId : numericId;

  const rawRepo = await request(`/repos/${encodeURIComponent(targetId)}`);
  const adapted = adaptRepository(rawRepo);
  return {
    success: true,
    repository: adapted,
    raw: rawRepo,
  };
}

/**
 * Reindexes an existing repository
 * POST /repos/{repo_id}/reindex
 */
export async function reindexRepository(repoId, accessToken = null) {
  const numericId = parseInt(repoId, 10);
  const targetId = Number.isNaN(numericId) ? repoId : numericId;

  const rawRepo = await request(`/repos/${encodeURIComponent(targetId)}/reindex`, {
    method: 'POST',
    body: JSON.stringify({
      access_token: accessToken ? accessToken.trim() : null,
    }),
  });
  return {
    success: true,
    repository: adaptRepository(rawRepo),
    raw: rawRepo,
  };
}

/**
 * Removes repository from frontend tracking
 * Note: Backend does not expose a DELETE endpoint.
 */
export async function disconnectRepository(repoId) {
  return {
    success: true,
    id: repoId,
    note: 'Removed from local frontend session. Backend repository records remain preserved.',
  };
}

// ============================================
// GITHUB (repo picker and branch list for the connect page)
// ============================================

/**
 * One page of the repositories the signed-in user can read on GitHub (public and private).
 * GET /github/repos. Rejects with error.code === 'github_reauth_required' when the GitHub sign-in must be refreshed.
 */
export async function listGitHubRepos({ page = 1, perPage = 30 } = {}) {
  const res = await request(`/github/repos?page=${page}&per_page=${perPage}`);
  return {
    repos: res.repos || [],
    page: res.page || page,
    hasMore: Boolean(res.has_more),
  };
}

/**
 * Real branches of one repository ("owner/name"). GET /github/branches
 */
export async function listGitHubBranches(fullName) {
  const res = await request(`/github/branches?repo=${encodeURIComponent(fullName)}`);
  return {
    defaultBranch: res.default_branch || null,
    branches: res.branches || [],
    truncated: Boolean(res.truncated),
  };
}

// ============================================
// EXPLORER & FILES
// ============================================

/**
 * Fetches flat file list from backend and builds hierarchical folder tree
 * GET /repos/{repo_id}/files
 */
export async function getFileTree(repoId) {
  const numericId = parseInt(repoId, 10);
  const targetId = Number.isNaN(numericId) ? repoId : numericId;

  const rawFiles = await request(`/repos/${encodeURIComponent(targetId)}/files`);
  const tree = buildFileTree(rawFiles);
  return {
    success: true,
    tree,
    files: rawFiles,
  };
}

/**
 * Fetches detailed symbols and import relationships for a single file
 * GET /repos/{repo_id}/files/{path}
 */
export async function getFileDetails(repoId, filePath) {
  const numericId = parseInt(repoId, 10);
  const targetId = Number.isNaN(numericId) ? repoId : numericId;

  // Preserve path slashes while encoding special characters
  const encodedPath = filePath
    .split('/')
    .map(encodeURIComponent)
    .join('/');

  const raw = await request(`/repos/${encodeURIComponent(targetId)}/files/${encodedPath}`);
  const details = adaptFileDetails(raw, filePath);
  return {
    success: true,
    details,
    raw,
  };
}

/**
 * File source code content retrieval notice
 * Backend does not retain complete source files after AST parsing (safe_rmtree).
 */
export async function getFileContent(repoId, filePath) {
  // Check if we can get indexed chunks for this file
  try {
    const hits = await searchCode(repoId, filePath, 5);
    const fileHits = (hits.hits || []).filter((h) => h.file_path === filePath);

    if (fileHits.length > 0) {
      const code = fileHits
        .sort((a, b) => a.start_line - b.start_line)
        .map(
          (h) =>
            `// --- Lines ${h.start_line}-${h.end_line} (from indexed AST chunk) ---\n${h.content}`
        )
        .join('\n\n');
      return { success: true, content: code, isPartial: true };
    }
  } catch {
    // ignore search failure
  }

  const notice = `// =========================================================================
// Source File: ${filePath}
//
// NOTE: Complete raw file blobs are not stored in the backend database.
// To conserve disk and avoid retaining external codebases, the backend AST
// worker extracts symbols, dependency edges, and semantic vector chunks,
// then purges the temporary git clone directory.
//
// See the right panel for extracted symbols, signatures, and imports.
// =========================================================================`;
  return { success: true, content: notice, isPartial: true };
}

/**
 * Searches symbols by query string
 * GET /repos/{repo_id}/symbols?q={query}&limit={limit}
 */
export async function searchSymbols(repoId, query, limit = 20) {
  const numericId = parseInt(repoId, 10);
  const targetId = Number.isNaN(numericId) ? repoId : numericId;

  const symbols = await request(
    `/repos/${encodeURIComponent(targetId)}/symbols?q=${encodeURIComponent(query)}&limit=${limit}`
  );
  return {
    success: true,
    symbols: symbols || [],
  };
}

// ============================================
// PLAIN-ENGLISH EXPLANATIONS
// ============================================

/**
 * Normalizes GET /explain. `explanation` is null when the backend has no LLM key
 * (the relationship sentence and lists are still returned, they come from the import/call graphs).
 */
function adaptExplanation(raw) {
  return {
    success: true,
    kind: raw.kind,
    target: raw.target,
    name: raw.qualname || raw.path || raw.target,
    module: raw.module || null,
    relationshipSummary: raw.relationship_summary || '',
    relationships: raw.relationships || {},
    explanation: raw.explanation || null,
    source: raw.source || 'none', // 'llm' | 'cache' | 'none'
    warnings: raw.warnings || [],
    caveat: raw.caveat || '',
    raw,
  };
}

async function fetchExplanation(repoId, param, value, refresh) {
  const numericId = parseInt(repoId, 10);
  const targetId = Number.isNaN(numericId) ? repoId : numericId;
  const params = new URLSearchParams({ [param]: value });
  if (refresh) params.set('refresh', 'true');
  const raw = await request(`/repos/${encodeURIComponent(targetId)}/explain?${params.toString()}`);
  return adaptExplanation(raw);
}

/**
 * Beginner-friendly explanation of one file + "this file uses X and is used by Y"
 * GET /repos/{repo_id}/explain?file={path}
 */
export async function getFileExplanation(repoId, filePath, { refresh = false } = {}) {
  return fetchExplanation(repoId, 'file', filePath, refresh);
}

/**
 * Beginner-friendly explanation of one function/class/method + what it calls and who calls it
 * GET /repos/{repo_id}/explain?symbol={uid or name}
 */
export async function getSymbolExplanation(repoId, symbol, { refresh = false } = {}) {
  return fetchExplanation(repoId, 'symbol', symbol, refresh);
}

// ============================================
// DEPENDENCY MAP
// ============================================

/**
 * Fetches module map and module-to-module graph for React Flow visualization
 * GET /repos/{repo_id}/map
 */
export async function getDependencyGraph(repoId) {
  const numericId = parseInt(repoId, 10);
  const targetId = Number.isNaN(numericId) ? repoId : numericId;

  const rawMap = await request(`/repos/${encodeURIComponent(targetId)}/map`);
  return {
    success: true,
    projectSummary: rawMap.project_summary,
    modules: rawMap.modules || [],
    entryPoints: rawMap.entry_points || [],
    graph: rawMap.graph || { nodes: [], edges: [] },
    techStack: rawMap.tech_stack || {},
    raw: rawMap,
  };
}

// ============================================
// SEARCH & Q&A
// ============================================

/**
 * Hybrid vector + keyword search over code chunks (No LLM required)
 * POST /repos/{repo_id}/search
 */
export async function searchCode(repoId, query, k = 8) {
  const numericId = parseInt(repoId, 10);
  const targetId = Number.isNaN(numericId) ? repoId : numericId;

  const res = await request(`/repos/${encodeURIComponent(targetId)}/search`, {
    method: 'POST',
    body: JSON.stringify({ query, k }),
  });
  return {
    success: true,
    hits: res.hits || [],
  };
}

/**
 * Adapts a backend "impact report" (shared by /ask and /impact) to camelCase fields used by the UI.
 */
function adaptImpactReport(r) {
  if (!r) return null;
  return {
    target: r.target,
    targetInfo: r.target_info || {},
    depth: r.depth,
    totals: r.totals || { symbols: 0, files: 0, tests: 0 },
    affectedSymbols: r.affected_symbols || [],
    affectedFiles: r.affected_files || [],
    affectedTests: r.affected_tests || [],
    dependencies: r.dependencies || { calls: [], imports: [] },
    summary: r.summary || '',
  };
}

/**
 * Grounded AI Q&A over codebase with citations.
 * "What would break if I change X?" style questions come back with intent "impact" and a structured report;
 * when the question is ambiguous the backend returns needsClarification + candidates instead of guessing.
 * Optional hints ({ symbol, file, depth }) pin the target, e.g. after the user picks a candidate.
 * POST /repos/{repo_id}/ask
 */
export async function askCodebaseQuestion(repoId, question, hints = {}) {
  const numericId = parseInt(repoId, 10);
  const targetId = Number.isNaN(numericId) ? repoId : numericId;

  const body = { question };
  if (hints.symbol) body.symbol = hints.symbol;
  if (hints.file) body.file = hints.file;
  if (hints.depth) body.depth = hints.depth;

  const res = await request(`/repos/${encodeURIComponent(targetId)}/ask`, {
    method: 'POST',
    body: JSON.stringify(body),
  });

  const citations = res.citations || [];
  const impact = adaptImpactReport(res.impact);
  const referencedFiles = Array.from(
    new Set(citations.map((c) => c.path).concat((res.sources || []).map((s) => s.file_path)))
  ).filter(Boolean);

  return {
    success: true,
    answer: res.answer,
    intent: res.intent || 'question',
    citations,
    sources: res.sources || [],
    referencedFiles,
    impact,
    needsClarification: Boolean(res.needs_clarification),
    candidates: res.candidates || [],
    warnings: res.warnings || [],
    caveat: res.caveat || '',
    raw: res,
  };
}

// ============================================
// IMPACT ANALYSIS
// ============================================

/**
 * Reverse dependency blast-radius analysis via NetworkX
 * GET /repos/{repo_id}/impact?symbol={uid}&file={path}&depth={depth}&explain={explain}
 */
export async function getImpactAnalysis(repoId, { symbol, file, depth = 3, explain = false } = {}) {
  const numericId = parseInt(repoId, 10);
  const targetId = Number.isNaN(numericId) ? repoId : numericId;

  const params = new URLSearchParams();
  if (symbol) params.set('symbol', symbol);
  if (file) params.set('file', file);
  params.set('depth', String(depth));
  if (explain) params.set('explain', 'true');

  const res = await request(
    `/repos/${encodeURIComponent(targetId)}/impact?${params.toString()}`
  );
  return {
    success: true,
    target: res.target,
    depth: res.depth,
    affectedSymbols: res.affected_symbols || [],
    affectedFiles: res.affected_files || [],
    caveat: res.caveat,
    explanation: res.explanation,
    // Fields added for natural-language impact answers (absent on older backends, so always default them)
    report: adaptImpactReport(res),
    raw: res,
  };
}

// ============================================
// ONBOARDING
// ============================================

/**
 * Generates dynamic onboarding roadmap tasks from repository summary & module map
 */
export async function getOnboardingTasks(repoId) {
  const repoRes = await getRepositoryById(repoId);
  if (!repoRes.success || !repoRes.repository) {
    throw new Error('Repository not found for onboarding quests.');
  }

  const tasks = generateOnboardingTasks(repoRes.repository);
  return {
    success: true,
    tasks,
  };
}

/**
 * Updates task status in localStorage
 */
export async function updateOnboardingTask(repoId, taskId, status) {
  saveTaskStatus(repoId, taskId, status);
  return { success: true, taskId, status };
}
