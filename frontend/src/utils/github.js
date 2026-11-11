/**
 * GitHub URL and branch rules. These mirror the backend (ai_pipeline/repo.py) exactly, so the form rejects
 * what the API would reject: https only, github.com/<owner>/<repo>.
 */
const GITHUB_URL = /^https:\/\/github\.com\/([\w.-]+)\/([\w.-]+?)(?:\.git)?\/?$/;
const BRANCH_NAME = /^[\w][\w./-]{0,99}$/;

/** { owner, name, fullName, url } for a valid repository URL (canonical form), otherwise null. */
export function parseGitHubUrl(input) {
  const match = GITHUB_URL.exec((input || '').trim());
  if (!match) return null;
  const [, owner, name] = match;
  return { owner, name, fullName: `${owner}/${name}`, url: `https://github.com/${owner}/${name}` };
}

/** True for an empty branch (= the repository's default branch) or a name the backend accepts. */
export function isValidBranch(branch) {
  const value = (branch || '').trim();
  if (!value) return true;
  return BRANCH_NAME.test(value) && !value.includes('..') && !value.endsWith('/');
}
