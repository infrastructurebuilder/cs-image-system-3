# Feature Specification: Every builder written by its qualified word works as its bare word does

**Feature Directory**: `specs/009-qualified-builder-words`

**Feature Branch**: `feature/009-qualified-builder-words` (to be created from `develop` when planning starts)

**Created**: 2026-11-21

**Status**: Draft

**Input**: User description: "A configuration that writes a builder's class word in its qualified form (state backends such as tf-s3-state/s3 or local-state/local, OS builders such as default-os/rhel, storage builders such as tf-ebs-instance/tf-aws-s3) loads today but does not emit as the bare word does: spec 006's planning (research R2) found 22 of the shared golden's 117 files move, the worst being each Terraform root's `backend \"tf-s3-state/s3\"` label (and its .tfbackend.hcl comment and meta-state/state-locations.yaml entry), which OpenTofu does not accept, so a qualified state backend word produces roots that cannot init; OS builders leak the qualified word into the Packer build's OS update comment, and storage builders into meta-state/storage.yaml's plugin field. Instance and image builder words already emit identically. Every builder kind's qualified class word should validate, bake and emit exactly as its bare word does, as the registry's namespaced words promise (spec 131), without the provider plugins each having to change, while the configuration's written word stays recorded where the system records what was written. Spec 006 covers the runtime word only, by the operator's decision of 2026-11-21 (its D1); this is the separate specification for the other builder kinds. Serves operators and an adopting team, and a plugin author (two plugins may register one bare word, and then only the qualified word says which is meant)."

## Clarifications

### Session 2026-11-21

- Q: Do the system's records (the storage record, the state-location
  record) keep the word as the configuration wrote it, or the same word
  the bare form records? → A: The same word whatever form the tree wrote
  (the class's registered word); a qualified tree's records are identical
  to a bare tree's, and the written word stays in the configuration files
  themselves
- Q: Do runtimes follow this specification's rule too? → A: No; a runtime
  keeps its written word, and specification 006 makes it emit as the
  bare word does (006's FR-006 stands)
- Q: Which release carries this specification? → A: The release batched
  for specifications 002, 003 and 006 if this one merges before it is
  cut; otherwise the next one
- Q: Amend the four statements planning found inaccurate? → A: Yes, as
  the plan writes them (the dated notes below)

**Users served**: operators (who write a qualified word to say which
plugin they mean, or must once two plugins register one bare word); an
adopting team (whose tree, copied from a starter or written by hand, may
use either form); a plugin author (who should not have to do anything for
the qualified form of their words to work).

## Why

Every `type:` word a configuration writes has two forms: the bare word
(`s3`), which is enough while one installed plugin registers it, and the
qualified word (`tf-s3-state/s3`), which names the plugin's namespace and
always works. The system promises the two forms are one declaration: a
configuration that writes either loads the same class.

Specification 006 found that promise broken for a runtime's word, and its
planning found it broken further: a state backend, an OS builder or a
storage builder written by its qualified word loads the right class, but
the word as written then reaches what the run emits. The worst case is a
state backend: every Terraform root of a tree that writes
`type: tf-s3-state/s3` carries `backend "tf-s3-state/s3"`, which OpenTofu
refuses, so not one of those roots can initialise. The others are quieter:
the qualified word appears in a bake's generated comments and in the
storage record. In all, 23 of the shared fixture's 117 emitted files
differ from the bare form's, once user builders are written qualified too
*(amended 2026-11-21: the Input's count of 22 left them out)*.

This matters most exactly when the qualified form is needed: once two
installed plugins register the same bare word, the bare form is refused as
ambiguous, and the qualified form is the only one a configuration can
write. Today such a tree cannot run.

Specification 006 keeps to the runtime word by the operator's decision of
2026-11-21 (its D1); this specification covers every other builder kind.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A qualified state backend word produces roots that run (Priority: P1)

An operator writes `type: tf-s3-state/s3` (or `local-state/local`) for a
state backend instead of the bare word, and every Terraform root bound to
it emits the same backend as the bare word gives, so the roots initialise,
plan and apply exactly as before.

**Why this priority**: it is the one case where the qualified form does not
merely differ but cannot run at all.

**Independent Test**: the shared fixture with its state backends written
qualified emits every root's backend block, backend configuration and
state-location record identical to the bare form's, and a root's
`tofu init` accepts it.

**Acceptance Scenarios**:

1. **Given** a tree whose state backends are written qualified, **When** a
   dry run emits its roots, **Then** every root's backend block and its
   backend configuration are identical to the bare form's.
2. **Given** the same tree, **When** its state locations are recorded,
   **Then** the record is identical to the bare form's.
3. **Given** a root emitted from that tree, **When** OpenTofu initialises
   it, **Then** it accepts the backend.

---

### User Story 2 - Every other builder kind's qualified word emits as its bare word does (Priority: P2)

An operator writes the qualified word for an OS builder, a storage builder,
or any other builder kind the registry serves, and what every lifecycle
emits, and every record the system keeps, is identical to the bare form's.

**Why this priority**: the remaining differences do not stop a run, but
they break the promise and change what an operator reads and reviews.

**Independent Test**: the shared fixture with every builder kind's word
written qualified (runtimes included, once specification 006 lands) emits
all of its files identical to the bare form's.

**Acceptance Scenarios**:

1. **Given** a tree whose OS builders are written qualified, **When** its
   bakes are emitted, **Then** the bake files are identical to the bare
   form's, comments included.
2. **Given** a tree whose storage builders are written qualified, **When**
   its storage is recorded, **Then** the storage record is identical to the
   bare form's.
3. **Given** a tree whose every builder word is written qualified, **When**
   a dry run of every lifecycle emits, **Then** all of its emitted files are
   identical to the bare form's.
4. **Given** an image whose modifications or base are declared through a
   qualified word, **When** its fingerprint is computed, **Then** it equals
   the bare form's, so writing the qualified word never re-bakes an image.

---

### User Story 3 - Two plugins that register one bare word are told apart (Priority: P3)

A plugin author ships a plugin that registers a bare word another
installed plugin also registers. An operator writes each one's qualified
word, and each emits what its own plugin emits.

**Why this priority**: it is the reason the qualified form exists; it
holds only once stories 1 and 2 do.

**Independent Test**: with two test plugins registering one bare state
backend word, a tree writing each one's qualified word emits each plugin's
own backend, and a tree writing the bare word is refused as ambiguous.

**Acceptance Scenarios**:

1. **Given** two installed plugins registering one bare word, **When** a
   tree writes each qualified word, **Then** every line an external tool
   reads is each plugin's own output, as each would emit alone, and the
   records name each qualified word, the registered word of each
   *(amended 2026-11-21)*.
2. **Given** the same plugins, **When** a tree writes the bare word,
   **Then** it is refused as ambiguous, naming both qualified words.

---

### Edge Cases

- A word that names an alias of a class (rather than its name) emits as
  the class's own name does, qualified or bare.
- If the system comes to resolve a plugin's own unqualified word within
  the loading plugin (an implicit qualification, which no code does
  today), that word behaves as the explicit qualified word does
  *(amended 2026-11-21: kept as a rule for a future resolution)*.
- A word whose namespace names no installed plugin is refused at load, as
  today, naming the missing plugin and its extra.
- A tree that mixes forms (some builders bare, some qualified) emits as the
  all-bare tree does.
- The modification fingerprint hashes a builder's type word today; a
  qualified word must not change it, or writing the qualified form would
  re-bake every image that uses it.
- The external tools' own words (an OpenTofu backend type, a Packer source
  type) are not the configuration's words; a qualified configuration word
  must never reach them.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A state backend written by its qualified word MUST emit, in
  every Terraform root bound to it, the same backend block and backend
  configuration as its bare word, and the same state-location record.
- **FR-002**: An OS builder written by its qualified word MUST emit the
  same bake files as its bare word.
- **FR-003**: A storage builder written by its qualified word MUST produce
  the same storage record as its bare word.
- **FR-004**: Every other builder kind the registry serves (instance,
  image, group, user, modification, state, storage, OS and runtime
  builders) MUST emit and record identically whichever form a tree writes;
  instance and image builders, which already do, MUST stay so.
- **FR-005**: A builder's qualified word MUST NOT change any fingerprint,
  lineage record or other identity the system derives from it.
- **FR-006**: The rule MUST be the core's: no provider plugin needs to
  change for its words' qualified form to work, and a plugin written
  against the published kit keeps working unchanged.
- **FR-007**: Every record a run keeps (the storage record, the
  state-location record and any other) MUST hold the same word for a
  builder whatever form the tree wrote: the class's registered word, so a
  qualified tree's records are identical to a bare tree's. The word as the
  operator wrote it stays in the configuration files themselves, which the
  system never rewrites.
- **FR-008**: Two installed plugins registering one bare word MUST each be
  reachable by its qualified word, and the bare word MUST be refused as
  ambiguous, naming both.
- **FR-009**: Every statement in this repository's documentation that the
  change makes false MUST be corrected, including the registry's
  recorded-word rule in the kit's README, which is narrowed to what the
  registry answers: what a run emits and records holds the class's
  registered word.

### Key Entities

- **A builder's class word**: the `type:` a configuration writes for a
  builder, in its bare form (`s3`) or its qualified form
  (`tf-s3-state/s3`), both naming one registered class.
- **What a run emits**: every generated file of every lifecycle, and the
  records the run keeps.
- **An external tool's word**: a word an external tool reads (an OpenTofu
  backend type, a Packer source type), which is a plugin's own and never
  the configuration's.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The shared fixture with every builder kind's word written
  qualified emits all 117 of its files identical to the bare form's
  (today 23 differ).
- **SC-002**: Every Terraform root emitted from a tree with qualified state
  backend words initialises under OpenTofu (today none does).
- **SC-003**: Writing any builder's qualified word changes zero image
  fingerprints, so zero images re-bake.
- **SC-004**: Zero provider plugins change for the fix; a plugin built
  against the published kit before it passes its own tests after it.
- **SC-005**: With two plugins registering one bare word, both qualified
  words work and the bare word is refused, in every order the plugins are
  found.

## Assumptions

- Specification 006 lands the runtime word first; this specification's
  whole-tree proof (SC-001) writes runtimes qualified only once it has.
- The shared fixture stands for this repository's providers at the time:
  AWS and docker today, docker alone once specification 007 moves the AWS
  family out; the proof runs on what the fixture then declares, and the
  test kit's double runtime (specification 007, research R6) carries what
  docker cannot.
- The families released from their own repositories (the Google Cloud
  family today) gain the fix with this repository's release that carries
  it and the Terraform libraries' 0.2.2, the fix being the engine's and
  the Terraform library's; their own tests of qualified words widen then
  (specification 006, research R11) *(amended 2026-11-21)*.
- The order of work is the operator's decision of 2026-11-21: specification
  008, then 003, then 007, with 006, 002 and this one fitting between.
