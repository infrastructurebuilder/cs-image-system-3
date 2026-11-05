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
| `AwsCLIVersionChecker` ([aws_runtime_builders.py](src/cs_image_system/aws_runtime/aws_runtime_builders.py)) | `aws-cli` | `VCT.VERSION_CHECKER` | `version_checker` |

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

**The AWS section of the bootstrap**, through the
`cs_image_system.bootstrap` entry-point group: `aws =
cs_image_system.aws_runtime.bootstrap:aws_section`. It owns the questions
and the terraform for this cloud's one-time initialisation -- the GitHub
OIDC identity provider, the READ-ONLY and WRITE roles of CI_SETUP.md 3.3
with their trust and permission documents, and the state buckets (the
default backend's and every other declared S3 backend's that a root is
bound to) and the Session Manager instance profile when the account
lacks them (`tfmodules/bootstrap_aws`). The
section renders its coverage audit for the generated README: what it
made, read, adopted, or leaves by hand and why (a backend bound to no
root is left out and said so). The section declares the two repository
secrets the AWS workflows read (`AWS_ROLE_ARN`, `AWS_APPLY_ROLE_ARN`; both
set from the applied root's outputs when the section is wanted) and the
`AWS_REGION` Actions variable, valued by its `region` answer; the GitHub
section's script and module set them with the rest, so the core names
neither. The section is wanted by default where the
tree declares an AWS runtime or an S3 state backend. Its defaults come
from the raw `cfg/runtime-builders.yml` and `cfg/state-backends.yml`
(read as YAML, never loaded; a starter's `REPLACE-ME` values and its
example account id are no defaults), and every "does it already exist?"
question is a probe of the account as the runtime's profile (`aws iam
get-open-id-connect-provider`, `get-role`, `get-instance-profile`,
`s3api head-bucket`): found, absent, or -- with no session -- unanswerable,
which `--quiet` refuses by name. A role that exists is adopted with an
`import` block in the root, and the subjects it already trusted that are
not this repository's are read from its trust document and kept (another
repository may share the role); the root's state binds to the tree's declared
S3 backend when the bucket exists. See OPERATIONS.md, "The bootstrap".

## Models

### `AwsCredentials`

Extends `CredentialsBase` in
[credentials.py](../base/src/cs_image_system/base/models/credentials.py).
The base declares no fields; each provider narrows it. Field names are
boto3 `Session` keyword arguments and pass straight through. The four
keys, all `str | None` and `None` by default, are tabled in
[CONFIGURATION 4.3](../../docs/CONFIGURATION.md#43-aws): `profile_name` names a
profile in the operator's AWS configuration (the fixture uses `noaa`);
`aws_access_key_id`, `aws_secret_access_key` and `aws_session_token`
carry a template such as `{{ ENV['AWS_ACCESS_KEY_ID_east2'] }}`, never a
literal.

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
another name. The field table, base keys and AWS additions, is
[CONFIGURATION 4.5](../../docs/CONFIGURATION.md#45-networking).

The keys it adds:

- `addl_security_groups` (`list[str]`, `[]`): existing groups every
  launched instance also wears, unmodified. Checked against the account
  at load and the only list counted toward the limit of five below. The
  instance module's `vpc_security_group_ids` lists them after the
  generated group; the EFS storage builder uses them as the mount
  targets' client groups. The accessor is `get_addl_security_groups()`.
- `ssh_ingress_security_group_ids` (`list[str]`, `[]`): groups whose
  members may reach port 22 on launched instances. The generated instance
  security group's ingress references only these groups, never a CIDR
  range; when the list is empty the ingress is the VPC's own CIDR block
  instead. Not checked against the account.
- `_model_id` (not an init field): the back-reference to the owning
  runtime model.

What this runtime does with the base keys: `name` empty or `default`
falls back to the network id; `network` (`default` resolves at load to
the account's default VPC) is written as the packer `vpc_id`, the
instance root's `data "aws_vpc"` id and the EFS builder's `vpc_id`; the
first `subnets[]` entry with `is_default: true` is the default subnet,
the packer `subnet_id` and the instance module's `subnet_id`, and without
one the model refuses to load; the EFS builder mounts on every non-public
subnet, one per zone, reading `subnets[].public` (the operator's
statement, not overwritten by discovery) and `subnets[].availability_zone`
(declared, never inferred; `validate` refuses a zone incompatible with an
instance's zonal storages); `subnets[].cidr` is informational and
`subnets[].config` accepted, not read; the default entry of
`availability_zones`, when declared, becomes the packer source's
`availability_zone`.

It strips `name` and refuses one that is empty afterwards (only a
whitespace-only name can reach that check, because the base already
substitutes the network id for an empty or `default` name).
`get_subnet_id()` raises when no default subnet exists. It does not accept
security groups by name, only by id, and it refuses more than five groups in
`addl_security_groups`.

There is no `security_group_ids` key: declaring it is an unknown-key
refusal at load naming the key (the shared model config forbids extra
keys), because `addl_security_groups` is the list that reaches the packer
source and the instance and storage roots; put the ids there
([when this changed](../../docs/CHANGES.md#s63)).

### `AwsCloudBuilderModel`

Extends `CloudBuilderModel` in
[cloud_builder.py](../base/src/cs_image_system/base/models/cloud_builder.py),
which extends `RuntimeBuilderModel` in
[runtime.py](../base/src/cs_image_system/base/models/runtime.py), which
extends `BuilderModel` and `NameTyped` in
[builder_model.py](../base/src/cs_image_system/base/models/builder_model.py).
The field tables, base and own, are
[CONFIGURATION 4.1 to 4.3](../../docs/CONFIGURATION.md#43-aws); what follows is what
this plugin does with each key.

The keys it adds:

- `account_id` (`str | None`): the AWS account. Reported by
  `runtime describe`; usable in templates as `{{ this.account_id }}`.
  Nothing else reads it: the account boto3 acts in is the profile's.
- `credentials` (`AwsCredentials`, empty): narrows the base
  `CredentialsBase`.
- `state_configuration` (`str`, `default`): foreign key to a state
  backend. The second rung of every storage and instance root's backend
  resolution on this runtime: a root whose own `state_configuration` is
  `default` inherits this one; `default` here falls through to the
  default backend
  ([orchestrator.py](../base/src/cs_image_system/base/orchestrator.py)).
- `ena_support` and `sriov_support` (`bool | None`): when declared,
  written into the `amazon-ebs` packer source as `ena_support =
  true|false` (the baked AMI's Elastic Network Adapter flag, set
  explicitly) and `sriov_support = true|false` (enhanced networking
  through the Intel SR-IOV interface); unset, nothing is written and
  packer's default applies.
- `iam_instance_profile` (`str | None`): the instance profile written
  into the packer source for build instances when
  `session_instance_profile` is unset (it is also the SSM fallback then).
  When both are set the SSM profile wins. Never attached to launched
  instances.
- `session_mechanism` (`str | None`): `ssm` (any case, surrounding
  whitespace ignored) is the only value. Any other string is an error the
  first time the builder's `session_mechanism()` is called, which is at
  generation.
- `session_instance_profile` (`str | None`): the SSM-capable instance
  profile given to launched instances (through the instance plugin) and
  to build instances (through the packer source).
- `ssh_username` (`str`, `default`): the bake's SSH user for images on
  this runtime that name none more specifically: step 4 of the bake-user
  order ([CONFIGURATION 5.1.1](../../docs/CONFIGURATION.md#511-the-bake-ssh-user)); an entry's
  own `ssh_username` wins over it.
- `networking` (`AwsCloudNetworkingModel | None`): narrows the base type
  and makes it optional. Missing networking logs a warning at load; image
  generation then fails (the packer source reads the VPC and subnet from
  it).
- Not init fields, discovered at load: `vpc_map`
  (`{vpc_id: {"subnets": [...]}}` from the account), `default_vpc_id`
  and `all_security_groups` (`{group_id: description}`).

What this runtime does with the keys it inherits: `type` is `aws`;
`tags` merge into every image's tags, so they reach the AMI and the
packer source, and `is_default` makes this the runtime `default`
resolves to; `region` (required) is boto3's `region_name`, the packer
`region`, the `aws` provider block and `--region` on the release and
storage-transition commands; `default_machine_type` (required) is the
instance type when neither an OS-builder runtime entry nor an image
names one, and the instance type of a launched instance that declares no
`machine_type`; `default_image_builder` is accepted and checked as a
foreign key but read by nothing: an OS-builder runtime entry with
`image_builder: default` resolves to the registry's default image builder
(the one declared `is_default: true`), not to this field;
`default_owners` joins every vendor-image query's owner list on this
runtime, after the OS builder's owners and before the entry's own (the
lookup in
[os_builder_runtime_config.py](../base/src/cs_image_system/base/models/os_builder_runtime_config.py)
takes the image builder's runtime); `default_config_username` is the
bake's SSH user when nothing more specific names one, step 5 of the
bake-user order; `ephemeral`, `retention_keep`, `on_failure` and
`teardown_after` are read as "Retention and the cycle" says.

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
| Resolution | `query_provider_image_by_id(subconfig, image_id)` | The AMI an entry pins with `image_id`, looked up with `DescribeImages` by id (`aws_utils._query_by_ami_id`) instead of the query. Same return shape; `None` when AWS does not know the id. |
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
| Power state | `can_query_instance_power_state()`, `query_instance_power_state(name)` | `True`; EC2's `State.Name` mapped onto the system's vocabulary (`pending` -> starting, `running`, `stopping`/`shutting-down` -> stopping, `stopped`, `terminated` -> absent, no instance -> absent, anything else -> unknown); `None` only when the cloud could not be asked. |
| Power state | `can_set_instance_power_state()`, `start_instance(name, timeout)`, `stop_instance(name, timeout)` | `True`; `start_instances` / `stop_instances` followed by the EC2 `instance_running` / `instance_stopped` waiter (5 s delay, `timeout // 5` attempts). Only `running_for_task` calls them. |
| Identity | `can_query_instance_identity()`, `query_instance_identity(name)` | `True`; `{"instance_id": InstanceId, "provider_hostname": PrivateDnsName}` of the named instance whatever its power state, or `None`. |
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

### Sessions

The preflight's reading of the AWS session is this plugin's, not the
core's: the builder class answers the contract's `session_status` hook
from [`session.py`](src/cs_image_system/aws_runtime/session.py), and the
core prints and judges what it answers. The hook takes the runtime's (or
an `s3` state backend's) settings, finds the profile in `profile`,
`credentials.profile_name` or `AWS_PROFILE`, and reads the caches on the
host -- `~/.aws/config` and `~/.aws/sso/cache` (`CSIS_AWS_DIR` when set)
-- never a credential value. Static keys in the environment, or a profile
without SSO, are present with no readable expiry, so the line says NOT
JUDGED and why (keys lapse without notice, and the next call says
`RequestExpired`). A legacy SSO profile's token has a fixed expiry, judged
against the expected run length. An `sso-session` profile's token renews
itself from its refresh token while the portal session lives: while the
access token has not lapsed the session is present and self-renewing and
nothing is asked of the cloud; once it has lapsed the hook makes ONE
read-only `aws sts get-caller-identity --profile <p>`, which refreshes the
cache when the refresh token still works and says EXPIRED, with
`aws sso login --profile <p>` as the renew command, when it does not. The
token's own expiry rides along for the release recipe, which wants to
know how long the session it starts on has left. The class also declares
`AWS_*` as its credential prefix (a variable set but empty is refused) and
classifies the lapsed-credential codes (`RequestExpired`, `ExpiredToken`,
...) and botocore's session classes into the one-line load failure under
"When it fails". The plugin's `initialize()` quiets the `boto3`,
`botocore` and `urllib3` loggers to INFO.

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
declared `subnets[].subnet_id` must be one of that VPC's subnets (below);
every id in `addl_security_groups` must exist; more than five of
them is an error. The declared `subnets[].public` flag is the operator's
statement and is not overwritten by the discovered `is_public`.

The subnet check compares each declared `subnet_id` with the subnets
the account listed for the declared VPC in `vpc_map`. When a declared id
is not among them the load is refused with
`Subnet <id> (<name>) in networking configuration for AWS cloud builder
<runtime> is not in VPC <vpc>.`, so a subnet from another VPC (or a typo)
fails at load rather than at the first bake or apply. The check makes a claim only
when the account's answer lists subnets for the VPC: a VPC listed without
any subnets (an empty VPC, or a session that cannot see them) leaves every
declared subnet unchecked rather than refusing all of them. A load
therefore needs a live AWS session even for a dry run, and so does every
command that loads the configuration for another runtime (the GCE cycle
included).

### The image query

`query_provider_image()` takes one OS-builder runtime entry
(`OSBuilderBaseImageBuilderSubconfig` in
[os_builder_runtime_config.py](../base/src/cs_image_system/base/models/os_builder_runtime_config.py))
and asks it for its effective query, `entry.image_query()`: an
`ImageQuery` in the SYSTEM's vocabulary
([contract/image.py](../contract/src/cs_image_system/contract/image.py)).
That query is the image-source catalog's `aws` block for the
OS builder's family (the release's layer under the tree's
`cfg/image-sources*.yml`), with the OS builder's own `query` landing on it
key by key and the runtime entry's landing on that; the publishers declared
anywhere (the OS builder's `owners`, this runtime's `default_owners`, the
entry's `owners`, in that order, deduplicated) replace the catalog's. The
entry's own `query` mapping is never rewritten. The builder then
translates it with `translate_image_query()` (the table below) and
`query_image()` in [aws_utils.py](src/cs_image_system/aws_runtime/aws_utils.py)
runs the `DescribeImages` request `describe_images_request()` makes from
it, paging through the results, and returns the newest by `CreationDate`,
or `None` when nothing matches; with `newest: false` more than one match
raises `AMIQueryError` as ambiguous. The builder reads the owner straight
from the AMI record, `ImageOwnerAlias` (for example `amazon`) else
`OwnerId` (the account id), and returns `(ImageId, owner, raw)`; the base
registers an `AwsProviderSpecificImage` in the resolved state. A record
with neither field raises `Could not get owner alias or owner id ...`. No
match returns `None`, and the base's resolve step then fails the run.
`validate` has already refused an entry whose query uses a key this
runtime cannot translate, or has no source at all, and has printed every
entry's query in both vocabularies (`image source: OS builder '<name>' on
runtime <rt> (aws): <system query> -> <EC2 query>`).

The `aws` blocks of the release's catalog are this plugin's: it ships them
as package data,
[`data/image-sources.yml`](src/cs_image_system/aws_runtime/data/image-sources.yml),
and `AwsCloudBuilder.image_source_entries()` reads that file. The core
merges every installed runtime's part by family, so the release catalog a
tree sees carries an `aws` block exactly when this plugin is installed;
a family with no public AMI publisher (`centos-stream`) is absent from the
file, and a tree that bakes it on EC2 declares its own block.

The vocabulary is the system's, with EC2's spellings kept where they
were good names; the older spellings of an entry's query (EC2's field
names in snake case, from when the system started on AWS and used its
filter keys: `root_device_type`, `virtualization_type`, `owners`, the
nested `filters:` form) still read, and an unknown key is refused by name
instead of going to a post-query filter
([when the vocabulary changed](../../docs/CHANGES.md#s106)).

### Image query translation

What `translate_image_query()` does with each key of the system's
vocabulary (`supported_query_keys()` is the set of rows not marked
refused; [tests/test_docs_image_sources.py](../../tests/test_docs_image_sources.py)
holds this table to it). The answer is `{"owners": [...], "filters":
{<EC2 filter name>: value}, "most_recent": bool}`: what packer's
`data "amazon-ami"` body and `describe_images` both take.

| System key | EC2 filter | Note |
| --- | --- | --- |
| `name` | `name` | a glob over the AMI name |
| `family` | refused | EC2 has no image families; name the image |
| `version` | refused | the catalog fills `{version}` into `name` |
| `architecture` | `architecture` | `x86_64` or `arm64`, EC2's own words |
| `publisher` | `owners` | account ids and the aliases `self`, `amazon`, `aws-marketplace` |
| `state` | `state` | `available` when unset: the query always forced it |
| `virtualization` | `virtualization-type` | `hvm` |
| `root_device` | `root-device-type` | `ebs` |
| `tags` | `tag:<key>` | one filter per tag |
| `newest` | `most_recent` | true when unset; false refuses more than one match |
| `native` | verbatim | each key an EC2 filter name, passed as written |

When the entry declares `image_id`, the base's resolve step
does not call `query_provider_image()` at all: it calls
`query_provider_image_by_id(entry, image_id)`, which runs `DescribeImages`
with `ImageIds=[<id>]` through `_query_by_ami_id` in
[aws_utils.py](src/cs_image_system/aws_runtime/aws_utils.py), with the
runtime's own client configuration (profile and region). The entry's
query is not consulted. The owner is read from the record the same way,
`ImageOwnerAlias` else `OwnerId` (else `self`), and the result is
`(ImageId, owner, raw)`. An id AWS answers `InvalidImageID.NotFound` or
`InvalidImageID.Malformed` for, or one that returns no image, gives
`None`, and the base stops resolution with `OS builder <name>: image_id
'<id>' on runtime <rt> is not known to the provider`; any other API
refusal raises `AMIQueryError`. An AMI id is regional, so a pinned id must
exist in this runtime's region. Pinning makes the base bake reproducible:
the same vendor AMI every time, where the query takes the newest match.

`AwsProviderSpecificImage.get_query_assets()` gives the packer
`data "amazon-ami"` body:

- resolved: `filters = { image-id = "<ami>" }` plus `owners = ["<owner>"]` when known;
- deferred (an image a build produces later): an `ImageQuery` (`name =
  "<pattern>*"`, `root_device = ebs`, `virtualization = hvm`, the
  architecture or `x86_64`, publisher `self`) translated like a vendor
  query and quoted: `owners = ["self"]`, `filters = { name = "<pattern>*",
  root-device-type = "ebs", virtualization-type = "hvm", architecture =
  "<arch>" }`, `most_recent = true`.

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
`note` in the report, not drift and not a failure to answer.
`verify_instance` is the deferred verification step of the instance
lifecycle; `run_session_command` is how the system runs a script on an
instance (the unmount before a detach, the post-bake tests, the AltNames
write). `query_instance_identity` feeds the generation ledger
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
  `sriov_support` only when the runtime declares them (the fixture
  declares neither, so the golden source carries neither), and, because the
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
  `lineage.bake_disk_size(ctx, image, runtime)`, the one rule the
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
running
([the incident](../../docs/INCIDENTS.md#the-aws-session-lapsed-mid-cycle-and-then-before-the-preflight-could-say-so)).

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
  `pydantic>=2.13`, and the system's own `cs-image-system-contract`,
  `cs-image-system-base` and `cs-image-system-hashicorp-utils` (the HCL
  formatter) at the same version ([pyproject.toml](pyproject.toml)).

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

The YAML this plugin owns is the `type: aws` entry under
`runtime_builders:`. Its field tables are
[CONFIGURATION 4.1](../../docs/CONFIGURATION.md#41-fields-common-to-every-builder) (every
builder), [4.2](../../docs/CONFIGURATION.md#42-fields-common-to-every-runtime) (every runtime),
[4.3](../../docs/CONFIGURATION.md#43-aws) (the `aws` keys) and [4.5](../../docs/CONFIGURATION.md#45-networking)
(`networking`); the base's own fields are there because this plugin is
what reads them on AWS, and the Models section above says what it does
with each. Three things to know that the tables do not say: `executable`,
`config` and `gitignore` are accepted from `BuilderModel` and this plugin
reads none of them; `profile`, `parameters`, `runtime_classifier` and
`executables` are refused as unknown keys (the fixture's comments record
the replacements: the modelled key is `credentials.profile_name`, and the
load names the replacement for `parameters`); and `networking` left null
loads with a warning and fails at image generation.

### What other entries contribute

These are not this plugin's fields, but the packer source reads them:

| Where | Field | Effect on AWS |
|---|---|---|
| OS builder `runtimes[]` entry | `default_machine_type` | The bake instance type for that base (the fixture bakes on `t3.medium` because a `t2.micro` OOMs). |
| OS builder `runtimes[]` entry | `ssh_username` | The bake user for that OS on this runtime (step 2 of the bake-user order); unset, the order continues down to the chain root family's vendor user. |
| OS builder `runtimes[]` entry | `owners`, `query` | The `describe_images` request. |
| OS builder `runtimes[]` entry | `image_id` | An AMI id that replaces the query; looked up by id with `DescribeImages`. |
| OS builder `runtimes[]` entry | `default_primary_disk_size` | The base image's `volume_size` on this runtime when declared. |
| OS builder | `default_primary_disk_size` | The base image's `volume_size` when the entry declares none (200 by default). |
| image `runtimes[]` entry | `machine_type` | The bake instance type for that instance image. |
| image | `primary_disk_size` | The root volume size of an instance-image bake, in GB. |
| instance | `machine_type` | The launched instance type; the runtime default otherwise. |

### Variations

- **A queried vs a pinned vendor AMI.** Without `image_id` on the OS
  builder's entry, resolution runs the `describe_images` query and takes
  the newest match, so the next base bake may start from a newer vendor
  AMI. With `image_id` the query is skipped and that one AMI is
  looked up by id; it must exist in this runtime's region, and the id is
  part of the fingerprint's vendor source.
- **Where the bake disk comes from.** `volume_size` is
  `lineage.bake_disk_size`: this runtime has no `default_disk_size`, so a
  base image takes its entry's `default_primary_disk_size`, else the OS
  builder's (200). The input fingerprint hashes the same rule, so the
  size that is hashed is the size that is baked; a fingerprint recorded
  under an older rule reads DUE until `lineage restamp --runtime <rt>
  --commit` records the current one ([when the rule changed](../../docs/CHANGES.md#s63)).

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
  profile wins); `iam_instance_profile` applies to build
  instances only when the SSM profile is unset.
- **`networking.network: default`** resolves to the account's default VPC
  at load and is refused when the account has none. **A VPC id** must be one
  the session can describe. Either way, **a declared subnet in that VPC**
  loads and **a subnet id from another VPC** (or a mistyped one) is refused
  at load (rather than at the first bake or apply);
  **a VPC the account lists without subnets** leaves the declared subnets
  unchecked.
- **Security groups in `addl_security_groups`** are checked, counted
  (at most five) and worn by every launched instance; **the same ids under
  `security_group_ids`** are an unknown-key refusal at load.
- **`ena_support` / `sriov_support` declared** (`true` or `false`) are
  written into the `amazon-ebs` source as that value; **not declared**, the
  source carries neither line and packer's defaults decide.
- **`ephemeral: true`** keeps nothing baked here past a successful run;
  **`false`** (the fixture) keeps everything until `retention_keep`, an
  image's `retention` or an explicit `dispose image`.
- **A pinned parent** (`parent_policy: pinned` with a pin, or a rebuild)
  writes `filters = { image-id = "<pinned>" }`, `owners = ["self"]` into
  the data lookup; **an unpinned or deferred parent** writes the
  name-pattern / most-recent lookup from `get_query_assets()`; **a
  resolved vendor image** writes its exact id and owner.
- **An entry's `ssh_username`** wins over the runtime's; the OS
  builder's `config_username` wins over
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
  the lookups answer "absent" and the alias pass does nothing.
- **A stopped instance** is a `note` in the state report, skips
  verification and login proof unless the task may start it, and is left
  off by the alias pass; **a running one** is verified and aliased; **a
  terminated record** counts as absent.
- **An encrypted value** (`ENC[age:...]`) anywhere in the entry is
  decrypted by the core before this plugin sees it; the plugin has no
  behaviour of its own for encryption.

## What it tests and verifies

The plugin also tells the public-safety scan the shape of its own
secret: `secret_patterns()` declares `aws-access-key` (`AKIA` or `ASIA`
plus sixteen upper-case alphanumerics), and `just public-safe`, the
pre-commit hook and the meta-state writes refuse one anywhere, so the
core's scan names no cloud and still knows this one's keys.

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
  that VPC (skipped when the account lists none for it), a
  security group in `addl_security_groups` the account does not have, and
  more than five groups in `addl_security_groups`. Missing
  `networking` is a warning, not an error. Every verdict is a `ValueError`
  with the message logged at ERROR first; the load fails and `run` exits 1
  (`validate` exits 1).
- `security_group_ids` under `networking:` is refused as an unknown key by
  the shared model config, like any other undeclared key.
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
is no further check on them. Resolution's `query_provider_image`
raises when the region is unset or the AMI record carries neither
`ImageOwnerAlias` nor `OwnerId`, and returns `None` on no match, which
[resolve.py](../base/src/cs_image_system/base/commands/resolve.py) turns
into a failed run. For an entry that pins `image_id`,
`query_provider_image_by_id` returns `None` when AWS does not know the id,
and resolve.py stops the run naming the id and the runtime.

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

`tests/test_v2_bootstrap_aws.py` holds the bootstrap's AWS section: the
entry point and the tree-derived gate, the starter's placeholders and an
unaskable account refused by name under `--quiet`, the forks following a
stubbed account, the subject forms following the ids, the import blocks,
the backend (the declared bucket when it stands, local when the bootstrap
makes it, and the second interview that binds it), the module's
statements held to the guide's Sid for Sid, and a real `tofu validate` of
a root carrying the GitHub and AWS sections together.

## When it fails

What the operator sees, what it means and what to do, for the failures
this plugin raises or takes part in. The failures that have happened live
are recorded, dated, in [INCIDENTS.md](../../docs/INCIDENTS.md); a row below links its
entry where one exists.

### Seen live

| Symptom | Meaning | What to do |
|---|---|---|
| `No valid credential sources found` from packer's `data "amazon-ami"` while your shell is logged in ([the entry](../../docs/INCIDENTS.md#packers-ami-lookup-found-no-credentials)) | packer reads no profile it is not told about; the source carries `profile = "<profile_name>"` on both the lookup and the source, so the runtime's `credentials.profile_name` is unset or the profile has no live session. | Set the profile; `aws sso login --profile <p>`. |
| `Timeout waiting for SSH` on every bake ([the entry](../../docs/INCIDENTS.md#every-aws-bake-timed-out-waiting-for-ssh)) | The VPC has no internet gateway, so packer's SSH communicator can never reach the build instance; `session_mechanism: ssm` with a profile makes packer connect through Session Manager. With that declared, the Session Manager plugin is missing on the baking host, the build instance never registered with SSM (no route to the SSM endpoints from the default subnet, the `user_data` bootstrap failed, or the profile lacks the SSM policy), or the bake ran past `ssh_timeout = "15m"`. | Read the packer log of the bake and SSM Fleet Manager for the instance. |
| `Timeout waiting for SSH` over the SSM tunnel on a Debian chain ([the entry](../../docs/INCIDENTS.md#a-debian-chain-baked-as-ec2-user-never-authenticated)) | Only the vendor user's `authorized_keys` receives packer's key, so the bake user follows the chain root's family (`admin` for debian); a runtime `ssh_username` or an entry `ssh_username` that names the wrong user brings it back. | Fix or remove that `ssh_username`. |
| An AMI carrying two volumes in the root slot; instances from it never boot ([the entry](../../docs/INCIDENTS.md#a-baked-ami-carried-two-root-slot-volumes)) | A device hard-coded for a Debian root, whose root is `/dev/xvda`. The mapping uses the source AMI's real `RootDeviceName`, else the family default, so only a deferred source whose chain root family is unknown to `_chain_root_family` still gets `/dev/sda1`. | Resolve the vendor query, or make the chain root's family one the map knows. |
| A bake that dies mid-provisioner (`dnf update` killed), or an instance that stops answering SSM after boot ([the entry](../../docs/INCIDENTS.md#a-1-gb-bake-host-starved-the-package-manager-and-the-ssm-agent)) | A 1 GB `t2.micro` cannot keep the package manager and the SSM agent alive at once. | Bake on `t3.medium` (the OS builder entries' `default_machine_type`); give the instance its own `machine_type`. |
| `curl: (23)` in the agent provisioner on Debian ([the entry](../../docs/INCIDENTS.md#curl-refused-to-re-download-the-ssm-agent-on-debian)) | The `user_data` bootstrap had already left a root-owned `/tmp/ssm.deb`. The provisioner skips the install when the agent is present and downloads to its own file name. | Nothing; a recurrence means the agent is absent and the download target clashes again. |
| `sft ssh` hangs on the advertised private address while SSM works ([the entry](../../docs/INCIDENTS.md#sft-ssh-hung-on-an-instance-every-step-had-reported-as-launched)) | The instance root creates `csis-instances` with SSH ingress from `ssh_ingress_security_group_ids` only (opening the shared CIDRs is forbidden), and the gateway relay needs the target in the gateway's own group (`addl_security_groups`). | Check those two lists. |
| `foreign` AMIs in the state query: our tags, no record ([the entry](../../docs/INCIDENTS.md#orphan-amis-from-failed-and-unrequested-bakes)) | Orphans from failed or unrequested bakes (a stale runner script). | `state import` adopts one, `dispose image` removes a recorded one, the console deregisters the rest. A `foreign` line is never hard drift, but every line is actionable. |
| `changed` for a child baked in the same run as its parent ([the entry](../../docs/INCIDENTS.md#a-follow-image-kept-its-generation-time-tags)) | Generation-time tags (a `series-...` parent, a placeholder fingerprint); the packer plugin calls `retag_image` after every bake. | `lineage relabel --runtime <rt>` re-tags any build whose tags still disagree with its record. |
| `No valid credential sources found ... backend s3 ... the SSO session has expired` from a `tofu plan` after `cloud-preflight` passed, or `AWS Error: ...` from `get_vpc_map_and_default_vpc_id` on any load, GCE work included ([the entry](../../docs/INCIDENTS.md#the-aws-session-lapsed-mid-cycle-and-then-before-the-preflight-could-say-so)) | The session lapsed mid-run. Environmental, not a defect: `preflight` and the strict state query flag a session expiring within `config.preflight.expected_run_minutes`, and an `sso-session` profile reports no fixed expiry. | `aws sso login --profile noaa`, then `just full-test-legs` or the legs that were running. |
| `InvocationDoesNotExist` right after `send_command` ([the entry](../../docs/INCIDENTS.md#invocationdoesnotexist-right-after-send_command)) | SSM had not yet registered the invocation. The poll tolerates that code until its deadline ([test_v2_aws_parity.py](../../tests/test_v2_aws_parity.py)); any other SSM error still raises. | Nothing; the receipt is written once the poll completes. |
| A validation error naming `credentials.profile_nme` ([the entry](../../docs/INCIDENTS.md#a-misspelt-credentials-key-was-silently-dropped)) | The typed `AwsCredentials` refuses a misspelt key, so a typo cannot leave the profile unset with boto3 falling back to `AWS_PROFILE` or nothing. | Fix the key. |
| `STOPPED (switched off; not drift)` in a `note`, or `cannot run a command on '<name>': it is STOPPED (switched off; not drift)` ([the entry](../../docs/INCIDENTS.md#a-stopped-machine-was-reported-as-the-provider-could-not-answer)) | The power-state hook separates a machine the operator switched off from an unreachable cloud. | Leave it off, or start it yourself; the system starts one only for a bounded task. |
| The strict query refuses the launch that finishes an upgrade ([the entry](../../docs/INCIDENTS.md#the-first-live-replacement-four-traps-in-one-afternoon)) | After `upgrade instance` moves the pin, the booted AMI is behind it by design; with the pending-replacement marker present it is a `note`, without the marker it is drift. | Run the launch; if the marker is gone, `upgrade instance` again. |
| A replacement writes no aliases (the same entry) | The alias pass waits for a machine launched in the same run; one that never enrolls gets no alias that run (the log says so). | Enroll the machine; the next run writes the alias. |

A disposal's success is read from the cloud, not from the log line:
after `dispose image <ids> --no-dry-run --commit`, `describe-images` on
the ids answers an empty list.

### Raised by the code

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

The subnet line means a declared `subnets[].subnet_id` is not one of the
subnets the account lists for the declared VPC: a typo, a subnet from
another VPC or account, or a `network: default` that resolved to a VPC other
than the one the subnets belong to. Fix the subnet id or the `network` in the
tree; without this check the mistake surfaces at the first bake or apply
as a packer or tofu error about the subnet. The security-group count line
counts only `addl_security_groups`.

Declaring `networking.security_group_ids` fails the load as an unknown key,
with the shared model config's extra-key error naming
`security_group_ids`; move its ids into `addl_security_groups`, which is
the list that reaches the instance and storage roots.

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
OS builder <name>: image_id '<id>' on runtime <rt> is not known to the provider   (base: the pinned AMI is not in this region, is deregistered, or is malformed)
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
- [dummy-plugin](../dummy-plugin/README.md): the extension template.
- Base classes: [runtime.py](../base/src/cs_image_system/base/models/runtime.py), [cloud_builder.py](../base/src/cs_image_system/base/models/cloud_builder.py), [credentials.py](../base/src/cs_image_system/base/models/credentials.py), [provider_specific_image.py](../base/src/cs_image_system/base/models/provider_specific_image.py), [builder_base_runtime.py](../base/src/cs_image_system/base/basic/builder_base_runtime.py), [abstract_version_checker.py](../base/src/cs_image_system/base/basic/abstract_version_checker.py).
- Consumers of the hooks: [state_query.py](../base/src/cs_image_system/base/state_query.py), [retention.py](../base/src/cs_image_system/base/retention.py), [dispose.py](../base/src/cs_image_system/base/commands/dispose.py), [verify_instance.py](../base/src/cs_image_system/base/commands/verify_instance.py), [unmount.py](../base/src/cs_image_system/base/commands/unmount.py), [relabel.py](../base/src/cs_image_system/base/commands/relabel.py), [release.py](../base/src/cs_image_system/base/release.py), [power_state.py](../base/src/cs_image_system/base/power_state.py), [provider_aliases.py](../base/src/cs_image_system/base/provider_aliases.py), [runtime_facts.py](../base/src/cs_image_system/base/commands/runtime_facts.py).
- [docs/OPERATIONS.md](../../docs/OPERATIONS.md) for the credential contract and the operator's cycles; [docs/DESIGN.md](../../docs/DESIGN.md) for the design; [docs/PLUGINS.md](../../docs/PLUGINS.md) for the package index.
- [The configuration reference](../../docs/CONFIGURATION.md) -- every field of the YAML this plugin reads, with an example.
