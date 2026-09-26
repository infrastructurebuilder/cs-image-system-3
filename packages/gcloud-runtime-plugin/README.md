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
answers the state query from the Compute API (images, booted images, power
states and instance identities), relabels released images, starts and stops
instances for bounded tasks, and deletes images by name. Credentials are
Application Default Credentials; the model declares none.

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

The version checker is looked up by an executable's `name` first and its
`type` second, so the fixture's `- name: gcloud` executable in
[executables.yml](../../tests/fixtures/config/cfg/executables.yml) is parsed
by it: the checker runs `gcloud --version` and matches
`Google Cloud SDK ([\d\.]+)` on the first line of the output, so the version
checked is the SDK's (`585.0.0`), not the `core` component's date-shaped
one (stage 48, 2026-09-17; before that the checker read the `core` line).
The fixture requires `>=500`.

Present in the package but not registered as a service:

- `GcpProviderSpecificImage` ([gcp_provider_specific_image.py](src/cs_image_system/gcloud_runtime/gcp_provider_specific_image.py)), reached through the builder's `provider_specific_image_class()` hook.

Stage 63 removed three dead pieces of code that earlier versions of this
README listed here (removed 2026-09-25): the unused constant `GCP_CLI`, the
unregistered `DummyGroupBuilderModel` copy of the
[dummy plugin](../dummy-plugin/README.md)'s group model that sat at the
bottom of the models module, and the `get_image_ssh_user` helper in
`gcp_utils.py`, which nothing called (the bake user comes from the
bake-user order, see `bake_ssh_username` below).

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
| `subnets` | `list[RuntimeSubnetModel]` | required, non-empty | `name`, `subnet_id`, `is_default`, `public`, `cidr`, `availability_zone`, `config`. `subnet_id` is a subnetwork name, a full self link, or a `projects/<p>/regions/<r>/subnetworks/<n>` path. The first entry with `is_default: true` is the default subnet. |
| `availability_zones` | `list[RuntimeAvailabilityZoneModel]` | `[]` | Entries `{name, is_default}`. Read only by `validate`'s zone-compatibility check (stage 52); the GCE emitters use the runtime's `zone` instead. |

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
| `zone` | `str \| None` | `None` | The zone build VMs and instances run in; the packer `zone`, the `google` provider's `zone`, and the scope of `inventory()`, `serial_console()`, the boot-image probe, the power-state and identity probes and `start_instance`/`stop_instance`. |
| `service_account_email` | `str \| None` | `None` | The service account attached to build VMs (`service_account_email` in the packer source). Without it packer attaches the project's default compute service account. Nothing passes it to the instance module: an instance gets whatever the module attaches. |
| `default_disk_size` | `int \| None` | `None` | Boot disk size in GB for every image baked on this runtime; wins over the image's `primary_disk_size`. A GCE instance's boot disk is exactly its image's disk. |
| `bake_preemptible` | `bool` | `False` | Bake on a preemptible (spot) VM; a preempted bake re-runs. |
| `state_configuration` | `str` | `DEFAULT` | Foreign key to a state backend. The storage and instance roots on this runtime resolve their backend as their own builder's `state_configuration`, else this value, else the default backend (`validate` resolves the bindings the same way). |
| `ssh_username` | `str` | `DEFAULT` | The bake's SSH user for images here that name none more specifically: step 4 of the bake-user order ([CONFIGURATION 5.1.1](../../docs/CONFIGURATION.md#511-the-bake-ssh-user)). Until stage 63 it overrode every entry. |
| `session_mechanism` | `str \| None` | `None` | `iap` is the only value. The model accepts any string; the builder's `session_mechanism()` raises on anything else the first time a run or `validate` asks for it. |
| `networking` | `GCPCloudNetworkingModel \| None` | `None` | Narrows the base type and makes it optional. Missing networking logs a warning at load. |
| `network_map` | `dict` | discovered | Not an init field. `{network: {"subnets": [...]}}` from the project. |
| `default_network` | `str \| None` | discovered | Not an init field. `default` when a network of that name exists. |
| `all_firewall_rules` | `dict[str, dict]` | discovered | Not an init field. `{rule_name: rule}` from the project. |

Base fields it inherits, and what this runtime does with them:

| Field | From | Default | Meaning here |
|---|---|---|---|
| `name`, `type`, `description`, `aliases` | `NameTyped` | `name`/`type` required | `type` is `gcloud`. |
| `executable`, `is_default`, `config`, `gitignore`, `tags` | `BuilderModel` | | `executable` (default `gcloud` on this model, stage 63 item 14) names the `executables` entry every gcloud call on this runtime runs through (`gcloud_binary()`), and `validate` refuses it undeclared; `is_default` makes this the runtime an unqualified reference resolves to. `tags` are accepted and read by nothing on this runtime: image labels are the lineage tags plus the image's own, and the instance's labels are the instance's own. For the same reason `validate`'s label-key check (stage 63, "Label keys" below) does not look at the runtime's own `tags`. |
| `region` | `CloudBuilderModel` | required | The `google` provider's `region`; the client config's `region`. |
| `credentials` | `RuntimeBuilderModel` | `CredentialsBase()` | Not narrowed. The base declares no fields and forbids extra keys, so `credentials:` accepts nothing; clients use Application Default Credentials. |
| `default_machine_type` | `RuntimeBuilderModel` | required | Machine type when neither an OS-builder runtime entry nor an image names one; always the instance module's `machine_type`. |
| `default_image_builder` | `RuntimeBuilderModel` | `DEFAULT` | The image builder an OS-builder runtime entry with `image_builder: default` resolves to. |
| `default_owners` | `RuntimeBuilderModel` | `None` | Appended to every vendor-image query's owner list (through the runtime entry's `get_owners()`), then mapped to projects. The lookup that reads it keyed the runtime by the wrong name until stage 63 item 22, so it was never found before 2026-09-25. |
| `default_config_username` | `RuntimeBuilderModel` | `None` | The bake SSH user when nothing more specific names one: step 5 of the bake-user order ([CONFIGURATION 5.1.1](../../docs/CONFIGURATION.md#511-the-bake-ssh-user)), read since stage 63 item 22. |
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
zone selector (use `zone`). Because no field can reach a key file, the
load-time warning for a missing project no longer suggests one (stage 63;
until 2026-09-25 it told the operator to configure a "service account key
file"): it says that no `project_id` is declared and none is in the
Application Default Credentials.

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
| Resolution | `query_provider_image_by_id(subconfig, image_id)` | Stage 63: the image an entry pins with `image_id` (a GCE image NAME), searched in the entry's owner projects with the filter `name = "<id>"` instead of the query's filters. Same return shape; `None` when no owner project has an image of that name. |
| Image generation | `packer_source_type()` | `googlecompute`. |
| Image generation | `packer_source_blocks(...)` | The `source "googlecompute"` block for one image. |
| Image generation, `validate` | `session_mechanism()` | `iap` or `None`; raises on any other declared value. Also read by the launch-parameter record (`session`), by the instance builder (no public IP under `iap`) and by `validate`'s dead-end rule (a base image with no admin key AND no session mechanism). |
| Image generation | `session_agent_commands(os_family)` | Installs `google-guest-agent` when missing (`apt-get` for `debian`/`ubuntu`, `yum` otherwise) and enables it together with `sshd`/`ssh`. Empty when the mechanism is not `iap`. |
| Image generation | `session_verify_commands(os_family)` | Assertions that the guest agent is present and enabled. Empty when the mechanism is not `iap`. |
| `validate` | `label_key_problem(key)` | Implemented by this runtime (stage 63; the base returns `None`, because AWS tags take any key). Returns a reason when `gce_label(key)` does not start with a lowercase letter: `GCE label keys must start with a lowercase letter; '<key>' becomes '<label>'`; otherwise `None`. `validate`'s `check_label_keys` asks it for every tag key declared on an image, instance or storage that lands on this runtime (see "Label keys" below). |
| Image generation | `default_bake_user(family)`, `bake_ssh_username(image)`, `one_bake_user_per_chain()` | `default_bake_user` is `packer` for every family (the last step of the bake-user order). `bake_ssh_username(image)` is the RESOLVED user for that image, the one the packer source bakes as, and the ansible provisioner names it (stage 63 item 23; it read only the runtime's field and said `packer` otherwise). `one_bake_user_per_chain()` is True, so `validate` refuses a chain whose images resolve to different users (finding 43). |
| Image generation | `bake_finalize_commands(os_family)` | The last provisioner of every bake here: adds the build user to `google-sudoers` when that group exists, so the guest agent's first-boot user cleanup succeeds and metadata SSH keys get provisioned. Emitted whatever the session mechanism. |
| After a bake | `build_id_from_artifact(artifact_id)` | The packer manifest's `artifact_id` is the image name itself; returned unchanged. |
| After a bake | `retag_image(image_id, tags)` | The packer builder stamps the recorded `csis_parent` and `csis_fingerprint` back onto the image (zero-drift-report). |
| Instance verification | `serial_console(name)` | Serial port 1 output of the instance, read-only. |
| Instance verification | `verify_instance(name, expected_build, expect_mounts, timeout)` | Polls the serial console every 15 s until the guest agent reports the startup scripts finished (`Finished running startup scripts`, or the older `startup-script exit status 0`) or an explicit failure line appears, compares the booted image with the expected build, and counts the kernel's `XFS (...): Ending clean mount` lines against the declared data disks. |
| Instance operations | `run_session_command(name, script, timeout)` | `<declared gcloud> compute ssh <name> --project <p> --zone <z> --tunnel-through-iap --quiet --command <script>` as the operator's gcloud account. Refused with `declares no session_mechanism` before anything runs when the runtime declares none (stage 63 item 14; it used to tunnel anyway and fail as IAP's problem). Used by `verify instance` (post-bake tests), `unmount storage`, the alias writer and the reachability wait. |
| Instance operations | `can_query_instance_power_state()`, `query_instance_power_state(name)` | `True`; GCE's `Instance.status` mapped onto the system's vocabulary: `PROVISIONING`/`STAGING` starting, `RUNNING` running, `STOPPING`/`SUSPENDING` stopping, `SUSPENDED` suspended, `TERMINATED` **stopped** (on GCE it means the machine exists and can be started; a deleted instance is simply not found and answers `absent`), `REPAIRING` unknown. `None` means the runtime could not answer, never that the machine is off. |
| Instance operations | `can_set_instance_power_state()`, `start_instance(name)`, `stop_instance(name)` | `True`; `instances.start`/`instances.stop`, waiting on the operation, then re-reading the state. Only `running_for_task` calls them (a bounded task that needs a running machine, which puts it back). |
| Instance operations | `can_query_instance_identity()`, `query_instance_identity(name)` | `True`; the numeric instance id and the internal hostname (a custom `hostname` when set, else `<name>.c.<project>.internal`). Feeds the generation ledger and the provider-alias writer. |
| `empty --runtime` | `inventory()` | Instances and disks in the zone and every custom image in the project (Compute API), plus the project's buckets (`gcloud storage buckets list`). |
| Retention | `dispose_image(build_id)` | Deletes the image named by the build id and waits for the operation. `NotFound` returns `False` (already gone). |
| State reconciliation | `retag_image(image_id, tags)` | `setLabels` on one of the system's own images: the current labels merged with the given tags, both sides passed through `gce_label()`, with the image's label fingerprint. Also the hook behind `lineage relabel` and `restamp`. |
| State query | `query_images(series)` | The images in the project whose `csis_series` label equals `gce_label(<s>)` for one of the series `s` asked about: `{image_id, name, state, created, tags}` (labels as tags). An empty `series` list keeps every image that carries a `csis_series` label. Stage 63: until 2026-09-25 the argument was ignored and every csis-labelled image in the project came back. The state query asks for every recorded series plus every declared OS builder and image; `lineage relabel` asks for the series of the builds it relabels. |
| State query | `can_query_instance_boot_image()`, `query_instance_boot_image(name)` | `True`; the instance's boot disk's `source_image` basename, or `None` when the instance, disk, zone or project cannot be resolved. Read-only, never fatal. |
| Release | `release_commands(build_id, tags)` | Base default: none. A release on GCE is recorded and relabelled through `retag_image`, not through a CLI command. |

`gce_name()` and `gce_label()` in
[gcp_packer_source.py](src/cs_image_system/gcloud_runtime/gcp_packer_source.py)
are the one place every csis name and tag is mapped to GCE's constrained
forms: names to `[a-z]([-a-z0-9]*[a-z0-9])?` (63 characters, prefixed `i-`
when they would start with a digit), labels to lowercase `[a-z0-9_-]`.
Every hook that names a GCE resource goes through them.

### Label keys

`gce_label()` lowercases a key and replaces what GCE cannot keep, but it
cannot invent a first letter, and GCE requires a label KEY to start with a
lowercase letter. A tag key such as `2024`, `-env` or `_x` therefore
becomes a label key GCE refuses. Since stage 63 the runtime says so through
`label_key_problem(key)`, and `validate` runs `check_label_keys` in
[validate.py](../base/src/cs_image_system/base/commands/validate.py) over
every declared tag key that becomes a label here: an image's tags for each
runtime it bakes on, an instance's tags on its runtime, and a storage's
tags on its storage builder's runtime. A key GCE cannot take is refused,
naming who declared it:

```text
<image|instance|storage> '<name>': tag key '<key>' on runtime <rt>: GCE label keys must start with a lowercase letter; '<key>' becomes '<label>'; rename the key
```

The key is never renamed silently: the operator renames it in the YAML.
Before stage 63 (until 2026-09-25) such a key passed `validate` and
generation and was refused by GCE at apply. Label VALUES are not checked.
The runtime's own `tags` are not checked because nothing on this runtime
reads them.

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

When the entry declares `image_id` (stage 63), the base's resolve step
calls `query_provider_image_by_id(entry, image_id)` instead. A GCE image
is named uniquely within its project, so the id is an image name and is
searched where the vendor query would search: `remap_for_image_query()`
builds the same `projects` list (the entry's merged owners, or a
`query.owners`), then the builder drops the query's `family` and `filter`
and sets the filter to `name = "<id>"`; the post-query filter is not
applied, and a match whose status is not `READY` is refused by name
(stage 67: `GCP runtime <rt>: pinned image '<id>' is <status>, not READY; a
bake from it would fail`). The owning project
is read from the result as for the query (else `self`). No match returns
`None`, and the base stops resolution with `OS builder <name>: image_id
'<id>' on runtime <rt> is not known to the provider`. Pinning makes the
base bake reproducible: the same vendor image every time, where the query
takes the newest match (a vendor family publishes a new image often).

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
so the state query compares the same facts on both clouds, and since stage
63 it filters on that label: only images whose `csis_series` equals
`gce_label(<series>)` for a series it was asked about come back (the label
carries the sanitised form, so the comparison is made in that form).

### IAP

With `session_mechanism: iap` the packer source gets `use_iap = true` and
`iap_tunnel_launch_wait = 120`, so packer reaches the build VM through the
IAP tunnel instead of its external address; the ephemeral external IP stays
for package egress only. `run_session_command` tunnels the same way, and the
GCE instance builder launches instances with `public_ip = false`. The
operator prerequisites are outside the tree: a firewall rule allowing
`35.235.240.0/20` to port 22 and `roles/iap.tunnelResourceAccessor` for the
account that opens tunnels. The bake installs `google-guest-agent` so
metadata SSH keys are provisioned at first boot.

### The state query and instance hooks

`query_images`, `query_instance_boot_image`, `query_instance_power_state`,
`query_instance_identity`, `inventory`, `serial_console`, `retag_image`,
`dispose_image`, `start_instance` and `stop_instance` use `compute_v1`
clients built from the session config. The state query in
[state_query.py](../base/src/cs_image_system/base/state_query.py) reads
`query_images` to classify `missing`, `foreign` and `changed` images
(asking for every recorded series and every declared OS builder and image,
so since stage 63 an image labelled with a series the tree neither records
nor declares is not listed on GCE; until 2026-09-25 every csis-labelled
image in the project came back whatever was asked), asks
`query_instance_boot_image` because `can_query_instance_boot_image()` is
`True`, and asks `query_instance_power_state` before calling a silent boot
probe "unavailable": a stopped machine is a `note`, not drift.
`verify_instance` is the deferred verification step of the instance
lifecycle, run inside `running_for_task` (a stopped instance is started for
the check and stopped again afterwards; one that cannot be started is a
SKIP, recorded as such). `inventory()` feeds `empty --runtime`, which
subtracts the declared storages' cloud names and the released builds and
reports what is left.

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
  `disk_size` (from `lineage.bake_disk_size`, the one rule the input
  fingerprint also hashes (stage 63); here the runtime's
  `default_disk_size`), `ssh_username` and
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
  project, region, zone, alias }`; the instance module's `machine_type`
  (the runtime default), `zone`, `subnetwork` (the default subnet),
  `image_family` (the series), `public_ip = false` under `iap` and, when
  declared, `network_tags`. The `.tfbackend.hcl` beside them is an S3
  backend written by the state-backend plugin; GCE roots keep their state
  there.
- Runtime facts: `cs-image-system runtime describe gcloud-east1`
  ([runtime_facts.py](../base/src/cs_image_system/base/commands/runtime_facts.py))
  reports `runtime`, `type`, `project_id`, `zone`, `region`,
  `default_machine_type`, `ephemeral`, `retention_keep`, the `images`,
  `storages`, `instances` and `ephemeral_instances` declared on it, the
  `builders` bound to it and its `emission` directories;
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
    # build VMs run as the least-privilege runner account (the packer source
    # carries it; the instance module attaches no service account)
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

## Prerequisites and integration

Everything below exists outside the system; the plugin creates none of it
and generates no IAM change. For each item: how the plugin finds it.

**A GCP project with the Compute Engine API enabled.** Found through
`project_id` on the runtime entry; it is the `project` of every Compute
client call, the packer source's `project_id`, the `google` provider's
`project` and the project `self` resolves to in an owner list. Without it
the tree loads with a warning and nothing that touches GCE works. The
Compute API must be enabled for the project: the first thing the plugin
does with it is list its networks at load.

**Application Default Credentials (ADC) for a principal that can act in
that project.** The model declares no credentials (`credentials:` accepts
no key), so every `compute_v1` client is built with no explicit credentials
and the Google auth library's default chain applies, in its order:
`GOOGLE_APPLICATION_CREDENTIALS` naming a credentials file, else
`~/.config/gcloud/application_default_credentials.json` (written by `gcloud
auth application-default login`), else the metadata server of an attached
service account. The operator's form, from
[docs/OPERATIONS.md](../../docs/OPERATIONS.md) ("Credentials and sessions"):

```sh
gcloud auth application-default login --impersonate-service-account=csis-runner@<project>.iam.gserviceaccount.com
```

which needs `roles/iam.serviceAccountTokenCreator` on the runner for the
operator's own Google user. `cs-image-system preflight` and every `run` and
`state` check that the ADC file exists at the same path (presence only: an
impersonated or authorized-user ADC refreshes itself, so no expiry is
readable) and print one `session:` line for it. In CI the
`google-github-actions/auth` action turns `GCP_WORKLOAD_IDENTITY_PROVIDER`
and `GCP_SERVICE_ACCOUNT` into ADC (read-only in CI: the GCE runtime is out
of CI by the cost decision, and the perform job only records and guards).

What that principal must be allowed to do, by hook: list networks, routes,
firewalls and subnetworks (load); list and get images in the project and in
the public image projects the owner aliases name (`resolve`, the state
query, `lineage relabel`, `empty`); `getFromFamily` (a family query);
`images.delete` (retention, `dispose image`) and `images.setLabels` (the
post-bake retag, `relabel`, `restamp`); `instances.get`, `instances.list`,
`instances.getSerialPortOutput`, `instances.start`, `instances.stop` and
`disks.get`/`disks.list` in the zone (verification, the state query,
`empty`, the power-state and identity probes). Bakes run as this principal
too: packer creates the build VM and the image, and attaching
`service_account_email` to the build VM needs `roles/iam.serviceAccountUser`
on that account (found live: a least-privilege runner cannot `actAs` the
default compute service account, which is why the field exists).

**A service account for build VMs.** Optional. Found through
`service_account_email`; emitted into the packer source only. Without it
packer attaches the project's default compute service account.

**A VPC network and a subnetwork in the project.** Found through
`networking.network` (`default` means the network named `default`; the
project must have one) and `networking.subnets[].subnet_id`; both are
checked against the project at every load, so a load needs the API and the
credentials above even for a dry run or `validate`. The subnetwork's region
should be the runtime's `region` and contain the runtime's `zone`; the
plugin does not check that, GCE refuses the VM at bake or launch if it is
wrong. Under `iap` instances get no public IP, so anything an instance must
reach on the internet needs a route the operator provides (the bake VM keeps
an ephemeral external IP for package egress).

**IAP TCP forwarding, when `session_mechanism: iap`.** Three things the
tree never creates, from OPERATIONS.md ("IAP sessions on GCE"): a firewall
rule allowing `tcp:22` from `35.235.240.0/20` on the instances' network
(`network_tags` on the runtime select tagged rules; a tag no rule targets
is warned about at load); `roles/iap.tunnelResourceAccessor` for the runner
service account, because bakes tunnel too (`use_iap = true`); and the same
role for each operator's own Google user, because `run_session_command`
runs `gcloud compute ssh --tunnel-through-iap` as the operator's active
gcloud account, not as the impersonated ADC. The operator's SSH key must be
agent-loaded or passphrase-less: nothing in a run can prompt (found live
2026-09-09). The images bake the Google guest agent so metadata SSH keys
are provisioned at first boot; the base image's package manager must be
able to install `google-guest-agent` (`apt-get` on `debian`/`ubuntu`,
`yum` elsewhere; the vendor images carry it already).

**The `gcloud` CLI.** Two hooks shell out to it: `run_session_command`
(`gcloud compute ssh`) and `inventory()` (`gcloud storage buckets list`,
so `empty --runtime` needs `storage.buckets.list` for the gcloud account).
Both run the `binary` of the `executables` entry the runtime's
`executable` names (default `gcloud`; stage 63 item 14, before which they
called `gcloud` from `PATH`), so the entry must be declared: `validate`
refuses the runtime without it. Its version is checked
when it is declared under `executables:` with `name: gcloud` (the checker
is registered under that name): the fixture declares
`binary: /usr/local/bin/gcloud` and `version: ">=500"`, the Google Cloud
SDK version; `validate` and every run refuse when the binary is missing,
the version cannot be parsed from `gcloud --version`, or it is below the
floor. Packer's `googlecompute` plugin is a prerequisite of the packer
image builder (`required_plugins` on the `packer-gce` builder), not of this
package.

**A live AWS session as well.** The GCE roots keep their terraform state
in the S3 backend by standing decision, and the tree's AWS runtimes
validate their networking at the same load, so a GCE lifecycle, `empty
--runtime gcloud-east1` and every configuration load need the AWS
profile's session too (found live 2026-09-08: an expired SSO session
stopped GCE work with GCP fully authenticated). See
[docs/OPERATIONS.md](../../docs/OPERATIONS.md) for the profile.

**Python dependencies**, from [pyproject.toml](pyproject.toml):
`google-cloud-compute>=1.49`, `google-api-core>=2.31`, `google-auth>=2.55`,
`python-hcl2>=8.1`, `pydantic>=2.13`, and the system's own
`cs-image-system-system` and `cs-image-system-hashicorp-utils` at the same
version. Python 3.13 or later.

Environment variables the plugin or its checks read: `GOOGLE_APPLICATION_CREDENTIALS`
(optional; the ADC file), and in CI `GCP_WORKLOAD_IDENTITY_PROVIDER` and
`GCP_SERVICE_ACCOUNT` (read by the auth action, not by the plugin). The
preflight also refuses any `GOOGLE_*` variable that is set but empty.

## Configuration reference

The YAML this plugin owns is one entry of `runtime_builders:` in
`cfg/runtime-builders.yml` with `type: gcloud`; the manual's section is
[docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) 4.4. Every field the
plugin's model accepts, and who reads it:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | the runtime's name; other builders name it through `runtime:`; the `# runtime bake finalization (<name>)` provisioner carries it |
| `type` | str | required | `gcloud` |
| `description` | str or null | null | free text; accepted, not read by this plugin |
| `aliases` | list[str] | `[]` | extra names the runtime answers to |
| `executable` | str or null | `gcloud` | the `executables` entry whose `binary` every gcloud call on this runtime runs (the session command, `inventory()`, the tf-gcp storage lookups and generated scripts); `validate` refuses a name that is not declared. Stage 63 item 14: until 2026-09-25 every call was a bare `gcloud` from `PATH` |
| `is_default` | bool | false | the runtime an unqualified runtime reference resolves to |
| `config` | mapping | `{}` | free-form; accepted, not read |
| `gitignore` | list[str] | `[]` | accepted, not read by this plugin |
| `tags` | mapping[str, str] | `{}` | accepted, not read: no image label, instance label or storage label comes from the runtime's tags |
| `region` | str | required | the `google` provider's `region`; the client config's `region` |
| `project_id` | str or null | null | the project (see above); `runtime describe` reports it |
| `zone` | str or null | null | the zone of build VMs and instances and the scope of every zonal query; `runtime describe` reports it |
| `service_account_email` | str or null | null | the packer source's `service_account_email`; instances are not given it |
| `default_disk_size` | int or null | null | the packer source's `disk_size` in GB, the first step of `lineage.bake_disk_size`; null falls back, for a base image, to its OS builder entry's `default_primary_disk_size` and then the OS builder's, and for an instance image to its `primary_disk_size` (stage 63) |
| `bake_preemptible` | bool | false | `preemptible = true` on the packer source |
| `state_configuration` | str | `default` | the state backend rung between a root's own and the default backend |
| `ssh_username` | str | `default` | the bake's ssh user for images that name none more specifically (step 4 of the bake-user order, CONFIGURATION 5.1.1); with nothing named anywhere, `packer` |
| `session_mechanism` | str or null | null | `iap`, or nothing; any other string is refused by the builder when first read |
| `default_machine_type` | str | required | the bake's `machine_type` when the OS-builder runtime entry names none, and always the instance module's `machine_type` |
| `default_image_builder` | str | `default` | the image builder an OS-builder runtime entry with `image_builder: default` resolves to |
| `default_owners` | list[str] or null | null | extra owners for every vendor-image query on this runtime, resolved to projects |
| `credentials` | mapping | `{}` | must be empty; any key is a validation error |
| `default_config_username` | str or null | null | the bake ssh user when no image entry, OS entry, `config_username` or runtime `ssh_username` names one (stage 63 item 22) |
| `ephemeral` | bool | false | every image baked here is disposed by the closing retention lifecycle |
| `retention_keep` | int or null | null | builds kept per series when the image declares no `retention`; null keeps all |
| `on_failure` | str or null | null | ephemeral default: `keep` or `teardown` |
| `teardown_after` | str or null | null | ephemeral default: `<number>` followed by `m`, `h` or `d` |
| `networking` | mapping or null | null | below; null loads with a warning and bakes and instances then emit no `subnetwork` |

`networking:`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | the network | a label; must not be empty after stripping |
| `network` | str | `default` | the network name; `default` becomes the network literally named `default` at load |
| `subnets` | list | required, at least one, one `is_default: true` | see below |
| `availability_zones` | list | `[]` | `{name, is_default}`; only `validate`'s zone-compatibility check reads the default one |
| `network_tags` | list[str] | `[]` | the packer source's `tags` and the instance module's `network_tags` |

`networking.subnets[]:`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | the subnet id | label |
| `subnet_id` | str | required | a subnetwork name, self link, or `projects/<p>/regions/<r>/subnetworks/<n>` path; checked against the project at load; the default one is the packer source's and the instance module's `subnetwork` |
| `is_default` | bool | false | the subnet bakes and instances use |
| `public` | bool | false | accepted, not read (the plugin discovers publicness from the routes) |
| `cidr` | str or null | null | accepted, not read |
| `availability_zone` | str or null | null | the zone `validate`'s compatibility check attributes to the runtime when no default availability zone is declared |
| `config` | mapping | `{}` | accepted, not read |

Fields the plugin reads from YAML it does not own:

| Where | Field | Read by |
|---|---|---|
| the OS builder's runtime entry (`os_builders[].runtimes[]`) | `owners`, `query.filters`, `query.owners` | the image query |
| the same entry | `image_id` | stage 63: a GCE image name that replaces the query's filters; searched in the entry's owner projects |
| the same entry | `default_primary_disk_size` | stage 63: a base image's `disk_size` when the runtime declares no `default_disk_size` |
| the same entry | `machine_type`, `default_machine_type` | the packer source's `machine_type`, before the runtime default |
| the same entry | `ssh_username` | the packer source's `ssh_username` and the ansible provisioner's `user`, for this OS and every image built on it, whatever the runtime declares |
| the image | `primary_disk_size` | an instance image's `disk_size` when the runtime declares no `default_disk_size` (a base image's is its entry's `default_primary_disk_size`, else the OS builder's) |
| the image | `source_image`, `parent_policy`, the pin | `source_image` (pinned or resolved) or `source_image_family` (deferred) |
| `cfg/executables.yml` | the `gcloud` entry's `binary` and `version` | the version checker |
| the instance | `runtime`, `image`, `storages`, `tags` | the GCE instance plugin, which reads `zone`, `default_machine_type`, `networking` and `session_mechanism` from this model |

Not in the model, and refused at load because unknown keys are errors:
`account_id`, `security_group_ids`, `session_instance_profile`,
`iam_instance_profile`, `ena_support`, `sriov_support`, `runtime_classifier`,
and any key inside `credentials:`.

### Variations

- **`session_mechanism: iap` vs unset.** With `iap` the packer source gets
  `use_iap = true` and `iap_tunnel_launch_wait = 120`, the bake gains the
  guest-agent install provisioner and the guest-agent assertions in its
  in-bake verification, the instance module gets `public_ip = false`, the
  launch record's `session` is `iap`, and `run_session_command` works. Unset,
  the bake reaches the build VM over its external IP on tcp:22 (which needs
  a firewall rule the operator owns), instances keep a public IP, no agent
  is installed or asserted, `run_session_command` still runs `gcloud
  compute ssh --tunnel-through-iap` (it does not check the mechanism, so it
  fails without the IAP wiring), and `validate` refuses a base image on
  this runtime that also declares no admin public key (no debug path). The
  finalize provisioner is emitted either way.
- **`ephemeral: true` vs `false`.** Ephemeral: the closing retention step
  disposes every build baked here that is not released, pinned or launched
  from, whatever `retention_keep` or the images' `retention` say; `empty
  --runtime` then expects no custom image but released ones. Durable:
  builds stand until `retention.keep`, `retention_keep` or an explicit
  `dispose image`.
- **Pinned vs deferred vs resolved parent.** A pinned parent bakes from
  `source_image = gce_name(<build id>)`; a resolved vendor image from
  `source_image = <name>` plus `source_image_project_id = ["<project>"]`
  (omitted when the owner is `self` or unset); a deferred parent (built
  earlier in the run or by a previous one) from `source_image_family =
  gce_name(<series>)`, which GCE resolves to the newest image of the family.
  `parent_policy: follow` moves the pin after the bake and the post-bake
  retag writes the resolved parent onto the image.
- **`default_disk_size` set vs null.** The packer source's `disk_size`
  is `lineage.bake_disk_size` (stage 63), the rule the input fingerprint
  also hashes. Set: every image here bakes at that size and everything
  else is ignored. Null: a base image takes its OS builder entry's
  `default_primary_disk_size` for this runtime when declared, else the OS
  builder's `default_primary_disk_size` (200 GB unset); an instance image
  takes its own `primary_disk_size`. Stage 63 moved no GCE fingerprint:
  the runtime's `default_disk_size` already won, and still does.
- **A queried vs a pinned vendor image.** Without `image_id` on the OS
  builder's entry, resolution runs the filter query and takes the newest
  match, so the next base bake may start from a newer vendor image. With
  `image_id` (stage 63) that one image name is looked up in the entry's
  owner projects; the id is part of the fingerprint's vendor source.
- **`ssh_username` set vs `default`.** Either way the packer source and
  the ansible provisioner name the same user, the one the bake-user order
  resolves: an entry's user wins over this field, this field over the
  runtime's `default_config_username`, and with nothing named anywhere it
  is `packer`. Before stage 63 the runtime's value overrode the entry, and
  with it unset the provisioner said `packer` even when the entry named
  another user.
- **`network: default` vs a name.** `default` is replaced at load by the
  network named `default` and the packer source emits no `network` line;
  a named network is checked to exist and emitted as `network`.
- **`network_tags` declared vs empty.** Declared: `tags = [...]` on the
  packer source, `network_tags` on the instance module, a load-time warning
  per tag no firewall rule targets. Empty: neither line is emitted.
- **Owner aliases vs project ids vs AWS-only owners.** `self` becomes
  `project_id`; distro aliases become the public image projects; a valid
  project id is used as is; `amazon`, `aws-marketplace`, `aws-backup-vault`
  and anything that cannot be a project id (an AWS account number) are
  dropped, so a shared OS-builder query works on both clouds.
- **`filters` with AWS-only keys.** `root_device_type`,
  `virtualization_type`, `block_device_mapping.*` and the rest of
  `AWS_ONLY_QUERY_KEYS` are dropped with a DEBUG line; an unknown key is
  applied as an exact post-query match on the image dictionary (a typo
  therefore matches nothing and the resolution fails, by design).
- **`state: available` vs anything else.** `available` maps to `status =
  "READY"`, which is also forced when no status is given; `pending`/`failed`
  map to `PENDING`/`FAILED`; another value is upper-cased as given.
- **`bake_preemptible: true` vs `false`.** True emits `preemptible = true`;
  a preempted bake fails and is re-run by the next run (nothing is recorded
  for it). False emits nothing.
- **`project_id` set vs null.** Null: the load warns and skips network
  discovery and validation; `resolve` then fails with `Owner 'self'
  requires a project ...` and every Compute hook raises `no project ...`.
  The warning names the missing `project_id` (stage 63; it named a
  "service account key file" until 2026-09-25, which no field of this
  runtime can declare, and the project is never read from the
  Application Default Credentials).
- **A tag key that starts with a lowercase letter vs one that does not.**
  A key whose `gce_label` form starts with `a`-`z` (`Project` becomes
  `project`) passes and is emitted as a label. A key whose label form
  starts with anything else (`2024`, `-env`, `_x`) on an image, instance or
  storage that lands on this runtime is refused by `validate` (stage 63,
  `check_label_keys`); the same key on an AWS runtime passes, because the
  base `label_key_problem` answers `None` there. Until 2026-09-25 it passed
  `validate` everywhere and GCE refused it at apply.
- **`query_images` with series vs with none.** Given series, only images
  whose `csis_series` label is one of them (in `gce_label` form) come back;
  given an empty list, every csis-labelled image in the project does
  (stage 63; the argument was ignored until 2026-09-25).
- **Dry run vs real run.** The plugin itself does not read the flag. A dry
  run still loads (so network discovery still calls the API), still
  resolves vendor images (the `resolve` phase queries the image projects),
  and still emits the packer source and the terraform arguments; nothing is
  baked, verified, disposed or relabelled because the runner scripts are
  enumerated, not executed. `dispose image` under `--dry-run` prints its
  plan and calls no hook; `lineage relabel` is dry by default.
- **Apply flag on vs off.** With `apply_instances: [gcloud-east1]` (or
  `--apply-runtime gcloud-east1`) the instance root applies, the launch is
  recorded, the verification runs, `mark_launched` fires, the generation
  ledger asks `query_instance_identity` and the alias writer asks it again.
  Off, the root plans and gates only and none of the instance hooks run.
- **`--only-runtime` another runtime.** No GCE image bakes and no GCE root
  is generated or planned (a run scoped away from this runtime cannot fail
  on its family lookup); retention disposes within the scoped runtime only.
- **A stopped instance.** `TERMINATED` maps to `stopped`; the state query
  writes a `note` instead of an `unavailable` line, `verify instance` starts
  the machine for the check and stops it again, `verify login` and the
  alias writer skip it, and nothing else touches its power state.
- **Encrypted vs clear values.** The plugin reads no encrypted value: every
  field it owns is a name, an id or a number. An `ENC[age:...]` marker in
  one of them would reach the API as the literal marker.

## What it tests and verifies

**At load (pydantic, then `finalize()`).** Unknown keys anywhere in the
entry are refused with the field path (`extra="forbid"`); `credentials:`
with any key is refused; a networking block must have a non-empty `name`
and `network`, at least one subnet and one `is_default: true`; a runtime
must declare `default_machine_type`. Then `update_networking()`: with a
project it calls the Compute API and refuses the load (a `ValueError`; the
CLI exits 1 for any command that loads the tree, `validate` included) when
`network: default` names nothing, the network is absent from the project,
or a `subnet_id` matches no subnetwork of that network; it logs a warning
per network tag no firewall rule targets, a warning when `networking` is
absent, and a warning when no project can be resolved. The verdict lands
in the log; the discovered `network_map`, `default_network` and
`all_firewall_rules` stay on the model for the emitters. The test suite
stubs `get_network_map_and_default_network` with the fixture's own subnet
ids (see `tests/v2_support.py`), so no test reaches the API.

**At `validate`.** The `gcloud` executable's binary exists and its SDK
version satisfies the declared requirement (one INFO line names every
version found; a failure names the tool); `session_mechanism()` is asked
for the dead-end rule, so an unsupported value surfaces here as a
`ValueError`; the zone-compatibility check reads `networking`'s default
availability zone or the default subnet's `availability_zone` against the
instances and zonal storages on the runtime; the state-location check
resolves each root's backend through `state_configuration`; and (stage 63)
`check_label_keys` asks `label_key_problem` about every tag key declared on
an image baked here, an instance on this runtime and a storage whose
builder's runtime is this one, refusing a key whose label form does not
start with a lowercase letter (it used to pass here and fail at apply
until 2026-09-25). Every failure is one line naming the object, and
`validate` exits 1.

**At generation.** `session_mechanism()` again (the packer provisioners,
the instance builder, the launch record). The packer source is emitted
with the sanitised names; the golden emission under
`tests/fixtures/v2_golden` pins its exact shape, and `just test` fails on
any drift of it. `test_v2_explore_gcp.py` asserts the emitted commands: the
finalize provisioner is the last one of every GCE bake, IAP runtimes emit
`use_iap` and the tunnel wait and non-IAP ones do not, the disk size comes
from the runtime, the device name and the mounted by-id path agree.
`test_v2_gce_cycle.py` pins that `bake_preemptible` lands on the source and
that `retag_image` merges the lineage truth into the labels. The package's
own tests pin the query remap and project resolution.

**In the bake (packer, on the build VM).** The in-bake verification
provisioner runs `session_verify_commands` under `set -e`: the guest agent
binary exists and the unit is enabled; a failed assertion fails the bake
and packer deletes the build VM. The finalize provisioner runs last and is
tolerant (`|| true`).

**After a bake.** The packer builder records the build from the manifest
(`build_id_from_artifact` returns the image name) and calls `retag_image`
to stamp `csis_parent` and `csis_fingerprint` from the record; the labels
and the record then agree, which the state query later checks.

**After the instance apply (verification).** `verify instance <name>`
runs inside `running_for_task`; the hook polls the serial console until
the startup scripts report completion, checks the booted image against the
pin or launch record (or, for an image built this run, against the lineage
records of the instance's series on this runtime), counts clean XFS mounts
against the declared data disks, and then runs the image's declared
post-bake tests over `run_session_command`. The verdict lands in
`meta-state/verifications.yaml` (`ok`, `checks`, the last 20 serial
console lines mentioning `startup`, `XFS` or
`google_metadata_script_runner` as `evidence`), post-bake results in
`meta-state/image-tests.yaml`, one `verify <name>: <check>: ok|FAILED --
<detail>` log line per check, and a failed verdict raises
`VerificationFailed`, which stops the runner with the instance standing
(`on_failure: keep`) or after its teardown (`teardown`); the run exits 1.
A stopped instance that cannot be started is recorded as `skipped` with no
verdict.

**After the apply (generations and aliases).** `query_instance_identity`
gives the numeric instance id that defines the instance's generation in
`meta-state/instance-state.yaml`; the alias writer reads it again, waits
until `run_session_command` answers, and writes the AltNames over the same
session (log lines `now also answers to [...]` or a `WARNING`/`ERROR`
naming why not).

**In the state query.** `query_images` lists the images whose
`csis_series` label is `gce_label` of a series the query asked about (the
recorded series and the declared OS builders and images; stage 63, it
listed every csis-labelled image until 2026-09-25); the base classifies `missing` (recorded, not found),
`foreign` (labelled, not recorded) and `changed` (labels disagree with the
record) images. `query_instance_boot_image` compares a pinned instance's
booted image with its pin (`changed`, or a `note` when a replacement is
pending) and finds standing ephemerals; `query_instance_power_state` turns
a stopped machine into a `note`. Any hook that raises becomes an
`unavailable:` line naming the label and the error, never a claim. The
report is `generated/state-report.json` (run-local) and the log;
`state query --strict` exits 1 on any drift but `stale`.

**In `empty --runtime`.** `inventory()` is subtracted by the declared
storages' cloud names and the released builds; any leftover instance,
image, disk or bucket is printed and the command exits 1; a hook that
cannot answer exits 2.

**In retention and `dispose image`.** `dispose_image` reports
`deleted=True|False` per build in the log (`False` when GCE already had no
such image); the lineage record is dropped either way.

## When it fails

Failures that have happened, newest first. Dates are the ledger's
([docs/history/LEDGER.md](../../docs/history/LEDGER.md)) or the test
docstrings'.

- **2026-09-21 -- a stopped machine reported as "could not answer".** The
  boot-image probe answered `None` for an instance the operator had
  stopped, the state query wrote `unavailable`, and the records described a
  machine that was not there. Since stage 57 the plugin maps GCE's
  `TERMINATED` to `stopped` (it is not deleted: a deleted instance is `not
  found` and maps to `absent`), the query asks the power state before
  calling silence unavailable, and the line is a `note` (`instances/<name>:
  stopped; its pinned build ... still stand ...`). Nothing to do; a stopped
  machine is the operator's decision.
- **2026-09-10 -- `Script disconnected unexpectedly` at the last scriptlet
  of the security-update transaction.** A GCE base bake over the IAP tunnel
  died after 3 min 24 s as the transaction closed (`pam`, `dbus-broker`,
  `libssh`, `curl`, `python3`...); packer cleaned its build VM, nothing was
  left on GCE, and a scoped retry (`run base-image --only
  basic-rh-10@gcloud-east1`) baked cleanly. Transient, not reproduced; the
  watch item is packer's `expect_disconnect` or a pause on the OS-update
  provisioner of IAP runtimes if it recurs. Look at packer's log in the
  bake's block directory; retry the bake alone.
- **2026-09-10 -- `family/imgfile-basic-dask` returned 404 at the GCE
  instance plan.** A run scoped to the AWS runtime still planned the GCE
  instance root, whose module resolves a deferred image through
  `data "google_compute_image" { family = ... }`, and the previous cycle's
  retention had disposed every GCE image. Since then a run scoped to one
  runtime (`--only-runtime`, or `--apply-runtime` implying it) generates
  and plans no other runtime's root. If it appears in an unscoped run: the
  family is empty because retention emptied it; bake the series first.
- **2026-09-09 -- `read_passphrase: can't open /dev/tty`.** The operator's
  `google_compute_engine` key was passphrase-protected and the session hook
  (`gcloud compute ssh`, non-interactive) cannot prompt, so every
  `run_session_command` failed. Use an agent-loaded or passphrase-less key
  (the project's `ssh-keys` metadata was re-provisioned by the guest agent
  within seconds of the change).
- **2026-09-08 -- `changed` drift: `fingerprint differs` on a follow image
  (finding 66).** A `parent_policy: follow` image baked in the same run as
  its parent got its labels from packer at generation time (parent
  `series:...`, a placeholder fingerprint); the lineage record was written
  after the bake; `retag_image` was a no-op on GCE, so the strict preflight
  refused the next run. `retag_image` now does `setLabels`. For images
  already standing: `lineage relabel --runtime <rt>` (`just cloud-relabel
  <rt> no`; dry by default) re-labels every recorded build whose labels
  disagree with its record.
- **2026-09-08 -- `4047: Failed to lookup instance` and an SSH timeout
  against a healthy build VM (finding 64).** A bake that followed another
  build in the same run hit IAP's instance-lookup lag for longer than
  packer's default 30 s tunnel wait; four reproductions, serial consoles
  showed sshd up in 30 s. IAP bakes now set `iap_tunnel_launch_wait = 120`.
  If it recurs, `PACKER_LOG=1` shows the tunnel retries; the wait is a
  constant in `gcp_packer_source.py`.
- **2026-09-08 -- `No valid credential sources found ... backend s3 ...
  the SSO session has expired` at the GCE instance plan (finding 65).** The
  AWS session lapsed mid-cycle; the GCE roots' state is in S3 and every
  load validates the AWS runtimes' networking. Renew the AWS session (`aws
  sso login --profile <p>`) and rerun; the preflight now reads session
  lifetimes before a run. `empty --runtime gcloud-east1` needs the AWS
  session for the same reason.
- **2026-09-08 -- verification failed on `booted image` with a launch
  record of `unbound` (finding 63).** The instance's image was baked in the
  same run, so nothing was pinned and the check compared the booted image
  with the literal `unbound`; the instance was left standing by the rule.
  Verification now requires the booted image to be a recorded build of the
  instance's image series on its runtime. The recovery was the next
  instance-image run resuming the sequence.
- **2026-09-07 -- `gce-verify` never saw `startup-script exit status 0`
  (finding 56).** Guest agent 20260715 logs `Finished running startup
  scripts` instead; the instance was healthy the whole time. The hook
  accepts both lines. A verification that reports `no completion on the
  serial console within <timeout>s` on a newer agent means a third
  spelling: read `serial_console` output (the `evidence` in
  `verifications.yaml`) and extend the pattern.
- **2026-09-07 -- a dask bake timed out waiting for SSH through the IAP
  tunnel (finding 55).** In the window GitHub's release downloads were
  returning 504; the retry booted, provisioned in about 90 s and imaged
  cleanly. Later understood as finding 64 above.
- **2026-09-06 -- every bake timed out `waiting for SSH` (finding 54).**
  Packer reached build VMs over their external IP on tcp:22, which only
  worked while the default VPC's `default-allow-ssh` rule existed; deleting
  it (deliberate hygiene) broke every bake. IAP runtimes now bake through
  the tunnel (`use_iap = true`); the operator prerequisite is
  `roles/iap.tunnelResourceAccessor` for the runner service account. The
  same symptom today means that role is missing.
- **2026-09-05 -- the instance boot disk was 200 GB, about $8/month
  (finding 51).** The boot disk inherited the image's `disk_size`, which
  inherited the OS builder's 200 GB default (a RHEL vendor minimum carried
  forward). `default_disk_size` on the runtime now wins; the fixture bakes
  at the vendor image's 10 GB floor (a boot disk cannot be smaller than its
  source image).
- **2026-09-05 -- every SSH/IAP session to the launched instance refused
  (finding 47).** At first boot the guest agent removes users absent from
  metadata; when the bake user's `google-sudoers` membership was missing
  (the agents race over it during bakes) `gpasswd` exited 3 and the agent
  aborted its whole metadata-ssh-key setup, so no operator key was ever
  provisioned. `bake_finalize_commands` now guarantees the membership as
  the bake's last act. The symptom returning means the finalize provisioner
  is not the last one in the emitted `-build.pkr.hcl` (the test
  `test_gce_bakes_end_with_the_finalize_provisioner` guards it).
- **2026-09-05 -- ansible tasks died `unreachable / Failed to create
  temporary directory` (finding 48).** Packer's ansible provisioner
  defaulted `ansible_user` to the operator's local login, not the build
  VM's ssh user, so ansible built `~/.ansible/tmp` under
  `/home/<local-user>`; intermittent because packer's `use_proxy`
  auto-detection masked it. `bake_ssh_username(image)` pins the provisioner
  `user` to the bake's user, the one the packer source resolves (since
  stage 63 item 23; it read only the runtime's field before).
- **2026-09-04 -- the base bake used ssh user `ec2-user` while the
  instance bake fell back to `packer` (finding 43).** The new-generation
  guest agent removes the other-name user at first boot and aborts key
  provisioning; one GCE chain must bake every image as ONE user. Declare
  `ssh_username` on the OS-builder runtime entry (it covers the chain), or
  on the runtime. Since stage 63 `validate` refuses a chain whose images
  would bake as different users, and the GCE family default is `packer`.
- **2026-09-03 -- a dask bake fell through to the runtime's 1 GB machine
  and OOMed at 65 minutes (finding 41).** The packer source's
  `machine_type` now follows the AWS-parity chain: the OS-builder runtime
  entry's `machine_type`, its `default_machine_type`, then the runtime's
  `default_machine_type`. A bake that needs memory declares it on the
  entry; the runtime default is the free-tier `e2-micro` in the fixture.
- **2026-09-03 -- underscores in GCE names (findings 34-37).** GCE refuses
  `_` in resource and device names; every name now goes through
  `gce_name()`. A `gce_data` disk attached under that name while the
  startup script mounted `/dev/disk/by-id/google-gce-data` (finding 50,
  2026-09-05) is the same lesson on the instance side: one sanitisation
  serves both.

Failures the code raises that have not happened live, by where they
surface:

- **Load.** ``No usable GCP project could be resolved for cloud builder
  <name> (no `project_id` declared on the runtime). Skipping network validation; image
  resolution and build execution will not work until valid GCP credentials
  are configured.`` (WARNING): no `project_id`; add one. (Stage 63: until
  2026-09-25 this warning pointed at a "service account key file", which
  no field of this runtime can declare.) `No networking configuration provided for GCP cloud builder
  <name>` (WARNING): bakes and instances will carry no `subnetwork`.
  `No network specified ... and no 'default' network found in GCP project`,
  `Network <n> ... not found in GCP project`, `Subnetwork <id> ... not
  found in network <n>` (ERROR, then a `ValueError` that ends the load,
  exit 1): fix the declaration or the project. `GCP Error: <api error>`
  (`ValueError`): the API refused the listing, usually permissions or a
  disabled Compute API. An auth error (`DefaultCredentialsError`, no ADC)
  is not wrapped and ends the load with the library's own message: run the
  ADC login above. `Network tag <t> ... is not targeted by any firewall
  rule` (WARNING): the tag selects nothing.
- **`validate` / generation.** `GCP runtime <name>: unknown session
  mechanism '<x>' (supported: iap)` (`ValueError`): only `iap` exists.
  `gcloud: binary '/usr/local/bin/gcloud' not found`, `gcloud:
  GCPCLIVersionChecker could not parse a version from ...`, `gcloud <v>
  does not meet its requirement >=500 (cfg/executables.yml)`: install or
  upgrade the SDK, or move the floor in `executables.yml`.
  `Executable gcloud specified for provider <runtime> not found in
  executables list.`: the runtime's `executable` (default `gcloud`, stage
  63 item 14) names no declared entry; declare `- name: gcloud` with its
  `binary`, or point `executable` at the entry you have. The same cause at
  a session or lookup reads `GCP runtime <name>: executable 'gcloud' is
  not declared in cfg/executables.yml`.
  `<image|instance|storage> '<name>': tag key '<key>' on runtime <rt>: GCE
  label keys must start with a lowercase letter; '<key>' becomes
  '<label>'; rename the key` (stage 63, from `validate`, exit 1): a tag key
  declared on that image, instance or storage would become a label key GCE
  refuses (a key such as `2024`). Rename the key in the YAML; nothing
  renames it for you. Until 2026-09-25 the key passed `validate` and GCE
  refused it at apply.
- **A session command (post-bake verify, unmount, the alias writer).**
  `GCP runtime <name> declares no session_mechanism, so no session command
  can reach its instances (supported: iap)`: declare
  `session_mechanism: iap` (and its firewall rule and grant) or run
  nothing that needs a session on that runtime.
- **Resolution (`resolve`, the base-image phase of a run).** `Owner
  'self' requires a project in the session configuration (set project_id
  on the runtime builder ...)`; `No usable GCP projects resolved from
  query ...` (every owner was dropped as invalid); `Failed to query images
  in project '<p>' with filter: <error>` and `Failed to query image family
  '<f>' in project '<p>': <error>` (`ImageQueryError`: permissions or an
  unknown project); `No resolved Image identifiers for OS <name> in
  predefined_resolve` (the base's message when the query matched nothing:
  loosen `filters`, check the owner and the `status`); `OS builder <name>:
  image_id '<id>' on runtime <rt> is not known to the provider` (stage 63:
  the pinned `image_id` names no image in the entry's owner projects;
  check the name and that its project is among the owners); `Could not get
  owning project for image <name>` (a result with neither `project` nor a
  `self_link`; not expected from the API). Each ends the run, exit 1.
- **The state query.** `state query images/<rt> unavailable: GCP runtime
  <rt>: no project to query` or an API error: an `unavailable:` line, never
  drift; `state query --strict` still refuses on a session that will not
  outlast the run, and a plain run warns. `instances/<name>: booted image
  (runtime <rt> could not answer)`: the boot probe returned `None` and the
  machine is not stopped; the DEBUG log carries the exception.
- **Verification.** `verify <name>: startup scripts: FAILED -- an explicit
  failure line` (a `startup-script exit status <non-zero>` or a `failed`/
  `error` startup line on the console; read the `evidence`); `no completion
  on the serial console within <t>s` (the agent never reported; raise
  `--timeout`, read the console); `booted image: FAILED -- booted <x>,
  expected <y>` (the instance did not boot its pin: `upgrade instance` and
  replace, or `state query` to see the mismatch); `booted <x>, which
  lineage does not record for <image> on <rt>`; `data disks mounted:
  FAILED -- <n> clean XFS mount(s) on the console, <m> declared` (the
  startup script did not format or mount a pd: the device name and the
  by-id path must agree); `declared tests: FAILED -- k of n failed: ...`
  (the image's post-bake suite; the per-build record in
  `image-tests.yaml` names the assertion; `release` refuses the build).
  `GCP runtime <rt>: no project/zone to read a serial console`
  (`RuntimeError`): declare `zone`. A `VerificationFailed` leaves the
  instance standing under `keep` and fails the run.
- **Session commands.** A non-zero exit from `gcloud compute ssh` is
  returned with the combined output: `unmount storage` writes a failed
  receipt and raises `unmount of <mount> on <instance> failed (exit
  <rc>)`, the alias writer logs `alias write failed (<rc>): <tail>`,
  `wait_until_reachable` keeps polling until its deadline, and a post-bake
  suite shows as `no result`. The usual causes are the missing IAP role or
  firewall rule, a passphrase-protected key, or a machine still booting.
  `GCP runtime <rt>: no project/zone for a session command`: declare
  `zone`.
- **Power state.** `GCE runtime <rt>: instance '<n>' reports unrecognised
  status '<s>'; treating it as unknown` (WARNING): a status outside the
  eight the map knows; nothing acts on it. `GCP runtime <rt>: no
  project/zone to start an instance` / `... to stop an instance`
  (`RuntimeError`). `<n>: FAILED to stop it again after <why>: <error>. It
  was switched off before this run and is now RUNNING -- stop it by hand.`
  (ERROR from `running_for_task`): the one case that leaves a billable
  change behind; stop the instance.
- **`empty --runtime`.** `GCP runtime <rt>: no project/zone to inventory`;
  `gcloud storage buckets list: <stderr tail>` (the gcloud account cannot
  list buckets, or is not logged in): exit 2. A leftover named under
  `leftovers` is exit 1: dispose or decommission it through the recorded
  path, never by hand.
- **Retention and `dispose image`.** `GCE image <id> not found in <p>;
  nothing to delete` (WARNING, `deleted=False`): the image was already
  gone; the record is dropped anyway. `GCP runtime <rt>: no project to
  dispose in` (`RuntimeError`). An API error (permissions, an image in
  use by a disk) propagates and stops the retention step; the record then
  still exists and the next run retries.
- **Relabel.** `relabel: could not retag <id>: <error>` (WARNING,
  `retagged=False`): the record is right and the state query keeps showing
  the tag. `relabel: <id> is not in <rt>; nothing to relabel`: the image
  is gone; the state query reports it `missing`. The post-bake retag has no
  guard: an error there fails the bake's record step.
- **Names.** `gce_name()` never fails; two csis names that differ only in
  characters it strips (`a_b` and `a-b`, or case) collide on GCE, and the
  second bake or launch fails with the API's `already exists`. Keep names
  distinct in the lowercase `[a-z0-9-]` alphabet.

## Related

- [aws-runtime-plugin](../aws-runtime-plugin/README.md): the other runtime type, with the same hook surface on EC2.
- [default-os-plugin](../default-os-plugin/README.md): the OS builders whose runtime entries this plugin resolves to GCE images.
- [tf-gcp-plugin](../tf-gcp-plugin/README.md): the GCE instance and storage roots that read this model.
- [dummy-plugin](../dummy-plugin/README.md): the extension template (this package no longer carries a copy of its group model; removed in stage 63).
- Base classes: [runtime.py](../base/src/cs_image_system/base/models/runtime.py), [cloud_builder.py](../base/src/cs_image_system/base/models/cloud_builder.py), [credentials.py](../base/src/cs_image_system/base/models/credentials.py), [provider_specific_image.py](../base/src/cs_image_system/base/models/provider_specific_image.py), [builder_base_runtime.py](../base/src/cs_image_system/base/basic/builder_base_runtime.py), [abstract_version_checker.py](../base/src/cs_image_system/base/basic/abstract_version_checker.py), [power_state.py](../base/src/cs_image_system/base/power_state.py).
- Consumers of the hooks: [state_query.py](../base/src/cs_image_system/base/state_query.py), [retention.py](../base/src/cs_image_system/base/retention.py), [dispose.py](../base/src/cs_image_system/base/commands/dispose.py), [verify_instance.py](../base/src/cs_image_system/base/commands/verify_instance.py), [runtime_facts.py](../base/src/cs_image_system/base/commands/runtime_facts.py), [relabel.py](../base/src/cs_image_system/base/commands/relabel.py), [provider_aliases.py](../base/src/cs_image_system/base/provider_aliases.py), [generations.py](../base/src/cs_image_system/base/generations.py), [validate.py](../base/src/cs_image_system/base/commands/validate.py).
- [docs/OPERATIONS.md](../../docs/OPERATIONS.md) for the credential contract and the operator's cycles; [docs/DESIGN.md](../../docs/DESIGN.md) for the design; [docs/PLUGINS.md](../../docs/PLUGINS.md) for the package index.
- [The configuration reference](../../docs/CONFIGURATION.md) -- every field of the YAML this plugin reads, with an example.
