# Feature Specification: Every machine and every id recorded once, by an identity the system ships

**Feature Directory**: `specs/010-posix-server-registry`

**Feature Branch**: `feature/010-posix-server-registry` (to be created from `develop` when planning starts)

**Created**: 2026-11-22

**Status**: Merged, 2026-11-23: phases 1 to 11 merged into `develop` (`6bd23ee7`, squash), the feature branch kept; T003 (a read-only look at an enrolled machine), T046 (the release) and T047 (the reference configuration's applying run and record) are the operator's. Records are in [tasks.md](tasks.md).

**Input**: User description: "The POSIX identity plugin keeps a registry of the servers launched for its groups. A group builder's server registry (the contract's can_query_servers, registered_servers, retire_servers_named, and alias_registration_script) is what the core uses to refuse a launch whose canonical hostname is already claimed (validate_claimed_hostnames, which refuses on silence), to retire a decommissioned instance's registration (_retire_registration), to give a launched machine its provider alias (the alias pass in provider_aliases), and to report which generation a registered machine is (registered_as, booted_as). Today only the Okta group builder keeps one (its registry is OPA's enrolled servers, read through the network), and the POSIX identity plugin, the identity a group gets without an external provider, answers can_query_servers False, so a POSIX-owned instance gets none of these guarantees: two launches can take one canonical name, and a decommission leaves nothing retired because nothing was recorded. Spec 008 moves the Okta plugin out of this repository, and about 30 core tests (hostname claims, provider aliases, the alias pool, canonical names, generations, one capability test) prove those core behaviours only through the Okta builder's registry; by the operator's decision of 2026-11-22 (\"Give POSIX a registry\") the POSIX plugin gains a real server registry that carries them, rather than a test-only double. The registry must keep the contract's meaning (None when it cannot be asked, never an empty list; a retirement that did not happen raises), must record each launched machine's id, hostname and address per group, must be readable and retirable by the core exactly as Okta's is, and must make no network call in a dry run. Spec 008's task T035 (re-hosting the core-through-Okta tests) waits for it. Serves operators (whose POSIX-owned instances gain the one-name-one-machine guarantee and clean decommissions), an adopting team (whose first tree uses the POSIX identity and should get the same guarantees as an Okta tree), and a plugin author (who sees in a shipped plugin how a server registry is written against the published kit)."

**Users served**: operators (whose machines owned by a POSIX group gain
the guarantee that one name means one machine, whose users and groups
each keep one id for good, and whose decommissions leave nothing behind);
an adopting team (whose first tree uses the POSIX identity, which needs
no outside service, and should get what an Okta tree gets); a plugin
author (who reads, in a plugin the system ships, how a registry is
written against the published kit, and whose own identity plugin's ids
are kept apart from every other's).

## Why

When an image belongs to a group, the group's identity decides who can
log in to the machines launched from it. The system offers two
identities: Okta's, through an outside service, and POSIX's, as plain
accounts on the machine, which needs nothing outside. They are not
exclusive: an Okta group's accounts are made on the machine as POSIX
accounts (Okta names the POSIX identity as its delegate), so both
identities' users and groups can live on one machine.

Two kinds of record decide whether that machine works.

**The server registry.** The identity's list of which machines are
enrolled for a group, under which name. The system uses it to:

- refuse a launch whose canonical hostname another machine already holds,
  and refuse when the list cannot be read, since an unreadable list is not
  a free name;
- retire a machine's entry when the machine is decommissioned, so no stale
  entry answers to its name;
- give a launched machine its provider alias (the cloud provider's own
  host name, kept as a second name) unless another machine claims it;
- report, in the state query, which name each machine is registered
  under, beside the name its generation booted with.

Only the Okta identity keeps one today. A machine owned by a POSIX group
gets none of these guarantees: two launches can take one name, and a
decommission retires nothing, because nothing was ever recorded.

**The ids.** Every user and group has a numeric id on the machine, and
shared storage is owned by number, so every machine must agree on each
one. The system already refuses one name with two ids and two names with
one id, but only among what the configuration and the POSIX identity
declare: the ids Okta holds are not part of the check, an id no one
declares is refused rather than given, and nothing records an id once it
is in use, so nothing stops it from changing later. Okta's ids are the
less flexible: a group's id can be set only when the group is created,
and a user's is Okta's own. A POSIX id that lands on one of them makes
two accounts one on the machine, and cannot be fixed by moving Okta's.

The cost is about to be paid twice. Specification 008 moves the Okta
plugin out of this repository, and about 30 of the core's tests prove the
registry's guarantees only through Okta's. By the operator's decision of
2026-11-22, the POSIX identity gains a real registry, and those tests are
carried by it, rather than by a stand-in that exists only for tests. The
operator added, the same day, that the ids belong to the same record: every
user and group has a recorded id, no two identity plugins' ids collide,
and a recorded id never drifts.

## Clarifications

### Session 2026-11-22

- Q: About 30 core tests prove hostname claims, provider aliases, the
  alias pool, canonical names and generations only through the Okta group
  builder's server registry; what carries them once the plugin leaves
  (specification 008)? → A: The POSIX identity plugin gains a server
  registry and carries them; this specification is that registry
- Q: Where is the registry kept? → A: With the configuration's own
  records: saved by the system's record step and committed with the tree,
  read offline; "could not be asked" means the record could not be read
- Q: Does a POSIX machine answer to its provider alias? → A: The alias is
  recorded in the registry only (the collision rules and the state query
  hold); nothing is written on the machine, and a login by alias is the
  operator's own name resolution
- Q (the operator's direction, not a question asked): what else is the
  registry's? → A: Okta's and POSIX's records must coexist on one machine.
  The registry is a plugin's, and that plugin is internal to the system.
  Every user and group has a recorded id; ids never collide across any
  plugins that manage user and group ids (POSIX, Okta, any later one); a
  declared id that conflicts fails validation with a message saying why;
  an undeclared id comes from a known pool and, once concrete, never
  drifts
- Q: Which identities does the pool serve? → A: Every identity that can
  be given an id: each identity plugin has its own pool (the Okta service
  notes which ids are in its pool, and the POSIX identity gains
  configuration for its own), and the system gives an undeclared name an
  id from its identity's pool, a new Okta group's at its creation
- Q: What happens when an id a provider assigned itself lands on an id
  already recorded for another name? → A: The run is refused, naming both,
  until the operator retires one of the names; and every identity's pool
  is kept apart from every other's, with declared ids checked against
  them, so it can arise only from an id declared by hand
- Q (the operator's direction): what is the POSIX identity's place among
  the identities? → A: It is the final fallback, and the only identity
  that defers: a POSIX user or group whose name an external identity
  provider already holds (Okta's user `abc` with id 15001) takes that
  provider's id (15001), and a different declared id is refused. Between
  external identity providers there is no deferring: a collision is a
  configuration error. An id held anywhere in the system is never given
  to another name; it may only return to the name it was first held by
- Q (the specification's validation, 2026-11-22): six requirements could
  not all hold, and four statements were loose; how are they settled? → A:
  As recommended: (1) the pool checks bind ids not yet recorded; a recorded
  id stays and is reported, and no pool may move over another identity's
  recorded id; (2) validation and dry runs read only the records: an
  applying run or the record step reads Okta's pool and ids and records
  them, and an Okta name whose id is not yet recorded is an id to come,
  checked when read; (3) a deferring user's private group takes the
  user's id when that group id is free, and validation fails naming the
  holder when not; (4) a POSIX name recorded first that an external
  identity later takes with another id fails validation, naming both, and
  nothing moves; (5) a group moved between identities keeps its recorded
  id under (1), and a move to Okta creates the group there with that id;
  (6) the core gains one step: for an identity whose registry is kept in
  the records, the alias pass writes the aliases into the entry instead
  of running a script on the machine; (8) settled separately, below;
  (9) a deferring POSIX name and its external namesake are one record,
  held by the external identity, POSIX noted as deferring; (10) both
  identities' registries live side by side in one tree
- Q (item 7): can a new Okta group be created with an id the system
  chose? → A: Planning researches it (the Okta service's Terraform
  provider exposes no id on a group; the system reads it afterwards). If
  it cannot, Okta assigns the id, which is an id to come until an applying
  run or the record step reads and records it
- Q (item 7): who chooses an Okta user's id? → A: Okta; the system records
  it when first read and never chooses one, and a POSIX user of that name
  takes it (FR-004a)
- Q (item 7): where does the system learn Okta's pool? → A: From the
  service, read by an applying run or the record step and recorded;
  validation reads the record; if the service does not give the bounds,
  the Okta group builder's configuration declares them
- Q (item 8): what is the "same name" the POSIX fallback matches on? → A:
  The same configured name, never a generated one. The operator added
  that the system may be too lenient in how it accepts Okta's names, which
  needs guided research and may need stories here or a specification of
  its own: an Okta group's accounts appear on the machine under a name
  Okta templates (`sft_<group>_user`), generally only once someone logs in,
  because of the way PAM works; Okta's user accounts persist on the
  machine when the system forces them to, which the Okta plugin should do
  by default; and the groups PAM makes are fluid on the machine. The plan's
  research R-names (Assumptions) settles where the stories land
- Q (the operator's note): is Okta's part still read-only? → A: Yes, for
  now: the system only looks Okta's users up and never writes them. It
  should change soon; a specification to extend the Okta plugin past
  read-only is to be written once the plugin is in its own repository
  (`REMINDERS.md`), and this specification assumes read-only

### Session 2026-11-22 (planning)

- Q (D1): which runs record ids? → A: applying runs and dry runs with
  `--commit` (the record step, the operator's deliberate record); a plain
  dry run shows the ids it would give and records nothing
- Q (D2): how does a new Okta group get its id? → A: Okta assigns it and
  the system records it when first read (OPA takes no gid at a group's
  creation, and setting one afterwards would be a write to OPA); story 2,
  scenario 6 takes its fallback
- Q (D3): where do the naming rules and the Okta plugin's claims land? →
  A: a live, read-only look at one enrolled machine first (the operator's
  box); then the naming rules and the Okta plugin's claims and pool are
  the Okta repository's specification 002, written once this
  specification's contract is released. This specification ends with the
  POSIX side done and the contract able to carry the rest
- Q (D4): the POSIX pool's default? → A: 3000 to 59999
- Q (D5): which release? → A: the batched release for specifications 002,
  003 and 006 if this merges before it is cut, else the next

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A declared id that collides is refused at validation (Priority: P1)

An operator declares a user or a group with an id. If any other user or
group, in any identity plugin, already holds or claims that id (or the
same name is known with another id), validation fails before anything is
emitted, naming the id, both names and the identity each belongs to.

**Why this priority**: two accounts on one id are one account on the
machine, and storage owned by that number is then both of theirs. It is
the failure that cannot be undone after a bake.

**Independent Test**: a tree declaring a POSIX group whose id an Okta
group holds (recorded, or declared) fails validation naming both; a tree
declaring a POSIX user with a recorded user's id fails the same way; a
tree with no collision passes.

**Acceptance Scenarios**:

1. **Given** a POSIX group declared with an id an Okta group of another
   name holds, **When** the tree is validated, **Then** validation fails,
   naming the id, both groups and both identities, and saying the Okta id
   cannot move.
2. **Given** a POSIX user declared with an id another user holds in any
   identity, **When** the tree is validated, **Then** validation fails
   naming both.
3. **Given** a name already recorded with one id, **When** the tree
   declares it with another, **Then** validation fails, naming the
   recorded id and the declared one, and saying a recorded id does not
   change.
4. **Given** a user's private group (same name, same id as the user),
   **When** another group declares that id, **Then** validation fails
   naming the user whose private group it is.
5. **Given** a tree with no collision, **When** it is validated, **Then**
   it passes, and every user and group has exactly one id.
6. **Given** an Okta user `abc` holding id 15001, **When** the tree
   declares a POSIX user `abc` with no id, **Then** the POSIX user takes
   15001, the same account on the machine, and nothing is drawn from the
   POSIX pool.
7. **Given** the same Okta user, **When** the tree declares the POSIX user
   `abc` with id 15002, **Then** validation fails, saying the POSIX
   identity defers to the external one and the id must be 15001.
8. **Given** a POSIX user `abc` recorded with 20003, **When** Okta later
   holds a user `abc` with 15001, **Then** validation fails, naming both
   ids and saying one of the names must change; neither id moves.
9. **Given** two external identity providers (Okta and a later one) that
   each hold a name, **When** their ids collide (one name with two ids, or
   one id with two names), **Then** validation fails as a configuration
   error, naming both providers; neither defers.

---

### User Story 2 - An undeclared id comes from the pool and never drifts (Priority: P1)

An operator declares a user or a group without an id. Unless an external
identity already holds the name (story 1's fallback), the system gives it
an id from its identity's own pool, never one held or claimed by any
identity, and records it. Every later run uses the recorded id, whatever else the tree
or the pool does.

**Why this priority**: it is what lets a tree leave ids out without
inviting a collision, and what makes an id, once in use, safe to own
storage by.

**Independent Test**: a tree with an undeclared group is validated and
recorded; the group has a pooled id, outside every other identity's ids.
Add groups, reorder the files, change the pool's bounds: the first
group's id is unchanged, and if it now lies outside its pool, the run says
so and keeps it. Exhaust the pool: validation fails naming it.

**Acceptance Scenarios**:

1. **Given** a group or user with no declared id, **When** the tree's
   ids are made concrete, **Then** it is given the lowest free id in its
   identity's pool that no identity holds, claims or once held, and the
   id is recorded.
2. **Given** a recorded pooled id, **When** later runs add, remove or
   reorder other users and groups, **Then** its id is unchanged.
3. **Given** a recorded pooled id, **When** the tree later declares the
   same id for that name, **Then** validation passes; **When** it declares
   another, **Then** validation fails as in story 1.
4. **Given** a pool with no free id left, **When** an undeclared name is
   validated, **Then** validation fails, naming the pool and its bounds.
5. **Given** a dry run, **When** it validates a tree with undeclared ids,
   **Then** it shows the ids they would be given and records nothing.
6. **Given** a new Okta group with no declared id, **When** it is
   created, **Then** it is created with an id from Okta's pool that the
   system chose and recorded, if the Okta service accepts an id at
   creation (the plan's research); if it does not, Okta assigns the id,
   which is an id to come until an applying run or the record step reads
   and records it.
7. **Given** a tree whose POSIX pool overlaps Okta's pool (or any other
   identity's), **When** it is validated, **Then** validation fails,
   naming both pools and the ids they share.
8. **Given** a recorded id that a pool change leaves outside its
   identity's pool, **When** the tree is validated, **Then** the id is
   kept and reported, not refused; **Given** a pool moved over an id
   another identity has recorded, **Then** validation fails, naming the
   id and its holder.

---

### User Story 3 - Okta and POSIX coexist on one machine (Priority: P1)

A machine carries accounts from both identities: an Okta group's
accounts, made on the machine through the POSIX identity, beside POSIX
groups and users of its own. Every id on it is one recorded id, and none
is held twice.

**Why this priority**: it is the configuration the reference runs today;
the guarantees of stories 1 and 2 mean nothing if they stop at one
identity's edge.

**Independent Test**: a tree with an Okta group and POSIX groups owning
images baked for one machine validates with every id distinct across
both, and its bake's accounts script makes each account under its
recorded id.

**Acceptance Scenarios**:

1. **Given** an Okta group that existed before this change, whose id the
   Okta service assigned, **When** the id is first read by an applying run
   or the record step, **Then** it is recorded, and from then on no
   declared or pooled id may take it; until then it is an id to come.
2. **Given** a recorded Okta id, **When** the service later reports
   another id for that group, **Then** the run is refused, naming both,
   and the recorded id is not overwritten.
3. **Given** an Okta-assigned id that lands on an id already recorded for
   another name, **When** it is read, **Then** the run is refused, naming
   both, until the operator retires one of the names. Since every pool is
   apart from every other, no pool moves over a recorded id, and a
   declared id not yet recorded is refused inside another's pool, this can
   arise only from an id recorded before this change.
4. **Given** a third identity plugin installed later, **When** it claims
   ids, **Then** its claims join the same check, with nothing in the core
   changed.

---

### User Story 4 - One name, one machine, for a POSIX group (Priority: P2)

An operator launches an instance whose image belongs to a POSIX group.
The machine is registered for the group under its canonical hostname. A
later launch of a different machine under that name is refused before
anything is created, naming the machine that holds it.

**Why this priority**: two machines answering to one name make a login by
name unusable; it follows the ids because the ids are what the machine
is made with.

**Independent Test**: with a POSIX group whose registry holds a machine
under a name, a launching run of an unlaunched instance with that
canonical hostname is refused, naming the holder; with the registry
unreadable, the run is refused as unable to check, never let through.

**Acceptance Scenarios**:

1. **Given** a POSIX-owned instance launched by a run, **When** the run
   finishes, **Then** the group's registry lists the machine with its
   provider id, canonical hostname and address, and the record step saves
   it with the tree.
2. **Given** that registry, **When** a launching run declares another
   unlaunched instance with the same canonical hostname, **Then** the run
   is refused before any machine is created, naming the registered machine.
3. **Given** a launched instance with two registry entries under its
   name, **When** a launching run starts, **Then** it is refused, naming
   both entries.
4. **Given** a registry record that cannot be read, **When** a launching
   run starts, **Then** it is refused as unable to check the claim, and no
   machine is created.
5. **Given** any of these trees, **When** a dry run is made, **Then** it
   reads the registry from the tree's records only, makes no network call
   for it and changes nothing in it.

---

### User Story 5 - A decommission leaves nothing behind (Priority: P2)

An operator decommissions a POSIX-owned instance. Its registry entries are
retired with it, so its name is free for a new machine; a retirement that
could not be done is said, not reported as done. The ids of its users and
groups stay recorded.

**Why this priority**: without it, story 4's guarantee turns against the
operator: a dead machine's entry would block every new machine of that
name.

**Independent Test**: decommission an instance whose name has one entry;
the entry is gone, the ids are unchanged, and a new launch of that name
passes the claim check. Make the retirement fail; the run says loudly
that it was not retired.

**Acceptance Scenarios**:

1. **Given** a registered POSIX-owned instance, **When** it is
   decommissioned, **Then** every registry entry under its canonical
   hostname for that group is retired, and the run says how many.
2. **Given** a retirement that cannot be done, **When** the instance is
   decommissioned, **Then** the run says the entry was NOT retired and how
   to remove it by hand, and the decommission itself is not undone.
3. **Given** an instance replaced by a new generation, **When** the new
   machine launches, **Then** the registry holds exactly one entry under
   the name, the new machine's.
4. **Given** a decommissioned machine, **When** its group's and users'
   ids are next checked, **Then** they are unchanged and still held.

---

### User Story 6 - A POSIX-owned machine's alias and generation are visible (Priority: P3)

A launched POSIX-owned machine is given its provider alias by the same
rules as an Okta-owned one (a name another machine or the configuration
claims is skipped, and said), recorded in its registry entry; the state
query reports the name it is registered under beside the name its
generation booted with.

**Why this priority**: it completes the parity with Okta's registry; the
core's rules exist already and only lack a registry to read.

**Independent Test**: a running POSIX-owned machine whose provider
hostname is free gains it as an alias in its entry; one whose provider
hostname another entry claims has it skipped, with the claimant named.
The state query lists each machine's registered and booted names.

**Acceptance Scenarios**:

1. **Given** a running, registered POSIX-owned machine, **When** an
   applying run reaches the alias pass, **Then** the free aliases are
   recorded against its entry and nothing is written on the machine.
2. **Given** an alias another entry or the configuration claims, **When**
   the alias pass runs, **Then** that alias is skipped and the claimant is
   named.
3. **Given** a registered machine, **When** the state query runs, **Then**
   it reports the machine's registered name and its booted name, and a
   note when they differ.

---

### User Story 7 - The core's proofs no longer need Okta (Priority: P3)

A plugin author or maintainer runs the core's tests with the Okta plugin
absent, and the guarantees above (ids, hostname claims, provider aliases,
the alias pool, canonical names and retirement, generations) are still
each proven, through the POSIX identity.

**Why this priority**: it is what specification 008's T035 waits for; it
follows once the stories above hold.

**Independent Test**: the core's tests of those guarantees pass in this
repository with the Okta plugin not installed, none of them skipped.

**Acceptance Scenarios**:

1. **Given** this repository without the Okta plugin, **When** the
   acceptance tests run, **Then** every case specification 008 classified
   as needing a registry passes on the POSIX identity, none skipped.

---

### Edge Cases

- A tree in use before this change has ids in use but none recorded. The
  first record after the change records every id as it stands (declared,
  or read from the identity that holds it), changing none, and says so; a
  collision already present is refused then, naming both, rather than
  recorded.
- A user or group removed from the tree keeps its recorded id: the id is
  never given to another name, since storage may still be owned by it.
  The only reuse is a restore: the name it was first held by, declared
  again, takes it back.
- A POSIX name an external identity also holds is the same account on the
  machine, under the external identity's id; it is not a collision and
  draws nothing from the POSIX pool.
- An id below the system's floor (the system's own accounts) is refused
  whether declared or pooled; the pool lies above it.
- A user's private group shares the user's id and name; it is checked
  once, on the user. A POSIX user that defers to an external identity's
  id (FR-004a) brings its private group to that id too, when that group id
  is free; when another group holds it, validation fails, naming that
  group, since neither id may move.
- Two trees (two configurations) record their ids apart; a collision
  between trees is outside the system's knowledge, as today.
- A machine launched before this change has no registry entry. The first
  applying run that finds it launched registers it, from its launch
  record and the runtime's own report of the machine, and says so.
- A runtime that cannot report a machine's provider id (a local container
  runtime) still registers the machine, under an id the runtime does give,
  so a retirement can find it.
- Two groups may register one hostname each; a hostname claim is per
  group, as Okta's is. An id claim is not: it is across every group and
  identity of a kind.
- A registry entry whose machine no longer exists at the provider stays
  until it is retired; the state query notes it as stale and names the
  command that retires it.
- A group moved from POSIX to Okta, or back, keeps its recorded id (a
  recorded id is never refused for the pool it lies in, FR-006); a group
  moved to Okta is created there as a new group with that id, and if the
  identity cannot take it, the move is refused.
- A failed launch (the machine never came up) leaves no registry entry;
  the ids it would have used stay recorded.

## Requirements *(mandatory)*

### Functional Requirements

#### Ids

- **FR-001**: Every user and group in a tree MUST have exactly one
  recorded id, kept with the configuration's own records.
- **FR-002**: No id MAY be held by two names of one kind (two users or
  two groups) across every identity plugin that manages user and group
  ids: POSIX, Okta, and any plugin installed later.
- **FR-003**: A declared id that conflicts with another name's recorded,
  declared or provider-held id, or with the name's own recorded id, MUST
  fail validation with a message naming the id, both names, the identity
  each belongs to and what the operator can change.
- **FR-004**: A name with no declared id MUST be given one from its
  identity's pool, never an id any identity holds, claims or once held,
  and the id MUST be recorded when the tree's records are saved.
- **FR-004a**: The POSIX identity MUST be the final fallback: a POSIX user
  or group whose name an external identity provider holds (a name being
  the configured name, never a name the provider generates on the
  machine) MUST take that provider's id, and a different declared id MUST fail validation saying
  which id it must be. Only the POSIX identity defers so.
- **FR-004a1**: A POSIX name recorded with one id that an external
  identity later holds with another MUST fail validation, naming both ids
  and saying one of the names must change; neither id moves.
- **FR-004b**: Between external identity providers, one name with two
  ids, or one id with two names, MUST fail validation as a configuration
  error naming both providers.
- **FR-004c**: An id held anywhere in the system, now or before, MUST NOT
  be given to another name; it MAY only return to the name it was first
  held by.
- **FR-005**: A recorded id MUST NOT change: not by a later run, a change
  of the pool, a reordering of the tree or a provider's later report. A
  change requested by any of these MUST be refused, naming both ids.
- **FR-006**: Every identity plugin that manages ids MUST have a pool
  with known bounds, above the system's floor: Okta's as its service
  notes it (read by an applying run or the record step and recorded, or,
  when the service does not give them, declared in the Okta group
  builder's configuration), the POSIX identity's in the tree's configuration (with a
  default the system gives). Two identities' pools MUST NOT overlap, and
  an overlap MUST fail validation, naming both. A declared id not yet
  recorded that lies inside another identity's pool MUST fail validation,
  unless it is the POSIX fallback's id of FR-004a. A recorded id is never
  refused for where it lies: one a pool change leaves outside its pool is
  kept and reported. A pool MUST NOT be moved over an id another identity
  has recorded; such a move MUST fail validation, naming the id and its
  holder.
- **FR-007**: An id an identity's provider assigned itself (an Okta
  group's id read from the service, an Okta user's) MUST be recorded when
  first read and MUST take precedence over any declared or pooled id that
  would collide with it. An Okta user's id is always Okta's own; the
  system never chooses one.
- **FR-008**: An identity plugin MUST be able to say which ids it holds
  or will hold, through the contract, and the core MUST check every
  installed plugin's claims together; a plugin added later joins the
  check without a change to the core.
- **FR-009**: A dry run without `--commit` MUST show the ids it would
  give and MUST NOT record any; an applying run, and a dry run with
  `--commit` (the record step), record them *(amended 2026-11-22, D1)*.
- **FR-009a**: Validation and dry runs MUST read ids and pools only from
  the tree's records and configuration, with no network call. An external
  identity's pool and the ids it holds MUST be read by an applying run or
  the record step and recorded; a name whose external id is not yet
  recorded MUST be treated as an id to come, held against the pools and
  checked when it is read.

#### The server registry

- **FR-010**: The POSIX identity MUST keep, per group, a registry of the
  machines launched for that group, each entry holding the machine's
  provider id, its canonical hostname, its address and the aliases it is
  recorded with, kept with the configuration's own records.
- **FR-011**: The registry MUST be read by the core exactly as Okta's is:
  the same questions (whether a registry is kept, which machines a group
  holds, retire a name) with the same answers' meaning. An answer that
  cannot be given MUST be "could not be asked", never an empty list.
- **FR-012**: A retirement MUST either remove every entry under the name
  and say which, or fail loudly; a retirement that did not happen MUST NOT
  be reported as one.
- **FR-013**: A run that launches a POSIX-owned machine MUST register it
  when the launch succeeds; a run that does not launch it MUST NOT.
- **FR-014**: Decommissioning a POSIX-owned instance MUST retire its
  registry entries, as it does for an Okta-owned one, and MUST leave its
  users' and groups' recorded ids as they are.
- **FR-015**: A dry run MUST NOT make a network call for the registry, and
  MUST NOT change it.
- **FR-016**: A POSIX-owned machine's provider alias MUST be chosen by the
  core's existing alias rules and recorded in its registry entry, and
  nothing MUST be written on the machine for it: for an identity whose
  registry is kept in the records, the alias pass writes the aliases into
  the entry instead of running a script on the machine.
- **FR-017**: A machine launched before the change MUST be registered by
  the first applying run that finds it, without a relaunch.

#### Coexistence and where it lives

- **FR-018**: Okta's and POSIX's records MUST coexist: a machine carrying
  both identities' accounts MUST be made with every account under its one
  recorded id, and both identities' server registries MUST live side by
  side in one tree, each group's machines in its own identity's.
- **FR-019**: The registry and the id records MUST be provided by a
  plugin internal to the system: shipped in this repository, installed
  with every installation of the system (never an optional extra, never
  moved to a repository of its own), and written against the same
  published contract as any plugin.
- **FR-020**: The contract's existing registry questions MUST NOT change
  meaning. Any question the contract gains (FR-008) is an addition, and
  the contract's version moves with it.
- **FR-021**: Every core test that specification 008 classifies as
  needing a registry MUST be carried by the POSIX identity, and pass with
  the Okta plugin absent.
- **FR-022**: Every statement in this repository's documentation that the
  change makes false (for example, that an id no side supplies is
  refused, that only an identity with an outside service keeps a
  registry, or that a POSIX group's names are not claimed) MUST be
  corrected.

### Key Entities

- **A recorded id**: one user's or group's numeric id, with the name, the
  kind (user or group), the identity it belongs to and how it was made
  concrete (declared, pooled, or read from a provider); never changed once
  recorded. A POSIX name that defers to an external namesake shares that
  namesake's one record, which is the external identity's, with POSIX
  noted as deferring.
- **An id pool**: an identity's bounded range, from which its
  undeclared names are given ids; each identity has its own, apart from
  every other's.
- **An external identity provider**: an identity plugin whose ids come
  from a service outside the system (Okta today); the POSIX identity is
  the one internal identity and the final fallback.
- **An id claim**: what one identity plugin says about one name's id: an
  id, the name only, or an id it will supply later.
- **A server registry**: an identity's list, per group, of the machines
  enrolled for that group.
- **An entry**: one machine in that list: its provider id, canonical
  hostname, address and aliases.
- **A hostname claim**: a canonical hostname or alias held by an entry;
  one name is claimed by at most one entry per group.
- **A retirement**: the removal of every registry entry under a name, when
  its machine is decommissioned or replaced.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every tree that declares a colliding id, across any two
  identity plugins, fails validation, with zero files emitted and a
  message naming both names.
- **SC-002**: Every user and group of a validated and recorded tree has
  exactly one recorded id, and zero ids are held twice within a kind.
- **SC-003**: Across any number of later runs, pool changes and
  reorderings, zero recorded ids change.
- **SC-004**: The reference configuration's ids are recorded by one
  record step with zero ids changed and zero machines rebuilt.
- **SC-005**: A second launch under a name a POSIX group's registry
  already holds is refused in every case, with zero machines created.
- **SC-006**: After a decommission, zero registry entries remain under the
  retired name, or the run has said by name which one did not retire.
- **SC-007**: Every core test of the registry's guarantees (about 30,
  listed in specification 008's test classification) passes with the Okta
  plugin absent, zero skipped.
- **SC-008**: Validation and dry runs make zero network calls for the
  registry, the ids or the pools, and a dry run records zero ids.
- **SC-009**: Every POSIX-owned machine already launched in the reference
  configuration is registered after one applying run, with zero
  relaunches.
- **SC-010**: Every POSIX user or group whose name an external identity
  holds takes that identity's id, in every case; every collision between
  two external identities fails validation; zero ids are ever given to a
  name other than the one they were first held by.

## Assumptions

- The core's rules for hostname claims, retirement, aliases and
  generations are right as they stand and are not changed here, but for
  one step: the alias pass writes an identity's aliases into its recorded
  registry when the identity keeps its registry in the records (FR-016),
  where it runs the identity's script on the machine today. Any contract
  question this needs is an addition under FR-020.
- The core's existing id rule (one name with two ids, or two names with
  one id, is refused) stands and is widened to every identity; its second
  rule (a side that knows only the name takes the other side's id) is the
  POSIX fallback of FR-004a; its fourth rule (a name no side supplies an
  id for is refused) is replaced by the pools.
- The POSIX identity plugin is already installed with every installation
  of the system; FR-019 keeps it so.
- The Okta plugin, in its own repository after specification 008, answers
  the contract's id and pool questions for its ids in that repository's
  specification 002, written once this specification's contract is
  released (D3); this specification names what it must answer, and until
  then Okta's ids are recorded as the state query reads them
  *(amended 2026-11-22)*.
- The POSIX identity's registry holds what the system itself launched; it
  cannot know of a machine another tool made under the same name, as
  Okta's can when that machine enrolls.
- This specification lands before specification 008's T035, which
  re-hosts the core tests on it; 008's other tasks do not wait for it.
- The release that carries it is the next one after it merges, which may
  be the batched release for specifications 002, 003 and 006.
- **Research R-names, the plan's to do, guided by the operator
  (2026-11-22)**, before any story on names is fixed. The fallback matches
  configured names only; what it must find out is how many other names one
  Okta identity has on a machine, and whether accepting them is too
  lenient:
  - which accounts and groups Okta's agent makes on a machine, under which
    names (an account's `unix_user_name`, which need not be its Okta
    username; a group's `unix_group_name`, `sft_<group>_user` by default),
    and when (at login, through PAM and the name service) — the Okta
    plugin already reads `unix_user_name` per member for this reason;
  - which of them persist (user accounts, when the agent is told to keep
    them; the operator: the Okta plugin should tell it to by default) and
    which are fluid (the groups PAM makes, present while a session is);
  - whether the group the POSIX delegate makes for an Okta group (its
    configured name, under Okta's id) and the fluid `sft_<group>_user`
    group Okta's agent makes are two names on one id on the machine,
    which FR-002 refuses, and what the rule should be;
  - whether the system should refuse an Okta group whose machine name is
    not derived from its configured name, or map the two, and how a POSIX
    name that matches only a generated name is treated.
  Its outcome says whether the rules land as stories in this
  specification or in one of their own, and whether forcing persistent
  user accounts belongs to this specification or to the Okta plugin's
  own (the plugin is then in its own repository, specification 008).
- Okta's part stays read-only here: the system looks Okta's users up and
  never writes them, and every Okta id rule above assumes so.
- The live proof runs against the reference configuration
  (`cs-image-system-testconfig`), whose instances are the operator's; a
  launch, a decommission or a record step in it is the operator's to run.
