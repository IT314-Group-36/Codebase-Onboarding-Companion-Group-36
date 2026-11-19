/**
 * White-box tests for services/api.js
 *
 * Tests the internal error parsing (parseError) and core request() wrapper
 * with mocked fetch. Covers every branch in error extraction:
 *   - detail as string, array (Pydantic), object (with code)
 *   - non-JSON response body fallback to .text()
 *   - status-specific fallback messages (401, 404, 409, 422, 429, 503, 502)
 *   - auth:expired event dispatch on 401
 *   - 204 No Content handling
 *   - network error (fetch throws)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// We need to mock fetch before importing the module.
// The api.js module uses `import.meta.env.VITE_API_BASE_URL` — Vitest handles that.
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

// Mock window.dispatchEvent to track auth:expired
const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

// Now import the module under test
const {
  request,
  checkHealth,
  askCodebaseQuestionStream,
  connectRepository,
  searchCode,
  getImpactAnalysis,
} = await import('../../services/api');

function jsonResponse(status, body, headers = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: `Status ${status}`,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
    headers: new Headers(headers),
  };
}

function textResponse(status, text) {
  return {
    ok: false,
    status,
    statusText: `Status ${status}`,
    json: () => Promise.reject(new Error('not json')),
    text: () => Promise.resolve(text),
    headers: new Headers(),
  };
}

beforeEach(() => {
  mockFetch.mockReset();
  dispatchSpy.mockClear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ============================================================================
// request() — success paths
// ============================================================================
describe('request — success paths', () => {
  it('returns parsed JSON for a 200 response', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(200, { status: 'ok' }));
    const result = await request('/health');
    expect(result).toEqual({ status: 'ok' });
    expect(mockFetch).toHaveBeenCalledOnce();
    // Verify credentials: 'include' is sent (session cookie)
    const callArgs = mockFetch.mock.calls[0][1];
    expect(callArgs.credentials).toBe('include');
  });

  it('returns null for 204 No Content', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      statusText: 'No Content',
      json: () => Promise.reject(new Error('no body')),
      headers: new Headers(),
    });
    const result = await request('/repos/1', { method: 'DELETE' });
    expect(result).toBeNull();
  });

  it('sends Content-Type: application/json by default', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(200, {}));
    await request('/test');
    const callArgs = mockFetch.mock.calls[0][1];
    expect(callArgs.headers['Content-Type']).toBe('application/json');
  });
});

// ============================================================================
// request() — error handling: parseError branches
// ============================================================================
describe('request — error parsing', () => {
  it('extracts detail string from error body', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(400, { detail: 'Bad input' }));
    await expect(request('/test')).rejects.toThrow('Bad input');
  });

  it('extracts Pydantic validation error array', async () => {
    const body = {
      detail: [
        { loc: ['body', 'url'], msg: 'field required' },
        { loc: ['body', 'branch'], msg: 'invalid format' },
      ],
    };
    mockFetch.mockResolvedValueOnce(jsonResponse(422, body));
    await expect(request('/test')).rejects.toThrow('body.url: field required');
  });

  it('extracts message and code from detail object', async () => {
    const body = { detail: { message: 'Token expired', code: 'github_reauth_required' } };
    mockFetch.mockResolvedValueOnce(jsonResponse(403, body));
    try {
      await request('/test');
    } catch (err) {
      expect(err.message).toBe('Token expired');
      expect(err.code).toBe('github_reauth_required');
    }
  });

  it('falls back to response.text() when body is not JSON', async () => {
    mockFetch.mockResolvedValueOnce(textResponse(500, 'Internal Server Error'));
    await expect(request('/test')).rejects.toThrow('Internal Server Error');
  });

  it('uses status-specific fallback for 401 when no detail', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(401, {}));
    await expect(request('/test')).rejects.toThrow('session has expired');
  });

  it('uses status-specific fallback for 409', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(409, {}));
    await expect(request('/test')).rejects.toThrow('409');
  });

  it('uses status-specific fallback for 429', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(429, {}));
    await expect(request('/test')).rejects.toThrow('Too many requests');
  });

  it('uses status-specific fallback for 503 (no LLM)', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(503, {}));
    await expect(request('/test')).rejects.toThrow('LLM is not configured');
  });

  it('uses status-specific fallback for 502', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(502, {}));
    await expect(request('/test')).rejects.toThrow('AI provider call failed');
  });

  it('uses generic fallback for unknown status codes', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(418, {}));
    await expect(request('/test')).rejects.toThrow('Backend request failed: 418');
  });
});

// ============================================================================
// request() — auth:expired event
// ============================================================================
describe('request — auth:expired dispatch', () => {
  it('dispatches auth:expired on 401 for non-auth endpoints', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(401, {}));
    await expect(request('/repos')).rejects.toThrow();
    expect(dispatchSpy).toHaveBeenCalledWith(expect.any(Event));
    const event = dispatchSpy.mock.calls[0][0];
    expect(event.type).toBe('auth:expired');
  });

  it('does NOT dispatch auth:expired on 401 for /auth/ endpoints', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(401, {}));
    await expect(request('/auth/me')).rejects.toThrow();
    // Should not dispatch the event for auth endpoints
    const authExpiredCalls = dispatchSpy.mock.calls.filter(
      (call) => call[0]?.type === 'auth:expired'
    );
    expect(authExpiredCalls).toHaveLength(0);
  });
});

// ============================================================================
// request() — network error
// ============================================================================
describe('request — network errors', () => {
  it('throws readable message when fetch itself rejects', async () => {
    mockFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await expect(request('/health')).rejects.toThrow('Unable to reach the backend server');
  });
});

// ============================================
// askCodebaseQuestionStream() — SSE & Security
// ============================================
describe('askCodebaseQuestionStream', () => {
  function sseStreamResponse(chunks) {
    const encoder = new TextEncoder();
    let index = 0;
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      body: {
        getReader: () => ({
          read: () => {
            if (index < chunks.length) {
              const value = encoder.encode(chunks[index++]);
              return Promise.resolve({ value, done: false });
            }
            return Promise.resolve({ value: undefined, done: true });
          },
        }),
      },
      headers: new Headers({ 'Content-Type': 'text/event-stream' }),
    };
  }

  it('filters out unsupported keys (history) and keeps symbol/file/depth', async () => {
    mockFetch.mockResolvedValueOnce(
      sseStreamResponse(['data: {"type": "token", "content": "hi"}\n\n'])
    );
    const onEvent = vi.fn();
    const hints = {
      symbol: 'save_order',
      file: 'shop/db.py',
      depth: 2,
      history: [{ role: 'user', content: 'prior turn' }], // MUST be discarded
      unsupportedKey: 'inject',
    };

    await askCodebaseQuestionStream(1, 'How does checkout work?', hints, onEvent, 42);

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain('/repos/1/ask/stream');
    const sentBody = JSON.parse(options.body);

    expect(sentBody.question).toBe('How does checkout work?');
    expect(sentBody.conversation_id).toBe(42);
    expect(sentBody.symbol).toBe('save_order');
    expect(sentBody.file).toBe('shop/db.py');
    expect(sentBody.depth).toBe(2);
    expect(sentBody.history).toBeUndefined();
    expect(sentBody.unsupportedKey).toBeUndefined();
    expect(onEvent).toHaveBeenCalledWith({ type: 'token', content: 'hi' });
  });

  it('handles null or missing conversationId and null hints gracefully', async () => {
    mockFetch.mockResolvedValueOnce(
      sseStreamResponse(['data: {"type": "done"}\n\n'])
    );
    const onEvent = vi.fn();
    await askCodebaseQuestionStream(1, 'What is this repo?', null, onEvent);

    const [, options] = mockFetch.mock.calls[0];
    const sentBody = JSON.parse(options.body);
    expect(sentBody.question).toBe('What is this repo?');
    expect(sentBody.conversation_id).toBeNull();
    expect(onEvent).toHaveBeenCalledWith({ type: 'done' });
  });

  it('throws an error when SSE event type is error', async () => {
    mockFetch.mockResolvedValueOnce(
      sseStreamResponse(['data: {"type": "error", "message": "model overloaded"}\n\n'])
    );
    const onEvent = vi.fn();
    await expect(
      askCodebaseQuestionStream(1, 'Fail please', {}, onEvent)
    ).rejects.toThrow('model overloaded');
  });

  it('dispatches auth:expired when stream returns 401', async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(401, { detail: 'Unauthorized' }));
    const onEvent = vi.fn();
    await expect(
      askCodebaseQuestionStream(1, 'Auth test', {}, onEvent)
    ).rejects.toThrow('Unauthorized');
    expect(dispatchSpy).toHaveBeenCalledWith(expect.any(Event));
  });

  it('throws when browser does not support response.body stream', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: null,
      headers: new Headers(),
    });
    const onEvent = vi.fn();
    await expect(
      askCodebaseQuestionStream(1, 'No body', {}, onEvent)
    ).rejects.toThrow('does not support streamed responses');
  });
});

// ============================================
// connectRepository() — Validation & Request
// ============================================
describe('connectRepository', () => {
  it('rejects invalid GitHub URL without calling fetch', async () => {
    const res = await connectRepository('https://gitlab.com/owner/repo');
    expect(res.success).toBe(false);
    expect(res.error).toContain('Invalid GitHub URL');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('rejects invalid branch name without calling fetch', async () => {
    const res = await connectRepository('https://github.com/owner/repo', 'bad..branch');
    expect(res.success).toBe(false);
    expect(res.error).toContain('Invalid branch name');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('sends POST /repos on valid input and adapts response', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(202, { id: 10, url: 'https://github.com/owner/repo', status: 'queued' })
    );
    const res = await connectRepository('https://github.com/owner/repo', 'main', 'token123');
    expect(res.success).toBe(true);
    expect(res.repository.id).toBe('10');
    expect(res.repository.status).toBe('pending');

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain('/repos');
    expect(options.method).toBe('POST');
    const sent = JSON.parse(options.body);
    expect(sent.url).toBe('https://github.com/owner/repo');
    expect(sent.branch).toBe('main');
    expect(sent.access_token).toBe('token123');
  });

  it('returns success: false on backend error', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(409, { detail: 'Repository already exists' })
    );
    const res = await connectRepository('https://github.com/owner/repo');
    expect(res.success).toBe(false);
    expect(res.error).toBe('Repository already exists');
  });
});

// ============================================
// searchCode() & getImpactAnalysis()
// ============================================
describe('searchCode and getImpactAnalysis', () => {
  it('searchCode sends POST /search and returns hits', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(200, { hits: [{ file_path: 'a.py', score: 0.9 }] })
    );
    const res = await searchCode(5, 'checkout', 10);
    expect(res.success).toBe(true);
    expect(res.hits).toHaveLength(1);

    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain('/repos/5/search');
    expect(JSON.parse(options.body)).toEqual({ query: 'checkout', k: 10 });
  });

  it('getImpactAnalysis builds correct query parameters and adapts report', async () => {
    mockFetch.mockResolvedValueOnce(
      jsonResponse(200, {
        target: 'save_order',
        depth: 2,
        affected_symbols: [{ uid: 'charge_card', distance: 1 }],
        affected_files: [{ path: 'payments.py' }],
        explanation: 'Callers may break',
      })
    );
    const res = await getImpactAnalysis(1, { symbol: 'save_order', depth: 2, explain: true });
    expect(res.success).toBe(true);
    expect(res.target).toBe('save_order');
    expect(res.affectedSymbols).toHaveLength(1);
    expect(res.report.affectedSymbols).toHaveLength(1);

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain('symbol=save_order');
    expect(url).toContain('depth=2');
    expect(url).toContain('explain=true');
  });
});

