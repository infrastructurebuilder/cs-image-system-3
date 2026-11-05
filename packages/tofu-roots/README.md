# cs-image-system-tofu-roots

The provider-neutral terraform roots: what an OpenTofu root is in this
system, written once, for every provider's root plugin to subclass. An
instance root and a storage root are the same terraform whatever the
cloud or daemon underneath -- one workspace per builder, one `module`
call per instance or per storage, bound to a state manager by reference,
planned, gated and applied by the lifecycle runner -- and this package
holds that sameness: the root mixin (the backend file, the `init`
arguments, the gated `plan`, gate, `apply` sequence), the instance and
storage root bases with the hooks a provider answers, their model bases,
the `tofu` version checker, and the run hooks through which the core,
which knows nothing of state backends, asks the roots where their state
lives.

**This is a library, not a plugin.** It registers no model and no builder
of its own: no tree writes a `type:` that names a class of this package,
and the bases have no `csis_name()`. What it does declare is one entry
point, `cs_image_system.plugins.hooks`, through which the core discovers
the [run hooks](#the-run-hooks) that check and record state locations; a
tree with no terraform roots installs the same hooks and they find
nothing to say. The three provider root plugins of the workspace
([tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md) for AWS,
[tf-gcp-plugin](../tf-gcp-plugin/README.md) for Google Cloud,
[tf-docker-plugin](../tf-docker-plugin/README.md) for a container
daemon) subclass the two bases, and the identity roots of
[okta-opa-plugin](../okta-opa-plugin/README.md) mix in the root mixin.

It builds on [hashicorp-utils](../hashicorp-utils/README.md), the
library that collects provider, backend and variable requirements per
workspace and renders HCL, and on the core: the roots are builders, so
they subclass the core's builder bases and read the run context. The
collector a root registers into is the run's own,
`terraform_collector(ctx)` over the context the builder sees; nothing
here constructs one.

Licensed under Apache-2.0. Requires Python 3.13 or later. Declared
dependencies ([pyproject.toml](pyproject.toml)): `cs-image-system-contract`,
`cs-image-system-base`, `cs-image-system-hashicorp-utils` and `pydantic`.
It imports nothing of any plugin, and the workspace's neutral-root test
([tests/test_v2_stage_120_neutral_root.py](../../tests/test_v2_stage_120_neutral_root.py))
and the import-order test in
[tests/test_v2_contract.py](../../tests/test_v2_contract.py) hold it to
that.

## Contents

- [Modules](#modules)
- [TerraformRootMixin](#terraformrootmixin)
- [The terraform roots](#the-terraform-roots)
- [The run hooks](#the-run-hooks)
- [Tests](#tests)
- [Prerequisites and integration](#prerequisites-and-integration)
- [Configuration reference](#configuration-reference)
- [What it tests and verifies](#what-it-tests-and-verifies)
- [When it fails](#when-it-fails)

## Modules

| Module | Provides |
| -------- | ---------- |
| [`roots.py`](src/cs_image_system/tofu_roots/roots.py) | `TerraformRootMixin` and `run_is_dry()`. |
| [`tofu_models.py`](src/cs_image_system/tofu_roots/tofu_models.py) | `TofuInstanceBuilderModelBase` and `TofuStorageBuilderModelBase`, what every terraform instance and storage root declares whatever its provider (`executable`, `required_plugins`, `state_configuration`, and for a storage root `variables`), and `TOFU_EXECUTABLE`. |
| [`tofu_instance_builder.py`](src/cs_image_system/tofu_roots/tofu_instance_builder.py) | `TofuInstanceBuilderBase`, the provider-neutral instance root, and `TofuVersionChecker`, the version checker for OpenTofu. |
| [`tofu_storage_builder.py`](src/cs_image_system/tofu_roots/tofu_storage_builder.py) | `TofuStorageBuilderBase`, the provider-neutral storage root; `RecordedStorage`, the stand-in for a storage known only from meta-state; the accessors `storage_groups()` and `storage_public_read()`. |
| [`hooks.py`](src/cs_image_system/tofu_roots/hooks.py) | The run hooks: `state_location_problems` (the validator), `record_state_locations` (after a lifecycle generates), `lifecycle_state_bindings` (the state-isolation evidence), and `initialize()`, the entry point that hands them to the core. |

Nothing in this package writes files of its own accord. The roots return
their HCL and their scripts as assets; the runner writes them.

## TerraformRootMixin

A builder whose workspace is a standalone terraform root (its own
`terraform {}` block, backend partial-configuration file and tofu command
sequence) mixes `TerraformRootMixin` in next to its `BuilderBase`
subclass. The mixin is duck-typed against `BuilderBase`: it relies on
`self.name`, `self.get_path_for_phase(phase, suffix=...)`,
`self.get_executable_copy()` and, when present, `self._get_context()` and
`self.model`. In the workspace the mixin is on `OktaTfGroupBuilder` (and
its read-only subclass) and `OktaTfUserBuilder` in the identity plugin,
and on the two provider-neutral roots of this package,
`TofuInstanceBuilderBase` and `TofuStorageBuilderBase`, from which every
provider's instance and storage root inherits it.

The mixin reaches the run's terraform collector through `_collector()`:
`terraform_collector(ctx)` of
[hashicorp-utils](../hashicorp-utils/README.md#terraformcollector) over
the context `_get_context()` gives, so the collector is the run's own
(one per context, no process-wide object), and a builder driven outside
a run, with no context, gets `None` and is treated as having bound no
backend. `_context()` is the guarded accessor: a stub in a plugin's unit
test may give any object, and a context that refuses because no
configuration is loaded reads as none.

### Backend file and init arguments

`_backend_config_path(phase)` is
`<builder>/<phase>/<builder>-<phase>.tfbackend.hcl`, the file
`generate_backend_config` fills.

`_init_args(phase)` is the generation-time `init`:

| Run | Arguments | Why |
| ----- | ----------- | ----- |
| dry run | `init -backend=false` | Providers are installed and the emission validated without touching remote state, which holds decrypted values. A read-only CI role, a drift check and an operator's preview all stay off the state bucket. |
| real run, backend bound | `init -reconfigure -backend-config=<file>` | The bare file name, because tofu runs inside the phase directory. `-reconfigure` because a backend argument may differ from the one the root was last initialised with (`encrypt`, for example), and the state is remote, so there is nothing to migrate; without it tofu refuses with "Backend configuration changed". |
| real run, no backend | `init` | Backends disabled, or the workspace bound to nothing. |

"Backend bound" is decided by whether the run collector's
`generate_backend_config(self.name)` returns lines, so the gate flag and
the binding both count.

`run_is_dry(builder)` reads the run context's `dry_run` flag; a builder
used outside a run (no context bound, as in unit tests, where `_get_context`
is absent or raises) is not in a dry run. `_dry_run()` is the
method form.

`_runner_init_args(phase)` is the `init` a committed runner script performs
for itself, always in the real-run form:
`init -input=false -reconfigure [-backend-config=<file>]`. A dry run's
generation-time init was backend-less and a fresh clone has no
`.terraform/` at all, so the script must initialise the root itself. It is
deferred like the plan it precedes, so an in-process real run repeats it
(idempotent, seconds) and the script stays a faithful record of what
finalization executes.

### The runtime rung

`runtime_state_configuration()` returns the `state_configuration` of the
runtime the builder's model names (`model.get_runtime_provider()`), read
from that runtime builder's model in the run context. It is the second
rung of the chain a root's backend resolves through: the
root's own value when it names a backend, else its runtime's, else the
default. It answers `None` for a root without a runtime (the identity
roots), for a runtime still at `default`, and outside a run. The storage
and instance builders pass it to `bind_workspace` beside their own
`state_configuration`.

### Plaintext reads and the private mirror

`plaintext_read_commands(phase, working_directory, arg_lists)` builds the
generation-time tofu commands that must read the **plaintext** emission.
The committed emission carries `ENC[age:...]` ciphertext, and a derived
e-mail address carries it inside the string;
`fmt`, `init` and `validate` do not care, but a real run's generation-time
`plan` does -- the Okta user lookups search by that address. So, exactly as
the deferred runner does, the sequence is:

1. `cs-image-system --root-dir <config root> --no-dry-run [--overlay ...]
   materialize .` in the workspace directory, which copies the root to
   `_private/<the same relative path>` under the configuration root with
   every marker replaced by its plaintext (`mirror_path` in
   [`materialize.py`](../base/src/cs_image_system/base/materialize.py):
   `_private/` stands where `generated/` stands, at the same depth, so
   relative module sources and `local` state paths keep resolving);
2. `_runner_init_args(phase)` **in the mirror** (providers are not
   mirrored, so the copy is initialised there);
3. each of `arg_lists` in the mirror.

Without a configuration root to mirror under (the offline harness's bare
context has no `working_path`) the commands run where they always did. The
identity builders call it for their real-run generation-time `plan` (the
group root with `-refresh=false`); the storage and instance builders do
not plan at generation time at all.

### Command materialization

`terraform_commands(phase, arg_lists, working_directory)` returns one
`ExecutableModel` per argument list, each a fresh `get_executable_copy()`
bound to the workspace directory. A fresh copy per command is mandatory:
`args` and `working_directory` are mutated per command, so sharing one
model would make every command run the last arguments. A `None` working
directory is an assertion failure naming the phase and the builder class;
a builder whose `executable` names no entry in `cfg/executables.yml`
fails inside `get_executable_copy()` with
`Executable '<key>' not found for builder '<name>' of type '<type>'`.
That is the only refusal for a missing executable: `get_executable_copy()`
raises first, naming the builder, so `terraform_commands` checks nothing
after it returns.

### The gated plan, gate, apply sequence

`gated_apply_commands(phase, working_directory, apply, allow_destroy=(),
replace=(), pre_plan=(), apply_flag_key=None, apply_root=None,
apply_root_aliases=(), plan_extra_args=(), pre_commands=(),
require_unmounted=(), pre_plan_backup=False)` returns the deferred
sequence for a terraform root, in this order:

1. `rm -f tfplan` -- a failed plan must leave nothing for the gate to
   read, or the gate judges the previous sequence's plan.
2. `<tofu> init -input=false -reconfigure [-backend-config=<file>]` -- the
   runner's own init. When the root is **migrating** this run (its name is
   in the run context's `migrate_state` list, from
   `run --no-dry-run --migrate-state <root>`), this step is instead
   `cs-image-system ... state-migration begin --workspace <ws> --tofu <bin>
   --backend-config <file> --location <new location> --run <id>` followed
   by `<tofu> init -input=false -migrate-state -force-copy
   -backend-config=<file>`.
3. only when `pre_plan` is non-empty and `pre_plan_backup` is true:
   `cs-image-system ... state-migration backup --workspace <ws> --tofu
   <bin> --run <id>`, which pulls the state the root is initialised
   against and keeps it as
   `_private/state-backups/<ws>.backup-<run>.tfstate` under the
   configuration root (a `state rm` the system decides on is preceded by
   the backup a hand edit would take).
4. each `pre_plan` argument list (for example `state rm <address>` for a
   group leaving management).
5. each `pre_commands` executable, as given (for example the unmount before
   a detach, or the identity runner's `prune-attachments` step).
6. `<tofu> plan -input=false -out=tfplan [-detailed-exitcode]
   [-replace=<address> ...] [plan_extra_args ...]` -- `-detailed-exitcode`
   only when migrating (a change stops the runner: the move is accepted
   only clean); `replace` addresses are forced replacements (an explicit
   upgrade); `plan_extra_args` carries flags such as
   `-var=ephemeral_present=false`.
7. `cs-image-system gate-plan --planfile tfplan --tofu <tofu>
   [--allow-destroy <address> ...] [--require-unmounted <pair> ...]` -- the
   gate. Every `allow_destroy` address and every `replace` address is
   passed as `--allow-destroy`, so a replacement's destroy is whitelisted
   and any other planned destroy fails the gate. Each `require_unmounted`
   pair demands an unmount receipt.
8. only when migrating: `cs-image-system ... state-migration finish
   --workspace <ws> --run <id>`, which records the move in meta-state.
9. only when `apply` is true:
   - when `apply_flag_key` is given, `cs-image-system apply-check
     --lifecycle <key> [--root <apply_root> --root-alias <alias> ...]
     [--overlay <file> ...] [--apply-runtime <rt>]`, re-checking the
     `apply_<key>` flag at execution time so a script generated under
     yesterday's flags cannot apply under today's; the
     run's overlays and `--apply-runtime` are carried from the run
     context;
   - `<tofu> apply -input=false tfplan` -- the very plan that passed the
     gate.

The `cs-image-system ...` commands written with an ellipsis above are
built by `system_cli_executable_with_config` in the base library and carry
`--root-dir <configuration root> --no-dry-run [--overlay <file> ...]`
before their own arguments (the runner renders the root as `"$CSIS_ROOT"`);
`gate-plan` and `apply-check` need no configuration and are emitted bare.
`<tofu>` for the system commands is the executable entry's `binary`, else
its `name`.

`apply` is the value of the lifecycle's `apply_<lifecycle>` configuration
flag for this root (`apply_enabled(key, root, aliases)` in the base
library), so a root that is not allowed to apply still plans and gates.
The instance root's ephemeral-teardown sequence passes `apply=True`
because it is only built when the root may apply; `apply-check` still
stands in front of its apply.

## The terraform roots

An instance root and a storage root are the same terraform whatever the
cloud or daemon underneath: one workspace per builder, one `module` call
per instance or per storage against a module the provider names, driven
by OpenTofu, bound to a state manager by reference, planned, gated and
applied by the lifecycle runner. What differs between providers is small
and nameable: which provider and how it is configured, which module,
what the module call carries, how the launch script reaches the machine,
which address a replacement or a detach names. So the root lives here,
once, as two provider-neutral bases, and a provider's root plugin
subclasses a base and answers its hooks. The three root plugins of the
workspace ([tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md)
for AWS, [tf-gcp-plugin](../tf-gcp-plugin/README.md) for Google Cloud,
[tf-docker-plugin](../tf-docker-plugin/README.md) for a container
daemon) are each such a subclass, and no root plugin depends on another
provider's root plugin: installing the GCE or the container root
installs neither the AWS root, nor `aws-runtime-plugin`, nor `boto3`.
The change that put the root here is recorded in the stage index under
[a provider-neutral terraform root](../../docs/CHANGES.md#s120).

### The two bases

[`tofu_instance_builder.py`](src/cs_image_system/tofu_roots/tofu_instance_builder.py)
holds `TofuInstanceBuilderBase`, an `InstanceBuilderBase` with
`TerraformRootMixin` mixed in;
[`tofu_storage_builder.py`](src/cs_image_system/tofu_roots/tofu_storage_builder.py)
holds `TofuStorageBuilderBase`, the same over `StorageBuilderBase`. Each
is generic in its model (`TofuInstanceBuilderBase[Q]` with `Q` bound to
`TofuInstanceBuilderModelBase`), so a subclass that binds the parameter
to its own model reads that model's fields through `self.model`. Neither
base has a `csis_name()`: the bases register nothing, and no tree ever
writes a `type:` that names one; the `type:` is always the subclass's.

**The instance base owns** everything no provider owns:

- the root's layout (the main file `<B>-instance-generation.tf`, one
  `<B>-instance-generation-instance-<label>.tf` per instance with the
  launch template beside it, the partial backend file) and the header
  comment that opens the main file;
- the provider requirement (from the builder's `required_plugins`, or
  the provider's own bare requirement when none is declared) and the
  aliased provider block, both filled through the hooks;
- the variables, in the order `_declare_variables` emits them: the
  ephemeral toggle `ephemeral_present` (when any instance is ephemeral),
  one image variable per instance that finalization fills from the
  packer manifests (`_image_var(label)`, default `<label>_image`), and
  the enrollment-token variable `sft_enrollment_token` (sensitive, empty
  by default, supplied at apply time and never recorded);
- the state-manager binding (`bind_workspace` on the run's collector,
  with the builder's own `state_configuration` and the runtime's) and the remote-state
  references to every storage builder that owns storages and to every
  identity workspace that owns an instance image's group, so storage
  outputs and gids enter by terraform reference and never as literals;
- the module call per instance (`render_module_call` over the
  provider's `_module_args`, with the `count` an ephemeral instance
  gets) and the launch template (`user_data_template` over the recorded
  launch parameters);
- the runner lines: `fmt`, `init` and `validate` at generation, and at
  finalization the [gated plan, gate and apply
  sequence](#the-gated-plan-gate-apply-sequence) of the mixin with this
  root's unmount steps and gate requirements for every detach, the
  `-replace` of every pending upgrade or `follow`, and the destroy
  whitelist: the decommissioned instances (recorded, no longer declared,
  scoped to this runtime by the pinned build's lineage), the detached
  attachments, the replaced instances' attachments, and the root's own
  resources once no instance is declared;
- the ephemeral sequence after the launch applied: `verify instance`
  per ephemeral (`--record-only` under `on_failure: teardown`; skipped
  once `teardown_after` has elapsed since a failed verdict), then the
  same root planned with `-var=ephemeral_present=false` and that
  whitelisted destroy applied;
- when the root is emitted at all (`_root_has_work()`): declared
  instances, or a recorded instance no longer declared, or a recorded
  state location whose state may still hold the root's own resources;
  nothing for another runtime's root under `--only-runtime`;
- the two finalization hooks that pin an instance to the build it
  launched from: `pre_finalize_phase` writes `instances.auto.tfvars`
  with the resolved image id of every instance whose build this run
  baked, under the name `_image_var` gives, for the `instance-image`
  lifecycle alone and only for a root in the run's runtime scope;
  `post_finalize_phase`, after a real apply, moves a `follow` pin and
  binds every unpinned durable instance to the build it launched from
  (from the resolved image, else from the image the runtime reports it
  booted when lineage records that build).

**The storage base owns**, in the same way: the root's layout and
header; the provider requirement and block through the hooks; the
state-manager binding and the identity remote-state references (gids by
reference, never a literal: `gid_reference(group)` is the group
builder's expression, `group_subtrees(storage)` maps each allowed group
to `{gid, path, permissions}`); the module call and the
`output "storage_<label>"` per live storage, the tombstone comment per
`destroyed` storage and the archive comment per `archived` one on a
builder that supports archiving; the runner lines (`fmt`, `init`,
`validate`, then the transition scripts of every storage moving to
`destroyed` or `archived`, the gated plan, gate and apply, and the
post-transition actions after the apply); `_script(name, body)`, which
writes a bash script beside the root as a deferred step; `RecordedStorage`,
the stand-in for a storage that left the YAML but is still recorded
(name, recorded state, the record's facts), so its destroy is planned
and whitelisted; the state query (`query_state()` over every declared
and recorded storage, through the provider's `_lookup`, with `present`
and the capability type); and the ownership test a shared account needs
(`_owned` and `_elsewhere`: a thing of our name whose tags belong to
another configuration is reported absent for us and noted, never
claimed). `storage_groups(storage)` and `storage_public_read(storage)`
are the duck-typed accessors a stand-in satisfies.

### The hooks

A hook is a method the base calls and a subclass answers. A hook with no
default raises `NotImplementedError` naming the subclass (`<Class> must
name its provider`) from the first generation that needs it; a hook with
a default is overridden only where the provider differs. The columns
give the three workspace answers as examples.

The instance root's hooks (`TofuInstanceBuilderBase`):

| Hook | What it answers | AWS (`TofuInstanceBuilder`) | GCE (`TofuGceInstanceBuilder`) | docker (`TofuDockerInstanceBuilder`) |
|---|---|---|---|---|
| `_provider_name()` | the provider required and configured when the builder declares no `required_plugins` | `aws` | `google` | `docker` |
| `_provider_source()` | that provider's registry source | `hashicorp/aws` | `hashicorp/google` | `kreuzwerker/docker` |
| `_provider_config(rtb)` | the provider block's arguments from the runtime builder; `None` is no provider block at all, `{}` a block with no arguments | `region` and, when the runtime names one, `profile`; `None` without a region | `project`, `region`, `zone`, each when the runtime names it; `None` when it names none | `{}`: the daemon's address rides in the environment of every tofu process |
| `_module_dirname()` | the `tfmodules/` directory every instance's module call targets | `aws_instance` | `gce_instance` | `docker_container` |
| `_module_resource()` | the resource type inside the module a replacement names (`module.instance_<label>.<type>.this`) | `aws_instance` | `google_compute_instance` | `docker_container` |
| `_instance_word()` | how the module-call comment calls one instance (default `instance`) | the default | `GCE instance` | `container` |
| `_root_header_lines()` | the comment lines that open the main file (default: one line naming the class and the builder) | the default | `# Terraform configuration for GCE instances generated by ...` | three lines, the last two saying the daemon's address is not in the file |
| `_root_extra_blocks(rtb)` | root-level blocks of the provider's own, emitted after the shared ones (default none) | the VPC lookup and the instances' security group, both bound to the aliased provider | none | none |
| `_image_var(label)` | the per-instance variable finalization fills (default `<label>_image`) | `<label>_ami_id` | the default | the default |
| `_launch_template_name(label)` | the launch script template beside the root (default `user-data-<label>.sh.tftpl`) | the default | the default | `launch-<label>.sh.tftpl`, uploaded into the container at creation |
| `_declare_variables(col, ws)` | the root's variables in emission order (default: the ephemeral toggle, the image variables, the enrollment variable) | the image variables first, then the toggle, then the enrollment variable | the default | the default |
| `_attachment_address(instance, storage)` | the terraform address whose destroy IS the detach; `None` when the attachment is an in-place attribute of the instance (default `None`) | `module.instance_<label>.aws_volume_attachment.this` | the default | the default |
| `_own_resources_to_let_go()` | the root's own resources the gate may let a plan destroy once no instance is declared (default none) | `aws_security_group.csis_instances` | the default | the default |
| `_module_args(ctx, rtb, instance, params)` | the module call's inputs for one instance: the image (the pinned build, else the resolved image, else the variable with the provider's own fallback), the machine type, the network, the labels, and the launch arguments when the parameters are given | `ami_id` with `ami_name_pattern` as the fallback, `instance_type`, `associate_public_ip_address`, the security groups, `subnet_id`, `iam_instance_profile`, `tags` | `image` with `image_family` as the fallback, `machine_type`, `zone`, `subnetwork`, `network_tags`, `public_ip`, `labels` | `image` with `image_tag` as the fallback, `hostname`, `cpus`, `memory`, `network`, `labels` |
| `_launch_args(ctx, label, params)` | the launch script (`templatefile` over the recorded launch parameters) and the storage attachments, each runtime value by terraform reference | `user_data`, `ebs_volumes` | `startup_script`, `attached_disks` | `launch_script`, `volumes` |

The storage root's hooks (`TofuStorageBuilderBase`; the last five are
`StorageBuilderBase` hooks the root calls at the places named):

| Hook | What it answers | AWS (`TofuStorageBuilder` and its services) | GCP (`TofuGcpStorageBuilder` and its services) | docker (`TofuDockerVolumeStorageBuilder`) |
|---|---|---|---|---|
| `_provider_name()`, `_provider_source()`, `_provider_config(rtb)` | as on the instance root | `aws`, `hashicorp/aws`, the region and profile | `google`, `hashicorp/google`, the project, region and zone | `docker`, `kreuzwerker/docker`, `{}` |
| `_root_header_lines()` | the main file's opening comment (default: one line naming the class and the builder) | the default | `# Terraform configuration for GCP storages generated by ...` | three lines, as the container instance root |
| `module_dirname()` | the `tfmodules/` directory this builder's storages map to | `aws_storage_ebs`, `aws_storage_efs`, `aws_storage_s3`, one per service subclass | `gcp_storage_pd`, `gcp_storage_filestore`, `gcp_storage_gcs` | `docker_volume` |
| `module_args(storage)` | the module call's inputs for one storage | the declared `variables`, the name, the size, the placement, the lifecycle, the access points or prefixes, the tags | the name through `gce_name`, the size and disk type, or tier and capacity, or location; the labels; the zone | the volume name, the driver and its options, the labels |
| `_lookup(storage)` | the provider's record of one storage by name, `None` when absent; raise when the answer is unavailable | boto3: `describe_volumes` or the archive snapshot, `describe_file_systems`, `get_bucket_tagging` | the compute client for a disk or its snapshot; `gcloud` for a share or a bucket | `docker volume inspect` |
| `supports_archive()` | whether the builder realizes `archived` (default no) | EBS yes; EFS and S3 no | pd yes; Filestore and GCS no | no |
| `transition_actions(storage, from, to)` | the commands run before the apply of a transition (default none) | the EBS snapshot and snapshot-delete scripts, the S3 wipe | the `gcloud` snapshot and snapshot-delete scripts, the GCS wipe script | none: the volume goes with its data |
| `post_transition_actions(storage, from, to)` | the commands run after the apply of a transition (default none) | the EBS restore's snapshot delete | the pd restore's snapshot delete | none |
| `retag_storage(storage, tags)` | re-tag a standing storage for `lineage relabel` | `create_tags`, `tag_resource`, `put_bucket_tagging` | `set_labels`, `gcloud ... update --update-labels` | refuses: a volume's labels are fixed at creation |
| `destroy_whitelist(storage)` | the addresses the gate may let a transition destroy (default `module.storage_<label>`) | the default | the default | the default |

### The models

[`tofu_models.py`](src/cs_image_system/tofu_roots/tofu_models.py)
holds the two model bases, both pydantic dataclasses under
`CSIS_MODEL_CONFIG`, and `TOFU_EXECUTABLE`
(`"tofu"`). `TofuInstanceBuilderModelBase` extends the core's
`InstanceBuilderModel` with what every terraform instance root declares
whatever its provider: `executable` (default `tofu`, the
`cfg/executables.yml` entry), `required_plugins` (a list of
`TFTofuPluginModel`; empty means the provider's own bare requirement)
and `state_configuration` (a foreign key to a state backend, default
`default`, the first rung of the chain the mixin's
[runtime rung](#the-runtime-rung) continues). `TofuStorageBuilderModelBase`
extends `StorageBuilderModel` with the same three and `variables`, a
`ModuleVariables` each provider narrows to its module's own tunables
(`EbsVariables`, `GcpVariables`, `DockerVolumeVariables`). A provider's
model subclasses a base, sets `type` and answers `csis_name()`; the base
answers neither, because the `type:` a tree writes is the subclass's,
never one of these (`tofu`, `tofu-gce`, `tofu-docker` for the instance
roots; `tf-aws-ebs`, `tf-gcp-pd`, `tf-docker-volume` and their siblings
for the storage roots).

### The version checker

`TofuVersionChecker` in
[`tofu_instance_builder.py`](src/cs_image_system/tofu_roots/tofu_instance_builder.py)
is the version checker for OpenTofu: an `AbstractVersionChecker` named `tofu`,
so an entry of `cfg/executables.yml` with `type: tofu` is checked by it;
it runs `<binary> --version -json` and reads `terraform_version`, and
the base library compares that with the entry's `version` requirement at
`validate` and at every run. **Every root plugin registers it** (under
its instance service: `tofu`, `tofu-gce`, `tofu-docker`), so a tree
whose terraform roots are on one provider alone still has its tofu
checked. The registry's rule makes that safe: the same class registered
under one name by several plugins is one registration; only a
*different* class under an existing name is a `Type Collision`.

### Writing a new provider's root

1. Subclass the models: a `TofuInstanceBuilderModelBase` and, per
   storage service, a `TofuStorageBuilderModelBase`, each with its
   `type` and `csis_name()`; narrow `variables` to the module's
   tunables.
2. Subclass `TofuInstanceBuilderBase[YourModel]` and answer the hooks
   with no default (`_provider_name`, `_provider_source`,
   `_provider_config`, `_module_dirname`, `_module_resource`,
   `_module_args`, `_launch_args`) and whichever defaults the provider
   differs on. The module arguments resolve the image in the base's
   order (the pinned build, else the resolved provider-specific image,
   else `var.<image var>` with the provider's own fallback) and put
   every runtime value in the launch arguments by terraform reference.
3. Subclass `TofuStorageBuilderBase[YourModel]` per service: the
   provider hooks, `module_dirname`, `module_args`, `_lookup`, the
   capability type, the cardinality, whether it is zonal, and the
   transition and re-tag hooks where the service realizes them.
4. Register the models, the builders and `TofuVersionChecker` from the
   plugin's `initialize()`; depend on this package, on
   [hashicorp-utils](../hashicorp-utils/README.md) and on the
   provider's runtime plugin, never on another provider's root plugin
   (the neutral-root test refuses the import and the dependency).
5. Add the provider's modules under `tfmodules/` with the inputs the
   module arguments name.

## The run hooks

The core knows lifecycles, builders and meta-state; it knows nothing of
terraform state backends, and it imports nothing of this package or of
hashicorp-utils. What a terraform root needs from a run -- its state
location checked before anything is generated, recorded after its
lifecycle generates, and shown beside the others as the state-isolation
evidence -- comes from [`hooks.py`](src/cs_image_system/tofu_roots/hooks.py),
which `initialize()` hands to the core through the
`cs_image_system.plugins.hooks` entry point as a hook set:

| Hook | When the core calls it | What it does |
| --- | --- | --- |
| `state_location_problems(ctx)` | as a validator, at `validate` and before every run generates | resolves every terraform root's location from the declarations through the run's collector (nothing when backends are disabled) and refuses two things: a **collision** (two roots that would write one state object: the same bucket and normalised prefix under two backend names, two names that collapse under `super_safe_name`, a doubled slash against a single one) and an **unsafe move** (a root whose resolved location differs from the one meta-state recorded while the records show live resources in it; the new location is empty, so the next plan would create everything again and strand the old state). A root with nothing deployed moves freely; the escape is the operation `--migrate-state <workspace>`, never an override. |
| `record_state_locations(ctx, lifecycle)` | after a lifecycle generates | writes each generated root's resolved location (`backend_record`) to `meta-state/state-locations.yaml`, the memory a later run's move guard compares against; a root migrating this run is left to the migration's own `finish` step |
| `lifecycle_state_bindings(ctx)` | when the runner scripts and the run summary are written | `{lifecycle: {workspace: state file}}` from `workspace_backend(ws).state_location(ws)` per builder, which the core writes as the `# state: workspace <ws> -> <location>` header line of each lifecycle's runner script |

A tree with no terraform roots installs the same hooks and they find
nothing to say: no workspace is bound, so nothing is checked, recorded
or listed.

## Tests

[`tests/test_roots.py`](tests/test_roots.py) pins the root mixin against
a bare run holder (the workspace suite's `v2_support.bare_run`, which
offers what the mixin reads of a context): the dry-run and real-run
`init` arguments, the runner's own `init`, the backend path, one
executable copy per command. The terraform roots have no unit test of
their own here: their behaviour is pinned through the root plugins that
subclass them (their module-call tests), through the golden emission of
the frozen fixture ([tests/test_v2_golden.py](../../tests/test_v2_golden.py))
and through the neutral-root test
([tests/test_v2_stage_120_neutral_root.py](../../tests/test_v2_stage_120_neutral_root.py)),
which holds the import graph, the declared dependencies and an isolated
install to the rule that no root plugin depends on another provider's
root. The run hooks are exercised by the workspace suite's state-location
tests ([tests/test_v2_state_locations.py](../../tests/test_v2_state_locations.py)):
the collision refusal, the move guard, the record and the header lines.
The package's tests borrow the S3 kind from `tf-s3-state-plugin` to
build registrations, so they need that package installed (the workspace
always has it).

## Prerequisites and integration

**This is a library, not a plugin.** Nothing here answers a `type:`,
nothing here loads configuration, and no configuration file names this
package; its one entry point is the hook set above. It is installed as a
workspace member from the root [pyproject.toml](../../pyproject.toml) by
`just init`, and every root plugin pins it at the same version. There is
no account, role, API or credential of its own. What its OUTPUT needs at
execution time is listed here, because the commands this package emits
are the ones the operator sees fail.

- **A tofu or terraform binary, found through the builder.** Every
  command the mixin emits is a copy of the executable the root's builder
  names in its `executable:` field (default `tofu` on the storage and
  instance models), which must be an entry in `cfg/executables.yml`
  ([CONFIGURATION section 3](../../docs/CONFIGURATION.md)). The entry's
  `binary` is what runs and what `gate-plan --tofu` and the
  `state-migration` steps are handed. This package sets no version floor;
  the entry's `version` requirement is what `validate` and every run
  check, and the fixture's floor is `>1,<2` on
  `open-tofu-1`. The flags the mixin emits (`-backend=false`,
  `-reconfigure`, `-migrate-state -force-copy`, `-detailed-exitcode`,
  `-replace=`, `-input=false`, `-out=`) exist on OpenTofu 1.x and
  Terraform 1.x alike.
- **`rm` on `PATH`.** Step 1 of every gated sequence is `rm -f tfplan`.
- **The state backend's own prerequisites.** The bucket, the AWS profile,
  the lock service and the credentials belong to the state plugin whose
  kind renders the backend file ([tf-s3-state-plugin](../tf-s3-state-plugin/README.md),
  [local-state-plugin](../local-state-plugin/README.md),
  [gcs-state-plugin](../gcs-state-plugin/README.md)). This package only
  writes what the kind returns into `.tfbackend.hcl` and hands the file
  to `init`. A real run's `init -reconfigure -backend-config=<file>`
  therefore needs a live session for that backend (an AWS SSO session
  for S3); a dry run's `init -backend=false` needs none.
- **The provider credentials.** `okta`/`oktapam` (`OKTA_API_*`,
  `TF_VAR_<team>_key`/`_secret`), AWS and GCP credentials are declared,
  wired and documented by the plugins that configure those providers;
  the collector passes their `config` through `hcl_value` and adds the
  alias.
- **A configuration root, for the mirror.** `plaintext_read_commands` and
  the `..._with_config` system commands read `working_path` and
  `generation_path` from the run context to compute `_private/...`.
  Outside a run (the bare harness) they degrade: the commands run in
  `generated/` and no `--root-dir` is rendered.
- **The sensitive data source's own needs** (the `hashicorp/external`
  provider, the system's CLI for `decrypt --json`, `CSIS_CONFIG_IDENTITY`
  for whoever plans) are the collector's and are listed in
  [hashicorp-utils](../hashicorp-utils/README.md#prerequisites-and-integration).

**What depends on the roots.** The three provider root plugins subclass
`TofuInstanceBuilderBase` and `TofuStorageBuilderBase` and register
`TofuVersionChecker`: [tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md)
(AWS, which also depends on `aws-runtime-plugin` for its boto3 session),
[tf-gcp-plugin](../tf-gcp-plugin/README.md) (Google Cloud) and
[tf-docker-plugin](../tf-docker-plugin/README.md) (a container daemon).
Each depends on this package and on its own runtime plugin, and on no
other provider's root plugin. A provider's prerequisites (the account,
the credentials, the CLI the transition scripts call, the network) are
that plugin's and are listed in its README; what the roots emit needs
only what is listed above.

Integration points the rest of the system relies on:

| Reader | What it takes | Where it lands |
| --- | --- | --- |
| the core's runner (`run_lifecycles` in [`run_lifecycles.py`](../base/src/cs_image_system/base/commands/run_lifecycles.py)), through the hook set | `lifecycle_state_bindings(ctx)` | the `# state: workspace <ws> -> <location>` header lines of each runner script and the run summary |
| the same, after a lifecycle generates | `record_state_locations(ctx, lifecycle)` | `meta-state/state-locations.yaml` |
| `validate` in [`validate.py`](../base/src/cs_image_system/base/commands/validate.py), through the hook set | `state_location_problems(ctx)` | validation errors naming the workspace, the backend and the shared object or the unsafe move |
| the three root plugins and the identity roots | the two bases, the mixin and `TofuVersionChecker` | every terraform root the system emits |

## Configuration reference

This package owns no YAML key. What it reads, it reads through the
builders that subclass it and through the run context. The table lists
every configuration field whose value reaches this package, who hands it
over, and what the package does with it; the fields that reach the
collector itself (the required providers, the state backends, the gate
flag) are in
[hashicorp-utils](../hashicorp-utils/README.md#configuration-reference).

| Field (file) | Type | Default | Handed over by | What this package does with it |
| --- | --- | --- | --- | --- |
| `executables[].binary`, `.name`, `.prepended_arguments`, `.appended_arguments` (`cfg/executables.yml`) | see [section 3](../../docs/CONFIGURATION.md) | | the root builder's `get_executable_copy()` | Every tofu command is a deep copy of the entry named by the builder's `executable`; the mixin sets `args` and `working_directory` on the copy and passes `binary` (else `name`) to `gate-plan --tofu` and the `state-migration` steps. `version` is checked against `TofuVersionChecker`'s reading of `<binary> --version -json` by the base library's version-check machinery. |
| `<builder>.executable` (instance, storage, group, user builders) | str or null | `tofu` | `BuilderBase.get_executable_copy()` | Selects the entry above. Missing from `cfg/executables.yml`: `ValueError` at the first command. |
| `<builder>.required_plugins[]` / `required_providers[]` (`name`, `version`, `source`, `config`) | list of `TFTofuPluginModel` | `[]` | instance and storage builders (`required_plugins`), the Okta workspace mixin (`required_providers`) | Handed to the run's collector: `require_provider(ws, name, source, version)` per entry; merged, conflict-checked, emitted into `required_providers {}`. `name` and `version` are required by `GenericPluginModel` ([`hashicorp_models.py`](../hashicorp-utils/src/cs_image_system/hashicorp_utils/hashicorp_models.py)); `source` is optional and omitted from the block when absent; `config` is read by the Okta builders (provider arguments) and ignored by the storage and instance builders. An empty list on a storage or instance root falls back to the provider's own bare requirement (`_provider_name()` from `_provider_source()`: `aws` from `hashicorp/aws` on the AWS roots, `google` from `hashicorp/google` on the GCE roots, `docker` from `kreuzwerker/docker` on the container roots) with no version. |
| `<builder>.state_configuration` (instance, storage, group, user builders) | str | `default` | `bind_workspace(ws, own, runtime's)` | First rung of the chain. A value outside `default`, `self`, empty, unset names a backend registration; the name must exist (`validate` refuses one that does not). `none` is refused by `validate` by name: it would read as unset. |
| `runtime_builders[].state_configuration` (`cfg/runtime-builders.yml`) | str | `default` | `runtime_state_configuration()` of the root mixin, as the second argument of `bind_workspace` | Second rung, for storage and instance roots only. |
| `config.apply_identity`, `apply_storage`, `apply_instances` (`cfg/_config.yml`) | bool or list[str] | `false` | the builder, as the `apply` argument through `apply_enabled(key, root, aliases)` | Decides whether the sequence ends in `apply-check` + `apply`. Re-read at execution by `apply-check`, which this package emits with the lifecycle key, root and aliases. |
| run options `--dry-run`/`--no-dry-run`, `--migrate-state <root>`, `--overlay <file>`, `--apply-runtime <rt>` | CLI | dry run on | the run context (`dry_run`, `migrate_state`, `overlays`, `apply_runtime`) | See the variations below. |

### Variations

- **Dry run vs real run (generation-time init).** With `--dry-run` (the
  default) `_init_args` is `init -backend=false`: providers are installed,
  the emission is validated, and the state bucket is never opened. With
  `--no-dry-run` it is `init -reconfigure -backend-config=<file>` when the
  workspace has a backend and backends are enabled, else `init`. The
  identity builders also skip their generation-time `plan` in a dry run
  (the user builder logs `dry run, 'plan' not run at generation time`);
  the storage and instance builders never plan at generation time.
- **Dry run vs real run (the deferred sequence).** The sequence is
  emitted identically in both modes, always with the real-run init
  (`_runner_init_args`). A dry run only enumerates it; a real run
  executes it in process and the committed script carries it either way.
- **Migrating vs not.** When the root's name is in `--migrate-state`, the
  runner's init becomes `state-migration begin` + `init -input=false
  -migrate-state -force-copy -backend-config=<file>`, the plan carries
  `-detailed-exitcode` so any change stops the runner, and
  `state-migration finish` follows the gate. Otherwise the init is
  `-reconfigure` ("do not migrate") and there are no migration steps. A
  dry run refuses the flag before this package sees it.
- **`replace` given vs empty.** Each address becomes `-replace=<address>`
  on the plan and `--allow-destroy <address>` on the gate, so the
  replacement's destroy passes and nothing else does. The instance builder
  fills it from pending upgrades and follow moves.
- **`allow_destroy` given vs empty.** Each address is whitelisted at the
  gate. Empty: every planned destroy fails the gate with
  `DESTROY NOT WHITELISTED`.
- **`require_unmounted` given vs empty.** Each `<instance>:<storage>` pair
  makes the gate demand a successful receipt in `./unmount-receipts`
  before it even reads the plan; missing, `DETACH NOT UNMOUNTED`, exit 3.
- **`pre_plan` given, with or without `pre_plan_backup`.** The argument
  lists run between init and plan as tofu commands. With
  `pre_plan_backup=True` a `state-migration backup` step precedes them;
  with `pre_plan` empty the backup flag does nothing, by decision: the
  flag covers the `pre_plan` lines alone, and
  a pre-command that removes state, such as the identity runner's prune
  step, takes its own backup, so a run never pulls state twice for one
  removal and never backs up a run that removes nothing. The group builder
  passes `state rm module.group_<name>` for a newly unmanaged group with
  the backup on.
- **`pre_commands` given vs empty.** Executables inserted verbatim after
  `pre_plan` and before the plan (the instance root's unmount steps, the
  identity root's `prune-attachments`).
- **`apply` true vs false.** False: the sequence ends at the gate (or at
  `state-migration finish`); the root plans and gates and nothing changes.
  True: `apply-check` (when `apply_flag_key` is given) and `apply
  -input=false tfplan` follow.
- **`apply_flag_key` with or without `apply_root`.** Without a root, the
  emitted `apply-check` re-checks the lifecycle flag as a whole; with a
  root and aliases, a list-valued flag is re-checked for that root by
  builder name or runtime. The run's `--overlay` files are carried as
  `--overlay <file>` and `--apply-runtime <rt>` as itself, so the
  execution-time check reads the flags as generation did.
- **In a run vs outside one.** Inside a run `plaintext_read_commands`
  materialises the root into `_private/` and runs there; outside one it
  runs in place. `run_is_dry` answers false outside a run.

## What it tests and verifies

At load, the two model bases validate what every root declares (pydantic
dataclasses under the contract's model configuration: `executable`,
`required_plugins`, `state_configuration`, and a storage root's
`variables`). The rest runs at generation, at `validate` through the run
hooks, and inside the commands the roots emit.

**At generation (the terraform roots).**

- A subclass that answers no `_provider_name()`, `_provider_source()`,
  `_provider_config()`, `_module_dirname()` or `_module_resource()` --
  `NotImplementedError` naming the class (`<Class> must name its
  provider`, `... must name its provider's source`, `... must configure
  its provider`, `... must name its terraform module`, `... must name
  its instance resource`) from the first generation that needs the
  answer; an unanswered `_module_args`, `_launch_args`, `module_args` or
  `_lookup` raises a bare `NotImplementedError` from the first module
  call or state query. A builder entry whose `type:` names a provider's
  shared storage base (`tf-aws`) reaches the module-dirname refusal; the
  GCP one (`tf-gcp`) is refused by its model at load instead.
- A storage whose allowed group has no identity builder, or whose
  identity builder supplies no gid -- `ValueError` from `gid_reference`
  naming the builder and the group.
- An instance with no provider-specific image on the builder's runtime
  -- a warning, and a module call without an image argument (the plan
  fails later, in the module).

**At plugin load (the registry).** `TofuVersionChecker` registered by
several root plugins under one name is one registration; a *different*
class registered under a name the registry already holds is
`ValueError: Type Collision: <name>`, and the load stops.

**At `validate` (the run hooks of this package).** Every root's
backend name resolves to a registration, every location is well-formed,
no two collide, and a root whose location differs from the record while
resources stand in it is refused (`state_location_problems` in
[`hooks.py`](src/cs_image_system/tofu_roots/hooks.py), which the core
runs as a validator). The verdicts are validation errors (`validate` exit
1; `run` exit 1 before generation).

**At execution (the commands this package emits; the checks live in
[`gate.py`](../base/src/cs_image_system/base/commands/gate.py),
[`state_migration.py`](../base/src/cs_image_system/base/commands/state_migration.py)
and the [system CLI](../system/src/cs_image_system/system/cli.py)).**

| Step | Checks | Verdict |
| --- | --- | --- |
| `rm -f tfplan` then `plan -out=tfplan` | a failed plan leaves no file | the runner stops at the plan under `set -euo pipefail` |
| `gate-plan --planfile tfplan` | the planfile exists and is newer than the root's newest `*.tf`; every planned destroy is whitelisted; every `--require-unmounted` pair has a successful receipt | `STALE PLANFILE: ...`, `DESTROY NOT WHITELISTED: <address>`, `DETACH NOT UNMOUNTED: <pair>` on stderr, exit 3; `Plan passes the apply gate.` on success |
| `apply-check --lifecycle <key> ...` | `cfg/_config.yml` is found walking up from the working directory; every `--overlay` still exists; the flag allows this root NOW | `apply_<key> is false NOW in <file> for root '<root>' -- this runner script was generated when it allowed the apply; not applying.`, exit 3; `apply_<key> allows ...; proceeding.` on success |
| `state-migration backup` | the root is an initialised terraform root and its location holds state | `state backup for workspace '<ws>' REFUSED/FAILED ...` in the log, exit 1, nothing removed from state; on success an INFO line with the serial, the resource count and the backup path |
| `state-migration begin` | the new location is empty or holds this workspace's lineage; the old state pulls | refused as a collision, or the backup written beside the root and the move logged |
| `plan -detailed-exitcode` (migrating) | the plan at the new location reports no changes | exit 2 from tofu stops the runner before the gate |
| `state-migration finish` | the begin record exists | the move recorded in meta-state and the location record moved |
| `apply -input=false tfplan` | tofu's own | the runner stops on failure; the after-apply hooks never run |

**Not checked here.** The comparison of the tool's version with the
entry's requirement (the base library's version-check machinery, fed by
`TofuVersionChecker` here); everything the collectors check as a root
registers and generates ([hashicorp-utils](../hashicorp-utils/README.md#what-it-tests-and-verifies):
provider conflicts, variable redefinition, backend registration, the
collision rule); the plaintext guard over `generated/` (the base
library's, at `validate` and every commit).

## When it fails

Incidents that have happened, with their cause and fix, are recorded on
[INCIDENTS.md](../../docs/INCIDENTS.md); what follows keeps each
failure's symptom, its meaning and what to do.

The commands this package emits are the ones the operator sees fail, so
the table covers the messages of the emitted sequence as well as the
exceptions the roots raise. The exceptions the collectors raise while a
root registers and generates (provider conflicts, a rebound workspace, a
state location collision, a backend without a kind) are
[hashicorp-utils](../hashicorp-utils/README.md#when-it-fails)'. Each row
is the symptom, what it means and what to do.

| Message or symptom | Meaning | Where to look, what to do |
| --- | --- | --- |
| `oktapam` fails on refresh with `user "x" is not present within group "g"` during the group root's plan | state still holds an attachment the roster dropped by hand; a refreshing plan asks the provider for it | the identity runner's `prune-attachments` step runs between init and plan for exactly this, and the group root's generation-time plan runs `-refresh=false`; the prune step's log lines name each attachment and why it was kept; the repair is a `state rm` after the backup the step already took |
| a generation-time plan reports unknown users whose addresses are derived (`first.last@ENC[age:...]`) | the plan ran against the committed ciphertext instead of the plaintext mirror; the Okta lookups search by the derived address | the command's working directory in the run log must be under `_private/` (`plaintext_read_commands` materialises the root there, initialises there and plans there, exactly as the runner does) and `CSIS_CONFIG_IDENTITY` must be set for the materialisation |
| `Module not found` or `Unreadable module directory` from an init whose working directory is under `_private/` | the mirror stands at the wrong depth, so every relative module source counts up to the wrong directory | `_private/` must replace `generated/` at the same depth (`mirror_path` in the base library); compare the mirror path against the `generated/` one |
| a committed runner script fails at its first `tofu plan` on an uninitialised root | a dry run's generation-time init is backend-less and a fresh clone has no `.terraform/` at all | every gated sequence begins with the runner's own `init -input=false -reconfigure [-backend-config=<file>]`; a script without that line was not generated by this package: regenerate |
| `init` fails with a provider-cache or lock error while something else runs tofu | two tofu processes share `TF_PLUGIN_CACHE_DIR`, which is not safe under concurrent `init` | run alone; the recipes that execute roots pass `--locked` |
| `Executable '<key>' not found for builder '<name>' of type '<type>'` (`ValueError`) | the builder's `executable` names no entry in `cfg/executables.yml` | add the entry or fix the name; `validate` also reports unresolved foreign keys |
| `NotImplementedError: <Class> must name its provider` (or `... its provider's source`, `... must configure its provider`, `... must name its terraform module`, `... must name its instance resource`) at generation | a root subclass left a hook with no default unanswered, or a builder entry's `type:` names a provider's shared storage base (`tf-aws`) rather than a service | a plugin defect when the class is a provider's root: answer the hook; a configuration error when the class is a shared base: use the service type (`tf-aws-ebs`, `tf-aws-efs`, `tf-aws-s3`) |
| `ValueError: Type Collision: <name>` at plugin load | two plugins register *different* classes under one service name (the same class from several plugins, as `TofuVersionChecker` is, is one registration) | the two plugins' `initialize()`; rename one service or share the class |
| `Storage builder <B>: group '<g>' has no identity builder` / `... supplies no gid` (`ValueError`) at generation | a storage's allowed group is owned by no group builder, or by one that answers no gid expression | declare the group under a group builder that supplies gids, or remove it from `groups:` (`validate` usually reports the unknown group first) |
| `Working directory for commands in phase <phase> cannot be None for builder <class>` (`AssertionError`) | a plugin called `terraform_commands` with no directory | a plugin defect |
| tofu: `Backend configuration changed` | a hand `tofu init` without `-reconfigure` in a root the system initialised, after a backend argument (`encrypt`, for example) changed; the state is remote, so nothing needs migrating | run the system's form (`init -reconfigure -backend-config=<file>`), never `-migrate-state` by hand (that flag is reserved for `--migrate-state`) |
| tofu: `Error: Backend initialization required` or a plan in `generated/` that reads ciphertext | the root was not initialised where the command runs | the deferred sequence initialises itself; a generation-time plan runs in `_private/`; check the working directory in the log |
| `STALE PLANFILE: ...` (exit 3) | no `tfplan`, or one older than the newest `*.tf`: the plan step produced no file, or the root was regenerated after the plan (`rm -f tfplan` is step 1 of every sequence so the gate never judges the previous sequence's plan) | read the plan's own error above it in the runner output; rerun the sequence |
| `DESTROY NOT WHITELISTED: <address>` (exit 3) | the plan destroys something no operation asked for | OPERATIONS "The apply gate": a decommission, an upgrade, a storage state change or a detach are the only whitelists; a zone or a module change that forces replacement is refused here by design |
| `DETACH NOT UNMOUNTED: <instance>:<storage> has no successful unmount receipt` (exit 3) | a detach planned without the unmount | `unmount storage ...` first (or `--confirm`), then rerun |
| `apply_<lifecycle> is false NOW in <file> for root '<root>' -- this runner script was generated when it allowed the apply; not applying.` (exit 3) | the script is older than the configuration, not wrong: `apply-check` re-reads the flag at execution so a runner generated under yesterday's flags cannot apply under today's | regenerate, or turn the flag back on deliberately |
| `apply-check: no cfg/_config.yml found from the working directory up; refusing to apply` (exit 3) | the runner runs outside a configuration tree | run it from its own directory in the tree (`final_execution.sh` does) |
| `apply-check: overlay <path> is gone; refusing to apply` (exit 3) | an overlay the run was generated under was deleted | restore it or regenerate |
| `state backup for workspace '<ws>' REFUSED: <dir> is not an initialised terraform root` / `... the location holds no state, yet a state rm is due` (exit 1) | the backup that precedes a `state rm` cannot see the state | the root's init failed or bound to an empty location; nothing was removed; fix the binding, rerun |
| a migrating runner stops after `plan -detailed-exitcode` with exit 2 | the plan at the new location is not clean | OPERATIONS "Where state lives": the move is accepted only clean; the backup is beside the root, the old location untouched |
