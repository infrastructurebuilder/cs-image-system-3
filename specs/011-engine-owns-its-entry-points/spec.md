# Feature Specification: The engine declares its own plugin and modules, not the kit

**Feature Directory**: `specs/011-engine-owns-its-entry-points`

**Feature Branch**: `feature/011-engine-owns-its-entry-points` (to be created from `develop` when planning starts)

**Created**: 2026-11-22

**Status**: Draft

**Input**: User description: "Base's two entry points move to the engine (REMINDERS.md, raised after the release that followed stage 113's; 0.1.11 and 0.1.12 have both gone out and the entry points are still in packages/base/pyproject.toml). Stage 113 split base into a kit and an engine and kept in the kit's pyproject.toml the two entry points that name engine modules: the base plugin (cs_image_system.plugins.base, cs_image_system.engine.init:initialize) and the terraform module directory (cs_image_system.modules, cs_image_system.base:tfmodules, which holds the bootstrap's bootstrap_github). That kept every .csis-module stamp's plugin: at base, so no tree's module copies changed at that release. The cleaner form moves both to the engine's distribution; the module entry's namespace then becomes engine, every stamp changes, and every tree refreshes its modules at its next take, which the take now does by itself (stage 112). Plan it as a stage of its own."

**Users served**: a plugin author (who installs the kit to write a
plugin, and should get a kit that names nothing outside itself);
operators and an adopting team (whose trees hold copies of the
bootstrap module, and must take the change without editing anything by
hand).

## Why

The system's published libraries are split in two. The **kit**
(`cs-image-system-base`) is what a plugin author installs and writes
against. The **engine** (`cs-image-system-engine`) is what loads the
plugins and runs a configuration. A plugin author's install holds the
kit and not the engine.

When the two were split (stage 113, 2026-11-14), two declarations that
belong to the engine stayed in the kit's package metadata, so that no
tree's files would change in that release:

- **the base plugin**: the plugin the engine loads first, which gives
  every executable its fallback version checker and the default storage
  mapping. The kit declares it, but its code is the engine's, so a kit
  installed alone declares a plugin it cannot load;
- **the module directory**: the Terraform modules the kit ships as
  package data, which today is the one bootstrap module,
  `bootstrap_github`, that the engine's bootstrap uses.

The operator's decision then was to move both once the release after
stage 113's had gone out. Two releases have since (0.1.11 and 0.1.12),
and the move is overdue.

Moving the module directory changes the name the modules are stamped
with. Every tree's copy of the bootstrap module says which plugin it
came from (`plugin: base` today, `plugin: engine` after). Since stage
112, a tree's take of a new release refreshes unedited module copies by
itself, so the change reaches every tree with no hand edit.

## Clarifications

### Session 2026-11-22

- Q: What does a tree that writes a base plugin word in its old qualified
  form (`base/<word>`) get once the declaration moves to the engine? → A:
  Validation refuses it, with a message naming the new form
  (`engine/<word>`) and the bare word; no alias is kept, since no tree
  writes the old form today

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The kit names nothing outside itself (Priority: P1)

A plugin author installs the kit alone and lists what it declares. Every
plugin and module directory it declares can be loaded from the kit
itself; nothing points into the engine.

**Why this priority**: it is the defect: the kit is the library an
outside author depends on, and it should not declare code it does not
ship.

**Independent Test**: install the kit alone in a clean environment;
every entry point it declares loads, and none names the engine.

**Acceptance Scenarios**:

1. **Given** the kit installed alone, **When** its declared entry points
   are listed and each loaded, **Then** every one loads, and none names a
   module outside the kit.
2. **Given** the engine installed, **When** the plugins are discovered,
   **Then** the base plugin is found, from the engine's own declaration,
   and registers exactly what it registers today.
3. **Given** the engine installed, **When** the modules are listed,
   **Then** `bootstrap_github` is listed once, from the engine, with the
   same content as today.

---

### User Story 2 - A tree takes the release without a hand edit (Priority: P1)

An operator or an adopting team takes the release that carries the move.
Their tree's copy of the bootstrap module is refreshed by the take, its
stamp now naming the engine, and nothing else in the tree changes.

**Why this priority**: the move must cost a tree nothing; a take that
stopped on the module, or refused it as edited, would.

**Independent Test**: a tree whose bootstrap module copy is stamped
`plugin: base`, untouched since its take, takes the release: the copy is
refreshed, its stamp says `plugin: engine`, and the module's files are
otherwise unchanged; the reference configuration's own take does the
same.

**Acceptance Scenarios**:

1. **Given** an unedited copy stamped `plugin: base`, **When** the tree
   takes the release, **Then** the copy is refreshed and stamped
   `plugin: engine`, and the run says so.
2. **Given** a copy the tree edited, **When** it takes the release,
   **Then** the take refuses it by name, as for any edited copy, saying
   how to keep the edit (`config: module_sources`) or take the release's
   copy.
3. **Given** a tree that names `bootstrap_github` in `config:
   module_sources`, **When** it takes the release, **Then** its copy is
   left alone, as today.
4. **Given** the reference configuration, **When** it takes the release
   and runs its drift check, **Then** the check is green.

---

### User Story 3 - Nothing a tree writes changes meaning (Priority: P2)

A configuration that names any word the base plugin registers loads and
emits exactly as before.

**Why this priority**: the base plugin's registrations take their
namespace from the distribution that declares them, so the move changes
their qualified form; a tree must not break for it.

**Independent Test**: the shared fixture and the reference
configuration validate and emit byte-identically before and after the
move.

**Acceptance Scenarios**:

1. **Given** a tree using the base plugin's words in their bare form,
   **When** it is validated and emitted, **Then** the result is
   byte-identical to before.
2. **Given** a tree writing a base plugin word in its old qualified form
   (`base/<word>`), **When** it is validated, **Then** it is refused,
   with a message naming the new form (`engine/<word>`) and the bare
   word.

### Edge Cases

- A tree that took a release before stage 113 and never since holds a
  stamp from an older release; the take refreshes it the same way.
- A tree whose module directory holds no copy of `bootstrap_github`
  (one that never bootstrapped GitHub) gains none it did not have.
- A copy whose stamp names `base` but whose content no release shipped is
  an edited copy, refused by name, as today.
- The kit's version moves for the removal of its declarations; a plugin
  written against the kit, which never used those declarations, keeps
  working.
- An install that holds an older kit beside a newer engine (or the
  reverse) never finds the base plugin or the module twice, nor zero
  times.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The kit's package metadata MUST NOT declare the base plugin
  or a module directory; every entry point the kit declares MUST be
  loadable from the kit alone.
- **FR-002**: The engine's package metadata MUST declare the base plugin
  and the module directory that holds `bootstrap_github`, and the module
  files MUST ship with the engine.
- **FR-003**: The base plugin MUST register exactly what it registers
  today, and the module directory MUST hold exactly the modules it holds
  today, with the same content.
- **FR-004**: An unedited copy of a moved module in a tree MUST be
  refreshed by that tree's take of the release, its stamp naming the
  engine; an edited copy MUST be refused by name as any edited copy is;
  a copy named in `config: module_sources` MUST be left alone.
- **FR-005**: The shared fixture and the reference configuration MUST
  validate and emit byte-identically before and after the move, the
  stamp of the moved module excepted.
- **FR-006**: A base plugin word written in its old qualified form
  (`base/<word>`) MUST fail validation with a message naming the new form
  (`engine/<word>`) and the bare word; no alias is kept.
- **FR-007**: No install MUST find the base plugin, or any module, twice
  or not at all, whatever the kit's and the engine's versions within the
  ranges the system allows.
- **FR-008**: The kit's version MUST move by the kit's version rule for
  the removal, and the engine's with it; the release that carries the
  move MUST say, in its notes, that every tree's bootstrap module stamp
  changes at the take and that nothing need be done by hand.
- **FR-009**: Every statement in this repository's documentation that the
  move makes false (the kit's and the engine's READMEs say the kit
  declares both) MUST be corrected, and the reminder in `REMINDERS.md`
  closed.

### Key Entities

- **The kit**: the library a plugin is written against
  (`cs-image-system-base`).
- **The engine**: the library that loads plugins and runs a
  configuration (`cs-image-system-engine`).
- **The base plugin**: the plugin the engine loads first; its words take
  their namespace from the distribution that declares it.
- **A module copy and its stamp**: a Terraform module copied into a tree,
  and the file beside it naming the plugin, the release and the content
  hash it came from.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The kit installed alone declares zero entry points that
  name code outside it.
- **SC-002**: Every tree that takes the release refreshes its bootstrap
  module copy with zero hand edits, and the reference configuration's
  drift check is green after its take.
- **SC-003**: The shared fixture's emission is byte-identical before and
  after the move (117 of 117 files), and the reference's likewise but for
  the one module stamp.
- **SC-004**: Zero plugins written against the published kit need a
  change.

## Assumptions

- Stage 112's take refreshes unedited module copies by itself; the move
  relies on it and does not change it.
- No tree today writes a base plugin word in its qualified form (the
  reference configuration writes none); one that does is refused with
  the new form named (FR-006).
- The release that carries it is the one batched for specifications 002,
  003 and 006 if this merges before it is cut; otherwise the next one.
- The families released from their own repositories (the Google Cloud
  family, and the AWS family and Okta plugin once specifications 007 and
  008 move them) declare no module or plugin under the kit's name, and
  need no change.
