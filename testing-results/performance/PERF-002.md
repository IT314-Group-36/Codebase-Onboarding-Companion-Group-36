# PERF-002: Performance Baseline

## Test configuration
- Application: Codebase Onboarding Companion
- Tool: Grafana k6 v2.4.0
- Virtual users: 5
- Duration: 30 seconds
- Endpoints: GET /health, GET /ready, GET /auth/config
- Test type: Lightweight API performance baseline

## Results
| Metric | Result |
|---|---:|
| Total HTTP requests | 435 |
| Requests per second | 14.428 |
| Average response time | 12.58 ms |
| Minimum response time | 2.8 ms |
| Median response time | 8.86 ms |
| P90 response time | 23.42 ms |
| P95 response time | 27.63 ms |
| Maximum response time | 46.94 ms |
| Failed HTTP requests | 0% |
| Successful checks | 435 / 435 |
| Failed checks | 0 |
| Virtual users | 5 |
| Test duration | 30 seconds |

## Endpoint checks
- GET /health: Passed
- GET /ready: Passed
- GET /auth/config: Passed

## Conclusion
All checks passed, with no failed HTTP requests. The tested lightweight
endpoints showed low response times under the baseline workload.

This result does not establish the maximum capacity of the application.
Authenticated repository operations, database-heavy operations, and AI
operations were not tested in this run.

## Evidence
- raw-metrics.json
- summary.json

## Docker resource usage before load testing

| Container | CPU | Memory |
|---|---:|---:|
| Web | 0.00% | 9.555 MiB |
| API | 0.43% | 109.3 MiB |
| PostgreSQL | 0.01% | 46.34 MiB |

Total memory usage: 165.2 MiB

All three containers were running before load testing.
