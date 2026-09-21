# TODO

Execution worksheet: the stages of work in flight, one section per stage.
A section is removed when its stage lands, and the squash commit that
lands it is the record; how the system got here lives in git history and
in the frozen [docs/history/](docs/history/README.md). Steps marked
**USER** need the operator: a decision, or a console or IAM action the
system must not take itself.

Current stage: **none in progress**.

Open stages and their order (revised 2026-09-21, when §58-§60 were added):
**§55 steps 1-3 -> §58 -> §60 -> §55 step 4 -> §56 -> §19 steps 4-5 -> §59**,
with §30 orthogonal. (§57 led and LANDED 2026-09-21: it settled the
runtime-hook convention §58 and §60 both follow, and the rule §60 depends on
that a stopped machine is the same machine.) §55 SPLITS: steps 1-3 (retire,
refuse, validate the length) need only the OPA client, so they land early and
unblock §58, while step 4 (the generation suffix) needs §60's durable counter
and lands after it -- taken as one indivisible stage, §55, §58 and §60 form a
dependency cycle; see the ordering note in §55 step 4. §56 proves what §19
step 4 claims and wants the naming settled before it writes the proof down,
after which §19 finishes -- its step 5, the upgrade path, having gained
something concrete to mean from §60. §59 is deliberately LAST: it overlaps
§55 step 4, and only once the suffix is standing can anyone judge whether a
name pool is still wanted. §30 waits on the operator's decision and depends
on none of this. §61 is the open hygiene bundle (V); a new hygiene issue
goes there.

**If §19 matters more than the naming work**, the cut is clean: §55 steps 1-3
alone make §56's proof meaningful, so **§55 steps 1-3 -> §56 -> §19**
delivers the stated purpose in three from here, with §58, §60, §55 step 4
and §59 following afterwards. Nothing in that shorter path has to be redone -- §58
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

## 55. A canonical hostname is claimed once in OPA

**Why**: OPA identifies a server by its canonical hostname, and enrollment by
token does not refuse a name already in use -- it registers another server
with the same one. Three `coops-model` entries stand in `coops_rg_login`
today (2026-09-21), one per launch this stage made, and only one of them is
the live machine:

| address | id | |
| --- | --- | --- |
| 10.26.34.156 | `10ff7662-17e8-428e-bc55-30592d313db0` | the running `i-0169f82844f4cc08d` |
| 10.26.35.236 | `772d4058-0606-47bb-83b3-7a5d2b1eb173` | a destroyed launch |
| 10.26.35.35 | `eb95bf11-5c65-4da3-8c6e-804f81ed0d9e` | the first node, destroyed |

`sft ssh coops-model` then has three servers to choose between and no way to
know which answers; the operator reports it as very hard to log in. The
system CAUSES this: it sets the hostname from the instance's declared name
(`launch_params.py:102`, `hostnamectl set-hostname`), so every relaunch of one
declaration enrolls the same name again, and nothing ever retires the old
record (the command itself is at `launch_params.py:127`). Stage 19 made three in two days without noticing.

1. **Retire the record when the instance goes.** A decommission already drops
   the pin and the launch parameters; the OPA server registration is the third
   record of the same event and is not dropped. Same hook, same guard -- and
   the same refusal to act when the destroy did not apply.
2. **Refuse a name already claimed, before launching.** At validate, an
   instance whose canonical hostname is already registered to a DIFFERENT
   server is a refusal naming both, not a second registration. Cheap, and it
   is the check that would have stopped the second `coops-model`.
3. **How long may the name be, and does uniqueness cost us the name?**
   Okta documents no maximum for `CanonicalName` -- its name-resolution page
   says only that the value stands in for the OS hostname and ranks highest
   when resolving an ambiguous name -- so the limit that actually bites is
   ours: the canonical name IS the OS hostname here
   (`launch_params.py:127`, `hostnamectl set-hostname`), so Linux's
   `HOST_NAME_MAX` of 64 bytes applies, and RFC 1123 caps a label at 63
   characters of letters, digits and hyphens. Nothing in the system validates
   this today, and the failure is worse than late -- it is SILENT: the line
   is `hostnamectl set-hostname '<name>' || true`, so an over-long or
   otherwise invalid name does not stop the boot script. The machine keeps
   whatever hostname the hyperscaler gave it (`ip-10-26-34-156`), enrolls in
   OPA under THAT name, and `sft ssh <declared name>` finds nothing at all
   while everything reports success. Refuse the name at validate, where it
   is a declaration error and costs nothing.

   That budget decides the shape of the fix. Decoration was the obvious
   move, and the obvious objection to it was that it destroys the thing the
   operator had just used: `sft ssh coops-model` works BECAUSE the name is
   memorable, and `i-0169f82844f4cc08d` is 19 characters,
   `2026_09_20t19_22_23_470066` is 26. That objection is answered -- not by
   refusing to decorate, but by decorating SMALL and handing the bare name
   back as an alias (step 4). Decided 2026-09-21.

4. **The canonical name is the declared name plus the durable generation**
   (operator decision, 2026-09-21), zero-padded to three digits:

       canonical = f"{instance.get_name()}-{generation:03d}"
       # coops-model-003, coops-model-054, coops-model-256

   The pad is a MINIMUM width, not a cap -- generation 1000 renders
   `-1000` and nothing breaks; four characters against a 63-character
   budget is not a constraint worth designing around. The counter is the
   DURABLE one from §60, so ephemeral churn never advances a standing
   machine's number.

   **Why this is cheap here, when decoration usually is not.** Replacement
   in this system is always control-plane-initiated: `aws_instance` carries
   `lifecycle { ignore_changes = [ami, user_data] }`
   (`tfmodules/aws_instance/main.tf:35`) and a machine moves only when the
   system passes `-replace=<addr>` (`roots.py:203`). So the generation is
   not PREDICTED at render time -- it is DECIDED, by the same code that
   decides to replace -- and because user_data changes are ignored, a name
   change can never itself trigger the replacement that would bump it.
   No feedback loop, and no guessing.

   It also lands on the existing immutability check correctly with no new
   code: `hostname` is a compared launch parameter (`_VOLATILE` excludes
   only run / user_data_sha256 / launched / launched_run / build), so a
   suffix bump is REFUSED unless `pending_replacements[name]` is set --
   which `move_pin` sets on exactly the sanctioned paths. A canonical name
   can only change as part of a deliberate replacement. That is the
   property we want, arrived at for free.

   **The memorable name comes back as an alias.** §58 puts the bare
   `coops-model` on as an `AltName`. The canonical is then unique forever,
   even against stale records; the alias is memorable and unique among LIVE
   machines once step 1 retires the dead ones. The degradation is graceful
   in a way today's is not: if retirement fails, the alias goes ambiguous
   but the canonical still gets you in, where today a failed retirement
   makes the only name you have ambiguous.

   **The one real gap: replacement out of band.** Terminate a machine in
   the console and terraform recreates it on the next apply as a missing
   resource, not via `-replace`. The machine is new and §60 observes a new
   generation, but the name was rendered with the old number, so name and
   observed generation disagree until the next render. The rule: the NAME
   tracks sanctioned generations, the LEDGER tracks observed ones, and a
   disagreement between them is a finding the state report raises -- not
   something either side silently corrects.

   **Settle the overlap with §59.** The suffix and the name pool both
   supply uniqueness; they are not contradictory (suffix for the canonical
   name, pool for an alias), but building both needs a reason. Decide when
   §59 opens, not now.

   **This step lands LAST, and that matters.** As written, §55 needs §60's
   counter, §60 needs §58's identity hook, and §58 needs §55's OPA client --
   a cycle, if each stage is taken as one indivisible unit. It is not one:
   steps 1-3 above need only the OPA client and no generation at all, so
   they land first and unblock §58; §58 then unblocks §60; and THIS step is
   a second pass over §55 once §60's durable counter exists. Implement in
   that order -- 55 (steps 1-3), 58, 60, 55 (step 4) -- and nothing waits on
   itself.

5. **The credentials can already do both** -- corrected 2026-09-21, having
   first claimed otherwise. Servers are NOT reachable at the team-level path
   (`/v1/teams/<team>/projects/.../servers` answers `401 Missing capability`,
   which is what the wrong conclusion was drawn from). They are reachable
   under the RESOURCE GROUP, where the service key's `resource_admin` and
   `delegated_resource_admin` roles apply:

       /v1/teams/<team>/resource_groups/<rg>/projects/<project>/servers

   `GET` answers 200 and `DELETE` 204. No capability needs granting and there
   is nothing to do in either console. Note the ids are not the flattened
   name `sft list-servers` prints: `coops_rg_login` is resource group
   `bca5c2ed-1ffc-4bce-9a56-71d3f7ab7c00` and project
   `69e32009-0f50-4f56-af87-803cb94ee47b`, and passing the printed name as
   the project gives `404 Resource not found`.
6. **The duplicates are gone** (2026-09-21): `772d4058…` and `eb95bf11…`
   deregistered, `10ff7662…` at 10.26.34.156 kept, and `sft ssh coops-model`
   reaches the live machine. That is the symptom cleared, not the cause --
   the next relaunch makes another one.
7. Records: OPERATIONS on what a canonical hostname is, why a second one is
   worse than a refusal, and the resource-group path the API actually wants.
   Feature branch `feature/opa-hostname-unique`, squash-merged, kept.

## 56. CI logs in as a member of the group, and that is the proof

**Why**: §19 claims that owning a group gets you into the machine, and
nothing demonstrates it. The system verifies an AWS instance through SSM --
that is how `coops-model`'s mounts and packages were checked -- which proves
the box is healthy and says nothing about access. The operator proved the
claim by hand on 2026-09-21 (`sft ssh coops-model`, after the duplicate
registrations were cleared); a claim proved by hand once is a claim that
regresses silently.

It is also worth stating why this is not a workaround. `sft ssh` felt to the
operator like something automation is meant to be excluded from. It is not:
the team already has SIX service users, access is granted to GROUPS rather
than to human-ness, and the client (1.114.0) carries `SFT_NO_BROWSER`,
`SFT_TOKEN_FILE` and Okta's PAM SDK including `api_service_users.go` and an
`IsServiceUser` flag. The browser step is the human OIDC flow, not the
protocol. The alternative -- a long-lived SSH key in a CI secret -- is the
thing OPA exists to replace with a short-lived, audited, per-session
certificate.

1. **Settle the client ceremony first, cheaply.** How a SERVICE user enrols a
   client non-interactively is the one unknown: whether `SFT_TOKEN_FILE`
   takes a service token, whether `sft enroll` is needed at all, and what
   `SFT_NO_BROWSER` changes. Establish it here with a throwaway service user
   before anything depends on it. **USER**: this writes to the OPA team
   (a service user, a key pair, a group membership), so it needs a go-ahead.
2. **A CI identity in the group, not an exception.** One service user in
   `coops_user` -- the same group a scientist is in -- so the test asserts
   the real path. Its key pair joins the repository secrets beside
   `TF_VAR_NOS_KEY`/`SECRET`. If it needs a group of its own for hygiene,
   that group is added to the project like any other; what it must not get is
   a capability humans do not have, or the proof is of something else.
3. **The proof itself**: the runner installs `sft` (nothing in the Justfile
   or CI does today), enrols non-interactively, runs ONE command over
   `sft ssh` against the standing instance, and asserts on its output. A leg
   of `cloud-verify` beside `serial` and `iap`, so it is the same shape as
   the checks that already exist.
4. **What it must fail on.** A revoked membership, a machine that never
   enrolled, and a DUPLICATE canonical hostname (§55) all have to fail it
   loudly -- the last one especially, since a second `coops-model` makes
   `sft ssh` reach an arbitrary one of them and a green test would then mean
   nothing.
5. **Cost**: the proof needs a standing instance to log into, so it runs
   against whatever §19 leaves standing rather than launching its own.
6. Records: OPERATIONS on proving access rather than health, and on the
   service-user pattern. Feature branch `feature/ci-logs-in`, squash-merged,
   kept.

## 58. An instance answers to its provider's names too

**Why**: `sft ssh coops-model` works only if you are holding the declared
name. The two identifiers an operator actually has in hand -- from the EC2
console, a cost report, an alarm, a log line -- are the provider's instance
id (`i-0169f82844f4cc08d`) and the first label of the provider's own
hostname (`ip-10-26-34-156` out of
`ip-10-26-34-156.us-east-2.compute.internal`), and neither resolves today.
The second one the system DESTROYS itself: `hostnamectl set-hostname
'<declared>'` (`launch_params.py:127`) overwrites the provider hostname
before sftd ever enrolls, so the name AWS gave the machine is gone by the
time OPA sees it. Each instance should answer to both, and to neither when
answering would be a lie.

1. **Find out what already resolves before building anything.** Okta
   documents the ASA resolution order as a RANKING: (1) server id or
   `CanonicalName`, (2) **Cloud Instance ID**, (3) Hostname, (4)
   **AltNames**, (5) default IP address
   ([server name resolution](https://help.okta.com/asa/en-us/content/topics/adv_server_access/docs/server-name-resolution.htm)).
   Rank 2 is the operator's first alias, already in the platform -- if the
   agent reports cloud metadata, `sft ssh i-0169f82844f4cc08d` may work
   right now with no change at all. Prove it against the live
   `coops-model` (the server record's fields, and the `sft ssh` itself)
   BEFORE writing a line. If rank 2 answers, this stage is only about the
   hostname alias, and the id alias is a documentation note. Do not build
   what the platform already gives.
2. **The field is `AltNames` in `/etc/sft/sftd.yaml`** -- the spelling is
   confirmed twice, by the doc page above and by the `sft` binary's own
   server model (`AltNames`, `GetAltNames`, `alt_names_contains`). Note
   what already writes that file: the bake's `activation_commands` truncates
   it with `tee` (`okta_opa_tf_group_builder.py:113`, `Labels: tx.group`),
   and the launch script appends `AccessAddress` only if absent
   (`launch_params.py:192`). An alias write joins the second pattern --
   idempotent append, never truncate.
3. **The machine cannot decide this; the control side must.** The operator's
   rule is "if there are existing collisions, skip that alias", and a booted
   instance holds an enrollment token and no API credentials, so it cannot
   know what names are already claimed. Nothing in the boot script can honour
   the rule. This is therefore a POST-LAUNCH reconciliation, and every piece
   it needs already exists: the values come back with the instance itself
   (`describe_instances` returns `InstanceId` and `PrivateDnsName` -- see
   `_running_instance`, `aws_runtime_builders.py:108`), the claimed-name set
   comes from §55's resource-group servers path (the one that answers 200),
   and the write is `run_session_command`
   (`builder_base_runtime.py:60`; SSM on AWS, IAP ssh on GCE) appending
   `AltNames` and restarting sftd -- the same post-launch shape
   `verify_instance.py:123` already uses. **Depends on §55**: it needs that
   stage's OPA client and its hook, and it is worth nothing until stale
   records stop accumulating.
4. **The two aliases are not symmetric, and the skip rule is the DEFAULT,
   not a fallback.** An AWS instance id is globally unique and never reused,
   so a genuine collision is impossible -- a duplicate there means a stale
   record of the same machine, which is §55's problem and not this one. The
   IP-derived name is the opposite: private addresses are recycled inside the
   VPC constantly and stale records keep them (the `asa-enrollment-routing`
   note records exactly that). And the ranking makes a collision actively
   harmful rather than merely useless: a stale record's Hostname is rank 3
   while our alias is rank 4, so the name either resolves to a dead machine
   or, per the same page, "resolves to more than one server" and "the client
   will return an error to avoid inadvertently connecting to an unintended
   server". A colliding alias breaks resolution for BOTH servers. Skip on any
   match -- against a registered canonical name, hostname or alt name, and
   against any name the configuration itself declares -- and say which alias
   was skipped and why. Silence here is how the operator ends up debugging an
   ambiguity error.
5. **A runtime contract pair, not an AWS special case.** Same shape as the
   existing gate (`can_query_instance_boot_image` /
   `query_instance_boot_image`, `builder_base_runtime.py:142`):
   `can_query_instance_identity()` and `query_instance_identity(name)`
   returning the provider id and the provider hostname, or None. AWS fills
   both from the dict `_running_instance` already returns; GCE from its
   instance get (`<name>.c.<project>.internal`, numeric id). A runtime that
   cannot answer makes no claim and its instances get no aliases -- no
   provider-specific branching at the call site. §57 landed this convention
   first (2026-09-21) -- FOLLOW IT rather than inventing a parallel one:
   a `can_x()` predicate gating an `x()` that returns None for "this runtime
   cannot answer", the provider's own spellings mapped inside the plugin
   onto a vocabulary `base` owns, and None never read as a value. The
   identity hook is the same shape with a different payload; note that the
   AWS side can reuse `_named_instance` (added by §57), which sees a machine
   whatever its power state, rather than `_running_instance`, which cannot
   see one that is switched off.
6. **These values do NOT belong in the launch parameters.** Launch
   parameters are the immutable record of what the machine booted with,
   compared against the declaration; an alias is discovered from the
   provider AFTER boot and is not declared anywhere, so recording it there
   would read as drift on every comparison, forever. It belongs with the
   state query, beside the OPA registration it describes.
7. Records: OPERATIONS on what an instance answers to and why an alias is
   sometimes refused -- including the fact that the system takes the
   provider hostname away at boot, which is why the alias has to be given
   back deliberately. Feature branch `feature/provider-name-aliases`,
   squash-merged, kept.

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
   at 3am when it is the next one up.
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

## 60. An instance has generations, and each one is a machine

**Why**: the system already controls WHETHER a machine may be replaced --
`validate_immutability` (`launch_params.py:376`) refuses a launched instance
whose parameters changed and names the keys, and the three sanctioned exits
(an explicit `upgrade`, a policy follow, decommission and redeclare) are each
an exemption in that check. What it does not have is any identity for the
machine that RESULTS. `launch-params.yaml` is keyed by instance name and
holds exactly one record per name, overwritten on every relaunch; no EC2
instance id appears anywhere in meta-state; the verification record names the
image, never the machine. So "which machine is this, and what happened to the
one before it" is answerable only by parsing `pins.yaml.upgrades` and
guessing.

The cost of that gap is already paid, three times over, in the stages around
this one. §55 exists because three `coops-model` registrations piled up in
OPA -- nothing knew a SECOND MACHINE had happened, so nothing retired the
first. §58 has to reach into the cloud to discover a provider identity the
system never kept. §59's spend-once name pool is a generation counter spelled
with words. One concept underneath would serve all three.

Storage already has it: `record_storage_transition` bumps a `generation` on
every regeneration (`meta_state.py:205`) and `storage_generation`
(`meta_state.py:217`) reads it back. A storage knows it is on generation 3.
`coops-model` does not know it is the fourth machine of that name. Give
instances the same thing, in the same words, so the two read alike.

1. **A generation is one machine, and the machine decides -- not our
   bookkeeping.** It begins when a machine is created and ends when THAT
   machine is destroyed. The tempting signal is control flow (bump when
   `mark_launched` flips `launched` to true, or when a pending replacement
   clears) and it is the wrong one: it infers a new machine from our own
   records, and the entire failure this stage addresses is records that did
   not know a new machine had happened. Define it by OBSERVATION instead --
   the provider instance id differs from the recorded one, via §58's
   `query_instance_identity` -- so a machine replaced out of band (a taint, a
   manual terminate and re-apply, a console delete) is caught. Keep the
   control-flow signal only as the fallback for a runtime that cannot answer,
   and mark a generation recorded that way as inferred, not observed.
   **Depends on §58** for the hook.
2. **What is NOT a new generation.** A reboot. A stop and start (§57 -- the
   power state is the operator's and a stopped machine is the same machine;
   this is the trap, because a stopped instance may also fail an identity
   query, and "cannot read the id" must never be treated as "the id
   changed"). A mount detach, which is the one in-place change immutability
   allows (`launch_params.py:359`). An image pin that has moved but not been
   applied. Only a new machine is a new generation.
3. **Two counters, not one** (operator decision, 2026-09-21): a durable
   count and an ephemeral count per instance, bumped according to that
   generation's own `ephemeral` flag. §55 builds the canonical name from the
   DURABLE one, so a standing machine's number never advances because a
   throwaway was spun up.

   Be honest about what the split buys, because it is less than it looks.
   Counters are per DECLARED INSTANCE NAME, so the isolation is mostly
   already there: `gce-test` churning cannot touch `coops-model`'s number --
   they are different declarations. The split covers exactly one case, a
   single name whose declaration flipped `ephemeral` between generations,
   which is rare and already gated (`ephemeral` is a compared launch
   parameter, so flipping it forces a replacement). It is one dict key
   instead of an int; do it for correctness, not for leverage.

4. **Its own file, for a reason worth writing down.** Follow the storage
   shape: `launch-params.yaml` keeps holding what the CURRENT machine booted
   with, and a new `meta-state/instance-state.yaml` holds the generation, the
   lifecycle transitions, the provider identity, and the superseded parameter
   sets -- exactly as `storage.yaml` and `storage-state.yaml` divide today.
   Do NOT put the counter in the launch-params record itself: `_comparable`
   filters by key (`launch_params.py:356`), so a `generation` that changes
   would read as a changed launch parameter and refuse the very replacement
   that bumped it, unless it were added to `_VOLATILE` -- at which point it
   is excluded from every comparison and the file is carrying a field it
   never compares. Separate files, separate jobs.
5. **Archive, never overwrite.** When a generation ends, its launch-params
   record moves into the ledger with its number, the run that created it, the
   run that ended it, why it ended, and the provider identity if it was ever
   known. Growth is per MACHINE, not per run -- `coops-model` managed four in
   two days of unusually heavy work, which is nothing next to `runs.yaml` at
   58KB -- so keep it complete and do not cap it.
6. **Ephemerals get generations too.** `forget_ephemerals`
   (`launch_params.py:296`) currently deletes the launch record outright, on
   the reasoning that the machine is gone. But it EXISTED: it booted, it
   enrolled in OPA, and it may well have left a registration behind -- which
   is §55's problem arriving by the one path that erases its own evidence. An
   ephemeral machine opens and closes a generation within the run, and the
   record of that is what lets §55 deregister it honestly.
7. **What it buys the stages around it.** §55 stops searching by name and
   guessing: retiring a registration becomes "generation N ended, deregister
   the server generation N enrolled". §58's provider id and hostname become
   per-generation facts rather than things rediscovered each time. §59's
   drawn name is recorded ON the generation, so "what was iteration 3 called"
   has an answer. §19's step 5 upgrade path gets something concrete to mean.
8. **Do not fabricate the past.** What stands now becomes generation 1,
   marked as the first RECORDED generation, not the first machine. The
   earlier `coops-model` machines are visible only in `pins.yaml.upgrades`
   and stay there; backfilling a history the system never observed would put
   invented facts in the one file meant to be trustworthy.
9. Records: OPERATIONS on what a generation is, what does and does not start
   one, and how to read the ledger; DESIGN on why observation beats inference
   here. The word is `generation`, matching storage, even though the
   operator said "iteration" -- one word for one concept across both. Feature
   branch `feature/instance-generations`, squash-merged, kept.

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
