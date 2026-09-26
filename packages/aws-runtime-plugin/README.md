# cs-image-system-aws-runtime-plugin

The `aws` runtime type. A runtime is where images are baked and instances
run; this package makes Amazon EC2 one. It registers one runtime model
(`AwsCloudBuilderModel`), one runtime builder (`AwsCloudBuilder`) and one
version checker (`AwsCLIVersionChecker`, for the `aws` CLI). At load it
discovers the account's VPCs, subnets and security groups with boto3 and
checks the declared networking against them. During a run it resolves vendor
AMIs by owner and filter, emits the `amazon-ebs` packer source for every image
baked here, bakes and reaches instances through AWS Systems Manager (SSM),
answers the state query from `describe-images` / `describe-instances`, reads
and (for one bounded task at a time) sets an instance's power state, tags
released AMIs, and disposes of AMIs together with their snapshots.

## What it registers

The entry point is declared in [pyproject.toml](pyproject.toml):

```toml
[project.entry-points."cs_image_system.plugins.runtime"]
aws_plugin = "cs_image_system.aws_runtime.main:initialize"
```

`initialize()` in [main.py](src/cs_image_system/aws_runtime/main.py) returns an
`AwsRuntimePluginMetadata` whose services map the key `aws` to three classes
and whose `builders_for_models` binds the model to its builder.

| Class | `csis_name()` | `csis_classifier()` | Registered under |
|---|---|---|---|
| `AwsCloudBuilderModel` ([aws_runtime_models.py](src/cs_image_system/aws_runtime/aws_runtime_models.py)) | `aws` | `VCT.CLOUD_BUILDER_MODEL` | `cloud_builder_model` and, because the loader re-registers cloud models as runtimes, `runtime_builder_model` |
| `AwsCloudBuilder` ([aws_runtime_builders.py](src/cs_image_system/aws_runtime/aws_runtime_builders.py)) | `aws` | `VCT.RUNTIME_BUILDER` | `runtime_builder` |
| `AwsCLIVersionChecker` ([aws_runtime_builders.py](src/cs_image_system/aws_runtime/aws_runtime_builders.py)) | `aws-cli` | `VCT.VERSION_CHECKER` | `version_checker`, since stage 48.1 (2026-09-17) |

A YAML entry selects the model and builder with `type: aws` under
`runtime_builders:`. There are no type aliases; `aws` is the only type key.
An entry's own `aliases:` list gives that runtime extra names (the fixture's
`aws-east2-runtime` also answers to `aws`, `amazon` and `us-east-2`), and
other entries refer to it by any of them.

The version checker is selected differently: `validate` and every run look
up a checker for each entry of `cfg/executables.yml` under the entry's
`name` first, then its `type` (see
[validate.py](../base/src/cs_image_system/base/commands/validate.py)). An
executable named `aws-cli` therefore gets this checker, which runs
`<binary> --version` and reads the version from the regex
`aws-cli\/([\d\.]+)\s` on the first output line (`aws-cli/2.32.0 Python/...`).
An entry named anything else with `binary: aws` falls to the generic
checker.

Present in the package but not registered as a service:

- `AwsProviderSpecificImage` ([aws_provider_specific_image.py](src/cs_image_system/aws_runtime/aws_provider_specific_image.py)), reached through the builder's `provider_specific_image_class()` hook.

## Models

### `AwsCredentials`

Extends `CredentialsBase` in
[credentials.py](../base/src/cs_image_system/base/models/credentials.py).
The base declares no fields; each provider narrows it. Field names are
boto3 `Session` keyword arguments and pass straight through.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `profile_name` | `str \| None` | `None` | A named profile in the operator's AWS configuration. The fixture uses `noaa`. |
| `aws_access_key_id` | `str \| None` | `None` | Key id; carries a template such as `{{ ENV['AWS_ACCESS_KEY_ID_east2'] }}`, never a literal. |
| `aws_secret_access_key` | `str \| None` | `None` | Secret; same rule. |
| `aws_session_token` | `str \| None` | `None` | Session token; same rule. |

`as_dict()` omits unset fields, so an absent key never reaches boto3 as
`None`. The shared model config forbids extra keys, so a misspelled key
inside `credentials:` is a validation error naming the field path. No
credential value belongs in the configuration tree: these fields name a
profile or read the environment.

### `AwsCloudNetworkingModel`

Extends `CloudNetworkingConfig` in
[cloud_builder.py](../base/src/cs_image_system/base/models/cloud_builder.py),
which is `RuntimeNetworkingModel` in
[runtime.py](../base/src/cs_image_system/base/models/runtime.py) under
another name.

Fields it adds:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `addl_security_groups` | `list[str]` | `[]` | Existing groups every launched instance also wears, unmodified. Checked against the account at load and the only list counted toward the limit of five below. The instance module's `vpc_security_group_ids` lists them after the generated group; the EFS storage builder uses them as the mount targets' client groups. |
| `ssh_ingress_security_group_ids` | `list[str]` | `[]` | Groups whose members may reach port 22 on launched instances. The generated instance security group's ingress references only these groups, never a CIDR range. Not checked against the account. |
| `_model_id` | `str \| None` | `None` (not an init field) | Back-reference to the owning runtime model. |

Base fields it inherits:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | `str` | the network id | Empty or `default` falls back to `network`. |
| `network` | `str` | `default` | The VPC id. `default` resolves at load to the account's default VPC. |
| `subnets` | `list[RuntimeSubnetModel]` | required, non-empty | Each has `name`, `subnet_id`, `is_default`, `public`, `cidr`, `availability_zone`, `config`. The first entry with `is_default: true` is the default subnet; without one the model refuses to load. |
| `availability_zones` | `list[RuntimeAvailabilityZoneModel]` | `[]` | `name`, `is_default`. The default zone, when declared, becomes the packer source's `availability_zone`. |

It strips `name` and refuses one that is empty afterwards (only a
whitespace-only name can reach that check, because the base already
substitutes the network id for an empty or `default` name).
`get_subnet_id()` raises when no default subnet exists. It does not accept
security groups by name, only by id, and it refuses more than five groups in
`addl_security_groups`.

There is no `security_group_ids` field any more (stage 63). Until
2026-09-25 the model accepted it, checked its ids against the account and
counted them toward the limit of five, but no emitter ever read it, so a
group listed there reached neither the packer source nor the instance and
storage roots. It was removed rather than wired in, because
`addl_security_groups` already is the list that reaches the roots. Declaring
it is now an unknown-key refusal at load (the shared model config forbids
extra keys), and the error names the key; move the ids into
`addl_security_groups`. The accessor `get_security_group_ids()` went with
it; `get_addl_security_groups()` remains.

### `AwsCloudBuilderModel`

Extends `CloudBuilderModel` in
[cloud_builder.py](../base/src/cs_image_system/base/models/cloud_builder.py),
which extends `RuntimeBuilderModel` in
[runtime.py](../base/src/cs_image_system/base/models/runtime.py), which
extends `BuilderModel` and `NameTyped` in
[builder_model.py](../base/src/cs_image_system/base/models/builder_model.py).

Fields it adds:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `account_id` | `str \| None` | `None` | The AWS account. Reported by `runtime describe`; usable in templates as `{{ this.account_id }}`. Nothing else reads it: the account boto3 acts in is the profile's. |
| `credentials` | `AwsCredentials` | empty | Narrows the base `CredentialsBase`. |
| `state_configuration` | `str` | `DEFAULT` | Foreign key to a state backend. The second rung of every storage and instance root's backend resolution on this runtime: a root whose own `state_configuration` is `default` inherits this one; `default` here falls through to the default backend (stage 46.2, [orchestrator.py](../base/src/cs_image_system/base/orchestrator.py)). |
| `ena_support` | `bool \| None` | `None` | When declared, written into the `amazon-ebs` packer source as `ena_support = true\|false`, so the baked AMI's Elastic Network Adapter flag is set explicitly; unset, nothing is written and packer's default applies (stage 63; until 2026-09-25 accepted and read by nothing). |
| `sriov_support` | `bool \| None` | `None` | When declared, written into the `amazon-ebs` packer source as `sriov_support = true\|false` (enhanced networking through the Intel SR-IOV interface); unset, nothing is written and packer's default applies (stage 63; until 2026-09-25 accepted and read by nothing). |
| `iam_instance_profile` | `str \| None` | `None` | Instance profile written into the packer source for build instances when `session_instance_profile` is unset (it is also the SSM fallback then). When both are set the SSM profile wins (stage 63 item 9, decided 2026-09-24; until then this one, written after the SSM block, replaced it). Never attached to launched instances. |
| `session_mechanism` | `str \| None` | `None` | `ssm` (any case, surrounding whitespace ignored) is the only value. Any other string is an error the first time the builder's `session_mechanism()` is called, which is at generation. |
| `session_instance_profile` | `str \| None` | `None` | The SSM-capable instance profile given to launched instances (through the instance plugin) and to build instances (through the packer source). |
| `ssh_username` | `str` | `DEFAULT` | The bake's SSH user for images on this runtime that name none more specifically: step 4 of the bake-user order ([CONFIGURATION 5.1.1](../../docs/CONFIGURATION.md#511-the-bake-ssh-user)). Until stage 63 it overrode every entry. |
| `networking` | `AwsCloudNetworkingModel \| None` | `None` | Narrows the base type and makes it optional. Missing networking logs a warning at load; image generation then fails (the packer source reads the VPC and subnet from it). |
| `vpc_map` | `dict` | discovered | Not an init field. `{vpc_id: {"subnets": [...]}}` from the account. |
| `default_vpc_id` | `str \| None` | discovered | Not an init field. |
| `all_security_groups` | `dict[str, dict]` | discovered | Not an init field. `{group_id: description}` from the account. |

Base fields it inherits, and what this runtime does with them:

| Field | From | Default | Meaning here |
|---|---|---|---|
| `name`, `type`, `description`, `aliases` | `NameTyped` | `name`/`type` required | `type` is `aws`. |
| `executable`, `is_default`, `config`, `gitignore`, `tags` | `BuilderModel` | | `tags` merge into every image's tags; `is_default` makes this the runtime `default` resolves to. |
| `region` | `CloudBuilderModel` | required | boto3 `region_name`, the packer `region`, the `aws` provider block, `--region` on the release and storage-transition commands. |
| `default_machine_type` | `RuntimeBuilderModel` | required | Instance type when neither an OS-builder runtime entry nor an image names one; the instance type of a launched instance that declares no `machine_type`. |
| `default_image_builder` | `RuntimeBuilderModel` | `DEFAULT` | The image builder an OS-builder runtime entry with `image_builder: default` resolves to. |
| `default_owners` | `RuntimeBuilderModel` | `None` | Joins every vendor-image query's owner list on this runtime, after the OS builder's owners and before the entry's own. Read since stage 63 item 22: the lookup in [os_builder_runtime_config.py](../base/src/cs_image_system/base/models/os_builder_runtime_config.py) keyed the runtime by the entry's `image_builder` name and never found it; it now takes the image builder's runtime. |
| `default_config_username` | `RuntimeBuilderModel` | `None` | The bake's SSH user when nothing more specific names one: step 5 of the bake-user order ([CONFIGURATION 5.1.1](../../docs/CONFIGURATION.md#511-the-bake-ssh-user)), read since stage 63 item 22. |
| `ephemeral` | `RuntimeBuilderModel` | `False` | See "Retention and the cycle". |
| `retention_keep` | `RuntimeBuilderModel` | `None` | Builds kept per series on this runtime when the image declares no retention. |
| `on_failure`, `teardown_after` | `RuntimeBuilderModel` | `None` | Runtime-level defaults for ephemeral instances. |

It overrides `finalize()` to run `update_networking()` after the base
finalization, and `csis_name()` to return `aws`. It carries the class
attribute `type = "aws"`.

Not supported: a top-level `profile:` key (the modelled key is
`credentials.profile_name`; unknown keys are rejected), a `parameters:` key
(retired; the load names the replacement), any session mechanism other than
`ssm`, and a run without a `region`.

## The builder

`AwsCloudBuilder` extends `CloudBuilderBase` in
[builder_base_cloud.py](../base/src/cs_image_system/base/basic/builder_base_cloud.py),
an empty specialisation of `RuntimeBuilderBase` in
[builder_base_runtime.py](../base/src/cs_image_system/base/basic/builder_base_runtime.py).
The runtime builder writes no files of its own: `generate_items_during`
defers to the base and returns nothing. Everything it contributes reaches
`generated/` through the image, instance and release builders that call its
hooks. In the order a run reaches them:

| When | Hook | What it does |
|---|---|---|
| Configuration load | `AwsCloudBuilderModel.finalize()` | Runs `update_networking()` (network discovery below). |
| Resolution | `provider_specific_image_class()` | Returns `AwsProviderSpecificImage`. |
| Resolution | `query_provider_image(subconfig)` | Finds the vendor AMI for one OS-builder runtime entry (image query below). Returns `(ami_id, owner, raw_result)` or `None`. |
| Resolution | `query_provider_image_by_id(subconfig, image_id)` | Stage 63: the AMI an entry pins with `image_id`, looked up with `DescribeImages` by id (`aws_utils._query_by_ami_id`) instead of the query. Same return shape; `None` when AWS does not know the id. |
| Image generation | `packer_source_type()` | `amazon-ebs`. |
| Image generation | `packer_source_blocks(...)` | The `data "amazon-ami"` lookup and the `source "amazon-ebs"` block for one image. |
| Image generation | `session_mechanism()` | `ssm` or `None`; raises on any other declared value. |
| Image generation | `session_agent_commands(os_family)` | Installs and enables the SSM agent on a base image; `dpkg` path for `debian`/`ubuntu`, `yum` path otherwise. Empty when no mechanism is declared. |
| Image generation | `session_verify_commands(os_family)` | Assertions that the agent is present and enabled. Empty when no mechanism is declared. |
| Image generation | `default_bake_user(family)`, `bake_ssh_username(image)`, `bake_finalize_commands()` | `default_bake_user`: the vendor AMI's user, `admin` for `debian`, `ubuntu` for `ubuntu`, `ec2-user` otherwise (the last step of the bake-user order). `bake_ssh_username` keeps the base `None`, so the ansible provisioner keeps its own user on AWS; no closing provisioner. |
| After a bake | `build_id_from_artifact(artifact_id)` | Base default: the packer manifest's `<region>:<ami>` becomes the AMI id. |
| After a bake | `retag_image(ami, tags)` | The packer plugin stamps the resolved `csis_parent` and `csis_fingerprint` onto every recorded build. |
| Instance generation | `session_instance_profile()` | The instance profile the instance module attaches when the mechanism is `ssm`; `None` otherwise. |
| Instance verification | `verify_instance(name, expected_build, expect_mounts, timeout)` | Over SSM: waits for the launch completion marker `/var/lib/csis/launch-applied`, counts mounts under `/mnt`, compares the booted AMI with the expected build. |
| Instance operations | `run_session_command(name, script, timeout)` | `AWS-RunShellScript` through SSM on the RUNNING instance whose `Name` tag matches; polls the invocation to completion. |
| Power state (stage 57) | `can_query_instance_power_state()`, `query_instance_power_state(name)` | `True`; EC2's `State.Name` mapped onto the system's vocabulary (`pending` -> starting, `running`, `stopping`/`shutting-down` -> stopping, `stopped`, `terminated` -> absent, no instance -> absent, anything else -> unknown); `None` only when the cloud could not be asked. |
| Power state (stage 57) | `can_set_instance_power_state()`, `start_instance(name, timeout)`, `stop_instance(name, timeout)` | `True`; `start_instances` / `stop_instances` followed by the EC2 `instance_running` / `instance_stopped` waiter (5 s delay, `timeout // 5` attempts). Only `running_for_task` calls them. |
| Identity (stage 58) | `can_query_instance_identity()`, `query_instance_identity(name)` | `True`; `{"instance_id": InstanceId, "provider_hostname": PrivateDnsName}` of the named instance whatever its power state, or `None`. |
| Release | `release_commands(build_id, tags)` | One `aws ec2 create-tags --region ... --resources <ami> --tags Key=..,Value=..` executable, with `--profile` when `credentials.profile_name` is set. Runs only under `--no-dry-run` and only when the global `apply_release` is true. |
| State reconciliation | `retag_image(image_id, tags)` | `create-tags` on one of the system's own AMIs (`lineage relabel`, `lineage restamp`). |
| Retention | `dispose_image(build_id)` | Deregisters the AMI and deletes every EBS snapshot in its block device mappings. A missing AMI returns `False` (already gone). |
| State query | `query_images(series)` | Every AMI owned by `self` that carries a `csis_series` tag: `{image_id, name, state, created, tags}`. |
| State query | `can_query_instance_boot_image()`, `query_instance_boot_image(name)` | `True`; the `ImageId` of the pending or running instance whose `Name` tag matches, or `None`. Read-only, never fatal. |
| `empty --runtime` | `inventory()` | Not implemented on AWS; the base raises `NotImplementedError`, so the emptiness check refuses this runtime. |

Every instance lookup above is by the EC2 `Name` tag, which the instance
module sets to the instance's declared name
(`tags = merge({ Name = var.name }, var.tags)` in
[tfmodules/aws_instance/main.tf](../../tfmodules/aws_instance/main.tf)). Two
lookups differ on purpose: `_running_instance` filters on `pending`/`running`
(the boot-image query, the session command), `_named_instance` takes any
state and prefers a non-`terminated` record (the power-state and identity
queries, start and stop), because EC2 keeps a `terminated` record visible for
about an hour after the machine is gone.

### Credentials

`AwsCloudBuilderModel.self_to_aws_client_config()` is the one conversion
point: `credentials.as_dict()` plus `region_name` from `region`. Every boto3
call in the plugin builds `boto3.Session(**config)` from it, so a
`profile_name` selects a profile and an empty `credentials:` lets boto3's
default chain run (environment variables, `AWS_PROFILE`, an instance role).
The same profile name is written into the packer source (`profile = "noaa"`
on both the data lookup and the source), passed as `--profile` to the release
command, and read by the state-backend, storage and instance plugins for
their provider blocks, backend files and transition scripts, so packer,
terraform and the plugin's own calls all authenticate the same way.

### Network discovery at load

`update_networking()` in
[aws_runtime_models.py](src/cs_image_system/aws_runtime/aws_runtime_models.py)
calls `get_vpc_map_and_default_vpc_id()` in
[aws_utils.py](src/cs_image_system/aws_runtime/aws_utils.py), which issues
`describe_vpcs`, `describe_subnets`, `describe_route_tables` and
`describe_security_groups` once each and builds:

- `vpc_map`: for every VPC, a `subnets` list of `{subnet_id, cidr, is_public, tags, config}`. A subnet is public when its effective route table (its own association, else the VPC's main table) has a `0.0.0.0/0` or `::/0` route whose gateway id starts with `igw-` or `vgw-`.
- `default_vpc_id`: the VPC with `IsDefault`.
- `all_security_groups`: every group by id.

Then it validates the declaration: `network: default` becomes the default
VPC (an error when the account has none); the VPC must exist; every
declared `subnets[].subnet_id` must be one of that VPC's subnets (stage 63,
below); every id in `addl_security_groups` must exist; more than five of
them is an error. The declared `subnets[].public` flag is the operator's
statement and is not overwritten by the discovered `is_public`.

The subnet check (stage 63) compares each declared `subnet_id` with the
subnets the account listed for the declared VPC in `vpc_map`. When a
declared id is not among them the load is refused with
`Subnet <id> (<name>) in networking configuration for AWS cloud builder
<runtime> is not in VPC <vpc>.` Until 2026-09-25 the declared subnet ids were
not checked at all, so a subnet from another VPC (or a typo) passed the load
and failed only at the first bake or apply. The check makes a claim only
when the account's answer lists subnets for the VPC: a VPC listed without
any subnets (an empty VPC, or a session that cannot see them) leaves every
declared subnet unchecked rather than refusing all of them. A load
therefore needs a live AWS session even for a dry run, and so does every
command that loads the configuration for another runtime (the GCE cycle
included).

### The image query

`query_provider_image()` takes one OS-builder runtime entry
(`OSBuilderBaseImageBuilderSubconfig` in
[os_builder_runtime_config.py](../base/src/cs_image_system/base/models/os_builder_runtime_config.py)).
`remap_for_image_query()` builds a `describe_images` request:

- `Owners` is the entry's `get_owners()`: the OS builder's owners, then the runtime's `default_owners`, then the entry's own, deduplicated in order (the runtime's were never found before stage 63 item 22).
- `query.filters` keys are mapped through `AWS_DI_MAP` (snake_case to EC2 filter names, `tag:<key>` kept), booleans lowercased, and `state: available` forced.
- Keys the map does not know go to a post-query exact-match filter on the result dictionaries.
- The rewrite works on a deep copy of the entry's `query` (stage 63). `get_query()` hands back the entry's own nested mappings, and until 2026-09-25 the rewrite injected `state: available` into the OS builder entry's own `filters` mapping on every resolution, so the loaded model changed each time an image was resolved. The entry is now left exactly as declared.

`query_image()` in [aws_utils.py](src/cs_image_system/aws_runtime/aws_utils.py)
runs that `DescribeImages` query (paging through `describe_images`), keeps
every match that agrees with the post-query filter, and returns the newest
by `CreationDate`, or `None` when nothing matches. Its docstring says so
since stage 63; the unreachable `raise` that used to follow the return is
gone. The builder then reads the owner straight from the AMI record,
`ImageOwnerAlias` (for example `amazon`) else `OwnerId` (the account id),
and returns `(ImageId, owner, raw)`; the base registers an
`AwsProviderSpecificImage` in the resolved state. A record with neither
field raises `Could not get owner alias or owner id ...`. Before stage 63 a
second, unreachable `Could not get owner` branch followed that one; it was
removed on 2026-09-25. No match returns `None`, and the base's resolve step
then fails the run.

When the entry declares `image_id` (stage 63), the base's resolve step
does not call `query_provider_image()` at all: it calls
`query_provider_image_by_id(entry, image_id)`, which runs `DescribeImages`
with `ImageIds=[<id>]` through `_query_by_ami_id` in
[aws_utils.py](src/cs_image_system/aws_runtime/aws_utils.py), with the
runtime's own client configuration (profile and region). The entry's
`owners` and `query` are not consulted. The owner is read from the record
the same way, `ImageOwnerAlias` else `OwnerId` (else `self`), and the
result is `(ImageId, owner, raw)`. An id AWS answers
`InvalidImageID.NotFound` or `InvalidImageID.Malformed` for, or one that
returns no image, gives `None`, and the base stops resolution with
`OS builder <name>: image_id '<id>' on runtime <rt> is not known to the
provider`; any other API refusal raises `AMIQueryError`. An AMI id is
regional, so a pinned id must exist in this runtime's region. Pinning
makes the base bake reproducible: the same vendor AMI every time, where
the query takes the newest match.

Stage 63 also removed helpers from
[aws_utils.py](src/cs_image_system/aws_runtime/aws_utils.py) that nothing
called: `get_ami_owner`, `get_ami_ssh_user`, `remap_for_aws`,
`_query_by_name` and `_build_ami_filters`. `_query_by_ami_id` (an exact
lookup by AMI id) was kept, and since stage 63 it is what
`query_provider_image_by_id()` calls.

`AwsProviderSpecificImage.get_query_assets()` gives the packer
`data "amazon-ami"` body:

- resolved: `filters = { image-id = "<ami>" }` plus `owners = ["<owner>"]` when known;
- deferred (an image a build produces later): `owners = ["self"]`, `filters = { name = "<pattern>*", root-device-type = "ebs", virtualization-type = "hvm", architecture = "<arch or x86_64>" }`, `most_recent = true`.

[tests/test_aws_provider_specific_image.py](tests/test_aws_provider_specific_image.py)
pins both shapes.

### The state query and instance hooks

`query_images`, `query_instance_boot_image`, `query_instance_power_state`,
`query_instance_identity`, `start_instance`, `stop_instance`,
`verify_instance`, `run_session_command`, `retag_image` and `dispose_image`
all go through `aws_utils.ec2_client()` / `aws_utils.aws_client("ssm", ...)`,
which build a client from the same session config. The state query in
[state_query.py](../base/src/cs_image_system/base/state_query.py) reads
`query_images` to classify `missing`, `foreign` and `changed` images, and
asks `query_instance_boot_image` only because `can_query_instance_boot_image()`
is `True`. When that answers `None` it asks `query_instance_power_state`
before calling the silence `unavailable`: a `stopped` machine becomes a
`note` in the report, not drift and not a failure to answer (stage 57).
`verify_instance` is the deferred verification step of the instance
lifecycle; `run_session_command` is how the system runs a script on an
instance (the unmount before a detach, the post-bake tests, the AltNames
write of stage 58). `query_instance_identity` feeds the generation ledger
and the alias pass in
[provider_aliases.py](../base/src/cs_image_system/base/provider_aliases.py).

### Retention and the cycle

The closing `retention` lifecycle in
[retention.py](../base/src/cs_image_system/base/retention.py) runs
`dispose image --retention` at execution time. For each series on this
runtime the number of builds kept is, in order: `0` when the runtime is
`ephemeral`, the image's `retention.keep`, the runtime's `retention_keep`,
else everything. Builds beyond that are disposed through `dispose_image()`,
except released builds and builds an instance is pinned to or was launched
from, which are reported as retention debt and kept. Declared storages are
never touched by retention.

`ephemeral: true` on an AWS runtime means nothing baked there survives a
successful run. The fixture's AWS runtimes are not ephemeral and declare no
`retention_keep`, so every AMI baked on them stands until an explicit
`dispose image`. `on_failure` and `teardown_after` on the runtime are the
defaults for its ephemeral instances: `keep` leaves a failed instance
standing and fails the run; `teardown` tears it down and still fails the
run; `teardown_after: "2h"` lets a later run tear a standing failure down.

### Cost posture

A run on an AWS runtime may leave standing: every AMI it baked and the
snapshots behind them (kept by default), every released AMI (exempt from
retention), the declared storages (managed by the storage plugins), every
non-ephemeral instance, and an ephemeral instance whose verification failed
under `on_failure: keep`. The packer build instance is terminated by packer;
`force_deregister = !var.release` lets a non-release rebuild replace an AMI
of the same name. Because `inventory()` is not implemented here,
`empty --runtime` cannot prove an AWS runtime empty; the state query and
`query_images` are the checks. An instance the operator switched off is
left off: the system never starts one except for a bounded task
(verification, the post-bake tests) and stops it again afterwards.

## Emission

The plugin's output is visible in the golden emission under
[tests/fixtures/v2_golden/generated](../../tests/fixtures/v2_golden/generated).

- [pckr-ebs-ans-image-generation-source-basic-rh-10-block-000.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-source-basic-rh-10-block-000.pkr.hcl):
  the `data "amazon-ami"` lookup (`filters`, `owners`, `profile`) and the
  `source "amazon-ebs"` block written by `amazon_ebs_source()` in
  [aws_packer_source.py](src/cs_image_system/aws_runtime/aws_packer_source.py):
  `source_ami`, `ami_name`, `instance_type` (the runtime entry's machine
  type, else the runtime default), `region`, `vpc_id`, `subnet_id` (the
  default subnet), the merged lineage `tags`, `profile`, `ena_support` and
  `sriov_support` only when the runtime declares them (stage 63; the
  fixture declares neither, so the golden source carries neither), and, because the
  runtime declares `session_mechanism: ssm`, `ssh_interface =
  "session_manager"`, `iam_instance_profile`, `associate_public_ip_address =
  false`, `ssh_timeout = "15m"` and a `user_data` script that installs the
  SSM agent on vendor images that lack it. `ssh_username` is what
  `cs_image_system.base.bake_user.resolve_bake_user` answers (the image's
  entry, the chain root's entry, `config_username`, this runtime's
  `ssh_username` and `default_config_username`, then the family's vendor
  user: `admin` for debian, `ubuntu` for ubuntu, `ec2-user` otherwise). `launch_block_device_mappings` uses the source
  AMI's real `RootDeviceName` (else `/dev/xvda` for debian and amazon roots,
  `/dev/sda1` otherwise), `gp3`, and `volume_size` from
  `lineage.bake_disk_size(ctx, image, runtime)` (stage 63), the one rule the
  input fingerprint also hashes: this runtime declares no
  `default_disk_size`, so for a base image it is the OS builder entry's
  `default_primary_disk_size` for this runtime when declared, else the OS
  builder's `default_primary_disk_size` (200); for an instance image its
  own `primary_disk_size`. The fixture's base images bake with
  `volume_size = 200`.
- [pckr-ebs-ans-image-generation-block-000-build.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-build.pkr.hcl):
  the `# debug session mechanism (ssm)` shell provisioner per base image
  (`session_agent_commands`) and the `# verify: SSM agent baked` lines inside
  the in-bake verification provisioner (`session_verify_commands`). The
  `amazon` entry in the neighbouring `-plugins.pkr.hcl` comes from the image
  builder's `required_plugins`, not from this package.
- [open-tofu-instance-generation.tf](../../tests/fixtures/v2_golden/generated/instance-image/open-tofu/instance-generation/open-tofu-instance-generation.tf)
  and
  [open-tofu-instance-generation-instance-test.tf](../../tests/fixtures/v2_golden/generated/instance-image/open-tofu/instance-generation/open-tofu-instance-generation-instance-test.tf):
  written by the instance plugin from this model. `provider "aws" { region,
  profile, alias }`; an `aws_security_group` whose port-22 ingress lists
  `ssh_ingress_security_group_ids` and no CIDR; the instance module's
  `subnet_id` (the default subnet), `vpc_security_group_ids` (the generated
  group, then `addl_security_groups`), and `iam_instance_profile`
  (`session_instance_profile`). The `.tfbackend.hcl` beside them carries the
  same `profile`, written by the state-backend plugin.
- [run-release.sh](../../tests/fixtures/v2_golden/generated/release/run-release.sh):
  carries the `aws ec2 create-tags` line from `release_commands()` when a
  release is declared. The golden declares none, so it is empty of them.
- Runtime facts: `cs-image-system runtime describe aws-east2-runtime`
  ([runtime_facts.py](../base/src/cs_image_system/base/commands/runtime_facts.py))
  reports `runtime`, `type`, `region`, `account_id`, `default_machine_type`,
  `ephemeral`, `retention_keep`, the `images`, `storages`, `instances` and
  `ephemeral_instances` declared on it, the `builders` bound to it and its
  `emission` directories. It is a command, not a file.

## Example configuration

From
[tests/fixtures/config/cfg/runtime-builders.yml](../../tests/fixtures/config/cfg/runtime-builders.yml),
the default runtime:

```yaml
runtime_builders:
  - name: aws-east2-runtime
    is_default: true
    aliases:
      - aws
      - amazon
      - us-east-2
    type: aws
    account_id: "514190660293"
    description: |
      AWS runtime builder for the {{ this.region }} region account {{ this.account_id }}.
    credentials:
      profile_name: noaa
    tags:
      Project: MyProject
      Environment: Development
    region: us-east-2
    # Debug sessions and bakes connect through SSM: no public IP, no SSH from outside.
    session_mechanism: ssm
    session_instance_profile: AmazonSSMRoleForInstancesQuickSetup
    default_machine_type: t2.micro
    default_image_builder: pckr-ebs-ans
    networking:
      # network is the VPC id
      network: vpc-0c78d0d63b7a100df
      # SSH reaches instances only through the session relay's group; no CIDR ingress
      ssh_ingress_security_group_ids:
        - sg-03015ec107ae5f81a
      # existing groups every instance also wears (never modified here)
      addl_security_groups:
        - sg-03015ec107ae5f81a
      subnets:
        - name: east2-az1-private
          subnet_id: subnet-09f79018af845358a
          is_default: true
        - name: east2-az2-private
          subnet_id: subnet-00075cfbfcbc8f2cf
        - name: east2-az1-public
          subnet_id: subnet-01e56d2f9c1c95cc8
          public: true
        - name: east2-az2-public
          subnet_id: subnet-0c127b762e075a94d
          public: true
```

The same file declares two more `type: aws` runtimes (`aws-east1`, `west1`)
with `network: default` and no session mechanism; they show the minimum an
AWS runtime needs: `name`, `type`, `region`, `credentials`,
`default_machine_type` and a `networking` block with one default subnet. The
live tree adds `availability_zone` to each subnet so that `validate` can
refuse a zone mismatch between an instance, its zonal storages and its
runtime's default subnet.

## Prerequisites and integration

Everything below exists outside the system. The plugin creates none of it;
the rule in [docs/OPERATIONS.md](../../docs/OPERATIONS.md) ("The system
generates no IAM changes; IAP, SSM and impersonation are operator wiring")
applies to all of it.

**An AWS account and a region.** The plugin finds the region in the
runtime's `region` field. It acts in whatever account the credentials
resolve to; `account_id` is a fact for `runtime describe` and templates, not
a check.

**Credentials.** Found through `credentials:` on the runtime, converted by
`self_to_aws_client_config()`:

- `credentials.profile_name` names a profile in `~/.aws/config` (fixture and
  live: `noaa`, an `sso-session` profile; `aws sso login --profile noaa`
  opens it). This is the operator's path.
- `credentials.aws_access_key_id` / `aws_secret_access_key` /
  `aws_session_token` carry `{{ ENV[...] }}` templates for static keys.
- An empty `credentials:` lets boto3's default chain run: `AWS_ACCESS_KEY_ID`
  and friends, `AWS_PROFILE`, an instance role.

botocore drops the environment credential provider when a profile is named,
so a named profile must itself carry credentials: in CI the workflow writes
a `[noaa]` shim into `~/.aws/credentials` from the federated keys (the
`[noaa]` profile shim in [docs/OPERATIONS.md](../../docs/OPERATIONS.md)).
`preflight` reads the same field (else `AWS_PROFILE`) to find the SSO cache
under `~/.aws/sso/cache` (`CSIS_AWS_DIR` overrides the directory) and
reports the token's expiry; static keys have no readable expiry.

Because `update_networking()` runs at configuration load, the session must
be live for every load, dry runs and GCE-only work included. An
`sso-session` profile's token renews itself only while the browser portal
session lives; a session that lapses mid-run costs the legs that were
running (2026-09-08, and again 2026-09-21).

**IAM permissions for the caller.** What the plugin itself calls, all with
the session above: `ec2:DescribeVpcs`, `DescribeSubnets`,
`DescribeRouteTables`, `DescribeSecurityGroups` (every load);
`ec2:DescribeImages` (resolution, the state query, disposal);
`ec2:DescribeInstances` (every instance lookup); `ec2:CreateTags` (retag,
and the release command through the CLI); `ec2:DeregisterImage` and
`ec2:DeleteSnapshot` (disposal); `ec2:StartInstances`, `ec2:StopInstances`
(the bounded power-state exception); `ssm:SendCommand` and
`ssm:GetCommandInvocation` (verification, unmounts, post-bake tests, the
alias write). Packer's bake and the tofu roots need their own permissions
on top, including `iam:PassRole` for the instance profile and
`ssm:StartSession` for the Session Manager communicator; the CI table in
[docs/OPERATIONS.md](../../docs/OPERATIONS.md) (`AWS_ROLE_ARN` read-only,
`AWS_APPLY_ROLE_ARN` write) lists the two roles the live job uses.

**Network.** Found through `networking:`: the VPC (`network`, or `default`
for the account's default VPC), the subnets by id, the security groups by
id. The fixture's VPC has no internet gateway, which shapes everything else:
bakes and instances go on the default (private) subnet with
`associate_public_ip_address = false`, egress is the subnet's NAT, and both
packer and the operator reach machines through SSM. The default subnet must
route to the SSM endpoints and to the package repositories the bootstrap
downloads from (`s3.<region>.amazonaws.com`); SSH ingress is by
security-group reference only (`ssh_ingress_security_group_ids`, the Okta
gateway's group), and the gateway relay requires the target to wear that
same group (`addl_security_groups`).

**An SSM-capable instance profile.** Found in `session_instance_profile`
(live: `AmazonSSMRoleForInstancesQuickSetup`), attached to launched
instances by the instance plugin and to build instances by the packer
source. Without it, `session_mechanism: ssm` still bakes the agent but
packer keeps the SSH communicator and instances get no profile. The role
behind it needs the SSM managed policy; the caller needs `iam:PassRole` on
it.

**Tools.** Found through `cfg/executables.yml`
([executables.yml](../../tests/fixtures/config/cfg/executables.yml)):

- `aws` (the entry named `aws-cli`, fixture floor `>=2.32`): the release
  command and the storage builders' transition scripts run it; its version
  is read by `AwsCLIVersionChecker` at `validate` and at every run.
- `packer` with the `amazon` plugin: declared on the image builder's
  `required_plugins`, not here; the source this package emits needs it.
- The AWS Session Manager plugin for packer's `ssh_interface =
  "session_manager"`: installed on the machine that bakes (CI installs it
  before the performing step). Not declared in the tree; packer fails
  without it.
- `tofu` with the `hashicorp/aws` provider for the instance and storage
  roots, declared on those builders.
- Python: `boto3>=1.43`, `botocore>=1.43`, `python-hcl2>=8.1`,
  `pydantic>=2.13`, and the `cs-image-system-hashicorp-utils` package for
  the HCL formatter ([pyproject.toml](pyproject.toml)).

**Vendor images.** Found through the OS builders' `owners` and `query`
(fixture: AlmaLinux 10 from owner `764336703387`, the Debian images by
family name). The account must be allowed to see and launch them (Allowed
AMIs, Marketplace subscriptions where they apply).

**Instances reachable by name.** The instance module tags every machine
`Name=<declared name>`; every lookup in this plugin depends on that tag and
on the SSM agent being registered on the machine (baked in by
`session_agent_commands`, bootstrapped by the source's `user_data` on a
vendor image that lacks it). The launch script writes
`/var/lib/csis/launch-applied` as its last act; verification waits for it.

**Nothing from the identity side.** Enrollment, OPA and `sft` are the
identity plugins' concern; this plugin only runs their scripts on the
machine over SSM when asked.

## Configuration reference

Every field the plugin reads from the YAML it owns (the `type: aws` entry
under `runtime_builders:`). The base's own fields are included because this
plugin is what reads them on AWS. Types are the model's; `default` in a
value column means the literal string `default`.

### The runtime entry

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | The runtime's name; the value other builders' `runtime:` and the lineage records carry. |
| `type` | str | required | `aws`. |
| `description` | str or null | null | Free text; templates such as `{{ this.region }}` resolve. |
| `aliases` | list[str] | `[]` | Extra names the runtime answers to. |
| `is_default` | bool | `false` | The runtime `default` resolves to; at most one per class. |
| `tags` | mapping[str, str] | `{}` | Merged into every image's tags, so they reach the AMI and the packer source. |
| `region` | str | required | boto3 `region_name`; the packer `region`; the provider block; `--region` on the CLI commands the plugin and the storage builders emit. |
| `default_machine_type` | str | required | The bake instance type when neither the OS-builder runtime entry (`default_machine_type`) nor the image's runtime entry (`machine_type`) names one; the instance type of a launched instance without `machine_type`. |
| `default_image_builder` | str | `default` | What an OS-builder runtime entry with `image_builder: default` resolves to. |
| `credentials` | `AwsCredentials` | `{}` | See the model above. An unknown key is a validation error naming its path. |
| `credentials.profile_name` | str or null | null | The profile. Reaches boto3, the packer source, the release command, the provider blocks and the backend files. |
| `credentials.aws_access_key_id`, `aws_secret_access_key`, `aws_session_token` | str or null | null | Static keys through `{{ ENV[...] }}` templates; reach boto3 only. |
| `account_id` | str or null | null | Reported by `runtime describe`; a template value. A bare number is coerced to a string. |
| `state_configuration` | str | `default` | The backend a storage or instance root on this runtime inherits when its own is `default`; `default` here means the default backend. |
| `session_mechanism` | str or null | null | `ssm` bakes the SSM agent into base images, makes packer connect through Session Manager, attaches `session_instance_profile` to instances, and makes every instance operation possible (verification, unmount, post-bake tests, aliases). Any other value is refused at generation. |
| `session_instance_profile` | str or null | null | The instance profile for launched instances and (when `iam_instance_profile` is unset) build instances. Read only when the mechanism is `ssm`. |
| `iam_instance_profile` | str or null | null | The build instances' profile in the packer source when `session_instance_profile` is unset; with both set the SSM profile wins (stage 63 item 9). Never reaches launched instances. |
| `ssh_username` | str | `default` | The bake SSH user for images that name none more specifically (step 4 of the bake-user order, CONFIGURATION 5.1.1). |
| `networking` | mapping or null | null | See below. Null loads with a warning and fails at image generation. |
| `ephemeral` | bool | `false` | Nothing baked here survives a successful run: the closing retention disposes every build on this runtime. |
| `retention_keep` | int or null | null | Builds kept per series when the image declares no `retention`; null keeps all. |
| `on_failure` | str or null | null | Default failure policy for ephemeral instances here: `keep` or `teardown`. |
| `teardown_after` | str or null | null | Default grace for ephemeral instances here: `<number>` then `m`, `h` or `d`. |
| `default_owners` | list[str] or null | null | Owners added to every vendor-image query on this runtime (stage 63 item 22). |
| `default_config_username` | str or null | null | The bake SSH user when no image entry, OS entry, `config_username` or runtime `ssh_username` names one (stage 63 item 22). |
| `ena_support` | bool or null | null | Declared `true` or `false`: written as `ena_support = true\|false` in the `amazon-ebs` packer source of every image baked here. Null: not written; packer's default applies (stage 63; until 2026-09-25 accepted and read by nothing). |
| `sriov_support` | bool or null | null | Declared `true` or `false`: written as `sriov_support = true\|false` in the same source. Null: not written; packer's default applies (stage 63; until 2026-09-25 accepted and read by nothing). |
| `executable`, `config`, `gitignore` | | | Accepted from `BuilderModel`; this plugin reads none of them. |
| `profile`, `parameters`, `runtime_classifier`, `executables` | | | Refused (unknown keys); the fixture's comments record the replacements. |

### `networking`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | the network id | A label; stripped, and refused when empty afterwards. |
| `network` | str | `default` | The VPC id; `default` resolves at load to the account's default VPC. Written as the packer `vpc_id`, the instance root's `data "aws_vpc"` id and the EFS builder's `vpc_id`. |
| `subnets` | list | required, at least one | Exactly one entry with `is_default: true`; the load refuses none. |
| `subnets[].name` | str | the subnet id | Label. |
| `subnets[].subnet_id` | str | required | The subnet id. The default one is the packer `subnet_id` and the instance module's `subnet_id`; the EFS builder mounts on every non-public one (one per zone). Checked at load against the subnets the account lists for the declared VPC, and refused when it is not one of them (stage 63; until 2026-09-25 not checked). A VPC the account lists without subnets makes no claim. |
| `subnets[].is_default` | bool | `false` | The subnet bakes and instances use. |
| `subnets[].public` | bool | `false` | The operator's statement; not overwritten by discovery. The EFS builder skips public subnets. |
| `subnets[].cidr` | str or null | null | Informational. |
| `subnets[].availability_zone` | str or null | null | Declared, never inferred; `validate` refuses a zone incompatible with an instance's zonal storages. The EFS builder uses it to pick one subnet per zone. |
| `subnets[].config` | mapping | `{}` | Accepted, not read. |
| `availability_zones` | list | `[]` | `{name, is_default}`; the default one becomes the packer `availability_zone`. |
| `addl_security_groups` | list[str] | `[]` | Checked to exist at load; the only list counted toward the limit of five; appended to the instance's `vpc_security_group_ids`; the EFS mount targets' client groups. |
| `ssh_ingress_security_group_ids` | list[str] | `[]` | Not checked at load. The generated instance group's port-22 source; when empty the ingress is the VPC's own CIDR block instead. |
| `security_group_ids` | | | Refused (unknown key) since stage 63. Until 2026-09-25 it was checked and counted but reached no emitter; put the ids in `addl_security_groups`. |

### What other entries contribute

These are not this plugin's fields, but the packer source reads them:

| Where | Field | Effect on AWS |
|---|---|---|
| OS builder `runtimes[]` entry | `default_machine_type` | The bake instance type for that base (the fixture bakes on `t3.medium` because a `t2.micro` OOMs). |
| OS builder `runtimes[]` entry | `ssh_username` | The bake user for that OS on this runtime (step 2 of the bake-user order); unset, the order continues down to the chain root family's vendor user. |
| OS builder `runtimes[]` entry | `owners`, `query` | The `describe_images` request. |
| OS builder `runtimes[]` entry | `image_id` | Stage 63: an AMI id that replaces the query; looked up by id with `DescribeImages`. |
| OS builder `runtimes[]` entry | `default_primary_disk_size` | Stage 63: the base image's `volume_size` on this runtime when declared. |
| OS builder | `default_primary_disk_size` | The base image's `volume_size` when the entry declares none (200 by default). |
| image `runtimes[]` entry | `machine_type` | The bake instance type for that instance image. |
| image | `primary_disk_size` | The root volume size of an instance-image bake, in GB. |
| instance | `machine_type` | The launched instance type; the runtime default otherwise. |

### Variations

- **A queried vs a pinned vendor AMI.** Without `image_id` on the OS
  builder's entry, resolution runs the `describe_images` query and takes
  the newest match, so the next base bake may start from a newer vendor
  AMI. With `image_id` (stage 63) the query is skipped and that one AMI is
  looked up by id; it must exist in this runtime's region, and the id is
  part of the fingerprint's vendor source.
- **Where the bake disk comes from.** `volume_size` is
  `lineage.bake_disk_size` (stage 63): this runtime has no
  `default_disk_size`, so a base image takes its entry's
  `default_primary_disk_size`, else the OS builder's (200). Until
  2026-09-25 the fingerprint hashed the entry's value (then defaulting to
  100) while the bake used the OS builder's 200; the fingerprint now
  hashes what is baked, so every AWS base image's recorded fingerprint
  moved once and reads DUE until `lineage restamp --runtime <rt> --commit`
  records the new one.

- **`session_mechanism: ssm` declared, with a profile.** The packer source
  gets `ssh_interface = "session_manager"`, the profile as
  `iam_instance_profile`, `associate_public_ip_address = false`,
  `ssh_timeout = "15m"` and the agent-installing `user_data`; base images get
  the agent provisioner and its verification lines; launched instances get
  the profile; verification, unmounts, post-bake tests and alias writes work.
  **Not declared:** the source keeps packer's SSH communicator with
  `associate_public_ip_address = true` and no `user_data`, no agent
  provisioner is emitted, instances get no profile, and every session-based
  operation fails with SSM's `TargetNotConnected` / `InvalidInstanceId`.
  **Declared without any profile:** the agent is baked and verified, but
  the source keeps the SSH communicator (the SSM block needs a profile).
- **`iam_instance_profile` set beside `session_instance_profile`.** Both
  build and launched instances wear `session_instance_profile` (the SSM
  profile wins, stage 63 item 9); `iam_instance_profile` applies to build
  instances only when the SSM profile is unset.
- **`networking.network: default`** resolves to the account's default VPC
  at load and is refused when the account has none. **A VPC id** must be one
  the session can describe. Either way, **a declared subnet in that VPC**
  loads and **a subnet id from another VPC** (or a mistyped one) is refused
  at load (stage 63; it used to pass and fail at the first bake or apply);
  **a VPC the account lists without subnets** leaves the declared subnets
  unchecked.
- **Security groups in `addl_security_groups`** are checked, counted
  (at most five) and worn by every launched instance; **the same ids under
  `security_group_ids`** are an unknown-key refusal at load (stage 63; until
  2026-09-25 accepted, checked and counted, but never emitted).
- **`ena_support` / `sriov_support` declared** (`true` or `false`) are
  written into the `amazon-ebs` source as that value; **not declared**, the
  source carries neither line and packer's defaults decide (stage 63; until
  2026-09-25 the fields were accepted and read by nothing, whatever their
  value).
- **`ephemeral: true`** keeps nothing baked here past a successful run;
  **`false`** (the fixture) keeps everything until `retention_keep`, an
  image's `retention` or an explicit `dispose image`.
- **A pinned parent** (`parent_policy: pinned` with a pin, or a rebuild)
  writes `filters = { image-id = "<pinned>" }`, `owners = ["self"]` into
  the data lookup; **an unpinned or deferred parent** writes the
  name-pattern / most-recent lookup from `get_query_assets()`; **a
  resolved vendor image** writes its exact id and owner.
- **An entry's `ssh_username`** wins over the runtime's (stage 63 item 23;
  the runtime's used to win); the OS builder's `config_username` wins over
  the runtime's too. With nothing named anywhere, an image takes `admin`
  (debian root), `ubuntu` (ubuntu root) or `ec2-user`.
- **A vendor query that resolved** gives the bake the real
  `RootDeviceName`; **a deferred source** falls back by family (`/dev/xvda`
  for debian and amazon, `/dev/sda1` otherwise).
- **Dry run versus real run.** A dry run still loads (network discovery
  runs), still resolves vendor AMIs, still emits the source and provider
  blocks, and still runs the state query's read-only hooks; it never bakes,
  never tags, never disposes, never starts or stops a machine, and the
  release and dispose commands print their plan. Only `--no-dry-run` runs
  the runner scripts that call `aws ec2 create-tags` and `dispose image`.
- **`apply_release` on** (global `config`) adds the `create-tags`
  executables to the release runner; **off**, `release` records the release
  in meta-state and tags nothing in the cloud.
- **`apply_instances` on for this runtime** lets the instance root apply,
  after which the plugin's instance hooks have something to find; **off**,
  the lookups answer "absent" and the stage-58 alias pass does nothing.
- **A stopped instance** is a `note` in the state report, skips
  verification and login proof unless the task may start it, and is left
  off by the alias pass; **a running one** is verified and aliased; **a
  terminated record** counts as absent.
- **An encrypted value** (`ENC[age:...]`) anywhere in the entry is
  decrypted by the core before this plugin sees it; the plugin has no
  behaviour of its own for encryption.

## What it tests and verifies

**At load (pydantic validators and `finalize`).**

- `AwsCredentials`: unknown keys refused (`extra="forbid"`), so
  `profile_nme` is a validation error naming `credentials.profile_nme`.
- `RuntimeNetworkingModel.__post_init__`: `network` non-empty; at least one
  subnet; exactly one default subnet. `AwsCloudNetworkingModel`: the name
  non-empty after stripping. `RuntimeBuilderModel`: `default_machine_type`
  present. `CloudBuilderModel`: `region` present.
- `update_networking()` (at `finalize`, after the base): discovers the
  account (four describe calls) and refuses a `default` network with no
  default VPC, a VPC the account does not have, a declared
  `subnets[].subnet_id` that is not among the subnets the account lists for
  that VPC (stage 63; skipped when the account lists none for it), a
  security group in `addl_security_groups` the account does not have, and
  more than five groups in `addl_security_groups`. Missing
  `networking` is a warning, not an error. Every verdict is a `ValueError`
  with the message logged at ERROR first; the load fails and `run` exits 1
  (`validate` exits 1).
- `security_group_ids` under `networking:` is refused as an unknown key by
  the shared model config, like any other undeclared key (stage 63; until
  2026-09-25 it was a field that was validated and counted but never
  emitted).
- The AWS CLI version: `validate` and every run look up the checker for
  each declared executable; for the entry named `aws-cli` it is this
  package's, and a missing binary, an unreadable version or one below the
  floor fails validation by name.

**At `validate`.** Nothing of this plugin's own beyond the load and the
tool check. The base's N9 dead-end rule reads `session_mechanism()`: a base
image with no admin public key and no session mechanism on a runtime is a
validation error naming the runtime.

**At generation.** `session_mechanism()` raises `ValueError` on a value
other than `ssm`. `amazon_ebs_source()` asserts that the source image has
query assets (an `AssertionError` naming the image and runtime; it cannot
fire for a resolved or deferred PSI). `ena_support` and `sriov_support` are
written into the source only when declared, as the declared boolean; there
is no further check on them (stage 63). Resolution's `query_provider_image`
raises when the region is unset or the AMI record carries neither
`ImageOwnerAlias` nor `OwnerId`, and returns `None` on no match, which
[resolve.py](../base/src/cs_image_system/base/commands/resolve.py) turns
into a failed run. For an entry that pins `image_id`,
`query_provider_image_by_id` returns `None` when AWS does not know the id,
and resolve.py stops the run naming the id and the runtime (stage 63).

**At apply.** Nothing in this package runs at apply: packer and tofu do,
with what this package emitted. Packer's own in-bake verification carries
the two SSM assertions from `session_verify_commands` (the agent binary
present, the unit enabled); a failed assertion fails the bake.

**After apply (post-finalize hooks and deferred commands).**

- After a bake the packer plugin calls `retag_image()` for every recorded
  build; the verdict is the AMI's tags (checked by the next state query).
- `verify instance <name>` (the ephemeral sequence, `just cloud-verify`,
  the post-bake tests) calls `verify_instance()`: three checks named
  `startup scripts` (the marker within `timeout`, polled every 15 s over
  SSM), `booted image` (the running instance's `ImageId` against the
  expected build, or against lineage when nothing is pinned yet) and, when
  the instance declares storages, `data disks mounted` (`findmnt` targets
  under `/mnt/` at least the declared count). The base appends
  `declared tests` from `tests.post_bake`, run over `run_session_command`.
  The verdict lands in `meta-state/verifications.yaml` with the last 20
  lines of output as evidence; a failed verdict stops the runner and
  `verify assert` fails the run.
- Before a detach, `unmount storage` runs the unmount script over
  `run_session_command`; the verdict is the receipt under
  `unmount-receipts/<instance>__<storage>.json` in the root's workspace,
  which `gate-plan --require-unmounted` reads.
- After an applies-on instance run the alias pass asks
  `query_instance_identity` and `query_instance_power_state`, and writes
  AltNames over `run_session_command` to running machines only; the verdict
  is a log line per instance and `reality.instances` in the state report.
  The generation ledger (`meta-state/instance-state.yaml`) records the
  provider's instance id from the same identity query.
- `verify login` skips a machine whose power state is not `running`.

**In the state query** (`state query`, `just cloud-preflight`, the start of
every run): `query_images` on this runtime feeds `missing`, `foreign` and
`changed`; `query_instance_boot_image` compares each pinned instance's
booted AMI with its pin (`changed` when they differ, a `note` when a
pending replacement explains it), and a standing ephemeral is reported;
`query_instance_power_state` turns a stopped machine into a `note` and a
stopped ephemeral into a STANDING line. A hook that raises makes an
`unavailable:` line, never a failure. The verdicts land in
`generated/state-report.json` (run-local, never committed) and on the
console; `--strict` exits 1 on anything but `stale`.

## When it fails

Failures that have happened, oldest first, then the ones the code raises
that have not. Dates are from [docs/history/LEDGER.md](../../docs/history/LEDGER.md),
[docs/OPERATIONS.md](../../docs/OPERATIONS.md) and the tests.

### Seen live

- **2026-08-31, stage 1: packer's `data "amazon-ami"` found no credentials.**
  `No valid credential sources found` from the datasource although the
  operator's shell was logged in: packer does not read a profile it is not
  told about. The source now carries `profile = "<profile_name>"` on both
  the lookup and the source. If it recurs, the runtime's
  `credentials.profile_name` is unset or the profile has no live session.
- **2026-08-31, stage 1: `Timeout waiting for SSH` on every bake.** The
  VPC has no internet gateway, so packer's SSH communicator could never
  reach the build instance. `session_mechanism: ssm` with a profile makes
  packer connect through Session Manager; the same message today means the
  Session Manager plugin is missing on the baking machine, the build
  instance never registered with SSM (no route to the SSM endpoints from
  the default subnet, the `user_data` bootstrap failed, or the profile
  lacks the SSM policy), or the bake ran past `ssh_timeout = "15m"`. Look at
  the packer log of the bake and at SSM Fleet Manager for the instance.
- **2026-08-31, stage 1: a Debian chain baked as `ec2-user` never
  authenticated** (again `Timeout waiting for SSH`, over the SSM tunnel).
  Only the vendor user's `authorized_keys` receives packer's key, so the
  bake user now follows the chain root's family (`admin` for debian). A
  runtime `ssh_username` or an entry `ssh_username` that names the wrong
  user brings it back.
- **2026-08-31, stage 1: two root-slot volumes on the deb-11 chain.** A
  hard-coded `/dev/sda1` device on a Debian root (whose root is
  `/dev/xvda`) baked an AMI carrying two volumes in the root slot; instances
  from it never booted. The mapping now uses the source AMI's real
  `RootDeviceName`, else the family default. A deferred source still falls
  back by family, so a chain whose root family is unknown to
  `_chain_root_family` gets `/dev/sda1`.
- **2026-08-31 to 2026-09-01, stage 1: `t2.micro` out of memory** at bake
  (`dnf update` killed) and on instances (the SSM agent killed, finding 25).
  The OS builder entries bake on `t3.medium`; an instance declares its own
  `machine_type`. The symptom is a bake that dies mid-provisioner or an
  instance that stops answering SSM after boot.
- **Stage 1: `curl: (23)` re-downloading the SSM agent** on Debian during
  the agent provisioner, because the `user_data` bootstrap had already left
  a root-owned `/tmp/ssm.deb`. The provisioner now skips the install when
  the agent is present and downloads to its own file name.
- **2026-09-01 to 2026-09-02, stage 1, findings 27 to 31: `sft ssh` hung
  on the advertised private address.** Instances wore only the VPC default
  group; the instance root now creates `csis-instances` with SSH ingress
  from `ssh_ingress_security_group_ids` only (opening the shared CIDRs is
  forbidden), and the gateway relay also needs the target in the gateway's
  own group (`addl_security_groups`). An instance that cannot be reached by
  the relay while SSM works points at those two lists.
- **2026-09-02 and 2026-09-03: orphan AMIs from failed and unrequested
  bakes.** Eleven AMIs and twelve snapshots from stage 1, and two more from
  stale runner scripts, appeared as `foreign` in the state query (they carry
  our tags, no record has them). The operator deregistered them by hand;
  `state import` adopts such an image, `dispose image` removes a recorded
  one. A `foreign` line is never hard drift, but every line is actionable.
- **2026-09-08: a follow image kept its generation-time tags.** A child
  baked in the same run as its parent was tagged with a `series-...`
  parent and a placeholder fingerprint; the state query reported `changed`.
  The packer plugin now calls `retag_image` after every bake, and `lineage
  relabel --runtime <rt>` re-tags any build whose tags still disagree with
  its record.
- **2026-09-08: the AWS SSO session lapsed mid-run.** A `tofu plan` failed
  with `No valid credential sources found ... backend s3 ... the SSO
  session has expired` after `cloud-preflight` had passed at the start;
  the same lapse ends any load with `AWS Error: ...` from
  `get_vpc_map_and_default_vpc_id`, on GCE work too. Environmental, not a
  defect: `aws sso login --profile noaa`, then `just full-test-legs` or the
  legs that were running. `preflight` and the strict state query flag a
  session expiring within `config.preflight.expected_run_minutes`;
  an `sso-session` profile reports no fixed expiry.
- **2026-09-09: the first live AWS disposal** (`dispose image <two EL8
  AMIs> --no-dry-run --commit`) deregistered both and deleted their
  snapshots; `describe-images` on both ids answered an empty list
  afterwards. Not a failure, but the proof that a disposal's success is
  read from the cloud, not from the log line.
- **2026-09-10, ledger 72: `InvocationDoesNotExist` right after
  `send_command`.** The unmount had already run on the instance when
  `get_command_invocation` raised, so no receipt was written and the gate
  refused the detach. The poll now tolerates that code until its deadline
  ([test_v2_aws_parity.py](../../tests/test_v2_aws_parity.py)); any other
  SSM error still raises.
- **2026-09-12, stage 17: `credentials.profile_nme` was silently dropped.**
  With `credentials` a plain mapping the typo left the profile unset and
  boto3 fell back to `AWS_PROFILE` or nothing. The typed `AwsCredentials`
  makes it a validation error naming `credentials.profile_nme`.
- **2026-09-21, stage 57: a stopped machine was reported as "the provider
  could not answer".** The boot-image probe filters on `running`, so a
  machine the operator had switched off looked like an unreachable cloud
  and `run_session_command` said `no running instance` for both. The
  power-state hook separates them: the state report says `STOPPED (switched
  off; not drift)` in a `note`, and a session command on a stopped machine
  fails with `cannot run a command on '<name>': it is STOPPED (switched off;
  not drift)`.
- **2026-09-22: the strict query refused the launch that finishes an
  upgrade.** After `upgrade instance` moved the pin, the booted AMI was
  behind it by design, and `cloud-launch`'s preflight called that
  `changed`. With the pending-replacement marker present it is now a
  `note`; without the marker it is drift again.
- **2026-09-22, stage 58: the first live replacement wrote no aliases.**
  The alias pass ran before the new machine had enrolled; a machine launched
  in the same run is now waited for, and one that never enrolls gets no
  alias that run (the log says so).

### Raised by the code, not yet seen

Load (`ValueError`, logged at ERROR, `run`/`validate` exit 1):

```text
No VPC ID specified in networking configuration for AWS cloud builder <name>, and no default VPC found in AWS account. ...
VPC ID <vpc> specified in networking configuration for AWS cloud builder <name> not found in AWS account.
Subnet <id> (<name>) in networking configuration for AWS cloud builder <runtime> is not in VPC <vpc>.
Security group ID <sg> specified in networking configuration for AWS cloud builder <name> not found in AWS account.
Total number of security groups specified in networking configuration for AWS cloud builder <name> is <n>, which may exceed limits for certain instance types. ...
AWS Error: <botocore message>
Networking configuration name cannot be empty for <model>.
```

The subnet line (stage 63) means a declared `subnets[].subnet_id` is not one
of the subnets the account lists for the declared VPC: a typo, a subnet from
another VPC or account, or a `network: default` that resolved to a VPC other
than the one the subnets belong to. Fix the subnet id or the `network` in the
tree. Before 2026-09-25 this passed the load and surfaced at the first bake
or apply as a packer or tofu error about the subnet. The security-group
count line counts only `addl_security_groups` since stage 63.

Declaring `networking.security_group_ids` fails the load as an unknown key
(stage 63), with the shared model config's extra-key error naming
`security_group_ids`. Until 2026-09-25 the field was accepted, checked and
counted but never emitted; move its ids into `addl_security_groups`, which
is the list that reaches the instance and storage roots.

`AWS Error:` wraps every `BotoCoreError`/`ClientError` of the discovery: an
unknown profile (`The config profile (<p>) could not be found`), an expired
token, a role without the four describe permissions
(`UnauthorizedOperation`), no network. The message names the cause; the fix
is on the credential side, never in the tree. The warning
`No networking configuration provided for AWS cloud builder <name>` is not
fatal at load but the image generation that follows raises on the missing
VPC.

Resolution:

```text
Failed to create EC2 client: <e>                      (AMIQueryError)
Failed to query AMI with filters: <e>                 (AMIQueryError: a describe_images refusal, e.g. an invalid filter name)
Region must be specified in builder config to resolve image identifier, but got None
Could not get owner alias or owner id for image <ami> in region <region>, got <dict>
No resolved Image identifiers for OS <os builder> in predefined_resolve   (base: the query matched nothing)
Failed to query AMI by ID: <e>                        (AMIQueryError: a DescribeImages refusal other than NotFound/Malformed, for a pinned image_id)
OS builder <name>: image_id '<id>' on runtime <rt> is not known to the provider   (base, stage 63: the pinned AMI is not in this region, is deregistered, or is malformed)
```

The `No resolved Image identifiers` line is the usual symptom of a vendor query that is too narrow, an
owner id that is wrong, or a vendor image that went away; the request that
was sent is logged at DEBUG (`Querying for AMI with filters: ...`) and the
count found at INFO.

Generation:

```text
AWS runtime <name>: unknown session mechanism '<value>' (supported: ssm)
Provider-specific image for image <image> on runtime <rt> must have query assets ...   (AssertionError)
```

Instance operations (`RuntimeError` unless noted; the caller records or
reports it):

```text
AWS runtime <name>: cannot run a command on '<instance>': it is STOPPED (switched off; not drift)
AWS runtime <name>: cannot run a command on '<instance>': it is absent (no such machine)
AWS runtime <name>: cannot run a command on '<instance>': it is power state unavailable (no runtime could answer)
AWS runtime <name>: no instance named '<instance>' to start
AWS runtime <name>: no instance named '<instance>' to stop
ssm command <id> still <status> after <timeout>s          (returned as exit 1 with this text, not raised)
```

An SSM `send_command` on a running instance whose agent is not registered
raises botocore's `InvalidInstanceId`; a machine that exists but cannot be
reached shows as `TargetNotConnected` in the verification evidence. The EC2
waiters raise `WaiterError` when a start or stop exceeds `timeout`;
`running_for_task` then logs the machine as started but unreachable and
skips the work, and a failed stop is logged at ERROR with the instruction to
stop it by hand. An unrecognised `State.Name` is logged
(`reports unrecognised state '<raw>'; treating it as unknown`) and answered
as `unknown`.

Verification (`verify_instance`; the check's `detail` in
`meta-state/verifications.yaml`):

```text
no completion marker within <timeout>s
booted <ami>, expected <build>
<n> mount(s) under /mnt, <m> declared
```

Disposal and tags: `AMI <id> not found; nothing to deregister` is a
warning and returns `False` (the record is still dropped by the caller);
any other `describe_images`, `deregister_image` or `delete_snapshot`
refusal raises and stops `dispose image` with nothing recorded. A
`create_tags` refusal in `retag_image` is caught by `lineage relabel`
(`could not retag <id>`) and the state query keeps showing `changed`; in
the packer plugin's post-bake retag it propagates.

The state query and the read-only probes never fail a run on this plugin's
account: `query_images` raising becomes
`state query images/<rt> unavailable: <e>` and an `unavailable:` line;
`query_instance_boot_image`, `query_instance_power_state` and
`query_instance_identity` swallow every exception into a DEBUG line and
answer `None` (no claim).

Release: the runner script runs `aws ec2 create-tags ... --profile <p>`
under `set -euo pipefail`; a missing `aws` binary, a profile without a
session or a role without `ec2:CreateTags` fails the release lifecycle's
apply (`failed` in `run-summary.json`) after meta-state already recorded
the release. Re-run `run release` once the cause is fixed; the command is
idempotent.

`empty --runtime <aws runtime>` prints
`empty: AwsCloudBuilder cannot list its inventory` and exits 2; the
runtime cannot be proved empty this way.

Tool check (`validate` and every run, exit 1):

```text
aws-cli: binary 'aws' not found (declared in cfg/executables.yml; an absolute path, or a name on PATH)
aws-cli: could not read its version (`aws --version`): <e>
aws-cli: AwsCLIVersionChecker could not parse a version from `aws --version`
```

and the base's version-floor message naming `aws-cli` and the requirement
when the installed version is below it.

## Related

- [gcloud-runtime-plugin](../gcloud-runtime-plugin/README.md): the other runtime type, with the same hook surface on Compute Engine.
- [default-os-plugin](../default-os-plugin/README.md): the OS builders whose runtime entries this plugin resolves to AMIs.
- [packer-plugin](../packer-plugin/README.md): the image builder that asks this plugin for the `amazon-ebs` source and the session provisioners.
- [tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md): the instance and storage roots that read this model's networking, profile and session profile.
- [dummy-plugin](../dummy-plugin/README.md): the extension template; an unregistered copy of its group model sits at the bottom of this package's models module.
- Base classes: [runtime.py](../base/src/cs_image_system/base/models/runtime.py), [cloud_builder.py](../base/src/cs_image_system/base/models/cloud_builder.py), [credentials.py](../base/src/cs_image_system/base/models/credentials.py), [provider_specific_image.py](../base/src/cs_image_system/base/models/provider_specific_image.py), [builder_base_runtime.py](../base/src/cs_image_system/base/basic/builder_base_runtime.py), [abstract_version_checker.py](../base/src/cs_image_system/base/basic/abstract_version_checker.py).
- Consumers of the hooks: [state_query.py](../base/src/cs_image_system/base/state_query.py), [retention.py](../base/src/cs_image_system/base/retention.py), [dispose.py](../base/src/cs_image_system/base/commands/dispose.py), [verify_instance.py](../base/src/cs_image_system/base/commands/verify_instance.py), [unmount.py](../base/src/cs_image_system/base/commands/unmount.py), [relabel.py](../base/src/cs_image_system/base/commands/relabel.py), [release.py](../base/src/cs_image_system/base/release.py), [power_state.py](../base/src/cs_image_system/base/power_state.py), [provider_aliases.py](../base/src/cs_image_system/base/provider_aliases.py), [runtime_facts.py](../base/src/cs_image_system/base/commands/runtime_facts.py).
- [docs/OPERATIONS.md](../../docs/OPERATIONS.md) for the credential contract and the operator's cycles; [docs/DESIGN.md](../../docs/DESIGN.md) for the design; [docs/PLUGINS.md](../../docs/PLUGINS.md) for the package index.
- [The configuration reference](../../docs/CONFIGURATION.md) -- every field of the YAML this plugin reads, with an example.
