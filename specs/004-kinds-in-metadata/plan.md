# Implementation Plan: Kinds a plugin declares, not kinds it registers on import

**Branch**: `feature/004-kinds-in-metadata` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/004-kinds-in-metadata/spec.md`

**Users served**: a plugin author (primary); operators.

## Summary

A plugin declares its enrollment kinds and field kinds in its
metadata, as it declares everything else. The loader settles which
plugins are usable exactly as spec 001 made it do, treats a declared
kind as one more registration key in that settling, and then registers
the usable plugins' kinds once for the process. Nothing is registered
for a plugin that is skipped, so nothing needs taking back, and the
inference code spec 001 added for kinds registered on import is
deleted.

The approach, decided in [research.md](research.md):

1. The contract's metadata record and protocol gain `enrollment_kinds`
   and `field_kinds`; the kit's metadata base answers both with
   overridable properties (R1).
2. The two registration functions leave the contract's public names;
   the engine fills the registries through a private function of each
   module, and the surface check finds an underscore name imported
   from the contract (R2).
3. Declared kinds join the collision rules at settling; the system's
   own field-kind names are fixed in the contract and refused to a
   plugin (R3, R4).
4. The loader's kind inference, and its tests, are removed; the four
   cases spec 001 recorded become tests in every discovery order (R5,
   R6).
5. The Okta plugin declares its one kind; the emission does not move
   (R8).
6. The contract goes to 0.5.0, with every range on it; the kit stays on
   its unreleased 0.2.0 with its additions recorded (R7).

## Technical Context

**Language/Version**: Python 3.13 (uv workspace, 22 packages)
**Primary Dependencies**: the contract (`packages/contract`), the kit
(`packages/base`), the engine's loader (`packages/engine`), the Okta
plugin (`packages/okta-opa-plugin`)
**Storage**: N/A (the kind registries are in-process tables)
**Testing**: pytest through `just test` (lint, type check, unit tests,
the three isolated runs), with the shared golden as the guard that
nothing moved
**Target Platform**: the operator's machine and the CI runners
**Project Type**: library and command line (a plugin system)
**Performance Goals**: discovery no slower than today (it reads the
same metadata once)
**Constraints**: the emission of the frozen fixture and of the
reference configuration is byte-identical (FR-003, SC-004); a test does
not assert wording (Constitution IX)
**Scale/Scope**: one plugin declares a kind today (Okta); 21 manifests
carry the contract's range

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan meets it | Result |
| --- | --- | --- |
| I. Purpose first | Serves a plugin author and operators (spec, Users served) | Pass |
| II. Acceptance is executable | Every story ends in a test run in every discovery order, the golden, and `just test`; [quickstart.md](quickstart.md) | Pass |
| III. Nothing irreversible | No apply, no plan gate touched | Pass |
| IV. The emission | The shared golden must not move; the Okta renderers are unchanged to the byte (R8) | Pass |
| V. Public by construction | No secret is read or written | Pass |
| VI. Layers and no interference | The engine writes into the contract's tables; the contract imports nothing of the engine. A skipped plugin's kinds are never registered, so it cannot change another | Pass |
| VII. Budget, subtraction | The loader shrinks (below); growth is in tests that replace tests | Pass |
| VIII. One source per fact | No counts in documents; the version table is the contract's own | Pass |
| IX. Tests guard behaviour | The new tests assert who loads and what is registered, not wording | Pass |
| X. What a change makes false | Listed below | Pass |

**Re-check after design**: still passes. One cost is recorded under
Complexity Tracking (a breaking contract step).

### Budget (Principle VII)

Measured on `develop` at `46917a66`.

| Measure | Today | Expected | Reason for any growth |
| --- | --- | --- | --- |
| Loader (`engine/loader.py`) lines | 774 | −100 to −140 | The nine inference functions (97 lines) and their state leave; the declared-kind key and the registration after settling add about 30 |
| Source lines (`packages/*/src`, `src`) | measured at T001 | −80 to −130 | The loader's net fall, the kit's two re-exports, Okta's registration call; the contract gains two record fields and two protocol members |
| Test lines | measured at T001 | −100 to +50 | The kind sections of `test_unusable_plugins.py` (from line 216, the library and claimant tests) leave; the four recorded cases arrive, each over every order |
| Workspace packages | 22 | 22 | None added or removed |
| Contract protocol members | — | +2 | `enrollment_kinds`, `field_kinds` on `PluginMetadataProtocol` |
| Golden files | 222 | 222 | No emission moves |

### Statements this change makes false (Principle X)

Corrected in the same work.

- [packages/contract/README.md](../../packages/contract/README.md):
  the module table's `enrollment` row (line 41, "registers"), the
  `field_kinds` row (line 31), and the version rule's range
  `>=0.4,<0.5` (lines 140, 183); a version-table row for 0.5.0.
- [packages/contract/src/cs_image_system/contract/enrollment.py](../../packages/contract/src/cs_image_system/contract/enrollment.py)
  and [field_kinds.py](../../packages/contract/src/cs_image_system/contract/field_kinds.py):
  their module docstrings ("a plugin registers its kind when its module
  loads", "a plugin may `register_field_kind`").
- [packages/contract/src/cs_image_system/contract/context.py](../../packages/contract/src/cs_image_system/contract/context.py)
  line 131, which points at `register_enrollment_kind`.
- [packages/base/README.md](../../packages/base/README.md) line 488
  (field kinds by `register_field_kind`) and line 1317 (the contract's
  range).
- [packages/base/src/cs_image_system/base/launch_enrollment.py](../../packages/base/src/cs_image_system/base/launch_enrollment.py):
  its docstring and its re-exports.
- [packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/okta_opa_tf_group_builder.py](../../packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/okta_opa_tf_group_builder.py)
  line 30 ("importing it registers the kind's launch steps").
- [docs/WRITING_A_PROVIDER.md](../../docs/WRITING_A_PROVIDER.md): how
  a plugin brings a kind (one place, SC-006), and the collision list
  near line 314.
- Spec 001's record:
  [research.md](../001-standalone-docker-provider/research.md) R13 (the
  limit, and the "kinds a plugin registers by a call of its own"
  paragraphs), its plan's Complexity Tracking row, and
  [contracts/commands.md](../001-standalone-docker-provider/contracts/commands.md)
  lines 152 to 160 (the "is nobody's" line form, which no longer
  exists): each marked as superseded by this specification, not
  rewritten.
- The 21 manifests that carry `cs-image-system-contract>=0.4,<0.5`.

## Project Structure

### Documentation (this feature)

```text
specs/004-kinds-in-metadata/
├── spec.md
├── plan.md              # this file
├── research.md          # decisions R1 to R9
├── data-model.md        # the declared kinds and the registries
├── quickstart.md        # how to prove the feature
├── contracts/
│   └── plugin-metadata.md   # what a plugin declares, and what it may no longer call
├── checklists/
│   └── requirements.md
└── tasks.md             # from /speckit-tasks
```

### Source Code (repository root)

```text
packages/contract/src/cs_image_system/contract/
├── metadata.py          # PluginMetadata: + enrollment_kinds, field_kinds
├── core.py              # PluginMetadataProtocol: + the two members
├── enrollment.py        # register_enrollment_kind -> private _install
└── field_kinds.py       # register_field_kind -> private _install; SYSTEM_FIELD_KINDS
packages/base/src/cs_image_system/base/
├── basic/abstract_plugin_metadata.py   # + two overridable properties
├── launch_enrollment.py                # re-exports of the registration go
├── surface/check.py                    # + an underscore contract import is a finding
└── surface-baseline.txt                # re-recorded (additions)
packages/engine/src/cs_image_system/engine/
├── loader.py            # declared kinds as keys at settling; register after; inference removed
└── orchestrator.py      # the system's own field kinds through the private installer
packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/
├── main.py              # OktaTypes declares the sftd-token kind
└── sftd_launch.py       # the registration call goes
packages/engine/tests/test_unusable_plugins.py   # kind tests replaced
packages/base/tests/test_surface_check.py        # the new finding
tests/test_posix_identity.py                     # no reliance on the import side effect
```

**Structure Decision**: no package is added or moved; the change is in
the four packages above and the manifests that range on the contract.

## Delivery order

1. The contract: the two members, the private installers, the fixed
   system field-kind names; the version to 0.5.0 and every range.
2. The kit: the two properties, the re-exports removed, the surface
   check's new finding, the baseline re-recorded.
3. The loader: declared kinds at settling, registration after, the
   inference removed; the tests replaced, the four recorded cases in
   every order.
4. The Okta plugin; the golden is the proof that nothing moved.
5. The documents and spec 001's record.

Each step ends with `just test` green before the next.

## Complexity Tracking

No constitution principle is violated. One cost is recorded so it can
be rejected.

| Item | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| A breaking contract step (0.4 to 0.5) for one plugin's one kind | The registration functions must leave the plugin's reach, and the metadata must carry the kinds; both are observable | Keeping the functions public leaves the side effect available, and the recorded cases come back with the first plugin that uses it |
