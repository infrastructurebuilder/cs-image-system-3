# cs-image-system-gcloud-runtime-plugin

The `gcloud` runtime type. A runtime is where images are baked and instances
run; this package makes Google Compute Engine (GCE) one. It registers one
runtime model (`GCPCloudBuilderModel`), one runtime builder
(`GCPCloudBuilder`) and one version checker for the `gcloud` executable. At
load it lists the project's networks, subnetworks, routes and firewall rules
with the Compute API and checks the declared networking against them. During
a run it resolves vendor images by project and filter (or by image family),
emits the `googlecompute` packer source for every image baked here, bakes
and reaches instances through Identity-Aware Proxy (IAP) TCP forwarding,
answers the state query from the Compute API, relabels released images, and
deletes images by name. Credentials are Application Default Credentials;
the model declares none.

## What it registers

The entry point is declared in [pyproject.toml](pyproject.toml):

```toml
[project.entry-points."cs_image_system.plugins.runtime"]
gcloud = "cs_image_system.gcloud_runtime.main:initialize"
```

`initialize()` in [main.py](src/cs_image_system/gcloud_runtime/main.py)
returns a `GcpRuntimePluginMetadata` whose services map the key `gcloud` to
three classes and whose `builders_for_models` binds the model to its builder.

| Class | `csis_name()` | `csis_classifier()` | Registered under |
|---|---|---|---|
| `GCPCloudBuilderModel` ([gcp_runtime_models.py](src/cs_image_system/gcloud_runtime/gcp_runtime_models.py)) | `gcloud` | `VCT.CLOUD_BUILDER_MODEL` | `cloud_builder_model` and, because the loader re-registers cloud models as runtimes, `runtime_builder_model` |
| `GCPCloudBuilder` ([gcp_runtime_builders.py](src/cs_image_system/gcloud_runtime/gcp_runtime_builders.py)) | `gcloud` | `VCT.RUNTIME_BUILDER` | `runtime_builder` |
| `GCPCLIVersionChecker` ([gcp_runtime_builders.py](src/cs_image_system/gcloud_runtime/gcp_runtime_builders.py)) | `gcloud` | `VCT.VERSION_CHECKER` | `version_checker` |

A YAML entry selects the runtime with `type: gcloud` under
`runtime_builders:`. There are no type aliases; `gcloud` is the only type
key. An entry's own `aliases:` list gives that runtime extra names (the
fixture's `gcloud-east1` also answers to `gcp`, `google` and `us-east1`).

The version checker is looked up by an executable's `type`, which defaults
to its `name`, so the fixture's `- name: gcloud` executable in
[executables.yml](../../tests/fixtures/config/cfg/executables.yml) is parsed
by it: the checker takes the `core` line of `gcloud --version` and reads its
second token.

Present in the package but not registered as a service:

- `GcpProviderSpecificImage` ([gcp_provider_specific_image.py](src/cs_image_system/gcloud_runtime/gcp_provider_specific_image.py)), reached through the builder's `provider_specific_image_class()` hook.
- `DummyGroupBuilderModel` and `DummyUserBuilderModel`, unregistered copies of the [dummy plugin](../dummy-plugin/README.md)'s models; the models module imports `DUMMY` from that package.
- The constant `GCP_CLI = "gcloud-cli"`, which nothing uses.

## Models

### `GCPCloudNetworkingModel`

Extends `CloudNetworkingConfig` in
[cloud_builder.py](../base/src/cs_image_system/base/models/cloud_builder.py),
which is `RuntimeNetworkingModel` in
[runtime.py](../base/src/cs_image_system/base/models/runtime.py) under
another name.

Fields it adds:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `network_tags` | `list[str]` | `[]` | GCE network tags. Firewall rules apply by target tag, so these are the closest analog to AWS security group ids. Emitted as the packer source's `tags` and the instance module's `network_tags`. A tag no firewall rule targets logs a warning at load. |
| `_model_id` | `str \| None` | `None` (not an init field) | Back-reference to the owning runtime model. |

Base fields it inherits:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | `str` | the network name | Empty or `default` falls back to `network`. |
| `network` | `str` | `default` | The VPC network name. `default` resolves at load to the network literally named `default` (GCE has no default flag). |
| `subnets` | `list[RuntimeSubnetModel]` | required, non-empty | `name`, `subnet_id`, `is_default`, `public`, `cidr`, `config`. `subnet_id` is a subnetwork name, a full self link, or a `projects/<p>/regions/<r>/subnetworks/<n>` path. The first entry with `is_default: true` is the default subnet. |
| `availability_zones` | `list[RuntimeAvailabilityZoneModel]` | `[]` | Declared; the GCE emitters use the runtime's `zone` instead. |

It constrains `name` to be non-empty after stripping. `get_subnet_id()`
raises when no default subnet exists. There is no security group concept
here: `security_group_ids` and the like are not fields and are rejected.

### `GCPCloudBuilderModel`

Extends `CloudBuilderModel` in
[cloud_builder.py](../base/src/cs_image_system/base/models/cloud_builder.py),
which extends `RuntimeBuilderModel` in
[runtime.py](../base/src/cs_image_system/base/models/runtime.py), which
extends `BuilderModel` and `NameTyped` in
[builder_model.py](../base/src/cs_image_system/base/models/builder_model.py).

Fields it adds:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `project_id` | `str \| None` | `None` | The GCP project. `self` in an owner list resolves to it; without it network discovery is skipped with a warning and image resolution and bakes fail. Reported by `runtime describe`. |
| `zone` | `str \| None` | `None` | The zone build VMs and instances run in; the packer `zone`, the `google` provider's `zone`, and the scope of `inventory()`, `serial_console()` and the boot-image probe. |
| `service_account_email` | `str \| None` | `None` | The service account attached to build VMs (`service_account_email` in the packer source). Without it packer attaches the project's default compute service account. |
| `default_disk_size` | `int \| None` | `None` | Boot disk size in GB for every image baked on this runtime; wins over the image's `primary_disk_size`. A GCE instance's boot disk is exactly its image's disk. |
| `bake_preemptible` | `bool` | `False` | Bake on a preemptible (spot) VM; a preempted bake re-runs. |
| `state_configuration` | `str` | `DEFAULT` | Foreign key to a state backend. Declared on the runtime; the terraform roots take their backend from their own builders' field of the same name. |
| `ssh_username` | `str` | `DEFAULT` | When set, the bake's SSH user for every image baked here. |
| `session_mechanism` | `str \| None` | `None` | `iap` is the only value. Any other string is an error. |
| `networking` | `GCPCloudNetworkingModel \| None` | `None` | Narrows the base type and makes it optional. Missing networking logs a warning at load. |
| `network_map` | `dict` | discovered | Not an init field. `{network: {"subnets": [...]}}` from the project. |
| `default_network` | `str \| None` | discovered | Not an init field. `default` when a network of that name exists. |
| `all_firewall_rules` | `dict[str, dict]` | discovered | Not an init field. `{rule_name: rule}` from the project. |

Base fields it inherits, and what this runtime does with them:

| Field | From | Default | Meaning here |
|---|---|---|---|
| `name`, `type`, `description`, `aliases` | `NameTyped` | `name`/`type` required | `type` is `gcloud`. |
| `executable`, `is_default`, `config`, `gitignore`, `tags` | `BuilderModel` | | `tags` merge into every image's labels after `gce_label()` sanitising. |
| `region` | `CloudBuilderModel` | required | The `google` provider's `region`; the client config's `region`. |
| `credentials` | `RuntimeBuilderModel` | `CredentialsBase()` | Not narrowed. The base declares no fields and forbids extra keys, so `credentials:` accepts nothing; clients use Application Default Credentials. |
| `default_machine_type` | `RuntimeBuilderModel` | required | Machine type when neither an OS-builder runtime entry nor an image names one. |
| `default_image_builder` | `RuntimeBuilderModel` | `DEFAULT` | The image builder an OS-builder runtime entry with `image_builder: default` resolves to. |
| `default_owners` | `RuntimeBuilderModel` | `None` | Appended to every vendor-image query's owner list, then mapped to projects. |
| `default_config_username` | `RuntimeBuilderModel` | `None` | Fallback SSH user for OS-builder runtime entries that declare none. |
| `ephemeral` | `RuntimeBuilderModel` | `False` | See "Retention and the GCE cycle". The fixture's `gcloud-east1` is ephemeral. |
| `retention_keep` | `RuntimeBuilderModel` | `None` | Builds kept per series when the image declares no retention. |
| `on_failure`, `teardown_after` | `RuntimeBuilderModel` | `None` | Runtime-level defaults for ephemeral instances. |

It overrides `finalize()` to run `update_networking()` after the base
finalization, and `csis_name()` to return `gcloud`. It carries the class
attribute `type = "gcloud"`.

Not supported: any key inside `credentials:` (including a service-account
key file; `gcp_utils` can read `service_account_key_file` from a session
config, but no model field carries it, so that path is unreachable from
YAML), session mechanisms other than `iap`, and `availability_zones` as a
zone selector (use `zone`).

## The builder

`GCPCloudBuilder` extends `CloudBuilderBase` in
[builder_base_cloud.py](../base/src/cs_image_system/base/basic/builder_base_cloud.py),
an empty specialisation of `RuntimeBuilderBase` in
[builder_base_runtime.py](../base/src/cs_image_system/base/basic/builder_base_runtime.py).
The runtime builder writes no files of its own: `generate_items_during`
defers to the base and returns nothing. Everything it contributes reaches
`generated/` through the image, instance and release builders that call its
hooks. In the order a run reaches them:

| When | Hook | What it does |
|---|---|---|
| Configuration load | `GCPCloudBuilderModel.finalize()` | Runs `update_networking()` (network discovery below). |
| Resolution | `provider_specific_image_class()` | Returns `GcpProviderSpecificImage`. |
| Resolution | `query_provider_image(subconfig)` | Finds the vendor image for one OS-builder runtime entry (image query below). Returns `(image_name, owning_project, raw_result)` or `None`. |
| Image generation | `packer_source_type()` | `googlecompute`. |
| Image generation | `packer_source_blocks(...)` | The `source "googlecompute"` block for one image. |
| Image generation | `session_mechanism()` | `iap` or `None`. |
| Image generation | `session_agent_commands(os_family)` | Installs `google-guest-agent` when missing (`apt-get` for `debian`/`ubuntu`, `yum` otherwise) and enables it together with `sshd`/`ssh`. |
| Image generation | `session_verify_commands(os_family)` | Assertions that the guest agent is present and enabled. |
| Image generation | `bake_ssh_username()` | The model's `ssh_username` when set, else `packer`; the ansible provisioner names this user. |
| Image generation | `bake_finalize_commands(os_family)` | The last provisioner of every bake here: adds the build user to `google-sudoers` when that group exists, so the guest agent's first-boot user cleanup succeeds and metadata SSH keys get provisioned. |
| After a bake | `build_id_from_artifact(artifact_id)` | The packer manifest's `artifact_id` is the image name itself; returned unchanged. |
| Instance verification | `serial_console(name)` | Serial port 1 output of the instance, read-only. |
| Instance verification | `verify_instance(name, expected_build, expect_mounts, timeout)` | Polls the serial console until the guest agent reports the startup scripts finished (or an explicit failure line), compares the booted image with the expected build, and counts clean XFS mounts against the declared data disks. |
| Instance operations | `run_session_command(name, script, timeout)` | `gcloud compute ssh <name> --tunnel-through-iap --command <script>` as the operator's gcloud account. |
| `empty --runtime` | `inventory()` | Instances and disks in the zone and every custom image in the project (Compute API), plus the project's buckets (`gcloud storage buckets list`). |
| Retention | `dispose_image(build_id)` | Deletes the image named by the build id and waits for the operation. `NotFound` returns `False` (already gone). |
| State reconciliation | `retag_image(image_id, tags)` | `setLabels` on one of the system's own images: the current labels merged with the given tags, both sides passed through `gce_label()`. |
| State query | `query_images(series)` | Every image in the project with a `csis_series` label: `{image_id, name, state, created, tags}` (labels as tags). |
| State query | `can_query_instance_boot_image()`, `query_instance_boot_image(name)` | `True`; the instance's boot disk's `source_image` basename, or `None` when the instance, disk, zone or project cannot be resolved. Read-only, never fatal. |
| Release | `release_commands(build_id, tags)` | Base default: none. A release on GCE is recorded and relabelled through `retag_image`, not through a CLI command. |

`gce_name()` and `gce_label()` in
[gcp_packer_source.py](src/cs_image_system/gcloud_runtime/gcp_packer_source.py)
are the one place every csis name and tag is mapped to GCE's constrained
forms: names to `[a-z]([-a-z0-9]*[a-z0-9])?` (63 characters, prefixed `i-`
when they would start with a digit), labels to lowercase `[a-z0-9_-]`.
Every hook that names a GCE resource goes through them.

### Credentials

`GCPCloudBuilderModel.self_to_gcp_client_config()` returns `project`,
`region` and `zone` (and `credentials`, which is always empty). The Compute
clients in [gcp_utils.py](src/cs_image_system/gcloud_runtime/gcp_utils.py)
are built without explicit credentials, so the Google client library's
Application Default Credentials apply: `gcloud auth application-default
login` on a workstation, `GOOGLE_APPLICATION_CREDENTIALS`, or the runner's
attached service account. `run_session_command` and `inventory()` shell out
to `gcloud`, which uses the operator's active gcloud account. Nothing in the
tree names a key.

### Network discovery at load

`update_networking()` in
[gcp_runtime_models.py](src/cs_image_system/gcloud_runtime/gcp_runtime_models.py)
first calls `resolve_project()`; with no project it logs a warning and
returns, so a tree without `project_id` loads but cannot resolve images or
bake. With a project it calls `get_network_map_and_default_network()`, which
lists networks, routes, firewall rules and an aggregated subnetwork list once
each and builds:

- `network_map`: for every network, a `subnets` list of `{subnet_id, self_link, region, cidr, is_public, tags, config}`. GCE routes are network-scoped, so a network is public when it has a `0.0.0.0/0` or `::/0` route whose next hop is `default-internet-gateway`, and every subnetwork in it inherits that.
- `default_network`: `default` when a network of that name exists.
- `all_firewall_rules`: every rule by name.

Then it validates the declaration: `network: default` becomes the network
named `default` (an error when the project has none); the network must
exist; every declared `subnet_id` must match a subnetwork by name, full self
link, or `projects/...` path suffix; every `network_tags` entry that no
firewall rule targets logs a warning.

### The image query

`query_provider_image()` takes one OS-builder runtime entry
(`OSBuilderBaseImageBuilderSubconfig` in
[os_builder_runtime_config.py](../base/src/cs_image_system/base/models/os_builder_runtime_config.py)).
`remap_for_image_query()` builds a Compute `list()` query:

- `projects` is the entry's `get_owners()` (the OS builder's owners, the runtime's `default_owners`, the entry's own), resolved by `resolve_projects()`: `self` becomes the session project; the aliases `debian`, `ubuntu`, `rhel`, `centos`, `rocky`, `fedora`, `suse`, `windows`, `cos` and `google` become the public image projects (`debian-cloud`, `ubuntu-os-cloud`, `rhel-cloud`, ...); AWS-only aliases (`amazon`, `aws-marketplace`, `aws-backup-vault`) and anything that is not a valid project id (an AWS account number, for example) are dropped; a valid project id such as `almalinux-cloud` is kept as is.
- `query.filters` become a filter expression: `name`, `family`, `state`/`status`, `architecture`, `description` and `creation_date` map to image fields; `state: available` becomes `status = "READY"` (forced when absent); architectures map to `X86_64`/`ARM64`; `tag:<key>` becomes `labels.<key>`; AWS-only keys (`root_device_type`, `virtualization_type`, `block_device_mapping.*`, ...) are dropped instead of excluding every result; keys the map does not know go to a post-query exact-match filter.
- A `family` key with no filter expression resolves through `getFromFamily` instead.

`query_image()` lists every candidate project, applies the post-query
filter, and returns the newest `creation_timestamp` with the owning
`project` added. The builder returns `(name, project, raw)`; the base
registers a `GcpProviderSpecificImage` in the resolved state.

`GcpProviderSpecificImage.get_query_assets()` describes the image as a
generic query (`filters = { name = "<name>" }` plus `owners` when resolved;
`owners = ["self"]`, `filters = { name = "<pattern>*" }`, `most_recent`
when deferred). The packer source does not use these assets: GCE's image
families are the series, so `googlecompute_source()` writes `source_image`
(a resolved or pinned parent) or `source_image_family` (a deferred parent)
directly.

[tests/test_gcp_utils.py](tests/test_gcp_utils.py) and
[tests/test_gcp_provider_specific_image.py](tests/test_gcp_provider_specific_image.py)
pin the remap, the project resolution, the newest-wins rule and the asset
shapes without network access.

### Image families

Every bake sets `image_family = gce_name(<series>)`, so "the latest build of
series X" is GCE's own `source_image_family = X` lookup. A pinned parent
bakes from `source_image = gce_name(<build id>)`; the build id is the image
name. `query_images()` reads the `csis_series` label rather than the family
so the state query compares the same facts on both clouds.

### IAP

With `session_mechanism: iap` the packer source gets `use_iap = true` and
`iap_tunnel_launch_wait = 120`, so packer reaches the build VM through the
IAP tunnel instead of its external address; the ephemeral external IP stays
for package egress only. `run_session_command` tunnels the same way. The
operator prerequisites are outside the tree: a firewall rule allowing
`35.235.240.0/20` to port 22 and `roles/iap.tunnelResourceAccessor` for the
account that opens tunnels. The bake installs `google-guest-agent` so
metadata SSH keys are provisioned at first boot.

### The state query and instance hooks

`query_images`, `query_instance_boot_image`, `inventory`, `serial_console`,
`retag_image` and `dispose_image` use `compute_v1` clients built from the
session config. The state query in
[state_query.py](../base/src/cs_image_system/base/state_query.py) reads
`query_images` to classify `missing`, `foreign` and `changed` images, and
asks `query_instance_boot_image` because `can_query_instance_boot_image()`
is `True`. `verify_instance` is the deferred verification step of the
instance lifecycle. `inventory()` feeds `empty --runtime`, which subtracts
the declared storages' cloud names and the released builds and reports what
is left.

### Retention and the GCE cycle

The closing `retention` lifecycle in
[retention.py](../base/src/cs_image_system/base/retention.py) runs
`dispose image --retention` at execution time. For each series on this
runtime the number of builds kept is, in order: `0` when the runtime is
`ephemeral`, the image's `retention.keep`, the runtime's `retention_keep`,
else everything. Builds beyond that are disposed through `dispose_image()`,
except released builds and builds an instance is pinned to or was launched
from, which are reported as retention debt and kept. Declared storages are
never touched by retention.

The fixture's `gcloud-east1` declares `ephemeral: true`, and this is the
GCE cycle: a run bakes its images, launches its ephemeral instance, verifies
it from the serial console, tears it down, and the closing retention step
disposes of every image baked on the runtime. What persists across runs is
the declared storages (a persistent disk and a bucket in the fixture) and
any released build. `empty --runtime gcloud-east1` proves the runtime is in
that state afterwards.

### Cost posture

A successful run on an ephemeral GCE runtime leaves standing: the declared
storages and any released build. It may also leave standing: a
non-ephemeral instance, and an ephemeral instance whose verification failed
under `on_failure: keep` (`teardown_after` lets a later run tear it down).
`bake_preemptible: true` bakes on spot VMs; `default_disk_size` fixes the
boot disk of every image, and therefore of every instance, at a small size.
On a non-ephemeral GCE runtime the AWS rules apply: images stand until
retention or an explicit `dispose image` removes them.

## Emission

The plugin's output is visible in the golden emission under
[tests/fixtures/v2_golden/generated](../../tests/fixtures/v2_golden/generated).

- [pckr-gce-ans-image-generation-source-basic-rh-10-block-000.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-gce-ans/image-generation/block-000/pckr-gce-ans-image-generation-source-basic-rh-10-block-000.pkr.hcl):
  the `source "googlecompute"` block written by `googlecompute_source()`:
  `project_id`, `zone`, `source_image` and `source_image_project_id` (a
  resolved vendor image and its project), `image_name` (`gce_name` of the
  final name), `image_family` (the series), `image_labels` (the merged
  lineage tags, sanitised), `machine_type` (the runtime entry's, else the
  runtime default), `service_account_email`, `use_iap` and
  `iap_tunnel_launch_wait` (the mechanism is `iap`), `preemptible`,
  `disk_size` (the runtime's `default_disk_size`), `ssh_username` and
  `subnetwork` (the default subnet). `network` is emitted only when it
  resolves to a non-default name, and `tags` only when `network_tags` are
  declared.
- [pckr-gce-ans-image-generation-block-000-build.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-gce-ans/image-generation/block-000/pckr-gce-ans-image-generation-block-000-build.pkr.hcl):
  the `# debug session mechanism (iap)` shell provisioner
  (`session_agent_commands`), the `# verify: guest agent baked for IAP
  sessions` lines inside the in-bake verification (`session_verify_commands`),
  and the closing `# runtime bake finalization (gcloud-east1)` provisioner
  (`bake_finalize_commands`). The `googlecompute` entry in the neighbouring
  `-plugins.pkr.hcl` comes from the image builder's `required_plugins`.
- [tofu-gce-instance-generation.tf](../../tests/fixtures/v2_golden/generated/instance-image/tofu-gce/instance-generation/tofu-gce-instance-generation.tf)
  and
  [tofu-gce-instance-generation-instance-gce_test.tf](../../tests/fixtures/v2_golden/generated/instance-image/tofu-gce/instance-generation/tofu-gce-instance-generation-instance-gce_test.tf):
  written by the GCE instance plugin from this model. `provider "google" {
  project, region, zone, alias }`; the instance module's `zone`,
  `subnetwork` (the default subnet), `image_family` (the series) and, when
  declared, `network_tags`. The `.tfbackend.hcl` beside them is an S3
  backend written by the state-backend plugin; GCE roots keep their state
  there.
- Runtime facts: `cs-image-system runtime describe gcloud-east1`
  ([runtime_facts.py](../base/src/cs_image_system/base/commands/runtime_facts.py))
  reports `runtime`, `type`, `project_id`, `zone`, `region`,
  `default_machine_type`, `ephemeral`, `retention_keep`, the `images`,
  `storages`, `instances` and `ephemeral_instances` declared on it;
  `empty --runtime gcloud-east1` adds the live `inventory` and the
  `leftovers`. Commands, not files.

## Example configuration

From
[tests/fixtures/config/cfg/runtime-builders.yml](../../tests/fixtures/config/cfg/runtime-builders.yml):

```yaml
runtime_builders:
  - name: gcloud-east1
    aliases:
      - gcp
      - google
      - us-east1
    type: gcloud
    # Credentials come from the environment only (Application Default
    # Credentials or GOOGLE_APPLICATION_CREDENTIALS); nothing is declared here.
    project_id: csis-sandbox
    zone: us-east1-b
    session_mechanism: iap
    # build VMs and instances run as the least-privilege runner account
    service_account_email: csis-runner@csis-sandbox.iam.gserviceaccount.com
    # bake disk (= every instance's boot disk) at the vendor image's 10 GB floor
    default_disk_size: 10
    bake_preemptible: true
    # nothing baked here survives a successful run; declared storages persist
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

## Related

- [aws-runtime-plugin](../aws-runtime-plugin/README.md): the other runtime type, with the same hook surface on EC2.
- [default-os-plugin](../default-os-plugin/README.md): the OS builders whose runtime entries this plugin resolves to GCE images.
- [dummy-plugin](../dummy-plugin/README.md): the extension template; this package's models module imports it.
- Base classes: [runtime.py](../base/src/cs_image_system/base/models/runtime.py), [cloud_builder.py](../base/src/cs_image_system/base/models/cloud_builder.py), [credentials.py](../base/src/cs_image_system/base/models/credentials.py), [provider_specific_image.py](../base/src/cs_image_system/base/models/provider_specific_image.py), [builder_base_runtime.py](../base/src/cs_image_system/base/basic/builder_base_runtime.py), [abstract_version_checker.py](../base/src/cs_image_system/base/basic/abstract_version_checker.py).
- Consumers of the hooks: [state_query.py](../base/src/cs_image_system/base/state_query.py), [retention.py](../base/src/cs_image_system/base/retention.py), [dispose.py](../base/src/cs_image_system/base/commands/dispose.py), [verify_instance.py](../base/src/cs_image_system/base/commands/verify_instance.py), [runtime_facts.py](../base/src/cs_image_system/base/commands/runtime_facts.py).
- [docs/OPERATIONS.md](../../docs/OPERATIONS.md) for the credential contract and the operator's cycles; [docs/DESIGN.md](../../docs/DESIGN.md) for the design; [docs/PLUGINS.md](../../docs/PLUGINS.md) for the package index.

- [The configuration reference](../../docs/CONFIGURATION.md) — every field of the YAML this plugin reads, with an example.
