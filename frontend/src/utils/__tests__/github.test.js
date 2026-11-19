/**
 * White-box tests for utils/github.js
 *
 * Tests parseGitHubUrl() and isValidBranch() with full branch and condition coverage.
 * These functions mirror the backend validation (ai_pipeline/repo.py) exactly.
 *
 * Coverage targets:
 * - parseGitHubUrl: null/empty guard, regex match/mismatch, .git stripping, trailing slash
 * - isValidBranch: empty (default), valid names, '..' injection, trailing '/', leading '-'
 */

import { describe, it, expect } from 'vitest';
import { parseGitHubUrl, isValidBranch } from '../../utils/github';

// ============================================================================
// parseGitHubUrl — Branch & Path Coverage
// ============================================================================
describe('parseGitHubUrl', () => {
  // ---- Happy path: valid URLs ----

  it('parses a standard GitHub URL', () => {
    const result = parseGitHubUrl('https://github.com/owner/repo');
    expect(result).toEqual({
      owner: 'owner',
      name: 'repo',
      fullName: 'owner/repo',
      url: 'https://github.com/owner/repo',
    });
  });

  it('strips trailing .git suffix', () => {
    const result = parseGitHubUrl('https://github.com/owner/repo.git');
    expect(result).toEqual({
      owner: 'owner',
      name: 'repo',
      fullName: 'owner/repo',
      url: 'https://github.com/owner/repo',
    });
  });

  it('strips trailing slash', () => {
    const result = parseGitHubUrl('https://github.com/owner/repo/');
    expect(result).toEqual({
      owner: 'owner',
      name: 'repo',
      fullName: 'owner/repo',
      url: 'https://github.com/owner/repo',
    });
  });

  it('handles owner/name with dots, hyphens, and underscores', () => {
    const result = parseGitHubUrl('https://github.com/my-org/my.repo-name_2');
    expect(result).not.toBeNull();
    expect(result.owner).toBe('my-org');
    expect(result.name).toBe('my.repo-name_2');
    expect(result.fullName).toBe('my-org/my.repo-name_2');
  });

  it('trims surrounding whitespace from input', () => {
    const result = parseGitHubUrl('  https://github.com/owner/repo  ');
    expect(result).not.toBeNull();
    expect(result.url).toBe('https://github.com/owner/repo');
  });

  // ---- Rejection paths: input → null ----

  it('returns null for null input', () => {
    expect(parseGitHubUrl(null)).toBeNull();
  });

  it('returns null for undefined input', () => {
    expect(parseGitHubUrl(undefined)).toBeNull();
  });

  it('returns null for empty string', () => {
    expect(parseGitHubUrl('')).toBeNull();
  });

  it('returns null for non-GitHub host (gitlab)', () => {
    expect(parseGitHubUrl('https://gitlab.com/owner/repo')).toBeNull();
  });

  it('returns null for a lookalike host (evilgithub.com)', () => {
    expect(parseGitHubUrl('https://evilgithub.com/owner/repo')).toBeNull();
  });

  it('returns null when repo part is missing (owner only)', () => {
    expect(parseGitHubUrl('https://github.com/owner')).toBeNull();
  });

  it('returns null for URLs with extra path segments (tree/main)', () => {
    expect(parseGitHubUrl('https://github.com/owner/repo/tree/main')).toBeNull();
  });

  it('returns null for file:// protocol (injection attempt)', () => {
    expect(parseGitHubUrl('file:///etc/passwd')).toBeNull();
  });

  it('returns null for SSH URLs', () => {
    expect(parseGitHubUrl('ssh://git@github.com/owner/repo')).toBeNull();
  });

  it('returns null for local filesystem paths', () => {
    expect(parseGitHubUrl('/tmp/some/local/clone')).toBeNull();
  });

  it('returns null when owner is empty (double slash)', () => {
    expect(parseGitHubUrl('https://github.com//repo')).toBeNull();
  });
});

// ============================================================================
// isValidBranch — Branch & Condition Coverage
// ============================================================================
describe('isValidBranch', () => {
  // ---- True paths ----

  it('returns true for empty string (use default branch)', () => {
    expect(isValidBranch('')).toBe(true);
  });

  it('returns true for null (use default branch)', () => {
    expect(isValidBranch(null)).toBe(true);
  });

  it('returns true for undefined (use default branch)', () => {
    expect(isValidBranch(undefined)).toBe(true);
  });

  it('returns true for a simple branch name', () => {
    expect(isValidBranch('main')).toBe(true);
  });

  it('returns true for branch with slashes and hyphens', () => {
    expect(isValidBranch('feature/x-1')).toBe(true);
  });

  it('returns true for branch with dots', () => {
    expect(isValidBranch('release/v1.2.3')).toBe(true);
  });

  it('trims whitespace and treats blank as empty', () => {
    expect(isValidBranch('   ')).toBe(true);
  });

  // ---- False paths ----

  it('returns false for double-dot traversal (a..b)', () => {
    expect(isValidBranch('a..b')).toBe(false);
  });

  it('returns false for trailing slash', () => {
    expect(isValidBranch('main/')).toBe(false);
  });

  it('returns false for leading dash (--exec=x)', () => {
    expect(isValidBranch('--exec=x')).toBe(false);
  });

  it('returns false for leading single dash (-x)', () => {
    expect(isValidBranch('-x')).toBe(false);
  });

  it('returns false for spaces in name (a b)', () => {
    expect(isValidBranch('a b')).toBe(false);
  });
});
