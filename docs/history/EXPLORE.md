> **Frozen record.** This document is history, kept verbatim as it was when frozen; nothing in it describes the present. Current documentation starts at [README.md](../../README.md).

# V2 Exploration

This document is meant to capture some additional exploration work within the V2 lifecycle work before it is accepted into the mainline.

## Rules

1. Any plans generated for "Exploration Items" in this document should be noted under the explored item one heading level deeper than the item heading.  This is to ensure that the exploration work is documented alongside its item and can be reviewed easily.
2. For any actual work on item in this document, branch off the current v2-lifecycles branch for the exploration attempt, and if it doesn't pan out, ask if we should discard that work.  Keep track of the work in a local-only branch.  Each item should be a separate branch, and the branch name should be prefixed with `v2-explore-` (e.g., `v2-explore-opa-gid-source`).
3. None of the exploration work should be pushed to the remote repository unless explicitly stated.
4. All exploration work should be documented in this file under the item explored as with #1 above, including the purpose, approach, plan, and any findings.  For example, exploration on "More Targeted Updates" should be documented under the heading "### More Targeted Updates?" with a subheading for the exploration work, a possible subheading for the approach, a subheading for the plan, and a subheading for findings.  This is to ensure that the exploration work is documented alongside its item and can be reviewed easily.
5. This file will be used to advise and/or update [GOALS.md](GOALS.md) and [docs/DESIGN.md](docs/DESIGN.md) as needed.  If any of the exploration work is successful, it should be incorporated into those files and the exploration branch should be merged into v2-lifecycles.

## Notes

### Systemic Purpose

This system is meant to support transitions of the execution of HPC data models to the cloud.  Building the correct image for a given model can be challenging, and ensuring that the relevant configuration of a base OS is correct can be even more challenging.  The system is meant to support the creation of images and instances that are correct for a given model, and to support the transition of those models to the cloud.

To this end, the debugging activity of an image is actually a very important part of the system.  The system should support the ability to debug an image, and to support the ability to debug an instance that is running in the cloud.  The system should also support the ability to debug a model that is running in the cloud.  I expect that this just means "stand up the image as an instance and let someone log in", but it would be nice if the system could support a more sophisticated debugging workflow.  This is one of the areas that I want to explore.

The system should also support the ability to formally release images that are known to be correct for a given model.  This is important because it allows the system to support the transition of models to the cloud in a controlled manner.  This is another area that I want to explore.

## Exploration Items

These are some specific things that I want to explore in the context of V2 lifecycles.  Some of these may be dead ends, but I want to explore them anyway.  Some may necessictate new lifecycles or new paths of execution, but that is okay.  The goal is to explore the space of possibilities and to document the findings.

### More Targeted Updates?

One modification that generally gets performed is "update this OS to the latest revision of all it's packages (the "dnf -y update" command for RedHat OS Family, for instance).

This modification is heavy-handed and can often break underlying things.

What would be a way to produce more targetd updates?  Especially important would be security-patches, but also important would be updates to specific packages that are known to be important for a given model. 

### Locally Installing Modifications

Another area is that a way to debug an image might be to ensure that all modifications were items that were installed locally and could be re-run (assuming idempotence). This would allow for a more targeted debugging workflow, and would allow for a more targeted update workflow.

### More Streamlined Plugin Development

Several items within /packages are libraries.  These were mostly hand-crafted and often had cruft left around from the original development.  It would be nice to have a more streamlined way to develop plugins, and to have a more streamlined way to develop libraries. 

### Automated Testing for Modifications

It would be beneficial to have automated tests for modifications to ensure they work as expected and do not introduce regressions. This could include unit tests for individual modifications as well as integration tests for the overall system.

### Automated Testing for Image Builds

It would be beneficial to have automated tests for image builds to ensure that images are built correctly and consistently. This could include tests that verify the presence of expected files, the correct configuration of services, and the successful execution of key workflows within the image.

### User and Group Management

Currently, the target is read-only user management and only have group-membership management.  It would be beneficial to have a more complete user and group management system that allows for the creation, modification, and deletion of users and groups. This could include support for managing user attributes, group memberships, and access controls. Ensuring that we could treat read-only-managed groups and users the same way we treat managed groups and users would be important.

### Possible Other Infra-as-Code tools

Tofu is the current tool for managing infrastructure as code, and its state file system is considered the downstream source-of-truth for subsequent builds.  But it would be beneficial to explore other tools that may offer different features or capabilities. This could include tools like Terraform, Ansible, or Pulumi. Exploring these tools could provide insights into different approaches to infrastructure management and potentially lead to improvements in our current system. 

### Generation of Idempoent Script-based Modifications

Generating idempotent script-based modifications would ensure that scripts can be safely re-applied without causing unintended side effects. This could involve creating scripts that check the current state before making changes and only apply modifications if necessary. I am unsure where this lives or where it would fit.

### Expanding What Else Plugins Could Do

What sort of actions could plugins perform for the system?

### Using Systemic State For Additional Actions and Decisions and Debugging

Systemic state, which is the state of the system as a whole, could be used to make additional decisions and perform additional actions.  This could include using systemic state to determine if certain actions should be taken, or to provide additional context for debugging.  Currently, the state of the system is the committed generated and updated code, and the state that Tofu captures.  Other state could be determined by adding a "Query this plugin/providers's state" call, that would let us see what the current state of that plugin/provider is.  This could be used to make decisions about what actions to take, or to provide additional context for debugging.  

An example might be querying the identity system for all the information we could know about it aside from the TF statefile.  Another example might be querying the storage system for some metadata that WE WROTE DURING STORAGE CREATION, so we could ensure that a given storage was being used in accordance with the original intent.  Another example might be querying the image store for actual images, using metadata tagging methods, so that we could determine if the image stores were modified (eg. images deleted or poossibly renamed) outside of the system.

### Existing Systemic State Migration

We might need to see if we should or can migrate existing systemic state into the new system.  This could include migrating existing images, storage, and identity information into the new system.  

<!-- ===================================================================== -->
<!-- Exploration notes added 2026-08-27 (investigation only; no code changed, -->
<!-- no branches cut yet -- see "How To Proceed"). Each item's notes sit one   -->
<!-- heading level below the item, per Rule 1.                                -->
<!-- ===================================================================== -->

### More Targeted Updates? — exploration

#### Findings (code as of `feature/v2-lifecycles`)

- Today's "update" is the OS plugin's `get_command_to_update()`
  (`default-os-plugin/rhel_type.py`: `dnf clean all; dnf -y update; dnf -y
  upgrade; dnf -y autoremove; dnf -y autoclean`), applied as one shell
  provisioner on a **base** image only when its runtime subconfig says
  `auto_update: true`. It is all-or-nothing and unrecorded beyond the
  build's `csis_fingerprint`.
- Nothing distinguishes "security" from "everything"; nothing pins package
  versions; nothing records what the update actually changed (the package
  delta is only visible inside the packer log).
- The lineage record (gate 6) already carries per-build `mods` with content
  hashes — the natural place to record an *update policy* and its result.

#### Approach

Make "update" a first-class, declarative **update policy** owned by the OS
plugin, instead of a boolean:

```yaml
os_builders:
  - name: basic-rhel-8
    update:
      policy: security          # none | security | packages | full
      packages: [openssl, kernel]   # policy=packages (or additions to security)
      exclude: [kernel*]        # never touch these
      pin: {glibc: "2.28-236"}  # explicit versions (recorded, reproducible)
```

The OS plugin translates the policy into family-specific commands:
`dnf -y update --security` / `dnf -y update <pkgs>` / `dnf versionlock`
(RHEL), `apt-get install --only-upgrade` + `unattended-upgrades` security
lists (Debian). The provisioner also emits a **post-update manifest** step
(`rpm -qa --qf ... > /var/lib/csis/packages.txt` or `dpkg-query`) so the
package set of the build is known.

#### Plan (branch `v2-explore-targeted-updates`)

1. Add `UpdatePolicy` model (`base/models/update_policy.py`) and an
   `update: UpdatePolicy` field on `OsBuilderModel`, with `auto_update: true`
   kept as an alias for `policy: full` (deprecation warning).
2. `OsBuilderBase.generate_items_for_os_update` consumes the policy; the
   RHEL/Debian plugins implement `commands_for_policy(policy)`.
3. Include the policy in `input_fingerprint` and record it in
   `lineage.yaml` under `update:`; a follow-up records the package manifest
   (see "Automated Testing for Image Builds").
4. Tests: golden emission per policy; unit tests per family.
5. Open question for the stakeholder: should `security` be the DEFAULT for
   base images (safer) or `none` (reproducible)?

#### Findings from execution (branch `feature/v2-explore-targeted-updates`, 2026-08-27)

- **Done.** `update:` on an OS builder declares `policy: none | security
  | packages | full` with `packages`, `exclude` and `pin` (`auto_update:
  true` is now literally an alias for `policy: full`). The dnf family
  realizes it (`dnf -y update --security`, `--exclude=`, per-package
  updates, `versionlock` for pins; RHEL's subscription-manager repo setup
  is a separate hook reused by every policy) and the apt family likewise
  (`apt-mark hold` around the run, security-suite-only upgrades,
  `--only-upgrade`, pinned `pkg=ver` + hold). Every update ends by writing
  `/var/lib/csis/packages.txt` (rpm/dpkg manifest). The policy is part of
  the build's input fingerprint and its lineage record; invalid policies
  are hard validation failures.
- **Decision 2026-08-27:** the default stays `none` (reproducible);
  `security` is opt-in per base image.
- Scope kept deliberately: updates stay a **base-image** concern (instance
  images bake "the same base, refreshed modifications", N17). The
  stakeholder question stands: should `security` be the default for base
  images (safer) or `none` (reproducible)? The code defaults to `none`.
- Limits: apt's "security only" is a heuristic over `dist-upgrade -s`
  output (`unattended-upgrades` is the robust tool and could be a later
  realization); the package manifest is recorded on the image, not yet
  copied back into lineage (a post-bake step, same shape as the image
  tests' post-bake layer).
- Evidence: `tests/test_v2_explore_targeted_updates.py`; `just verify`
  339; golden regenerated (fixture: `basic-rhel-8` uses
  `security + openssl, exclude kernel*`).

### Locally Installing Modifications — exploration

#### Findings

- Modifications are already staged locally beside the packer root (gate 8:
  playbooks and script files are copied into `generated/<lc>/<builder>/
  image-generation/block-NNN/`), but they are *consumed by packer from the
  build host*; nothing lands on the image itself for re-running.
- Bash inline lines and ansible playbooks are both executed exactly once at
  bake; there is no on-image copy and no idempotence contract.

#### Approach

Bake a **modification bundle** onto every image: `/opt/csis/mods/<n>-<name>/`
containing the playbook or script, a `run.sh` wrapper, and a `MANIFEST.yaml`
(name, type, content hash, run id — the same record lineage keeps). A tiny
on-image runner (`csis-mods rerun [name]`) re-applies them in order. Then
"debug an image" = stand it up, `csis-mods rerun`, inspect. This is the
concrete mechanism that "Generation of Idempotent Script-based
Modifications" needs, and it doubles as an audit trail on the machine.

#### Plan (branch `v2-explore-local-mods`)

1. In the packer builder, after the mod provisioners, emit a `file`
   provisioner uploading the block's staged mod assets to `/opt/csis/mods`
   plus a generated `MANIFEST.yaml` from `lineage.mod_records`.
2. Ship `csis-mods` as a small POSIX shell script (no Python on the image);
   ansible mods re-run via `ansible-playbook` if present, else are reported
   as "not re-runnable here".
3. Record `local_mods: true` in the lineage build record.
4. Tests: golden emission; a unit test that the manifest equals the lineage
   record.

#### Findings from execution (branch `feature/v2-explore-local-mods`, 2026-08-27)

- **Done.** Every instance-image bake now stages a bundle beside the packer
  root (`csis-mods/<image>/NN-<mod>/` with the playbook/script files, an
  `inline.sh`, a `run.sh` wrapper and a `MANIFEST.yaml` equal to the lineage
  mod record) and installs it at `/opt/csis/mods` with a POSIX runner
  `csis-mods list | rerun [name]`, via a `file` + `shell` provisioner after
  the image's mods and activation. Real `packer validate` accepted it.
- Idempotent script generation is folded in: a bash mod may declare
  `ensure: {packages, files, services, commands: [{run, unless}]}` and the
  plugin generates guarded shell (query-before-install, cmp-before-replace,
  is-enabled/is-active, `unless` checks). Lineage records `idempotent:
  ansible | declared | unknown` per mod and `local_mods: true` per build.
- Limits found: (1) the bundle holds THIS bake's mods only — a chained
  image's parent bakes are in lineage, not on disk; (2) ansible re-runs
  need `ansible-playbook` on the image (the wrapper says so and exits 3
  otherwise) — a real debugging workflow would bake it into base images
  that declare it (a candidate `tooling:` declaration, like storage types);
  (3) `ensure.packages` is generic across rpm/dpkg but naive — a per-family
  hook on the OS plugin would be cleaner.
- Evidence: `tests/test_v2_explore_local_mods.py`; `just verify` 338;
  golden regenerated (the bundle files are part of the pinned emission).

### Google Compute Platform (GCP) Support — exploration

#### Findings

- `gcloud-runtime-plugin` has the runtime model, network validation
  (`gcp_utils.py`, 573 lines) and a vendor image query; **no** GCP image
  builder (packer `googlecompute`), storage plugin, instance plugin, or
  session mechanism exists. The fixture's `gcloud-east1` runtime is inert.
- Everything V2 built is plugin-shaped on purpose: capability types
  (`storage_types`), prerequisites, session mechanism, launch params and
  lineage are all per-plugin hooks with AWS as the only implementation.
  GCP is therefore mostly *breadth*, not new architecture — with one real
  gap: the packer source type is hard-coded to `amazon-ebs` in several
  places (`get_packer_source_type`, `only = ["amazon-ebs.<img>"]` in the
  V2 provisioner helpers and the mod builders), and `image_to_source` casts
  the runtime model to `AwsCloudBuilderModel`.

#### Approach

Do it in three increments, each shippable: images → storage/instances →
identity/session parity.

#### Plan (branch `v2-explore-gcp`)

1. **Make the packer builder provider-neutral**: `get_packer_source_type()`
   drives every `only = [...]` (mod builders, V2 provisioners), and
   `image_to_source` dispatches source-block generation to the runtime
   plugin (`RuntimeBuilderBase.packer_source_args(image, subconfig)`).
2. `packer-gce` image builder in the gcloud plugin (`googlecompute` source,
   `image_family` as the series, labels as lineage tags — GCE labels are
   lowercase/limited, so define the label mapping once).
3. `tf-gcp-pd` (single-attach) and `tf-gcp-filestore` (many) storage
   plugins + `tf-gce` instance plugin, reusing the gid-by-reference and
   launch-param machinery; session mechanism = OS Login / IAP
   (`session_mechanism: iap`).
4. Fixture: a second, GCP-only frozen fixture so the golden
   for AWS stays untouched; gate tests per increment.
5. Azure and Docker follow the same shape later; Docker needs a different
   *artifact* notion (image digest, not AMI) — flag that lineage's
   `build_id` must stay an opaque string.

#### Findings from execution (branch `feature/v2-explore-gcp`, 2026-08-27)

- **Increments 1 and 2 done; 3 (storage/instances/session) not started.**
  The packer builder is provider-neutral: the runtime plugin now owns
  `packer_source_type()`, `packer_source_blocks(...)` (the whole
  `source` block plus any data lookups) and `build_id_from_artifact()`
  (the manifest's `artifact_id` -> lineage build id). `amazon-ebs` moved
  verbatim into `aws_runtime/aws_packer_source.py`; every `only = [...]`
  (OS update, bash/ansible mods, V2 provisioners) goes through
  `ImageBuilderBase.build_target_label(image)` and nothing outside the AWS
  plugin spells `amazon-ebs` any more. `type: packer-gce` binds the same
  builder body to a GCE runtime, whose `googlecompute` source
  (`gcloud_runtime/gcp_packer_source.py`) maps csis tags to GCE labels once
  (`gce_name`/`gce_label`: lowercase, `[a-z0-9_-]`, 63 chars).
- **GCE image families are native series.** The bake sets `image_family`
  to the csis series, so a deferred parent is `source_image_family =
  <series>` -- GCE resolves "latest build of the series" itself; no
  name-pattern query. A pinned parent is `source_image = <build id>` (the
  build id *is* the image name). This is neater than the AWS name-pattern
  lookup and worth copying back as an AWS *tag* filter (`csis_series`).
- **Two architectural findings the plan did not see:**
  1. *One image, one image builder* was an invariant (`image_builder`
     setter raised on a second assignment; items attach to their `type`
     builder only). A base image on AWS *and* GCE broke it at once. Relaxed:
     the first builder stays primary, others are `extra_image_builders`;
     `_attach_image` also attaches an image to builders its `runtimes` name
     **on a different runtime** (same-runtime extras still ignored, so the
     AWS golden is byte-identical). `predefined_resolve` now resolves the
     vendor image *per runtime* and generates **one** BaseImage whose
     subconfigs each carry their own vendor image -- previously the second
     runtime overwrote the first's `image_identifier` on every subconfig.
  2. *Lineage pins are keyed by image name, not (image, runtime).*
     `pinned_parent_build(image)` would hand the GCE bake an AMI id. Not
     fixed here (dry runs never pin); the fix is to key `pins.images` /
     `pins.instances` by `<name>@<runtime>` and record `runtime` in the
     pin, which `lineage.yaml` already stores per build. **Do this before
     any second runtime is used for real.**
- Also seen: base-image capability prerequisites are per base image, not
  per runtime -- the GCE bake of `basic-rhel-8` installs `amazon-efs-utils`
  and the AWS CLI because the base declares `storage_types: [ebs, efs, s3]`.
  Increment 3 should filter prerequisites by the storage plugins that
  exist on the bake's runtime (or make `storage_types` per-runtime).
- **Decision 2026-08-27: a real GCP target is in sight** -- increment 3
  (per-runtime prerequisites, `tf-gcp-pd`, `tf-gcp-filestore`, `tf-gce`,
  `iap` session, state-query parity, a GCE golden) is planned in
  [PLAN.md](PLAN.md) "GCP increment 3"; not started.
- Not done: `packer-plugin` still lists the AWS plugin as a dependency
  (only the pyproject line remains; no import), GCP storage/instance/session
  plugins, the second fixture tree (a temp overlay in the test replaced it).
- Evidence: `tests/test_v2_explore_gcp.py` (source type ownership, GCE
  base bake with labels/family, instance bake from the family with
  ansible+bash+activation targeting `googlecompute.*`, AWS bake untouched);
  golden + gate tests unchanged; `just verify` 337.

### More Streamlined Plugin Development — exploration

#### Findings

- The pattern is real but heavy: every plugin repeats `main.py`
  (`AbstractPluginMetadata` with three parallel dicts), `csis_name`/
  `csis_classifier` on both model and builder, an entry point in
  `pyproject.toml`, and a `pythonpath`/`testpaths`/`extraPaths` line in the
  ROOT pyproject (three places to edit per plugin).
- `docs/example-plugin/plugin-b` exists but nothing checks it still works.
- Cruft is mostly commented-out history in the older builders
  (`packer_ebs_builder.image_to_source` carries ~90 lines of dead code) and
  duplicated tofu command sequences that `TerraformRootMixin` was created
  to remove but not every builder uses yet.

#### Plan (branch `v2-explore-plugin-dx`)

1. `cs-image-system plugin new <name> --kind storage|identity|runtime|mod|image`
   scaffolds a package from a template (model, builder, main, test, entry
   point) and patches the root pyproject lists.
2. A `PluginMetadata.from_pairs([(Model, Builder), ...])` helper so `main.py`
   is one expression; keep the old constructor.
3. Move the remaining tofu builders onto `TerraformRootMixin`; delete the
   dead code in `image_to_source`; add a `just plugin-check` that builds the
   example plugin and runs its tests (so the template never rots).
4. Ruff: turn on `E`/`I` (import order) and `F841` now that V2 stabilized —
   small, mechanical, but do it as its own commit.

### Automated Testing for Modifications — exploration

#### Findings

- Today a modification is tested only by a real packer build. Nothing runs
  playbooks or scripts locally, and nothing checks that a mod is idempotent.
- Gate 8 gives every mod a content hash and a staged copy; that staged copy
  is exactly what a local test harness needs.

#### Approach

A `test-mods` lifecycle-adjacent command (not a lifecycle: it produces no
IaC) that runs each mod against a **throwaway local target** matching the
image's OS family: a container (`podman run rhel/ubi8`) for RHEL/Debian.
Ansible runs with the `docker`/`podman` connection; bash mods run inside
the container. Two assertions per mod: (a) exit 0, (b) **idempotent** — a
second run reports no changes (ansible `changed=0`; for bash, the script
must be written so a second run exits 0 and a `--check` mode, if declared,
reports nothing).

#### Plan (branch `v2-explore-mod-tests`)

1. `ModBuilderBase.test_locally(mod, target) -> TestResult` hook; ansible
   and bash implementations.
2. `cs-image-system test-mods [--image X]` + `just test-mods`; results
   recorded in `meta-state/mod-tests.yaml` keyed by content hash so an
   unchanged mod is not re-tested.
3. CI: runs only when podman is available; otherwise skips loudly.
4. Ties to the next two items: the same harness runs the image tests.

#### Findings from execution (branch `feature/v2-explore-mod-tests`, 2026-08-27)

- **Done and proven live.** `cs-image-system test-mods [--image X]
  [--force] [--strict]` (`just test-mods`) runs every modification of an
  instance image against a throwaway **docker** container standing in for
  the root OS (`rockylinux:8` for `basic-rhel-8`, `debian:11` for
  `my-deb-11`; overridable with `local_test_image` on the OS builder),
  twice: run 1 must exit 0; run 2 must leave the container's filesystem
  diff unchanged (volatile paths ignored) and, for ansible, report
  `changed=0`. Results are cached in `meta-state/mod-tests.yaml` by
  content hash (unchanged mods are not re-tested).
- Live result for `imgfile-basic-dask`: `dask-setup-jeffy` (ansible via
  the docker connection) **pass, idempotent**; `derivative-setup` (bash:
  `ensure` + inline + `mod_image.sh`) **pass, idempotent**.
- Three target-prep facts the harness now handles, each found by a real
  run: bare containers have no `sudo` (an option-aware shim is installed —
  ansible's become calls `sudo -H -S -n -u root`); no Python for ansible
  modules; and RHEL-8's default `python3` is 3.6, which ansible-core 2.21
  rejects — the prep installs the newest `python3.x` the family offers and
  passes `ansible_python_interpreter`. All of this is test-target
  plumbing: real images get their Python from the OS.
- Limits: the harness proves *apply + idempotence in a container*, not
  kernel/cloud-dependent behaviour (systemd services are not running in
  the container; `ensure.services` lines are no-ops there). Docker-less CI
  reports `skipped` (exit 0) unless `--strict`.
- Evidence: `tests/test_v2_explore_mod_tests.py` (fake target; a live
  docker test behind `CSIS_DOCKER_TESTS=1`); `just verify` 338 + 1 skipped.

### Automated Testing for Image Builds — exploration

#### Findings

- The V1 `test`/`verify` lifecycle phases are stubs (now explicit no-ops in
  the V2 CLI). Packer only proves "the build finished".
- Lineage records give each build a stable identity to attach test results
  to; the base image's capability declaration says what MUST be present
  (sftd for `okta`, efs-utils for `efs`, the admin user, the SSM agent).

#### Approach

Two layers: (1) **in-bake checks** — a final packer shell provisioner that
asserts the declared capabilities (binaries, services, users) and fails the
build if any is missing; derived automatically from the same plugin hooks
that bake them (each `base_image_prerequisites` gains a `verify_commands`
sibling); (2) **post-bake tests** — stand the build up (ephemeral instance,
or a container for the parts that do not need a kernel) and run a test
suite (goss/testinfra-style YAML: files, services, ports, commands),
declared per image under `tests:`; results stored in
`meta-state/image-tests.yaml` keyed by build id and required by a **release**
(see "How To Proceed").

#### Plan (branch `v2-explore-image-tests`)

1. `verify_commands()` on group/storage/runtime plugins + the admin-user
   check; emitted as the last provisioner of every base and instance image.
2. `tests:` on images (goss-style YAML, kept in the config repo); a
   `cs-image-system test-image <build>` command that launches an ephemeral
   instance from the build (gated like any apply), runs the suite over the
   session mechanism, tears down, records the result.
3. Release gate: `cs-image-system release <image> --build <id>` refuses
   without a green test record (ties to "Systemic Purpose": formal releases).

#### Findings from execution (branch `feature/v2-explore-image-tests`, stacked on `v2-explore-plugin-hooks`, 2026-08-27)

- **In-bake verification, done.** Every image's bake now ends with a
  verification provisioner (`set -e` + assertions): the admin user and
  its key bodies, every declared identity/storage type's
  `verify_commands` (paired with the `base_image_prerequisites` that bake
  them: sftd present *and dormant*, EFS mount tooling, AWS CLI), the
  runtime's `session_verify_commands` (SSM agent), the owning group's
  `activation_verify_commands` on instance images, plus a declared
  goss-style `tests:` map (`files`/`packages`/`commands`/`services_enabled`/
  `users`) on images and OS builders, validated at generation. A failing
  assertion fails the bake, so a build recorded in lineage has passed it;
  lineage stores `tests: {in_bake: true, assertions: N}`.
- **The `release` lifecycle, done** (the item this document was missing):
  registered by base after `instance-image` through the plugin-hooks
  mechanism, so it is proven as the first real registered lifecycle.
  `cs-image-system release <image> --build <id> --model <m>` records a
  release in `meta-state/releases.yaml` (history + current build per
  model) and refuses builds that are not in lineage, wrong-series,
  unverified, or whose modifications have a failed/non-idempotent local
  mod test (`require_mod_tests` makes a *missing* result a refusal too).
  The lifecycle's runner tags released artifacts (AWS: `ec2 create-tags`)
  only under `apply_release`; `require_released_builds` makes an instance
  pin to an unreleased build a validation failure.
- Not done (deliberately): the post-bake layer — launching an ephemeral
  instance to run tests over the session mechanism. It is an *apply* and
  must ride the same gate/`apply_*` discipline; design it as a `test-image`
  command once a real instance apply has happened at least once.
- Lesson: registering a real lifecycle shifted every "exactly four
  lifecycles" assumption in the gate tests — small, mechanical, and a
  sign the registrable design works.
- Evidence: `tests/test_v2_explore_image_tests.py`; `just verify` 344;
  golden regenerated. Merge order: `plugin-hooks` first, then this.

### User and Group Management — exploration

#### Findings

- Identity is: users read-only (`okta-tf-ro`, `data "okta_user"`), OPA
  groups/policies/membership managed (`okta-tf`), the managed-user builder
  mothballed (docs/LEDGER.md "Kept on purpose"). V2 added `identity_type`,
  `gid_policy`, `unmanaged`, and the read-model; nothing about user
  attributes, and "read-only" vs "managed" is a *builder type*, not a
  per-item setting.
- The OPA Attributes API (found for the gid shim) also carries
  `unix_group_name`, and user attributes (`unix_uid`, shell, home) live under
  `/users/{user}/attributes` — the system never reads or writes them.
- The stated goal — treat read-only and managed items uniformly — is already
  the shape of the group side (`unmanaged: true` on a managed item).

#### Approach

One identity model with a per-item **management mode** instead of two
builder types: `managed: true|false` on users AND groups (default per
builder), where read-only items emit lookups and managed items emit
resources; attributes (`gid`, `unix_group_name`, `uid`, `shell`) become
declarable and, for managed items, applied through the Attributes API (a
new resource-shaped step in the identity runner: `cs-image-system identity
apply-attributes`, since the oktapam provider lacks them). Deletion stays
forbidden by policy (N19): "unmanage", never destroy.

#### Plan (branch `v2-explore-identity-mgmt`)

1. Schema: `managed:` on `User`/`Group`; `attributes:` map validated per
   plugin; the RO user builder and the managed user builder collapse into
   one builder with two emission paths (keep type names as aliases).
2. Attribute application as a plugin transition action, read-only probed
   first (the shim's client already authenticates).
3. Validation: attribute conflicts (the `/attributes/conflicts` endpoint)
   are a hard failure at generation.
4. This is the largest item and touches live Okta; do it last, behind a
   `apply_identity` flag as today, and only after the stakeholder confirms
   Q7's "may reappear" has become "should".

#### Findings from execution (branch `feature/v2-explore-identity-mgmt`, 2026-08-27)

- **Steps 1-3 done; step 4 (writing) deliberately not.** `managed:` is a
  per-user setting (`None` = the builder's default: `okta-tf` managed,
  `okta-tf-ro` lookup-only); the two builders are one emission path chosen
  per item (`resource "okta_user"` + dependent lookup vs. eager lookup),
  and the read-only type refuses an explicit `managed: true` rather than
  quietly upgrading. Groups already had `unmanaged:`; both gained
  `attributes:`. The okta plugin validates names/types against what the
  OPA Attributes API actually holds (groups: `unix_gid`,
  `unix_group_name`, `windows_group_name`; users: `unix_uid`, `unix_gid`,
  `unix_user_name`, `windows_user_name`), ids below 1024 refused.
- **Plan / probe / apply are a separate, resource-shaped path** because
  the terraform providers cannot carry attributes: the identity lifecycle
  writes `generated/identity/attributes-plan.json` (only when something is
  declared -- a plain configuration generates byte-identically) and the
  identity runner gains one deferred step, `cs-image-system
  identity-attributes --probe --dry-run-apply`. `--apply` exists so the
  shape is complete but raises `AttributeApplyDisabled`; **no code path
  writes to Okta or OPA**, and the fake-transport tests assert the probe
  issues only GETs.
- **Verified read-only against the live team (2026-08-27):**
  `GET /users/{user}/attributes` (unix_uid 150006 for avery.alpha, each
  attribute carrying OPA's own `managed` flag -- `true` = admin-set,
  `false` = OPA-generated, exactly the distinction a declared attribute
  makes), `GET /users/{user}`, `GET /users`, and
  `GET /attributes/conflicts` (`{"list": []}`). A live `identity-attributes
  --probe --dry-run-apply` on a fixture copy declaring the real values
  answered "attributes already match". The identity `run` itself failed
  at `tofu init` in that shell (no AWS credentials in the default profile
  for the S3 backend) -- environmental, unrelated to this change.
- Open before step 4: Q7 confirmation; the write verb and its response
  shape (`PUT .../attributes/{id}`? the conflicts endpoint suggests OPA
  validates uniqueness server-side); whether a declared `unix_gid` should
  also pin the group builder's `gid_policy` (today they are independent).
- Evidence: `tests/test_v2_explore_identity_mgmt.py` (10 tests: models,
  validation hard failures, RO refusal, plan + runner step, no-plan for
  plain configs, probe/changes, apply preview + disabled write, unavailable
  provider); golden untouched; `just verify` 343.

### Possible Other Infra-as-Code tools — exploration

#### Findings

- Tofu/Terraform: the collectors, `TerraformRootMixin`, the gate and the
  remote-state gid chain are all terraform-shaped; Terraform proper is a
  binary swap (`executables.yml`) — already supported in practice.
- Pulumi/CDK would replace the state-file reference chain (N7) with
  program-level references; that is a different system, not a plugin.
- Ansible as an IaC *target* (GOALS.md "Formats") is the interesting one: it is
  the natural executor for the on-image work (mods, updates, tests) and for
  "no-cloud" targets (metal, containers).

#### Plan (branch `v2-explore-iac-tools`, investigation only)

1. Confirm terraform-binary parity with one `just verify` run using
   `terraform` in `executables.yml` (no code).
2. Prototype an ansible *emitter* for the instance-image lifecycle's
   launch parameters (inventory + playbook instead of user_data) to see how
   much of the mount/enrollment logic is reusable on metal.
3. Recommend NOT pursuing Pulumi/CDK now; record why in DESIGN §3H.

#### Findings from execution (branch `feature/v2-explore-iac-tools`, 2026-08-27)

- **Terraform-binary parity: confirmed, with no code.** Every generated
  root (identity users/groups, three storage roots, the instance root)
  was run through `init -backend=false && validate` under OpenTofu 1.12.6
  *and* Terraform 1.9.8 (tfenv auto-installed 1.9.8 for the check -- a
  local tool download, nothing else touched): identical outcomes on all
  six -- the users root valid under both, the other five failing under
  both with the same "Unreadable module directory", because the harness
  copy has no `tfmodules/` (the live V2 verification, run inside
  the then-live `test_folder`, validated them). Swapping `binary:` in `executables.yml`
  is the whole change.
- **Ansible as a target: prototyped and cheap.** `base/ansible_launch.py`
  renders the *same* structural launch parameters
  (`compute_launch_params`) as an inventory (hosts grouped by owning group
  and identity type) and a playbook: hostname, EBS filesystem + mount +
  per-group subtree (`group: "{{ group_gid }}"`), EFS mount by
  `file_system_id`/`access_point_id` extra-vars, sftd enrollment token as
  a `no_log` copy guarded on the var. Runtime values stay references
  (extra-vars instead of `templatefile` variables); the tests assert the
  playbook mirrors the user-data decision for decision and that rendering
  changes no meta-state. That is the metal/container executor for N26
  when there is a target: nothing reads it yet.
- **Pulumi / CDK: no** -- recorded in DESIGN §3H. The gid-by-reference
  chain (N7), the apply gate over a saved plan (N19), remote-state
  read-models and the whole runner-script design are terraform-shaped;
  a program-level IaC would replace, not plug into, them.
- Evidence: `tests/test_v2_explore_iac_tools.py` (3 tests); `just verify`
  336; the parity table above (scratch run, not committed).

### Generation of Idempotent Script-based Modifications — exploration

#### Findings

- Bash mods are free-form; nothing enforces or even encourages idempotence.
  Ansible modules are idempotent by construction, which is the strongest
  argument for "prefer ansible; use bash only for glue".
- Where it lives: this is a **mod-plugin concern plus a test concern**. The
  bash plugin can *generate* guarded scripts from a small declarative form;
  the mod-test harness can *prove* idempotence.

#### Plan (fold into `v2-explore-local-mods` and `v2-explore-mod-tests`)

1. A `bash-remote` item may declare `ensure:` steps (`packages: [...]`,
   `files: [{path, content, mode}]`, `services: [...]`, `commands: [{run,
   unless}]`); the plugin generates guarded shell (`rpm -q || dnf install`,
   `cmp || install`, `systemctl is-enabled || enable`, `unless` checks).
   Free-form `script:` stays available and is marked `idempotent: unknown`
   in lineage.
2. The mod-test harness's second-run check is the enforcement.

### Expanding What Else Plugins Could Do — exploration

#### Findings

What plugins do today: models + builders per VCT, version checkers,
resolution passes, field kinds. What V2 added as hooks: capability types,
prerequisites, activation, launch parameters, gid export, transition
actions, destroy whitelists, session mechanism. What has no seam yet:
lifecycle-level hooks for third parties (only the runner's internal
registry), state queries (next item), tests (items above), notifications,
and *new lifecycles*.

#### Plan (branch `v2-explore-plugin-hooks`, small)

1. Expose the runner's hook registry as an entry-point group
   (`cs_image_system.plugins.hooks`: validators, after-generate,
   before/after-apply) so a plugin can participate without editing base.
2. Allow a plugin to declare a **lifecycle** (name, phases, builder VCTs,
   position in the order) — the mechanism exists (`LIFECYCLE_ORDER` /
   `LIFECYCLE_PHASES` are data); make it registrable. Candidate first user:
   a `release` lifecycle.
3. A `notify` hook (run summary → webhook/Slack) as the trivial proof.

#### Findings from execution (branch `feature/v2-explore-plugin-hooks`, 2026-08-27)

- **Done, small, as predicted.** Two seams now exist without touching the
  runner's internals: (1) an entry-point group
  `cs_image_system.plugins.hooks` whose plugins return a `HookSet`
  (validators, after-generate, before/after-apply, **on-summary**,
  lifecycles); (2) `register_lifecycle(LifecycleSpec(name, phases,
  builder_vcts, after))` — a registered lifecycle takes its place in the
  order, gets its own `generated/<name>/` directory, hooks, runner script
  and gating exactly like a built-in (`LifecycleLike = Lifecycle |
  LifecycleSpec` throughout the runner/context).
- The dummy plugin proves both: an on-summary notifier (`CSIS_NOTIFY_FILE`
  appends one JSON line per run) and an example `notify` lifecycle.
- **Lesson**: a registered lifecycle joins `run --all`, so an *example*
  lifecycle must be opt-in (`CSIS_DUMMY_LIFECYCLE=1`) — the first version
  leaked into every golden/gate run. Real plugin lifecycles (a `release`
  lifecycle) will want to be on by default; that is the intent.
- Evidence: `tests/test_v2_explore_plugin_hooks.py`; `just verify` 336.
  Ready to merge into `develop` on approval; the `release` lifecycle
  (image-tests item) is its first real consumer.

### Using Systemic State For Additional Actions and Decisions and Debugging — exploration

#### Findings

- Meta-state (read-models, lineage, pins, launch params, storage state) is
  the system's *belief*; tofu state is terraform's belief; the cloud and OPA
  are reality. Nothing reconciles the three today except the apply gate
  (which only looks at a plan) and the N14 hand inventory.
- Every V2 artifact is already tagged for exactly this: AMIs carry
  `csis_series/parent/run/fingerprint` tags, EFS access points and S3
  prefixes carry `csis:group`, storage carries its name tag.

#### Approach

A **`query_state()` plugin hook** returning that plugin's view of reality
as public-safe structured data, and a `cs-image-system state
[--reconcile]` command that diffs reality against meta-state and reports
drift classes: *missing* (recorded but gone — e.g. an AMI deregistered by
hand), *foreign* (tagged as ours but unrecorded), *changed* (tag/metadata
differs), *stale* (recorded state ≠ cloud state for storages). Read-only
by construction; reconciliation is a proposal, never an action.

#### Plan (branch `v2-explore-state-query`)

1. Hook + three implementations: okta (groups, attributes, memberships,
   policies — the local-migration lesson says *policies and memberships*),
   AWS images (`describe-images` by `csis_*` tags), AWS storage (EFS/EBS/S3
   by `Name`/`csis:group` tags and the storage read-model).
2. `state` command writes `generated/state-report.json`; validators may
   consult it (e.g. refuse to pin to a build that no longer exists).
3. Tests with fake clients; one live read-only run for the summary.

#### Findings from execution (branch `feature/v2-explore-state-query`, 2026-08-27)

- **Done, read-only by construction.** Three plugin hooks --
  `RuntimeBuilderBase.query_images()`, `StorageBuilderBase.query_state()`,
  `GroupBuilderBase.query_state()` -- each answer with their provider's
  view of what the system manages (AWS: AMIs owned by us carrying a
  `csis_series` tag, EBS/EFS/S3 by `Name` tag; OPA: each managed group's
  `unix_gid`, local group name, `_user` members and `_admin` admins).
  `cs-image-system state query` assembles `generated/state-report.json`
  and classifies drift as *missing / foreign / changed / stale*; a pinned
  build or a live-recorded storage that no longer exists is **hard**
  drift, and every run's validators refuse to proceed while the last
  report records one. `state import` adopts *foreign* artifacts into
  meta-state only (lineage records stamped `imported: true` from the
  tags; a `None -> active` storage transition with action `import`) --
  that is the whole migration story; `tofu import` stays a human step.
- **Unavailable is not absent.** A provider that cannot answer
  (credentials, permissions, transport) is listed under `unavailable` and
  says nothing -- the first live run proved why: `GetBucketTagging` is
  denied to this role, and before the fix that read as "bucket missing".
- **Live run (profile `noaa`, account 514190660293; OPA team
  `nos-coastal-modeling-cloud-sandbox`):** zero tagged AMIs in three
  regions and no managed EBS/EFS -- consistent with N14 (nothing to
  migrate). OPA answered gids for all five groups *and* memberships
  (`GET /v1/teams/{team}/groups/{group}/users` works). Against the test
  fixture's read-model it reported genuine drift: `coops_user` also holds
  `avery.alpha`; `secofs_user` holds `morganm, noel, lennox.lima` and
  `secofs_admin` holds `lennox.lima, oakley` in addition to
  `avery.alpha` -- the fixture's "mirrors existing state exactly" comment
  is out of date, and an identity apply from it would remove those
  people. That is precisely the pre-apply check this item asked for.
- Limits: drift on storages compares presence and provider state only
  (no size/type diff yet); OPA policies (the "local-migration lesson")
  are not queried -- the users endpoint was enough to make the point and
  the policy shape is unverified against the API; GCP has no hook.
- Evidence: `tests/test_v2_explore_state_query.py` (12 tests over faked
  hooks: every drift class, hard vs. soft, validator, import round-trip,
  secret refusal); `just verify` 345.

### Existing Systemic State Migration — exploration

#### Findings

- N14 (2026-08-25) established there is **nothing to migrate**: zero
  system-built images or instances; the only live managed state is the
  OPA group root (already imported and clean) and the users lookups.
- What *will* need a migration path is the next config change of the same
  kind (e.g. the identity-management item above), and adopting hand-built
  "truly external" resources if the stakeholder ever wants them managed.

#### Plan (no branch)

Fold into `v2-explore-state-query`: the *foreign* drift class is the
inventory a migration would start from; an `adopt` action (import into
tofu state + stamp a lineage/storage record) can be added when there is a
real candidate. Record in DESIGN §3H as "adoption of external resources".

## Review of this document (inconsistencies, synergies, stupidity)

- **Rule 2 vs. your instruction**: Rule 2 says each item gets a branch and
  work happens there; this session was told to touch only this file. So
  the plans above are unexecuted — no branches exist yet. Cutting twelve
  branches up front would be busywork; cut each when its work starts.
- **Rule 5 vs. the merged branch**: "merged into v2-lifecycles" implies
  `feature/v2-lifecycles` stays open through exploration. That is fine but
  it delays the squash into `develop` indefinitely; consider finishing V2
  first and branching explorations off `develop`.
- **"Existing Systemic State Migration" is already answered** (N14): moot
  today; the item should say what it is really about — adoption of
  external resources and future schema migrations.
- **"Generation of Idempotent Script-based Modifications" and "Locally
  Installing Modifications" are one item** with "Automated Testing for
  Modifications" as their proof; treat them as a single workstream.
- **"Automated Testing for Image Builds" is the release mechanism** from
  "Systemic Purpose" ("formally release images that are known to be
  correct"), but no item asks for a release lifecycle; add one — it is the
  most valuable thing in this document and it is missing.
- **"Possible Other Infra-as-Code tools"** mostly restates a non-goal: tofu
  ↔ terraform is a binary swap; Pulumi/CDK would replace the design, not a
  plugin. The useful kernel is "ansible as an executor for non-cloud
  targets", which belongs with GCP/Docker breadth, not IaC choice.
- **"Expanding What Else Plugins Could Do"** is a question, not an item;
  its concrete answer (registrable hooks and lifecycles) is a prerequisite
  for a `release` lifecycle and for third-party plugins, so keep it but
  scope it to that.
- **Synergy — the OPA Attributes API**: found for gids, it is also the
  basis for user/group attribute management (identity item) and for the
  state query (drift on attributes). One client, three consumers.
- **Synergy — lineage**: update policy, local mod bundles, mod/image test
  results and release marks all key off `build_id`; lineage.yaml is the
  spine of half these items. Do not create a second registry.
- **Possible stupidity to avoid**: (1) `dnf -y update` on *instance* image
  bakes would break the "same base, refreshed mods" promise of N17 — updates
  belong to base images only, by policy; (2) testing images by launching
  real instances is an *apply* and must go through the same gate and
  `apply_*` flags as everything else, or the "no changes to AWS" discipline
  evaporates; (3) GCP should not start until the packer builder is
  provider-neutral, or it will fork the builder.

## How To Proceed

1. **Finish V2 first.** `feature/v2-lifecycles` is complete against
   DESIGN (gates 1–8 green, TODO closed). Review it, squash-merge it to
   `develop` per git-flow, and branch every exploration off `develop`.
   Keeping explorations stacked on an unmerged feature branch is the one
   structural risk in this document.
2. **Order the explorations by dependency and value**, not by the list:
   1. `v2-explore-plugin-hooks` (small; registrable hooks + lifecycles) —
      unlocks a `release` lifecycle and everything test-shaped.
   2. `v2-explore-local-mods` (+ idempotent script generation) and
      `v2-explore-mod-tests` — one workstream; gives debugging and
      idempotence proof.
   3. `v2-explore-image-tests` **+ a `release` lifecycle** — the formal
      "known correct for a model" mark, keyed on lineage; this is the
      systemic purpose made concrete.
   4. `v2-explore-targeted-updates` — base images only, policy-driven,
      recorded in lineage.
   5. `v2-explore-state-query` (absorbs state migration) — drift detection
      across meta-state / tofu / reality; read-only.
   6. `v2-explore-gcp` — after the packer builder is provider-neutral;
      images first, then storage/instances, then Azure/Docker.
   7. `v2-explore-identity-mgmt` — last; largest; touches live Okta; needs
      the stakeholder to turn Q7's "may" into "should".
   8. `v2-explore-iac-tools` — investigation only; expect to record a
      "no" in DESIGN §3H.
3. **Add the missing item to this document**: a `release` lifecycle
   (image build → tested → released for model X; release marks in
   meta-state; instances may pin only to released builds when a policy says
   so). It is implied by "Systemic Purpose" and by the image-test item.
4. **Merge the duplicates**: state migration → state query; idempotent
   scripts → local mods; plugin expansion → plugin hooks.
5. Keep the discipline that made V2 tractable: each exploration gets a
   DESIGN-style gate row, stubbed tests as evidence, and no live applies
   without an explicit `apply_*` flag.

### Explore having the `output_image_name` config restored

We commented out `output_image_name` as a config name when doing phase 22 (Declarations that never land) because it was no longer being used in the build process. However, restoring it could improve clarity and maintainability by explicitly naming the output image in the configuration.

#### Potential Benefits
- **Improved clarity:** By explicitly naming the output image, it becomes immediately clear which image is being referred to in the configuration.
- **Enhanced maintainability:** Future changes to the build process or image naming conventions can be more easily managed when the output image name is explicitly specified.
- **Reduced risk of errors:** Explicitly naming the output image helps prevent accidental overwrites or misconfigurations, ensuring that the correct image is used throughout the system.
- **Consistency across environments:** Having a standardized way to specify the output image name ensures that all environments (development, testing, production) refer to the same image consistently.
- **Ease of automation:** Automated scripts and CI/CD pipelines can reliably reference the output image by its explicit name, reducing the need for complex logic to determine the correct image.

