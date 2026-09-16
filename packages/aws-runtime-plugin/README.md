# cs-image-system-aws-runtime-plugin

The `aws` runtime type. A runtime is where images are baked and instances
run; this package makes Amazon EC2 one. It registers one runtime model
(`AwsCloudBuilderModel`) and one runtime builder (`AwsCloudBuilder`). At load
it discovers the account's VPCs, subnets and security groups with boto3 and
checks the declared networking against them. During a run it resolves vendor
AMIs by owner and filter, emits the `amazon-ebs` packer source for every image
baked here, bakes and reaches instances through AWS Systems Manager (SSM),
answers the state query from `describe-images` / `describe-instances`, tags
released AMIs, and disposes of AMIs together with their snapshots.

## What it registers

The entry point is declared in [pyproject.toml](pyproject.toml):

```toml
[project.entry-points."cs_image_system.plugins.runtime"]
aws_plugin = "cs_image_system.aws_runtime.main:initialize"
```

`initialize()` in [main.py](src/cs_image_system/aws_runtime/main.py) returns an
`AwsRuntimePluginMetadata` whose services map the key `aws` to two classes and
whose `builders_for_models` binds the model to its builder.

| Class | `csis_name()` | `csis_classifier()` | Registered under |
|---|---|---|---|
| `AwsCloudBuilderModel` ([aws_runtime_models.py](src/cs_image_system/aws_runtime/aws_runtime_models.py)) | `aws` | `VCT.CLOUD_BUILDER_MODEL` | `cloud_builder_model` and, because the loader re-registers cloud models as runtimes, `runtime_builder_model` |
| `AwsCloudBuilder` ([aws_runtime_builders.py](src/cs_image_system/aws_runtime/aws_runtime_builders.py)) | `aws` | `VCT.RUNTIME_BUILDER` | `runtime_builder` |

A YAML entry selects them with `type: aws` under `runtime_builders:`. There
are no type aliases; `aws` is the only type key. An entry's own `aliases:`
list gives that runtime extra names (the fixture's `aws-east2-runtime` also
answers to `aws`, `amazon` and `us-east-2`), and other entries refer to it by
any of them.

Present in the package but not registered as a service:

- `AwsProviderSpecificImage` ([aws_provider_specific_image.py](src/cs_image_system/aws_runtime/aws_provider_specific_image.py)), reached through the builder's `provider_specific_image_class()` hook.
- `AwsCLIVersionChecker` (`csis_name` `aws-cli`, classifier `VCT.VERSION_CHECKER`), defined in the builders module but absent from the services list, so no executable gets its version parsed by it.
- `DummyGroupBuilderModel` and `DummyUserBuilderModel`, unregistered copies of the [dummy plugin](../dummy-plugin/README.md)'s models; the models module imports `DUMMY` from that package.

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
| `security_group_ids` | `list[str]` | `[]` | Security group ids. Checked against the account at load and counted toward the limit below; no emitter reads them. |
| `addl_security_groups` | `list[str]` | `[]` | Existing groups every launched instance also wears, unmodified. Checked against the account at load. The instance module's `vpc_security_group_ids` lists them after the generated group. |
| `ssh_ingress_security_group_ids` | `list[str]` | `[]` | Groups whose members may reach port 22 on launched instances. The generated instance security group's ingress references only these groups, never a CIDR range. Not checked against the account. |
| `_model_id` | `str \| None` | `None` (not an init field) | Back-reference to the owning runtime model. |

Base fields it inherits:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | `str` | the network id | Empty or `default` falls back to `network`. |
| `network` | `str` | `default` | The VPC id. `default` resolves at load to the account's default VPC. |
| `subnets` | `list[RuntimeSubnetModel]` | required, non-empty | Each has `name`, `subnet_id`, `is_default`, `public`, `cidr`, `config`. The first entry with `is_default: true` is the default subnet; without one the model refuses to load. |
| `availability_zones` | `list[RuntimeAvailabilityZoneModel]` | `[]` | `name`, `is_default`. The default zone, when declared, becomes the packer source's `availability_zone`. |

It constrains `name` to be non-empty after stripping. `get_subnet_id()`
raises when no default subnet exists. It does not accept security groups by
name, only by id, and it refuses more than five groups in
`security_group_ids` plus `addl_security_groups` combined.

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
| `account_id` | `str \| None` | `None` | The AWS account. Reported by `runtime describe`; usable in templates as `{{ this.account_id }}`. |
| `credentials` | `AwsCredentials` | empty | Narrows the base `CredentialsBase`. |
| `state_configuration` | `str` | `DEFAULT` | Foreign key to a state backend. Declared on the runtime; the terraform roots take their backend from their own builders' field of the same name. |
| `ena_support` | `bool \| None` | `None` | Declared; nothing reads it. |
| `sriov_support` | `bool \| None` | `None` | Declared; nothing reads it. |
| `iam_instance_profile` | `str \| None` | `None` | Instance profile attached to packer build instances; also the fallback SSM profile for bakes when `session_instance_profile` is unset. |
| `session_mechanism` | `str \| None` | `None` | `ssm` is the only value. Any other string is an error. |
| `session_instance_profile` | `str \| None` | `None` | The SSM-capable instance profile given to launched instances and to build instances. |
| `ssh_username` | `str` | `DEFAULT` | When set, overrides the bake's SSH user for every image baked on this runtime. |
| `networking` | `AwsCloudNetworkingModel \| None` | `None` | Narrows the base type and makes it optional. Missing networking logs a warning at load; image resolution and bakes then fail. |
| `vpc_map` | `dict` | discovered | Not an init field. `{vpc_id: {"subnets": [...]}}` from the account. |
| `default_vpc_id` | `str \| None` | discovered | Not an init field. |
| `all_security_groups` | `dict[str, dict]` | discovered | Not an init field. `{group_id: description}` from the account. |

Base fields it inherits, and what this runtime does with them:

| Field | From | Default | Meaning here |
|---|---|---|---|
| `name`, `type`, `description`, `aliases` | `NameTyped` | `name`/`type` required | `type` is `aws`. |
| `executable`, `is_default`, `config`, `gitignore`, `tags` | `BuilderModel` | | `tags` merge into every image's tags; `is_default` makes this the runtime `default` resolves to. |
| `region` | `CloudBuilderModel` | required | boto3 `region_name`, the packer `region`, the `aws` provider block. |
| `default_machine_type` | `RuntimeBuilderModel` | required | Instance type when neither an OS-builder runtime entry nor an image names one. |
| `default_image_builder` | `RuntimeBuilderModel` | `DEFAULT` | The image builder an OS-builder runtime entry with `image_builder: default` resolves to. |
| `default_owners` | `RuntimeBuilderModel` | `None` | Appended to every vendor-image query's owner list. |
| `default_config_username` | `RuntimeBuilderModel` | `None` | Fallback SSH user for OS-builder runtime entries that declare none. |
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
| Image generation | `packer_source_type()` | `amazon-ebs`. |
| Image generation | `packer_source_blocks(...)` | The `data "amazon-ami"` lookup and the `source "amazon-ebs"` block for one image. |
| Image generation | `session_mechanism()` | `ssm` or `None`. |
| Image generation | `session_agent_commands(os_family)` | Installs and enables the SSM agent on a base image; `apt` path for `debian`/`ubuntu`, `yum` path otherwise. |
| Image generation | `session_verify_commands(os_family)` | Assertions that the agent is present and enabled. |
| Image generation | `bake_ssh_username()`, `bake_finalize_commands()` | Base defaults: `None` and none. Provisioners keep their own user; no closing provisioner. |
| After a bake | `build_id_from_artifact(artifact_id)` | Base default: the packer manifest's `<region>:<ami>` becomes the AMI id. |
| Instance generation | `session_instance_profile()` | The instance profile the instance module attaches when the mechanism is `ssm`. |
| Instance verification | `verify_instance(name, expected_build, expect_mounts, timeout)` | Over SSM: waits for the launch completion marker `/var/lib/csis/launch-applied`, counts mounts under `/mnt`, compares the booted AMI with the expected build. |
| Instance operations | `run_session_command(name, script, timeout)` | `AWS-RunShellScript` through SSM on the running instance whose `Name` tag matches; polls the invocation to completion. |
| Release | `release_commands(build_id, tags)` | One `aws ec2 create-tags --region ... --resources <ami> --tags Key=..,Value=..` executable, with `--profile` when `credentials.profile_name` is set. Runs only under `--no-dry-run` and only when the global `apply_release` is true. |
| State reconciliation | `retag_image(image_id, tags)` | `create-tags` on one of the system's own AMIs. |
| Retention | `dispose_image(build_id)` | Deregisters the AMI and deletes every EBS snapshot in its block device mappings. A missing AMI returns `False` (already gone). |
| State query | `query_images(series)` | Every AMI owned by `self` that carries a `csis_series` tag: `{image_id, name, state, created, tags}`. |
| State query | `can_query_instance_boot_image()`, `query_instance_boot_image(name)` | `True`; the `ImageId` of the pending or running instance whose `Name` tag matches, or `None`. Read-only, never fatal. |
| `empty --runtime` | `inventory()` | Not implemented on AWS; the base raises `NotImplementedError`, so the emptiness check refuses this runtime. |

### Credentials

`AwsCloudBuilderModel.self_to_aws_client_config()` is the one conversion
point: `credentials.as_dict()` plus `region_name` from `region`. Every boto3
call in the plugin builds `boto3.Session(**config)` from it, so a
`profile_name` selects a profile and an empty `credentials:` lets boto3's
default chain run (environment variables, `AWS_PROFILE`, an instance role).
The same profile name is written into the packer source (`profile = "noaa"`
on both the data lookup and the source), passed as `--profile` to the release
command, and read by the state-backend and instance plugins for their
provider blocks and backend files, so packer, terraform and the plugin's
own calls all authenticate the same way.

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
VPC (an error when the account has none); the VPC must exist; every id in
`security_group_ids` and `addl_security_groups` must exist; more than five of
them is an error. The declared `subnets[].public` flag is the operator's
statement and is not overwritten by the discovered `is_public`. A load
therefore needs a live AWS session even for a dry run.

### The image query

`query_provider_image()` takes one OS-builder runtime entry
(`OSBuilderBaseImageBuilderSubconfig` in
[os_builder_runtime_config.py](../base/src/cs_image_system/base/models/os_builder_runtime_config.py)).
`remap_for_image_query()` builds a `describe_images` request:

- `Owners` is the entry's `get_owners()`: the OS builder's owners, then the runtime's `default_owners`, then the entry's own, deduplicated in order.
- `query.filters` keys are mapped through `AWS_DI_MAP` (snake_case to EC2 filter names, `tag:<key>` kept), booleans lowercased, and `state: available` forced.
- Keys the map does not know go to a post-query exact-match filter on the result dictionaries.

`query_image()` pages through `describe_images`, applies the post-query
filter, and returns the newest `CreationDate`. The builder then reads the
owner (`ImageOwnerAlias`, else `OwnerId`) and returns `(ImageId, owner,
raw)`; the base registers an `AwsProviderSpecificImage` in the resolved state.

`AwsProviderSpecificImage.get_query_assets()` gives the packer
`data "amazon-ami"` body:

- resolved: `filters = { image-id = "<ami>" }` plus `owners = ["<owner>"]` when known;
- deferred (an image a build produces later): `owners = ["self"]`, `filters = { name = "<pattern>*", root-device-type = "ebs", virtualization-type = "hvm", architecture = "<arch or x86_64>" }`, `most_recent = true`.

[tests/test_aws_provider_specific_image.py](tests/test_aws_provider_specific_image.py)
pins both shapes.

### The state query and instance hooks

`query_images`, `query_instance_boot_image`, `verify_instance`,
`run_session_command`, `retag_image` and `dispose_image` all go through
`aws_utils.ec2_client()` / `aws_utils.aws_client("ssm", ...)`, which build a
client from the same session config. The state query in
[state_query.py](../base/src/cs_image_system/base/state_query.py) reads
`query_images` to classify `missing`, `foreign` and `changed` images, and
asks `query_instance_boot_image` only because `can_query_instance_boot_image()`
is `True`. `verify_instance` is the deferred verification step of the
instance lifecycle; `run_session_command` is how the system runs a script on
an instance (for example an unmount before a detach).

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
`query_images` are the checks.

## Emission

The plugin's output is visible in the golden emission under
[tests/fixtures/v2_golden/generated](../../tests/fixtures/v2_golden/generated).

- [pckr-ebs-ans-image-generation-source-basic-rh-10-block-000.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-source-basic-rh-10-block-000.pkr.hcl):
  the `data "amazon-ami"` lookup (`filters`, `owners`, `profile`) and the
  `source "amazon-ebs"` block written by `amazon_ebs_source()` in
  [aws_packer_source.py](src/cs_image_system/aws_runtime/aws_packer_source.py):
  `source_ami`, `ami_name`, `instance_type` (the runtime entry's machine
  type, else the runtime default), `region`, `vpc_id`, `subnet_id` (the
  default subnet), the merged lineage `tags`, `profile`, and, because the
  runtime declares `session_mechanism: ssm`, `ssh_interface =
  "session_manager"`, `iam_instance_profile`, `associate_public_ip_address =
  false`, `ssh_timeout = "15m"` and a `user_data` script that installs the
  SSM agent on vendor images that lack it. `ssh_username` is the entry's
  user, else the chain root family's vendor user (`admin` for debian,
  `ubuntu` for ubuntu, `ec2-user` otherwise), overridden by the runtime's
  `ssh_username` when set. `launch_block_device_mappings` uses the source
  AMI's real `RootDeviceName` (else `/dev/xvda` for debian and amazon roots,
  `/dev/sda1` otherwise), `gp3`, and the image's `primary_disk_size`.
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
  `ephemeral_instances` declared on it. It is a command, not a file.

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
`default_machine_type` and a `networking` block with one default subnet.

## Related

- [gcloud-runtime-plugin](../gcloud-runtime-plugin/README.md): the other runtime type, with the same hook surface on Compute Engine.
- [default-os-plugin](../default-os-plugin/README.md): the OS builders whose runtime entries this plugin resolves to AMIs.
- [dummy-plugin](../dummy-plugin/README.md): the extension template; this package's models module imports it.
- Base classes: [runtime.py](../base/src/cs_image_system/base/models/runtime.py), [cloud_builder.py](../base/src/cs_image_system/base/models/cloud_builder.py), [credentials.py](../base/src/cs_image_system/base/models/credentials.py), [provider_specific_image.py](../base/src/cs_image_system/base/models/provider_specific_image.py), [builder_base_runtime.py](../base/src/cs_image_system/base/basic/builder_base_runtime.py).
- Consumers of the hooks: [state_query.py](../base/src/cs_image_system/base/state_query.py), [retention.py](../base/src/cs_image_system/base/retention.py), [dispose.py](../base/src/cs_image_system/base/commands/dispose.py), [verify_instance.py](../base/src/cs_image_system/base/commands/verify_instance.py), [runtime_facts.py](../base/src/cs_image_system/base/commands/runtime_facts.py).
- [docs/OPERATIONS.md](../../docs/OPERATIONS.md) for the credential contract and the operator's cycles; [docs/DESIGN.md](../../docs/DESIGN.md) for the design; [docs/PLUGINS.md](../../docs/PLUGINS.md) for the package index.

- [The configuration reference](../../docs/CONFIGURATION.md) — every field of the YAML this plugin reads, with an example.
