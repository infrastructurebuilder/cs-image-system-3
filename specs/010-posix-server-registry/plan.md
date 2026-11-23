# Implementation Plan: Every machine and every id recorded once, by an identity the system ships

**Branch**: `feature/010-posix-server-registry` (to be created from `develop` when implementation starts) | **Date**: 2026-11-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-posix-server-registry/spec.md`

**Users served**: operators; an adopting team; a plugin author.

## Summary

The POSIX identity plugin gains a server registry kept in the
configuration's records (`meta-state/servers.yaml`), answered through the
contract's existing registry questions, so a POSIX-owned machine gets what
an Okta-owned one gets: its canonical hostname claimed once, its entries
retired at decommission, its provider alias recorded, its registered name
in the state query. A new core step registers each launched machine
before the alias pass ([research.md](research.md) R2), and the alias pass
writes a recorded registry's aliases into the entry instead of onto the
machine (R4).

Every user and group gets one recorded id (`meta-state/ids.yaml`). The
core's id rule widens to every identity: claims name their identity and
whether it is external, recorded ids never move, the POSIX identity
defers to an external namesake and nothing else defers, a name with no
declared id draws from its identity's pool, and an id once held is never
given to another name (R6, R11). Okta's ids and pool are read from OPA,
read-only, and recorded (R8).

One contract PATCH (0.5.1; planned as the MINOR 0.6.0, D7) carries the additions
([contracts/registry-and-ids.md](contracts/registry-and-ids.md)); no
existing question changes meaning. The Okta plugin's own share (its
claims and its pool) is the Okta repository's (D3).

## Technical Context

**Language/Version**: Python 3.13 (uv workspace)

**Primary Dependencies**: the contract (`packages/contract`: the registry
and id questions, the records' members, `Claim`); the kit
(`packages/base`: `launch_params.py`'s new registration step and the
ephemeral retirement, `meta_ledgers.py`'s two records, the builders'
defaults); the engine (`posix_ids.py`, `validate.py`'s `check_posix_ids`,
`meta_state.py`, `provider_aliases.py`, `commands/login_proof.py`); the
POSIX identity plugin (its registry, its pool, its claims); the AWS and
docker runtimes (`query_instance_identity`'s `address`)

**Storage**: two YAML records under a configuration's `meta-state/`,
written by the engine's atomic, public-safety-scanned writer

**Testing**: pytest under the strict session; the shared fixture gains
POSIX ids and, for the registry tests, seeded `servers.yaml` copies

**Target Platform**: the system's CLI on the operator's machine and CI

**Constraints**: validation and dry runs read only the records and the
configuration for ids and pools (FR-009a); a dry run records nothing
(D1); nothing is written to Okta or OPA (R8, D2)

**Scale/Scope**: the 30 registry tests specification 008 left, every id
test, two new records

## Constitution Check

| Principle | How the plan keeps it |
| --- | --- |
| I. Purpose first | operators (one name, one machine; ids that never drift), an adopting team (a POSIX tree gets Okta's guarantees), a plugin author (a registry written against the kit) |
| II. Acceptance is executable | the quickstart's four steps: the id and registry tests, then `just test` with the Okta plugin absent, then the reference's record |
| III. Nothing irreversible | ids never move once recorded; retirements are said when they fail; nothing writes to Okta (D2's default) |
| IV. The emission | no root, bake or script changes for a tree whose ids are declared; the golden gains the two records only where its run records them (D1), each read file by file |
| V. Public by construction | the records hold ids, hostnames and addresses, no secret; both go through the public-safety scan |
| VI. Layers | the rule is the core's; the POSIX plugin answers through the contract; no plugin imports the engine |
| VII. Budget | below |
| VIII. One source | the ids live in `ids.yaml`; documents name the rule, never a list of ids |
| IX. Tests | every new test proves a behaviour: a refusal, a pool draw, a registration, a retirement |
| X. What it makes false | below |

No violation needs justifying.

## Budget

| Measure | Expected | Reason |
| --- | --- | --- |
| Source lines | about +700 (the POSIX registry about 150, the id rule about 250, the registration step and alias seam about 120, the records about 150, the contract about 30) | the two guarantees are new |
| Workspace packages | 0 | |
| Contract protocol members | +11 (group 3, user 1, the records 6, `Claim` 2 fields; the runtime's `address` a key, not a member) | each is a question a plugin answers or the core asks |
| Tests | about +40 new; about 30 re-hosted from Okta (specification 008's T035, part 2) | the id rules and the recorded registry |
| Subtraction | the Okta stubs of the 30 registry tests; the POSIX id rule's fourth rule | |

## What the change makes false

- `docs/OPERATIONS.md` ("A canonical hostname is claimed once", "What a
  machine answers to"), `docs/DAILY_DRIVER.md` (the decommission's "OPA
  registration", the alias walkthrough): both say a registry is OPA's.
- `packages/posix-identity-plugin/README.md` ("No credentials, no network,
  no state"; "the configuration is the authority"), `packages/base/README.md`
  (the registry hooks), `packages/engine/README.md` (aliases only through a
  script; "its OPA registration ... NOT retired").
- The docstrings and log lines that say "OPA registration"
  (`launch_params.py`, `builder_base_group.py`, `provider_aliases.py`,
  `posix_builders.py`), and `tests/test_login_proof.py`'s "the posix plugin
  keeps none".
- `posix_ids.py`'s rule 4 ("a name no side supplies an id for is refused").
- The contract's README (the version table, the member counts, the
  "Twelve members" of the records).
- Specification 008's T035, part 2, rests on this specification.

## Decisions (the operator's, all taken 2026-11-22 as their defaults)

- **D1. Who records ids: the record step too, or applying runs only?**
  `just record` is a dry run (`run --all --commit`), while the
  specification says a dry run records no ids but the record step records
  Okta's. Default: **a dry run with `--commit` records** (it is the
  operator's deliberate record: ids made concrete, Okta's read), a dry run
  without it records nothing; FR-009's wording says so. **Taken.**
- **D2. A new Okta group's gid: set by the system, or recorded as Okta
  assigns it?** OPA lets a gid be set only after the group exists, through
  the attributes API (a write to OPA), never at creation. Default: **Okta
  assigns, the system records** (story 2, scenario 6's fallback; no new
  write to OPA; the pools kept apart make a collision impossible but by
  hand). **Taken.**
- **D3. Where do the naming rules (R-names) and the Okta plugin's claims
  land?** Default: **a live, read-only look at one enrolled machine first**
  (the operator's box: `getent group 180007`, `getent group
  sft_coops_user`, `grep sft_ /etc/group /etc/passwd`); the naming rules
  and the Okta plugin's claims and pool then become the Okta repository's
  specification 002, written once this one's contract is released; this
  specification ends with the contract able to carry them and the POSIX
  side done. **Taken.**
- **D4. The POSIX pool's default bounds?** Default: **3000 to 59999**:
  every POSIX id declared today, clear of the system's accounts and of
  every range Okta has used (90000, the 150000s, 180007). **Taken.**
- **D5. Which release carries it?** Default: **the batched release for
  specifications 002, 003 and 006** if this merges first, else the next.
  **Taken.**

- **D6. The families released elsewhere pin the contract below 0.6;
  how is 0.6.0 reached?** Found at T005 (2026-11-22): the Google Cloud
  family 0.2.0 and the Okta plugin 0.2.0 pin
  `cs-image-system-contract>=0.5,<0.6`, so this repository cannot even
  lock on 0.6 (its `gcloud` and `all` extras take the family from the
  index), let alone release it beside them; research R10 was wrong to
  say the Okta plugin keeps working. **Taken** ("widen the families, with
  trusted publishing for Google Cloud"): each family releases 0.2.1
  with `>=0.5,<0.7` first (they use none of 0.6's members), the Google
  Cloud family gaining trusted publishing as the Okta repository has
  it, since no upload token is kept; then this repository locks on 0.6
  (tasks T049 to T052, before T005).

- **D7. No minor versions.** The operator, 2026-11-23: "versions will
  only increment the patch level, not the minor version ... until we
  stabilize more". The contract's additions are therefore 0.5.1, not
  0.6.0, and every dependent's range stays `>=0.5,<0.6`; the kit and the
  Terraform libraries take their LAST numbers (0.2.2) as planned. In
  hindsight D6's widening was not needed (the families' 0.2.0 already
  take any 0.5.x); their 0.2.1 (`>=0.5,<0.7`) stand, harmless. While the
  rule holds, the contract and the SDK only add: a removed or reshaped
  member would reach every plugin through its range unguarded, and
  `just surface-check` refuses one without a middle number. **Taken.**

## Project Structure

```text
packages/contract/src/cs_image_system/contract/
  group.py, user.py, runtime.py, context.py, identity_vocabulary.py   # the additions (0.5.1, D7)
packages/base/src/cs_image_system/base/
  launch_params.py          # register_launched_servers; forget_ephemerals retires
  meta_ledgers.py           # SERVERS, IDS in ALL_FILES
  basic/builder_base_group.py, basic/builder_base_user.py   # defaults for the new questions
packages/engine/src/cs_image_system/engine/
  posix_ids.py, commands/validate.py   # the widened rule, the pools, the records
  meta_state.py                         # the two records
  provider_aliases.py                   # record_aliases in place of the script
  commands/login_proof.py               # the one-registration check, for every registry
packages/posix-identity-plugin/src/cs_image_system/posix_identity_plugin/
  registry.py (new), posix_builders.py, posix_models.py (id_pool)
packages/aws-runtime-plugin, packages/docker-plugin   # query_instance_identity's address
tests/                                    # the id tests, the 30 registry tests on POSIX
tests/fixtures/                           # POSIX ids, the golden's two records (read file by file)
```

## Order of work

1. The contract's additions and the records (no behaviour yet).
2. The id rule and the pools, with their tests (stories 1 to 3, the POSIX
   side; Okta's claims arrive with the Okta repository's specification,
   D3).
3. The POSIX registry, the registration step, the ephemeral retirement,
   the alias seam and the login proof's check (stories 4 to 6).
4. The 30 registry tests re-hosted on POSIX (story 7; specification 008's
   T035, part 2), and the stubs that let six tests reach OPA and AWS
   (R13) closed.
5. The documents (Principle X), then the release (D5) and the reference's
   record (quickstart step 4).
