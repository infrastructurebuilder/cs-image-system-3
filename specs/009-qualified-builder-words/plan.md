# Implementation Plan: Every builder written by its qualified word works as its bare word does

**Branch**: `feature/009-qualified-builder-words` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-qualified-builder-words/spec.md`

**Users served**: operators; an adopting team; a plugin author.

## Summary

A builder entry written by its qualified class word loads the right
class, and then the word as written reaches what the run emits: the
converter keeps a written namespace on the model's `type_`
([orchestrator.py](../../packages/engine/src/cs_image_system/engine/orchestrator.py)
lines 982 to 999), and every reader after the load copies it out. With
every builder kind but runtimes written qualified, 23 of the shared
fixture's 117 files move ([research.md](research.md) R1, reproduced):
nine roots get `backend "tf-s3-state/s3"` or `backend
"local-state/local"`, which a full `tofu init` refuses; the Packer
builds' OS update comments, `meta-state/state-locations.yaml`,
`meta-state/storage.yaml` and `meta-state/identity.yaml` name the
qualified word. Beyond the word, two plugins that register one bare
word cannot be used in either qualified form: the loader finds a
model's builder by the bare name and meets the ambiguity
([config_loader.py](../../packages/engine/src/cs_image_system/engine/config_loader.py)
lines 992 to 994, R3).

The approach, decided in [research.md](research.md):

1. The converter reads a builder's class word once, at the load, as the
   word the registry lists its class by: the bare word while that class
   alone answers to it, the qualified word where two classes share it
   (R6, R7). Every reader after the load, in the core and in every
   plugin, then reads that word; no provider plugin changes.
2. The loader finds a model's builder class by the model class's own
   registration key (R8).
3. The Terraform collector labels a backend, and a consumer's
   remote-state `backend`, with the backend kind's own type, OpenTofu's
   word (R9).
4. The bootstrap interview finds a state backend written qualified
   (R11).
5. No golden moves; the Terraform libraries take a PATCH; the kit's code
   and the contract are untouched (R15).

The runtime word is left to spec 006 by default (**D1**); the release is
the operator's (**D2**).

## Technical Context

**Language/Version**: Python 3.13 (uv workspace, 19 packages)

**Primary Dependencies**: the engine (`packages/engine`: the converter's
dispatch, the loader's builder lookup, the bootstrap facts); the
Terraform library (`packages/hashicorp-utils`: the collector); the kit's
registry (`packages/base`, read, not changed: `models_under`,
`namespace_of_class`); the local state plugin and a test-only twin of it
for story 3

**Storage**: N/A (in-process; the records are meta-state YAML files the
run already writes)

**Testing**: pytest through `just test` (lint, type check, unit tests,
the isolated runs), with both goldens as the guard that nothing moved,
and OpenTofu (`tofu init` with a `local` backend, offline) for SC-002

**Target Platform**: your local machine and the CI runners

**Project Type**: library and command line (a compiler of configuration
into infrastructure code, with a plugin SDK)

**Performance Goals**: no slower than today: one listing of a
classification's words per builder entry at load (23 entries in the
shared fixture)

**Constraints**: the bare form's emission is byte-identical
(Constitution IV); no provider plugin and no contract member changes
(FR-006); a test does not assert wording (Constitution IX); no cloud is
touched before the release step

**Scale/Scope**: one dispatch rule (about 10 changed lines), one loader
lookup, two collector lines, two bootstrap comparisons; eight builder
classifications (nine with D1's other answer). The meaning of "the
class's registered word" where two plugins share a bare word was NEEDS
CLARIFICATION, resolved by research R6 (chosen, with the operator free
to overturn it). No NEEDS CLARIFICATION remains.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan meets it | Result |
| --- | --- | --- |
| I. Purpose first | Serves operators, an adopting team and a plugin author, named in the spec | Pass |
| II. Acceptance is executable | Every story ends in a test run by `just test-one` and in `just test`; SC-002 ends in a real `tofu init`, and a skip of it is a failure; [quickstart.md](quickstart.md) steps 1 to 8 | Pass |
| III. Nothing irreversible by default | No apply and no plan gate touched; the state-location move guard compares locations, which do not change (R6) | Pass |
| IV. The emission is the contract | Both goldens must not move (R6's experiment: the patched bare emission equals the golden, 117 of 117); the qualified trees are compared with the bare emission file for file | Pass |
| V. Public by construction | No secret read or written; records gain no field | Pass |
| VI. Layers and no interference | The change is in the engine and the Terraform library; nothing imports back (the library keeps to the contract, R9). Two plugins of one bare word become usable side by side (R3). One cost, recorded under Complexity Tracking: where a neighbour registers the same bare word, a qualified tree's records name the qualified word (R6) | Pass |
| VII. Budget, subtraction | Below: a small source growth, with its reason; the dead alias branch and the namespace-keeping rewrite go | Pass |
| VIII. One source per fact | A class's word has one source after the load (the registry's listing); the tool's word has one (the kind); CONFIGURATION 1.2 and base's README state the rule, the others link | Pass |
| IX. Tests guard behaviour | The new tests assert emissions, records, which plugin's builder is used and that OpenTofu initialises a root, not wording | Pass |
| X. What a change makes false | Listed below | Pass |

**Re-check after design**: still passes. The design adds no package, no
contract member, no declared surface member and no protocol; two costs
are recorded under Complexity Tracking so they can be rejected.

### Budget (Principle VII)

Measured on `develop` at `35446e3f` on 2026-11-21 by the method of spec
004's T002: lines of `*.py` under `packages/*/src` and `src`; tracked
`*.py` under `tests` and `packages/*/tests`, fixtures left out; tests as
`just test-one --collect-only -q` counts them.

| Measure | Today | Expected | Reason for any growth |
| --- | --- | --- | --- |
| Workspace packages | 19 | 19 | none added or removed by this work (specs 007 and 008 remove theirs) |
| Source lines | 54,249 | +10 to +30 | the registered word found at dispatch (about 8, replacing the namespace-keeping rewrite and the dead alias branch); the builder lookup by key (about 2); the label from the kind (about 6); the bootstrap matcher (about 4, reusing spec 006's) |
| Test lines | 46,069 | +170 to +260 | the story 3 twin plugin and its whole runs in both orders (about 90); the per-kind converter cases (about 25); the real `tofu init` (about 20); the rewrite extended to builder collections (about 20); the qualified core fixture case (about 20); the collector and bootstrap cases (about 25) |
| Tests | 2,610 | +7 to +11 | one or more per scenario of stories 1 to 3 and per edge case with behaviour |
| Contract protocol members | 0 | 0 | the contract does not change |
| Golden files | 117 shared, 32 core | 117, 32 | nothing moves |

### Statements this change makes false (Principle X)

Corrected in the same work (research R16):

- [packages/base/README.md](../../packages/base/README.md), "The
  registry", the Resolution paragraph: the recorded-word rule, narrowed
  to "what a run emits and records holds the class's registered word"
  (FR-009), with D1's exception when D1 keeps its default.
- [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) section 1.2: "A
  plugin may register a model under several names" and "What the entry
  wrote is what is recorded".
- [packages/engine/README.md](../../packages/engine/README.md), the
  converter paragraph: "An alias is canonicalized to the class's
  `csis_name()` first" and its `Registry().get_model`.
- [packages/hashicorp-utils/README.md](../../packages/hashicorp-utils/README.md):
  what `BackendRegistration.type` holds; the remote-state `backend` is
  the kind's type.
- [docs/WRITING_A_PROVIDER.md](../../docs/WRITING_A_PROVIDER.md), "The
  namespace": a model's `type_` holds the registered word; a backend's
  label is its kind's `type`.
- Code comments: `_dispatch`'s; the collector's two generator
  docstrings.
- Spec 006's records ([research.md](../006-qualified-runtime-type/research.md)
  R2 and [plan.md](../006-qualified-runtime-type/plan.md) D1): the fix
  touches no state plugin (a note, not a rewrite); its Complexity
  Tracking row ends.
- [specs/README.md](../README.md), row 009: its state.
- In the Google Cloud family's repository: `test_qualified_words.py`
  writes all four of its words qualified in the whole run; its
  docstring and release notes say so.

## Project Structure

### Documentation (this feature)

```text
specs/009-qualified-builder-words/
├── spec.md
├── plan.md              # this file
├── research.md          # R1 to R16
├── data-model.md        # the words a builder is known by
├── quickstart.md        # how to prove the feature
├── contracts/
│   └── recorded-builder-words.md   # what a tree writes; what is recorded; the label
├── checklists/
│   └── requirements.md
└── tasks.md             # from /speckit-tasks
```

### Source Code (repository root)

```text
packages/engine/src/cs_image_system/engine/
├── orchestrator.py                 # _dispatch: the type read as the registered word
├── config_loader.py                # the builder class by the model's own key
└── bootstrap/facts.py              # state backends found by a qualified word
packages/hashicorp-utils/src/cs_image_system/hashicorp_utils/
└── collector.py                    # the backend label and remote-state backend from the kind
packages/hashicorp-utils/pyproject.toml, packages/tofu-roots/pyproject.toml   # 0.2.1 -> 0.2.2
tests/test_qualified_builder_words.py                            # new: the rule per kind; story 3; tofu init
tests/test_a_qualified_tree_emits_what_the_bare_tree_emits.py    # the rewrite reaches every builder's type
tests/test_terraform_collector.py                                # the label from the kind
tests/test_bootstrap.py                                          # a qualified state backend found
packages/system/tests/test_core_golden.py                        # the qualified core fixture emits the core golden
docs/CONFIGURATION.md, docs/WRITING_A_PROVIDER.md, packages/*/README.md   # Principle X
```

**Structure Decision**: no package is added or moved. The change is in
the engine's load and the Terraform library's collector; the tests are
placed so that none needs the AWS family or the Okta plugin (research
R14), and survive specs 007 and 008.

## Delivery order

1. The converter's rule and the loader's lookup; the per-kind cases and
   story 3's whole runs in `tests/test_qualified_builder_words.py`.
2. The collector's label; its case; the real `tofu init`.
3. The bootstrap lookups and their case.
4. The whole-tree proofs: the shared fixture's rewrite extended to
   every builder collection, the qualified core fixture.
5. The documents of Principle X; `just sdk-bump terraform last`.
6. The release (D2), then the Google Cloud family's whole qualified run
   and its release.

Each step ends with `just test` green before the next.

## Depends on spec 006

Under D1's default the runtime word stays spec 006's, so:

- Steps 1 to 3, and step 4's rewrite of every builder kind but runtimes,
  do not need 006 and may be built before it lands.
- Step 4's whole tree with runtimes written qualified (SC-001 as the
  spec states it) needs 006 merged first: until then a qualified runtime
  is refused for want of an image source (006's R1).
- The bootstrap matcher reuses the one 006 adds for `runtimes_of_type`;
  built first, this work adds it and 006 reuses it.

Under D1's other answer ("read runtimes at the edge too"), SC-001 no
longer waits on 006 (R10's experiment), and 006's FR-006 is amended.

## How this survives specs 007 and 008

Spec 008 takes the Okta plugin out and spec 007 the AWS family (with
the S3 state backend). No test this plan adds needs either: story 3
uses the local state plugin and a twin of it over the docker family's
roots, the core fixture uses the test kit's double, and the shared
fixture's rewrite qualifies whatever builders the fixture declares. The
AWS family's and the Okta plugin's repositories then prove their own
qualified words against their own fixtures when they take the release,
as the Google Cloud family's does.

## Complexity Tracking

No constitution principle is violated. Two costs are recorded so they
can be rejected.

| Cost | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| Where an installed neighbour registers the same bare word, a qualified tree's records and two comments name the qualified word (`local-state/local`) where they named `local` before (R6) | It is the one word that names the class once two classes share the bare word; every later lookup of a model's word, and any plugin's own, resolves it without ambiguity | Recording the bare `csis_name` always leaves every later lookup ambiguous in story 3, and a record could not say which plugin's class it was |
| Under D1's default the edge rule has one exception: a runtime's word keeps its written form | Spec 006's FR-006 names a runtime's written word in a message, and its catalog resolves the word itself | Reading runtimes at the edge too is D1's other answer, open to the operator; it amends 006's FR-006 |

## Definition of done (constitution 1.2.0)

`/speckit-tasks` ends the task list with these, in order, each with a
record of what was done and its evidence:

1. `/speckit-converge` after the last implementation task, and every
   task it appends done.
2. The quickstart walked step by step on the final code, each result
   recorded, and any box it corrects bumped.
3. The squash-merge of `feature/009-qualified-builder-words` into
   `develop`, the branch kept.
4. The release of D2, every run it starts passed (`just release-watch
   <version>`), the reference has taken it (`UV_REFRESH=1 just take
   <version>`) with its drift check green; the Google Cloud family's
   release carrying the whole qualified run, its runs passed.
5. `spec.md`'s status line and the row for 009 in `specs/README.md`
   say **complete**, with the date.

## Decisions in this plan

**Chosen** by this plan (the operator may overturn any), one line each:

- R6: the registered word is the word the registry lists the class by
  (`models_under`): the bare word while one class answers, else
  `<namespace>/<word>`.
- R7: the word is read once, at the load, in the converter's dispatch,
  not mended reader by reader and not stripped in the plugins.
- R8: the loader finds a model's builder class by the model class's own
  registration key.
- R9: a backend's OpenTofu label and a consumer's remote-state
  `backend` come from the backend kind's `type`; the record and the
  backend file's comment keep the registered word.
- R11: the bootstrap state-backend lookups accept a qualified word by
  its name part, by spec 006's matcher.
- R13: refusals at load name the written word; messages after the load
  name the registered word.
- R14: the tests are placed so none needs the AWS family or the Okta
  plugin; SC-002 is a real offline `tofu init` of a `local` root.
- R15: the Terraform line takes a PATCH (0.2.1 to 0.2.2); the kit's
  version and the contract are unchanged.

**YOUR DECISION** (the operator's, each with its default):

- **D1. The runtime word** (research R10). Should the edge rule read a
  runtime's word as its registered word too? **Default: no; a runtime
  keeps its written word and spec 006 makes it emit identically.** Why:
  006's FR-006 names the written word in a message, the spec scopes this
  work to every other builder kind, and 006 needs no re-plan. Say "read
  runtimes at the edge too" to make the rule exceptionless; 006's FR-006
  is then amended, and this work's whole-tree proof no longer waits on
  006.
- **D2. The release that carries the fix** (research R15). **Default:
  the one final release the operator decided for specs 002, 003 and
  006, when this is merged before it is cut; else the next release
  after the merge.** Why: the whole-tree proof waits on 006 under D1's
  default, and one release lets the Google Cloud family's 0.2.1 carry a
  whole run with all four of its words qualified. Say "a release of its
  own" to cut one after 006's instead.

No NEEDS CLARIFICATION remains.

## Spec statements to amend

Under the defaults, by `/speckit-clarify` or a small edit before tasks:

- The Input's "22 of the shared golden's 117 files move" and SC-001's
  "today 22 differ": with every builder kind's word qualified (user
  builders included) 23 differ (R1).
- The Assumptions' "the families released from their own repositories
  gain the fix with the kit's next release": the fix is in the engine
  and the Terraform library, so they gain it with this repository's
  next release and the Terraform line's 0.2.2 (R15).
- Story 3 scenario 1, "each emits its own plugin's output, as each
  would alone": holds for every line an external tool reads; the
  records and the backend file's comment name the registered word,
  which is the qualified word there (R6, FR-007).
- The edge case on implicit qualification describes a resolution the
  code does not have (R12); it may be dropped or kept as a rule for any
  future one.

## Operator decisions of 2026-11-21

Asked one at a time after planning; each supersedes the default above where they differ.

- D1: runtimes keep their written word; specification 006 makes them emit as the bare word does, and 006's FR-006 stands.
- D2: this specification rides the release batched for 002, 003 and 006 if it merges before that release is cut; otherwise the next one.
- The four spec statements above are amended as written (the spec's dated notes); the implicit-qualification edge case is kept as a rule for any future resolution.
