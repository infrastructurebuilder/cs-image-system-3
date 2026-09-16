# Design record

This document is the design contract the code cites: the stakeholder
rulings (§2), the design itself (§3) and the standing constraints (§4).
It is derived from [../GOALS.md](../GOALS.md). Operating procedures are
in [OPERATIONS.md](OPERATIONS.md); the configuration schema is in
[CONFIGURATION.md](CONFIGURATION.md).

---

## 1. The shape of the system

The system is founded on separable lifecycles and a
configuration-repository workflow. The table reads GOALS.md against the
design as built.

| Requirement (GOALS.md) | Design |
| --- | --- |
| Identity lifecycle; create-vs-read as separate plugins | The identity lifecycle packages the user and group builders. The okta plugin ships a managed (`okta-tf`) and a read-only (`okta-tf-ro`) variant of each; users are read-only and OPA groups are managed (§3D). Other providers are future plugins against the same seam. |
| Storage lifecycle (S3, Azure Blob, GCS, local FS) | Storage builders exist for `ebs`, `efs` and `s3` (AWS) and `pd`, `filestore` and `gcs` (GCP), each realized by a terraform module; access is group-based (§3E). Azure Blob and local FS are future plugins. |
| Base vs instance images, OS-independent | `base_images` and `images` (instance images) are distinct collections; packer bakes both on the AWS and GCP runtimes. Container and Azure image builders are future plugins. |
| The instance-image lifecycle includes *launching instances* | Instances belong to the instance-image lifecycle (§3A). Group ownership lives on the image, so the image's `sftd.tx.group` label follows every instance (§3F2). |
| CLI-only, headless, CI/CD end-to-end | A typer CLI, dry-run by default, no interactive step anywhere; a failed run exits nonzero and writes a machine-readable summary (§3G). |
| Entirely plugin-based | An entry-point plugin registry supplies the builders. Lifecycles themselves may be plugin-registered (`release`, `retention`). |
| All-YAML config, human-editable | The configuration is YAML (`cfg/` plus the collections); see [CONFIGURATION.md](CONFIGURATION.md). |
| Config in an independent git repo, pulled by the system; generated IaC committed back | The configuration is its own repository; `--root-dir` runs the system against any checkout; `run --commit` makes the meta-state commit (§3B). |
| IaC output: terraform, ansible, CloudFormation, shell | OpenTofu and packer HCL plus shell runner scripts; ansible as provisioners. CloudFormation is a future format plugin. |
| Full + lifecycle idempotency | Terraform roots converge. Images are non-idempotent by design: unique names, series lineage and convergent bake decisions give idempotency at the *reference* level (§3F). |
| Meta-workflow: identity → storage → base image → instance image, each optional, independently state-managed, script-existence apply gating | Four lifecycle units with per-lifecycle generated directories, state and runner scripts (§3A, §3C). |

Preserved by design: the plugin/registry architecture, the YAML → cattrs →
builder pipeline, the HCL collectors, per-workspace S3 state, the applied
Okta/OPA end state, and the never-destroy / gated-apply discipline.

---

## 2. Rulings: the founding questions (Q1–Q7)

The stakeholder rulings in §2–§2k are binding on §3. Their labels
(Q1–Q7, N1–N26) are the names the code cites.

- **Q1 — Storage types are declared base-image capability.** A storage
  type indicates *any* prerequisite changes an image needs. **A base
  image must specify the storage types it can use, and those are the
  only storage types the system recognizes for it downstream.** If an
  AWS-backed base image does not declare EFS, the system refuses to
  attach EFS to subsequent builds/instances — *even though attaching EFS
  to a live instance is technically straightforward* — because the
  prerequisites are not known to be present. Declared capability, not
  technical possibility, is the contract.
- **Q2 — Base-image access is local administrative debug access.** Base
  images need "some form of local administrative access control to
  **debug** a stood-up instance of a base image," OS-independently — not
  managed users/groups, not the r/w/x blend. The mechanism is a
  mandatory local admin user (§2c) with operator-supplied public keys
  and session-based debug (§2d N9). Instance images' artifact-level
  r/w/x (AMI sharing/launch permissions) is deferred (§H).
- **Q3 — Storage access is group-based, by GID.** Storage definitions
  specify the **specific group instances** (never users) allowed
  access. Mechanics: (a) targets are assumed Linux-based; (b) the groups
  carry **system-defined GIDs**; (c) storage access uses group-access
  capabilities wherever possible (mount/directory ownership by GID, EFS
  access-point POSIX groups, and analogous constructs per storage type).
  A storage may declare `public_read: true`, meaning anyone can mount it
  read-only. The schema and emission are in §3E.
- **Q4 — Single owning group; multi-group is a planned later update.**
  An image belongs to exactly **one** group; that group supplies the
  `sftd.tx.group` label. Multiple groups per image is a planned later
  revision (§H). There is no `ALL` magic value.
- **Q5 (firm; revision expected later) — Per-lifecycle deletion.** A
  run wipes and regenerates only the lifecycles it was asked to
  generate; a full run is equivalent to GOALS.md's "delete all" step 0.
  This is the rule, recorded with the expectation that a later version
  revises it (N18).
- **Q6 — Nothing is completely deprecated.** EBS/EFS remain; packer is
  the *only* means of building images. Emulating the packer workflow
  with ansible or plain bash is a possible image-build backend plugin
  (§H).
- **Q7 — The identity lifecycle generalizes the shipped Okta/OPA
  model.** Users are read-only; **managing users via IaC may reappear in
  a later revision** — which is why the managed okta user builder stays
  in the tree, unconfigured, rather than being deleted (§3D).

---

## 2b. Rulings: gids, attachment, pins and meta-state (N1–N6)

- **N1 — The GID authority is the configured identity plugin** (the one
  named in `group_builders`). Per-provider semantics differ and the
  plugin declares them as its gid policy: **okta allows defining a gid
  only at group creation time — thereafter it is a read attribute**; a
  bash-style plugin (`groupadd`/`useradd`) could define gids at config
  time. Consumers never invent gids: **when storage uses a gid (the only
  use), the value is whatever the identity management produced**,
  delivered by reference through terraform remote state (N7) — never as
  a literal in the read-model.
- **N2 — Strict attach rule**: an instance may attach a group-gated
  storage only if its owning group is on the storage's allowed list.
  The `public_read` case (N3) is the "attach any storage" escape hatch.
- **N3 — `public_read` means any instance may mount, POSIX still
  governs.** A `public_read` storage is mountable by anything (the
  attach gate of N2 does not apply to it); internal ids/ownership are
  unchanged, so if group A has write and group B mounted via
  `public_read`, B can read only what A made readable-by-all. That is,
  mountability is opened; readability stays a filesystem-permission
  question. Object stores without POSIX modes map this per storage
  plugin (§3E).
- **N4 — Uniform declaration**: even zero-prerequisite types (ebs) must
  be declared to be used. Externally-managed volumes (not system-managed
  storages) sit outside this contract (§2c N8).
- **N5 — Pins apply between image layers too**: an instance image pins
  to the specific base build it was built from, moved only by an
  intentional upgrade or by a declared `parent_policy: follow` (§3F5).
  This is why **meta-state storage exists**: it holds the pinned images
  for later regeneration.
- **N6 — Read-models are committed files in the config tree.** The
  **meta-state management commit is REQUIRED**: it carries the
  read-models (N6), the pin file (N5, both instance→build and
  image→base edges), and generated IaC (§3B).

---

## 2c. Rulings: gids by reference, external volumes, the admin user (N7, N8)

- **N7 — GIDs are REFERENCED, never literal.** The applied gid value
  flows by *reference*, not as an explicit number passed between
  generations. Mechanism: `data.terraform_remote_state` against the
  identity workspace's statefile — the identity state lives in its own
  statefile and exists before it is needed (identity apply precedes
  storage apply by runner-script order). Every identity provider must
  make its produced gids **queryable downstream**. Consequences: the
  identity root emits terraform **outputs** (a group → gid map, rendered
  from `OutputSpec` blocks); storage and instance roots consume the
  remote state; the read-model files (N6) carry *structural* facts only
  (groups, members, types) — runtime values like gids travel exclusively
  through the reference chain. Where a provider's gid is not visible to
  its terraform provider (OPA's gid is not visible to the oktapam
  provider), the identity plugin supplies the queryable shim: the
  identity root emits a `data "external"` block whose program is this
  system's own CLI (`identity export-gids`), answering read-only from
  the provider's API with credentials from the environment.
- **N8 — Declared if inside, unscoped if truly external.** Two tiers:
  (1) truly external volumes (outside the entire system) may be applied
  by anyone to munge a final instance — out of scope, neither validated
  nor blocked; (2) storages **built within the system but currently
  unconnected** are legal (a storage needs no consumer), remain in
  scope, and **must be declared** — when later attached, the full
  capability/attach rules apply.
- **Q2 sliver — Every base image has a mandatory local admin user.**
  That user is how most base-image configuration is accomplished. In
  addition, where the cloud provides a mechanism (AWS SSM, GCP IAP),
  **standing up an instance in debug mode** is possible for someone
  with system-level access — a runtime-plugin-supplied capability
  (`session_mechanism`). Credential handling for the admin user is N9.

---

## 2d. Ruling: admin-user credentials (N9)

- **N9 — Operator-supplied public keys; session-based debug first; the
  dead end fails loudly.** Per-build persisted keypairs are rejected:
  meta-state lives in a **public** repo, so it can never hold a secret —
  which rules them out structurally. The rule:
  - the config supplies **public key material only** for the admin user
    — a **list** of public keys, so rotation is add-new → migrate →
    remove-old with overlap; the private halves never enter the system.
    Because modifications are bake-time only (N23), key rotation on
    running machines = new image builds + intentional upgrades of every
    instance; the incident-speed consequence is N25;
  - **schema guardrail**: the key field validates as a public key and
    hard-fails on anything resembling private-key material
    (`-----BEGIN … PRIVATE KEY-----`) — in a public config repo that
    mistake is unrecoverable, so it is made structurally impossible;
  - **debug stand-up prefers session access** (AWS SSM, GCP IAP) — a
    runtime-plugin capability (agent baked + role wiring), independent
    of the admin user;
  - where the supplied key exists, any stood-up instance can be logged
    into as the admin user with it — **accepted risk**, recorded: this
    bypasses OPA session recording, central revocation, and
    person-attribution. A future per-image flag may strip the admin key
    at *instance-image* build (base keeps it for debug; instances rely
    on OPA); default off, one flag away rather than one redesign away;
  - **the dead-end case fails loudly**: a base image with *neither* a
    supplied public key *nor* a session mechanism on any of its
    runtimes has no debug path — that is a **hard validation failure at
    generation time**, not a warning.

---

## 2e. Rulings: type-level prerequisites, pins as truth, admin keys (N10–N12)

- **N10 — Prerequisites are type-level; storage *instances* are the
  attachable artifacts.** A given storage type has **many instances**;
  **some instances attach to multiple server instances** (attachment is
  many-to-many — e.g., one EFS mounted by several servers); and **every
  storage instance has a systemwide-unique name** (like groups, enabling
  name-only references). Consequences: baking depends only on plugin
  type definitions plus the base image's declarations — the base-image
  lifecycle is *fully* independent of storage lifecycle runs; the
  storage read-model's job is the **instance inventory** (names, types,
  allowed groups, attachment mapping) consumed at activation/attach
  time by the instance-image lifecycle.
- **N11 — Capability validation resolves through PINS.** Declared
  capabilities are stamped into each build's lineage metadata at bake
  time; validation walks the pin chain to the actual built artifact's
  recorded capabilities. The YAML declares intent for *future* builds;
  the lineage record is truth for *existing* ones. Lineage metadata is
  thereby load-bearing for correctness.
- **N12 — Global admin-key list with per-base-image override**
  (`config.admin_public_keys`, overridden by a base image's own
  `admin_public_keys`; the gateway-selector precedent).

---

## 2f. Rulings: per-group subtrees; no backfill (N13, N14)

- **N13 — Per-group subtrees.** When a storage allows multiple groups,
  each allowed group owns a root-level directory of the storage (`/A/`,
  `/B/`), shared space by convention. Portable across any POSIX
  filesystem; per-group EFS access points remain a possible plugin
  refinement later.
- **N14 — There is nothing to backfill.** The system stamped lineage
  from its first build, so no unstamped system-built artifact exists.
  Hand-built cloud material is N8's "truly external" tier, which the
  system never touches. A backfill, were one ever needed, is a bounded
  one-time script: enumerate self-owned images by series naming/tags,
  stamp lineage records from the then-current declarations, commit to
  meta-state. It is retained as a contingency pattern only.

---

## 2g. Ruling: subtree permission posture (N15)

- **N15 — Group subtrees are private by default.** Each allowed group's
  subtree defaults to `2770` (group-private, setgid so new files inherit
  the gid); between allowed groups, "allowed" means "you get your own
  subtree." Sharing is by explicit choice: the per-storage `share_mode`
  may be set to `2775` for read-sharing between allowed groups. Private
  by default, sharing by declaration — matching the system's general
  posture.

---

## 2h. Rulings: per-instance attachment; rebuilds from the pin (N16–N18)

- **N16 — Storage attachment is per-instance**, for all types. The
  image contributes the *capability* (baked tooling); the instance
  declares which named storages it mounts, validated against the
  image's **pinned** capabilities (N11) and the storage's allowed groups
  via the image's owning group. Mount tooling bakes at image level;
  mount config is written at instance level. The forcing argument: EBS
  single-attach makes image-level attachment inconsistent.
- **N17 — A rebuilt instance image builds FROM its PINNED base build**,
  never the series head — same base, refreshed modifications. That is
  the default, `parent_policy: pinned`; only an explicit upgrade re-binds
  the base edge. An image may instead declare `parent_policy: follow`,
  under which a newer parent head re-bakes the image from it and moves
  the pin, recorded as a follow (§3F5). Emission consequence: the packer
  source query for an instance-image rebuild targets the **effective
  parent build id**, not a most-recent lookup. Running an image
  lifecycle is the build intent (script-existence gating makes baking
  opt-in per run), and bakes are convergent: an image bakes only when
  it has a reason to (§3F4).
- **N18 — Q5 is firm, with change expected.** Per-lifecycle deletion is
  the rule; it is recorded as expected to be revised in a later version
  rather than as unsettled.

Derived rule (it follows necessarily from "carried forward verbatim" +
Q5 wipes): **meta-state — the pin file and read-models — lives OUTSIDE
the per-lifecycle generated-IaC directories and is never touched by
deletion/regeneration.** Wipes apply to generated IaC only; pins change
only via bind, upgrade and follow operations (§3B).

---

## 2i. Rulings: removal semantics; identity types (N19, N20)

- **N19 — Removal semantics, per kind:**
  - **Groups (identity)**: never destroyed, never renamed in place. A
    previously-applied group disappearing from YAML is a hard
    validation failure unless marked `unmanaged: true` (state-rm: alive
    in OPA, unmanaged). Rename = unmanage old + create new.
  - **Storages — a lifecycle STATE, not a flag.** Every storage
    instance has a state, default **`active`**. It may move to
    **`archived`** — and be restored to `active` — **only when it is
    not attached to anything**, and only when its builder realizes
    archiving (snapshot + restore). Reaching **`destroyed`** wipes the
    storage clean. `destroyed`, like `archived`, requires the storage
    to be unattached first; a storage whose requested state is
    `destroyed` — or whose declaration is gone — is the ONLY storage
    whose destruction the apply gate whitelists. A storage EXISTS
    exactly as long as its declaration: deleting the entry is its
    demise, and the next storage run plans the whitelisted destroy and
    records the tombstone (§3E). Systemic data lifecycles per storage
    type are a `lifecycle:` declaration the builder realizes on the
    resource (§3E).
  - **Instances**: decommission is normal; explicit removal destroys
    the instance (data lives on storages), pins cleaned. Upgrade is
    defined in §3F5.
  - **Image builds**: never deleted by omission; removed series go
    quiet; lineage records are retained forever. Declared retention
    (§3F4) is the only thing that disposes of a build, and never one
    an instance is pinned to or was launched from.
  - Cross-cutting: gated applies whitelist only operation-driven
    destroys (upgrade, instance decommission, a storage's requested or
    undeclared demise); any other destroy is a gate failure.
- **N20 — Other identity types are deferred.** Okta is the only live
  identity type; `manual-add` joins LDAP/AD in §H. The multi-type
  machinery (declarations, prerequisite injection, validation) is
  proven by tests rather than by a second live provider.

---

## 2j. Rulings: transition actions, tombstones, bake-time mods (N21–N23)

- **N21 — The plugin owns the transition action.** On a state
  transition the storage plugin is *informed* of the transition and
  executes whatever needs executing — the system defines the states,
  guards, and notification; the plugin defines the behavior.
  Operational consequence: because archiving requires the storage to be
  unattached, and instance changes apply *after* storage changes in the
  meta-workflow order, **detach-then-archive is a two-step process
  across two runs** (run 1: remove the attachment; run 2: request
  `archived`). A single-run "know it all at once" path is a possible
  future refinement, not a promise.
- **N22 — Tombstones keep history, not the name.** A destroyed storage
  is recorded in meta-state as a tombstone with its transition history.
  The declaration need not stay: a storage exists exactly as long as
  its YAML entry, and removing the entry is how a storage leaves the
  system (N19). A name declared again after its demise is a NEW
  storage, recorded as the next *generation* of that name — no data
  continuity is implied. `state: destroyed` in the YAML remains
  available as a staging/testing device.
- **N23 — Modifications are BAKE-TIME ONLY. No mods on runtime
  instances, ever.** (a) Mods apply at bake time to images — base
  images AND instance images; the image for a runnable instance must be
  fully baked before it can be launched. (b) Execution channel: the
  easiest possible means — on AWS, packer's temporary generated build
  key; other channels deferred. (c) Every applied modification is
  recorded per **image build** (operation, content hash, run id) in
  lineage/meta-state. (d/e) Applying a modification to an existing
  instance image **produces a new image build** in its series — never a
  new running instance; instances move only by explicit upgrade (or a
  declared `image_policy: follow`, §3F5).
- **N23 continued — The flow:** bake base images → bake instance images
  **off base images OR off other instance images** (per the build-blocks
  DAG) → stand up machine instances from instance images, with any
  specified attached storage. Instance-image chaining is first-class:
  the `source_image` DAG implements it.

---

## 2k. Rulings: capability inheritance, emergency revocation, launch parameters (N24–N26)

- **N24 — Root-stamp inheritance.** A chain's effective capabilities
  are exactly its **root base build's stamp**, inherited verbatim
  through the pinned parent chain (per N11); instance images can never
  extend or reduce the axes. Capability changes happen only by
  redeclaring the base and baking forward.
- **N25 — The out-of-band emergency procedure is sanctioned.**
  Revocation of a compromised admin key may be executed as a documented
  manual procedure (e.g., via cloud-native session access), explicitly
  **outside** the system's machinery and for revocation only. The
  system itself stays bake-time-only; after the emergency, truth is
  restored the normal way (rotated key list → new builds → intentional
  upgrades), which reconciles any manual intervention.
- **N26 — Launch parameterization is a sanctioned, narrow, recorded
  channel distinct from modification.** The image carries all *tooling
  and policy* (baked); launch parameters carry only *instance-specific
  bindings* (which storages to mount, enrollment trigger,
  hostname-class values), are generated from validated config, recorded
  in meta-state, and are **immutable after launch** — changing them
  means instance replacement, an intentional operation. This boundary
  is what makes N16 (per-instance attachment) and N23 (fully-baked
  images) compatible.

---

## 3. The design

### A. Lifecycle decomposition (the structural core)

The generation work is partitioned into four **lifecycle units** —
`identity`, `storage`, `base-image`, `instance-image` — each owning its
slice of the generation phases:

- A lifecycle = ordered phases (its own validate → generate → finalize),
  a set of participating builder classifications, its own generated-IaC
  directory (`generated/<lifecycle>/`), its own state workspaces, and
  its own **runner script** (see C).
- The **meta-workflow** is a thin orchestrator: it runs lifecycles in
  declared order (identity → storage → base image → instance image),
  each optional, passing forward read-model outputs (group structure
  into storage; the storage instance inventory into the instance-image
  lifecycle). Base images need no lifecycle outputs at all —
  prerequisites are type-level plugin definitions (N10).
- The phase partition: user + group generation → identity; storage
  generation → storage; image generation → base-image; image generation
  and instance generation → instance-image. Before/after hooks still fire
  for every builder, so a builder that reacts to another lifecycle's
  phase keeps doing so.
- The four built-ins are an enum, but the order and the phase/builder
  partition are data, so a plugin may register additional lifecycles
  positioned after an existing one. Two are registered this way: the
  `release` lifecycle after `instance-image` (§3F4) and the closing
  `retention` lifecycle last (§3F4). A registered lifecycle participates
  in every runner mechanism — its own directory, hooks, runner script,
  gating — without any change to the runner.
- CLI: `cs-image-system run <lifecycle>...` (any subset, always executed
  in declared order) or `run --all`; `build-all` is the alias for every
  lifecycle. The usage is in [OPERATIONS.md](OPERATIONS.md).
- **Instances belong to the instance-image lifecycle** (GOALS.md
  §Instance Images: "launching instances from those images").

### B. The configuration repository model

The configuration tree **is** the configuration: it is an independent
git repository, checked out beside this one, and the system runs against
whatever checkout `--root-dir` names. Git (or the CI checkout) handles
the pulling. There is no config-source abstraction; cloud-storage config
sources are deferred (§H). The tests own a frozen fixture of their own
(`tests/fixtures/config/`).

- **Module sources**: generated module calls reach the terraform modules
  through `config.module_source_base` (default `../tfmodules`). In the
  sibling-checkout shape the config repo declares the path to this
  repo's `tfmodules/`, the modules stay here, and nothing else in the
  config tree points outside itself (`.envrc`/key files are
  operator-local either way).
- **Per-lifecycle generated-IaC directories** (`generated/<lifecycle>/`),
  required by §3C's gating and Q5's deletion semantics.
- **The meta-state management commit** (`run --commit`): a single
  well-formed commit after a run recording the cross-run state — the
  identity/storage read-models (N6), the pin file covering
  instance→build *and* image→base edges (N5), lineage, the storage
  state machine's state and history, recorded launch parameters, the
  run journal and generated IaC — with a templated message (run id +
  lifecycles run). **Meta-state lives at `<config root>/meta-state/`,
  OUTSIDE the per-lifecycle generated-IaC directories**: Q5's
  wipe-and-regenerate applies to generated IaC only; pins and
  read-model history survive every wipe and change only via their own
  operations (bind, upgrade, follow, regeneration of the owning
  lifecycle's read-model). Every meta-state write is scanned for
  secret-shaped material and refused if any is found (§4).

### C. Per-lifecycle runner scripts and apply gating

GOALS.md 5.5 realized: each generated lifecycle directory contains at
most one executable entry script (`run-identity.sh`, `run-storage.sh`,
…); the root `final_execution.sh` runs each lifecycle's runner script in
order. The apply step and its gate are described operationally in
[OPERATIONS.md](OPERATIONS.md).

- **Script exists → it runs; script absent → that lifecycle is a no-op.**
  The apply step iterates lifecycle directories and executes what it
  finds. This is the whole gating mechanism, exactly as GOALS.md
  specifies.
- Scripts are reviewable artifacts; dry-run means "generate and
  enumerate, don't execute."
- State is separated per terraform root (per-workspace S3 keys), and a
  lifecycle's runner script touches only that lifecycle's roots, so
  "apply identity only" cannot touch storage state.
- Idempotency contract: each script is safe to run twice (terraform
  gives this; image builds get it from the convergent bake decision, F).
- Self-contained: the header defines `CSIS_ROOT` as the configuration
  root relative to the script and every root-based argument
  (`--root-dir`, `--overlay`) goes through it; each terraform root's
  block begins with its own `tofu init` in the real-run form. A
  committed script names no machine's path and assumes no prior run:
  it runs from any checkout that holds the tree and the credentials.

### D. Identity lifecycle

- The user and group builders are *the* identity lifecycle.
- The model: users are read-only (created by a person in the Okta admin
  UI), OPA groups/policies/membership are managed, and the
  never-destroy invariants are enforced (N19).
- The provider seam is the user-builder and group-builder plugin
  points. The okta plugin ships a read-only (`okta-tf-ro`) and a managed
  (`okta-tf`) variant of each; the managed user builder stays in the
  tree unconfigured (Q7). LDAP/AD/local-file providers are future
  plugins against the same seam (GOALS.md explicitly allows them to not
  exist yet).
- The lifecycle publishes a machine-readable **identity read-model**
  (groups with their builder, identity type, gid policy, managed flag,
  members and admins; users; user builders — *structural facts only*,
  per N7) as a committed file in meta-state (N6). **GID contract (N1 +
  N7)**: the group's identity plugin is the authority; each plugin
  declares its gid policy — settable at config time (bash-style
  providers), settable only at creation (okta), or purely
  provider-assigned — and every plugin makes its produced gids
  **queryable downstream**. The identity terraform root emits
  **outputs** (a group → gid map) for `terraform_remote_state`
  consumers, and where the terraform provider cannot see the gid the
  root's `data "external"` shim asks this system's CLI (§2c N7); gids
  travel exclusively by reference, never as literals in generated
  artifacts.
- **Group-type prerequisite contract**: every group-type plugin (okta,
  future manual-add/LDAP/AD…) defines the config it requires baked into
  a base image that declares support for that type — packages, agents,
  files, service units (`base_image_prerequisites`) — plus how it is
  later *activated* on an instance image (`activation_commands`) and
  verified. The identity plugins own these definitions; the image
  lifecycles only consume them (§3F1).

### E. Storage lifecycle: group-based access and the state machine

- **Schema (Q3)**: every storage definition specifies the specific
  *group instances* (`groups`, never users) allowed access, an optional
  `public_read: true`, the subtree `share_mode` (N15), the requested
  `state` (below) and an optional data `lifecycle` (below). Targets are
  assumed Linux-based.
- **Attach rule (N2, strict)**: an instance may attach a group-gated
  storage only if its owning group is on the storage's allowed list —
  validated at generation time, hard failure. `public_read` storages are
  exempt from the gate: anything may mount them (N3), with POSIX
  permissions still governing what is actually readable (only
  readable-by-all content is visible to non-member mounts). Storage
  plugins for non-POSIX stores (S3, GCS) define their own mapping of
  "readable by all" — plugin-owned semantics, not global.
- **Emission (Q3/N1/N7)**: access is realized through group-access
  capabilities wherever possible — mount/directory ownership by GID,
  EFS access-point POSIX groups (one per allowed group, plus a
  `public_read` access point), and each storage type's analogous
  construct — with every gid consumed **by reference**:
  `data.terraform_remote_state` against the identity workspace (which
  exists before storage applies, by runner-script order), or the
  identity plugin's queryable shim where terraform can't carry it. No
  literal gid ever appears in generated storage IaC. Also legal:
  **unconnected storages** (N8) — built and managed with no current
  consumer, gated like everything else when later attached.
- **Storage is a REAL state machine** (N19) — "not just a
  terraform-state style state management": storages are one of the two
  actually problematic parts of the system, so the design is explicit:
  - **States**: `active` (default on create) ⇄ `archived` → `destroyed`.
    YAML declares the *requested* state; the **authoritative current
    state and full transition history live in meta-state**
    (public-safe: names, states, run ids, structural facts — no
    secrets), not in terraform state and not inferred from cloud
    reality.
  - **Guarded transitions**: `active→archived` and `→destroyed` require
    the storage to be **unattached**; `archived→active` restores;
    `archived` is available only where the builder realizes it
    (snapshot + restore). An illegal request — archiving or destroying
    an attached storage, referencing an `archived`/`destroyed` storage
    from an instance, a new storage starting in any state but `active`
    — is a hard generation-time failure.
  - **Why terraform cannot own this**: declarative convergence cannot
    express imperative sequences ("wipe clean, then delete", "snapshot,
    then delete volume"), cannot guard on attachment, and
    destroy-by-diff is exactly what the apply gate forbids. The state
    machine owns legality and ordering; **terraform is one executor**
    (the resource-shaped steps), and per-plugin **transition actions**
    are another (wipe, snapshot, backup, restore). The storage runner
    script sequences both; every executed transition is recorded in
    meta-state with its run id.
  - **A storage exists exactly as long as its declaration.** Deleting
    the entry is its demise: the next storage run plans the
    whitelisted destroy of the *undeclared* storage (from the root its
    record names) and records the tombstone. A tombstone keeps history,
    not the name: a name declared again after its demise is a NEW
    storage, recorded as the next *generation* (N22). A storage whose
    record names no owning root cannot be planned and is reported
    instead. Only a storage requested `destroyed`, or undeclared,
    passes the apply gate's destroy whitelist.
  - **Detach-then-archive is two runs** (N21): instance changes apply
    after storage changes in the meta-workflow order, so run 1 removes
    the attachment and run 2 may request `archived`. A single-run
    "know it all at once" path is a possible future refinement, not a
    commitment.
  - **Transition actions are plugin-owned** (N21): the system informs
    the plugin of the transition; the plugin executes whatever the
    transition requires for its type.
- **Systemic data lifecycles** are a per-storage `lifecycle:`
  declaration the builder realizes on the resource itself — S3:
  transition days, storage class, expiry, prefix; EFS: infrequent-access
  and archive days. A builder without a data lifecycle refuses the key
  at validation.
- **The storage read-model is the instance inventory** (N10): names
  (systemwide-unique), builder and capability type, allowed groups,
  `public_read`, `share_mode`, requested and current **state** with the
  generation (N19), the data lifecycle, whether the type is POSIX, the
  attachment cardinality and the attachment mapping — consumed at
  attach/activation time by the instance-image lifecycle. **Attachment
  is many-to-many** where the type permits it; each storage plugin
  declares its **attachment cardinality** (EFS/S3: many consumers; EBS:
  single-attach) and validation enforces it.
- Storage **prerequisites are type-level plugin definitions** (N10) —
  drivers/agents/mount tooling per type (`base_image_prerequisites`) —
  consumed by base images that *declare* the type (§3F1). Consequence:
  the base-image lifecycle is fully independent of storage lifecycle
  *runs*; it needs only plugin definitions and its own declarations.
- Providers: `ebs`, `efs` and `s3` on AWS; `pd`, `filestore` and `gcs`
  on GCP. Further provider plugins (Azure Blob, local FS) slot in behind
  the same storage-builder classification when actually needed — no
  speculative implementation.

### F. Image lifecycles: group-type capability, the access loop, and lineage

1. **Base images declare capability on two symmetric axes: identity
   types AND storage types** (GOALS.md §"Base Images define TYPES of
   Identity…" + Q1). A base image declares `identity_types` (e.g.,
   `[okta]`) and `storage_types` (e.g., `[efs, ebs, s3]`). For each
   declared type, the owning plugin's prerequisite contract contributes
   build-time provisioners: identity plugins per §3D (okta → sftd
   installed, enrollment **off**), storage plugins per §3E (efs →
   efs-utils, …). The base image ends up *capable but dormant* for
   every declared type — and **declared capability, not technical
   possibility, is the contract**: an undeclared type is unusable
   downstream even where post-hoc attachment would be easy (Q1's EFS
   example). Every base image additionally bakes the **mandatory local
   admin user** (`admin_user`, default `csisadmin` — the vehicle for
   base-image configuration; operator-supplied public keys per N9, the
   global `config.admin_public_keys` list with a per-base-image
   `admin_public_keys` override per N12), and runtime plugins supply
   **debug-mode stand-up** for system-level operators
   (`session_mechanism`: `ssm` on AWS, `iap` on GCP). A base image with
   neither a supplied key nor a session mechanism on any of its
   runtimes hard-fails validation (N9).
2. **Instance images define specific instances of those types — closing
   the group→server-label gap.** An instance image names only its
   owning `group`; group names are system-unique, so the group name
   alone resolves to its backing identity type through the group's
   builder — no separate type declaration on instance images.
   **Validation is a hard stop on both axes: an instance image whose
   group resolves to an identity type its base does not declare — or
   whose attached storages are of a type its base does not declare — is
   invalid and the whole cycle breaks** (abort the run, not a warning).
   For valid images the lifecycle (a) writes the activation config —
   for okta: the server's `sftd.tx.group` label from the single owning
   group (Q4: one group per image; multi-group is a planned later
   revision, §H) — and (b) turns the dormant plumbing on (the group
   builder's activation commands, verified in-bake). Only then does the
   applied Okta/OPA work govern a real machine end to end. Schema
   consequence: **group ownership lives on the instance image, not the
   instance** — `instances.yaml` has no per-instance `groups:` field
   (and no `ALL` magic value); all instances of one instance image
   share that image's owning group by construction. **Chaining (N23
   continued)**: instance images bake from base images OR from other
   instance images (the `source_image` build-blocks DAG). Each
   instance-image bake **(re)writes the activation config for its OWN
   owning group**, overwriting whatever activation its parent image
   carried — so chaining off group A's image to build group B's image
   cannot leak A's access into B's machines. Capability inheritance
   through the chain is root-stamp, verbatim (N24).
3. **Base-image prerequisites from storage types** (Q1/N10): same
   injection mechanism as identity types — for each *declared* storage
   type, that storage plugin's type-level prerequisite definition
   contributes provisioners (efs-utils, drivers, …). No storage
   lifecycle run is consulted (N10). Identity-type and storage-type
   prerequisites are two producers feeding one "base-image build
   inputs" pipeline.
4. **Unique naming + lineage instead of artifact idempotency.** Image
   generation is inherently non-idempotent — a bake always writes a new
   image. The design embraces it:
   - every generated image gets a **unique name**: stable series
     identifier + build discriminator (the run timestamp);
   - every image carries **lineage metadata** (tags and a lineage record
     in meta-state): series id, parent/source build id, input
     fingerprint, run id, the modifications applied (operation, content
     hash) and — load-bearing per N11 — the **declared capabilities
     stamped at bake time** (identity types, storage types); capability
     validation resolves through the pin chain to these recorded
     values, never to the current YAML (which declares intent only for
     future builds);
   - **bakes are convergent**: an image bakes in a run only when it has
     a reason to — no build on the runtime yet; its **input
     fingerprint** (parent build, capability stamp, modifications,
     in-bake verification commands, disk size, and for base images the
     vendor source, admin user and keys, and update policy) differs from
     the series head's recorded one; its parent moved under
     `parent_policy: follow`; an `update.refresh_days` policy is due; or
     `--force-bake`. A current image is not rebaked, which is what makes
     a bake runner script safe to run twice;
   - **consumers bind to a series once, then stay pinned** (see F5) —
     series-head resolution happens only at first bind, at an explicit
     upgrade, or under a declared `follow` policy, never silently on
     re-run. Per N17 this governs *builds* too: an instance-image
     rebuild's packer source targets its **effective parent build id** —
     never a most-recent query — so refreshing modifications cannot
     silently move the base edge;
   - **retention is declared, never implicit**: `retention: {keep: N}`
     on an image (or a runtime's `retention_keep`) lets the closing
     `retention` lifecycle dispose of older builds of that series on
     that runtime; a build an instance is pinned to or was launched
     from is never disposed (it is reported as retention debt). Without
     a declaration every build is kept;
   - **release is a recorded, reviewable mark on a build**:
     `meta-state/releases.yaml` holds every release and, per model, the
     current released build of each series. Releasing requires evidence
     (the build exists in lineage, passed its in-bake verification, and
     its modifications have no failed mod test on record). An image may
     declare release intent (`release: {model: …}`), in which case the
     `release` lifecycle marks a build whose post-bake tests passed in
     the same run; otherwise the operator's explicit `release` command
     does it. With `config.require_released_builds: true` an instance
     may pin only to a released build.
5. **Upgrades are intentional — instance pinning** (GOALS.md §"Upgrades
   are intentional"). Head-convergence would silently replace instances
   whenever a new build appeared — `aws_instance` treats an AMI change
   as destroy-and-recreate — so it is not the default. The rule: once
   instance XYZ is created from resolved build `ami-abcdefa`, rebuilding
   that image's series must not change XYZ in any way; XYZ keeps its
   original image until deliberately destroyed and rebuilt.
   Cloud-provider-universal. Mechanism (the answer to GOALS.md's
   "cross-run state" question — yes, and the config repo is where it
   lives):
   - a **committed pin file** in meta-state covering BOTH edge kinds
     (N5): instance → resolved build id, and instance image → the base
     build it was built from, per runtime. Written at first bind,
     carried forward verbatim by every subsequent regeneration; the
     meta-state commit (§3B) makes it durable, reviewable cross-run
     state — this file is the concrete reason meta-state storage
     exists;
   - terraform state is the cross-check: generation may consult the
     instance workspace's state to confirm the pin matches reality and
     flag drift (the `state query` report), but the pin file is the
     source of truth for emission;
   - the explicit **upgrade operation** (`upgrade instance <name> [--to
     <build>]`, `upgrade image <name> [--to <build>]`) moves a pin to a
     newer build and records the move — for an instance it is
     understood as a destroy-and-recreate, planned as a whitelisted
     replacement by the next instance-image run. Upgrades move **exactly
     one pinned edge and never cascade**: upgrading an instance image
     (rebuilding it against a newer base build) does not touch any
     instance's pin — each downstream edge moves only by its own
     explicit act (direct consequence of "upgrades are intentional");
   - a declared **follow policy** is the one sanctioned alternative to
     the explicit act: `parent_policy: follow` on an image re-bakes it
     whenever its parent series' head moves and records the pin move as
     a follow; `image_policy: follow` on an instance plans the gated
     replacement whenever its image's series head moves. The default
     for both is `pinned`; an unknown policy is a hard generation-time
     failure;
   - belt-and-braces: the instance modules set `lifecycle {
     ignore_changes }` on the image reference (and on user data /
     metadata) so even an erroneous regeneration cannot replace a
     running instance via apply.
6. Terminology: the configuration keys are `base_images:` (base
   images), `images:` (instance images) and `instances:`; prose uses
   GOALS.md's names, *base images* and *instance images*.
7. **Ephemeral instances and their failure policy.** An instance may
   declare `ephemeral: true`: the instance-image lifecycle launches it,
   runs the runtime's verification, and destroys it in the same run.
   When the verification FAILS, `on_failure` decides: `keep` (the
   default — the instance is left standing for inspection and the run
   fails; the state query reports it as a standing ephemeral until the
   operator decommissions it) or `teardown` (the verdict is recorded
   first, the instance is torn down through the gate, and the run still
   fails). `teardown_after: <duration>` lets the next run tear a
   standing failed instance down without re-verifying once the duration
   has passed — a later run's closing phase is the honest substitute
   for a scheduler the system does not have. Both knobs live on the
   instance or as the runtime's default; the instance wins.

### M. Modifications — recognized problem area

**Storages and modifications are the two actually problematic parts of
this system.** Storage has its state machine (§3E). Modifications have
this section — an honest accounting rather than silent omission.

**Ruled (N23): modifications are BAKE-TIME ONLY — no modification of
runtime instances, ever.** The contract:

- Mods apply at image bake — to base images and to **instance images**
  — through the existing mod-builder machinery, executed over the
  easiest channel (on AWS: packer's temporary generated build key;
  other channels deferred). The image for a runnable instance must be
  fully baked before launch.
- Modifying an existing instance image **produces a new build** in its
  series (unique name, lineage-stamped, mods recorded with operation +
  content hash + run id). It never touches a running instance;
  instances pick up new builds only by explicit upgrade
  (destroy-and-recreate) or a declared `image_policy: follow` (§3F5).
- Consequence for running instances: there is **no in-place change
  channel at all**. Anything that must change on a machine = new
  image build + intentional upgrade (N9 on key rotation; N25 on
  emergency revocation).
- Per-instance *launch parameterization* (user_data/cloud-init writing
  instance-specific mount config, enrollment trigger) is a distinct,
  narrower channel than modification — its sanctioned boundary is N26.
- Drift never exists by construction: a running instance is exactly its
  pinned build plus launch parameters, both provenance-recorded.

### M2. Modification plugins: shell and ansible both work

- **Builder resolution**: deferred `modifications` items resolve their
  builder from the item's `type:` (name or alias of a configured mod
  builder), never from the field name; an unknown type is a hard
  failure, `default`/absent falls back to the default mod builder.
- **Bash mod contract**: `BashModItemModel` accepts inline `script:`
  lines and/or `scripts:` file paths (config-root-relative, copied
  beside the packer root like playbooks), and a declarative `ensure:`
  form that renders as guarded, idempotent shell. Emission is
  well-formed `provisioner "shell"` blocks scoped to the image —
  `scripts = [...]` and `inline = [...]` as two blocks when both are
  given, because packer forbids both arguments in one provisioner;
  optional `execute_command`/`environment_vars` from the builder model.
  No raw lines ever land in the build file.
- **Lineage**: bash mods record `operation: bash` with a content hash
  over inline lines + script-file contents (N23c), exactly as ansible
  mods hash playbooks.
- **Fixture + golden**: the frozen fixture carries one bash mod (inline
  and file) next to the ansible ones so the golden emission covers both
  kinds.

### G. CI/CD headless hardening

- No phase ever blocks on a TTY. There is no interactive finalization
  countdown (`sleep_before_finalization` is accepted for configuration
  compatibility and ignored): a headless pipeline has nobody to change
  its mind, and the safety it pretended to give comes from
  dry-run-by-default, the reviewable runner scripts and the apply gate.
- Exit codes: any failed step fails the run with a nonzero exit, and
  `generated/run-summary.json` is the machine-readable summary of what
  completed.
- The credential contract per lifecycle is environment-only
  (`OKTA_API_*`, `TF_VAR_*`, `AWS_*`, the age identity variable for
  encrypted values); it is documented in
  [OPERATIONS.md](OPERATIONS.md).

### H. Deferred (explicitly not now)

Azure images, container images, CloudFormation output, LDAP/AD identity
providers, artifact-level image access (Q2), cloud-storage config
sources, any config-source abstraction beyond `--root-dir` + git
checkout, **multi-group image ownership** (Q4: planned later revision),
**alternative image-build backends emulating the packer workflow via
ansible or bash** (Q6), **IaC-managed users** (Q7: may reappear in a
later revision — the seam and the managed okta user builder stay), and
**`manual-add` and all non-okta identity types** (N20). All are
plugin-shaped; none block A–G.

**Pulumi / CDK / other program-level IaC** — explicitly not now, and
not plugin-shaped: the gid-by-reference chain (N7), the plan-file apply
gate (N19), the remote-state read-models and the runner scripts are all
terraform-shaped, so a program-level tool would replace the system's
core rather than plug into it. Terraform proper is a binary swap for
OpenTofu. Ansible as an *executor* for launch parameters on
no-user-data targets is a prototype (`base/ansible_launch.py`) that
waits for a real metal/container target. **Adoption of external
resources**: the `state query` report's *foreign* class is the
inventory and `state import` adopts into meta-state; `tofu import`
stays a deliberate human step until there is a real candidate.

---

## 4. Standing constraints

Never destroy OPA groups or users; applies only via reviewed scripts
with state backups; DPoP stays off; manage scopes stay ungranted.

A hard design constraint: **the config repo IS public — by design, not
circumstance.** Everything the system reads from or writes to the config
tree (configuration, generated IaC, meta-state, read-models, pin files)
must be safe for the open internet; secrets reach the system only via
operator-local environment (`.envrc`-style) or as public-key material,
and every schema that could plausibly receive a secret validates against
it. Consequence for membership data: names, usernames and emails in the
rosters and the committed read-models are public unless encrypted. Any
roster value may be declared as an `ENC[age:…]` ciphertext encrypted to
the recipients listed in `cfg/_config.yml`; the loader decrypts it with
the identity the environment supplies (a marked value with no identity
is a load-time refusal, never a silent plaintext), generated IaC carries
the ciphertext and opens it at apply time through the CLI's `decrypt`
command, and every meta-state write is refused if it contains
secret-shaped material. What the operator accepts as public is recorded,
with its reason, under `public_safe:` in `cfg/_config.yml`. If the
publicness is ever *not* intended, it is a constraint problem to raise,
not a code problem.
