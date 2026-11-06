# 128. Tests named for behaviour

**Status: OPEN 2026-11-04; RE-EVALUATED 2026-11-05 after §125. Waits
for "do 128"; nothing blocks it.**

**Re-evaluated 2026-11-05.** The drift the stage names continues
while it waits: the root suite is 138 files, 129 with the `v2_`
prefix and 49 named for a stage, bundle, gate or defect list; of the
five test files §121 to §125 added, two took the `v2_` prefix and
none a stage name (the rule is not yet a test, so it is not yet
held). The five packages without tests are the same five (ansible,
contract, contract-example, dummy, tf-s3-state; tf-gcp has one), and
the missing `packages/contract/tests` tripped three agents'
acceptance commands this week, which is item 6's case made again.
Item 4 (docker in the golden) is unchanged. Recommended: item 2's
rule and item 1's naming rule land first as tests with today's
counts as ceilings that only fall (the §124 closure test's pattern),
then the renames.

49 of 128 root test files (427 tests) are named after a stage, bundle,
gate or defect list; 36 files pin the literal text of the Justfile, a
README, the CI workflow or a guide, one of them the order of substrings
inside a recipe; 739 assert lines compare an English sentence against
output (REEXAMINE1 §3.4). 123 files carry a `v2_` prefix with V1
retired. Six gate-1 tests have been skipped unconditionally since
2026-09-11 beside a 252 KB fixture kept "as evidence". The frozen
fixture declares no docker runtime, so the newest runtime's emission
is pinned only by stage-named tests. PARITY's proposed drift tests
were never written. Five packages have no tests of their own.

1. Rename: each stage-named file is split or renamed by the behaviour
   it holds (a table old → new in the squash); `v2_` goes everywhere
   (`v2_support.py` included); the golden's name stays.
2. Prose pins become behaviour: `just --summary` names the recipe and
   the recipe runs in its dry form; the workflow parses and names its
   jobs; a CLI assertion keeps the exit code and one stable token,
   not the sentence. Those with no behaviour behind them go.
3. Dead: the skipped gate-1 tests and `tests/fixtures/v1_baseline/`
   go; git holds them.
4. The golden covers docker: the frozen fixture gains the docker
   runtime (the commented block in `runtime-builders.yml`, named for
   the fixture's synthetic daemon) and the golden is re-frozen once,
   the diff reviewed as the docker emission.
5. PARITY's tests, real: every registered model's fields appear in
   CONFIGURATION; every recipe in `just --summary` appears in
   OPERATIONS; every plugin package appears in README's list; every
   CLI command in OPERATIONS's table; the starter count is one
   constant the docs tests read. PARITY.md's column points at them.
6. The packages without tests (ansible, contract, contract-example,
   dummy, tf-s3-state; tf-gcp with one) each gain the test that will
   travel with them when they move: a dry generation of a tree
   declaring only them.

**Out of scope**: documentation edits beyond the minimum that makes a
parity test green (the rest is the rolling documentation stage).

**Acceptance**: `just test` green; the test count falls only by the
six deleted; the golden re-frozen once with its diff in the squash;
one squash, branch kept. Records: the squash; this section goes at
"merge 128".
