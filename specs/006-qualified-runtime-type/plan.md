# Implementation Plan: A runtime written by its qualified word works as its bare word does

**Branch**: `feature/006-qualified-runtime-type` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-qualified-runtime-type/spec.md`

**Users served**: operators; an adopting team.

## Summary

A runtime entry's vendor-image query asks the image-source catalog for
a block under the runtime's `type:` word exactly as the tree wrote it,
while every block is keyed by the bare word, so a runtime written
`docker-runtime/docker` or `aws-runtime/aws` finds no block: validation
refuses its OS builder entries, and an entry that declares part of its
own query passes with a thinner query and would bake from it
([research.md](research.md) R1, reproduced on the shared fixture and on
the core fixture). The defect is in the kit's catalog,
[image_sources.py](../../packages/base/src/cs_image_system/base/image_sources.py)
lines 357 to 369, reached from
[os_builder_runtime_config.py](../../packages/base/src/cs_image_system/base/models/os_builder_runtime_config.py)
lines 203 to 226.

The approach, decided in [research.md](research.md):

1. The catalog resolves the word it is asked for to the one installed
   runtime it names, by the rule `set_declared` already uses (R3).
2. The release's layer answers from that runtime's own plugin part,
   under its bare word, and from no other part, so two runtimes of one
   bare word each get their own plugin's blocks (R4).
3. The tree's layer answers under the runtime's bare word and, landing
   on it, under its qualified word; a key that names no installed
   runtime is named by `validate` in a warning (R5, R6).
4. The stand-in is listed by the registry's word, and the bootstrap
   interview finds a runtime written qualified (R7, R8).
5. No golden moves; the kit takes a PATCH; the contract is untouched
   (R4, R12).

The search for the defect's reach found the runtime word read in one
more place (the bootstrap interview, R8), and found that the class
words of state backends, OS builders and storage builders, written
qualified, load but change the emission (R2). That second finding is
not a runtime's word; it is the operator's decision **D1** below, by
default a specification of its own.

## Technical Context

**Language/Version**: Python 3.13 (uv workspace, 19 packages)

**Primary Dependencies**: the kit (`packages/base`: the image-source
catalog, the OS builder runtime entry); the engine (`packages/engine`:
`validate`, the modification tests, the bootstrap facts); the test kit
(`packages/system`: the double runtime) for the tests

**Storage**: N/A (the catalog is in-process, read from package data and
the tree's `cfg/image-sources*.yml`)

**Testing**: pytest through `just test` (lint, type check, unit tests,
the isolated runs), with both goldens as the guard that nothing moved

**Target Platform**: your local machine and the CI runners

**Project Type**: library and command line (a compiler of
configuration into infrastructure code, with a plugin SDK)

**Performance Goals**: no slower than today; each runtime's part is
read once per run and cached, as the merged layer is

**Constraints**: the bare form's emission is byte-identical (FR-007,
Constitution IV); a test does not assert wording (Constitution IX); no
provider plugin and no contract member changes (spec, Assumptions); no
cloud is touched before the release step

**Scale/Scope**: one module's lookup (about 60 changed lines), one
validation line, two bootstrap comparisons; two runtime families in
this workspace (the AWS family, the docker family) and the test kit's
double; the Google Cloud family proves FR-008 in its own repository.
The reach beyond the runtime word was NEEDS CLARIFICATION, resolved by
search in research R2 into the operator's decision D1

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan meets it | Result |
| --- | --- | --- |
| I. Purpose first | Serves operators and an adopting team, named in the spec | Pass |
| II. Acceptance is executable | Every story ends in a test run by `just test-one` and in `just test`; FR-008 ends in the Google Cloud family's test after the release; [quickstart.md](quickstart.md) steps 1 to 8 | Pass |
| III. Nothing irreversible by default | No apply, no plan gate touched; validation gains a warning, never a destroy | Pass |
| IV. The emission is the contract | Both goldens must not move (R4 says why they cannot); the qualified trees are compared with the bare emission file for file, never accepted | Pass |
| V. Public by construction | No secret read or written; the warning prints a key and family the tree already holds | Pass |
| VI. Layers and no interference | The change is in the kit and the engine; nothing imports back. A runtime's blocks come from its own plugin's part only, so one plugin can no longer answer for another's runtime (FR-003): interference falls | Pass |
| VII. Budget, subtraction | Below: a small source growth, with its reason | Pass |
| VIII. One source per fact | A block's one source is its runtime's own part; CONFIGURATION 5a stays the reference, the READMEs link it | Pass |
| IX. Tests guard behaviour | The new tests assert queries, emissions and which plugin answers, not wording | Pass |
| X. What a change makes false | Listed below | Pass |

**Re-check after design**: still passes. The design adds no package,
no contract member and no protocol; one cost is recorded under
Complexity Tracking (FR-008 met for the runtime word, the storage and
state words waiting on D1).

### Budget (Principle VII)

Measured on `develop` at `35446e3f` on 2026-11-21 (the method of spec
004's T002: lines of `*.py` under `packages/*/src` and `src`; tracked
`*.py` under `tests` and `packages/*/tests`, fixtures left out; tests
as `just test-one --collect-only -q` counts them).

| Measure | Today | Expected | Reason for any growth |
| --- | --- | --- | --- |
| Workspace packages | 19 | 19 | none added or removed |
| Source lines | 54,249 | +45 to +80 | the catalog resolves a word to its runtime and reads its own part (about 30); the tree's two keys and the finder of keys that name nothing (about 20); `validate`'s warning (about 6); the stand-in's listed word and the bootstrap comparisons (about 8). Nothing is deleted: the lookup gains the step it lacked |
| Test lines | 46,069 | +220 to +350 | the catalog cases (about 80); the two test-only runtime plugins of story 3 and their load (about 120); the qualified core fixture (about 25); the shared fixture's rewrite reaching runtimes (about 10); the bootstrap case (about 15) |
| Tests | 2,610 | +9 to +14 | the cases above, one or more per scenario of stories 1 to 3 and per edge case that has behaviour |
| Contract protocol members | 0 | 0 | the contract does not change |
| Golden files | 117 shared, 32 core | 117, 32 | nothing moves |

### Statements this change makes false (Principle X)

Corrected in the same work (research R13):

- [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) section 5a: the
  `sources` row, "The stack" step 1, and the merge paragraph.
- [packages/base/README.md](../../packages/base/README.md), "Image
  sources": the collision sentence and the stand-in's block.
- [image_sources.py](../../packages/base/src/cs_image_system/base/image_sources.py):
  the module docstring, `merge_entries`, `block` and `stand_in_types`.
- [os_builder_runtime_config.py](../../packages/base/src/cs_image_system/base/models/os_builder_runtime_config.py):
  `runtime_type()`'s docstring.
- [bootstrap/facts.py](../../packages/engine/src/cs_image_system/engine/bootstrap/facts.py):
  `runtimes_of_type`'s docstring.
- Spec 005's record ([plan.md](../005-relocate-gcp-provider/plan.md)
  line 47, [tasks.md](../005-relocate-gcp-provider/tasks.md) T028): a
  note that this specification mends the defect.
- [specs/README.md](../README.md), row 006: its state.
- In the Google Cloud family's repository: `test_qualified_words.py`'s
  docstring ("proves the load, not a run") and its next release's
  notes.

## Project Structure

### Documentation (this feature)

```text
specs/006-qualified-runtime-type/
├── spec.md
├── plan.md              # this file
├── research.md          # R1 to R13
├── data-model.md        # the words a query is looked up by
├── quickstart.md        # how to prove the feature
├── contracts/
│   └── image-source-keys.md   # a tree's keys; what the catalog answers
├── checklists/
│   └── requirements.md
└── tasks.md             # from /speckit-tasks
```

### Source Code (repository root)

```text
packages/base/src/cs_image_system/base/
├── image_sources.py                       # the word resolved; own part; tree keys; stand-in listed word
└── models/os_builder_runtime_config.py    # docstring only
packages/engine/src/cs_image_system/engine/
├── commands/validate.py                   # one WARNING per tree key that names no runtime
└── bootstrap/facts.py                     # a qualified runtime word found by its section's word
packages/base/pyproject.toml               # the kit 0.2.1 -> 0.2.2
tests/test_image_sources.py                # the catalog cases
tests/test_a_qualified_tree_emits_what_the_bare_tree_emits.py   # the rewrite reaches runtime_builders.type
tests/test_bootstrap.py                    # the bootstrap case
packages/system/tests/test_core_golden.py  # the qualified core fixture emits the core golden
packages/system/tests/test_qualified_runtime_words.py           # new: story 3 through a load
docs/CONFIGURATION.md, packages/base/README.md                  # Principle X
```

**Structure Decision**: no package is added or moved. The change is in
the kit's catalog and two engine readers; the tests are placed so that
none needs the AWS family (research R10), and survive spec 007.

## Delivery order

1. The catalog: resolution, the runtime's own part, the tree's keys,
   the stand-in's listed word; its cases in `tests/test_image_sources.py`.
2. `validate`'s warning; the bootstrap comparisons and their case.
3. The whole-run proofs: the qualified core fixture, the shared
   fixture's rewrite, story 3's two plugins.
4. The documents of Principle X; the kit's version.
5. The release (D2), then the Google Cloud family's whole run and its
   release (R11).

Each step ends with `just test` green before the next.

## How this survives spec 007

Spec 007 takes the AWS family out of this workspace. No test this plan
adds needs it: the catalog cases use stand-in parts, story 3 and the
core fixture use the test kit's double runtime (the vehicle spec 007's
research R6 keeps here), and the shared fixture's rewrite qualifies
whatever runtimes the fixture declares, so after spec 007 it covers the
docker family's runtime alone. The AWS family's repository then proves
its own qualified word against its own fixture, as the Google Cloud
family's does (research R10). The two specifications touch different
code and may land in either order.

## Complexity Tracking

No constitution principle is violated. One cost is recorded so it can
be rejected.

| Cost | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| Under D1's default, FR-008's whole run in the Google Cloud family writes the runtime and instance words qualified and keeps its storage and state words at the load (research R11) | Those two words move the emission (a state backend's `backend "<namespace>/<word>"` is not valid OpenTofu) until the class-word defect of R2 is fixed, and that fix touches every state plugin and the recorded-word rule, which this spec says it does not | Widening this spec to every builder's class word is D1's other answer: it is open to the operator, and changes the spec's scope and its assumption that no plugin changes |

## Definition of done (constitution 1.2.0)

`/speckit-tasks` ends the task list with these, in order, each with a
record of what was done and its evidence:

1. `/speckit-converge` after the last implementation task, and every
   task it appends done.
2. The quickstart walked step by step on the final code, each result
   recorded, and any box it corrects bumped.
3. The squash-merge of `feature/006-qualified-runtime-type` into
   `develop`, the branch kept.
4. The release of D2, every run it starts passed (`just release-watch
   <version>`), the reference has taken it (`UV_REFRESH=1 just take
   <version>`) with its drift check green; the Google Cloud family's
   release carrying R11's test, its runs passed.
5. `spec.md`'s status line and the row for 006 in `specs/README.md`
   say **complete**, with the date.

## Decisions in this plan

**Chosen** by this plan (the operator may overturn any), one line each:

- R3: the word is resolved in the catalog, by the rule `set_declared`
  already uses, not in the model and not by rewriting the word.
- R4: a block comes from the resolved runtime's own plugin part; what a
  family IS still comes from the merged declared parts.
- R4: the merge's collision line is not said for two runtimes that
  share a bare word and each own their block.
- R5: a tree's bare key answers either form; a qualified key answers
  one plugin's runtime and lands on the bare key's block.
- R6: a tree key that names no installed runtime is a `validate`
  WARNING, not a refusal.
- R7: the stand-in is listed by the registry's word, and `--stand-in`
  reads either form.
- R8: the bootstrap interview's runtime lookups read a qualified word
  by its name part; `declared_classes` is left as it is.
- R10: the tests are placed so none needs the AWS family.
- R11: the Google Cloud family's test gains a whole dry run once the
  fix is released.
- R12: the kit 0.2.1 to 0.2.2 (PATCH); the contract unchanged.

**YOUR DECISION** (the operator's, each with its default):

- **D1. The class words of state backends, OS builders and storage
  builders** (research R2). Written qualified, they load but move the
  emission (22 of the shared fixture's 117 files; a state backend's
  root gets `backend "tf-s3-state/s3"`). **Default: a specification of
  its own, written next; this one stays on the runtime word.** Why:
  the fix touches every state plugin and reverses part of the
  recorded-word rule, both outside this spec's stated scope, and the
  runtime fix stands without it. Say "widen 006" to amend this spec
  instead.
- **D2. The release that carries the fix** (research R12). **Default:
  0.1.13, a final release of this repository after the merge, then the
  Google Cloud family's next release (0.2.1) with R11's test.** Why:
  FR-008 cannot be met without both. Say "ride spec 007's release" to
  carry it in the next release spec 007 cuts instead.

No NEEDS CLARIFICATION remains.

## Spec statements to amend

The spec's Input says every other qualified word (instance, storage,
state builders) "already works". It loads; it does not emit as the bare
word does, for the storage and state builders (research R2). Under D1's
default the spec gains one sentence saying so and naming the
specification that will mend it; FR-008 then reads "drive a whole run
for the qualified runtime word". Under "widen 006" the spec is amended
by `/speckit-clarify` and this plan is redone.

## Operator decisions of 2026-11-21

Asked one at a time after planning; each supersedes the default above where they differ.

- D1: the other builder kinds' qualified words are a separate specification, written next; this one stays on the runtime word, and the spec's input line is amended.
- D2: one final release carries specs 002, 003 and 006 together; then the Google Cloud family's 0.2.1 carrying its new test.
- Order: 008, then 003, then 007; 006 fits between.
