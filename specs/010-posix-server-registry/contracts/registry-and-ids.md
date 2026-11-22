# Contract: the registry and the ids (contract 0.6.0)

**Feature**: [spec.md](../spec.md) | **Research**: [research.md](../research.md)

What the contract gains, all additions (R10). The meaning of every
existing question stays (FR-020).

## Group builder (`GroupBuilderProtocol`)

| Member | New? | Meaning |
| --- | --- | --- |
| `can_query_servers()` | existing | True for an identity that keeps a registry (Okta's, or POSIX's recorded one) |
| `registered_servers(group)` | existing | the entries, or None when the registry cannot be asked; never `[]` for "could not ask" |
| `retire_servers_named(group, hostname)` | existing | removes every entry under the name and returns their ids, or raises |
| `alias_registration_script(names)` | existing | the script that makes the machine answer to `names`, or None |
| `record_aliases(group, entry_id, names)` | **new** | a recorded registry writes `names` into the entry and returns them, or raises; None from the kit's default means "this builder writes aliases on the machine, by its script" |
| `keeps_recorded_registry()` | **new** | True when the registry lives in the configuration's records (the core registers launches for it and skips the enrolment wait); kit default False |
| `id_pool()` | **new** | `(min, max)` of the ids this identity gives, or None; kit default None |
| `posix_id_claims()` | existing | the claims, now carrying `identity` and `external` |

## User builder (`UserBuilderProtocol`)

`id_pool()` (new, as for groups) and `posix_id_claims()` (existing).

## Runtime builder (`RuntimeBuilderProtocol`)

`query_instance_identity(name)` (existing) may also answer `address`
(new key, optional): the machine's private address.

## The records (`MetaStateProtocol`)

| Member | New | Meaning |
| --- | --- | --- |
| `registered_servers(identity, group)` | yes | the entries, or None when `servers.yaml` cannot be read |
| `record_server(identity, group, entry)` | yes | adds or replaces the entry with that `instance_id` |
| `retire_servers(identity, group, hostname)` | yes | removes and returns the entries under the hostname |
| `record_server_aliases(identity, group, entry_id, names)` | yes | sets an entry's `alt_names` |
| `recorded_ids()` | yes | the `ids.yaml` document |
| `record_ids(document)` | yes | writes it, refusing any change to a recorded id |

## The claim (`identity_vocabulary.Claim`)

`identity: str = ""` and `external: bool = False`, both new.
