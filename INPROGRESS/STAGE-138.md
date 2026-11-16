# 138. Hygiene bundle XXX

**Status: OPEN 2026-11-15. The open bundle; takes items as they are
found. Waits for "do 138". None of its items blocks a release.**

The findings carried out of [§137](../docs/CHANGES.md#s137)
(hygiene bundle XXIX); none is blocking, each its own commit on the
bundle's branch.

1. The golden's fixture directory is still `tests/fixtures/v2_golden`
   and the harness's run class is still `V2Run` (`tests/harness.py`,
   `tests/golden.py`); the `golden-regen` recipe, the tests and many
   package READMEs name the directory (about 450 references outside
   the frozen history). A rename moves every one of the golden's 148
   paths, though not a byte of their content. **YOUR DECISION:** leave
   them (the default: the directory is data, its name harms nothing,
   and every README link would move), or rename the directory and the
   class in one commit with every reference, the golden's content
   byte-identical under its new path (found by §137 item 2).

**Acceptance**: each item its own commit; the bar and
`just full-test-legs` green; the golden's content unchanged. Records:
the squash message; this file goes at "merge 138".
