# System testing — black-box case guide for its owner

**Guidance only: these cases are planned, not implemented or executed here.**

## Scope and oracle

Evaluate the integrated product from externally observable behavior and documented requirements.
Do not derive pass criteria from function names, private state, or branch coverage.
The oracle is the requirement/API contract and user-visible result.

Browser automation with mocked API responses is frontend-only testing, not proof that the entire system works.
If external GitHub/AI services are controlled, document that boundary and the resulting limitations.

## Environment and data

1. Create a separate system-testing branch and case register.
2. Start the production-like frontend and an isolated real backend/database. Record exact revisions.
3. Use test-only OAuth/account/session setup approved by the team; never copy production cookies or secrets.
4. Prepare two test users and controlled public/private repositories, an invalid/inaccessible repo,
   a branch/revision fixture, a small codebase with known dependencies/source ranges, and labelled issues.
5. Define deterministic AI/provider fixtures or a constrained live-provider budget. Do not equate model wording
   with correctness; verify grounding and relevant observable results.
6. Store evidence securely; clean up indexed data, test conversations, issue fixtures, and accounts after runs.
7. Do not run backend destructive migration/truncation fixtures against production or a shared persistent database.

## Black-box cases

| ID | Priority | Preconditions / external actions | Expected result |
|---|---|---|---|
| SYS-01 | High | Anonymous user opens a protected repository URL | Sign-in required; no repository data disclosed |
| SYS-02 | High | Complete sign-in using approved test OAuth flow; refresh; sign out | Session persists correctly, then protected access is denied after sign-out |
| SYS-03 | High | Select and connect a controlled public repo | Registration completes asynchronously; progress reaches ready; overview reflects known repo |
| SYS-04 | High | Connect a private repo accessible to the test account | Indexing works using authorized credentials without displaying the token |
| SYS-05 | High | Submit malformed URL, missing repo, wrong branch, or inaccessible private repo | Clear refusal/failure; no misleading ready state |
| SYS-06 | High | Index known revision, browse files, follow a citation | Source path/range/content agree with the indexed commit |
| SYS-07 | High | Ask a grounded question with a known source answer | Relevant answer/citations; no invented source reference is accepted as valid evidence |
| SYS-08 | High | Send a long Unicode question/answer and a follow-up; reload saved conversation | Content remains intact or explicitly marked as a bounded older excerpt; context is coherent |
| SYS-09 | High | Ask an ambiguous impact question, pick a target, retry a transient failure | Correct conversation/target is retained; result corresponds to selected target |
| SYS-10 | High | Disable or fail the LLM; use available non-LLM functions | Useful error/fallback; search and graph functions remain usable where documented |
| SYS-11 | High | Start new chat; cancel deletion; confirm deletion; hit replacement-chat quota | New chat preserves old chats; cancel preserves data; delete removes target data; quota does not falsify successful deletion |
| SYS-12 | High | Open task plan, change state, reload/sign back in | Saved state persists for the same user/repository |
| SYS-13 | High | User B requests User A's repositories, chats, source, and progress | Access denied/no cross-user data exposure |
| SYS-14 | High | Sync labelled issues; repeat; simulate a failed later sync | Correct issue-derived/orientation tasks; no duplicate corruption; last good data retained where specified |
| SYS-15 | Medium | Request AI task guides after saving progress | Guides do not reset existing progress |
| SYS-16 | High | Request change impact for a known symbol/file; view map | Known static relationships appear, with stated approximation limits |
| SYS-17 | Medium | Retrieve history for whole repo/folder/file; use an empty repo | Correct scope and empty-state behavior; bounded results and contributor context |
| SYS-18 | High | Reindex unchanged/changed repository; include failed reindex | Correct updated data without duplication; previous readable data retained on failure where promised |
| SYS-19 | High | Confirm repository deletion and reload/list again | Indexed data and associated owned records removed; source GitHub repo unaffected |
| SYS-20 | High | Disconnect GitHub access while staying signed in | Saved credential removed; session remains; private/GitHub-dependent actions explain reauthentication |
| SYS-21 | High | Expire/revoke session or token mid-operation | No unauthorized disclosure; understandable recovery; no falsely saved/ready state |
| SYS-22 | Medium | Induce rate/quota limits and transient network/provider failures safely | Correct refusal/retry information; no duplicate destructive action or silent data loss |

## Execution notes

Use observable state (including reload/re-query results) to verify persistence, not a toast alone.
Check repository/account isolation with separate sessions, not just separate browser tabs sharing cookies.
Record whether live GitHub and model behavior were exercised.

## Deliverables

Requirement-to-case matrix, environment/dependency diagram, reproducible data/preconditions,
actual results, evidence, defects, rerun results, and cleanup log. Mark unexecuted or blocked cases explicitly.
Coordinate performance/security stress cases with the non-functional owner rather than running them incidentally.
