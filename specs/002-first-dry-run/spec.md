# Feature Specification: Fifteen minutes to a first dry run

**Feature Directory**: `specs/002-first-dry-run`

**Feature Branch**: `feature/002-first-dry-run` (created 2026-11-25)

**Created**: 2026-11-16

**Status**: Planned 2026-11-21, the plan revised 2026-11-25 for releases on TestPyPI until 1.0 ([plan](plan.md))

**Input**: User description: "A newcomer with nothing installed reaches a successful dry run by following one page, and CI runs that page's commands."

## Clarifications

### Session 2026-11-21

- Q: In what order do specs 002, 003, 006, 007 and 008 land? → A: 008 first, then 003, then 007; 006 and 002 fit between, and 002, 003 and 006 are carried by one batched release
- Q: A dry run of the docker starter needs uv, Docker, OpenTofu, Packer and bash 5; the limit was four. → A: Raise the limit to five (FR-002, SC-004 amended)
- Q: Who walks the page for SC-002? → A: A member of an adopting team, on their own macOS machine, after the next final release that carries the page; recorded under the tasks
- Q: What happens to the older public repository `cs-image-system-starter-tree`? → A: Its README is replaced by three lines pointing at the quickstart page and the five template repositories, then it is archived

### Session 2026-11-25

- Q: Until 1.0 every release is on TestPyPI alone, and a plain or unpinned install still gets PyPI's older 0.1.12. How should the page's first install command get the current release? → A: The one install form with the exact version (TestPyPI as the index, PyPI as the extra, `--index-strategy unsafe-first-match`, `cs-image-system[docker]==<version>`), the version written in the page and moved by each release's bump (FR-004)
- Q: Releases are published by the tag's push, so the release gate on the operator's machine no longer controls the upload. Where does the page run against a release's packages before they are published? → A: Both: in the release's own gate (`just test-quickstart` against the built packages, in the lighter check and so under `--full`, before the tag), and in the Publish workflow, on a clean stock runner against the built files, with the upload waiting on it (about 3 to 5 minutes; the gate about 1). CI's quickstart job still runs on every push (FR-011, SC-008)
- Q: The install needs both test.pypi.org and pypi.org; what does the page promise a reader whose machine reaches packages only through a company proxy or mirror? → A: Out of scope: the page assumes direct internet access and says nothing about proxies or mirrors. The operator: TestPyPI is forced only for the current development cycles, no one but the operator uses the project yet, and the TestPyPI-only rule will not stay once the project is stable (Edge Cases)
- Q: SC-002 needs someone who has never used the system, and nobody but the operator uses the project yet; who walks the page, and when? → A: Keep SC-002 as written; the specification stays incomplete until it is walked. The walker may in the end be the operator on a clean account, but not now. This replaces the 2026-11-21 answer's timing ("after the next final release") (SC-002)

**Users served**: an adopting team (primary); operators who are new to the system.

## Why

Nobody can enter the system today. There is no document that tells a
competent stranger what this is, how to install it and how to run it. The
page listed first under "Where to start" is 1,600 lines long and a reader
gets through 670 of them before the first command of a first run. Followed
literally it breaks in several places: its first install command needs a
file that only a later command creates; the plain install carries no
provider; a fresh configuration needs a step that is mentioned somewhere
else; and the starter documents still state requirements that are no
longer true.

An adopting team should be able to see the system work on their own
machine, with no cloud account, before they invest in anything.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - From nothing to a dry run on one page (Priority: P1)

A member of a team considering the system has a laptop with a small,
stated set of common tools. They open one page, run its commands in order
without editing anything, and within fifteen minutes see a successful dry
run of a small example configuration on their own machine. They need no
cloud account, no identity provider and no secret of their own.

**Why this priority**: this is the whole feature. Everything else exists
to keep this true.

**Independent Test**: on a clean machine that has only the stated
prerequisites, run the page's commands exactly as written. The last one
reports a successful dry run.

**Acceptance Scenarios**:

1. **Given** a machine with only the prerequisites the page states,
   **When** the page's commands are run in order exactly as written,
   **Then** each succeeds and the last reports a successful dry run.
2. **Given** the same machine, **When** the page is followed from start
   to finish, **Then** no cloud account, login, identity provider or
   self-made key is needed at any point.
3. **Given** the first install command on the page, **When** it is run
   before any configuration repository exists, **Then** it works.
4. **Given** a completed dry run, **When** the reader looks at the page,
   **Then** it tells them in a few sentences what was produced, where it
   is, and that nothing was applied.
5. **Given** the page has been followed once, **When** its commands are
   run again, **Then** they succeed again.

---

### User Story 2 - The page cannot go stale unnoticed (Priority: P2)

A maintainer changes the system in a way that would break a newcomer's
first run. CI runs the page's own commands on a clean machine and fails,
so the maintainer finds out before a newcomer does.

**Why this priority**: every first-run instruction in the repository went
stale because nothing ran it. A page that is executed is a page that
stays true.

**Independent Test**: change one command on the page to something that
fails; CI fails on that change. Restore it; CI passes.

**Acceptance Scenarios**:

1. **Given** the page, **When** CI runs, **Then** the commands CI executes
   are taken from the page itself, not from a second copy.
2. **Given** a change that breaks any command on the page, **When** CI
   runs on that change, **Then** it fails and names the command.
3. **Given** a release of the system, **When** it is published, **Then**
   the page's commands have been run against that release's packages,
   in its gate before the tag and on a clean machine before the upload.
4. **Given** the CI job that runs the page, **When** it cannot run (a
   missing tool on the runner, for example), **Then** it reports a
   failure, not a pass.

---

### User Story 3 - A first-run failure says what to do (Priority: P3)

A newcomer is missing one of the prerequisites, or has an older version
of a tool, or has an older release of the system installed. The command
that fails says in one line what is missing and what to do about it.

**Why this priority**: the common first-run failures are few and known. A
newcomer who hits one with no explanation stops.

**Independent Test**: for each of the listed first-run failures, create
the condition on a clean machine and run the page; the failing command's
message names the cause and the remedy in one line.

**Acceptance Scenarios**:

1. **Given** a prerequisite tool is absent, **When** the step that needs
   it runs, **Then** the message names the tool and how to get it.
2. **Given** a prerequisite tool is older than required, **When** the
   step that needs it runs, **Then** the message names the tool, the
   version found and the version needed.
3. **Given** the system is installed without the provider the example
   uses, **When** the example is validated, **Then** the message names
   the provider and the exact install command.
4. **Given** an older release of the system is already installed,
   **When** the page's install command is run, **Then** the newcomer ends
   with the current release, or is told in one line how to.

---

### User Story 4 - What to do next is signposted (Priority: P4)

A newcomer who has seen a dry run wants to do something real: make a
first actual run locally, move to a cloud, or start their own
configuration repository. The page ends with those three routes, one
link each. The front page of the repository leads a reader to this page
second, after a short description of what the system is.

**Why this priority**: the page is an entrance; it has to open onto the
rest.

**Independent Test**: from the repository's front page, a reader reaches
the description and then this page in two steps; from this page, each of
the three next routes is one link away and that link's first command
works.

**Acceptance Scenarios**:

1. **Given** the repository's front page, **When** a new reader follows
   "where to start", **Then** the first stop says what the system is and
   the second is this page.
2. **Given** the end of the page, **When** the reader wants a first real
   local run, a cloud starter, or their own repository, **Then** each has
   one link and the page linked to begins with a command that works.
3. **Given** the other documents, **When** this feature is done, **Then**
   none of them repeats these steps; they link to the page.

---

### Edge Cases

- The reader's machine is offline after the install step. The page states
  which steps need the network.
- No container daemon is running. If a dry run does not need one, the
  page must work without it; if it does, the daemon is a stated
  prerequisite and its absence produces a one-line message.
- The reader is behind a proxy or a mirror for packages: out of scope.
  The page assumes direct internet access and says nothing about
  either; the TestPyPI-only install is for the development cycles
  before 1.0 alone. *(Clarified 2026-11-25.)*
- The reader runs the page in a directory that already contains a
  configuration.
- The reader is on an operating system the page does not cover; the page
  says which it covers.
- The example configuration carries placeholder values meant to be
  replaced by a real team. They must not stop a first dry run.
- The example carries encrypted values that need a key to open. A
  first dry run must work with what the example ships.
- A step takes much longer than usual on a slow connection; the page says
  which step that is likely to be.

## Requirements *(mandatory)*

### Functional Requirements

**The page**

- **FR-001**: There MUST be one page that takes a reader from the stated
  prerequisites to a successful dry run of a small example configuration
  on their own machine.
- **FR-002**: The page MUST state its prerequisites at the top, by name
  and minimum version, and they MUST be five or fewer. *(Amended
  2026-11-21: four became five, the operator's decision.)*
- **FR-003**: Every command on the page MUST be runnable exactly as
  written, in order, with no value for the reader to fill in.
- **FR-004**: The first install command MUST work before any
  configuration repository exists, and MUST install everything the
  example needs, at the current release: until 1.0 by the one install
  form (every name of the system from TestPyPI, every other from PyPI)
  with the exact version written in the page, which each release's
  bump moves, so the reader types nothing. *(Clarified 2026-11-25.)*
- **FR-005**: The path MUST NOT require a cloud account, a login, an
  identity provider, or a key or secret the reader creates.
- **FR-006**: The example configuration MUST validate and dry-run as it
  is written out, including any placeholder or encrypted value it
  carries.
- **FR-007**: The page MUST say, after the dry run, what was produced,
  where it is, and that nothing was applied.
- **FR-008**: The page MUST have ten or fewer commands and MUST end with
  one link each to: a first real local run, the cloud starters, and
  starting a team's own configuration repository.
- **FR-009**: The page MUST state which operating systems it covers and
  which steps need the network.

**Kept true by CI**

- **FR-010**: CI MUST execute the page's commands, taken from the page
  itself, on a clean machine that has only the stated prerequisites.
- **FR-011**: That job MUST run on every change, and MUST fail when any
  command fails or when it could not run. Every release's packages MUST
  have run the page twice over before they are published: in the
  release's own gate on the operator's machine, before the tag (the
  lighter check and so the full proof), and in the publishing workflow,
  on a clean machine that has only the stated prerequisites, with the
  upload waiting on it. *(Clarified 2026-11-25.)*
- **FR-012**: The job MUST record how long the path took.

**First-run failures**

- **FR-013**: For each of these conditions the failing command MUST say,
  in one line, the cause and the remedy: a prerequisite absent; a
  prerequisite older than required; the system installed without the
  provider the example uses; an older release of the system already
  installed; the command run where a configuration already exists.

**The way in**

- **FR-014**: The repository's front page MUST lead a new reader first to
  a short description of what the system is and second to this page.
- **FR-015**: The steps MUST be written in this page only; other
  documents and the starters MUST link to it instead of repeating them.
- **FR-016**: The statements in the starters and the manuals that are
  false today or become false with this feature (the install command
  that installs no provider, the claim that loading needs a live cloud
  session, the name shown for the image builder's type) MUST be
  corrected in the same work.

### Key Entities

- **The quickstart page**: the single page of prerequisites, commands and
  next steps.
- **The example configuration**: the small configuration the page writes
  out and dry-runs; it needs no account.
- **Prerequisites**: the named tools, with minimum versions, a reader
  must have before the first command.
- **The quickstart job**: the CI job that runs the page's commands on a
  clean machine and records the time taken.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a clean machine with only the stated prerequisites, the
  page's commands reach a successful dry run in 15 minutes or less.
- **SC-002**: A person who has never used the system completes the page
  unaided in 15 minutes or less, on the first attempt (done once, by
  someone outside the project, and recorded). Until it is, the
  specification is not complete; the walker may in the end be the
  operator on a clean account, but no date is set. *(Clarified
  2026-11-25.)*
- **SC-003**: The path needs zero cloud accounts, zero logins and zero
  values typed in by the reader.
- **SC-004**: The page has at most ten commands and at most five
  prerequisites. *(Amended 2026-11-21.)*
- **SC-005**: A deliberately broken command on the page makes CI fail;
  restoring it makes CI pass.
- **SC-006**: Each of the five listed first-run failures produces a
  one-line message naming cause and remedy.
- **SC-007**: From the repository's front page a new reader reaches the
  quickstart in two steps, and no other document repeats its commands.
- **SC-008**: Every release published after this feature has had the
  page run against its packages first, both in its gate before the tag
  and on a clean machine before its upload.

## Assumptions

- The example is the docker starter, because it is the only one that
  needs no cloud account. If a dry run of it needs a running container
  daemon, the daemon counts as one of the five prerequisites.
- The page covers macOS and Linux. Windows is out of scope.
- The starter ships a test key for its encrypted example values; using
  it for a first dry run is acceptable because nothing real is protected
  by it. The page says so.
- Placeholder values in the starter either have defaults that work for a
  local trial or are filled by the command that writes the example out.
  Which, is a planning decision; the reader types nothing (FR-003).
- A first real run, the cloud starters and the upgrade procedure are
  separate pages this one links to. Reorganising the two long manuals is
  out of scope except for the corrections in FR-016 and removing the
  duplicated steps.
- The 15 minutes assume an ordinary broadband connection and exclude
  installing the prerequisites themselves.
- "Clean machine" in CI means a stock image with only the prerequisites,
  not the project's own runner image with every tool preinstalled.
