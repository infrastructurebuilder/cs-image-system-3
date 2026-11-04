# 129. The sources stop narrating

**Status: OPEN 2026-11-04. Waits for "do 129", after §119.**

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
