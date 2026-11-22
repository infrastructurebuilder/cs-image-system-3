# Research: Every machine and every id recorded once

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Three read-only investigations of 2026-11-22: the registry's seams in the
code, the id rules and records, and Okta's own documentation (the
operator's research R-names). Paths are repository-relative. Each item
ends in a decision, or in the operator's decision it waits for (D1 to D5,
in the plan).

## R1. The server registry today: four contract questions, six callers

The contract asks a group builder four questions
([contract/group.py](../../packages/contract/src/cs_image_system/contract/group.py)
lines 113 to 119), and the kit answers "none kept"
([builder_base_group.py](../../packages/base/src/cs_image_system/base/basic/builder_base_group.py)
lines 158 to 190): `can_query_servers` False, `registered_servers` None,
`retire_servers_named` raises, `alias_registration_script` None. The entry
shape every caller reads is Okta's: `{id, hostname, address,
canonical_name, alt_names, instance_id}`, sorted by hostname, address, id.

| Caller | Runs | On None |
| --- | --- | --- |
| `validate_claimed_hostnames` ([launch_params.py](../../packages/base/src/cs_image_system/base/launch_params.py) 583-637) | a launching, non-dry run, per applying instance | refuses: an unreachable registry is not a free name |
| `_retire_registration` (563-580), from `forget_decommissioned` and `mark_launched` | after apply | logs "NOT retired", never raises |
| the alias pass ([provider_aliases.py](../../packages/engine/src/cs_image_system/engine/provider_aliases.py) 155-237) | after apply, applies on | skips every alias |
| `_enrolled_after_launch` / `_wait_for_registration` (240-256) | a machine launched this run | waits up to 300 s, then no alias |
| `instance_identity_notes` (309-367) | every state query, dry runs included | no note |
| the Okta login proof (the plugin's `sft_login.py`) | `verify login` | a failed check |

**Decision**: the POSIX identity answers the same four questions (the
contract unchanged in meaning, FR-011), reading and writing an entry list
kept in the configuration's records (Q1). The kit's defaults stay.

## R2. Where a launch becomes a registry entry

`mark_launched` (launch_params.py 466-501) marks a launch by apply scope
and does not know the machine's id. The first code that does is
`reconcile_generations` ([generations.py](../../packages/base/src/cs_image_system/base/generations.py)
133-185), through `rtb.query_instance_identity(name)`, which answers
`{instance_id, provider_hostname}` and no address. The after-apply hooks
run in a fixed order
([run_lifecycles.py](../../packages/engine/src/cs_image_system/engine/commands/run_lifecycles.py)
745-759): `mark_launched`, `forget_decommissioned`, `forget_ephemerals`,
`record_resizes`, `record_detachments`, then `register_provider_aliases`,
the launch scripts, the accounts, the generations. A plugin's own hook
runs after all of them, so after the alias pass.

**Decision**: a new core after-apply step, `register_launched_servers`,
in launch_params.py, registered after `record_detachments` and so before
the alias pass. For every launched, in-scope instance whose group's
builder keeps a recorded registry, it asks the runtime for the machine's
identity and records the entry when a provider id comes back: a
successful launch registers (FR-013), a machine launched before the
change registers on the first applying run that finds it (FR-017), a
launch that never came up leaves nothing. Because it runs before the
alias pass, the pass finds the entry at once and never waits.

**Decision**: the runtime's identity answer gains an optional `address`
(the AWS private address, the docker container's), recorded in the entry
(FR-010); a runtime that gives none records an empty address, which the
claim check already prints as `?`.

## R3. Decommission and the ephemeral gap

`_retire_registration` is called by `forget_decommissioned` and by
`mark_launched` for a replaced machine, both after apply with instances
applying, never in a dry run. `forget_ephemerals` (424-463) drops an
ephemeral machine's launch record and never retires its registration.

**Decision**: `forget_ephemerals` retires too, so an ephemeral POSIX
machine leaves no entry. For Okta this also retires OPA's entry, which a
torn-down ephemeral machine leaves today (a correction the plan names,
Principle X).

## R4. Aliases recorded, not written on the machine (FR-016)

The alias pass changes aliases only by rendering the identity's script and
running it on the machine, then reading the registry back. Its seam is the
call to `_write_aliases` (provider_aliases.py 237).

**Decision**: one contract question, `record_aliases(group, entry_id,
names)`, which a recorded registry answers by writing the names into the
entry (raising on failure); the core calls it in place of the script when
the builder keeps a recorded registry, skips the enrolment wait (nothing
enrols), and keeps the collision rules and the equality short-circuit as
they are. "A machine that is off is left off" no longer applies to a
recorded registry, since nothing is written on the machine.

## R5. How a plugin reaches the records

A builder reaches the run through `_get_context()` (public), whose
`meta_state` is the contract's `MetaStateProtocol`
([contract/context.py](../../packages/contract/src/cs_image_system/contract/context.py)
50-84): twelve members, none for a plugin-owned record, no generic read or
write. The kit's `MetaStateRecords` is not on the surface. A new record
file is a constant in
[meta_ledgers.py](../../packages/base/src/cs_image_system/base/meta_ledgers.py)
and a member of `ALL_FILES` (held complete by `tests/test_meta_state.py`).

**Decision**: two records, `meta-state/servers.yaml` (the recorded
registries, per identity, per group) and `meta-state/ids.yaml` (every
user's and group's recorded id), with typed members on
`MetaStateProtocol` (`registered_servers`, `record_server`,
`retire_servers`, `record_server_aliases`; `recorded_ids`,
`record_ids`). Both written by the engine's atomic, public-safety-scanned
writer and committed by the record step like every record.

## R6. The id rule today

[posix_ids.py](../../packages/engine/src/cs_image_system/engine/posix_ids.py)
resolves the builders' `Claim`s
([identity_vocabulary.py](../../packages/contract/src/cs_image_system/contract/identity_vocabulary.py)
27-40) by four rules: two ids for one name is a configuration error; a
side that knows only the name takes the other's id; providers resolve
before the configuration; a name nobody supplies is refused unless a side
says DEFERRED. Two names on one id within a kind are refused.
`check_posix_ids`
([validate.py](../../packages/engine/src/cs_image_system/engine/commands/validate.py)
235-264) runs it in every validation, dry runs included. Only the POSIX
builders claim (groups, and users with their private groups, `derived`);
**the Okta plugin claims nothing**, so Okta's ids are invisible to the
check. DEFERRED and provider-rank claims exist only in tests. Nothing
records an id: `meta-state/identity.yaml` says "structural facts only;
gids flow by terraform remote-state reference".

**Decision**: the rule becomes: claims carry the identity they come from
and whether that identity is external; recorded ids are a side of their
own that resolves first and never moves (FR-005); the POSIX identity
defers to an external one by name (FR-004a) and nothing else defers
(FR-004b); rule 4 is replaced by the pools (FR-004); an id once recorded
for a name is never given to another (FR-004c). The `Claim` dataclass
gains `identity: str` and `external: bool` (defaults keep today's claims
valid).

## R7. The ids declared and seen today

The shared fixture declares `pxgroup` 3101 and the users `taylor_tango`
3201 and `unix_uniform` 3202, all POSIX; its Okta groups declare none. The
reference configuration declares one id, `pxproof` 3101 (POSIX,
unmanaged), has no POSIX user builder, and its records show Okta's ids:
users and their groups in the 150000s, `coops` 180007, OPA's own
`sft-admin` 90000. **No declared POSIX id lies in a range Okta has used.**

**Decision**: the POSIX pool's default is 3000 to 59999 (D4), covering
every POSIX id declared today and clear of Okta's observed ranges and of
the system's own accounts.

## R8. Okta's ids: what can be read, what can be set

From the OPA API documentation (the OpenAPI bundle the developer site
serves) and the `okta/oktapam` provider's docs:

- A group's gid **cannot** be set at creation: `oktapam_group` takes only
  `name` and `roles`, and `POST /v1/teams/{team}/groups` the same. It
  **can** be changed afterwards, with `PUT
  /v1/teams/{team}/groups/{group}/attributes/{attribute_id}`
  (`unix_gid`, 100 to 2147483647, `security_admin`); likewise a user's
  `unix_uid`. Changing it does not change an account already on a
  machine.
- The range OPA assigns from is **per team, readable**: `GET
  /v1/teams/{team}/attributes/options` lists the `unix_uid` and
  `unix_gid` ranges (min greater than 1000). The default is not
  documented; the reference team's 180007 is explained only by reading
  its options.
- OPA forbids two groups on one gid, and holds back a deleted group's gid.

**Decision**: Okta's pool is read from the attribute options and
recorded (FR-006, FR-009a), read-only. Whether the system sets a new
Okta group's gid by the attributes API after its creation (a write to
OPA) or records what Okta assigns is the operator's (D2).

## R9. R-names: Okta's names on a machine

From OPA's and its predecessor ASA's documentation, and this system's own
records:

- **Accounts** are made on demand at access and deleted at logout or loss
  of access, by default. They persist when the project's "account
  lifecycle" is on (`Project.persistent_server_user_accounts` in the API;
  the oktapam provider does not expose it) or by the agent's
  `PersistentAccount` option in `/etc/sft/sftd.yaml`, which the system's
  activation leaves at `auto` (it writes only `Labels`). An account's name
  is its `unix_user_name`; the Okta plugin already reads it per member.
- **Groups** the agent makes are prefixed `sft_` (ASA documents it; OPA's
  pages are silent), and OPA names `coops`'s server group `sft_coops_user`
  with gid 180007.
- **The POSIX delegate makes `coops` on the machine with OPA's gid**, so
  every Okta machine is meant to hold two group names on one gid:
  `coops` (the delegate's, persistent) and `sft_coops_user` (the
  agent's). The reference's own login proof shows `180007(coops)` in a
  member's groups. ASA's documentation says that when the agent meets a
  group of another name on its gid it "will attempt to take ownership of
  the conflicting group", undocumented in effect; and the POSIX accounts
  script refuses a gid another name holds. Whether the agent's
  `sft_coops_user` ever appears in `/etc/group` on these machines is
  unknown without looking.

**Decision**: the fallback matches configured names only (FR-004a, as
clarified). The naming rules (one name per gid on an Okta machine, what
persists, the delegate's group beside the agent's) are not settled here:
a live, read-only look at one enrolled machine comes first (`getent group
180007`, `getent group sft_coops_user`, `grep sft_ /etc/group
/etc/passwd`), and where the rules land is the operator's (D3).

## R10. The contract and the SDK

Contract 0.5.0; a protocol member added is a MINOR while 0.x (0.6.0), and
every dependent's range moves (`>=0.6,<0.7`). The kit's new public
methods are surface additions (`just surface-record`, the kit's LAST
number). The Okta plugin, released from its own repository, pins
`contract>=0.5,<0.6`, so it keeps working against 0.5 releases and takes
0.6 when its repository raises its range.

**Decision**: one contract MINOR (0.6.0) carries the registry's new
question (`record_aliases`), the records' members, the `Claim` fields,
the identity question for pools (`id_pool()`, R11) and the runtime
identity's `address`. The release that carries it is the operator's
(D5).

## R11. Pools

**Decision**: every identity that manages ids answers `id_pool()`: its
bounds, or None for none (the kit's default). The POSIX identity answers
its builder's `id_pool` (a new model field, default 3000 to 59999). An
external identity answers the bounds it read and recorded (the Okta
plugin, from its attribute options, D2). One pool serves users and groups
alike, so a user and its private group draw one id (the conflict the
specification's validation found, its item 3).

## R12. The login proof's one-registration check

The Okta plugin's `verify login` refuses a duplicate or silent
registration; the POSIX `login_checks` has no such check, and two waiting
tests need it.

**Decision**: the core's `prove_login` checks it for every builder that
keeps a registry, before any login; Okta's own check becomes redundant
and stays until its repository drops it.

## R13. The waiting tests and the network

The 25 tests T035 left (and five more: `test_canonical_names.py` 3,
`test_alias_pool.py` 1, `test_generations.py` 1) stub Okta's registry by
monkeypatching `OktaTfGroupBuilder`. On POSIX they seed the recorded
registry instead, and the alias assertions read the entry's `alt_names`
where they read the session script. Separately, a run of the acceptance
tests with a connection logger (2026-11-22) found six existing tests
reaching the fixture's OPA host and AWS endpoints in-process
(`test_alias_draws.py`, `test_decommission.py`, `test_lineage_pins.py`,
`test_ephemeral.py`, `test_convergent_bakes.py`, `test_canonical_names.py`):
the stubs miss a call. **Decision**: found and named here; fixed with
the tests this plan re-hosts, and any not among them by a task of its own.
