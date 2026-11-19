# Frontend testing follow-ups — owned by the testing team

## Status

Frontend tests are deliberately deferred at the project owner's request. No frontend test framework,
test files, test scripts, browser tests or frontend request smoke tests were added for the
server-owned Q&A history cleanup. Lint/build checks are not substitutes for these tests.

Last checked: 2026-11-19. `package.json` has no test script, and no frontend test/spec files were found.

## Pending Q&A regression coverage

- [ ] Inspect `askCodebaseQuestionStream`'s outgoing JSON: it contains the new question and conversation ID,
  but no `history`, even if unsupported keys are supplied in the hints object.
- [ ] Verify supported `symbol`, `file` and `depth` hints are retained and the callback/conversation-ID
  arguments still reach their correct positions after removal of the history argument.
- [ ] In the Q&A page, display an answer longer than 4,000 characters, including Unicode/emoji, then send
  a follow-up. The displayed answer must remain intact, and earlier messages must not be replayed in the request.
- [ ] Verify clarification/retry flows still use the current conversation and supported target hints.
- [ ] Cover request failures and streaming event delivery without introducing browser-owned model context.

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
