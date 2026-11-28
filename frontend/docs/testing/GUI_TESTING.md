# GUI testing — implementation guide for its owner

**Guidance only: not implemented or executed by the white-box assignment.**

## Scope

Verify what a user sees and interacts with: controls, layout, navigation, visible states,
responsiveness, and keyboard operation. Do not inspect internal branch coverage to decide GUI success.
Coordinate formal accessibility audits with the non-functional owner.

## Suggested setup

1. Create a separate GUI-testing branch.
2. Choose a real-browser runner such as Playwright or Cypress, or document a manual protocol.
3. Install/configure it in that branch only. Keep browser specs separate from white-box `tests/`.
4. Use a production frontend build for representative CSS/layout. Declare browser versions and viewports.
5. For focused GUI behavior, control API responses at the network boundary. Include delayed, empty,
   failed, and successful responses. Unexpected requests must not fall through to production.
6. Use isolated storage/session state per case. Fix dates/data where needed for repeatable screenshots.
7. Prefer roles and accessible names over fragile CSS selectors. Use condition-based waits, not arbitrary sleeps.
8. Save failure screenshots and traces; a separate CI job can be added by this assignment's owner.

## Priority cases

| ID | Priority | Preconditions and actions | Expected visible behavior |
|---|---|---|---|
| GUI-01 | High | Open a protected deep link as an anonymous user | Login is shown; protected content is not briefly exposed |
| GUI-02 | High | Check login while session lookup is pending, then with sign-in unavailable | Clear loading/unavailable messages; actions reflect current state |
| GUI-03 | High | Open repository picker, filter case-insensitively, load another page, select a private repo | Filtering and pagination retain selection; private/public status is understandable |
| GUI-04 | High | Paste empty, malformed, and valid URLs; toggle optional token field | Clear validation; password masking; selected repo summary matches input |
| GUI-05 | High | Connect a repo with queued, indexing, ready, and failed API states | Correct progress/error states; retry and next-step buttons appear appropriately |
| GUI-06 | High | Open a cited file/line range in Explorer | Correct file and range are shown; tree, source, and details agree |
| GUI-07 | Medium | Change editor theme, navigate away, and return | Chosen colors and preference persist; source remains readable |
| GUI-08 | High | Stream an answer containing more than 4,000 characters, Unicode, and emoji; ask a follow-up | Existing answer remains intact; stream/loading controls settle correctly |
| GUI-09 | High | Show an ambiguous impact answer; choose a target; simulate failure; retry | Clarification is understandable; retry recovers without duplicate visible failed pairs |
| GUI-10 | High | Show an LLM-unconfigured response, switch to Code Search | Useful alternative is visible and search results open relevant source |
| GUI-11 | High | Open new chat, then cancel/confirm chat deletion | New chat does not imply old chats were erased; destructive action requires confirmation |
| GUI-12 | High | Change task state; simulate a failed save and repeated rapid clicks | Optimistic state rolls back on error; no misleading duplicate transitions |
| GUI-13 | Medium | Combine status/source filters, expand task details, request guides, sync issues | Filter counts, empty messages, expanded content, and busy states stay coherent |
| GUI-14 | High | Render actual dependency nodes/edges; expand/collapse shared branches; select a node | Graph interaction works in a real browser; inspector and Explorer destination match selection |
| GUI-15 | Medium | Exercise graph search, filters, zoom, fit, fullscreen, and Escape | Controls remain operable; viewport and selected context are understandable |
| GUI-16 | Medium | Change history scope between whole repo, folder, and file; simulate errors/empty results | Correct selection and readable results; retry does not hide useful history unnecessarily |
| GUI-17 | High | Cancel/confirm repository deletion and GitHub disconnect | Clear distinct warnings; list changes only after successful deletion; session intent is explicit |
| GUI-18 | High | Open each modal, use keyboard only, and exercise loading state | Accessible name/description, focus placement/trapping/restoration, Escape/backdrop rules, no double submission |
| GUI-19 | Medium | Repeat key pages on narrow/mobile and desktop viewports | No inaccessible controls, clipped dialogs, unreadable code, or unusable graph controls |

## Particular areas to inspect

- The confirmation dialog focuses itself, but a complete focus trap/restoration should be verified.
  Its current backdrop invokes cancellation even while loading; agree expected behavior and file a defect
  if that violates the requirement. Do not silently approve it.
- A graph algorithm unit test does not verify actual React Flow sizing, pointer interaction, or camera behavior.
- A page shown with mocked progress does not demonstrate persistence in a real backend.
- Test slow responses and navigation away/switching repositories; stale content must not overwrite current context.

## Evidence and completion

Record browser/version/viewport, frontend revision, mocked-versus-real API mode, expected and actual
results, screenshots, and defect IDs. Separate visual baselines from functional interaction assertions.
Agree required browsers/viewports with the team before claiming coverage complete.
