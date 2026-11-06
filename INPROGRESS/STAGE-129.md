# 129. The sources stop narrating

**Status: OPEN 2026-11-04; RE-EVALUATED 2026-11-05 after §125. Waits
for "do 129"; nothing blocks it.**

**Re-evaluated 2026-11-05.** The count grew while the stage waited:
1,173 stage, hygiene, finding and date tokens across 218 source files
under `packages/*/src` (690 in `base` alone on 2026-11-04), of which
106 say "stage 120" to "stage 125" and were written this week by the
seam stages themselves (`# a model holds no context (stage 124 shim)`
and its kin); the Justfile carries 40, `pyproject.toml` 9,
`tfmodules/` 11, the fixture's comments 85. Every stage adds more
until the rule is a test. Recommended: item 1's grep-test lands
first, with today's count as a ceiling that only falls and a rule
that a new token fails the bar, in the open hygiene bundle or as the
first commit of this stage; the cleanup follows. The allowed form is
unchanged: the behaviour's name, or a CHANGES reference.

690 stage, date and finding tokens sit in `base`'s sources alone and
207 source files carry at least one; 43 in the Justfile, 11 in the
terraform modules; the root `pyproject.toml` carries a paragraph
beginning "stage 64: … found by the reference configuration's first
CI run" (REEXAMINE1 §3.4, §4.3). A docstring that says "stage 75 step
2" points into a worksheet that is deleted on landing. The working
memory of a session belongs in the worksheets, the squash messages and
the private notes, not in code the people who were not there will
read.

1. Docstrings and comments: each "stage N", "hygiene X", "FNN" and
   date becomes the behaviour's name or goes; where the why matters, a
   reference to the CHANGES entry (§119) is the one allowed form. A
   grep-test over `packages/*/src`, `Justfile`, `pyproject.toml` and
   `tfmodules/` holds zero.
2. The fixture's comments (`tests/fixtures/config`) the same way; the
   golden does not read comments.
3. Test docstrings keep the behaviour; this stage cleans what [§128](STAGE-128.md)'s
   renames did not reach.
4. The Justfile's comments name each recipe's purpose; the release
   family's history moves with the script in [§130](STAGE-130.md).

**Out of scope**: any behaviour; any rename; the documents (§119).

**Acceptance**: emission byte-identical; the grep-test green; `just
test`; one squash, branch kept. Records: the squash; this section goes
at "merge 129".
