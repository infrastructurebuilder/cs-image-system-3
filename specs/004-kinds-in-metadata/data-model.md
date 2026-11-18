# Data model: Kinds a plugin declares

**Feature**: [spec.md](spec.md) | **Decisions**: [research.md](research.md)

## Enrollment kind

What an identity plugin renders for one way of enrolling an instance at
launch. Unchanged from today; it becomes something a plugin declares
rather than registers.

| Field | Meaning | Rule |
| --- | --- | --- |
| `kind` | The kind's name, as a group builder's launch parameters carry it (`enrollment`) | Required, non-empty; unique within one plugin's declaration |
| `script_lines` | Renders the launch script's steps from the launch parameters | Required |
| `ansible_tasks` | Renders the equivalent configuration-management steps | Required |

Two enrollment kinds are **equal** when they are the same object or
carry the same name and the same two renderers.

## Field kind

How the system reads and resolves a configuration field of one sort.
A handler supplies optional hooks; a plain handler does nothing.

| Field | Meaning | Rule |
| --- | --- | --- |
| name | The kind's name, as a field's metadata names it | Required; unique within one plugin's declaration; not one of the system's own names |
| handler | The behaviour (`FieldKindHandler`) | Required |

Two field kinds are **equal** when their handlers are the same object.

**The system's own field kinds**: `fk`, `templated`, `deferred_list`,
`deferred_list_fk`. Fixed in the contract; never a plugin's.

## Plugin's declared contributions (`PluginMetadata`)

| Member | Today | After |
| --- | --- | --- |
| `services`, `builders_for_models`, `injected_models`, `is_injected_models_default`, `version`, `plugin_metadata_version`, `python`, `namespace` | as today | unchanged |
| `enrollment_kinds` | — | the plugin's enrollment kinds; empty by default |
| `field_kinds` | — | the plugin's field kinds, by name; empty by default |

A plugin's declaration is accepted or refused as a whole: a plugin
whose declared kinds collide is skipped with everything else it
declares.

## The kind registries

One table per sort of kind, in the contract, shared by the process.

| State | When | Holds |
| --- | --- | --- |
| Before discovery | process start | the system's own field kinds, once the resolver is imported |
| After discovery settles | once per process | plus the declared kinds of every usable plugin |

There is no other transition: nothing is taken back, because nothing
is registered for a plugin that is skipped.

## A collision over a kind

| Declarations | Outcome |
| --- | --- |
| Two plugins, one name, different definitions | both skipped, one line naming both and the kind; the kind registered by neither |
| Two plugins, one name, equal definitions | both usable; the kind registered once |
| Three or more, one name, any of them different | every plugin in the dispute skipped, each line naming two that differ |
| A plugin, a system field-kind name | that plugin skipped, one line saying the kind is the system's |
| One plugin, one name twice | that plugin refused, naming the kind |

Each outcome is the same in every discovery order.
