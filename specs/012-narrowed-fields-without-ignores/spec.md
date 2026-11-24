# Feature Specification: A provider narrows its own fields with no type-check exception

**Feature Directory**: `specs/012-narrowed-fields-without-ignores`

**Feature Branch**: `feature/012-narrowed-fields-without-ignores` (to be created from `develop` when planning starts)

**Created**: 2026-11-22

**Status**: Planned 2026-11-24 ([plan](plan.md))

**Input**: User description: "Create a spec to deal with the pyright ignores. Take a new look at the code to see if there is a simple solution, but still move it to a spec. Ask questions where relevant." (REMINDERS.md, Before 1.0, \"The nine variable-override ignores\", the operator 2026-11-12 at hygiene bundle XXV item 5: nine pydantic fields carry `# pyright: ignore[reportIncompatibleVariableOverride]` where a subclass narrows a field's type on purpose; keep them, or make the base models generic over the field's type so that no ignore is needed.)

**Users served**: a plugin author (who writes a provider's own
`credentials:` or `variables:` class and should be able to declare it
with the type checker's full support, not an exception copied from the
system's own plugins); maintainers (whose acceptance tests hold the type
check at zero errors, and for whom every exception is a place a real
error could hide).

## Why

A provider plugin declares its own form of a field the kit defines
generally: a runtime's `credentials:` (the AWS runtime's own class), a
storage builder's `variables:` (the docker volume's, the EBS, EFS and S3
storage's, the Google Cloud storage's). The narrowed class is what makes
the configuration loader refuse a key the provider does not know, so the
narrowing is deliberate and correct.

The type checker cannot tell a field that is only ever narrowed from one
that is reassigned, so each such field carries an exception that silences
the rule (`reportIncompatibleVariableOverride`). There are nine: six in
this repository (the docker volume's `variables`, the AWS runtime's
`credentials`, the EBS, EFS and S3 storage's `variables`, and an OS
builder entry's `description`), and three in the Google Cloud family's
repository. The operator's decision of 2026-11-12 kept them, with the
question to settle before 1.0: keep them, or make the kit's models
generic over the field's type so that none is needed.

**A fresh look (2026-11-22) found a simple form.** A base model that is
generic over the field's type, with each provider naming its own class as
the type argument, passes the type check with no exception and keeps the
loader's refusal of unknown keys. A provider that names no type argument
keeps the kit's general class and its default, so plugins written against
the published kit keep working unchanged. A probe of exactly that shape
passed both the type check (in the repository's mode) and the loader's
validation. The OS builder entry's `description` is simpler still: its
narrowing buys only the refusal of an explicitly empty description, and
its accessor already answers "maybe none".

## Clarifications

### Session 2026-11-22

- Q: With the OS builder entry's `description` narrowing removed, what
  does an explicitly empty description do? → A: It is accepted as no
  description (the kit's "text or none"); the template default still
  applies when the key is absent
- Q: Is removing the families' exceptions (the Google Cloud family's
  three, the AWS family's four once it moves) part of this
  specification? → A: No: this specification ends at this repository,
  with the kit and the Terraform library released; each family drops its
  own when it next takes the kit, in its own repository

### Session 2026-11-24 (at planning)

- Q: Removing the description's exception widens the kit's surface
  entry for it (`str` to `str | None`), a reshape the surface check
  refuses without a new middle number, while the operator's rule of
  2026-11-23 moves only the last number. How is the description
  handled? → A: Deferred. This specification removes the five
  provider exceptions; the description keeps its exception until the
  operator ends the patch-only rule, and `REMINDERS.md` keeps a line
  for it. Story 3, FR-006 and the description's share of FR-003 and
  SC-001 wait with it

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A provider declares its own credentials or variables class with no exception (Priority: P1)

A plugin author writes a runtime with its own credentials class, or a
storage builder with its own variables class, by naming that class as
the base model's type argument. The type check passes with zero errors
and no exception, and a configuration that writes a key the class does
not know is refused at load, naming the key.

**Why this priority**: it is the whole of the question; every other
story follows from it.

**Independent Test**: each of this repository's narrowed fields is
rewritten in the new form and carries no exception; the type check
reports zero errors; a configuration with an unknown key under each
field is refused at load as today.

**Acceptance Scenarios**:

1. **Given** the AWS runtime's credentials and the docker, EBS, EFS and
   S3 storage variables written in the new form, **When** the type check
   runs, **Then** it reports zero errors and the repository holds no
   `reportIncompatibleVariableOverride` exception.
2. **Given** a configuration writing an unknown key under any of those
   fields, **When** it is loaded, **Then** it is refused, naming the
   field path, exactly as today.
3. **Given** the shared fixture and the reference configuration, **When**
   they are validated and emitted, **Then** the result is byte-identical
   to before.

---

### User Story 2 - A plugin written against the published kit keeps working (Priority: P1)

A plugin author whose plugin subclasses the kit's runtime or storage base
without naming a type argument upgrades the kit and changes nothing. The
plugin loads, validates and passes its own tests as before.

**Why this priority**: the kit is published and other repositories build
on it; a change that broke an unparametrized subclass would break them.

**Independent Test**: a plugin built against the kit before the change
(this repository's docker family's own isolated run, at the low end of
the kit's range) passes its own tests against the kit after it.

**Acceptance Scenarios**:

1. **Given** a subclass that names no type argument, **When** it is
   loaded, **Then** its field is the kit's general class with the kit's
   default, as today.
2. **Given** a plugin's isolated run at the low and high ends of the
   kit's range, **When** it runs, **Then** it passes with zero skipped.

---

### User Story 3 - An OS builder entry's description needs no exception (Priority: P2; DEFERRED 2026-11-24)

**Deferred** (Clarifications, 2026-11-24): this story waits for the
first new middle number of the kit after the patch-only rule ends. It
is kept as written so that the work it needs is not lost.

The OS builder entry's `description` carries its template default
without narrowing the type the kit gives it.

**Why this priority**: it is the one exception that is not about a
provider's class, and the simplest to remove.

**Independent Test**: the field carries no exception, the type check
passes, and every entry that writes no description still gets the
template's.

**Acceptance Scenarios**:

1. **Given** an entry with no `description:`, **When** it is loaded,
   **Then** its description is the template's, as today.
2. **Given** an entry that writes an empty description (`description:`
   with no value), **When** it is loaded, **Then** it is
   accepted, and the entry has no description, as the kit's accessor
   already allows.

---

### User Story 4 - The families released elsewhere can drop theirs (Priority: P3)

A family released from its own repository (the Google Cloud family's
three exceptions, the AWS family's four once specification 007 moves
it) can remove its exceptions in the form story 1 sets as soon as it
takes the released kit and Terraform library. Doing so is that family's
own work, in its own repository; this specification ends at this one.

**Why this priority**: the exceptions exist because of the kit's shape;
the kit's release is what this repository owes them.

**Independent Test**: with the released kit and Terraform library, a
scratch copy of the Google Cloud family's storage model writes its three
fields in the new form with the type check at zero errors; nothing in
that repository is changed by this specification.

**Acceptance Scenarios**:

1. **Given** the released kit and Terraform library, **When** a family's
   narrowed field is written in the new form, **Then** the type check
   reports zero errors with no exception.
2. **Given** this specification complete, **When** its records are read,
   **Then** they name each family that still carries exceptions and say
   the removal is that family's.

### Edge Cases

- A provider that narrows a field the kit has not made generic (a field
  added later) still needs the exception; the rule for one is to make the
  kit's field generic in the same way, not to add an exception.
- A subclass of a provider's model (a second level of narrowing) names
  its own class as the argument and passes the same way.
- The loader's error message for an unknown key names the same field path
  as today; the generic form must not change it.
- The repository's type-check configuration comments say each narrowed
  field carries an exception; they are corrected.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The kit's runtime base and the Terraform library's storage
  base MUST let a subclass name its own credentials or variables class as
  a type argument, with no type-check exception needed.
- **FR-002**: A subclass that names no type argument MUST keep the kit's
  general class and default, unchanged.
- **FR-003** (the description excepted: deferred 2026-11-24): Every
  field in this repository that carries a
  `reportIncompatibleVariableOverride` exception today MUST carry none,
  and the type check MUST report zero errors.
- **FR-004**: The loader MUST refuse an unknown key under a narrowed
  field exactly as today, naming the same field path.
- **FR-005**: The shared fixture and the reference configuration MUST
  validate and emit byte-identically before and after.
- **FR-006** (DEFERRED 2026-11-24, with story 3): An OS builder
  entry's description MUST keep its template default when the key is
  absent, and an explicitly empty description MUST be accepted as no
  description.
- **FR-007**: The kit's and the Terraform library's versions MUST move by
  their version rule for the change, and their surface baselines with
  them; a plugin at the low end of their range MUST pass its own tests.
- **FR-008**: This specification MUST NOT change a family released
  from its own repository; its records MUST name each family that still
  carries exceptions, and the released kit MUST let each remove them in
  the form FR-001 sets.
- **FR-009**: The type-check configuration's comment, the kit's README
  where it shows a narrowed field, and `REMINDERS.md`'s item MUST be
  corrected or closed.

### Key Entities

- **A narrowed field**: a field the kit declares with a general class
  (credentials, module variables) that a provider declares with its own,
  stricter class.
- **A type argument**: the provider's class named on the base model,
  which tells the type checker the field's narrowed type.
- **A type-check exception**: a comment that silences one rule on one
  line.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001** (as deferred 2026-11-24: one remains, the
  description's): Zero `reportIncompatibleVariableOverride` exceptions
  remain
  in this repository (six today), with the type check at zero errors.
- **SC-002**: Every unknown key under a narrowed field is still refused
  at load, in every case the tests hold today.
- **SC-003**: The shared fixture's emission is byte-identical (117 of 117
  files).
- **SC-004**: Zero plugins written against the published kit need a
  change.

## Assumptions

- The repository's type check stays in its present mode ("standard");
  the generic form was probed in that mode. A stricter mode might ask an
  unparametrized subclass for its type argument; that is not this
  specification's concern.
- The order of work is the operator's (specification 008, then 003, then
  007, with 006, 002, 009 and others fitting between); if this lands
  before 007, the AWS family's four exceptions are removed here, before
  the family moves.
- The release that carries it is the next one after it merges.
