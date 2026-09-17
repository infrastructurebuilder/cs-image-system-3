# cs-image-system-ansible-plugin

The Ansible modification plugin. It registers one modification builder,
`ansible`, and the modification item model that goes with it. A
modification item under an image's `modifications:` names playbooks; for
each playbook the builder appends a `provisioner "ansible"` (preceded by a
small `provisioner "shell"` that pins a Python interpreter for Ansible) to
the image builder's Packer build file, scoped to that one image. The plugin
owns no files, roots or commands of its own: everything it produces lands
in the Packer root the image builder writes and runs when that root's
`packer build .` runs.

## What it registers

Entry point ([pyproject.toml](pyproject.toml)):

```toml
[project.entry-points."cs_image_system.plugins.modification"]
ansible_plugin = "cs_image_system.ansible_plugin.main:initialize"
```

`initialize()` ([main.py](src/cs_image_system/ansible_plugin/main.py))
returns an `AnsibleEbsTypes` metadata object (metadata version `1`, Python
`3.13`) with two service keys:

| Service key | Classes | Classification (VCT) |
|---|---|---|
| `ansible` | `AnsiblePackerModBuilderModel`, `AnsiblePackerModBuilder`, `AnsibleModItemModel` | `MOD_BUILDER_MODEL` / `MOD_BUILDER` / `MOD_BUILDER_ITEM_MODEL` |
| `ansible-playbook` | `AnsibleVersionChecker` | `VERSION_CHECKER` |

How a YAML entry selects these classes:

- A `mod_builders:` entry uses `type: ansible` (no aliases) to get an
  `AnsiblePackerModBuilderModel` and its `AnsiblePackerModBuilder`.
- A modification item under an image's `modifications:` uses `type:` to
  name a *builder*: the builder's `name`, one of its `aliases:`, `default`,
  or no `type:` at all (which means `default`, the builder with
  `is_default: true`). The builder model's
  `get_target_deferred_type_by_VCT(MOD_BUILDER_ITEM_MODEL)` returns
  `AnsibleModItemModel`, which is the class the item is loaded into.
- An `executables:` entry named `ansible-playbook` is version-checked by
  `AnsibleVersionChecker` (regex `\s+\[core\s([\d\.]+)` over
  `ansible-playbook --version`).

## Models

### `AnsibleBuilderModel` and `AnsiblePackerModBuilderModel` (`ansible`)

Defined in [ansible_models.py](src/cs_image_system/ansible_plugin/ansible_models.py).
`AnsibleBuilderModel` extends
[`ModBuilderModel`](../base/src/cs_image_system/base/models/mod_builder.py),
which adds nothing to
[`BuilderModel`](../base/src/cs_image_system/base/models/builder_model.py)
(`name`, `type`, `description`, `aliases`, `executable`, `is_default`,
`config`, `gitignore`, `tags`). `AnsiblePackerModBuilderModel` is the
registered subclass; it adds no fields.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `playbooks` | `list[str]` | `[]` | Playbook files (relative to the configuration root) copied beside the Packer root by `copy_external_assets`. They are copied only; no provisioner is emitted for them (see below). A builder with none logs a warning. |
| `extra_arguments` | `list[str]` | `[]` | Prepended to every emitted `provisioner "ansible"`'s `extra_arguments`. |
| `expect_disconnect` | `bool` | `False` | Emits `expect_disconnect = true` on every provisioner. |
| `ansible_connection` | `str \| None` | `None` | Emits `connection_type = "<value>"` when set (for example `docker`). |
| `configuration_user` | `str \| None` | `None` | Declared but not read by the emission; the provisioner's `user` comes from the runtime. |

Base fields this plugin constrains: `executable` should name the
`ansible-playbook` executable (the fixture does), though the emission does
not invoke it; Packer runs Ansible. `parameters:` is refused at load (a
base-model rule). `config:` on the builder is carried but never read.

### `AnsibleModItemModel`

Same file. Extends
[`ModItemModel`](../base/src/cs_image_system/base/models/moditem_type.py)
(`SubRootItem` -> `RootItem` -> `NameTyped`).

| Field | Type | Default | Meaning |
|---|---|---|---|
| `playbooks` | `list[str]` | `[]` | Playbook files, relative to the configuration root, run in order. One `provisioner "ansible"` per entry. An item with none logs a warning at load. |

Inherited item fields:

| Base field | From | Default | Use in this plugin |
|---|---|---|---|
| `name` | `NameTyped` | required | Names the provisioner comment and the local bundle directory (`NN-<name>`). |
| `type` | `ModItemModel` | `default` | Foreign key to a `mod_builders:` entry (see above). |
| `description`, `aliases`, `tags` | `NameTyped` / `RootItem` | | Carried; not emitted. |
| `config` | `RootItem` | `{}` | Not read by this plugin. It takes part in the lineage content hash of the modification and nothing else. |
| `_model_id` | `ModItemModel` | set at load | The owning image's global id. `identified_model` (and `builder`) therefore resolve to the *image*, not to the modification builder. |

`remap_self_with_copied_assets(copied)` rebuilds `playbooks` from
`getattr(self.identified_model, "playbooks", [])` followed by the item's own
entries, de-duplicated, replacing any path present in `copied` with its
copy. Since the identified model is the image, which has no `playbooks`
attribute, the first part contributes nothing: the item's playbooks are
exactly the ones it declares.

## The builder

`AnsiblePackerModBuilder`
([ansible_builder.py](src/cs_image_system/ansible_plugin/ansible_builder.py))
extends
[`ModBuilderBase`](../base/src/cs_image_system/base/basic/builder_base_mod.py).
A modification builder implements the three per-item hooks the image
builder calls while it writes a build file; it does not implement the
lifecycle-level hooks (`generate_items_before/during/after`,
`get_commands_to_run_*`, `pre/post_finalize_phase`), so it emits no files
of its own, runs no generation-time commands and defers nothing to a
`run-<lifecycle>.sh`.

For every modification of an instance image, the Packer image builder
calls, in order:

1. `copy_external_assets(block_dir, mod)`: copies each of the **builder
   model's** `playbooks` (resolved against the current working directory;
   a missing file raises `FileNotFoundError`, a path that contains the
   target directory raises `ValueError`) to `<block_dir>/<relative path>`
   and returns `{playbook: relative path}`. The item's own playbooks are
   not copied here.
2. `mod.remap_self_with_copied_assets(mapping)` on the item (see above).
3. `generate_items_before_modification`: returns an empty asset set.
4. `generate_items_during_modification(image, mod, image_builder, phase, build_path)`:
   for each playbook of the item, in order:
   - if the path is relative and the file exists, copies it to
     `<generation root>/<block dir>/<playbook>` so Packer finds it next to
     the HCL;
   - appends to the build file a comment
     `# Modifications for <item name> of type <item type>`;
   - a `provisioner "shell"` with `only = ["<source type>.<image>"]` whose
     single inline command creates `/usr/local/bin/csis-ansible-python`
     if absent: it tries `python3.12`, `python3.11`, `python3.9` (installing
     with `dnf` when needed), then the newest `/usr/bin/python3.N`, then
     `python3`, and symlinks the winner;
   - a `provisioner "ansible"` with `only`, `playbook_file = "<playbook>"`,
     `user = "<name>"` when the runtime declares a bake SSH user
     (`bake_ssh_username()`; the GCE runtime says `packer`, the AWS runtime
     says nothing), `extra_arguments = [<builder extra_arguments>..., "-e",
     "ansible_python_interpreter=/usr/local/bin/csis-ansible-python"]`,
     `connection_type` when `ansible_connection` is set, and
     `expect_disconnect = true` when set.
5. `generate_items_after_modification`: returns an empty asset set.

The provisioners run on the build VM when the image builder's deferred
`packer build .` executes. Separately, the Packer plugin's local
modification bundle records the item: its directory
`csis-mods/<image>/NN-<name>/` receives a copy of each playbook, a
`run.sh` that runs `ansible-playbook -i localhost, -c local '<playbook>'`
per playbook, and a `MANIFEST.yaml` with `operation: ansible` and
`idempotent: ansible`.

### A modification item with only `config:` is refused

An item that declares `config:` and no `playbooks:` has nothing to modify
with: `generate_items_during_modification` emits one provisioner per
playbook, and no code in this plugin reads `config:`, so such an item
would render nothing while lineage, the Packer plugin's local bundle and
the modification tests all recorded it as present. The item model refuses
it at load, by name ("Ansible modification 'x' declares no playbooks: it
has nothing to modify with"), so `validate`, `run` and every other
configuration load stop there
([ansible_models.py](src/cs_image_system/ansible_plugin/ansible_models.py)).
The fixture carries no such item.

The builder-level `playbooks` are a separate mechanism: they are copied
beside the Packer root (the golden block directory contains
`modify_image.yml`) but no provisioner references them, because the item
never inherits them. An item's own `playbooks` are the ones that run.

## Emission

Nothing under `generated/` belongs to this plugin alone; its output is
embedded in the Packer plugin's files. From the golden emission for
`imgfile-basic-dask` in
[pckr-ebs-ans-image-generation-block-000-build.pkr.hcl](../../tests/fixtures/v2_golden/generated/instance-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-build.pkr.hcl):

```hcl
# Modifications for dask-setup-jeffy of type ansible-default
provisioner "shell" {
  only = ["amazon-ebs.imgfile-basic-dask"]
  inline = [
    "test -x /usr/local/bin/csis-ansible-python || { ... }",
  ]
}
provisioner "ansible" {
  only = ["amazon-ebs.imgfile-basic-dask"]
  playbook_file = "setup_dask.yml"
  extra_arguments = ["-e", "ansible_python_interpreter=/usr/local/bin/csis-ansible-python"]
}
```

Files it causes to exist beside the Packer root
(`generated/instance-image/pckr-ebs-ans/image-generation/block-000/`):

| File | Origin |
|---|---|
| `setup_dask.yml`, `setup_data_science.yml` | Item playbooks, copied by `generate_items_during_modification`. |
| `modify_image.yml` | The `ansible-default` builder's playbook, copied by `copy_external_assets`; not referenced by any provisioner. |
| [csis-mods/imgfile-basic-dask/01-dask-setup-jeffy/](../../tests/fixtures/v2_golden/generated/instance-image/pckr-ebs-ans/image-generation/block-000/csis-mods/imgfile-basic-dask/01-dask-setup-jeffy/MANIFEST.yaml) `MANIFEST.yaml`, `run.sh`, `setup_dask.yml` | The local bundle entry the Packer plugin writes for this item. |

The GCE builder's root
([pckr-gce-ans/.../block-000](../../tests/fixtures/v2_golden/generated/instance-image/pckr-gce-ans/image-generation/block-000/pckr-gce-ans-image-generation-block-000-build.pkr.hcl))
carries the same provisioners with `only = ["googlecompute.imgfile-basic-dask"]`
and `user = "packer"`.

## Example configuration

The builder, from
[tests/fixtures/config/cfg/mod-builders.yml](../../tests/fixtures/config/cfg/mod-builders.yml):

```yaml
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
```

An item that selects it without a `type:` (so `default`), from
[tests/fixtures/config/images/image1.yaml](../../tests/fixtures/config/images/image1.yaml):

```yaml
images:
  - name: imgfile-data-science
    group: stofs
    aliases:
      - ds-node
    tags:
      data_science: "true"
    source_image: my-deb-11
    description: "Data Science node with pre-installed libraries and tools."
    runtimes:
      - image_builder: pckr-ebs-ans
    modifications:
      - name: data-science-setup
        playbooks:
          - setup_data_science.yml
        config:
          python_version: "3.10"
          r_version: "4.2.1"
```

The playbook path is relative to the configuration root
([tests/fixtures/config/setup_data_science.yml](../../tests/fixtures/config/setup_data_science.yml)).
For the config-only shape, see `imgfile-basic-dask-two` in
[image2.yaml](../../tests/fixtures/config/images/image2.yaml).

## Related

- Base models extended:
  [mod_builder.py](../base/src/cs_image_system/base/models/mod_builder.py),
  [moditem_type.py](../base/src/cs_image_system/base/models/moditem_type.py),
  [root_item.py](../base/src/cs_image_system/base/models/root_item.py),
  [builder_model.py](../base/src/cs_image_system/base/models/builder_model.py).
- Base builder class:
  [builder_base_mod.py](../base/src/cs_image_system/base/basic/builder_base_mod.py);
  the label helper `build_target_label_of` in
  [builder_base_image.py](../base/src/cs_image_system/base/basic/builder_base_image.py).
- The image builder that calls it and hosts its output:
  [packer-plugin](../packer-plugin)
  ([packer_ebs_builder.py](../packer-plugin/src/cs_image_system/packer_plugin/packer_ebs_builder.py),
  [v2_local_mods.py](../packer-plugin/src/cs_image_system/packer_plugin/v2_local_mods.py)).
- Lineage records for modifications:
  [lineage.py](../base/src/cs_image_system/base/lineage.py) (`mod_records`).
- No terraform modules and no hashicorp-utils usage: the plugin writes
  Packer provisioner lines directly.
