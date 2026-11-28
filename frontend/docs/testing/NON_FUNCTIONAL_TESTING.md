# Non-functional testing — implementation guide for its owner

**Guidance only: no performance, load, security, accessibility-audit, or reliability suite is implemented here.**

## Agree measurable requirements first

Performance and quality limits must come from approved requirements or an explicitly labelled proposed
baseline. Do not invent a passing threshold after seeing results. Record device, CPU/network profile,
browser, dataset size, deployment tier, and whether external services were real or controlled.

| Area | Proposed method/tooling | Measurements/evidence | Important cases |
|---|---|---|---|
| Page performance | Lighthouse, browser performance tools | LCP, INP, CLS, transfer size, startup timing | Login, dashboard, Explorer, graph, Q&A; cold/warm navigation |
| Large-repository responsiveness | Browser traces and representative fixtures | Interaction latency, long tasks, memory | Large file trees, many graph nodes, long code files, long chat histories |
| Streaming responsiveness | Browser network/performance timeline | First visible token latency, input responsiveness, completion behavior | Slow token delivery, Unicode, long responses, provider stalls |
| Accessibility | axe-core/Lighthouse plus manual assistive-technology review | Violations, keyboard records, screen-reader findings | All screens; modals, source tree, graph controls, live announcements |
| Cross-browser/device compatibility | Real browsers or a browser grid | Functional/visual compatibility matrix | Approved desktop/mobile browsers and viewport sizes |
| Reliability/recovery | Controlled network failures and isolated restarts | Recovery time, readable errors, stale-state findings | Offline/reconnect, interrupted streams, expired sessions, polling failures |
| Security/privacy behavior | Authorized review/proxy tools and focused manual checks | Redacted observations, exposed-data findings | Credentials, browser storage, source/issue rendering, unsafe content, ownership boundaries |
| Load/capacity | k6/JMeter or equivalent against an authorized disposable stack | Throughput, response percentiles, failure rates, saturation | Concurrent reads/streams, indexing pressure, rate-limit behavior |

Frontend bundle analysis alone does not establish backend capacity; API load tests alone do not establish browser responsiveness.

## Safe environment setup

1. Create a separate branch and an agreed test plan.
2. For UI measurements, serve an optimized production build rather than a development server.
3. For integrated load/reliability, provision a disposable database, repository data, and test accounts.
4. Declare which GitHub/AI calls are mocked. Provider delays and quotas can dominate measurements.
5. Get explicit authorization for load/security tests and agree maximum concurrency/request budgets.
6. Never load-test public production, send private code to unapproved services, or use real user credentials.
7. Keep runs repeatable: warm-up policy, sample count, test duration, and cleanup must be documented.

## Suggested cases

| ID | Case and procedure | Expected requirement to agree before execution |
|---|---|---|
| NF-01 | Measure cold and warm login/dashboard navigation under a fixed device/network profile | Approved timing and layout-stability budgets |
| NF-02 | Open a large file/tree and repeatedly navigate/filter | Approved interaction budget; no persistent UI freeze |
| NF-03 | Expand a large cyclic/shared graph, search, zoom, and collapse repeatedly | Approved responsiveness and memory-growth bounds |
| NF-04 | Receive a long streamed Unicode answer while navigating/scrolling | Responsive controls, stable content, no runaway resource use |
| NF-05 | Repeat open/close/navigation cycles and compare heap/listener behavior | No sustained unbounded growth after settling/cleanup |
| NF-06 | Audit pages with automated tools and keyboard/screen reader | Agreed accessibility standard, including manual exceptions/defects |
| NF-07 | Enable OS/app reduced motion and test animations/announcements | Preference honored without hiding essential state |
| NF-08 | Disconnect network during polling, save, and streaming; restore it | Clear recovery instructions; no false saved/success state |
| NF-09 | Use revoked sessions and another test user's repository IDs | No unauthorized content exposure; coherent sign-in recovery |
| NF-10 | Review storage, URLs, logs, traces, and rendered untrusted text | No credential leakage or unsafe execution under agreed threat model |
| NF-11 | Apply bounded concurrency to an isolated stack | Agreed percentiles/error rates; limits and overload fail gracefully |
| NF-12 | Compare approved browser/device combinations | Documented compatibility criteria; no blocking incompatibility |

## Reporting

Publish distributions and repeat-run data, not only a single average or a tool score.
Separate frontend, backend, third-party, and test-environment bottlenecks.
Report blocked measurements honestly; never reuse white-box code coverage as quality evidence.
The owner may later add tooling/configuration/CI on their own branch; none is supplied by this guide.
