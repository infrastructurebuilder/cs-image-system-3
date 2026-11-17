# Feature Specification: A provider that stands alone (docker first)

**Feature Directory**: `specs/001-standalone-docker-provider`

**Feature Branch**: `feature/001-standalone-docker-provider`

**Created**: 2026-11-16

**Status**: Implemented on the feature branch, 2026-11-17; not merged. Results and departures are in [tasks.md](tasks.md), under Records. Open: tasks T024 to T026 (four docker test files that still live in the every-provider suite).

**Input**: User description: "One provider family (docker first) builds, tests and versions with only its own declared dependencies, so it can live outside this repository. The docker family is isolated inside this repository; no repository move yet. The kit is the SDK a plugin is written against: it gets a declared public surface and its own version, and a provider pins a range of it."

**Users served**: a plugin author (primary); operators and an adopting team (they install one provider without being affected by another).

## Why

The goal for the system is that one runtime or plugin set cannot interfere
with another. Today that is true of imports and installs and not of
anything else: every provider is tested through one shared harness, one
shared fixture and one shared golden; every provider pins the kit at an
exact version; and several run-time channels let one installed plugin
change or break another. Until a single provider can be proven on its own,
moving any provider to its own repository proves nothing.

The docker family (the docker runtime and its Terraform roots) goes first
because it needs no cloud account and costs nothing to exercise.

## Clarifications

### Session 2026-11-16

- Q: Once the core and the docker family each have their own fixture and
  golden, what happens to today's shared fixture and golden, which mix
  AWS, Google Cloud and docker in one configuration? → A: They stay
  whole and unmoved, as an "every provider installed" suite that is no
  longer part of the core's tests. The core and the docker family get
  new, smaller ones of their own.
- Q: Does this feature finish with the docker family still inside this
  repository, or actually moved to a repository of its own? → A: It
  stays in this repository. The move is a later specification; this
  feature does not perform it and does not forbid it.
- Q: What version does the kit start at when it gets a version of its
  own, and what change forces the number up? → A: It stays below 1.0,
  like the contract, and starts at 0.2.0. Removing or altering anything
  on the public surface raises the middle number; adding to the surface
  raises the last number. A provider pins one middle number.
- Q: When must the docker family be tested against both ends of its kit
  range: on every change, or only before a release? → A: On every
  change, both ends. An end that is already published is installed from
  the index. An end that is not published yet is taken from this
  repository's build and reported as a development install.
- Q: When a core check needs somewhere local to run, who says which
  installed provider supplies that place? → A: A provider declares that
  it can serve as a local stand-in. If exactly one such provider is
  installed, it is used and the run says which. If two or more are
  installed, the person running the check must name one, and the check
  fails until they do.
- Q: When the core's tests run "with no provider installed", must the
  Okta identity plugin also be absent, or only docker, AWS and Google
  Cloud? → A: Okta is absent too. "The core" is exactly what a plain
  install of `cs-image-system` brings with no extras. Everything
  installed as an extra (docker, AWS, Google Cloud, Okta) is outside it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The docker family proves itself alone (Priority: P1)

A plugin author works on the docker family. They install the family and
only what it declares it depends on, run the family's own tests, and get a
verdict about the docker family and nothing else. No other provider is
installed, and no test file outside the family is needed.

**Why this priority**: this is the property everything else rests on. If
the family cannot be tested alone it cannot be owned, versioned or moved
alone.

**Independent Test**: in a clean environment containing the docker family
and its declared dependencies only, run the family's test suite. It passes
with no test skipped for a missing provider. Then copy the family's
directory to a location outside the workspace and repeat: same result.

**Acceptance Scenarios**:

1. **Given** a clean environment with only the docker family and its
   declared dependencies installed, **When** the family's tests are run,
   **Then** they all run and pass, and none imports another provider or a
   test helper that lives outside the family.
2. **Given** the docker family's own fixture configuration, **When** its
   emission is generated, **Then** it is byte-identical to the family's
   own golden.
3. **Given** a copy of the family's directory outside the workspace,
   **When** its dependencies are installed from built packages and its
   tests are run, **Then** the result is the same as inside the workspace.
4. **Given** any change to the repository, **When** CI runs, **Then** the
   isolated run of the docker family is one of its jobs, and that job
   cannot report success without having run the tests.

---

### User Story 2 - The core proves itself with no provider (Priority: P2)

A maintainer of the core changes the kit or the engine. The core's own
tests run and pass with nothing beyond the core installed, so a core
change is judged on the core, and a provider's defect cannot fail the
core's bar.

**Why this priority**: isolation has two sides. A provider that stands
alone is only half proven while the core still needs that provider to
test itself.

**Independent Test**: in a clean environment holding only what a plain
install with no extras brings, run the core's tests. They pass. Nothing in
them asks for docker, AWS, Google Cloud or Okta.

**Acceptance Scenarios**:

1. **Given** an environment with no extra installed (no docker, AWS,
   Google Cloud or Okta), **When** the core's tests are run, **Then**
   they all run and pass.
2. **Given** the core's own fixture configuration, which declares no
   provider-specific runtime and nothing that needs Okta, **When** its
   emission is generated, **Then** it is byte-identical to the core's
   golden.
3. **Given** a core check that needs somewhere local to run (for example
   the modification tests), **When** no installed provider offers one,
   **Then** the check reports that it did not run as a failure or as an
   explicit exclusion the caller asked for, never as a pass.

---

### User Story 3 - The kit is an SDK a provider can pin (Priority: P3)

A plugin author needs to know what they may import from the kit and which
versions of the kit their provider works with. The kit states its public
surface in one place and carries its own version. The docker family
depends on a range of kit versions, not on one exact build, and is checked
against the kit at both ends of that range on every change.

**Why this priority**: without a declared surface and a version, a
provider outside the workspace has nothing stable to depend on, and a
range is a promise nobody can keep.

**Independent Test**: read the kit's declared surface; confirm every
import the docker family makes from the kit is on it; build the family
against the lowest and the highest kit version in its declared range and
run its tests against each.

**Acceptance Scenarios**:

1. **Given** the kit's declared public surface, **When** the docker
   family's imports from the kit are listed, **Then** every one is on the
   surface.
2. **Given** a change to the kit that removes or alters something on the
   surface, **When** a release is attempted without the kit's version
   changing accordingly, **Then** the release is refused and says why.
3. **Given** the docker family's declared range of kit versions, **When**
   a change is made and the family is tested against the kit at the
   lowest and at the highest version of the range, **Then** it passes
   against both; a published end came from the index, and an
   unpublished end came from this repository's build and is reported
   as a development install.
4. **Given** a plugin that imports something from the kit that is not on
   the surface, **When** the plugin is checked, **Then** the check names
   the import and fails.

---

### User Story 4 - Another provider installed beside docker changes nothing (Priority: P4)

An operator runs a configuration that uses only docker. Someone installs
the AWS and Google Cloud providers in the same environment. The docker
configuration validates, generates and runs exactly as before. If one of
the other providers is broken, the docker configuration still works.

**Why this priority**: this is "does not interfere" at run time, the part
of the goal that isolation in tests does not cover.

**Independent Test**: generate the docker family's emission with only the
family installed, then with every provider installed; compare. Then
install a deliberately broken extra plugin and run a docker-only
configuration's commands.

**Acceptance Scenarios**:

1. **Given** a docker-only configuration, **When** its emission is
   generated with only the docker family installed and again with every
   provider installed, **Then** the two emissions are byte-identical.
2. **Given** an installed plugin that fails to load, **When** a command
   is run against a configuration that does not use that plugin, **Then**
   the command works and the failing plugin is named in one line.
3. **Given** two installed plugins that ship something under the same
   name (a Terraform module, a command, a setup section), **When** the
   system loads, **Then** it reports the collision naming both plugins;
   neither silently replaces the other.
4. **Given** a configuration that validated before an unrelated provider
   was installed, **When** it is validated afterwards, **Then** the
   result is the same, unless the new provider claims a word the
   configuration already uses, in which case validation names both
   plugins and the unambiguous form to write.

---

### User Story 5 - One guide for writing a provider (Priority: P5)

A plugin author who has never seen the repository reads one guide and
learns what a provider is made of, what it may import, how it declares
its dependencies, how it is tested alone, and where its Terraform modules
and its test fixture live. The docker family is the worked example.

**Why this priority**: the guide is the specification the first four
stories test; it comes last because it should describe what was proven.

**Independent Test**: a person who did not write the docker family
follows the guide and gets the family's isolated tests running from a
clean environment without asking a question.

**Acceptance Scenarios**:

1. **Given** the guide, **When** a reader looks for what a provider may
   import, how it pins the kit, and how it runs its tests alone, **Then**
   each is answered once, with the docker family as the example.
2. **Given** the current documents, **When** this feature is done,
   **Then** no document says a plugin is written "against the contract
   alone", and the statements this feature makes false are corrected.

---

### Edge Cases

- The kit and the docker family are changed together in one piece of
  work, so the family needs a kit version that is not published yet.
  The family must be testable against the unpublished kit, and that
  state must be visible as a development install, not mistaken for a
  release.
- The lowest kit version in the family's range lacks something the family
  now uses. The check against the lowest version must fail and name it.
- Two provider families ship a Terraform module with the same name.
- A live leg needs a container daemon and none is running. That leg is
  not part of the isolated test suite; where it is required it fails
  rather than skips.
- The docker family's packages are renamed or merged and the `[docker]`
  extra of `cs-image-system` still names the old ones, or names pins
  that cannot be installed together. The family's own tests still pass,
  because they install the family directly. The install check (FR-021)
  fails, on the change that caused it and before anything is published.
- The reference configuration and the `standard-docker` starter use the
  docker family today; their emission must not move.
- A second provider that declares itself a local stand-in is installed.
  A core check that needs one fails until the person running it names
  which to use (FR-008); it never picks by name or by order.
- The kit's surface changes in a way the shared Terraform libraries
  use. Their own isolated run fails and names what is missing, exactly
  as a provider's would; they get no private path into the kit.

## Requirements *(mandatory)*

### Functional Requirements

**The family alone**

- **FR-001**: The docker family MUST have its own tests, its own fixture
  configuration and its own golden emission, kept with the family.
- **FR-002**: The docker family's tests MUST run and pass in an
  environment that contains only the family and the dependencies it
  declares. They MUST NOT import another provider or any test helper
  kept outside the family, other than a published test kit that the
  family declares as a test dependency.
- **FR-003**: The same tests MUST pass when the family's directory is
  copied outside the workspace and its dependencies are installed from
  built packages.
- **FR-004**: CI MUST run the isolated docker job on every change, and
  that job MUST fail if the tests did not run.

**The core alone**

- **FR-005**: The core's tests MUST run and pass with nothing installed
  beyond the core: no docker, AWS or Google Cloud provider and no Okta
  identity plugin. A test that needs one of them belongs to that
  provider's suite, or to the every-provider suite until that provider
  has a suite of its own.
- **FR-006**: The core MUST have a fixture configuration and a golden
  that declare no provider-specific runtime and nothing that needs the
  Okta identity plugin.
- **FR-007**: A core check that depends on an installed provider MUST
  report "did not run" as a failure or as an exclusion the caller
  explicitly requested, never as a pass.
- **FR-008**: A provider MUST declare that it can serve as a local
  stand-in for the core's checks; nothing else makes it one. With
  exactly one such provider installed, a check MUST use it and say
  which it used. With two or more installed, the person running the
  check MUST name one, and the check MUST fail until they do. With none
  installed, FR-007 applies.

**The kit as the SDK**

- **FR-009**: The kit MUST declare its public surface in one place: what
  a plugin may import. Everything else is private.
- **FR-010**: The kit MUST carry its own version, separate from the
  workspace's release version, starting at 0.2.0 and staying below 1.0
  until the operator decides otherwise. The rule: removing or altering
  anything on the public surface raises the middle number; adding to
  the surface raises the last number.
- **FR-011**: A release MUST be refused when the kit's public surface
  changed and its version did not change according to that rule.
- **FR-012**: The docker family MUST declare the kit, and any other
  shared library it uses, by a range of versions, not an exact version.
  For the kit the range covers one middle number (for example at least
  0.2 and below 0.3).
- **FR-013**: The docker family MUST be tested against the kit at the
  lowest and the highest version of its declared range, on every
  change. An end that is published MUST be installed from the index. An
  end that is not published yet MUST be taken from this repository's
  build, and the run MUST report it as a development install.
- **FR-014**: A check MUST exist that any plugin can run against itself,
  inside or outside this repository, that fails when the plugin imports
  from the kit outside the public surface, imports the engine, or
  imports another provider.

**The shared Terraform libraries**

- **FR-026**: The two shared Terraform libraries
  (`cs-image-system-hashicorp-utils` and `cs-image-system-tofu-roots`)
  MUST be cleanly separable from the rest of this repository, so that a
  later specification can move them out of it. This feature does not
  move them. Separable means all of the following:
  - each declares its public surface as the kit does (FR-009), and a
    provider uses nothing of it that is not on that surface;
  - the two carry a version of their own, separate from the kit's and
    from the workspace's, under the same rule and the same release
    refusal as the kit (FR-010, FR-011);
  - they depend on the kit only through its public surface and by a
    range of versions, and on nothing else of this repository except
    the contract;
  - nothing in the contract, the kit, the engine or the command line
    imports them;
  - their own tests run and pass in an environment that holds only
    them and the dependencies they declare, on every change, and that
    run fails if the tests did not run.

**No interference**

- **FR-015**: The docker family's emission MUST be byte-identical whether
  the family is installed alone or beside every other provider.
- **FR-016**: A plugin that fails to load MUST NOT prevent any command on
  a configuration that does not use it; the failure MUST be reported in
  one line that names the plugin.
- **FR-017**: When two installed plugins ship something under one name
  (a Terraform module, a command, a setup section, a registered kind),
  the system MUST report the collision naming both. One MUST NOT
  silently replace the other.
- **FR-018**: A check that a run applies across every Terraform root
  (for example that provider versions agree) MUST NOT let one provider's
  declarations fail another provider's roots that do not share them.
- **FR-019**: The docker family MUST NOT reach into another package's
  private members, and everything provider-specific it needs at run time
  (including the Terraform modules its roots call) MUST ship with the
  family.
- **FR-020**: Installing, loading or testing the docker family MUST NOT
  change process-wide state that another plugin or another run in the
  same process can observe.

**Continuity**

- **FR-021**: On every change, CI MUST build the packages, install
  `cs-image-system[docker]` from them into a clean environment that
  holds nothing else, and there validate a docker-only configuration
  and complete a dry run of it. A failed install, a failed validation
  or a failed dry run MUST fail the job, and the job MUST fail if any
  of the three did not run.
- **FR-022**: The emission of the reference configuration and of the
  `standard-docker` starter MUST be byte-identical before and after this
  feature.
- **FR-023**: There MUST be one guide for writing a provider, with the
  docker family as its example, and the statements elsewhere that this
  feature makes false MUST be corrected in the same work.
- **FR-024**: The docker family MUST still be in this repository when
  this feature is done. Moving it to a repository of its own is a later
  specification, which this feature does not perform and does not
  forbid. This feature MAY increase the number of workspace packages.
- **FR-025**: The shared fixture and golden that exist today MUST stay
  whole and byte-identical. They become the every-provider suite: it
  runs with every provider installed, it is not part of the core's
  tests (FR-005), and the AWS, Google Cloud and Okta tests keep using
  it.

### Key Entities

- **Provider family**: the packages that together serve one provider
  (for docker: the runtime and its Terraform roots), with their tests,
  fixture, golden and Terraform modules.
- **The core**: exactly what a plain install of `cs-image-system` brings
  with no extras: the contract, the kit, the engine, the command line
  and the always-installed plugins. Everything installed as an extra
  (docker, AWS, Google Cloud, Okta) is outside it.
- **The kit (SDK)**: the package a plugin is written against; it has a
  public surface and a version of its own.
- **Public surface**: the declared list of what a plugin may import from
  the kit.
- **Shared Terraform libraries**: the two libraries that providers
  build their Terraform and Packer support on. They are part of a plain
  install, each has a public surface, and together they have a version
  of their own (FR-026).
- **Test kit**: the published helpers a provider's tests may use in place
  of the workspace's shared harness.
- **Core fixture and golden**: a configuration and its pinned emission
  that involve no provider-specific runtime.
- **Every-provider suite**: today's shared fixture and golden, kept
  whole, and the tests that need every provider installed. It is where
  "beside every other provider" (FR-015) is checked.
- **Isolated job**: the CI job that installs one family with only its
  declared dependencies and runs its tests.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a clean environment holding only the docker family and
  its declared dependencies, 100% of the family's tests run and pass,
  with zero skipped for a missing provider, on every change.
- **SC-002**: With no extra installed (no docker, AWS, Google Cloud or
  Okta), 100% of the core's tests run and pass.
- **SC-003**: The docker family's emission is byte-identical in three
  settings: alone, beside every other provider, and from a copy of its
  directory outside the workspace.
- **SC-004**: 100% of the docker family's imports from the kit are on
  the kit's declared public surface.
- **SC-005**: On every change, the docker family passes against the kit
  at both ends of its declared version range: from the index where that
  version is published, from this repository's build where it is not.
- **SC-006**: With a deliberately broken extra plugin installed, a
  docker-only configuration validates and completes a dry run.
- **SC-007**: The emission of the reference configuration and of the
  `standard-docker` starter is unchanged.
- **SC-008**: A person who did not write the docker family gets its
  isolated tests passing from a clean environment using the guide alone.
- **SC-009**: No repository check requires the docker family to be present for the
  core to pass.
- **SC-010**: On every change, `cs-image-system[docker]` installed from
  built packages into a clean environment validates a docker-only
  configuration and completes a dry run of it.
- **SC-011**: On every change, in a clean environment holding only the
  two shared Terraform libraries and their declared dependencies, 100%
  of their tests run and pass with zero skipped; and no module of the
  contract, the kit, the engine or the command line imports either
  library.

## Assumptions

- "The docker family" is the docker runtime plugin and the docker
  Terraform-roots plugin. Whether they stay two packages or become one is
  a planning decision.
- "The kit" is `cs-image-system-base`. The two shared Terraform libraries
  a provider also depends on are treated the same way (a declared
  surface, a version, a range) and are versioned separately from the
  kit (FR-026). Whether the two share one version between them is a
  planning decision. Moving them to a repository of their own is a
  later specification.
- The contract package stays as the types underneath the kit. Typing the
  domain data in the contract, and moving the contract to its own
  repository, are out of scope.
- Google Cloud and AWS follow by the same pattern as later
  specifications. This one changes them only where a shared channel
  (FR-015 to FR-020) has to change for docker's sake. Their tests stay
  in the every-provider suite (FR-025), so docker's emission is pinned
  twice, in the family's golden and in the shared one, until those
  specifications land.
- The published test kit and the split of the shared test harness are
  part of this feature, because Story 1 cannot pass without them.
- Moving the family to its own repository, and releasing the family on
  its own, are a later specification (FR-024). Every acceptance in this
  one is judged with the family in this repository.
- Development work on the kit and the family together uses an
  unpublished kit and is visibly a development install.
- Every plan made from this specification states its budget
  (Constitution VII). This feature is expected to remove more
  repository-wide checks than it adds.
