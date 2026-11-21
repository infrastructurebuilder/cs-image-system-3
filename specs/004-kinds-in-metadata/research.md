# Research: Kinds a plugin declares, not kinds it registers on import

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Each decision names what was chosen, why, and what else was weighed.
"**read**" marks a fact taken from the code as it stands on `develop`
at `46917a66`, the commit this branch started from.

### R1. Where a plugin declares its kinds

**Decision**: the plugin's metadata gains two members, beside
`services`, `builders_for_models` and `injected_models`:

- `enrollment_kinds`: the enrollment kinds the plugin provides, each an
  `EnrollmentKind` (the contract's existing record of a kind's name and
  its two renderers);
- `field_kinds`: the field kinds the plugin provides, by name, each a
  `FieldKindHandler`.

Both default to empty. The contract's data record (`PluginMetadata`)
and its protocol (`PluginMetadataProtocol`) carry them; the kit's
convenience base (`AbstractPluginMetadata`) answers them with two
properties that return empty and that a subclass overrides.

**Rationale**: FR-001. A plugin already declares every other
contribution there, and the loader already reads every candidate's
metadata before it decides (spec 001). `EnrollmentKind` already exists
as the value the registry holds (**read**:
`contract/enrollment.py`), so a plugin declares exactly what used to be
registered.

**Alternatives considered**: *a separate entry-point group for kinds*
(a second place to declare, read and collide, for one plugin today);
*a new constructor parameter on `AbstractPluginMetadata`* (it alters a
member's signature on the kit's declared surface, which spec 001's rule
makes a middle-number change of the kit; two properties are additions).

### R2. What a plugin may no longer do

**Decision**: the two registration functions,
`enrollment.register_enrollment_kind` and
`field_kinds.register_field_kind`, are removed from the contract's
public names. The registries are filled through one private function of
each module, which the engine calls: the loader for accepted plugins'
kinds, the resolver for the system's own field kinds. The kit's
re-export of the registration function and of the table
(`base/launch_enrollment.py`, **read**) goes with them.

The surface check (spec 001) gains one rule: an underscore-prefixed name
imported from the contract is a finding, private to the contract.

**Rationale**: FR-002. The contract is open to plugins: every public
name in it may be imported (**read**: `base/surface/check.py`, `OPEN`).
A registration function left public is one a plugin may call on import,
which is the side effect this feature removes. Underscore names were
never meant for plugins, and the new rule makes that checkable.

**Alternatives considered**: *keep the functions and forbid calling
them in documentation* (unenforceable: the check allows every public
contract name); *move the registries out of the contract into the
engine* (the kit's launch renderer reads the enrollment registry, and
the kit may not import the engine).

### R3. When the declared kinds are registered

**Decision**: once per process, after discovery has settled which
plugins are usable (spec 001's `_Discovering.settled`), the loader
registers the declared kinds of the usable plugins, and only theirs.
Discovery is already done once per process and shared by every run
(**read**: `loader._discovery`, cached), so the kinds are too (FR-013,
answered A on 2026-11-18).

**Rationale**: FR-004, FR-005. A kind is registered only after its
plugin is accepted, so nothing is ever registered for a plugin that is
then skipped, and nothing needs taking back.

**Alternatives considered**: *register in each run's load
(`load_plugins`)* (repeated for every registry for no gain, since every
run sees the same accepted plugins; the operator chose the shared form);
*register as each plugin is read* (the old problem: a later collision
would have to undo it).

### R4. How a collision over a kind is found

**Decision**: a declared kind is a registration key like any other
(`(kind sort, name)`), and the collision rules spec 001 applies to keys
apply to it at settling:

- two plugins declaring one kind with different definitions are both
  skipped, in one line naming both and the kind;
- two declaring an equal definition (the same object, or an
  `EnrollmentKind` with the same renderers) are one registration;
- a third claimant of a disputed kind is skipped too, by the same
  pairing that already makes every key collision order-independent;
- a plugin declaring a field kind with one of the system's own names
  (`fk`, `templated`, `deferred_list`, `deferred_list_fk`, **read**:
  `contract/field_kinds.py`) is skipped alone, in a line saying the kind
  is the system's. These names are fixed in the contract, so the rule
  does not depend on whether the resolver has registered them yet.

**Rationale**: FR-006 to FR-008. Collisions are decided on the
candidates' declarations, all known before anything is registered, so
the outcome cannot depend on discovery order. That is the property the
four recorded cases break (spec 001 research R13, tasks T140 to T143).

**Alternatives considered**: *compare the registries before and after
each import* (what is being removed); *let the first declaration win
with a warning* (order dependent, and what FR-017 of spec 001 forbids).

### R5. What leaves the loader

**Decision**: everything spec 001 added to infer and undo registrations
made on import (**read**: `loader.py`, 97 lines in nine functions:
`_shared_kinds`, `_replaced`, `_restore`, `_defined_in`, `_own_package`,
`_inside`, `_a_librarys`, `replaced_a_kind`, `_take_back_kinds`; and
their state in `_Discovering`: the snapshot taken around each import,
`kind_owner`, `kind_claimant`, `collided_kinds`, the `contested`
check). The tests that held that inference
(`engine/tests/test_unusable_plugins.py`, the sections on kinds
registered by a call, a library two plugins share, and a kind claimed
through a library) are replaced by tests of declared kinds.

**Rationale**: FR-009, SC-005, Constitution VII. Deleting is a
first-class outcome.

**Alternatives considered**: none; keeping the inference beside the new
path would leave two ways to bring a kind.

### R6. The four recorded cases, as tests

**Decision**: each case of spec 001 research R13 becomes a test that
runs its plugins in every order of discovery (discovery reads by name,
so the test permutes the names), declaring kinds instead of
registering them:

1. a plugin that fails while loading, beside a usable plugin declaring
   the same kind (T140);
2. two plugins colliding over a kind, with a third that collides with
   one of them over a builder type (T141);
3. two entry points of one package declaring one kind (equal), one of
   them skipped for another reason (T142);
4. two plugins sharing a library's kind object, with a third declaring
   the kind differently (T143).

Each asserts the same accepted plugins, the same skipped and named
plugins, and the same registered kinds, in every order.

**Rationale**: FR-010, SC-001.

### R7. Versions

**Decision**:

- **The contract**: 0.4.4 to **0.5.0**. Two protocol members are added
  and two public functions removed, which a plugin can observe; while
  the contract is 0.x such a change raises the middle number (**read**:
  `packages/contract/README.md`, its version rule). Every range on it,
  `cs-image-system-contract>=0.4,<0.5` in 21 manifests (**read**),
  becomes `>=0.5,<0.6`. No starter names the range (**read**:
  `docs/examples`).
- **The kit**: stays on **0.2.0**. Its changes are additions to its
  declared surface (two properties) and the removal of a re-export that
  is not on the surface (**read**: `base/surface/__init__.py` does not
  list `launch_enrollment`); the 0.2.0 line has not been released, so
  its baseline is re-recorded with the additions (`just
  surface-record`) and no number moves.
- **The Terraform libraries**: unchanged.

**Rationale**: FR-011, and spec 001's version rules.

**Alternatives considered**: *a PATCH of the contract* (wrong: a
protocol member added is observable).

### R8. The Okta plugin

**Decision**: `okta_opa_plugin/sftd_launch.py` keeps its two renderers
and drops its registration call; the plugin's metadata (`OktaTypes`)
declares `EnrollmentKind(SFTD_TOKEN, script_lines, ansible_tasks)`. The
comment in `okta_opa_tf_group_builder.py` that says importing the
module registers the kind is corrected.

**Rationale**: FR-003. The renderers are unchanged to the byte, so the
emission, whose launch-script hash is recorded in every machine's launch
parameters, cannot move (**read**: `sftd_launch.py`'s docstring).

### R9. Code that read a kind before any plugin was loaded

**Decision**: anything that renders a launch with an enrollment kind
does so after the plugins are discovered. A test that rendered one
without discovery, relying on the import side effect (**read**:
`tests/test_posix_identity.py` asserts the kind is registered after
importing the builder module), discovers first or registers the kind it
needs through the test kit.

**Rationale**: the side effect is what is removed; whatever depended on
it must say what it needs.
