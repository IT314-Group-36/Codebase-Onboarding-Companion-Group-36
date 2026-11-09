/**
 * CODEVERSE — Backend Data Adapters
 *
 * Transforms raw FastAPI backend responses into strongly-typed frontend models
 * compatible with existing UI components, preserving all Dark Aurora layouts,
 * status badges, graph visualizers, and metric cards.
 */

/**
 * Format bytes into human-readable string (e.g. 1.2 KB, 450 B)
 */
export function formatBytes(bytes = 0) {
  if (bytes === 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Maps backend status strings to frontend badge statuses
 * Backend: 'queued' | 'indexing' | 'ready' | 'failed'
 * Frontend: 'pending' | 'analyzing' | 'analyzed' | 'error'
 */
export function mapBackendStatus(backendStatus = '') {
  switch (backendStatus) {
    case 'queued':
      return 'pending';
    case 'indexing':
      return 'analyzing';
    case 'ready':
      return 'analyzed';
    case 'failed':
      return 'error';
    default:
      return 'pending';
  }
}

/**
 * Parses and formats indexing errors from the backend into human-readable details.
 * Strips raw PostgreSQL tracebacks, SQL statements, and internal parameters,
 * extracting the core failure reason, advisory guidance, and any referenced file.
 *
 * @param {string} rawError - The raw error string from the backend
 * @returns {{
 *   title: string,
 *   message: string,
 *   failingFile: string | null,
 *   isRetryable: boolean,
 *   advisory: string | null,
 *   technicalDetails: string | null
 * }}
 */
export function parseIndexingError(rawError) {
  if (!rawError || typeof rawError !== 'string') {
    return {
      title: 'Indexing Failed',
      message: 'Indexing encountered an unexpected error during background processing.',
      failingFile: null,
      isRetryable: true,
      advisory: null,
      technicalDetails: null,
    };
  }

  const clean = rawError.trim();

  // 1. PostgreSQL NUL (0x00) byte error (psycopg.DataError)
  if (clean.includes('NUL (0x00)') || clean.includes('cannot contain NUL') || clean.includes('0x00')) {
    const fileMatch =
      clean.match(/['"]file_path['"]\s*:\s*['"]([^'"]+)['"]/) ||
      clean.match(/file_path[:=]\s*['"]?([^\s,'"\]]+)/) ||
      clean.match(/([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)/);

    const failingFile = fileMatch ? fileMatch[1] : null;

    return {
      title: 'Invalid File Encoding (NUL Bytes)',
      message:
        'PostgreSQL cannot store text containing NUL (0x00) bytes. One of the repository files contains null or binary characters that cannot be stored.',
      failingFile,
      isRetryable: true,
      advisory: failingFile
        ? `The failure occurred in '${failingFile}'. Retrying will re-fetch this file and fail again unless the file is cleaned or excluded upstream on GitHub.`
        : 'Retrying without changes to upstream files containing null bytes will likely produce the same error.',
      technicalDetails: clean,
    };
  }

  // 2. Git Clone: branch not found
  if (clean.includes('Remote branch') && (clean.includes('not found') || clean.includes('Could not find'))) {
    const branchMatch = clean.match(/Remote branch ([^\s]+) not found/) || clean.match(/branch ([^\s]+)/);
    const branchName = branchMatch ? branchMatch[1] : 'specified branch';
    return {
      title: 'Remote Branch Not Found',
      message: `The branch '${branchName}' does not exist in this GitHub repository. Please verify the branch name.`,
      failingFile: null,
      isRetryable: false,
      advisory: 'Select an existing remote branch (e.g. main, master) from the branch selector before trying again.',
      technicalDetails: clean,
    };
  }

  // 3. Git Clone: private repo / authentication
  if (clean.includes('Could not clone the repo') || clean.includes('Authentication failed') || clean.includes('terminal prompts disabled')) {
    return {
      title: 'Repository Access Restricted',
      message: clean.includes('Sign in with GitHub again')
        ? 'GitHub rejected your saved sign-in. Sign in with GitHub again, then retry.'
        : 'Could not clone repository. If it is private, make sure your GitHub account can access it (for an organization repo, an owner may need to approve this app), or provide a Personal Access Token.',
      failingFile: null,
      isRetryable: true,
      advisory: clean.includes('Sign in with GitHub again')
        ? 'Sign out, then choose Continue with GitHub to refresh your access.'
        : 'Private repositories your GitHub account can access are cloned automatically. Otherwise provide a Personal Access Token with repository read permission.',
      technicalDetails: clean,
    };
  }

  // 4. No embeddable code files
  if (clean.includes('No embeddable text files found')) {
    return {
      title: 'No Indexable Code Files',
      message: 'No supported source code or text files were found in this repository branch.',
      failingFile: null,
      isRetryable: false,
      advisory: 'The repository might contain only binary assets or unsupported file formats.',
      technicalDetails: clean,
    };
  }

  // 5. Generic PostgreSQL / SQLAlchemy error
  if (clean.includes('[SQL:') || clean.includes('psycopg.') || clean.includes('sqlalchemy.')) {
    const sqlIndex = clean.indexOf('[SQL:');
    let firstPart = sqlIndex > -1 ? clean.slice(0, sqlIndex).trim() : clean;
    firstPart = firstPart.replace(/^\([a-zA-Z0-9_.]+\)\s*/, '');

    const fileMatch = clean.match(/['"]file_path['"]\s*:\s*['"]([^'"]+)['"]/);
    const failingFile = fileMatch ? fileMatch[1] : null;

    return {
      title: 'Database Storage Error',
      message: firstPart || 'Database rejected an index record during ingestion.',
      failingFile,
      isRetryable: true,
      advisory: failingFile ? `Related file: ${failingFile}` : null,
      technicalDetails: clean,
    };
  }

  // 6. Generic clean error
  const firstLine = clean.split('\n')[0].slice(0, 250);
  return {
    title: 'Indexing Failed',
    message: firstLine || 'Background indexing encountered an error in the worker process.',
    failingFile: null,
    isRetryable: true,
    advisory: null,
    technicalDetails: clean,
  };
}

/**
 * Adapts a backend Repository / RepoDetail object into frontend shape
 */
export function adaptRepository(raw) {
  if (!raw) return null;

  const id = String(raw.id);
  const cleanUrl = (raw.url || '').trim().replace(/\.git$/, '');
  const urlParts = cleanUrl.split('/').filter(Boolean);
  const owner = urlParts.length >= 2 ? urlParts[urlParts.length - 2] : 'github';
  const name = urlParts.length >= 1 ? urlParts[urlParts.length - 1] : `repo-${id}`;
  const fullName = `${owner}/${name}`;

  const techStack = raw.tech_stack || {};
  const summary = raw.summary || {};
  const indexReport = raw.index_report || {};
  const moduleMap = raw.module_map || {};

  // Compute language distribution percentages
  const langCounts = techStack.language_file_counts || {};
  const totalLangFiles = Object.values(langCounts).reduce((acc, count) => acc + count, 0);

  const languages = {};
  if (totalLangFiles > 0) {
    for (const [lang, count] of Object.entries(langCounts)) {
      languages[lang] = Math.round((count / totalLangFiles) * 100);
    }
  } else if (Array.isArray(techStack.languages) && techStack.languages.length > 0) {
    const share = Math.round(100 / techStack.languages.length);
    techStack.languages.forEach((l) => {
      languages[l] = share;
    });
  } else {
    languages.Unknown = 100;
  }

  const primaryLanguage =
    techStack.languages?.[0] || Object.keys(languages)[0] || 'Unknown';

  // Extract combined technologies list (frameworks + package managers + languages)
  const technologies = Array.from(
    new Set([
      ...(techStack.frameworks || []),
      ...(techStack.package_managers || []),
      ...(techStack.languages || []),
    ])
  );

  const defaultFile =
    moduleMap.entry_points?.[0]?.path ||
    summary.key_files?.[0] ||
    '';

  return {
    id,
    numericId: raw.id,
    name,
    owner,
    fullName,
    url: raw.url,
    branch: raw.branch || 'main',
    branches: [raw.branch || 'main'],
    status: mapBackendStatus(raw.status),
    rawStatus: raw.status,
    stage: raw.stage || null,
    error: raw.error || null,
    parsedError: raw.error ? parseIndexingError(raw.error) : null,
    commitSha: raw.commit_sha || null,
    warnings: raw.warnings || [],
    description:
      summary.one_line ||
      summary.description ||
      (raw.status === 'indexing'
        ? `Indexing in progress (stage: ${raw.stage || 'queued'})...`
        : 'Repository connected and indexed via Codeverse AST engine.'),
    language: primaryLanguage,
    languages,
    technologies: technologies.length > 0 ? technologies : [primaryLanguage],
    stars: 0,
    forks: 0,
    connectedAt: raw.created_at || new Date().toISOString(),
    analyzedAt: raw.status === 'ready' ? raw.updated_at || raw.created_at : null,
    stats: {
      files: indexReport.files ?? 0,
      modules: moduleMap.modules?.length ?? 0,
      functions: indexReport.symbols ?? 0,
      components: indexReport.call_edges ?? indexReport.import_edges ?? 0,
      importEdges: indexReport.import_edges ?? 0,
      chunks: indexReport.chunks ?? 0,
      secretsRedacted: indexReport.secrets_redacted ?? 0,
    },
    defaultFile,
    summary,
    moduleMap,
    indexReport,
    techStack,
    raw,
  };
}

/**
 * Transforms flat array of backend FileOut items:
 * [{ path, language, size, sensitive }]
 * into a hierarchical directory tree for ExplorerPage:
 * [{ id, name, type: 'folder', children: [...] }, { id, name, type: 'file', ... }]
 */
export function buildFileTree(files = []) {
  if (!Array.isArray(files) || files.length === 0) {
    return [];
  }

  const rootNodes = [];
  const folderMap = new Map();

  files.forEach((file) => {
    const pathParts = file.path.split('/');
    let currentPath = '';

    for (let i = 0; i < pathParts.length; i++) {
      const part = pathParts[i];
      const isFile = i === pathParts.length - 1;
      const prevPath = currentPath;
      currentPath = currentPath ? `${currentPath}/${part}` : part;

      if (isFile) {
        const fileNode = {
          id: file.path,
          name: part,
          type: 'file',
          path: file.path,
          language: file.language || part.split('.').pop() || 'text',
          size: formatBytes(file.size || 0),
          rawSize: file.size || 0,
          sensitive: Boolean(file.sensitive),
        };

        if (prevPath && folderMap.has(prevPath)) {
          folderMap.get(prevPath).children.push(fileNode);
        } else {
          rootNodes.push(fileNode);
        }
      } else {
        if (!folderMap.has(currentPath)) {
          const folderNode = {
            id: currentPath,
            name: part,
            type: 'folder',
            path: currentPath,
            children: [],
          };
          folderMap.set(currentPath, folderNode);

          if (prevPath && folderMap.has(prevPath)) {
            folderMap.get(prevPath).children.push(folderNode);
          } else {
            rootNodes.push(folderNode);
          }
        }
      }
    }
  });

  // Sort folders first, then alphabetical
  function sortTree(nodes) {
    nodes.sort((a, b) => {
      if (a.type !== b.type) {
        return a.type === 'folder' ? -1 : 1;
      }
      return a.name.localeCompare(b.name);
    });
    nodes.forEach((node) => {
      if (node.children) {
        sortTree(node.children);
      }
    });
    return nodes;
  }

  return sortTree(rootNodes);
}

/**
 * Adapts backend GET /repos/{id}/files/{path} response into Explorer file details
 */
export function adaptFileDetails(raw, filePath, moduleMap = null) {
  if (!raw) return null;

  const file = raw.file || {};
  const symbols = raw.symbols || [];
  const imports = raw.imports || [];
  const importedBy = raw.imported_by || [];

  // Match module purpose if path falls within a mapped module
  let purpose = `Source file ${filePath} with ${symbols.length} detected symbols.`;
  if (moduleMap?.modules) {
    const match = moduleMap.modules.find(
      (m) => filePath === m.path || filePath.startsWith(`${m.path}/`)
    );
    if (match) {
      purpose = `${match.name}: ${match.purpose}`;
    }
  }

  // Calculate importance
  let importance = 'medium';
  if (
    importedBy.length >= 3 ||
    filePath.includes('App') ||
    filePath.includes('main') ||
    filePath.includes('index')
  ) {
    importance = 'critical';
  } else if (importedBy.length >= 1) {
    importance = 'high';
  }

  // Calculate complexity
  let complexity = 'low';
  if (symbols.length >= 12) {
    complexity = 'high';
  } else if (symbols.length >= 5) {
    complexity = 'medium';
  }

  // Contextual suggestions
  const suggestions = [];
  if (file.sensitive) {
    suggestions.push(
      'Flagged as containing sensitive configuration or credentials. Ensure secret redaction.'
    );
  }
  if (importedBy.length >= 4) {
    suggestions.push(
      `Central dependency for ${importedBy.length} modules. Perform impact analysis before altering signatures.`
    );
  }
  if (symbols.length > 15) {
    suggestions.push(
      'High symbol density. Consider refactoring or splitting into specialized cohesive modules.'
    );
  }
  if (suggestions.length === 0) {
    suggestions.push(
      'Inspect symbol signatures and import references for architectural context.'
    );
  }

  return {
    path: filePath,
    purpose,
    importance,
    complexity,
    dependencies: imports,
    dependents: importedBy,
    exports: symbols.map((s) => s.signature || s.qualname || s.name),
    symbols,
    sensitive: Boolean(file.sensitive),
    size: formatBytes(file.size || 0),
    language: file.language || 'text',
    suggestions,
  };
}

/**
 * Dynamically synthesizes real onboarding milestones from repository summary & module map
 * and merges completion state stored in localStorage
 */
export function generateOnboardingTasks(adaptedRepo) {
  if (!adaptedRepo) return [];

  const summary = adaptedRepo.summary || {};
  const moduleMap = adaptedRepo.moduleMap || {};
  const repoKey = `codeverse_tasks_${adaptedRepo.id}`;

  let savedState = {};
  try {
    const raw = localStorage.getItem(repoKey);
    if (raw) savedState = JSON.parse(raw);
  } catch {
    savedState = {};
  }

  const tasks = [];

  // 1. Architecture Overview Task
  tasks.push({
    id: 't-arch',
    title: `Understand Project Architecture: ${summary.title || adaptedRepo.name}`,
    category: 'Architecture',
    difficulty: 'easy',
    description:
      summary.description ||
      summary.architecture ||
      summary.one_line ||
      'Review high-level architectural design and primary layers.',
    targetFiles: summary.key_files || [adaptedRepo.defaultFile].filter(Boolean),
    checklist: [
      'Read repository architecture summary',
      'Check primary language and detected framework stack',
      'Review key entrypoints in the visual dependency map',
    ],
    estimatedMinutes: 10,
    status: savedState['t-arch'] || 'completed',
  });

  // 2. Entrypoints Task
  const entryPoints = moduleMap.entry_points || [];
  tasks.push({
    id: 't-entry',
    title: 'Trace Primary Application Entrypoints',
    category: 'Entrypoints',
    difficulty: 'easy',
    description:
      entryPoints.length > 0
        ? `Execution bootstraps at ${entryPoints.map((e) => e.path).join(', ')}: ${entryPoints[0].reason}`
        : 'Inspect how the project initializes and registers application routes or services.',
    targetFiles: entryPoints.map((e) => e.path),
    checklist: [
      'Trace main function or root component initialization',
      'Inspect imported configuration and state context wrappers',
      'Verify execution environment bootstrap commands',
    ],
    estimatedMinutes: 12,
    status: savedState['t-entry'] || 'in-progress',
  });

  // 3. Module Quests
  const modules = moduleMap.modules || [];
  modules.forEach((mod, idx) => {
    const taskId = `t-mod-${idx}`;
    tasks.push({
      id: taskId,
      title: `Explore Module: ${mod.name}`,
      category: 'Modules',
      difficulty: idx > 2 ? 'medium' : 'easy',
      description: mod.purpose || `Core module responsible for ${mod.name} logic.`,
      targetFiles: mod.key_files?.length > 0 ? mod.key_files : [mod.path],
      checklist: [
        `Locate module folder at ${mod.path}`,
        'Inspect declared symbols and exported interfaces',
        'Verify dependent callers in Dependency Map',
      ],
      estimatedMinutes: 15,
      status: savedState[taskId] || 'pending',
    });
  });

  // 4. Run & Build Instructions Task
  if (summary.how_to_run && summary.how_to_run !== 'n/a') {
    tasks.push({
      id: 't-run',
      title: 'Review Build, Test, & Execution Instructions',
      category: 'Setup',
      difficulty: 'medium',
      description: summary.how_to_run,
      targetFiles: summary.key_files || ['README.md', 'package.json'],
      checklist: [
        'Review prerequisite runtime dependencies',
        'Inspect build and test invocation scripts',
        'Verify local execution steps',
      ],
      estimatedMinutes: 15,
      status: savedState['t-run'] || 'pending',
    });
  }

  // 5. Dependency Flow Task
  tasks.push({
    id: 't-deps',
    title: 'Analyze Cross-Module Dependency Flow',
    category: 'Exploration',
    difficulty: 'medium',
    description:
      'Open the interactive Dependency Map to inspect module relationships and detect coupling.',
    targetFiles: [adaptedRepo.defaultFile].filter(Boolean),
    checklist: [
      'Inspect module-to-module directional edges',
      'Verify acyclic dependency flow',
      'Locate highest in-degree hub modules',
    ],
    estimatedMinutes: 20,
    status: savedState['t-deps'] || 'pending',
  });

  return tasks;
}

/**
 * Saves task status for a given repository to localStorage
 */
export function saveTaskStatus(repoId, taskId, status) {
  try {
    const repoKey = `codeverse_tasks_${repoId}`;
    const raw = localStorage.getItem(repoKey);
    const state = raw ? JSON.parse(raw) : {};
    state[taskId] = status;
    localStorage.setItem(repoKey, JSON.stringify(state));
  } catch (err) {
    console.error('Failed to save task status to localStorage:', err);
  }
}

/**
 * Maps GET /auth/me to the shape the UI uses.
 */
export function adaptUser(raw) {
  return {
    id: raw.id,
    name: raw.name || raw.login,
    email: raw.email || '',
    githubUsername: raw.login,
    avatarUrl: raw.avatar_url || null,
    githubConnected: Boolean(raw.github_connected),
    tokenScopes: raw.token_scopes || '',
  }
}
