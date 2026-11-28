# Acceptance-level testing — guide for its owner

**Guidance only: no stakeholder acceptance runs or approvals are implemented/claimed here.**

## Purpose

Acceptance testing asks whether the application meets agreed user needs well enough to be accepted.
It is not another name for unit tests, a browser smoke run, or high code coverage.
Identify who can approve acceptance: product owner, instructor, project sponsor, or designated users.

## Preparation

1. Create a separate acceptance plan with stakeholder-approved criteria and priority.
2. Agree a representative repository and user persona (for example, a developer new to a codebase).
3. Use a release candidate in an isolated environment with realistic data and approved test accounts.
4. Explain static-analysis and AI limitations so users are not asked to approve unsupported guarantees.
5. Define acceptable blockers, defect severity, retest requirements, and approval authority in advance.
6. Reuse system-test evidence only where the acceptance owner agrees it supports a criterion;
   record the reference and approval separately.

## Candidate acceptance scenarios

These are proposed criteria to review with stakeholders, not already-approved requirements.

| ID | User goal / Given | When | Candidate acceptance criterion / Then |
|---|---|---|---|
| ACC-01 | A new developer has an authorized GitHub account and a target repository | They sign in and connect it | They can reach a ready project without handling backend commands or exposing credentials |
| ACC-02 | A project is ready | They review its overview and module map | They can identify the project's purpose, main technologies, entry points, and major responsibilities |
| ACC-03 | The developer wants to understand one file/function | They browse Explorer and request an explanation | They can read source and a useful explanation, with relationships and limitations made clear |
| ACC-04 | The developer has a concrete code question | They ask it and inspect the citations | They can find relevant supporting code and understand that generated answers require verification |
| ACC-05 | A conversation already contains a long answer | They ask a follow-up and return later | They retain understandable conversation continuity without silently losing recent content |
| ACC-06 | The developer plans to modify a known function | They inspect change impact | They can identify likely affected callers/files/tests and understand static-analysis limitations |
| ACC-07 | A repository has beginner-labelled issues, or none are suitable | They open the first-week plan | They receive relevant issue tasks or clearly labelled orientation tasks, not an unexplained empty plan |
| ACC-08 | The developer completes part of the plan | They save progress and return in another session | Their progress remains attached to their own account/repository |
| ACC-09 | A developer needs project history | They inspect scoped commits/contributors | They can understand recent activity without treating contribution percentages as proof of expertise |
| ACC-10 | The AI/provider is unavailable | They attempt a question and follow recovery options | They understand the limitation and can still use documented non-LLM exploration/search features |
| ACC-11 | The developer chooses to remove a chat or indexed repository | They cancel, then intentionally confirm | Cancellation preserves data; confirmation has the promised scope; unrelated data/source repo is preserved |
| ACC-12 | The developer no longer wants saved GitHub access | They disconnect it | They understand credential removal, session retention, and when reauthentication will be needed |
| ACC-13 | Two users use the same deployment | They view and manage their projects/progress | Neither user sees or modifies the other's private information |

## Suggested session protocol

- Give goal-based prompts rather than step-by-step coaching that hides usability problems.
- Observe task completion, misunderstandings, errors, and whether recovery guidance is usable.
- Use stakeholder-approved completion-time/usability targets only if such targets were agreed.
- Capture comments and outcomes without recording tokens, private code, or unnecessary personal information.
- Distinguish a defect from a requested feature outside current scope.
- Record each criterion as accepted, rejected, blocked, or not run; never infer acceptance from automation alone.

## Acceptance record

For every scenario record requirement, persona, release revision, environment, data,
actual outcome, evidence/linked system cases, stakeholder comments, blocking defects,
decision, approver, and date.

Overall sign-off should state which criteria were approved, any explicit exceptions/risks,
what remains blocked, and who authorized the decision. Retest after relevant fixes or release changes.
The white-box assignment supplies no acceptance decision.
