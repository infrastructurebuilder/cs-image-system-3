# Feature Specification: Kinds a plugin declares, not kinds it registers on import

**Feature Directory**: `specs/004-kinds-in-metadata`

**Feature Branch**: `feature/004-kinds-in-metadata` (to be created from `develop` when planning starts; spec 001, which it follows, is merged)

**Created**: 2026-11-18

**Status**: Draft

## Clarifications

### Session 2026-11-18

- Q: Should the kind registries stay shared by every run in the process,
  or become each run's own, like the type registry? → A: Stay shared by
  the process, registered once when the plugins are accepted (FR-013).
  Every run in a process is given the same accepted plugins, so a
  registry per run would add no isolation.

**Input**: User description: "Plugins declare their enrollment kinds and field kinds in their metadata instead of registering them as a side effect of being imported. The loader registers them itself, only for plugins it accepts, so a skipped plugin's kinds are never registered, a collision over a kind is found like any other registration collision, and nothing is left to take back. This changes the contract and the Okta plugin."

**Users served**: a plugin author (who writes a plugin that brings a kind of its own); operators (who install several plugins and need a broken or conflicting one to change nothing for the others).

## Why

Two kinds of thing a plugin can bring are registered today in a way no
other plugin contribution is. An **enrollment kind** (how an instance is
enrolled with an identity service at launch) and a **field kind** (how a
configuration field of a special sort is read and resolved) are added by
a plugin's own code calling a registration function when the plugin's
module is imported. They land in registries that every run in the
process shares.

Everything else a plugin brings (its builder types, its models, its
commands, its setup section) it declares, and the system decides whether
to accept it. Because kinds are registered by a side effect instead, the
system can only work out afterwards which plugin registered which kind
and try to undo it when the plugin is skipped. Specification 001 did that
work and went through five rounds of corrections. Four cases remain,
recorded in its research (R13) and its tasks (T140 to T143). In each, a
broken or conflicting plugin can still change what another plugin can
do, or the outcome depends on the order the plugins are found in. Those
are the two things specification 001 exists to rule out.

None of the four affects the plugins in this repository today. Only the
Okta plugin registers a kind, and from its own module. They affect the
first outside plugin that registers a kind through a shared library, and
they make the loader's rules hard to state and hard to trust.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A plugin declares its kinds and the system registers them (Priority: P1)

A plugin author writes an identity plugin that enrolls instances in a
way of its own. They declare the enrollment kind with the rest of the
plugin's contributions, as they declare its builder types. They do not
call a registration function. When the plugin is installed and accepted,
a configuration that uses the kind validates and its launch scripts
carry the kind's steps, exactly as with a kind registered today.

**Why this priority**: this is the change itself. Every other story
follows from kinds being declared rather than registered on import.

**Independent Test**: install a plugin that declares an enrollment kind
and a field kind and registers neither; a configuration that uses both
validates and emits what the kinds render. With the plugin not
installed, the same configuration is refused, naming the kind.

**Acceptance Scenarios**:

1. **Given** an accepted plugin that declares an enrollment kind,
   **When** a configuration launches an instance with that enrollment,
   **Then** the launch carries the kind's steps.
2. **Given** an accepted plugin that declares a field kind, **When** a
   configuration uses a field of that kind, **Then** the field is read
   and resolved by the kind's handler.
3. **Given** the Okta plugin, **When** the frozen fixture and the
   reference configuration are generated after this change, **Then** the
   emission is byte-identical to before it.

---

### User Story 2 - A plugin that is not used leaves nothing behind (Priority: P2)

An operator has a plugin installed that fails to load, or that is
skipped because it collides with another. None of its kinds is
registered, whatever it imported, and every other plugin keeps every
kind it declares, whatever it shares with the skipped one.

**Why this priority**: this is the property the cases left by
specification 001 break. It is what makes "a plugin that cannot be used
is an absence" true for kinds as for everything else.

**Independent Test**: install a plugin that declares a kind and fails to
load, and one that declares a kind and collides with another plugin over
a builder type; neither kind is registered. Install two plugins that
share a library and declare the same kind with the same definition, then
skip one; the other keeps the kind.

**Acceptance Scenarios**:

1. **Given** a plugin that fails to load, **When** the system loads,
   **Then** no kind it declares or imports is registered.
2. **Given** a plugin skipped because it collides with another,
   **When** the system loads, **Then** no kind it declares is registered,
   and no kind another accepted plugin declares is removed.
3. **Given** two plugins that use one shared library, **When** one of
   them is skipped, **Then** the other's kinds are all registered.

---

### User Story 3 - A collision over a kind is reported like any other (Priority: P3)

An operator installs two plugins that both declare one enrollment kind
(or one field kind) with different definitions. Both are skipped, one
line names both and the kind, and neither kind is registered. The result
is the same whichever plugin the system happens to find first, and a
third plugin that collides with neither loads.

**Why this priority**: specification 001 already promises this for
every other registration. Kinds are the one place it does not hold in
every order today.

**Independent Test**: for each pair of the four cases recorded in
specification 001 (research R13, tasks T140 to T143), install the
plugins in every order; the same plugins are skipped and named, and the
same kinds are registered, in every order.

**Acceptance Scenarios**:

1. **Given** two plugins declaring one kind differently, **When** the
   system loads, **Then** both are skipped, one line names both and the
   kind, and the kind is registered by neither.
2. **Given** two plugins declaring one kind identically, **When** the
   system loads, **Then** both load and the kind is registered once.
3. **Given** any set of plugins, **When** they are found in a different
   order, **Then** the same plugins are accepted, the same are skipped
   and named, and the same kinds are registered.
4. **Given** a plugin that declares a kind the system itself provides,
   **When** the system loads, **Then** that plugin is skipped and named
   and the system's own kind is unchanged.

---

### User Story 4 - The loader is simpler, not cleverer (Priority: P4)

A maintainer reads the loader after this change. The rules for kinds are
the same as for every other declared contribution, and the code that
specification 001 added to infer and undo registrations made on import
is gone.

**Why this priority**: Constitution VII. The cure for five rounds of
inference is to remove the need for it, and that is only shown by its
removal.

**Independent Test**: the loader no longer reads the shared kind
registries before and after a plugin is imported, and the tests that
held the inference are replaced by the stories above.

**Acceptance Scenarios**:

1. **Given** the loader after this change, **When** a plugin is
   imported, **Then** nothing compares the kind registries before and
   after the import.
2. **Given** the limit recorded in specification 001 (research R13 and
   its Complexity Tracking), **When** this feature is done, **Then** the
   limit is removed from the record because it no longer holds.

---

### Edge Cases

- A plugin built for the previous contract still calls the registration
  function on import. It cannot be installed beside this release: the
  contract's version range it declares no longer matches. A plugin
  inside this repository that still did so would fail its import check.
- A plugin declares a kind and also registers it on import. The system
  treats only the declared kind as the plugin's; the call is not
  available to a plugin.
- A plugin declares two kinds with one name. It is refused, naming the
  kind.
- The system's own field kinds (a reference to another item, a value
  that is rendered from a template) stay the system's and are never
  replaced by a plugin.
- A run that loads a second configuration in the same process sees the
  same kinds as the first, because the kinds are the process's and are
  registered once (FR-013).

## Requirements *(mandatory)*

### Functional Requirements

**Declaring**

- **FR-001**: A plugin MUST be able to declare, with its other
  contributions, each enrollment kind and each field kind it provides,
  with what the kind renders or how it is read.
- **FR-002**: Registering a kind as a side effect of importing a plugin
  MUST no longer be part of what a plugin may use. The system's own
  field kinds are provided by the system and are not a plugin's.
- **FR-003**: The Okta plugin MUST declare its enrollment kind instead of
  registering it on import, and the emission of the frozen fixture and
  of the reference configuration MUST be byte-identical before and after.

**Registering**

- **FR-004**: The system MUST register a plugin's declared kinds only
  for a plugin it has accepted, and only after every collision among
  the installed plugins is settled.
- **FR-005**: No kind declared by, or registered through the import of,
  a plugin that is skipped MUST be registered.
- **FR-006**: Two plugins declaring one kind with different definitions
  MUST both be skipped, named together in one line with the kind; two
  declaring it identically MUST both load.
- **FR-007**: A plugin declaring a kind the system itself provides MUST
  be skipped and named, and the system's kind MUST be unchanged.
- **FR-008**: Which plugins are accepted, which are skipped, and which
  kinds are registered MUST be the same whatever order the plugins are
  found in.

**Simplifying**

- **FR-009**: The system MUST NOT compare the kind registries before and
  after importing a plugin, and the code specification 001 added to
  record who registered a kind on import and to undo it MUST be removed.
- **FR-010**: The four cases recorded in specification 001 (research
  R13, tasks T140 to T143) MUST each be held by a test that runs the
  plugins in every order.

**The contract and its record**

- **FR-011**: The contract's version MUST rise by its middle number, and
  every range on it in this repository and in the starters MUST move.
- **FR-012**: The guide for writing a provider, the contract's own
  description, and specification 001's research and plan MUST say how
  a plugin brings a kind after this change, and the limit recorded in
  specification 001 MUST be marked as removed by this one.

- **FR-013**: The accepted kinds MUST be held once for the whole
  process, registered when the installed plugins are accepted, and every
  run in the process MUST see the same kinds. They do not become each
  run's own.

### Key Entities

- **Enrollment kind**: a named way an instance is enrolled with an
  identity service at launch; it renders the launch script's steps and
  the equivalent configuration-management steps.
- **Field kind**: a named sort of configuration field that the system
  reads and resolves in a particular way (for example a reference to
  another item).
- **Plugin's declared contributions**: what a plugin says it brings,
  which the system accepts or refuses as a whole; after this change it
  includes the plugin's kinds.
- **Kind registry**: where the accepted kinds are held for the system
  to use: one for the whole process, filled once when the installed
  plugins are accepted.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In every order of discovery, each of the four cases
  recorded in specification 001 produces the same accepted plugins, the
  same skipped and named plugins, and the same registered kinds: 4 of
  4 cases, every permutation.
- **SC-002**: With a plugin that declares a kind and fails to load, or
  is skipped for a collision, 0 of its kinds are registered.
- **SC-003**: With two plugins sharing a library and one of them
  skipped, 100% of the other's declared kinds are registered.
- **SC-004**: The emission of the frozen fixture and of the reference
  configuration is unchanged.
- **SC-005**: The loader is smaller than before the change, measured in
  source lines, and no part of it inspects the kind registries around a
  plugin's import.
- **SC-006**: A plugin author learns how to bring a kind from one place
  in the guide, without reading the loader.

## Assumptions

- The contract is still 0.x, so a change a plugin can observe raises the
  middle number (0.4 to 0.5) and is the breaking step, as the contract's
  own version rule says.
- No plugin outside this repository is known to register a kind; the
  only one inside it is the Okta plugin. The change therefore breaks no
  known plugin beyond the one it updates.
- Specification 001 is merged first: this feature removes code it added
  and amends its record.
- The registration functions are the contract's; the SDK's declared
  surfaces (specification 001) do not list them, so the SDK's version
  lines are not moved by their removal. The kit re-exports one of them
  for its own use, which this change removes with it.
