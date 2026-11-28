/**
 * White-box decision/path tests for api.js.
 * Derived from its guards, defaults, catch blocks, encoding loops and field allowlists.
 * Every fetch is a function stub; no HTTP server, rendered UI, or real backend is used.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../../src/services/api';

let fetchStub;
beforeEach(() => {
  fetchStub = vi.fn();
  vi.stubGlobal('fetch', fetchStub);
  vi.stubGlobal('window', Object.assign(new EventTarget(), { location: { assign: vi.fn() } }));
});

function returns(body, status = 200) {
  fetchStub.mockResolvedValueOnce({
    ok: status >= 200 && status < 300, status, statusText: 'stubbed',
    json: async () => body,
  });
}

function sent(index = 0) {
  const [url, options] = fetchStub.mock.calls[index];
  return { url, ...options, method: options.method, body: options.body ? JSON.parse(options.body) : undefined };
}

describe('request/error decision paths', () => {
  it.each([404, 422])('takes the %s fallback when detail is absent', async (status) => {
    returns({}, status);
    await expect(api.request('/test')).rejects.toMatchObject({ status, message: expect.stringContaining(String(status)) });
  });

  it.each([
    [{ message: 'Top-level error' }, 'Top-level error'],
    [{ detail: [{ msg: 'Missing location' }, { loc: ['body', 'x'] }] }, 'Missing location; body.x: Invalid field'],
    [{ detail: { reason: 'No message field' } }, '{"reason":"No message field"}'],
  ])('handles the error-body branch %j', async (body, message) => {
    returns(body, 400);
    await expect(api.request('/test')).rejects.toMatchObject({ message, status: 400 });
  });

  it('takes the status fallback if both response readers reject', async () => {
    fetchStub.mockResolvedValueOnce({
      ok: false, status: 429,
      json: async () => { throw new Error('Unreadable JSON'); },
      text: async () => { throw new Error('Unreadable text'); },
    });
    await expect(api.request('/test')).rejects.toThrow('Too many requests');
  });

  it('merges custom headers and preserves the original network error as cause', async () => {
    returns({});
    await api.request('/test', { headers: { 'Content-Type': 'custom/type', 'X-Test': 'value' } });
    expect(sent().headers).toEqual({ 'Content-Type': 'custom/type', 'X-Test': 'value' });
    const cause = new TypeError('offline');
    fetchStub.mockRejectedValueOnce(cause);
    await expect(api.request('/test')).rejects.toMatchObject({ cause });
  });
});

describe('auth and repository wrapper paths', () => {
  it('uses configured and failed auth-config return paths', async () => {
    returns({ github_login_enabled: true });
    expect(await api.getAuthConfig()).toEqual({ github_login_enabled: true });
    fetchStub.mockRejectedValueOnce(new Error('offline'));
    expect(await api.getAuthConfig()).toEqual({ github_login_enabled: false });
  });

  it('delegates OAuth to location.assign without making a fetch', () => {
    api.loginWithGitHub();
    expect(window.location.assign).toHaveBeenCalledExactlyOnceWith('/api/auth/github/login');
    expect(fetchStub).not.toHaveBeenCalled();
  });

  it('adapts the profile and handles the bodyless logout path', async () => {
    returns({ id: 1, login: 'octo' });
    expect(await api.getUserProfile()).toMatchObject({ success: true, user: { name: 'octo' } });
    returns(null, 204);
    expect(await api.logout()).toEqual({ success: true });
    expect(sent(1)).toMatchObject({ url: '/api/auth/logout', method: 'POST' });
  });

  it.each([null, []])('maps an absent/empty repository list %j to an empty array', async (raw) => {
    returns(raw);
    expect((await api.getRepositories()).repositories).toEqual([]);
  });

  it('maps every repository instead of returning raw API records', async () => {
    returns([{ id: 1, url: 'https://github.com/a/b', status: 'queued' }]);
    expect((await api.getRepositories()).repositories[0]).toMatchObject({ id: '1', status: 'pending' });
  });

  it.each([['007', '7'], ['not numeric', 'not%20numeric']])(
    'takes the numeric/NaN repository-id branch for %s', async (id, encoded) => {
      returns({ id: 7, url: 'https://github.com/a/b' });
      expect((await api.getRepositoryById(id)).success).toBe(true);
      expect(sent().url).toBe(`/api/repos/${encoded}`);
    },
  );

  it.each([[' token ', 'token'], [null, null]])('normalizes reindex token %j', async (token, expected) => {
    returns({ id: 7, url: 'https://github.com/a/b' });
    await api.reindexRepository(7, token);
    expect(sent()).toMatchObject({ url: '/api/repos/7/reindex', method: 'POST', body: { access_token: expected } });
  });

  it('keeps repository deletion and credential-disconnect delegation distinct', async () => {
    returns(null, 204);
    expect(await api.disconnectRepository('a/b')).toEqual({ success: true, id: 'a/b' });
    expect(sent()).toMatchObject({ url: '/api/repos/a%2Fb', method: 'DELETE' });
    returns({ github_connected: false });
    expect(await api.disconnectGitHub()).toEqual({ github_connected: false });
    expect(sent(1)).toMatchObject({ url: '/api/auth/github/disconnect', method: 'POST' });
  });

  it('takes default and populated GitHub pagination branches', async () => {
    returns({});
    expect(await api.listGitHubRepos()).toEqual({ repos: [], page: 1, hasMore: false });
    returns({ repos: [{ full_name: 'a/b' }], page: 2, has_more: true });
    expect(await api.listGitHubRepos({ page: 2, perPage: 10 })).toMatchObject({ page: 2, hasMore: true });
    expect(sent(1).url).toBe('/api/github/repos?page=2&per_page=10');
  });

  it('encodes branch lookups and takes missing-field defaults', async () => {
    returns({});
    expect(await api.listGitHubBranches('a/b')).toEqual({ defaultBranch: null, branches: [], truncated: false });
    expect(sent().url).toBe('/api/github/branches?repo=a%2Fb');
    returns({ default_branch: 'dev', branches: ['dev'], truncated: true });
    expect(await api.listGitHubBranches('a/b')).toEqual({ defaultBranch: 'dev', branches: ['dev'], truncated: true });
  });
});

describe('file and explanation paths', () => {
  it('builds a file tree and encodes path segments without removing separators', async () => {
    returns([{ path: 'src/a.py', size: 1 }]);
    expect((await api.getFileTree('007')).tree[0].name).toBe('src');
    returns({ file: {}, symbols: [], imported_by: [], imports: [] });
    expect((await api.getFileDetails(7, 'src/my file#1.py')).success).toBe(true);
    expect(sent(1).url).toBe('/api/repos/7/files/src/my%20file%231.py');
  });

  it.each([['code', 'code'], [undefined, '']])('uses the direct-source branch for content %j', async (content, expected) => {
    returns({ content, commit_sha: 'sha' });
    expect(await api.getFileContent(7, 'a.py')).toEqual({
      success: true, content: expected, isPartial: false, commitSha: 'sha',
    });
    expect(fetchStub).toHaveBeenCalledOnce();
  });

  it('filters, sorts, and joins matching excerpts in the first source fallback', async () => {
    fetchStub.mockRejectedValueOnce(new Error('source unavailable'));
    returns({ hits: [
      { file_path: 'a.py', start_line: 10, end_line: 12, content: 'later' },
      { file_path: 'other.py', start_line: 1, end_line: 2, content: 'exclude' },
      { file_path: 'a.py', start_line: 1, end_line: 2, content: 'earlier' },
    ] });
    expect(await api.getFileContent(7, 'a.py')).toMatchObject({
      isPartial: true,
      content: '// --- Lines 1-2 (indexed excerpt) ---\nearlier\n\n// --- Lines 10-12 (indexed excerpt) ---\nlater',
    });
  });

  it.each(['no matches', 'search throws'])('takes the final source fallback when %s', async (branch) => {
    fetchStub.mockRejectedValueOnce(new Error('source unavailable'));
    if (branch === 'search throws') fetchStub.mockRejectedValueOnce(new Error('search unavailable'));
    else returns({ hits: [{ file_path: 'other.py' }] });
    expect(await api.getFileContent(7, 'a.py')).toMatchObject({
      isPartial: true, content: expect.stringContaining('Source for a.py could not be fetched'),
    });
  });

  it('defaults missing symbols and encodes search text', async () => {
    returns(null);
    expect(await api.searchSymbols(7, 'save & load')).toEqual({ success: true, symbols: [] });
    expect(sent().url).toBe('/api/repos/7/symbols?q=save%20%26%20load&limit=20');
  });

  it.each([
    ['file', api.getFileExplanation, 'my file.py'],
    ['symbol', api.getSymbolExplanation, 'db::save'],
  ])('selects the %s explanation parameter and refresh condition', async (key, explain, value) => {
    returns({ target: value });
    expect(await explain(7, value)).toMatchObject({
      name: value, relationships: {}, explanation: null, source: 'none', warnings: [],
    });
    expect(new URL(sent().url, 'http://unit.test').searchParams.get(key)).toBe(value);
    expect(sent().url).not.toContain('refresh');
    returns({ target: value, qualname: 'save', source: 'cache', explanation: { summary: 'Saved' } });
    expect(await explain(7, value, { refresh: true })).toMatchObject({ name: 'save', source: 'cache' });
    expect(sent(1).url).toContain('refresh=true');
  });

  it('defaults absent dependency-map fields', async () => {
    returns({});
    expect(await api.getDependencyGraph(7)).toMatchObject({
      modules: [], entryPoints: [], graph: { nodes: [], edges: [] }, techStack: {},
    });
  });
});

describe('conversation and answer paths', () => {
  it.each([
    [api.getConversations, [7], '/api/repos/7/conversations', undefined, undefined],
    [api.createConversation, [7], '/api/repos/7/conversations', 'POST', { title: 'New conversation' }],
    [api.getConversationMessages, [7, 'a/b'], '/api/repos/7/conversations/a%2Fb/messages', undefined, undefined],
    [api.deleteConversation, [7, 'a/b'], '/api/repos/7/conversations/a%2Fb', 'DELETE', undefined],
  ])('encodes/delegates conversation helper %s', async (fn, args, url, method, body) => {
    returns([]);
    expect(await fn(...args)).toEqual([]);
    expect(sent()).toMatchObject({ url, method, body });
  });

  it('uses only truthy supported hints and takes absent answer-field defaults', async () => {
    returns({ answer: 'Answer' });
    const result = await api.askCodebaseQuestion(7, 'Question', {
      symbol: '', file: '', depth: 0, history: ['unsupported'], extra: true,
    });
    expect(sent().body).toEqual({ question: 'Question' });
    expect(result).toMatchObject({
      intent: 'question', citations: [], sources: [], referencedFiles: [], impact: null,
      needsClarification: false, candidates: [], warnings: [],
    });
  });

  it('deduplicates reference paths and adapts the impact/clarification branch', async () => {
    returns({
      answer: 'Which function?', intent: 'impact', needs_clarification: true,
      citations: [{ path: 'a.py' }, { path: 'a.py' }], sources: [{ file_path: 'b.py' }, {}],
      impact: { target: 'save', depth: 2 }, candidates: [{ path: 'a.py' }],
    });
    expect(await api.askCodebaseQuestion(7, 'Question', { symbol: 'save', file: 'a.py', depth: 2 })).toMatchObject({
      referencedFiles: ['a.py', 'b.py'], needsClarification: true,
      impact: { target: 'save', affectedFiles: [], dependencies: { calls: [], imports: [] } },
    });
    expect(sent().body).toEqual({ question: 'Question', symbol: 'save', file: 'a.py', depth: 2 });
  });

  it('defaults absent search hits and impact lists', async () => {
    returns({});
    expect((await api.searchCode(7, 'save')).hits).toEqual([]);
    returns({});
    expect(await api.getImpactAnalysis(7, { file: 'my file.py' })).toMatchObject({ affectedSymbols: [], affectedFiles: [] });
    expect(sent(1).url).toBe('/api/repos/7/impact?file=my+file.py&depth=3');
  });
});

describe('task/history wrapper decision paths', () => {
  it.each([false, true])('adds the explain parameter only when %s', async (explain) => {
    returns({ repo_id: 7, tasks: [] });
    expect((await api.getOnboardingTasks(7, { limit: 3, explain })).success).toBe(true);
    expect(sent().url).toBe(`/api/repos/7/onboarding-tasks?limit=3${explain ? '&explain=true' : ''}`);
  });

  it('encodes task keys, maps the save result, and adapts sync states', async () => {
    returns({ key: 'issue-42', status: 'completed' });
    expect(await api.updateOnboardingTask(7, 'issue/42', 'completed')).toEqual({
      success: true, key: 'issue-42', status: 'completed',
    });
    expect(sent()).toMatchObject({
      url: '/api/repos/7/onboarding-tasks/issue%2F42/progress', method: 'PUT', body: { status: 'completed' },
    });
    returns({ status: 'queued' });
    expect((await api.syncRepositoryIssues(7)).status).toBe('queued');
    expect(sent(1)).toMatchObject({ method: 'POST', body: {} });
    returns({ status: 'ok', fetched: 3 });
    expect((await api.getIssueSyncStatus(7)).fetched).toBe(3);
  });

  it.each([['', '/api/repos/7/history?limit=50'], ['src/my folder', '/api/repos/7/history?limit=50&path=src%2Fmy+folder']])(
    'takes the empty/nonempty history-path branch for %j', async (path, url) => {
      returns({ commits: [] });
      expect(await api.getRepositoryHistory(7, { path })).toEqual({ commits: [] });
      expect(sent().url).toBe(url);
    },
  );
});
