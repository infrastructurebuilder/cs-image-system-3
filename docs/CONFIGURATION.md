# Configuration reference

This document describes a cs-image-system configuration tree: every file,
every resource type, every field. The models in
[`packages/base/src/cs_image_system/base/models/`](../packages/base/src/cs_image_system/base/models/)
and the plugins' `*_models.py` files are the source of truth; the frozen
fixture under [`tests/fixtures/config/`](../tests/fixtures/config/) supplies
every example. Its people are synthetic personas on example domains.

Every model is a pydantic dataclass with one shared configuration
([`model_config.py`](../packages/base/src/cs_image_system/base/models/model_config.py)):

- an **unknown key is an error** (`extra="forbid"`), naming the field path;
- **numbers become strings** where a string is declared
  (`family_version: 11` reads as `"11"`, an unquoted account id likewise);
- a key with **no value** where a list, set or mapping is declared reads as
  the empty collection (`members:` alone is an empty set).

In the tables below, `type` is the YAML key; the Python field is `type_`.
"Required" means the load refuses an entry without it.

## 1. The tree

A configuration root is the directory named by `--root-dir` (default: the
current directory). The Justfile drives the live tree named by
`CSIS_CONFIG_ROOT`; the tests own the fixture.

| Path | Read by | Contents |
| --- | --- | --- |
| `cfg/` | every load | the global settings and every **builder** (`*.yml` / `*.yaml` directly in `cfg/`, not subdirectories) |
| `groups/` | every load, recursively | `users:` and `groups:` lists (both keys, any file) |
| `storages/` | every load, recursively | `storages:` lists |
| `images/` | every load, recursively | `images:` lists |
| `instances/` | every load, recursively | `instances:` lists |
| `base_images/` | nobody | the `base_images` kind is registered as base-only and is **not read**; base images are the OS builders in `cfg/os-builders.yml` |
| `overlays/` | nobody, unless named | transient declaration files (section 12) |
| playbooks, scripts | the bake | referenced by relative path from the root (`setup_dask.yml`, `mod_image.sh`, `playbooks/…`) |
| `generated/` | written by a run | see below |
| `meta-state/` | written by a run | see below |
| `.age-identity`, `.age-recipient` | the fixture only | its committed TEST identity and public key |

### 1.1 Load order

1. **`cfg/`**: every YAML file is loaded and merged into one document. A
   list-valued key (`executables`, `runtime_builders`, …) is concatenated
   across files; a scalar or mapping key keeps the last file's value. Names
   must be unique within a list; a `name` or `type` containing `{{` is
   refused.
2. **Templating**: the merged document is rendered with Jinja. Available
   scopes: `ENV` (the process environment, `{{ ENV.USER }}` or
   `{{ ENV['X'] }}`), `execution.timestamp` (the run start formatted with
   `dateformat`), `execution.date`, `execution.dateformat`, and `this`
   (the entry being rendered, e.g. `{{ this.region }}`,
   `{{ this.parent.family }}` inside a runtime entry of an OS builder).
3. **Global settings**: the keys that are not builder collections structure
   into `IAConfig` (section 2).
4. **Builders**, in this order: `runtime_builders`, `state_backends`,
   `group_builders`, `user_builders`, `os_builders`, `mod_builders`,
   `storage_builders`, `image_builders`, `instance_builders`. Every entry
   needs `name` and `type`. Foreign keys (`runtime`, `state_configuration`,
   `image_builder`, `executable`, …) are resolved after all builders exist,
   so order within `cfg/` does not matter.
5. **Collections**, in this order: users, groups (both from `groups/`),
   storages, images, instances. Users are read before groups so every
   member can be checked. Overlays and `--undeclare` are applied to each
   collection before its items structure (section 12).

### 1.2 `type`, aliases and `is_default`

- On a **builder**, `type` names the plugin model that structures the entry
  (`aws`, `packer-ebs`, `tf-aws-efs`, `okta-tf-ro`, `s3`, …). A plugin may
  register a model under several names; the canonical name is recorded.
- On a **collection item**, `type` names the builder that owns it, by the
  builder's `name` or one of its `aliases` (`type: pckr-ebs-ans`,
  `type: some-other-builder`). Inside `modifications:` and `storages:` the
  item's `type` likewise names a mod builder or a storage builder.
- `type: default`, or an omitted `type` where the field has a default,
  resolves to the builder marked `is_default: true` in that class of
  builder. At most one entry per class may be the default; the load refuses
  a second. The same rule serves `runtime: default`, `image_builder:
  default`, `state_configuration: default`.
- `aliases:` is a list of extra names an entry answers to. Aliases must be
  unique within the class; `default`, `self` and the empty string are not
  allowed as a name or an alias; `/` and `\` are refused.
- Names are normalized: trimmed, lower-cased, spaces and colons replaced by
  `_`. The original spelling survives as the display name and is what an
  output artifact is named from.

### 1.3 What a run writes

`generated/` (the `generation_directory`) holds, per lifecycle, a
directory with its runner script and one sub-directory per builder that
emitted something:

```text
generated/
  .gitignore                     # the merged gitignore (section 2)
  final_execution.sh
  identity/   run-identity.sh   <group builder>/  <user builder>/  attributes-plan.json (when attributes are declared)
  storage/    run-storage.sh    <storage builder>/ ...
  base-image/ run-base-image.sh <image builder>/ ...
  instance-image/ run-instance-image.sh <image builder>/ ... <instance builder>/ ...
  release/    run-release.sh    releases.yaml
  retention/
  run-summary.json  state-report.json
```

`meta-state/` is the committed record of what the system knows:

| File | Holds |
| --- | --- |
| `identity.yaml` | the identity read-model: groups (builder, identity type, gid policy, managed, members, admins), users, user builders |
| `storage.yaml` | the storage read-model: builder, requested and current state, allowed groups, share mode, lifecycle, attachments |
| `storage-state.yaml` | every recorded storage transition |
| `lineage.yaml` | every recorded build |
| `pins.yaml` | instance pins and image pins (`<image>@<runtime>`) |
| `launch-params.yaml` | what each launched instance was launched with |
| `runs.yaml` | run summaries |
| `verifications.yaml` | ephemeral instance verifications |
| `image-tests.yaml` | post-bake test results per build |
| `releases.yaml` | every release and the current release per model |
| `mod-tests.yaml` | local modification test results |

## 2. `cfg/_config.yml`

Model: `IAConfig`
([`ia_config.py`](../packages/base/src/cs_image_system/base/models/ia_config.py)).
The builder collections listed in 1.1 are also accepted at the top level of
any `cfg/` file; they are documented in their own sections.

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `id` | str | required | the configuration's identifier |
| `generation_directory` | str | `generated` | where a run writes, relative to the root |
| `dateformat` | str | `%Y-%m-%d-%H%M%S` | `strftime` format of `execution.timestamp` (used in generated image names) |
| `gitignore` | list[str] | `[]` | entries appended to the built-in list (`target/`, `.terraform/`, `terraform.tfstate`, `terraform.tfstate.backup`, `!.terraform.lock.hcl`) and written to `generated/.gitignore`; duplicates keep their last position |
| `sleep_before_finalization` | int | `1` | seconds to wait before finalization executes |
| `encryption` | mapping | `{recipients: []}` | see 2.1 |
| `public_safe` | mapping | `{allow: []}` | see 2.2 |
| `config` | mapping | `{}` | the global settings the run reads; see 2.3 |
| `executables` | list | `[]` | section 3 (usually in its own file) |
| `working_directory` | str | `./workdir` | accepted; the CLI's `--root-dir` (or the current directory) is the working directory, so this value is not used |
| `last_updated` | datetime | now | accepted; not used |

### 2.1 `encryption`

`EncryptionConfig`
([`encryption_config.py`](../packages/base/src/cs_image_system/base/models/encryption_config.py)).

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `recipients` | list[str] | `[]` | age X25519 public keys (`age1…`), one per holder. Every `ENC[age:…]` value in the tree is encrypted to all of them. `encrypt` and `reencrypt` read this list as text, without loading the tree. |

### 2.2 `public_safe`

`PublicSafeConfig`
([`public_safe_config.py`](../packages/base/src/cs_image_system/base/models/public_safe_config.py)).

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `allow` | list[str] | `[]` | what the public-safe scanner lets through, by decision. A plain entry is a **case-insensitive substring**: a finding whose text contains it is allowed (an address domain, a service-account address). `path:<glob>` accepts a **file whole**, matched against the relative path and the basename. |

### 2.3 `config` keys the code reads

Any key is accepted under `config:`; these are the ones the system reads.
Everything else is carried on the context for plugins (it is not a
template scope: `{{ config.x }}` does not resolve in model fields).

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `apply_identity` | bool or list[str] | `false` | let the identity roots apply |
| `apply_storage` | bool or list[str] | `false` | let the storage roots apply |
| `apply_instances` | bool or list[str] | `false` | let the instance roots apply |
| `apply_release` | bool or list[str] | `false` | let the release lifecycle mark artifacts in the cloud |
| `use_state_backends` | bool | `false` | emit terraform `backend` and remote-state blocks (needs real state buckets) |
| `module_source_base` | str | `../tfmodules` | where generated `module` calls find the modules: a relative path is relative to the configuration root and rewritten for each root's depth; an absolute path or a git/registry URL passes through |
| `admin_public_keys` | list[str] (a single string is accepted) | `[]` | OpenSSH public key lines for the mandatory local admin user of every base image; anything resembling private-key material is refused; per-base override on the OS builder |
| `okta_gateway_selector` | str | none | fallback `gateway_selector` for an OPA group builder that sets none |
| `require_mod_tests` | bool | `false` | a release refuses a build whose modification has no local mod-test record |
| `require_image_tests` | bool | `true` | a release of an image that declares `tests.post_bake` needs a passing record |
| `require_released_builds` | bool | `false` | an instance may be pinned only to a released build of its image |
| `preflight.expected_run_minutes` | int | `30` | a credential session expiring sooner is reported as blocking |

**The `apply_*` flags.** `true` lets every root of that lifecycle apply;
`false` (or absent) lets none. A **list** names the roots that may apply,
by builder name or by the runtime a root belongs to
(`apply_instances: [gcloud-east1]` lets the GCE instance root apply and no
other). The generated runner scripts call `cs-image-system apply-check`
just before every `apply`; it re-reads these flags (and the overlays the
run was generated under) at execution, so a script generated when a flag
was on does not apply after it was turned off. There are no separate
`require_*` list forms; the `require_*` keys are booleans.

### 2.4 Example

[`cfg/_config.yml`](../tests/fixtures/config/cfg/_config.yml):

```yaml
---
id: cs-image-action-test
generation_directory: ./generated/
sleep_before_finalization: 30
encryption:
  recipients:
    - age1hl95vsankapyxyyejhdejmywuwc4ddvpjmflj0hf0y8xjtuk3vystd9ang
public_safe:
  allow:
    - ".iam.gserviceaccount.com"     # a service account's address is an identifier
    - "path:.age-identity"           # the fixture's TEST identity, committed on purpose
gitignore:
  - ".*"
  - "!.terraform.lock.hcl"
  - "!.gitignore"
  - "**/target/"
dateformat : "%Y%m%d_%H%M%S"
config:
  use_state_backends: true
  apply_instances: false
  apply_storage: false
  apply_identity: false
  module_source_base: ../tfmodules
  some_key: some_value
  systemuser: "{{ ENV.USER }}"
  okta_gateway_selector: "environment=staging"
  admin_public_keys:
    - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPlaceholderKeyReplaceMeReplaceMeReplaceMe csis-admin-placeholder"
```

## 3. `cfg/executables.yml`

Key: `executables`. Model: `ExecutableModel`
([`executable.py`](../packages/base/src/cs_image_system/base/models/executable.py)).
Builders refer to an executable by its `name` (`executable: open-tofu-1`).

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `name` | str | required | the name builders reference; non-empty, unique; not `default`/`self` |
| `type` | str | `executable` | selects the version checker; `default` means "same as `name`" |
| `version` | str or null | null | a version requirement (`">=1.14"`, `">1,<2"`), a PEP 440 specifier set checked by `validate` and every run |
| `binary` | str or null | the name | path or command to run |
| `prepended_arguments` | list[str] | `[]` | arguments placed before the command's own |
| `appended_arguments` | list[str] | `[]` | arguments placed after |
| `args` | list[str] | `[]` | arguments set by the system at emission; not for the YAML |
| `config` | mapping | `{}` | free-form |
| `working_directory` | path or null | null | set by the run; not for the YAML |
| `description` | str or null | null | free text |
| `aliases` | list[str] | `[]` | extra names |

**What `validate` checks (stage 48.1).** Every entry's binary must exist
(an absolute path, or a name on PATH), and when it declares a `version`
the version its checker reads must satisfy that PEP 440 specifier set; a
mismatch, a missing binary or an unreadable version fails validation and
every run, by name. The checker is looked up under the entry's `name`
first -- `packer` (`packer version -machine-readable`), `tofu`
(`--version -json`), `gcloud` (the `Google Cloud SDK` line), `aws-cli`
(`aws --version`), `ansible-playbook` (`[core x.y.z]`) and `bash` have
their own -- then under its `type` (`type: packer` on an entry with
another name); the default type, `executable`, is the generic checker:
`<binary> --version`, the first dotted number on the first line (`jq`,
`yq`, `docker`). One INFO line records what was checked and the versions
found. The fixture's requirements are the floors CI's runners and the
operator's machine ran in 2026-09.

[`cfg/executables.yml`](../tests/fixtures/config/cfg/executables.yml):

```yaml
---
executables:
  - name: aws-cli
    version: ">=2.32"
    binary: aws
  - name: packer
    version: ">=1.14, <1.15"
    binary: /usr/local/bin/packer
  - name: packer-1.9.4
    version: ">=1.8, <1.10"
    binary: packer-1.9.4
    type: packer
  - name: gcloud
    binary: /usr/local/bin/gcloud
    version: ">=2026.02.0, <2027.01.0"
  - name: ansible-playbook
    binary: /usr/local/bin/ansible-playbook
    version: "<2.21"
  - name: bash
    binary: /usr/local/bin/bash
  - name: docker
    binary: /usr/local/bin/docker
  - name: open-tofu-1
    type: tofu
    binary: /usr/local/bin/tofu
    version: ">1,<2"
  - name: yq
    version: ">=4.5"
  - name: jq
    version: ">=1.8"
```

## 4. `cfg/runtime-builders.yml`

Key: `runtime_builders`. Types: `aws`
([`aws_runtime_models.py`](../packages/aws-runtime-plugin/src/cs_image_system/aws_runtime/aws_runtime_models.py))
and `gcloud`
([`gcp_runtime_models.py`](../packages/gcloud-runtime-plugin/src/cs_image_system/gcloud_runtime/gcp_runtime_models.py)).
A runtime is where images are baked and instances stand; other builders
name it through `runtime:`.

### 4.1 Fields common to every builder

`NameTyped` and `BuilderModel`
([`builder_model.py`](../packages/base/src/cs_image_system/base/models/builder_model.py)).
Every builder in sections 4 to 10 has these.

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `name` | str | required | unique within its class |
| `type` | str | required | the plugin model |
| `description` | str or null | null | free text; templates allowed |
| `aliases` | list[str] | `[]` | extra names |
| `executable` | str or null | null (plugin models set their own) | an entry of `executables` |
| `is_default` | bool | `false` | the entry `default` resolves to |
| `config` | mapping | `{}` | free-form |
| `gitignore` | list[str] | `[]` | extra gitignore entries for this builder's output |
| `tags` | mapping[str, str] | `{}` | tags applied to what the builder creates |
| `parameters` | — | — | **refused** with a message: module inputs are a storage builder's `variables:` |

Builders that bake or launch on a runtime (`RuntimeEnabledBuilderModel`:
image, instance and storage builders) add:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `runtime` | str | `default` | the runtime builder (name or alias) |

### 4.2 Fields common to every runtime

`RuntimeBuilderModel` and `CloudBuilderModel`
([`runtime.py`](../packages/base/src/cs_image_system/base/models/runtime.py),
[`cloud_builder.py`](../packages/base/src/cs_image_system/base/models/cloud_builder.py)).

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `default_machine_type` | str | required | the machine type for bakes and instances that name none |
| `default_image_builder` | str | `default` | the image builder used when an image's runtime entry names none |
| `default_owners` | list[str] or null | null | accepted; not read by the cloud plugins |
| `credentials` | mapping | `{}` | provider-specific (4.3, 4.4); an unknown key is refused |
| `default_config_username` | str or null | null | the ssh user for bakes when neither the OS builder nor its runtime entry names one |
| `ephemeral` | bool | `false` | nothing baked here survives a successful run: the closing `retention` lifecycle disposes every image on this runtime. Declared storages are never touched. |
| `retention_keep` | int or null | null | how many builds per image series survive on this runtime when the image declares no `retention`; null keeps all |
| `on_failure` | str or null | null | runtime default for ephemeral instances: `keep` or `teardown` |
| `teardown_after` | str or null | null | runtime default: `<number>` followed by `m`, `h` or `d` |
| `region` | str | required | the region |
| `networking` | mapping | required in the base model; optional (null) on `aws` and `gcloud` | 4.5 |

### 4.3 `aws`

`AwsCloudBuilderModel`.

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `account_id` | str or null | null | the account (a number is coerced to a string) |
| `state_configuration` | str | `default` | a state backend (section 10); `default` inherits the runtime's, else the default backend |
| `ena_support` | bool or null | null | passed to the packer source |
| `sriov_support` | bool or null | null | accepted; not read |
| `iam_instance_profile` | str or null | null | instance profile attached to build VMs |
| `session_mechanism` | str or null | null | `ssm`: bakes and debug sessions go through SSM (the agent is baked into base images) |
| `session_instance_profile` | str or null | null | the profile attached to launched instances for SSM sessions |
| `ssh_username` | str | `default` | override of the bake ssh user |
| `networking` | mapping or null | null | 4.5 with the AWS additions |
| `credentials` | mapping | `{}` | `AwsCredentials`: `profile_name`, `aws_access_key_id`, `aws_secret_access_key`, `aws_session_token` (all str or null). Values belong in the environment: name a profile, or carry `{{ ENV['…'] }}` templates. |

At load the AWS runtime reads the account's VPCs and security groups with
these credentials: `networking.network` must be a VPC of the account (or
`default`, resolved to the default VPC); every security group must exist;
more than five in total is refused. A load therefore needs a live AWS
session.

### 4.4 `gcloud`

`GCPCloudBuilderModel`.

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `project_id` | str or null | null | the project |
| `zone` | str or null | null | the zone for build VMs and instances |
| `service_account_email` | str or null | null | the service account attached to build VMs and instances |
| `default_disk_size` | int or null | null | bake disk size in GB for every image baked here (a GCE boot disk is exactly its image's disk); null uses the image's own value |
| `bake_preemptible` | bool | `false` | bake on preemptible (spot) build VMs |
| `state_configuration` | str | `default` | a state backend (section 10); `default` inherits the runtime's, else the default backend |
| `ssh_username` | str | `default` | override of the bake ssh user |
| `session_mechanism` | str or null | null | `iap` is the only supported value |
| `networking` | mapping or null | null | 4.5 with `network_tags` |
| `credentials` | mapping | `{}` | the empty base: GCE uses Application Default Credentials, so any key here is refused |

At load the GCP runtime resolves the project; when it can, it checks
`networking.network` (or `default`) and every subnet against the project
and warns about a network tag no firewall rule targets.

### 4.5 `networking`

`RuntimeNetworkingModel`, `RuntimeSubnetModel`, `RuntimeAvailabilityZoneModel`.

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `name` | str | the network | a label; must not be empty after templating |
| `network` | str | `default` | the VPC id (AWS) or network name (GCP); `default` resolves to the account's default VPC / the project's `default` network |
| `subnets` | list | required, at least one | exactly one entry must have `is_default: true` |
| `subnets[].name` | str | the subnet id | label |
| `subnets[].subnet_id` | str | required | the subnet id (AWS) or `projects/…/subnetworks/…` path (GCP) |
| `subnets[].is_default` | bool | `false` | the subnet bakes and instances use |
| `subnets[].public` | bool | `false` | informational |
| `subnets[].cidr` | str or null | null | informational |
| `subnets[].config` | mapping | `{}` | free-form |
| `availability_zones` | list | `[]` | entries `{name, is_default}`; the default zone is passed to the instance root |
| `security_group_ids` (aws) | list[str] | `[]` | security groups for build VMs and instances |
| `addl_security_groups` (aws) | list[str] | `[]` | existing groups every instance also wears; never modified |
| `ssh_ingress_security_group_ids` (aws) | list[str] | `[]` | groups whose members may SSH in; when set, port-22 ingress references only these groups, never a CIDR |
| `network_tags` (gcloud) | list[str] | `[]` | network tags that select firewall rules |

### 4.6 Examples

[`cfg/runtime-builders.yml`](../tests/fixtures/config/cfg/runtime-builders.yml)
(the AWS default and the GCE runtime; the fixture also declares `aws-east1`
and `west1`):

```yaml
---
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
      session_mechanism: ssm
      session_instance_profile: AmazonSSMRoleForInstancesQuickSetup
      default_machine_type: t2.micro
      default_image_builder: pckr-ebs-ans
      networking:
        network: vpc-0c78d0d63b7a100df
        ssh_ingress_security_group_ids:
        - sg-03015ec107ae5f81a
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
    - name: gcloud-east1
      aliases:
        - gcp
        - google
        - us-east1
      type: gcloud
      project_id: csis-sandbox
      zone: us-east1-b
      session_mechanism: iap
      service_account_email: csis-runner@csis-sandbox.iam.gserviceaccount.com
      default_disk_size: 10
      bake_preemptible: true
      ephemeral: true
      tags:
        Project: csis-sandbox
        Environment: Development
      region: us-east1
      default_machine_type: e2-micro
      default_image_builder: pckr-gce-ans
      networking:
        network: default
        subnets:
        - name: subnet1
          subnet_id: projects/csis-sandbox/regions/us-east1/subnetworks/default
          is_default: true
          public: true
```

## 5. `cfg/os-builders.yml`

Key: `os_builders`. An OS builder **is** a base image: it names the vendor
image to start from on each runtime, the capabilities the base declares,
the update policy and the in-bake tests. Instance images point at it by
name through `source_image`.

Model: `OsBuilderModel`
([`os_builder_model.py`](../packages/base/src/cs_image_system/base/models/os_builder_model.py)).
Types: `rhel` (dnf; adds `subscription_id`), `fedora` (dnf), `debian`
(apt), `ubuntu` (apt), `alpine` (apk)
([`default-os-plugin`](../packages/default-os-plugin/src/cs_image_system/default_os_plugin/)).

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `family` | str | required | the OS family token. The mod-test harness knows `rhel`, `rocky-linux`, `alma-linux`, `centos`, `debian`, `ubuntu`, `fedora`; the plugins branch on `debian`/`ubuntu` for apt. |
| `family_version` | str | required | major version (a number is coerced); `rhel` accepts 8, 9 or 10 |
| `architecture` | str | `default` | passed to images that leave `architecture` at its default; otherwise `x86_64` |
| `default_primary_disk_size` | str or int | `default` (= 200) | GB; the default for images built from this base |
| `tags` | mapping[str, str] | `{}` | tags on the baked image |
| `owners` | list[str] | `[]` | image owners for the vendor-image query (`self`, `amazon`, an account id, `almalinux-cloud`) |
| `query` | mapping | `{}` | the vendor-image query: `filters:` by provider field (`name`, `state`, `root_device_type`, `architecture`, `virtualization_type`); the newest match is the source |
| `runtimes` | list | required, at least one | one entry per image builder (5.1); `image_builder` unique within the list |
| `config_username` | str or null | null | sudo-capable ssh user on the vendor image, used for provisioning |
| `auto_update` | bool | `false` | alias for `update: {policy: full}` when `update` is absent |
| `update` | mapping or policy name | null | 5.2 |
| `identity_types` | list[str] | `[]` | identity types this base bakes prerequisites for (`okta`); an instance image whose group's builder is of another type is refused |
| `storage_types` | list[str] | `[]` | storage types instances of this base may attach (`ebs`, `efs`, `s3`, `pd`, `filestore`, `gcs`); each must have a configured storage builder |
| `admin_user` | str | `csisadmin` | the mandatory local admin user; must not be empty |
| `admin_public_keys` | list[str] or null | null | per-base override of `config.admin_public_keys`; public keys only |
| `local_test_image` | str or null | null | the container standing in for this OS in local mod tests; default derived from family/version (`almalinux:<v>` for rhel 10 and above, `rockylinux:<v>` below) |
| `tests` | mapping | `{}` | in-bake assertions (5.3) |
| `subscription_id` (rhel) | str or null | null | accepted; not read |
| `is_default` | bool | `false` | the base `source_image: default` resolves to |

### 5.1 `runtimes[]` entries

`OSBuilderBaseImageBuilderSubconfig`
([`os_builder_runtime_config.py`](../packages/base/src/cs_image_system/base/models/os_builder_runtime_config.py)).

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `image_builder` | str | `default` | the image builder (section 6) that bakes this base on its runtime |
| `name` | str or null | null | a label; unique within the builder |
| `type` | str | the parent's name | set by the loader |
| `description` | str | templated | free text |
| `image_id` | str or null | null | a fixed provider image id instead of a query |
| `image_name` | str or null | null | accepted; not read |
| `auto_update` | bool or null | null | overrides the builder's `auto_update` for this runtime |
| `default_machine_type` | str or null | null | machine type for bakes on this runtime |
| `default_primary_disk_size` | int | `100` | GB |
| `tags` | mapping[str, str] | `{}` | merged over the builder's tags |
| `owners` | list[str] | `[]` | appended to the builder's owners |
| `query` | mapping | `{}` | merged over the builder's query, key by key |
| `ssh_username` | str | `default` | the bake ssh user on this runtime; unset falls back to `config_username`, then the runtime's `default_config_username` |
| `tests` | mapping or null | null | when set, **replaces** the builder's `tests` for bakes on this runtime |
| `tags`, `config` | | | accepted (`config` is not read); `aliases` are refused |

### 5.2 `update`

`UpdatePolicy`
([`update_policy.py`](../packages/base/src/cs_image_system/base/models/update_policy.py)).
A mapping, or a bare policy name.

| Key | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `policy` | str | `none` (`full` when `auto_update: true`) | `none`, `security`, `packages`, `full` |
| `packages` | list[str] | `[]` | with `packages`: exactly these; with other policies: also these |
| `exclude` | list[str] | `[]` | patterns never touched by any policy (`kernel*`); may not overlap `packages` |
| `pin` | mapping[str, str] | `{}` | package → version, installed and version-locked; a version may not be empty or contain a space |
| `refresh_days` | int or null | null | re-bake the series when its head is at least this old (positive) |

`policy: packages` needs `packages` and/or `pin`. The bake records the
resulting package set at `/var/lib/csis/packages.txt`.

### 5.3 `tests`

Validated by [`image_tests.py`](../packages/base/src/cs_image_system/base/image_tests.py).
Assertions run as the last packer provisioner; a failing one fails the bake.

| Key | Shape | Assertion |
| --- | --- | --- |
| `files` | list of `{path (required), contains, mode}` | the file exists; contains the string; has the octal mode |
| `packages` | list[str] | `rpm -q` or `dpkg -s` succeeds |
| `commands` | list of `{run (required), expect_rc (0), contains}` | exit status, or output contains the string |
| `services_enabled` | list[str] | `systemctl is-enabled` |
| `users` | list[str] | `id -u` |
| `post_bake` | the same keys plus `mounts` (list of absolute mount points) | run on a launched ephemeral instance by `verify instance`, recorded per build in `meta-state/image-tests.yaml` |

### 5.4 Example

[`cfg/os-builders.yml`](../tests/fixtures/config/cfg/os-builders.yml), the
default base (the fixture also declares `my-deb-11` and `basic-rhel-9`):

```yaml
---
os_builders:
  - name: basic-rh-10
    identity_types: [okta]
    storage_types: [ebs, efs, s3, pd, gcs]
    tests:
      packages: [nfs-utils]
      files:
        - path: /etc/yum.repos.d/oktapam-stable.repo
          contains: "dist.scaleft.com"
    update:
      policy: security
      packages: [openssl]
      exclude: ["kernel*"]
    type: rhel
    family: rhel
    family_version: 10
    is_default: true
    runtimes:
    -   name: aws-my-rhel8
        default_machine_type: t3.medium
        owners:
            - "self"
            - "764336703387"
        query:
          filters:
            name: "AlmaLinux OS 10*x86_64"
            state: available
            root_device_type: ebs
            architecture: x86_64
            virtualization_type: hvm
    -   name: gcp-my-rh10
        image_builder: pckr-gce-ans
        ssh_username: packer
        tests:
          packages: [google-guest-agent]
          files:
            - path: /etc/yum.repos.d/oktapam-stable.repo
              contains: "dist.scaleft.com"
        default_machine_type: e2-small
        owners:
            - almalinux-cloud
        query:
          filters:
            name: "almalinux-10-v*"
```

## 6. `cfg/image-builders.yml`

Key: `image_builders`. An image builder produces an image on one runtime
from a base or an instance image. Model: `ImageBuilderModel`
([`image_builder_model.py`](../packages/base/src/cs_image_system/base/models/image_builder_model.py))
and `PackerImageBuilderModel`
([`packer_models.py`](../packages/packer-plugin/src/cs_image_system/packer_plugin/packer_models.py)).
Types: `packer-ebs` (the `amazon-ebs` source) and `packer-gce` (the
`googlecompute` source); the two share one body, the runtime plugin owns
the source block.

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| common builder fields (4.1) | | | `executable` names the packer entry |
| `runtime` | str | `default` | the runtime this builder bakes on |
| `default_machine_type` | str | `default` | machine type for bakes when the image and the runtime entry name none |
| `required_plugins` | list | `[]` | packer plugins: `{name (required), version (required), source, config}` |

[`cfg/image-builders.yml`](../tests/fixtures/config/cfg/image-builders.yml):

```yaml
---
image_builders:
  - name: pckr-ebs-ans
    is_default: true
    type: packer-ebs
    runtime: default
    executable: packer
    required_plugins:
      - name: amazon
        source: github.com/hashicorp/amazon
        version: '>= 1.0.0'
      - name: ansible
        source: github.com/hashicorp/ansible
        version: '>= 1.0.0'
  - name: some-other-builder
    type: packer-ebs
    runtime: default
    executable: packer-1.9.4
    required_plugins:
      - name: amazon
        source: github.com/hashicorp/amazon
        version: '>= 1.0.0'
      - name: ansible
        source: github.com/hashicorp/ansible
        version: '>= 1.0.0'
  - name: pckr-gce-ans
    type: packer-gce
    runtime: gcloud-east1
    executable: packer
    required_plugins:
      - name: googlecompute
        source: github.com/hashicorp/googlecompute
        version: '>= 1.0.0'
      - name: ansible
        source: github.com/hashicorp/ansible
        version: '>= 1.0.0'
```

## 7. `cfg/mod-builders.yml`

Key: `mod_builders`. A modification builder turns an image's
`modifications:` items into packer provisioners. Models:
[`ansible_models.py`](../packages/ansible-plugin/src/cs_image_system/ansible_plugin/ansible_models.py),
[`bash_models.py`](../packages/bash-mod-plugin/src/cs_image_system/bash_mod_plugin/bash_models.py).

### 7.1 `ansible`

`AnsibleBuilderModel`. Each playbook becomes one `provisioner "ansible"`
(preceded by a shell step that pins a modern Python on the target).

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| common builder fields (4.1) | | | `executable` names the ansible-playbook entry |
| `playbooks` | list[str] | `[]` | playbooks run **before** every item's own, for every item of this builder; paths relative to the configuration root |
| `extra_arguments` | list[str] | `[]` | passed as the provisioner's `extra_arguments` (the system appends `-e ansible_python_interpreter=…`) |
| `ansible_connection` | str or null | null | the provisioner's `connection_type`; normally unset |
| `expect_disconnect` | bool | `false` | the provisioner's `expect_disconnect` |
| `configuration_user` | str or null | null | accepted; the provisioner's `user` comes from the runtime's bake ssh user |

### 7.2 `bash-remote`

`BashBuilderModel`. Every item becomes one `provisioner "shell"`.

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| common builder fields (4.1) | | | |
| `execute_command` | str or null | null | the provisioner's `execute_command` |
| `environment_vars` | list[str] | `[]` | the provisioner's `environment_vars` |
| `expect_disconnect` | bool | `false` | accepted |
| `extra_arguments` | list[str] | `[]` | accepted; not emitted |
| `configuration_user` | str or null | null | accepted; not emitted |

### 7.3 The modification item (inside an image's `modifications:`)

`ModItemModel`
([`moditem_type.py`](../packages/base/src/cs_image_system/base/models/moditem_type.py))
plus the builder type's fields. The item's `type` names a mod builder
(name or alias, `default`, or omitted = the default mod builder); the
builder's type decides which item model applies.

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `name` | str | required | unique within the image |
| `type` | str | `default` | the mod builder |
| `description`, `aliases`, `tags` | | | as elsewhere |
| `config` | mapping | `{}` | free-form. It is **part of the build's content hash** (a change re-bakes the image) and available to templates as `{{ this.config.x }}`; it is **not** passed to ansible or to the shell. |
| `playbooks` (ansible) | list[str] | `[]` | playbooks run after the builder's. **Required in effect**: an item with no playbooks has nothing to modify with (`config:` alone provisions nothing) and is refused at load, by name |
| `script` (bash-remote) | list[str] | `[]` | inline shell lines, run in order (no templating; literal) |
| `scripts` (bash-remote) | list[str] | `[]` | script files, relative to the root, copied beside the packer root |
| `ensure` (bash-remote) | mapping | `{}` | declarative, idempotent steps: `packages: [..]`, `files: [{path, content, mode (0644)}]`, `services: [..]` (enabled and started), `commands: [{run, unless}]` (run only when `unless` fails); any other key is refused |

A bash-remote item must give at least one of `script`, `scripts`,
`ensure`. An item with only `ensure` is recorded as `idempotent: declared`;
one with `script`/`scripts` as `idempotent: unknown`.

**An ansible item with only `config:`** loads with a warning and emits
no provisioner at all: the builder emits one provisioner per playbook the
ITEM carries, the builder's own `playbooks` are copied beside the Packer
root but never referenced, and nothing reads the item's `config`. The bake
proceeds as if the modification were not there, while the on-image bundle
still records the item (an empty `run.sh`, its `config` in the content
hash). The golden shows this for the two such items on
`imgfile-basic-dask-two`. A bash item with only `config:` refuses at load.

[`cfg/mod-builders.yml`](../tests/fixtures/config/cfg/mod-builders.yml):

```yaml
---
mod_builders:
  - name: ansible-default
    is_default: true
    type: ansible
    executable: ansible-playbook
    playbooks:
      - modify_image.yml
    config:
      key1: value1
      key2: value2
  - name: bash-remote
    aliases:
      - bash
    is_default: false
    type: bash-remote
    executable: bash
    config:
      some_unknown_mod_builder_setting: "{{ ENV.USER }} and some_value"
```

Items, from [`images/image1.yaml`](../tests/fixtures/config/images/image1.yaml):

```yaml
    modifications:
      - name: dask-setup-jeffy
        type: ansible-default
        playbooks:
          - setup_dask.yml
        config:
          dask_version: "2023.9.1AA"
          jupyterlab_extension: true
      - name: derivative-setup
        type: bash-remote
        script:
          - "echo 'derivative setup'"
          - "sudo mkdir -p /opt/derivative && echo 1.0.0 | sudo tee /opt/derivative/VERSION"
        scripts:
          - mod_image.sh
        ensure:
          packages: [git]
          files:
            - path: /etc/derivative.conf
              content: "version=1.0.0\n"
              mode: "0644"
          commands:
            - run: "sudo mkdir -p /opt/derivative/data"
              unless: "test -d /opt/derivative/data"
        config:
          derivative_version: "1.0.0"
```

## 8. `cfg/instance-builders.yml` and `cfg/storage-builders.yml`

### 8.1 Instance builders

Key: `instance_builders`. One terraform root per builder. Model:
`TofuInstanceBuilderModel`
([`tf_instance_models.py`](../packages/tf-ebs-instance-plugin/src/cs_image_system/tf_ebs_instance_plugin/tf_instance_models.py)),
types `tofu` (AWS) and `tofu-gce` (GCE, same fields,
[`tf_gcp_models.py`](../packages/tf-gcp-plugin/src/cs_image_system/tf_gcp_plugin/tf_gcp_models.py)).

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| common builder fields (4.1) | | | |
| `executable` | str or null | `tofu` | the tofu/terraform entry |
| `runtime` | str | `default` | the runtime instances stand on |
| `required_plugins` | list | `[]` | terraform providers: `{name (required), version (required), source, config}` |
| `state_configuration` | str | `default` | the state backend of this root; `default` inherits the runtime's, else the default backend |

[`cfg/instance-builders.yml`](../tests/fixtures/config/cfg/instance-builders.yml):

```yaml
---
instance_builders:
  - name: open-tofu
    type: tofu
    is_default: true
    runtime: aws-east2-runtime
    executable: open-tofu-1
    required_plugins:
      - name: aws
        source: hashicorp/aws
        version: '>= 4.0.0'
    state_configuration: s3-east2
  - name: tofu-gce
    type: tofu-gce
    runtime: gcloud-east1
    executable: open-tofu-1
    state_configuration: s3-east2
```

### 8.2 Storage builders

Key: `storage_builders`. One terraform root per builder; each realizes one
kind of storage on one runtime. Models:
[`tf_storage_models.py`](../packages/tf-ebs-instance-plugin/src/cs_image_system/tf_ebs_instance_plugin/tf_storage_models.py),
[`tf_gcp_models.py`](../packages/tf-gcp-plugin/src/cs_image_system/tf_gcp_plugin/tf_gcp_models.py).

Fields common to every storage builder (`TofuStorageBuilderModel`):

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| common builder fields (4.1) | | | |
| `executable` | str or null | `tofu` | |
| `runtime` | str | `default` | |
| `required_plugins` | list | `[]` | terraform providers, as above |
| `state_configuration` | str | `default` | |
| `variables` | mapping | `{}` | typed inputs to the module call (below); a misspelt key is refused |

Per type:

| Type | Capability token | Attachment | POSIX | Own fields | `variables` keys |
| --- | --- | --- | --- | --- | --- |
| `tf-aws-ebs` | `ebs` | single instance | yes | `size: int = 100` (GB) | `volume_type: str`, `encrypted: bool`, `tags` |
| `tf-aws-efs` | `efs` | many | yes | — | `performance_mode: str`, `encrypted: bool`, `tags` |
| `tf-aws-s3` | `s3` | many | no | `bucket_name: str` (required) | `force_destroy: bool`, `tags` |
| `tf-gcp-pd` | `pd` | single instance | yes | `size: int = 100`, `disk_type: str = pd-balanced` | `tags` (emitted as labels) |
| `tf-gcp-filestore` | `filestore` | many | yes | `tier: str = BASIC_HDD`, `capacity_gb: int = 1024` | `tags` |
| `tf-gcp-gcs` | `gcs` | many | no | `bucket_name: str` (required), `location: str or null` | `tags` |

`variables.tags` are builder-wide default tags; a storage item's own tags
win key by key. Every other variable is passed only when set, so the
module's default applies otherwise. What the builder derives from the
storage item (name, groups, lifecycle, restore snapshot, placement) always
wins over `variables`.

The capability token is what a base image lists under `storage_types`.
Attachment cardinality is enforced: two instances attaching one `ebs` or
`pd` storage is refused.

**Lifecycle declarations** (`lifecycle:` on a storage item, section 11.4)
are validated by the builder: `tf-aws-efs` accepts `ia_days` (one of 1, 7,
14, 30, 60, 90, 180, 270, 365) and `archive_days` (90, 180, 270, 365);
`tf-aws-s3` accepts `transition_days` (positive int), `storage_class` (one
of `STANDARD_IA`, `ONEZONE_IA`, `INTELLIGENT_TIERING`, `GLACIER_IR`,
`GLACIER`, `DEEP_ARCHIVE`; needs `transition_days`), `expire_days`
(positive int) and `prefix`, and needs at least one of `transition_days`
or `expire_days`. Every other builder refuses a `lifecycle`.

The requested state of a storage (`active`, `archived`, `destroyed`) is
realized by the builder: on AWS, archived EBS is a tag-named snapshot with
the volume gone, and restore recreates it from the snapshot.

[`cfg/storage-builders.yml`](../tests/fixtures/config/cfg/storage-builders.yml):

```yaml
---
storage_builders:
  - name: aws-efs
    type: tf-aws-efs
    executable: open-tofu-1
    runtime: aws-east2-runtime
    variables:
      performance_mode: generalPurpose
      encrypted: true
      tags:
        Project: MyProject
        Environment: Development
  - name: aws-ebs
    type: tf-aws-ebs
    executable: open-tofu-1
    is_default: true
    runtime: aws-east2-runtime
    size: 100
    variables:
      volume_type: gp3
      encrypted: true
      tags:
        Project: MyProject
        Environment: Development
  - name: aws-s3
    type: tf-aws-s3
    executable: open-tofu-1
    runtime: aws-east2-runtime
    bucket_name: noscsb-csis-test-514190660293-default-bucket
    variables:
      tags:
        Project: MyProject
        Environment: Development
  - name: gcp-pd
    type: tf-gcp-pd
    executable: open-tofu-1
    runtime: gcloud-east1
    size: 30
    disk_type: pd-standard
  - name: gcp-gcs
    type: tf-gcp-gcs
    executable: open-tofu-1
    runtime: gcloud-east1
    bucket_name: csis-sandbox-86233086783-default-bucket
```

## 9. `cfg/group-builders.yml`

Keys: `group_builders` and `user_builders`. Models:
[`okta_tf_models.py`](../packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/okta_tf_models.py),
[`okta_tf_workspace.py`](../packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/okta_tf_workspace.py),
[`group_builder.py`](../packages/base/src/cs_image_system/base/models/group_builder.py),
[`user_builder.py`](../packages/base/src/cs_image_system/base/models/user_builder.py).

### 9.1 The Okta terraform workspace (shared by group and user builders)

`OktaTfWorkspaceModelMixin`. Each builder owns one terraform root.

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `org` | str | required | the Okta org name; `okta` provider `org_name` |
| `team` | str | required | the OPA team; also names the credential variables (below) |
| `key` | EncryptedStr | `default` | the oktapam API key. Left at default it becomes `var.<team>_key`, filled from `TF_VAR_<team>_key`; a literal may be `ENC[age:…]` and is then emitted by reference |
| `secret` | EncryptedStr | `default` | likewise, `TF_VAR_<team>_secret` |
| `api_host` | str | `https://{{ this.org }}.pam.okta.com` | the OPA API host |
| `okta_base_url` | str | `okta.com` | `okta` provider `base_url` (`oktapreview.com` for a preview org) |
| `default_user_status` | str | `STAGED` | `okta_user.status` for enabled managed users: `ACTIVE`, `STAGED`, `SUSPENDED`, `DEPROVISIONED`; disabled users are always `SUSPENDED` |
| `required_providers` | list | `[]` | `{name (required), version (required), source, config}`; `oktapam` gets its credentials wired through variables, `okta` reads `OKTA_API_*` from the environment and its `config` may carry any provider argument |
| `state_configuration` | str | `default` | the state backend every root on this runtime inherits unless it names its own (stage 46) |

`<team>` in a variable name is the team with every non-alphanumeric
character replaced by `_` (`nos-coastal-modeling-cloud-sandbox` →
`nos_coastal_modeling_cloud_sandbox`).

### 9.2 Group builders

`OktaGroupBuilderModel`; types `okta-tf` (managed OPA groups) and
`okta-tf-ro` (lookups of existing Okta groups only). Common builder fields
(4.1) and 9.1 plus:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `gateway_selector` | str or null | null | the resource-group project's `gateway_selector`; falls back to `config.okta_gateway_selector` |
| `account_discovery` | bool | `true` | the project's `account_discovery` |

For every managed group `<g>` the `okta-tf` builder emits: the `oktapam`
groups `<g>_user` and `<g>_admin`; the resource group `<g>_rg`, delegated
to `<g>_admin` (and to the root group's admin group when the group keeps
`include_root_group_in_admins`); the project `<g>_rg_login` with the
gateway selector and account discovery; two security policies (user and
admin) that select servers by the labels `system.os_type = linux` and
`sftd.tx.group = <g>`; and one `oktapam_user_group_attachment` per member
and per admin, whose `username` is the user's `name`. Base images that
declare `identity_types: [okta]` get the OPA server agent baked, dormant;
an instance image activates it for its owning group. The identity type
token is `okta`.

The `dummy` plugin registers a `dummy` group builder and user builder
(`org`, `team`, `key`, `secret`, `api_host`) for tests.

### 9.3 User builders

`UserBuilderModel` and `OktaUserBuilderModel`; types `okta-tf` (managed:
an `okta_user` resource plus a lookup) and `okta-tf-ro` (lookup only;
`managed: true` on a user is refused). Common builder fields and 9.1 plus:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `default_user_email_template` | str | `{{ user.name }}` | the email of a user that declares none; `user` is the user being rendered |
| `default_user_description_template` | str | `User {{ user.name }} / {{ user.email }}` | the description of a user that declares none |
| `email_as_username` | bool | `true` | when true a user's `name` must equal its `email` (case-insensitive); a blank name is set from the email; a mismatch aborts the load |

The Okta login of an emitted user is its email. Lookups search
`profile.login` by that email and skip roles and groups.

### 9.4 Example

[`cfg/group-builders.yml`](../tests/fixtures/config/cfg/group-builders.yml):

```yaml
---
group_builders:
  - name: oktagroups
    is_default: true
    type: okta-tf
    executable: open-tofu-1
    org: "noaa"
    team: "nos-coastal-modeling-cloud-sandbox"
    required_providers:
      - name: oktapam
        source: okta/oktapam
        version: '>= 0.6.3'
user_builders:
  - name: okta-tf-users
    is_default: true
    type: okta-tf-ro
    executable: open-tofu-1
    org: "noaa"
    team: "nos-coastal-modeling-cloud-sandbox"
    email_as_username: false
    default_user_email_template: "{{ user.name }}@example.invalid"
    required_providers:
      - name: okta
        source: okta/okta
        version: '>= 6.0'
```

## 10. `cfg/state-backends*.yml`

Key: `state_backends`. Three types exist (stage 47): `s3`, model
`TofuS3StateBuilderModel`
([`tf_s3_state_models.py`](../packages/tf-s3-state-plugin/src/cs_image_system/tf_s3_state_plugin/tf_s3_state_models.py)),
`local`, model `LocalStateBuilderModel`
([`local_state_models.py`](../packages/local-state-plugin/src/cs_image_system/local_state_plugin/local_state_models.py)),
and `gcs`, model `GcsStateBuilderModel`
([`gcs_state_models.py`](../packages/gcs-state-plugin/src/cs_image_system/gcs_state_plugin/gcs_state_models.py)).
A type is a plugin: a model plus a *kind* that renders a root's location,
its backend file and a consumer's data source (the S3 plugin's README has
the recipe). Every terraform root names one backend through
`state_configuration`, or inherits its runtime's, or takes the default;
roots on different types read each other's state through
`terraform_remote_state` all the same. A root's state file is
`<root name>.tfstate`, the root name with non-alphanumerics replaced by
`_`, under the backend's prefix or directory.

**Where a root's state lives (stage 46).** A configured root keeps its state
in exactly one *location*, the tuple (backend type, bucket, key prefix,
state file name), and no two roots may write the same state object. The
backend a root uses resolves through a chain: the root's own
`state_configuration` when it names a backend, else its runtime's
`state_configuration` (declared on both runtime types: "everything on this
runtime keeps its state in that bucket"), else the single backend marked
`is_default`. "Names a backend" means a value outside the loader's absent
sentinels (`default`, `self`, empty, unset). The key prefix is normalised
before anything is emitted or compared -- repeated slashes collapsed,
leading and trailing ones stripped, case kept, `.` and `..` refused -- so
the doubled slash can never reach a `.tfbackend.hcl`. The operator's
examples, which are the test:

| Root | Declared location | Collides? |
| --- | --- | --- |
| A | `BUCKET1/abc` | no |
| B | `BUCKET2/xyz` | no, different bucket |
| C | `BUCKET1//xyz` | no, and normalises to `BUCKET1/xyz` |
| D | `BUCKET1/xyz` | **yes, with C** |

`validate` resolves every root's location from the declarations alone and
refuses a collision before anything is emitted: two backends whose bucket
and normalised prefix match, two root names that collapse under the state
file naming (`aws-ebs` and `aws_ebs` both become `aws_ebs.tfstate`), or a
`//` against a `/`. It also refuses a root bound twice to different
backends, a backend registered twice with different settings, and more
than one `is_default`. Every run records each root's resolved location in
`meta-state/state-locations.yaml`; a later run whose resolution differs
from the record is refused while the records show live resources in that
root (a storage not destroyed, a group or user the identity read-model
attributes to it, an instance pinned to a build), because the new location
is empty and the next plan would create everything again. A root with
nothing deployed moves freely. The escape is the operation
`run --no-dry-run … --migrate-state <root>` (OPERATIONS, "Where state
lives"); there is no flag that merely proceeds past the refusal. The
fixture binds its storage roots to `s3-east1` and everything else to the
default `s3-east2`, so its golden carries both buckets; the live
configuration keeps every root on its default backend by decision.

### `s3`

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| common builder fields (4.1) | | | `is_default` marks the backend `default` resolves to |
| `bucket` | str | required | the state bucket |
| `key` | str | required, non-empty | the key prefix; a trailing `/` is added |
| `region` | str | `us-east-2` | the bucket's region |
| `profile` | str or null | null | the AWS profile terraform uses for the backend |
| `encrypt` | bool | `false` | server-side encryption of the state objects |
| `use_lockfile` | bool | `true` | S3 lockfile locking |
| `executable` | str or null | `tofu` | |
| `required_plugins` | list | `[]` | `{name, version, source, config}` |
| `allowed_account_ids` | list[str] | `[]` | backend argument |
| `forbidden_account_ids` | list[str] | `[]` | backend argument |
| `http_proxy`, `https_proxy` | str or null | null | backend arguments |
| `no_proxy` | list[str] | `[]` | backend argument |
| `insecure` | bool | `false` | |
| `max_retries` | int | `5` | |
| `access_key`, `secret_key` | str or null | null | static keys (belong in the environment, not here) |
| `shared_config_file`, `shared_credentials_file` | str or null | null | |
| `skips_credentials_validation` | bool | `false` | (spelled with the `s`) |
| `skip_region_validation` | bool | `false` | |
| `skip_requesting_account_id` | bool | `false` | |
| `skip_metadata_api_check` | bool | `false` | |
| `skip_s3_checksum` | bool | `false` | |
| `use_dualstack_endpoint` | bool | `false` | |
| `use_fips_endpoint` | bool | `false` | |
| `endpoints` | mapping or null | null | `{dynamodb, s3, sts, iam, sso}` custom endpoints |
| `assume_role` | mapping or null | null | `{role_arn, duration, policy, policy_arns: [], session_name, source_identity, tags: {}, transitive_tag_keys: []}` |
| `assume_role_with_web_identity` | mapping or null | null | `{role_arn, duration, policy, policy_arns: [], session_name, web_identity_token, web_identity_token_file}` |

A root's location is `s3://<bucket>/<key>/<root name>.tfstate`; the backend
file carries `bucket`, `key`, `region`, `encrypt`, `use_lockfile` and the
profile; a consumer's data source `bucket`, `key`, `region` and the profile.

[`cfg/state-backends.yml`](../tests/fixtures/config/cfg/state-backends.yml)
and [`cfg/state-backends-2.yml`](../tests/fixtures/config/cfg/state-backends-2.yml):

```yaml
---
state_backends:
  - name: s3-east1
    type: s3
    encrypt: true
    bucket: my-east1-tfstate-bucket
    key: statefiles/csia/
    region: us-east-1
    profile: noaa
---
state_backends:
  - name: s3-east2
    type: s3
    encrypt: true
    is_default: true
    bucket: noaa-ioos-cloud-sandbox-tfstate
    key: statefiles/csia-image-system-test/
    region: us-east-2
    profile: noaa
```

### `local`

A state file on disk: no cloud, no credentials, so a developer or a test
can run a real `tofu init` against it. The live configuration keeps every
root on S3 by the standing decision; the fixture's identity roots use this
type, so its golden carries two backend types and reads across them.

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| common builder fields (4.1) | | | `is_default` marks the backend `default` resolves to |
| `path` | str | `state` | a directory, relative to the configuration root or absolute; non-empty |
| `executable` | str or null | `tofu` | |

A root's location is `local://<directory>/<root name>.tfstate`. The backend
file and a consumer's data source carry one setting, `path`: the absolute
directory as declared, or a relative one rewritten from the root
directory's fixed depth (`../../../../<directory>/<root name>.tfstate`,
since a root sits at `generated/<lifecycle>/<root>/<phase>/`), so the
emission names no absolute path of the machine that generated it.

[`cfg/state-backends-3.yml`](../tests/fixtures/config/cfg/state-backends-3.yml):

```yaml
---
state_backends:
  - name: local-dev
    type: local
    path: state
```

### `gcs`

A Google Cloud Storage bucket. Declared in the fixture and bound to
nothing: the GCE roots stay on the S3 backend by the standing decision,
and the live tree carries the same file with every line commented out.

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| common builder fields (4.1) | | | `is_default` marks the backend `default` resolves to |
| `bucket` | str | required, non-empty | the state bucket |
| `prefix` | str | `statefiles` | the prefix inside the bucket; each root gets `<prefix>/<root name>` beneath it |
| `credentials` | str or null | null | a PATH to a credentials file, never a value |
| `impersonate_service_account` | str or null | null | the service account terraform impersonates |
| `encryption_key` | str or null | null | a customer-supplied key |
| `kms_encryption_key` | str or null | null | a Cloud KMS key name |
| `executable` | str or null | `tofu` | |

A root's location is `gcs://<bucket>/<prefix>/<root name>/default.tfstate`
(OpenTofu's `gcs` backend names the default terraform workspace's object
`default.tfstate` under the prefix, so each root gets its own prefix). The
backend file carries `bucket`, `prefix` and the identity fields when set; a
consumer's data source `bucket`, `prefix` and the identity fields.

[`cfg/state-gcm.yml`](../tests/fixtures/config/cfg/state-gcm.yml):

```yaml
---
state_backends:
  - name: gcs-east1
    type: gcs
    bucket: csis-sandbox-tfstate
    prefix: statefiles/csia
```

## 11. The collections

Every item has the `RootItem` fields
([`root_item.py`](../packages/base/src/cs_image_system/base/models/root_item.py)):
`name` (required), `type`, `description`, `aliases`, `tags`
(mapping[str, str]) and `config` (mapping). Item names are normalized like
builder names. Templates in an item's fields see the item as `this` and
under its own kind (`{{ group.name }}`, `{{ user.name }}`,
`{{ image.name }}`), and see a resolved foreign key as the object
(`{{ image.name }}` inside an instance is the instance's image).

### 11.1 `base_images/`

Model `BaseImage`
([`base_image.py`](../packages/base/src/cs_image_system/base/models/base_image.py)):
`name`, `type` (image builder), `os` (OS builder) **or** `source_image`
(exactly one), `auto_update`, `is_default`, `primary_disk_size`,
`variables`, `tags`, `runtimes` (entries with `runtime`, `image_builder`,
`ssh_username`, `tests`, `auto_update`, `image_identifier`, `machine_type`,
`tags`, `owners`), `description`, `identity_types`, `storage_types`,
`admin_user`, `admin_public_keys`, `tests`. The collection is registered
as base-only and **the loader does not read it**. Declare base images as
OS builders (section 5). The fixture's
[`base_images/base-images1.yaml`](../tests/fixtures/config/base_images/base-images1.yaml)
is inert.

### 11.2 `images/`

Model: `Image`
([`image.py`](../packages/base/src/cs_image_system/base/models/image.py)).
An instance image: a base (or another instance image) plus modifications,
owned by exactly one group.

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `name` | str | required | the series name |
| `type` | str | `default` | the primary image builder |
| `source_image` | str | required | an OS builder name (a base image) or another image's name; the chain must end at an OS builder |
| `group` | str or null | null | the owning group; required for any image an instance uses; its builder's identity type must be one the root base declares |
| `runtimes` | list | required, at least one | one entry per image builder that bakes this image (11.2.1); one bake per runtime |
| `modifications` | list | `[]` | modification items (7.3) |
| `tests` | mapping | `{}` | in-bake and `post_bake` assertions (5.3) |
| `parent_policy` | str | `pinned` | `pinned`: bake from the pinned parent build until an explicit `upgrade image`; `follow`: a newer parent head re-bakes this image and moves the pin |
| `retention` | mapping or null | null | `{keep: N}`: the newest N builds per runtime survive the closing `retention` lifecycle; null uses the runtime's `retention_keep` |
| `release` | mapping or null | null | `{model: <name>}`: a build whose post-bake tests pass in a run is released for that model by the same run's `release` lifecycle |
| `is_default` | bool | `false` | |
| `architecture` | str | the OS builder's, else `x86_64` | |
| `primary_disk_size` | str or int | the OS builder's `default_primary_disk_size`, else 200 | GB |
| `variables` | mapping | `{}` | emitted as packer variables (`name = value` lines) |
| `tags` | mapping[str, str] | `{}` | tags on the baked image |
| `description` | str or null | `Image <name> from source image <source_image>` | |
| `auto_update` | bool or null | null | accepted; updates apply to base images only |
| `auto_generate_storage` | bool | `false` | accepted; not read |
| `default_groups` | list[str] | `[]` | accepted; not read |
| `aliases`, `config` | | | as elsewhere |

#### 11.2.1 `runtimes[]` entries

`ImageImageBuilderSubconfig`.

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `image_builder` | str | `default` | the image builder; its runtime is the runtime of this bake |
| `machine_type` | str or null | null | the bake machine type; null uses the runtime's default |
| `ssh_username` | str | `default` | the bake ssh user on this runtime |
| `image_identifier` | str or null | null | a fixed provider image id to bake from instead of the pinned parent |
| `owners` | list[str] | `[self]` | owners for the parent-image query |
| `tags` | mapping[str, str] | `{}` | merged over the builder's and the image's |
| `name` | str | the image builder | label |
| `type` | str | the image builder | set by the loader |
| `description`, `aliases` | | | accepted |

[`images/image1.yaml`](../tests/fixtures/config/images/image1.yaml)
(the `imgfile-basic-dask` entry; its modifications are shown in 7.3):

```yaml
images:
  - name: imgfile-basic-dask
    group: coops
    runtimes:
      - image_builder: pckr-ebs-ans
      - image_builder: pckr-gce-ans
        machine_type: e2-medium
    tags:
      dask: "true"
    type: pckr-ebs-ans
    source_image: basic-rh-10
    parent_policy: follow
    description: "Basic Dask head node with essential tools and configurations."
    tests:
      commands:
        - run: "git --version"
          contains: "git version"
      packages: [git]
      users: [csisadmin]
      post_bake:
        commands:
          - run: "python3 -c 'import dask'"
        files:
          - path: /var/lib/csis/launch-applied
        mounts: [/mnt/gce-data]
    release:
      model: default
    modifications:
      - ...
```

### 11.3 `instances/`

Model: `Instance`
([`instance.py`](../packages/base/src/cs_image_system/base/models/instance.py)).

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `name` | str | required | |
| `image` | str | required for generation | an instance image; its `group` is the instance's group |
| `type` | str | `default` | the instance builder (the terraform root) |
| `runtime` | str | `default` | the runtime |
| `machine_type` | str | `""` | the instance size; empty uses the runtime's default |
| `storages` | list | `[]` | attachments (11.3.1); a name attached twice keeps the later mapping |
| `ephemeral` | bool | `false` | launched, verified through the runtime and destroyed in the same run; a failed verification leaves it standing and fails the run |
| `on_failure` | str or null | null | `keep` (default: left standing, the run fails) or `teardown` (torn down, the run still fails); null inherits the runtime's |
| `teardown_after` | str or null | null | `<number>` followed by `m`, `h` or `d`: after a failed verification, the next run tears the standing instance down once this has elapsed; null inherits |
| `image_policy` | str | `pinned` | `pinned`: keep the launched build until an explicit `upgrade instance`; `follow`: plan the gated replacement whenever the image's head moves |
| `description` | str or null | `Instance from {{ image.name }}` | |
| `userdata` | str | `""` | accepted; not read by the tofu roots |
| `tags` | mapping[str, str] | `{}` | |
| `aliases`, `config` | | | as elsewhere |
| `groups` | — | — | **refused**: the owning group lives on the image |

An instance's pinned build must be a released build when
`config.require_released_builds` is true.

#### 11.3.1 `storages[]` entries

`StorageMapping`.

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `name` | str | required | a declared storage (11.4); the image's group must be on its `groups` list, or the storage `public_read` |
| `mount_point` | str | `/mnt/storage` | where the instance mounts it (recorded in launch params; the unmount step uses it) |
| `min_size` | int | `100` | must be positive; not consumed by the tofu roots |
| `type` | str | `default` | set to the storage's builder at generation |
| `description`, `tags`, `config` | | | accepted |
| `aliases` | | | ignored with a warning |

[`instances/instances.yaml`](../tests/fixtures/config/instances/instances.yaml):

```yaml
---
instances:
  - name: test
    machine_type: t3.medium
    image: imgfile-basic-cloudflow
    description: Test deploy of CSB Base Image RHEL 8.8 - Snapshot
    tags:
      stype: test
  - name: test2
    machine_type: t3.medium
    image: imgfile-basic-dask
    description: Test deploy of CSB Base Image AlmaLinux 9 - Snapshot
    tags:
      hype: test
    storages:
      - name: mnt_data
        mount_point: /mnt/data
  - name: gce-test
    image: imgfile-basic-dask
    runtime: gcloud-east1
    type: tofu-gce
    description: First GCE instance (GCP readiness); free-tier e2-micro
    storages:
      - name: gce_data
        mount_point: /mnt/gce-data
```

### 11.4 `storages/`

Model: `Storage`
([`storage.py`](../packages/base/src/cs_image_system/base/models/storage.py)).
A storage is realized by its builder's root; the YAML declares the
**requested** state, `meta-state/storage-state.yaml` holds the current one.

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `name` | str | required | system-wide unique |
| `type` | str | `default` | the storage builder (8.2); fixes the capability type and the runtime |
| `runtime` | str | `default` | accepted; the builder's runtime governs |
| `groups` | list[str] | `[]` | the groups allowed to attach (never users; each must be a declared group); each gets a private `/<group>/` subtree. The value `ALL` is refused. |
| `public_read` | bool | `false` | anyone may mount read-only; POSIX permissions still govern |
| `share_mode` | str | `2770` | mode of every allowed group's subtree: `2770` (private) or `2775` (read-shared between allowed groups) |
| `state` | str | `active` | requested lifecycle state: `active`, `archived`, `destroyed` (a permanent tombstone; the entry stays, the name is retired). Transitions are checked by the state machine; a `destroyed` transition needs no attachments. |
| `lifecycle` | mapping or null | null | the data lifecycle the builder realizes (8.2): EFS `{ia_days, archive_days}`; S3 `{transition_days, storage_class, expire_days, prefix}` |
| `bucket_name` | str or null | null | S3 / GCS: the bucket; null uses the storage name |
| `mount_point` | str or null | null | accepted; the attachment's `mount_point` on the instance is what a launch uses |
| `is_default` | bool | `false` | |
| `config` | mapping | `{}` | EFS: `file_system_id` adopts an existing filesystem |
| `tags` | mapping[str, str] | `{}` | merged over the builder's default tags |
| `singleton` | bool | `false` | accepted |
| `ephemeral` | bool | `false` | accepted; not read |
| `generative` | bool | `false` | accepted; not read |
| `source` | mapping[str, str] | `{}` | accepted; not read |
| `description`, `aliases` | | | as elsewhere |

[`storages/storage0.yaml`](../tests/fixtures/config/storages/storage0.yaml)
and [`storages/gce.yaml`](../tests/fixtures/config/storages/gce.yaml):

```yaml
storages:
  - name: mnt_data
    mount_point: /mnt/data
    is_default: true
    groups:
      - coops
    state: active
  - name: default-bucket
    is_default: false
    runtime: default
    type: aws-s3
    singleton: true
    bucket_name: noscsb-csis-test-514190660293-default-bucket
    public_read: true
    lifecycle:
      transition_days: 30
      storage_class: STANDARD_IA
    tags:
      env: production
      team: devops
  - name: efs-storage
    type: aws-efs
    groups:
      - coops
      - stofs
    share_mode: "2775"
    lifecycle:
      ia_days: 30
---
storages:
- name: gce_data
  type: gcp-pd
  mount_point: /mnt/gce-data
  groups:
  - coops
  state: active
- name: gce_bucket
  type: gcp-gcs
  bucket_name: csis-sandbox-86233086783-default-bucket
```

### 11.5 `groups/` — groups

Model: `Group`
([`group.py`](../packages/base/src/cs_image_system/base/models/group.py)).
Key `groups:`. Exactly one group in the whole tree must be `is_root:
true`; every member must be a declared user name.

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `name` | str | required | system-wide unique; the OPA group names derive from it |
| `type` | str | `default` | the group builder |
| `is_root` | bool | `false` | the single root/admin group; its admin group is a delegated admin of every resource group |
| `is_default` | bool | `false` | |
| `members` | set[EncryptedStr] | `{}` | user names; each entry may be `ENC[age:…]` |
| `admins` | set[EncryptedStr] | `{}` | user names; likewise |
| `in_both` | bool or null | null | `true`: every admin is also a member; `false`: no name may be in both (admins are removed from members and members from admins); null: as declared |
| `gid` | int, digit string, `default`, 0 or null | null | a pinned gid, at least 1024; null/0/`default` defer to the created group's gid |
| `include_root_group_in_admins` | bool | `true` | the root group's admin group is added to this group's delegated admins |
| `unmanaged` | bool | `false` | the group stays in the YAML but leaves management: its state entries are removed, nothing is destroyed. A group once managed may not simply disappear from the YAML. |
| `attributes` | mapping or null | null | provider attributes: OPA accepts `unix_gid` (int), `unix_group_name` (str), `windows_group_name` (str); planned and probed, never written |
| `description` | str or null | null | templates allowed (`{{ group.name }}`) |
| `tags`, `config`, `aliases` | | | as elsewhere |

[`groups/test-group.yaml`](../tests/fixtures/config/groups/test-group.yaml)
(entries encrypted to the fixture's test identity; markers shortened):

```yaml
groups:
  - name: basic
    is_root: true
    is_default: false
    description: "Root admin group with access to everything"
    admins:
      - ENC[age:YWdlLWVuY3J5cHRpb24ub3JnL3YxCi0+IFgyNTUxOSAvNFdjbVB6VExmbnZNQjFRR1dMel…]
    tags:
      environment: production
  - name: coops
    is_default: false
    description: "CO-Ops  group"
    members:
      - ENC[age:…]
      - ENC[age:…]
    admins:
      - ENC[age:…]
      - ENC[age:…]
    tags:
      environment: test
```

### 11.6 `groups/` — users

Model: `User`
([`user.py`](../packages/base/src/cs_image_system/base/models/user.py)).
Key `users:` (any file under `groups/`).

| Field | Type | Default | Meaning and allowed values |
| --- | --- | --- | --- |
| `name` | EncryptedStr | required | the username: the bare OPA username that group `members`/`admins` list and attachments use |
| `first_name` | EncryptedStr | required, non-blank | never derived from `name` |
| `last_name` | EncryptedStr | required, non-blank | never derived from `name` |
| `email` | EncryptedStr | the builder's `default_user_email_template` | the Okta login and lookup key; explicit, or derived from the template (`<name>@example.invalid` in the fixture) |
| `type` | str | `default` | the user builder |
| `description` | str or null | the builder's description template | |
| `middle_name` | str or null | null | emitted when set |
| `is_enabled` | bool | `true` | `false` emits status `SUSPENDED` |
| `managed` | bool or null | null | null: the builder's default (`okta-tf`: managed, `okta-tf-ro`: lookup only). A managed user is emitted as a resource; an unmanaged one only as a lookup. `okta-tf-ro` refuses `true`. |
| `attributes` | mapping or null | null | OPA accepts `unix_uid` (int), `unix_gid` (int), `unix_user_name` (str), `windows_user_name` (str) |
| `is_service_account` | bool | `false` | accepted; not emitted |
| `public_keys` | list[str] | `[]` | accepted; not emitted |
| `mobile_phone`, `honorific_prefix`, `honorific_suffix`, `title`, `display_name`, `nick_name`, `profile_url`, `second_email`, `primary_phone`, `street_address`, `city`, `state`, `zip_code`, `country_code`, `postal_address`, `preferred_language`, `locale`, `timezone`, `user_type`, `employee_number`, `cost_center`, `organization`, `division`, `department`, `manager_id`, `manager` | str or null | null | `okta_user` profile arguments, emitted when set |
| `tags`, `config` | | | accepted |
| `aliases` | | | **refused** |

[`groups/users.yaml`](../tests/fixtures/config/groups/users.yaml) holds
nineteen personas (`avery.alpha` … `sawyer`), every identifying field
encrypted; some carry an explicit `email` on an example domain, the rest
derive theirs. In clear, an entry has this shape (the second entry is
illustrative):

```yaml
users:
  - name: avery.alpha
    first_name: Avery
    last_name: Alpha
    # email derived: avery.alpha@example.invalid
  - name: some.persona
    first_name: Some
    last_name: Persona
    email: some.persona@example.org   # explicit: used for the org lookup
```

and in the file:

```yaml
users:
  - name: ENC[age:YWdlLWVuY3J5cHRpb24ub3JnL3YxCi0+IFgyNTUxOSBBeXNlTmFDeXN1NUxKNll2UTdNNlgxMVdWbFdHTjZJM3FiYStRN0tBeHhnCitDRHZHUWcvWjhhaUU1RWhDczZaUjRIcXdZUlJ4dkFTV0FkVXRKdDlCencKLS0tIEs2K2RrTmdtWTBEZ01kaGthVHVabWhVVDNieWtVK05YRHVKS3BuZTY3dXMKL6SV9wExndvLOcCh6sUtuTlSJXf8sKaELjPkg2bk9q8JPpVuBsbLJnAE9A==]
    first_name: ENC[age:…]
    last_name: ENC[age:…]
```

## 12. Overlays

An overlay is a YAML file merged over the tree for **one invocation**; the
tree on disk never changes. Named with the global `--overlay <file>`
option (repeatable, before the command). A missing overlay is a refusal.

Shape ([`load_overlay`](../packages/base/src/cs_image_system/base/global_context.py)):
a mapping whose keys are `config` and/or a collection key — `users`,
`groups`, `storages`, `images`, `instances`, `base_images`. Any other key
is refused. `config` must be a mapping; a collection must be a list of
mappings with a `name`.

- `config:` keys **override** `cfg/_config.yml`'s `config:` for the
  invocation (typically an `apply_*` list).
- A collection entry whose name **exists** in the tree is updated key by
  key (`state: destroyed` on a declared storage).
- An entry whose name is **new** is added; it is transient — declared by
  the overlay, not by the tree.
- `undeclare: true` on an entry **removes** the tree's declaration for the
  invocation: the instance decommissions, the storage is destroyed,
  exactly as if its entry had left the YAML.

The generated runner scripts carry the overlays they were generated under
and `apply-check` re-reads their `config:` at execution, so a script
generated under an overlay applies only under that overlay.

`--undeclare <kind>:<name>` (repeatable) is the `undeclare` form as a
flag, needing no file: `--undeclare instance:gce-test`,
`--undeclare storage:gce_data`. The kind is a collection key or its
singular.

[`overlays/gce-cycle-launch.yaml`](../tests/fixtures/config/overlays/gce-cycle-launch.yaml):

```yaml
config:
  apply_instances: [gcloud-east1]
instances:
  - name: gce-test
    image: imgfile-basic-dask
    runtime: gcloud-east1
    type: tofu-gce
    description: "GCE change-cycle instance (free-tier e2-micro); exists only for the cycle"
    storages:
      - name: gce_data
        mount_point: /mnt/gce-data
```

[`overlays/gce-cycle-decommission.yaml`](../tests/fixtures/config/overlays/gce-cycle-decommission.yaml):

```yaml
config:
  apply_instances: [gcloud-east1]
instances:
  - name: gce-test
    undeclare: true
```

[`overlays/gce-cycle-storage-teardown.yaml`](../tests/fixtures/config/overlays/gce-cycle-storage-teardown.yaml):

```yaml
config:
  apply_storage: [gcloud-east1]
storages:
  - name: gce_data
    state: destroyed
  - name: gce_bucket
    state: destroyed
```

### 12.1 Run scoping options

Options of `cs-image-system run` ([`cli.py`](../packages/system/src/cs_image_system/system/cli.py)):

| Option | Effect |
| --- | --- |
| `--only <image>[@<runtime>]` (repeatable) | restrict the **bake** surface to the named images (an OS builder or an image name; with `@<runtime>`, on that runtime only). Terraform roots are untouched. An unknown name fails. `--only none` bakes nothing. |
| `--only-runtime <rt>` | `--only <img>@<rt>` for every image baked on that runtime; the terraform roots of other runtimes emit nothing |
| `--apply-runtime <rt>` | sets `apply_storage` and `apply_instances` to `[<rt>]` for the run (the generated `apply-check` carries it) **and** implies `--only-runtime <rt>` unless `--only`/`--only-runtime` is given |
| `--allow-unscoped-bakes` | let a `--no-dry-run` run bake on runtimes outside its apply scope (a list-valued `apply_*` flag or `--apply-runtime`); without it such a run refuses |
| `--force-bake <image>` (repeatable; `all`) | bake even when current; otherwise an image bakes only when its inputs changed, its parent moved under `parent_policy: follow`, or `update.refresh_days` is due |
| `--apply/--no-apply`, `--commit/--no-commit`, `--state-query/--no-state-query` | execute the runner scripts; commit meta-state; ask reality first |

Global options (before the command): `--root-dir`, `--verbose`,
`--dry-run/--no-dry-run` (dry run is the default: finalization commands
are enumerated, not executed), `--overlay`, `--undeclare`, `--force`,
`--base-only`, `--only-providers` (accepted; the configuration is still
read in full).

## 12a. Availability zones

A subnet, a storage and an instance may each declare `availability_zone`. It is
declared, never inferred: an absent value constrains nothing.

`validate` refuses a set that is not **compatible** — more than one distinct
zone across an instance, the zonal storages it mounts, and its runtime's
effective subnet — naming each claimant and the zone it asked for. Compatible
rather than identical, because two things impose no constraint at all: an unset
value, and a **regional** storage. EBS and GCP persistent disks are zonal; EFS,
S3 and GCS are regional and are reachable from any zone in their region.

A runtime asserts a zone through `networking.default_availability_zone`, else
through its default subnet's declared `availability_zone`. A storage's own
declaration wins over its runtime's when the module call is emitted, so
declaring a zone pins the resource rather than decorating the file.

**Why it is refused early.** A zone is a replace-forcing attribute. Pointing a
runtime at a subnet in another zone does not fail to attach a volume — it plans
to destroy and recreate it, losing the data. The plan gate does refuse that as
an unwhitelisted destroy, but it names the volume rather than the cause, and it
does so at apply time.

## 13. Encrypted values

([`encryption.py`](../packages/base/src/cs_image_system/base/encryption.py))

A value may be the marker `ENC[age:<base64 of an age-encryption.org/v1
file>]`, encrypted to every key in `encryption.recipients`. **Any value
anywhere decrypts at load** (stage 49): no field has to be declared for it,
and each element of a list or set is encrypted on its own, so a roster is
encrypted entry by entry. A marked value with no identity in the environment
is a load-time refusal naming the value's path; a decrypted value prints as
`Decrypted('***')` in any dump or error.

Three places a marker may NOT stand, each refused at load by name:

| Refused | Why |
| --- | --- |
| a mapping **key** | keys dedupe list entries, dispatch the concrete class and name generated directories, so they must be readable with no identity |
| a marker **embedded** in a longer string | only a whole value decrypts: a composite carries no single ciphertext, so the emission could only write it in clear |
| `encryption.recipients`, `public_safe.allow`, a runtime builder's `name`/`type`/`profile`/`credentials.profile_name`, `config.preflight.*`, `config.apply_*`, and any declaration's `name`/`type` | these are read by the raw readers that run *before* the configuration loads, several of which must work with no identity at all (encrypting must not need one) |

`EncryptedStr` remains on the roster fields: it is the one annotation under
which pydantic keeps the decrypted value's identity without help.

**The identity** comes from `CSIS_CONFIG_IDENTITY`: the
`AGE-SECRET-KEY-1…` string itself, the path of an identity file in the
age-keygen layout, or a directory of `*.age-identity` files (each tried
until one opens the value). The fixture's `.age-identity` is the test
identity; the suite exports it.

**Commands** (none loads the tree; `encrypt` needs no identity):

| Command | Does |
| --- | --- |
| `cs-image-system encrypt <value>` (or `-` for stdin) | prints one marker encrypted to the recipients |
| `cs-image-system encrypt --file <yaml> --field <name> …` | encrypts, in place and textually, every scalar value of a key named `<name>` and every element of a block list under it; comments and every other byte are preserved; values already marked, templated (`{{`), empty or nested are left alone |
| `cs-image-system decrypt <marker>` | prints the plaintext (for the operator) |
| `cs-image-system decrypt --json` | the terraform `external` data source protocol: a JSON object of markers on stdin, decrypted on stdout; generated roots run it at plan time |
| `cs-image-system decrypt --file <yaml> --field <name> …` | the inverse of `encrypt --file`: writes those fields' markers back in clear, in place, comments preserved |
| `cs-image-system reencrypt [--dry-run]` | rotates every marker under the root to the current recipients; nothing is written unless every value opens |
| `cs-image-system materialize <dir> [dest]` | copies a generated root into the private mirror with every marker replaced by its plaintext, and prints where; what every deferred command runs through |
| `cs-image-system public-safe [--staged] [--tree] [--config]` | refuses material that must not be public; `public_safe.allow` lists the exceptions |

`bin/gen_age.sh`, `bin/crypt_age.sh` and `bin/rotate_age.sh` produce the
same marker with the `age` CLI.

**Emission and execution.** A decrypted value is emitted as the ciphertext
it was read from — the committed artifact says `ENC[age:…]` wherever the
configuration does, in packer and terraform alike. Before a deferred command
runs, its root is copied to `_private/<the same relative path>` under the
configuration root with every marker replaced by its plaintext, and the
command runs there; the mirror is never committed (refused by path, named in
the emitted `.gitignore`, skipped by the scanner), and only the provider lock
file is ever copied back out of it. Age is randomised, so the SOURCE marker is
reused rather than re-encrypted: re-encrypting would move every emitted byte
on every run. Terraform's older by-reference path — `local.sensitive["<key>"]`
filled by a `data "external"` block running `cs-image-system decrypt --json`
at plan time — still stands for the okta roots.

The guard is not a guess: the system knows every plaintext it opened, and
`validate` and every commit refuse if one of them stands in clear under
`generated/` or `meta-state/`, naming the file and line.

**A derived value inherits its inputs' encryption** (stage 51). A value
computed from a decrypted one — an address from `default_user_email_template` —
is declared nowhere and so has no ciphertext of its own; one is built from the
pieces, so the emission carries `blake.bravo@ENC[age:…]` and `materialize` puts
the address back together where the tools run. That is why the address domain
is its own declared value: put `email_domain` on the user builder and write the
template as `"{{ user.name }}@{{ builder.email_domain }}"`, encrypt the domain,
and one marker serves every user. A username stays public by decision, so a
value read only under `name`, `members` or `admins` is emitted in clear —
it is the join key between a roster and an access grant.

## 14. Environment variables

| Variable | Read by | Meaning |
| --- | --- | --- |
| `CSIS_CONFIG_ROOT` | the Justfile | the live configuration root the `cloud-*`/`gce-*` recipes drive (default: the sibling `cs-image-system-testconfig` checkout); the CLI itself takes `--root-dir` |
| `CSIS_CONFIG_IDENTITY` | every load; `decrypt`; `reencrypt` | the age identity (section 13) |
| AWS profile | the AWS runtime, the S3 backend, preflight | `credentials.profile_name` on the runtime (else `AWS_PROFILE`; static `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` are honoured when no profile is named); `profile` on the state backend. An SSO profile needs a live session: the load validates the account's network and refuses on an expired one. |
| `GOOGLE_APPLICATION_CREDENTIALS` | the GCE runtime, preflight | Application Default Credentials; default `~/.config/gcloud/application_default_credentials.json` |
| `TF_VAR_<team>_key`, `TF_VAR_<team>_secret` | an `okta-tf` builder with the `oktapam` provider; the gid shim; the state query | the OPA API key pair for the builder's `team` (non-alphanumerics of the team → `_`). Required at finalize when the builder's `key`/`secret` are left at default. The gid shim also accepts `OKTAPAM_KEY`/`OKTAPAM_SECRET`. |
| `OKTA_API_CLIENT_ID`, `OKTA_API_SCOPES`, `OKTA_API_PRIVATE_KEY`, `OKTA_API_PRIVATE_KEY_ID` (or `OKTA_API_TOKEN`) | the `okta/okta` provider at plan/apply | user (and read-only group) lookups. The load only checks that one of `OKTA_API_PRIVATE_KEY`, `OKTA_API_TOKEN`, `OKTA_ACCESS_TOKEN` is set and warns otherwise, skipping `plan` for that root. |
| `TF_VAR_sft_enrollment_token` | the instance roots | explicit override of the enrollment token the identity root mints |
| `CSIS_AWS_DIR` | preflight | the `~/.aws` directory to read session caches from |
| `{{ ENV.<name> }}` | the templating pass | any variable, in any string of `cfg/` (`systemuser: "{{ ENV.USER }}"`, `'{{ ENV["USER"] }}''s node'`) |

`cs-image-system preflight [--strict]` reports the AWS SSO and GCP ADC
sessions the runtimes need without loading the tree; `run` and `state`
perform the same check before loading.
