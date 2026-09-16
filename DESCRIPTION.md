# What cs-image-system does

## The one-paragraph version

cs-image-system is a declarative provisioning compiler for a cloud compute
environment. You describe the environment in a tree of small YAML files:
the machine images to bake, the instances to run them on, the storage they
mount, the users and groups who may log into them, and the clouds, regions
and credentials involved. The system compiles that description into
reviewable infrastructure-as-code (Packer HCL for images, OpenTofu for
everything else), then executes it in dependency order through phased
lifecycles with a review-before-execute posture. Its deployment target is
the NOAA NOS coastal-modeling cloud sandbox: scientific compute images
deployed as EC2 and GCE instances whose SSH access is governed by Okta
Privileged Access (OPA).

## The estate it manages

Five kinds of things, each declared in its own YAML collection and owned by
a pluggable builder, plus two cross-cutting declarations.

1. **Identities and access** (`groups/`). Users are looked up, not
   created: a person makes them in the Okta admin console and the system
   emits read-only `data "okta_user"` lookups, or, per user, a managed
   `okta_user` resource. Groups are fully managed OPA resources: for each
   named group the system emits a terraform module call producing
   `<name>_admin` and `<name>_user` OPA groups, a resource group delegated
   to the group's own admins, a login project with a gateway selector, a
   pair of SSH security policies (user-level and admin-level) scoped to
   servers labeled `sftd.tx.group=<name>`, and the project's server
   enrollment token, which the system owns and rotates through terraform.
   Membership lists become `oktapam_user_group_attachment` resources on
   bare OPA usernames. Who can SSH where, with or without sudo, is
   source-controlled YAML; identity itself stays human-owned. Roster
   entries and addresses can be encrypted in place (`ENC[age:…]`) and are
   decrypted at load, never written into the emission.
2. **Machine images** (`base_images/`, `images/`). A directed graph. Base
   images start from vendor images found by owner and filter queries,
   optionally updated with the OS family's package manager, and carry the
   prerequisites for the identity and storage types they declare (the OPA
   agent, EFS and S3 tooling), a mandatory local admin user with public
   keys only, and a debug session mechanism. Instance images chain off
   them through `source_image`, belong to one group, bake that group's
   activation, and carry `modifications`: ansible playbooks or shell
   scripts and `ensure` items that become Packer provisioners. Every
   modification is also installed on the image under `/opt/csis/mods` with
   a small runner, so a standing instance can re-apply or inspect it. The
   image graph is sorted into sequential Packer build blocks so a later
   image consumes the image a previous block produced; Packer's manifest
   records the resulting image ids. An image may declare in-bake tests and
   post-bake tests, and a `release` model that names the built image a
   release when the tests pass.
3. **Instances** (`instances/`). Named deployments of instance images as
   terraform-managed machines. An instance of an image built in the same
   run receives a deferred image reference: a name-pattern data source plus
   a variable the system fills in from the Packer manifest before the
   instance root plans. An instance pins its image by policy, may require
   a released build, mounts storages by name, wears the group's activation
   at launch through cloud-init (mounts, gid, the enrollment token supplied
   at launch time, never recorded), and may be declared `ephemeral`:
   launched, verified and torn down within one run.
4. **Storage** (`storages/`). EBS volumes, EFS filesystems and S3 buckets
   on AWS; persistent disks and GCS buckets on GCE. Each is a terraform
   module call with typed per-provider variables; instances reference them
   across workspaces through remote state. A storage has a lifecycle:
   standing, archived (a tag-named snapshot) and restored, transient (torn
   down by the run that declared it) or destroyed through the gate.
5. **Runtimes** (`cfg/runtime-builders.yml`). The cloud contexts: AWS
   profiles, regions, VPCs and subnets (discovered live through boto3,
   including which subnets are public) and GCE projects, zones and
   networks. Every other builder names the runtime it operates in.

Cross-cutting: **state backends** give every terraform workspace its own
encrypted S3 state object under one bucket and prefix, and **executables**
pin the tools (tofu, packer, ansible, gcloud, bash, docker) the
configuration expects to find.

## How it works

The architecture is a plugin-based compile pipeline around phased
lifecycles.

- **Configuration.** `cfg/*.yml` and the collections are merged, run
  through ordered Jinja passes (`ENV.*`, the run timestamp, `config.*`
  and scope-aware `this.*` references), then structured by Pydantic into
  typed dataclass models, dispatching on each entry's `type:` through a
  central registry. Unknown keys are refused. One configuration object
  (`IAConfig`) is the read-model for the run context, `GlobalTypeContext`,
  which every builder reads. Overlays passed on the command line adjust a
  configuration for one invocation without touching the tree.
- **Plugins.** Every capability is a plugin discovered through Python
  entry points (`cs_image_system.plugins.*`). A plugin registers model
  classes and builder classes under a classification enum of about forty
  values. The in-repo plugins: Okta and OPA (groups and users), packer
  (images), ansible and bash (modifications), default-os (OS families),
  the AWS and GCE runtimes, the terraform storage and instance builders,
  the GCP terraform pieces, the S3 state backend, and a dummy plugin as an
  extension template. Adding a cloud, a storage kind or a modification
  mechanism means adding a plugin, not editing the core. Each package has
  its own README ([docs/PLUGINS.md](docs/PLUGINS.md)).
- **Lifecycles.** Four generation lifecycles run in order — identity,
  storage, base-image, instance-image — followed by release and
  retention. Each is optional, regenerates only its own
  `generated/<lifecycle>/` directory, and writes its own runner script,
  `run-<lifecycle>.sh`: the script exists, so it runs; it is absent, so
  the lifecycle is a no-op. Within a lifecycle, phases run in a fixed
  order and every builder emits files plus commands split into run-now
  (`fmt`, `init`, `validate`) and deferred (packer builds, terraform plan,
  gate, apply). The scripts are self-contained: they reach the
  configuration root through a variable defined relative to the script and
  initialise their own terraform roots, so a committed script runs from
  any checkout.
- **The gate.** Every terraform root is applied through a plan file that
  a gate inspects: a plan that destroys anything not explicitly allowed is
  refused, and an apply happens only when the lifecycle's `apply_*` flag
  or `--apply-runtime` says so, re-checked at execution time.
- **Dry run by default.** A plain run generates and enumerates what would
  execute; `--no-dry-run` performs it in-process with the builders'
  pre- and post-finalize hooks around each phase, which is where Packer
  manifests become image ids and instance variables. A dry run never
  touches remote state.
- **Records.** Cross-run memory lives in the configuration repository
  under `meta-state/`: identity and storage read-models, image lineage
  with every modification's content hash, the pin file, launch parameters,
  the storage state machine, releases, test results. `--commit` commits
  the emission and the records into that repository, by pathspec, after a
  byte-level gate refuses anything that must never be public: key
  material, plans, state, tfvars, real addresses outside declared
  allowances. The same gate runs as a pre-commit hook and in CI.
- **Reality versus records.** `state query --strict` reads both clouds
  and the OPA API and reports every drift class between the records and
  what exists; the operator's cycles refuse to start on drift.

The generated tree is an honest intermediate representation: every
`.pkr.hcl` and `.tf` file the system intends to act on can be read, and the
terraform workspaces planned and applied under whatever review discipline
the operator imposes.

## The posture

Three commitments show up everywhere:

- **Humans own identity; code owns access.** Identities and OPA groups are
  never destroyed by the system; users are not created by it unless
  declared managed one by one.
- **Nothing irreversible happens by default.** Dry run is the default,
  applies are gated and reviewable, and generation is idempotent:
  `generated/` can be deleted and rebuilt byte-identically at any time,
  which is what the golden fixture proves.
- **Everything is a plugin.** The core knows about lifecycles, YAML
  structuring, registries and HCL emission; every opinion about a
  specific cloud, tool or product lives at the edge.

## Known limits

- **No model image exists yet.** The stated purpose is an image that is
  correct for a given HPC model. The released `imgfile-basic-dask` image
  installs dask and git and nothing else; the data-science playbook is a
  placeholder that changes nothing. The mechanisms are all there and
  proven; the content is not.
- **A modification that declares only `config:` renders nothing.** The
  ansible builder emits one provisioner per playbook, so an item with
  config keys and no playbook contributes no provisioner, while lineage,
  the on-image bundle and the modification tests record it as present.
  Two such items exist in the fixture and the live configuration.
- **Applies are the operator's.** CI verifies and reads; it never plans
  or applies. Real runs, the GCE cycle included, are hand-run through the
  Justfile, and GCE spending is the operator's own money, so nothing may
  be left standing there.
- **Identity writes are limited.** Users are looked up or, per user,
  managed; identity attribute writes (uids, gids on the identity side)
  are disabled. Discovery before an OPA reconciliation enumerates
  security policies by hand.
- **Clouds.** AWS and GCE are real; Azure and containers are goals
  without plugins.
- **Releases.** A release is a git tag; publishing packages to an index
  is not wired.

Where the documentation and the system can diverge, and how to check, is
[PARITY.md](PARITY.md).
