# TODO

Execution worksheet: the stages of work in flight, one section per stage.
A section is removed when its stage lands, and the squash commit that
lands it is the record; how the system got here lives in git history and
in the frozen [docs/history/](docs/history/README.md). Steps marked
**USER** need the operator: a decision, or a console or IAM action the
system must not take itself.

Current stage: **none in progress**.

Open stages and their order (revised 2026-09-21, when §58-§60 were added):
**§56 -> §19 steps 4-5 -> §59**, with §30 orthogonal. (§57, §55, §58 and
§60 all LANDED 2026-09-21 -- §55 in two passes, steps 1-3 before §58 and
step 4 after §60, which is how the three stages' dependency cycle was
broken. Both live proofs landed 2026-09-21 22:21 in one applies-on
instance-image run the operator made with `coops-model` running: its record
now answers to `ip-10-26-34-156` as an `AltNames` alias, and the ledger
opened it as durable generation 1. `coops-model` is grandfathered under its
bare name until its first sanctioned replacement, which is the first real
`-NNN` launch.) §55 SPLIT because, taken whole,
§55, §58 and §60 formed a dependency cycle. §56 proves what §19 step 4
claims; the naming is now settled, so it can write the proof down, after
which §19 finishes -- its step 5, the upgrade path, having gained something
concrete to mean from §60 (a sanctioned replacement is a new generation with
a new name). §59 is deliberately LAST: it overlaps the suffix, and only once
that is standing can anyone judge whether a name pool is still wanted. §30 waits on the operator's decision and depends
on none of this. §61 is the open hygiene bundle (V); a new hygiene issue
goes there.

**The path to §19 is now the path**: **§56 -> §19**, two stages, with §59
the only naming work left and deferrable. Nothing in that shorter path has to be redone -- §58
adds the bare name back as an alias, so a proof written against `coops-model`
survives the suffix.

Standing decisions (operator):

- The documentation describes what is; no document carries a commit hash;
  a landed stage is recorded by its squash message, not by a ledger or an
  archive entry.
- A hygiene issue that should be fixed but does not threaten function goes
  into the open **hygiene bundle** stage as a numbered item, not into a
  stage of its own and not only into a commit message. If no bundle is
  open, start one. Work that is large, or that blocks something, still
  earns its own stage.
- Publication is done: both repositories are public, each a single commit
  built from a redacted tree, with the pre-publication history private and
  archived. The identifiers (account id, project number, VPC, subnet and
  security-group ids, image ids, the state bucket, the Okta org and OPA
  team) are public by decision; the live rosters are real and encrypted to
  the four recipients; the fixture's people are synthetic.
- All terraform state stays in the AWS S3 backend by design; a GCS backend
  for the GCE roots and per-runtime networking validation are the very
  last priorities and are not stages; a session identity for the runtime
  session hook other than the operator's login key is deferred.
- No new GCP work unless a change is likely to make the existing GCP code
  fail; then the GCE cycle runs as the proof, on the operator's account,
  and is torn down. GCP is the operator's money.
- `main` performs (stage 45): a push to `main` records the full
  configuration, then bakes, releases and applies retention on the AWS
  runtime under the write role, then records again. The GCE runtime stays
  out of CI: a declaration change there fails the job before anything
  performs. A push to `main` is the operator's act.
- State backends (stages 46 and 47, landed 2026-09-17): three types, `s3`,
  `local` and `gcs`; every live root stays on the default S3 backend and
  the `gcs` backend is declared (commented out in the live tree) and bound
  to nothing until moving the GCE roots is decided.
- Releases publish to an index (stage 41, landed 2026-09-17): PyPI,
  TestPyPI first, every version through `just release <part|version>
  [test|pypi]`; the first upload, `0.1.1.dev1`, is on TestPyPI and
  installs from it into a fresh virtualenv (an install in the seconds after
  an upload can fail to resolve until the index has propagated). Versions
  on TestPyPI will be deleted during development, and a deleted version is
  never re-cut. The first final version (`just release stage pypi`, after
  a green `full-test` with docker on a clean live configuration, with
  `PYPI_TOKEN` in place) is the operator's call; trusted publishing
  replaces the tokens once the package names are stable.
- §19 (the first real model image) stays planned by the operator's
  instruction; §30 (the contract package) is planned.

---

## 19. The first real model image, released and in use

**Why**: the system's stated purpose (EXPLORE "Systemic Purpose") is
images that are correct for a given HPC model, formally released, with
scientists logging in. The retrospective's warning still stands — "the
doorway got finished before the building": the fixture's playbooks are
placeholders (DESCRIPTION.md), the dask image installs dask and nothing
else, and no image has been used by anyone. Every mechanism the purpose
needs now exists: shell + ansible modifications with local mod tests,
in-bake and post-bake tests, declared releases, `require_released_builds`,
group ownership → OPA access (proven by `sft ssh` in stage 1), storage
attached by group. This stage spends them on one model, on AWS.

1. **USER — the model.** **No GCP resources** (operator, 2026-09-20): this
   stage is AWS only, whatever the GCE runtime's images say they are due.
   Decided 2026-09-19: the group is **`coops`**, the
   instance is a **`c5n.4xlarge`**, and it mounts the **existing `mnt_data`
   and `efs-storage`** — no new storage declarations. What that settles, and
   what it implies:
   - Both storages already allow `coops` and are `active`
     ([storage0.yaml](../cs-image-system-testconfig/storages/storage0.yaml)):
     `mnt_data` is EBS at `/mnt/data`, `efs-storage` is EFS shared with
     `stofs` at mode 2775. Nothing there has to change.
   - **The AZ is already right, and nothing needs pinning.** `mnt_data` is the
     100 GiB volume `vol-0fe1e27716f86c2f2` in `us-east-2a`; EBS is AZ-bound,
     so the instance must be there to attach it — and the runtime's DEFAULT
     subnet is `east2-az1-private` (`subnet-09f79018af845358a`), which is 2a.
     The instance model names no subnet; the builder reads the runtime's
     default. `c5n.4xlarge` is offered in 2a, 2b and 2c, so the size does not
     constrain the choice. Both declared private subnets map no public IP, as
     the standing constraint requires. Note for later: if the default subnet
     is ever flipped to 2b, this instance stops being able to attach
     `mnt_data`.
   - Its users are the `coops` roster: `zachary.wills` (member),
     `mykel.alvis` (admin), conformed to OPA on 2026-09-18.
   - **The image derives from `basic-rh-10` directly** (decided 2026-09-19),
     not from either existing `coops` image: a new `coops`-owned instance
     image whose only modifications are the model's. Cleanest lineage, at the
     cost of repeating whatever setup `imgfile-basic-dask` already does.
   - **The instance stands 24/7** (decided 2026-09-19): a normal declaration,
     left running, so the group's members can log in whenever — the half of
     this stage's purpose that an ephemeral instance would not exercise. It
     bills continuously: roughly $620 a month at the figure above, plus the
     100 GiB volume and the EFS filesystem. `mnt_data` is
     `attachment_cardinality: single`, so while this instance stands it owns
     that volume and no other instance can attach it.

   **Still needed from the operator, and blocking the bake:**
   - **What the image must contain**: the model's packages, its source or
     binaries and where they come from, and the data paths it expects under
     `/mnt/data` and the EFS mount.
   - **What "correct" means**: the smoke run that proves the image, and the
     files and services that must be present after a bake.

   Everything else is settled, and nothing can be baked without those two:
   an image derived from `basic-rh-10` with no modifications is just
   `basic-rh-10`. The cost figure above could not be confirmed from the
   account — this role has no `pricing:GetProducts` — so check it before
   relying on it.
2. **The image**: `basic-rh-10` on AWS plus an instance image owned by
   the model's group; real modifications — ansible for the stack, bash
   `ensure` for glue — idempotent and passing `just test-mods`; in-bake
   `tests:` and `tests.post_bake` running the model's smoke test;
   `release: {model: <name>}`.
3. **The instance(s)**: declared for the group with `image_policy: pinned`
   and `require_released_builds: true` (only a released build may pin);
   storage per the decision; launched through the gates on AWS (private
   subnet, no public IP; the existing network configuration untouched —
   standing constraint).
4. **Users in**: the group's members log in through the Okta gateway
   relay (`sft ssh`); evidence captured, the stage-1 shape.
5. **Operations, once**: the upgrade path exercised end to end (`upgrade
image` → re-bake → `upgrade instance` → gated replace) so the model's
   second release is a procedure, not a discovery; the standing cost noted
   for the AWS account.
6. Records: ledger, PLAN, OPERATIONS "a model image, end to end".
   Feature branch `feature/model-<name>`, squash-merged, kept.

## 30. The plugin contract is a package of protocols

**Why**: a plugin author should be able to write a plugin against ONE
package — `cs-image-system-contract` — and never import, let alone
subclass, the core's base classes. The base classes are the convenient
implementation of that contract, not the contract itself; a plugin that
satisfies the protocols structurally is a first-class plugin. That is the
operator's stated goal (2026-09-13) and it reverses the direction §29 had
taken (fold the protocols into the bases): the protocols are kept and made
real. Today the promise is not delivered: `base/protocols/` imports
`constants`, `registry` and the field helpers from the rest of `base`; a
plugin's own `pyproject.toml` depends on `cs-image-system-system` (the CLI
host); plugins import from ~60 core modules and ~106 names, of which ~24
are functions whose first argument is the live run context, reached
through the `GlobalTypeContext` singleton at ~50 sites; the mapper
dispatches on base-class identity; and two things already satisfy a
protocol structurally only by accident (`ProviderSpecificImage`, and every
`BuilderBase` at the registry's gate). Measured 2026-09-13 with the
per-plugin distance: `tf-s3-state-plugin` needs 7 core names,
`tf-ebs-instance-plugin` 42 plus 24 context reaches.

**Honest cost**, in three tiers: the two static tiers (models, behaviour)
are ~3–4 days of mostly mechanical work; the context interface is 1–2
weeks and is the part that makes an external plugin real; the proving
plugin 1–2 days. Call it three weeks, done as three branches.

1. **The package**: `packages/contract` → `cs_image_system.contract`, a
   workspace member with NO dependency on `base` or `system` (pydantic and
   `packaging` only); `base` depends on it, never the reverse, and a test
   asserts the import direction. It carries the constants protocols need
   (`VCT`, `FK_TARGET`, `DEFAULT`/`SELF`/`OOPS_DEFAULTS`),
   `CSIS_MODEL_CONFIG`, `fk_field`/`templated_field`, the lifecycle enums
   (`ExecutionLifecyclePhase`, `Lifecycle`, `LifecycleSpec`, `HookSet`) and
   the value types a plugin constructs (`Asset`/`AssetSet`,
   `ExecutableModel`, `CFExecutables`) — concrete data carriers are part
   of a contract; behaviour is not.
2. **Tier A — model protocols** (structural, with attribute declarations):
   `NameTyped` (`name`, `type_`, `description`, `aliases`, `global_id`,
   `get_classification`), `BuilderModel`, and one per builder kind
   (runtime, os, storage, image, instance, mod, group, user, state) with
   exactly the attributes the core reads. A plugin model is any pydantic
   dataclass under `CSIS_MODEL_CONFIG` that satisfies them; the `type`
   alias and `fk_field` metadata are the contract's, exported. The
   `ParentPropertyHolding` attribute (`_model_id`) is declared in the
   protocol and by each implementer — a protocol cannot carry a dataclass
   field, which is why it is copied at nine sites today; `base` offers a
   pydantic-dataclass mixin as the convenience, and the copies in the
   core's own models go through it.
3. **Tier B — behaviour protocols**: `PluginMetadata` (the seven
   properties; `AbstractPluginMetadata`'s `version` bug — it returns the
   metadata version — fixed on the way), `PluginArtifact`
   (`csis_name`/`csis_classifier`), and the builder surface: the six
   universal lifecycle hooks (`generate_items_{before,during,after}`,
   `get_commands_to_run_{before,during,after}`) as `Builder`, plus one
   protocol per kind for the ~60 domain hooks (`StorageBuilder`:
   `module_args`, `capability_type`, `attachment_cardinality`,
   `transition_actions`, `supports_archive`…; `RuntimeBuilder`: the 21
   query/session/dispose/power hooks (16 until stage 57 added the power
   state -- `can_query`/`query_instance_power_state` and
   `can_set_instance_power_state`/`start_instance`/`stop_instance` -- so
   recount before trusting any number written here); `GroupBuilder`, `ImageBuilder`,
   `InstanceBuilder`, `ModBuilder`, `UserBuilder`, `StateBuilder`). The
   protocols carry NO implementation (today `NameTypedProtocol` supplies
   `global_id` and a `get_classification` default; those bodies move to
   the base classes). `StateManagementRootProtocol` is dead — zero
   implementers — and is deleted.
4. **Tier C — the context protocol**, the expensive part: `RunContext`
   with the ~55 members plugins read (top: `meta_state`,
   `runtime_builders`, `os_builders`, `run_id`, `instances`, `images_map`,
   `generation_path`, `storage_builders`, `storages`, `dry_run`, …), with
   `MetaState` its own protocol (the mutable run records that the storage
   and instance builders write on both clouds); the ~24 context-first
   functions plugins import (`capabilities.*`, `lineage.*`,
   `launch_params.*`, `image_tests.*`, `storage_state.*`,
   `identity_attributes.*`, three from `commands.verify_instance`) either
   become methods of the protocol or are re-exported by the contract as
   functions typed against it. `GlobalTypeContext` implements it; the
   builder protocol receives the context by injection (`bind(ctx)`) so a
   plugin never constructs the singleton — the ~18 direct
   `GlobalTypeContext()` constructions in plugin code and the 33
   `_get_context()` calls go through it.
5. **The base classes implement the protocols** — `class NameTyped(…)`
   declares the protocol nominally as well, so pyright checks every base
   against it at definition time; a `contract.testing` module ships
   `assert_conforms(cls, protocol)` (signature-level, via `typing`
   introspection, stricter than `runtime_checkable`'s name-only check)
   and the core's tests run it over every base class and every built-in
   plugin. The two accidental structural implementers become deliberate:
   `ProviderSpecificImage` and `BuilderBase` conform by the same test.
6. **Runtime checks stay structural** and move to the contract's
   protocols: `loader.py` (`PluginMetadata`), `registry.py`
   (`NameTyped`, `PluginArtifact`), the orchestrator's marker dispatch
   (`SelfInjectedName`, `ParentPropertyHolding`, `SubItemOverride`) — all
   `runtime_checkable`, all name-only at runtime, all backed by step 5's
   conformance test so the looseness is not the only check. The mapper:
   `PydanticConverter` drops its base-class identity table (`_base_vcts`)
   and dispatches by `csis_classifier()` for any registered dataclass that
   satisfies `NameTyped` — the registry already resolves plugin models by
   type key.
7. **Plugins depend on the contract**: every plugin's `pyproject.toml`
   depends on `cs-image-system-contract` and, only where it truly uses a
   core utility, on `base` (the ~12 pure helpers — `render_module_call`,
   `hcl_expr`, `super_safe_name`, … — move to the contract or to
   `hashicorp-utils`, which is declared for what it is: a library five
   plugins use, not a plugin). The three undeclared dependencies
   (`tf-ebs`→`aws_runtime`, `aws-runtime`/`gcloud-runtime`→`dummy_plugin`)
   are declared or removed; the three private cross-plugin imports
   (`_groups`, `_public_read`, `_make_credentials`) get public names. No
   plugin depends on `system`.
8. **The proof — an external plugin**: a new workspace member
   `packages/contract-example-plugin` implementing one trivial storage (or
   runtime) plugin against `cs_image_system.contract` ONLY — a test greps
   its source for `cs_image_system.base` and fails on any hit; it is
   loaded by entry point, its model structures from a fixture YAML, and it
   participates in a dry `run --all` over a copy of the frozen fixture
   with its module call emitted. That is the acceptance; without it the
   contract is a claim.
9. Residue carried from §29: fix `RuntimeBuilderBase`'s anonymous inline
   TypeVar (it was never generic); the nine `_model_id` copies in the core
   go through the mixin; the four type-escape hatches caused by the
   protocol/base split (`builder_base.py:61`, `orchestrator.py:681`,
   `registry.py:86`, `os_builder_runtime_config.py:173`) are fixed, not
   repointed. Golden byte-identical at every branch; bar green; pyright at
   0 errors. Records: ledger; DESIGN's plugin-contract section rewritten
   around the package; OPERATIONS "writing a plugin". Branches
   `feature/contract-package` (steps 1–3, 5–7),
   `feature/contract-context` (step 4), `feature/contract-example`
   (step 8), each squash-merged, kept.

## 56. CI logs in through the policy the system manages, and that is the proof

**Why**: §19 claims that owning a group gets you into the machine, and
nothing demonstrates it. The system verifies an AWS instance through SSM --
that is how `coops-model`'s mounts and packages were checked -- which proves
the box is healthy and says nothing about access. The operator proved the
claim by hand on 2026-09-21 (`sft ssh coops-model`, after the duplicate
registrations were cleared); a claim proved by hand once is a claim that
regresses silently. And it is not a claim about one model: the system emits
a login policy for EVERY group it manages
(`tfmodules/okta_opa_module/main.tf:64`), so the proof is that THOSE
policies grant, for every group with a machine standing.

It is also worth stating why this is not a workaround. `sft ssh` felt to the
operator like something automation is meant to be excluded from. It is not:
OPA shipped workload identity for exactly this in March 2026, access is
granted to principals rather than to human-ness, and the alternative -- a
long-lived SSH key in a CI secret -- is the thing OPA exists to replace with
a short-lived, audited, per-session certificate.

**Settled 2026-09-21/22 from the docs, the 1.114.0 client and the
provider's source (the team's API was not queried):**

- The legacy ASA "service user" route does NOT fit a GitHub runner: a
  service user authenticates from an enrolled SERVER (the automation host
  runs `sftd`, and the project's *Services* tab binds the service user to a
  local UID on THAT server). A fresh hosted runner per job has no such
  binding. `SFT_TOKEN_FILE`/`SFT_NO_BROWSER` are the human-flow switches,
  not the lever.
- The modern route needs no enrollment: `sft workload authenticate --team
  <t> --connection <c> --jwt-env VAR [--role-hint <role>]` prints a
  short-lived token (`OPA_TOKEN`); with `OPA_ADDR` and `SFT_TEAM` set,
  `sft ssh <host> --command '...'` then works. The identity proof is GitHub
  Actions' own OIDC JWT -- the same federation CI already uses for AWS -- so
  no static secret at all.
- Three OPA objects: a **Workload Connection** (team-scoped trust in the
  token signer; a DevOps admin drafts it, a security admin activates it), a
  **Workload Role** (a principal; conditions on the JWT claims), and a
  **security policy** naming the role.
- **The provider gap.** okta/oktapam 0.7.1 is the latest release (May
  2026; the module's constraint is `>= 0.6.3`) and its source contains the
  word "workload" zero times. Both `oktapam_security_policy` (principals:
  `groups`) and `_v2` (`user_groups`) accept ONLY groups as principals. So
  Terraform can neither create the connection or the role nor put a role
  into a policy. The OPA API can do all three (create endpoints for
  connections and roles; the console adds roles to policies), and the
  system already does API-side OPA work through the same client -- §55's
  retirements and §58's aliases.

**The shape (decided with the operator 2026-09-22):**

1. **One connection and one role per team, hand-made, referenced by
   name.** The connection is the trust anchor, scoped to the team, and its
   activation is a security-admin act by design. The role is CI's one
   identity: a role reaches nothing by itself, policies grant reach, and
   the policies are per group, so one role is exactly as much identity as
   CI needs (per-group roles would all carry the same condition and buy no
   isolation). Both are bootstrap objects like the OPA API key pair:
   created once, named in the live configuration on the okta-tf group
   builder beside `team` (`workload_connection: github-cs-image-system`,
   `workload_role: cs-image-system-ci`), read by the system from then on.
   The proof refuses when either named object is absent or the connection
   is still a draft (the API reads its status). The claims are pinned BY
   NAME (`repository` and, redundantly and on purpose, `repository_owner`)
   so the document serves the next organization and a person can read the
   values off their remote URL; the one impersonation a name pin leaves
   open (the owner's name recycled after deletion) and the relocation
   order are written down beside the choice. The click-by-click checklist
   with the values decided is
   [WORKLOAD_CONNECTION.md](WORKLOAD_CONNECTION.md); it makes ONLY those two
   objects. **USER**: create both on the morning of 2026-09-22 (the
   connection as a draft) and hand back the names (and the audience, if
   the form shows one).
2. **Prove the token before anything depends on it.** A dispatch-only CI
   step requests GitHub's OIDC token (`id-token: write` is already granted
   to the live and perform jobs) and runs `sft workload authenticate
   --role-hint cs-image-system-ci` against the DRAFT; a draft validates
   tokens and issues nothing usable, so this is free of consequence. When
   the log shows the token validate, the operator activates the
   connection.
3. **One CI policy per group, system-managed, SEPARATE from the user
   policy.** `<g>_v1_security_policy_ci`: a copy of the group's standing
   user policy record (`<g>_v1_security_policy_user`, the one terraform
   wrote: same resource group, the rule verbatim -- label selector
   `sftd.tx.group=<g>`, `principal_account_ssh`, admin-level off) with the
   team role as its only principal. Because the provider cannot name a
   role as a principal, the okta group builder creates and reconciles it
   through the OPA API in the identity lifecycle after the terraform apply,
   under the same guards as the rest of that lifecycle (`apply_identity`
   gates the write, a dry run reports what it would create or change),
   records it in `meta-state/identity.yaml`, and `state query` drift-checks
   it like the groups: absent or diverged from the user policy is drift
   [HARD], an unanswerable API is unavailable. Deriving the copy from the
   standing user-policy record at every reconcile is what makes "mirrors
   verbatim" structural rather than a promise. When a group leaves the
   configuration the CI policy goes in the same pass as terraform's
   destroy of the user policy, behind the same "did the destroy apply"
   check §55's retirement uses. Separate, and not a principal added to the
   user policy, for three reasons: the provider could not mix a role into
   that policy's principals anyway; a machine principal inside the human
   policy means a CI change can lock a scientist out; and a separate policy
   is its own audit line, revocable alone. Open question the first login
   answers: which Unix account a workload lands in under principal-account
   SSH (a workload has no personal account); record it. The security
   policy endpoint and JSON are known from the provider's own client; the
   `workload_roles` principal field is known from the client SDK's tags and
   is confirmed by a GET before the first POST.
   **Built 2026-09-22 on `feature/ci-logs-in`** (`workload_policy.py`,
   `workload_access.py`, the builder's three contract methods, the
   read-model and state-query wiring, 11 tests; the sibling names both
   objects on its okta-tf builder). **Owed**: the first live reconcile --
   an identity run with `apply_identity` on, which is the operator's
   (`run identity` against the live tree), and which also confirms the
   `workload_roles` principal shape and the workload listings' paths
   against the real API.
4. **The proof leg, generic.** The runner installs `sft` (nothing in the
   Justfile or CI does today). For each managed group with a standing
   instance: `sft workload authenticate --role-hint cs-image-system-ci`;
   `sft resolve <name>` must return exactly ONE server (§55); `sft ssh
   <name> --command id` and assert on the output. A leg of `cloud-verify`
   beside `serial` and `iap`, so it is the same shape as the checks that
   already exist. It runs against whatever §19 leaves standing and
   launches nothing. After its first green run from `main`, the operator
   adds `ref` Equals `refs/heads/main` to the role, matching the AWS write
   role's trust.
   **Built 2026-09-22** (`commands/login_proof.py`, `verify login`,
   `identity workload --env`, `scripts/opa-workload-token`, `just
   ci-login-proof`, the `sft` leg of `cloud-verify`, the two `perform`
   steps, 9 tests). **Owed**: the first live run, which needs the
   connection ACTIVE (checklist 6.3) and the CI policy created (step 3's
   owed identity apply), then `just ci-login-proof coops-model` by hand or
   a `perform` on `main`.
5. **What it must fail on.** The group's CI policy deactivated or absent;
   the role's condition not matching the run; a machine that never
   enrolled; and a DUPLICATE canonical hostname (§55) -- the last one
   especially, since a second `coops-model` makes `sft ssh` reach an
   arbitrary one of them. Deactivating one group's CI policy must turn
   THAT group's leg red and no other, or it proves nothing about the
   policy.
6. Records: OPERATIONS on proving access rather than health, on the team
   connection and role as bootstrap objects with the impersonation and
   relocation cases, and on the per-group CI policy; the checklist folds
   into OPERATIONS and the file is deleted. Feature branch
   `feature/ci-logs-in`, squash-merged, kept.

Order: 1 -> 2 -> 3 -> 4 -> 5 -> 6. This is larger than "a CI leg": the
identity lifecycle learns one more object, through the API, and that is
the honest size of it.

## 59. A pool of names, each spent once

**Why**: §58 gives an instance somewhere to put a memorable name; nothing
supplies one. A `meta-state/aliases.txt` in the configuration is a pool of
pre-approved names, hand-written in advance, one per line. When something
needs an alias the system takes the first line that is not commented out,
uses it, and comments that line out IN PLACE, recording on the same line what
took it and when. A name is therefore spent exactly once, permanently, and
the file is both the supply and the ledger -- `git log -p
meta-state/aliases.txt` is the whole history of who was called what.

Optional by construction: no file, no aliases, no error, nothing to
configure. That is the operator's stated shape and it should stay literal.

1. **The file contradicts the directory it lives in, and the file is right.**
   `meta-state/README.md` says "THIS IS GENERATED DATA... NEVER MODIFY
   ANYTHING IN THIS DIRECTORY MANUALLY", and this file is seeded by hand. The
   alternative -- putting the pool in `cfg/` -- is worse: `cfg/` is INPUT, and
   a system that rewrites its own input breaks the thing the whole design
   rests on. meta-state is already the committed, system-owned, durable
   record, which is exactly what a spent-name ledger is. So keep the file
   where the operator put it and amend the README with the one exception,
   stated as a division of bytes rather than of files: **a human only ever
   APPENDS lines; the system only ever comments out lines that are already
   there.** Neither writer touches what the other wrote, which also makes the
   merge trivial when two checkouts both draw.
2. **The burn is the claim, and it comes FIRST.** Write and commit the
   comment-out BEFORE the name is applied to anything. The failure that
   matters is burn-after-use: the run dies between using a name and recording
   it, the file still shows the name free, the next run draws it again, and
   now two machines answer to one name -- the §55 failure, reintroduced by
   the mechanism meant to prevent it. Claim, then use; an unused claim costs
   one name out of a list the operator can extend in one line, which is the
   cheap direction to fail in.
3. **A dry run draws nothing.** `--dry-run` is the default (`V2Run` defaults
   `dry_run=True`), so the obvious bug is a pool quietly drained by runs that
   never launched anything. A dry run reports which name it WOULD take and
   leaves the file untouched -- the same discipline as "dry runs never touch
   remote state".
4. **Two drawers at once.** Several sessions share this checkout and CI runs
   against its own clone, so the draw must be atomic: read-modify-write under
   an exclusive lock, following `MetaState.write`'s existing temp-file-then-
   `replace` pattern (`meta_state.py:154`). Across checkouts only the push
   settles it -- so push the burn promptly, and treat a rejected push on this
   file as "someone else took that name": re-read, draw again, never
   force. (`ALL_FILES` at `meta_state.py:59` is dead code and gates nothing;
   a `.txt` under `meta-state/` is staged and committed like everything else
   there. `MetaState.read`/`write` are YAML-only, so this file needs its own
   small text reader and writer, and no decrypt walk -- names are public.)
5. **The line format.** Keep the name readable and greppable after it is
   spent; the comment marker goes in front and the record after, on the same
   line as the operator asked:

       # bright-otter  -- instance coops-model (i-0169f82844f4cc08d) 2026-09-21T19:04:11Z run 2026_09_21t19_04_11_004213

   Blank lines and existing comments are skipped. Every uncommented line must
   be a legal name for the slot it will fill: since §58 puts it in OPA, it
   faces §55's budget -- an RFC 1123 label, at most 63 characters. Validate
   the whole file at `validate`, where an unusable line is a typo to fix, not
   at 3am when it is the next one up. The operator seeded the live pool on
   2026-09-21 (3671 names, e.g. `cod`, `red-cod`); every line is a legal
   label and none repeats, so the validator's first live pass is expected
   to be clean.
6. **Spent is spent.** A decommission does NOT return a name to the pool.
   That is the point: §55 exists because a name outlived the machine that
   answered to it, and recycling names through a pool would rebuild the same
   problem with extra steps. The pool only ever shrinks; the operator refills
   it by appending.
7. **Running out is a warning, not a failure.** `validate` reports how many
   names remain, so the floor is visible long before it arrives. An empty
   pool means the launch proceeds WITHOUT an alias and says so loudly --
   refusing to start a machine over a cosmetic name would be the wrong
   trade, and §58 already has to survive an instance with no alias.
8. **Not the canonical name.** A drawn name is an alias; the canonical name
   stays the declared instance name (`coops-model`), which is what makes it
   guessable. Drawing the canonical name from this pool would make §55's
   uniqueness structural, but it would also mean nobody can predict what the
   machine is called -- a real option, deliberately not taken here. Revisit
   only if §55's retire-and-refuse proves insufficient in practice.
9. Records: OPERATIONS on the pool -- how to seed it, that spending is
   permanent, and that a human appends while the system comments out. The
   fixture gets a small pool so the draw, the burn and the empty case are all
   tested offline. Feature branch `feature/alias-pool`, squash-merged, kept.

## 61. Hygiene bundle V

Non-critical items, each small enough that a stage of its own would be
ceremony. Landed together on `feature/hygiene-v`, squash-merged, kept.

1. **A group the provider could not be ASKED about is reported as MISSING.**
   `okta_opa_tf_group_builder.query_state` wraps its lookup in
   `except Exception` and records `{"present": False, "error": ...}`
   (`okta_opa_tf_group_builder.py:144`), and the drift assembly turns
   `present: False` into `missing ... [HARD]`. So a lapsed OPA key does not
   report a lapsed key -- it reports that five managed groups are "not known
   to the identity provider", fails `state query --strict`, and sends the
   reader hunting for a group somebody deleted.

   Found 2026-09-21 while proving §57: a `just full-test` launched without
   sourcing `.envrc` failed exactly this way, and the five groups were all
   present the whole time.

   This is the same conflation §57 removed for instances -- "cannot answer"
   dressed up as a state -- one subsystem over, and the fix is the same
   shape: the record already CARRIES the distinction in its `error` key, so
   the assembly need only route an errored lookup to `unavailable` instead
   of `missing`. Absent-and-known stays `missing [HARD]`; unreachable
   becomes unavailable, which `--strict` does not fail on. Whatever §57
   settled for the runtime hooks should be what this follows.
2. **Preflight knows when the session ends; a run that cannot finish before
   then should say so up front.** On 2026-09-21 a 15-minute `just full-test`
   passed every leg and died on the last one: the NOAA portal token expired
   at 16:04:17Z, mid-run. Preflight reads that very timestamp
   (`session: ... EXPIRED at ...`), so it could have refused at minute zero
   with "this session ends in 11 minutes; the live legs need ~15" instead of
   at minute fourteen. The number that binds is the PORTAL session: a
   CLI token issued mid-session only inherits what is LEFT of it (1h43m
   that morning; a fresh browser sign-in then gave a full 8h), while the 1h
   role-credential expiry underneath is auto-refreshed and is not the limit.
   So the remaining time is not knowable from the login time -- only from
   `expiresAt`, which preflight already reads.

   Corrected 2026-09-21, second occurrence: preflight ALREADY refuses when
   the session ends before `config.preflight.expected_run_minutes` (default
   30, `preflight.py:77`) -- but every CLI command runs that check for
   itself, so `full-test` passes preflight at minute zero with plenty of
   window, spends ~20 minutes on the docker and dry-run legs, and the
   state-query leg's OWN preflight then refuses with 11 minutes left. The
   fix is in the recipe, not the checker: run preflight once up front with
   full-test's whole estimate (`expected_run_minutes` for the sum of its
   legs, or a `--needs` override) and let the later legs skip the
   per-command check. Non-critical: the failure is honest and
   environmental; it is just late, and it has now cost two 20-minute runs.

   Since 2026-09-21 19:19 the `noaa` profile is an `sso-session` profile:
   the cache's `expiresAt` is now the ACCESS token's one hour, renewed
   silently from a refresh token while the portal session lives. So the
   number preflight reads no longer means what it did -- a run of 45
   minutes will read as "expires before the expected length" while the CLI
   would in fact carry it. LANDED the same evening, in 55 step 4's branch
   because it blocked that stage's full-test: `aws_sso_expiry` now answers
   "no fixed expiry readable; refreshes itself" for a cache entry carrying
   a `refreshToken`, the answer preflight already gave GCP ADC, so a
   refreshable token cannot block a run on its own. What REMAINS of this
   item is the recipe half: one up-front check with full-test's whole
   estimate instead of a per-leg check.
