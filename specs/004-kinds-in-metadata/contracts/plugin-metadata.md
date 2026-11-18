# Contract: what a plugin declares about its kinds

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R1 to R4, R7

This is what a plugin author writes against after this feature. It
serves FR-001, FR-002, FR-006, FR-007 and FR-011.

## Declaring

A plugin's metadata names its kinds beside its other contributions.

| Member | What a plugin gives |
| --- | --- |
| `enrollment_kinds` | a sequence of `EnrollmentKind(kind, script_lines, ansible_tasks)`, one per enrollment kind the plugin provides |
| `field_kinds` | a mapping from a field-kind name to its `FieldKindHandler` |

With the contract's data record, a plugin passes them as fields. With
the kit's metadata base class, a subclass overrides the two properties
of the same names. Both default to empty, so a plugin with no kinds
changes nothing.

## What a plugin may no longer call

- `cs_image_system.contract.enrollment.register_enrollment_kind`
- `cs_image_system.contract.field_kinds.register_field_kind`

Both leave the contract's public names. A plugin cannot register a
kind by a call at all; the registries are filled by the system.

An underscore-prefixed name imported from the contract is a finding of
the surface check (`python -m cs_image_system.base.surface check`):

```text
<file>:<line>: from cs_image_system.contract.<module> import _<name> — private to the contract
```

## What a plugin may still read

`enrollment_kind_for(params)`, `registered_kinds()`,
`get_field_kind_handler(name)`, `handler_for(metadata)`,
`field_kind(metadata)` and the four system field-kind names stay
public: a plugin may ask which kinds are registered and look one up.

## Messages

Logged once at ERROR while the plugins are discovered, in the forms
spec 001 already uses
([contracts/commands.md](../../001-standalone-docker-provider/contracts/commands.md)):

```text
Plugins <a> (<distribution>) and <b> (<distribution>) are both skipped: both register enrollment kind '<name>'
Plugins <a> (<distribution>) and <b> (<distribution>) are both skipped: both register field kind '<name>'
Plugin <name> (<distribution>) is skipped: refused: field kind '<name>' is the system's own
Plugin <name> (<distribution>) is skipped: refused: it declares enrollment kind '<name>' twice
```

The line that called a kind "nobody's" after an earlier collision is
gone: a third claimant is paired with one that differs, as for any key.

## Versions

| Package | From | To | Why |
| --- | --- | --- | --- |
| `cs-image-system-contract` | 0.4.4 | 0.5.0 | two protocol members added, two public functions removed |
| every dependent's range | `>=0.4,<0.5` | `>=0.5,<0.6` | the contract's series moved |
| `cs-image-system-base` (the kit) | 0.2.0 | 0.2.0 | additions only, on an unreleased line; baseline re-recorded |
