# Frontend testing follow-ups — owned by the testing team

## Status

Vitest test framework and initial white-box test suite have been established.
`package.json` now includes `test`, `test:watch`, and `test:coverage` scripts, and vitest configuration
is located at `vitest.config.js`.

Last updated: 2026-11-19. Initial test coverage covers:
- `src/utils/__tests__/github.test.js` (GitHub URL and branch validation)
- `src/services/__tests__/adapters.test.js` (Data adaptation, error parsing, and task mapping)
- `src/services/__tests__/api.test.js` (HTTP layer, error parsing, streaming, and Q&A payload inspection)
- `src/components/__tests__/Button.test.jsx` (Design system button states and variants)
- `src/components/__tests__/ConfirmDialog.test.jsx` (Modal interaction, cancellation, and escape key handling)
- `src/components/__tests__/StatusBadge.test.jsx` (Cosmic status badges and pulse animations)
- `src/components/__tests__/SearchInput.test.jsx` (Search input interaction and clearing)

## Pending Q&A regression coverage

- [x] Inspect `askCodebaseQuestionStream`'s outgoing JSON: it contains the new question and conversation ID,
  but no `history`, even if unsupported keys are supplied in the hints object. (Tested in `src/services/__tests__/api.test.js`)
- [x] Verify supported `symbol`, `file` and `depth` hints are retained and the callback/conversation-ID
  arguments still reach their correct positions after removal of the history argument. (Tested in `src/services/__tests__/api.test.js`)
- [ ] In the Q&A page, display an answer longer than 4,000 characters, including Unicode/emoji, then send
  a follow-up. The displayed answer must remain intact, and earlier messages must not be replayed in the request.
- [ ] Verify clarification/retry flows still use the current conversation and supported target hints.
- [x] Cover request failures and streaming event delivery without introducing browser-owned model context. (Tested in `src/services/__tests__/api.test.js`)

Backend tests in `backend/tests/test_qa_history.py` independently cover long saved answers, old-client
history compatibility, forged history, ownership and bounded database context. They do **not** prove
frontend request construction or UI behavior is tested.

## For future project reviews

1. Recheck `frontend/package.json` and test/spec files, including any newly added test directories.
2. Tell the project owner when frontend test infrastructure/files have appeared. Inspect the actual
   assertions before marking the checklist complete; a new folder alone is not evidence of this coverage.
3. Report any remaining gaps, and update this status with the paths of the testing team's tests.

This is a persistent handoff note, not an automatic file watcher. Tests can be checked and reported
during a later project review; folder changes cannot trigger an assistant notification on their own.
