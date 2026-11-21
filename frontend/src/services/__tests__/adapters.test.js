/**
 * White-box tests for services/adapters.js
 *
 * Full branch and condition coverage for all 8 exported adapter functions:
 *   formatBytes, mapBackendStatus, parseIndexingError, adaptRepository,
 *   buildFileTree, adaptFileDetails, adaptPlanTask, adaptIssueSync, adaptTaskPlan, adaptUser
 *
 * Each function is tested against every internal branch, switch-case,
 * ternary, and fallback path visible in the source code.
 */

import { describe, it, expect } from 'vitest';
import {
  formatBytes,
  mapBackendStatus,
  parseIndexingError,
  adaptRepository,
  buildFileTree,
  adaptFileDetails,
  adaptPlanTask,
  adaptIssueSync,
  adaptTaskPlan,
  adaptUser,
} from '../../services/adapters';

// ============================================================================
// formatBytes — 4 branches
// ============================================================================
describe('formatBytes', () => {
  it('returns "0 B" when bytes is 0', () => {
    expect(formatBytes(0)).toBe('0 B');
  });

  it('returns "0 B" when bytes is undefined (default param)', () => {
    expect(formatBytes()).toBe('0 B');
  });

  it('returns bytes with B suffix when < 1024', () => {
    expect(formatBytes(512)).toBe('512 B');
  });

  it('returns KB when >= 1024 and < 1MB', () => {
    expect(formatBytes(1024)).toBe('1.0 KB');
    expect(formatBytes(1536)).toBe('1.5 KB');
  });

  it('returns MB when >= 1MB', () => {
    expect(formatBytes(1024 * 1024)).toBe('1.0 MB');
    expect(formatBytes(2.5 * 1024 * 1024)).toBe('2.5 MB');
  });
});

// ============================================================================
// mapBackendStatus — 5 branches (4 cases + default)
// ============================================================================
describe('mapBackendStatus', () => {
  it('maps "queued" to "pending"', () => {
    expect(mapBackendStatus('queued')).toBe('pending');
  });

  it('maps "indexing" to "analyzing"', () => {
    expect(mapBackendStatus('indexing')).toBe('analyzing');
  });

  it('maps "ready" to "analyzed"', () => {
    expect(mapBackendStatus('ready')).toBe('analyzed');
  });

  it('maps "failed" to "error"', () => {
    expect(mapBackendStatus('failed')).toBe('error');
  });

  it('defaults to "pending" for unknown status', () => {
    expect(mapBackendStatus('something_else')).toBe('pending');
  });

  it('defaults to "pending" when called with no arguments', () => {
    expect(mapBackendStatus()).toBe('pending');
  });
});

// ============================================================================
// parseIndexingError — 6 distinct paths + null guard
// ============================================================================
describe('parseIndexingError', () => {
  // ---- Path 1: null / undefined / non-string ----
  it('returns generic fallback for null input', () => {
    const result = parseIndexingError(null);
    expect(result.title).toBe('Indexing Failed');
    expect(result.isRetryable).toBe(true);
    expect(result.failingFile).toBeNull();
  });

  it('returns generic fallback for undefined input', () => {
    const result = parseIndexingError(undefined);
    expect(result.title).toBe('Indexing Failed');
  });

  it('returns generic fallback for non-string input (number)', () => {
    const result = parseIndexingError(42);
    expect(result.title).toBe('Indexing Failed');
  });

  // ---- Path 2: NUL (0x00) byte error ----
  it('detects NUL byte error with file_path extracted', () => {
    const raw = `psycopg.DataError: cannot contain NUL (0x00) bytes 'file_path': 'src/data.bin'`;
    const result = parseIndexingError(raw);
    expect(result.title).toBe('Invalid File Encoding (NUL Bytes)');
    expect(result.failingFile).toBe('src/data.bin');
    expect(result.isRetryable).toBe(true);
    expect(result.advisory).toContain('src/data.bin');
  });

  it('detects NUL byte error without file_path', () => {
    const raw = 'cannot contain NUL (0x00) bytes in text column';
    const result = parseIndexingError(raw);
    expect(result.title).toBe('Invalid File Encoding (NUL Bytes)');
    expect(result.failingFile).toBeNull();
    expect(result.advisory).toContain('Retrying without changes');
  });

  it('detects 0x00 variant wording', () => {
    const result = parseIndexingError('error with 0x00 character detected');
    expect(result.title).toBe('Invalid File Encoding (NUL Bytes)');
  });

  // ---- Path 3: Remote branch not found ----
  it('detects remote branch not found error', () => {
    const raw = 'Remote branch feature/xyz not found in upstream origin';
    const result = parseIndexingError(raw);
    expect(result.title).toBe('Remote Branch Not Found');
    expect(result.message).toContain('feature/xyz');
    expect(result.isRetryable).toBe(false);
  });

  // ---- Path 4: Clone / authentication failure ----
  it('detects "Could not clone the repo" error', () => {
    const raw = 'Could not clone the repo: permission denied';
    const result = parseIndexingError(raw);
    expect(result.title).toBe('Repository Access Restricted');
    expect(result.isRetryable).toBe(true);
  });

  it('detects reauth message variant in clone error', () => {
    const raw = 'Could not clone the repo: Sign in with GitHub again';
    const result = parseIndexingError(raw);
    expect(result.title).toBe('Repository Access Restricted');
    expect(result.message).toContain('Sign in with GitHub again');
    expect(result.advisory).toContain('Sign in with GitHub again');
  });

  it('detects "Authentication failed" variant', () => {
    const raw = 'Authentication failed for https://github.com/private/repo.git';
    const result = parseIndexingError(raw);
    expect(result.title).toBe('Repository Access Restricted');
  });

  // ---- Path 5: No embeddable files ----
  it('detects "No embeddable text files found"', () => {
    const raw = 'No embeddable text files found in the checkout';
    const result = parseIndexingError(raw);
    expect(result.title).toBe('No Indexable Code Files');
    expect(result.isRetryable).toBe(false);
  });

  // ---- Path 6: Generic PostgreSQL / SQLAlchemy error ----
  it('detects SQLAlchemy error with [SQL: ...] marker', () => {
    const raw = `(psycopg.IntegrityError) duplicate key value [SQL: INSERT INTO chunks ...] params: {...}`;
    const result = parseIndexingError(raw);
    expect(result.title).toBe('Database Storage Error');
    expect(result.isRetryable).toBe(true);
    // The message should strip the [SQL:...] part
    expect(result.message).not.toContain('[SQL:');
  });

  it('detects psycopg. error without [SQL:] marker', () => {
    const raw = `psycopg.OperationalError: connection refused`;
    const result = parseIndexingError(raw);
    expect(result.title).toBe('Database Storage Error');
  });

  it('extracts file_path from SQLAlchemy error when present', () => {
    const raw = `sqlalchemy.exc.DataError: 'file_path': 'lib/broken.py' [SQL: INSERT ...]`;
    const result = parseIndexingError(raw);
    expect(result.failingFile).toBe('lib/broken.py');
  });

  // ---- Path 7: Generic fallback (none of the above match) ----
  it('falls back to first line for unrecognized error', () => {
    const raw = 'Something totally unexpected\nSecond line of detail';
    const result = parseIndexingError(raw);
    expect(result.title).toBe('Indexing Failed');
    expect(result.message).toBe('Something totally unexpected');
    expect(result.isRetryable).toBe(true);
    expect(result.technicalDetails).toBe(raw);
  });
});

// ============================================================================
// adaptRepository — heavy branching
// ============================================================================
describe('adaptRepository', () => {
  it('returns null for null input', () => {
    expect(adaptRepository(null)).toBeNull();
  });

  it('returns null for undefined input', () => {
    expect(adaptRepository(undefined)).toBeNull();
  });

  it('adapts a minimal backend repo (queued, no tech stack)', () => {
    const raw = { id: 1, url: 'https://github.com/owner/repo', status: 'queued' };
    const result = adaptRepository(raw);
    expect(result.id).toBe('1');
    expect(result.numericId).toBe(1);
    expect(result.owner).toBe('owner');
    expect(result.name).toBe('repo');
    expect(result.fullName).toBe('owner/repo');
    expect(result.status).toBe('pending'); // mapped from 'queued'
    expect(result.branch).toBe('main'); // default
    expect(result.language).toBe('Unknown');
    expect(result.languages).toEqual({ Unknown: 100 }); // fallback branch
  });

  it('computes language percentages from language_file_counts', () => {
    const raw = {
      id: 2,
      url: 'https://github.com/a/b',
      status: 'ready',
      tech_stack: { language_file_counts: { Python: 6, JavaScript: 4 } },
    };
    const result = adaptRepository(raw);
    expect(result.languages.Python).toBe(60);
    expect(result.languages.JavaScript).toBe(40);
    expect(result.language).toBe('Python'); // first in languages array or first key
  });

  it('distributes even shares when only tech_stack.languages array exists', () => {
    const raw = {
      id: 3,
      url: 'https://github.com/a/b',
      status: 'ready',
      tech_stack: { languages: ['Go', 'Rust'] },
    };
    const result = adaptRepository(raw);
    expect(result.languages.Go).toBe(50);
    expect(result.languages.Rust).toBe(50);
    expect(result.language).toBe('Go');
  });

  it('uses Unknown:100 when no language info exists', () => {
    const raw = { id: 4, url: 'https://github.com/a/b', status: 'ready', tech_stack: {} };
    const result = adaptRepository(raw);
    expect(result.languages).toEqual({ Unknown: 100 });
  });

  it('builds description from summary.one_line when available', () => {
    const raw = {
      id: 5,
      url: 'https://github.com/a/b',
      status: 'ready',
      summary: { one_line: 'A shop demo', description: 'Longer desc' },
    };
    const result = adaptRepository(raw);
    expect(result.description).toBe('A shop demo'); // one_line takes priority
  });

  it('falls back to summary.description when one_line is missing', () => {
    const raw = {
      id: 6,
      url: 'https://github.com/a/b',
      status: 'ready',
      summary: { description: 'Longer desc' },
    };
    const result = adaptRepository(raw);
    expect(result.description).toBe('Longer desc');
  });

  it('shows indexing stage message when status is indexing', () => {
    const raw = { id: 7, url: 'https://github.com/a/b', status: 'indexing', stage: 'embedding' };
    const result = adaptRepository(raw);
    expect(result.status).toBe('analyzing');
    expect(result.description).toContain('embedding');
  });

  it('populates parsedError when error field is present', () => {
    const raw = { id: 8, url: 'https://github.com/a/b', status: 'failed', error: 'Could not clone the repo' };
    const result = adaptRepository(raw);
    expect(result.error).toBe('Could not clone the repo');
    expect(result.parsedError).not.toBeNull();
    expect(result.parsedError.title).toBe('Repository Access Restricted');
  });

  it('sets parsedError to null when no error', () => {
    const raw = { id: 9, url: 'https://github.com/a/b', status: 'ready' };
    const result = adaptRepository(raw);
    expect(result.parsedError).toBeNull();
  });

  it('strips .git from URL for name extraction', () => {
    const raw = { id: 10, url: 'https://github.com/owner/my-lib.git', status: 'ready' };
    const result = adaptRepository(raw);
    expect(result.name).toBe('my-lib');
    expect(result.owner).toBe('owner');
  });

  it('extracts defaultFile from module_map entry_points', () => {
    const raw = {
      id: 11,
      url: 'https://github.com/a/b',
      status: 'ready',
      module_map: { entry_points: [{ path: 'src/main.py' }] },
    };
    const result = adaptRepository(raw);
    expect(result.defaultFile).toBe('src/main.py');
  });

  it('falls back defaultFile to summary.key_files when no entry_points', () => {
    const raw = {
      id: 12,
      url: 'https://github.com/a/b',
      status: 'ready',
      summary: { key_files: ['README.md'] },
    };
    const result = adaptRepository(raw);
    expect(result.defaultFile).toBe('README.md');
  });

  it('computes combined technologies list from frameworks + package_managers + languages', () => {
    const raw = {
      id: 13,
      url: 'https://github.com/a/b',
      status: 'ready',
      tech_stack: {
        frameworks: ['FastAPI'],
        package_managers: ['pip'],
        languages: ['Python'],
      },
    };
    const result = adaptRepository(raw);
    expect(result.technologies).toContain('FastAPI');
    expect(result.technologies).toContain('pip');
    expect(result.technologies).toContain('Python');
  });

  it('sets analyzedAt only when status is ready', () => {
    const readyRaw = { id: 14, url: 'https://github.com/a/b', status: 'ready', updated_at: '2026-01-01' };
    const indexingRaw = { id: 15, url: 'https://github.com/a/b', status: 'indexing' };
    expect(adaptRepository(readyRaw).analyzedAt).toBe('2026-01-01');
    expect(adaptRepository(indexingRaw).analyzedAt).toBeNull();
  });
});

// ============================================================================
// buildFileTree — hierarchical tree construction
// ============================================================================
describe('buildFileTree', () => {
  it('returns empty array for empty input', () => {
    expect(buildFileTree([])).toEqual([]);
  });

  it('returns empty array for undefined input', () => {
    expect(buildFileTree()).toEqual([]);
  });

  it('returns empty array for non-array input', () => {
    expect(buildFileTree(null)).toEqual([]);
  });

  it('creates root-level file nodes for flat paths', () => {
    const files = [
      { path: 'README.md', language: 'markdown', size: 100 },
      { path: '.gitignore', size: 50 },
    ];
    const tree = buildFileTree(files);
    expect(tree).toHaveLength(2);
    expect(tree[0].type).toBe('file');
    expect(tree[1].type).toBe('file');
  });

  it('creates folder hierarchy for nested paths', () => {
    const files = [
      { path: 'src/app.js', language: 'javascript', size: 200 },
      { path: 'src/utils/helper.js', language: 'javascript', size: 100 },
    ];
    const tree = buildFileTree(files);
    // Root should have one folder: "src"
    expect(tree).toHaveLength(1);
    expect(tree[0].type).toBe('folder');
    expect(tree[0].name).toBe('src');
    // src should have app.js and utils/
    expect(tree[0].children).toHaveLength(2);
  });

  it('sorts folders before files, then alphabetically', () => {
    const files = [
      { path: 'z_file.txt', size: 10 },
      { path: 'a_folder/inner.txt', size: 10 },
      { path: 'a_file.txt', size: 10 },
    ];
    const tree = buildFileTree(files);
    expect(tree[0].type).toBe('folder'); // a_folder comes first (folder)
    expect(tree[0].name).toBe('a_folder');
    expect(tree[1].type).toBe('file');
    expect(tree[1].name).toBe('a_file.txt'); // alphabetical
    expect(tree[2].name).toBe('z_file.txt');
  });

  it('marks sensitive files correctly', () => {
    const files = [{ path: '.env', size: 32, sensitive: true }];
    const tree = buildFileTree(files);
    expect(tree[0].sensitive).toBe(true);
  });

  it('formats file size using formatBytes', () => {
    const files = [{ path: 'big.js', size: 2048 }];
    const tree = buildFileTree(files);
    expect(tree[0].size).toBe('2.0 KB');
    expect(tree[0].rawSize).toBe(2048);
  });

  it('extracts language from extension when not provided', () => {
    const files = [{ path: 'script.py', size: 100 }];
    const tree = buildFileTree(files);
    expect(tree[0].language).toBe('py');
  });
});

// ============================================================================
// adaptFileDetails — importance, complexity, suggestions
// ============================================================================
describe('adaptFileDetails', () => {
  it('returns null for null input', () => {
    expect(adaptFileDetails(null, 'test.py')).toBeNull();
  });

  it('classifies importance as "critical" when importedBy >= 3', () => {
    const raw = {
      file: { size: 100 },
      symbols: [{ qualname: 'fn1' }],
      imported_by: ['a.py', 'b.py', 'c.py'],
      imports: [],
    };
    const result = adaptFileDetails(raw, 'core.py');
    expect(result.importance).toBe('critical');
  });

  it('classifies importance as "critical" when filename contains "App"', () => {
    const raw = { file: {}, symbols: [], imported_by: [], imports: [] };
    const result = adaptFileDetails(raw, 'src/App.jsx');
    expect(result.importance).toBe('critical');
  });

  it('classifies importance as "critical" when filename contains "main"', () => {
    const raw = { file: {}, symbols: [], imported_by: [], imports: [] };
    const result = adaptFileDetails(raw, 'main.py');
    expect(result.importance).toBe('critical');
  });

  it('classifies importance as "critical" when filename contains "index"', () => {
    const raw = { file: {}, symbols: [], imported_by: [], imports: [] };
    const result = adaptFileDetails(raw, 'src/index.js');
    expect(result.importance).toBe('critical');
  });

  it('classifies importance as "high" when importedBy >= 1 (but < 3)', () => {
    const raw = { file: {}, symbols: [], imported_by: ['one.py'], imports: [] };
    const result = adaptFileDetails(raw, 'helper.py');
    expect(result.importance).toBe('high');
  });

  it('classifies importance as "medium" when importedBy is 0 and no keyword in name', () => {
    const raw = { file: {}, symbols: [], imported_by: [], imports: [] };
    const result = adaptFileDetails(raw, 'utils.py');
    expect(result.importance).toBe('medium');
  });

  it('classifies complexity as "high" when symbols >= 12', () => {
    const symbols = Array.from({ length: 12 }, (_, i) => ({ qualname: `fn${i}` }));
    const raw = { file: {}, symbols, imported_by: [], imports: [] };
    const result = adaptFileDetails(raw, 'big.py');
    expect(result.complexity).toBe('high');
  });

  it('classifies complexity as "medium" when symbols >= 5 and < 12', () => {
    const symbols = Array.from({ length: 7 }, (_, i) => ({ qualname: `fn${i}` }));
    const raw = { file: {}, symbols, imported_by: [], imports: [] };
    const result = adaptFileDetails(raw, 'mid.py');
    expect(result.complexity).toBe('medium');
  });

  it('classifies complexity as "low" when symbols < 5', () => {
    const raw = { file: {}, symbols: [{ qualname: 'fn1' }], imported_by: [], imports: [] };
    const result = adaptFileDetails(raw, 'small.py');
    expect(result.complexity).toBe('low');
  });

  it('adds sensitive file suggestion when file.sensitive is true', () => {
    const raw = { file: { sensitive: true }, symbols: [], imported_by: [], imports: [] };
    const result = adaptFileDetails(raw, '.env');
    expect(result.suggestions.some((s) => s.includes('sensitive'))).toBe(true);
  });

  it('adds central dependency suggestion when importedBy >= 4', () => {
    const raw = { file: {}, symbols: [], imported_by: ['a', 'b', 'c', 'd'], imports: [] };
    const result = adaptFileDetails(raw, 'core.py');
    expect(result.suggestions.some((s) => s.includes('Central dependency'))).toBe(true);
  });

  it('adds refactoring suggestion when symbols > 15', () => {
    const symbols = Array.from({ length: 16 }, (_, i) => ({ qualname: `fn${i}` }));
    const raw = { file: {}, symbols, imported_by: [], imports: [] };
    const result = adaptFileDetails(raw, 'huge.py');
    expect(result.suggestions.some((s) => s.includes('refactoring'))).toBe(true);
  });

  it('adds default suggestion when no other suggestions apply', () => {
    const raw = { file: {}, symbols: [{ qualname: 'x' }], imported_by: [], imports: [] };
    const result = adaptFileDetails(raw, 'plain.py');
    expect(result.suggestions).toHaveLength(1);
    expect(result.suggestions[0]).toContain('Inspect symbol');
  });

  it('matches module purpose from moduleMap when path falls within a module', () => {
    const raw = { file: {}, symbols: [], imported_by: [], imports: [] };
    const moduleMap = { modules: [{ path: 'shop', name: 'Shop', purpose: 'Payments and orders' }] };
    const result = adaptFileDetails(raw, 'shop/payments.py', moduleMap);
    expect(result.purpose).toContain('Shop');
    expect(result.purpose).toContain('Payments and orders');
  });
});

// ============================================================================
// adaptPlanTask — task mapping
// ============================================================================
describe('adaptPlanTask', () => {
  it('maps an issue-sourced task correctly', () => {
    const task = {
      key: 'issue-42',
      title: 'Fix login bug',
      summary: 'The login form crashes on empty input',
      source: 'issue',
      difficulty: 'easy',
      status: 'pending',
      suggested_day: 1,
      number: 42,
      url: 'https://github.com/a/b/issues/42',
      labels: ['bug', 'good first issue'],
      reasons: ['beginner-friendly'],
      related_files: [{ path: 'src/login.py' }],
      guide: { what_to_do: 'Fix validation', where_to_start: 'login.py:10', done_when: 'Tests pass' },
    };
    const result = adaptPlanTask(task);
    expect(result.id).toBe('issue-42');
    expect(result.category).toBe('GitHub issue');
    expect(result.number).toBe(42);
    expect(result.targetFiles).toEqual(['src/login.py']);
    expect(result.guide.whatToDo).toBe('Fix validation');
    expect(result.guide.whereToStart).toBe('login.py:10');
    expect(result.guide.doneWhen).toBe('Tests pass');
  });

  it('maps an orientation task (non-issue) correctly', () => {
    const task = {
      key: 'orient-1',
      title: 'Read the README',
      source: 'orientation',
      difficulty: 'trivial',
      suggested_day: 1,
      related_files: [],
    };
    const result = adaptPlanTask(task);
    expect(result.category).toBe('Orientation');
    expect(result.source).toBe('orientation');
    expect(result.number).toBeNull();
    expect(result.url).toBeNull();
    expect(result.guide).toBeNull();
    expect(result.status).toBe('pending'); // default
  });
});

// ============================================================================
// adaptIssueSync — sync status mapping
// ============================================================================
describe('adaptIssueSync', () => {
  it('maps a full sync response', () => {
    const raw = { status: 'ok', message: 'Synced 5 issues', fetched: 5, synced_at: '2026-01-01T00:00:00Z' };
    const result = adaptIssueSync(raw);
    expect(result.status).toBe('ok');
    expect(result.fetched).toBe(5);
    expect(result.syncedAt).toBe('2026-01-01T00:00:00Z');
  });

  it('defaults to "never" for null/undefined input', () => {
    expect(adaptIssueSync(null).status).toBe('never');
    expect(adaptIssueSync(undefined).status).toBe('never');
  });

  it('defaults missing fields', () => {
    const result = adaptIssueSync({});
    expect(result.status).toBe('never');
    expect(result.message).toBeNull();
    expect(result.fetched).toBe(0);
    expect(result.syncedAt).toBeNull();
  });
});

// ============================================================================
// adaptTaskPlan — plan aggregation
// ============================================================================
describe('adaptTaskPlan', () => {
  it('maps a full task plan with sync and tasks', () => {
    const raw = {
      repo_id: 1,
      sync: { status: 'ok', fetched: 3 },
      eligible_issues: 3,
      fallback_used: false,
      notes: ['All issues found'],
      tasks: [
        { key: 't1', title: 'Task 1', source: 'issue', difficulty: 'easy', suggested_day: 1, related_files: [] },
      ],
    };
    const result = adaptTaskPlan(raw);
    expect(result.repoId).toBe(1);
    expect(result.sync.status).toBe('ok');
    expect(result.eligibleIssues).toBe(3);
    expect(result.fallbackUsed).toBe(false);
    expect(result.tasks).toHaveLength(1);
    expect(result.tasks[0].id).toBe('t1');
  });

  it('defaults missing fields in plan', () => {
    const raw = { repo_id: 2 };
    const result = adaptTaskPlan(raw);
    expect(result.eligibleIssues).toBe(0);
    expect(result.fallbackUsed).toBe(false);
    expect(result.notes).toEqual([]);
    expect(result.tasks).toEqual([]);
  });
});

// ============================================================================
// adaptUser — user mapping
// ============================================================================
describe('adaptUser', () => {
  it('maps a full user response', () => {
    const raw = {
      id: 1,
      name: 'Octo Cat',
      login: 'octo',
      email: 'octo@example.com',
      avatar_url: 'https://avatars.example/octo.png',
      github_connected: true,
      token_scopes: 'repo,read:user',
    };
    const result = adaptUser(raw);
    expect(result.id).toBe(1);
    expect(result.name).toBe('Octo Cat');
    expect(result.email).toBe('octo@example.com');
    expect(result.githubUsername).toBe('octo');
    expect(result.avatarUrl).toBe('https://avatars.example/octo.png');
    expect(result.githubConnected).toBe(true);
    expect(result.tokenScopes).toBe('repo,read:user');
  });

  it('falls back name to login when name is missing', () => {
    const raw = { id: 2, login: 'dev', email: '', github_connected: false };
    const result = adaptUser(raw);
    expect(result.name).toBe('dev');
  });

  it('defaults optional fields', () => {
    const raw = { id: 3, login: 'x' };
    const result = adaptUser(raw);
    expect(result.email).toBe('');
    expect(result.avatarUrl).toBeNull();
    expect(result.githubConnected).toBe(false);
    expect(result.tokenScopes).toBe('');
  });
});
