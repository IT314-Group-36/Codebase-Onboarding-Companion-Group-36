# CI/CD setup checklist

Repository changes do not change your GitHub, Render, Neon or Vercel account settings.
An administrator must complete the following steps. No deployment API token or production DB
credential belongs in GitHub Actions for this setup.

## 1. Publish and review the branch

Push `ci/deployment-readiness-checks`, open a PR to `main`, and wait for:

| Required check | Scope |
|---|---|
| Backend checks | Ruff, real migrations and backend pytest on disposable pgvector Postgres |
| Frontend checks | ESLint and build only; automated tests remain assigned to the testing team |
| Backend Docker smoke | Actual production image, entrypoint/migrations, readiness, revision, database failure |
| Dependency security | Locked backend dependency audit and frontend high/critical dependency audit |

Review any security findings rather than bypassing them. Backend audits reject all reported
vulnerabilities; frontend audits reject high/critical findings. Registry/audit-service outages can
also fail this check. Dependabot opens weekly dependency-update PRs; it does not auto-merge them.
These checks are not a complete SAST, secret, or container-OS vulnerability scan.

## 2. Protect `main` in GitHub

After the PR has run once (so GitHub knows the new check names):

1. Repository **Settings → Rules → Rulesets → New ruleset → New branch ruleset**.
2. Name it `Protect main`, set enforcement to **Active**, and target branch `main`.
3. Enable **Require a pull request before merging**; use at least one approval if your team can review.
4. Enable **Require status checks to pass** and add the four exact check names above.
   Select GitHub Actions as the expected source when available.
5. Enable **Require branches to be up to date before merging**.
6. Block force pushes and branch deletion. Avoid broad bypass permissions, including administrator
   bypass, unless your team has a documented emergency procedure.
7. Save. If rulesets are unavailable on your organization's plan, use
   **Settings → Branches → Add branch protection rule** with the same requirements.

Do **not** require `Deployed backend readiness` for PR merges. It only runs manually after production
deployment. Do not enable a merge queue without adding/testing `merge_group` support in CI.
The Vercel preview check is optional as a required check: inspect its exact name and whether every PR,
including external contributors' PRs, is authorized to produce it before requiring it.

## 3. Configure Render (no deployment tokens)

1. Open the existing backend service → **Settings**.
2. Verify branch `main`, Dockerfile `backend/Dockerfile`, build context `./backend`.
3. Change **Auto-Deploy → After CI Checks Pass**, not `On Commit`.
   Ensure the Render GitHub integration has access to this repository and its checks.
4. After this PR's code is deployed, change **Health Check Path → /ready**.
   Leave `/health` in place until then: older code does not have `/ready`.
5. Leave Docker Command and Pre-Deploy Command empty; the production entrypoint runs migrations.
6. Keep your Neon `DATABASE_URL` and other production secrets in Render only. Render automatically
   supplies `RENDER_GIT_COMMIT`; do not override it.

Render waits for commit checks, potentially including Vercel checks. A blocked Vercel preview can
therefore delay backend deployment; inspect both dashboards if a deploy does not start.
Do not additionally configure GitHub deploy hooks/API deployment workflows: there should be one
deployment controller, not two.

For the initial rollout, either wait for the successful main-branch checks to trigger a deploy, or
explicitly approve a manual deploy in Render **only after those checks pass**.
Readiness failure keeps an unhealthy replacement out of service, but does not undo migrations.
Use backward-compatible migrations and take a database backup/restore point before risky schema changes.

## 4. Verify each production backend deployment

This is a deliberately **manual, read-only** check. It is not automatically run after every deployment.
Native Render CI gating plus an automatic GitHub post-deploy check on the same commit can create a
circular wait, so this workflow has no `push` or `workflow_run` trigger.

1. GitHub **Settings → Secrets and variables → Actions → Variables → New repository variable**.
2. Set `BACKEND_URL` to `https://onboarding-companion.onrender.com` (no trailing path or credentials).
3. After Render reports a successful deploy, copy that deploy's **full 40-character commit SHA**.
4. GitHub **Actions → Verify backend deployment → Run workflow**.
5. Select branch **main**, paste the SHA into `revision`, and run.
6. Expect `Deployed backend readiness` to turn green. It retries for up to ten minutes to allow
   free-tier cold starts and only succeeds when `/ready` reports database connectivity **and that SHA**.
   A healthy old deployment must not count as success.

The workflow appears after this PR is merged into the default branch. It needs no Actions secrets and
never runs migrations, tests, or writes against Neon. A failure does not trigger an automatic rollback:
inspect Render events/logs and Neon availability, then decide whether a rollback is safe for the schema.
Do not run this workflow against a feature branch; it is restricted to `main`.

Optional local equivalent:

```powershell
python backend/scripts/verify_deployment.py --url https://onboarding-companion.onrender.com --revision <FULL_SHA>
```

## 5. Enable GitHub security features

Under **Settings → Advanced Security** (sometimes **Code security** or **Code security and analysis**):

1. Enable **Dependency graph**, **Dependabot alerts**, and **Dependabot security updates**, where available.
2. Enable **Secret scanning** and **Push protection**, where your plan supports them.
3. Confirm the **Dependabot** tab can read `uv.lock`, `package-lock.json`, Dockerfile and Actions updates.
4. Review Dependabot PRs normally; all CI checks and review requirements still apply.

Do not place Neon credentials in test workflows. All CI databases are disposable pgvector Postgres.
Do not run backend pytest against Neon: fixtures downgrade/truncate the test database.

## 6. Confirm Vercel and testing-team handoff

In Vercel **Project → Settings → Git**, verify production branch `main` and preview deployments for PRs.
Keep root directory `frontend` and the existing `/api/*` rewrite. Frontend deployments remain managed
by Vercel; this change does not gate Vercel production deployment on GitHub CI or trigger it from Actions.
Do not assume a Vercel preview backend is isolated: the current rewrite points to production Render.

No frontend tests were added/run for this change. `frontend/TESTING_FOLLOWUPS.md` remains the source
of the testing team's deferred coverage; lint/build and dependency audits do not fill that gap.
Recheck actual test files and assertions in future reviews before calling that coverage complete.
