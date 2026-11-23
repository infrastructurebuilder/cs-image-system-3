# Data model: Every machine and every id recorded once

**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

Two new records in a configuration's `meta-state/`, written by applying
runs (and the record step, D1), committed with the tree, read offline by
every run.

## `meta-state/servers.yaml`: the recorded server registries

```yaml
servers:
  <identity builder name>:          # e.g. posix-local
    <group>:                        # e.g. pxgroup
      - id: <provider id>           # the runtime's instance id (i-0abc..., a container id)
        hostname: <canonical hostname>
        address: <private address, or "">
        canonical_name: <canonical hostname>
        alt_names: [<alias>, ...]   # sorted; written by the alias pass (FR-016)
        instance_id: <provider id>  # the key a launch finds its own entry by
        instance: <declared instance name>
        registered_run: <run id>
```

| Rule | Source |
| --- | --- |
| One entry per machine; a machine is found by `instance_id` | R1 |
| Entries are sorted by hostname, address, id (Okta's shape) | R1 |
| A launch adds its machine's entry when the runtime reports a provider id | FR-013, R2 |
| A decommission, a replacement or an ephemeral teardown removes every entry under the hostname, or fails loudly | FR-012, FR-014, R3 |
| A file that cannot be read answers "could not be asked" (None), never `[]` | FR-011 |

## `meta-state/ids.yaml`: every recorded id

```yaml
ids:
  group:
    <name>: {id: <int>, identity: <builder>, external: <bool>, how: declared|pooled|read|restored, recorded_run: <run id>}
  user:
    <name>: {id: <int>, identity: <builder>, external: <bool>, how: declared|pooled|read|restored, recorded_run: <run id>}
  defers:                               # POSIX names that take an external namesake's id (FR-004a)
    group: {<name>: <external builder>}
    user:  {<name>: <external builder>}
pools:
  <identity builder name>: {min: <int>, max: <int>, how: declared|read}
retired:                                # names removed from the tree: their ids are never given to another name (FR-004c)
  group: {<name>: <int>}
  user:  {<name>: <int>}
```

| Rule | Source |
| --- | --- |
| A recorded id never changes; a change asked for is refused, naming both | FR-005 |
| A name removed from the tree moves to `retired` with its id; declared again, with that id or none, it takes it back (`how: restored`) | FR-004c |
| An undeclared name gets the lowest id of its identity's pool that no record (current or retired) and no claim holds | FR-004, FR-006 |
| One pool per identity serves users and groups; a user and its private group draw one id | R11 |
| An external identity's id is recorded when first read (`how: read`) and wins over any declared or pooled id | FR-007 |
| A POSIX name an external identity holds is recorded once, under the external identity, with POSIX in `defers` | FR-004a, the validation's item 9 |
| Pools never overlap; a pool may not be moved over another identity's recorded id | FR-006 |
| A recorded id outside its pool after a pool change is kept and reported | FR-006 |

## The claim

The contract's `Claim` gains `identity: str` (the builder that claims)
and `external: bool` (whether its ids come from an outside service). Their
defaults keep every claim written today valid.

## State transitions of a name's id

```text
declared or undeclared ──validate──> concrete (shown; a plain dry run records nothing)
concrete ──applying run / record step (D1)──> recorded
recorded ──name removed from the tree──> retired (id held)
retired ──name declared again──> recorded (same id)
recorded ──any later change asked for──> refused
```
