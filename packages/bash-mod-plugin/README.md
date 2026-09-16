# cs-image-system-bash-mod-plugin

The shell modification plugin. It registers one modification builder,
`bash-remote`, and the modification item model that goes with it. A
modification item under an image's `modifications:` carries inline shell
lines (`script`), script files (`scripts`) and/or a declarative, idempotent
form (`ensure`); the builder turns them into `provisioner "shell"` blocks in
the image builder's Packer build file, scoped to that one image. The plugin
owns no files, roots or commands of its own: everything it produces lands in
the Packer root the image builder writes and runs when that root's
`packer build .` runs.

## What it registers

Entry point ([pyproject.toml](pyproject.toml)):

```toml
[project.entry-points."cs_image_system.plugins.modification"]
bash_plugin = "cs_image_system.bash_mod_plugin.main:initialize"
```

`initialize()` ([main.py](src/cs_image_system/bash_mod_plugin/main.py))
returns a `BashModTypes` metadata object (metadata version `1`, Python
`3.13`) with two service keys:

| Service key | Classes | Classification (VCT) |
|---|---|---|
| `bash-remote` | `BashModBuilderModel`, `BashModBuilder`, `BashModItemModel` | `MOD_BUILDER_MODEL` / `MOD_BUILDER` / `MOD_BUILDER_ITEM_MODEL` |
| `bash` | `BashVersionChecker` | `VERSION_CHECKER` |

How a YAML entry selects these classes:

- A `mod_builders:` entry uses `type: bash-remote` (no aliases on the
  type key) to get a `BashModBuilderModel` and its `BashModBuilder`.
- A modification item under an image's `modifications:` uses `type:` to
  name a *builder*: the builder's `name`, one of its `aliases:`, or
  `default`. The fixture's builder is itself named `bash-remote` with the
  alias `bash`, so `type: bash-remote` and `type: bash` on an item both
  reach it. The builder model's
  `get_target_deferred_type_by_VCT(MOD_BUILDER_ITEM_MODEL)` returns
  `BashModItemModel`, the class the item is loaded into.
- An `executables:` entry named `bash` is version-checked by
  `BashVersionChecker` (regex `.*version\s+([\d\.]+)` over
  `bash --version`).

## Models

### `BashBuilderModel` and `BashModBuilderModel` (`bash-remote`)

Defined in [bash_models.py](src/cs_image_system/bash_mod_plugin/bash_models.py).
`BashBuilderModel` extends
[`ModBuilderModel`](../base/src/cs_image_system/base/models/mod_builder.py),
which adds nothing to
[`BuilderModel`](../base/src/cs_image_system/base/models/builder_model.py)
(`name`, `type`, `description`, `aliases`, `executable`, `is_default`,
`config`, `gitignore`, `tags`). `BashModBuilderModel` is the registered
subclass; it adds no fields.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `execute_command` | `str \| None` | `None` | Emitted as `execute_command = "..."` on every shell provisioner of every item (Packer's command template, for example `sudo -E bash '{{.Path}}'`). |
| `environment_vars` | `list[str]` | `[]` | Emitted as `environment_vars = [...]` on every shell provisioner. |
| `expect_disconnect` | `bool` | `False` | Emits `expect_disconnect = true` on every shell provisioner. |
| `extra_arguments` | `list[str]` | `[]` | Declared but not read by the emission. |
| `configuration_user` | `str \| None` | `None` | Declared but not read by the emission. |

Base fields this plugin constrains: `executable` should name the `bash`
executable (the fixture does), though the emission does not invoke it;
Packer runs the shell on the build VM. `parameters:` is refused at load (a
base-model rule). `config:` on the builder is carried but never read.

### `BashModItemModel`

Same file. Extends
[`ModItemModel`](../base/src/cs_image_system/base/models/moditem_type.py)
(`SubRootItem` -> `RootItem` -> `NameTyped`).

| Field | Type | Default | Meaning |
|---|---|---|---|
| `script` | `list[str]` | `[]` | Inline command lines, run in order in one `provisioner "shell"` (`inline = [...]`). Literal shell; no templating. Blank entries are dropped. |
| `scripts` | `list[str]` | `[]` | Script files, relative to the configuration root, copied beside the Packer root and run as `scripts = [...]`. Blank entries are dropped. |
| `ensure` | `dict[str, Any]` | `{}` | The declarative form. Allowed keys: `packages` (list of names), `files` (list of `{path, content, mode}`; `mode` defaults to `0644`), `services` (list of unit names, enabled and started), `commands` (list of `{run, unless}`; `run` executes only when `unless` fails). Any other key raises `ValueError` at load. |

Validation at load: at least one of `script`, `scripts`, `ensure` must be
non-empty, otherwise `ValueError` ("must supply 'script' (inline lines),
'scripts' (script files) and/or 'ensure' (declarative, idempotent)").

Derived behaviour:

- `idempotent`: `declared` when only `ensure` is given, `unknown`
  otherwise. This is what the lineage record and the local bundle's
  `MANIFEST.yaml` report.
- `ensure_lines()`: guarded shell for the declarative form, so re-running
  is a no-op. Packages: `rpm -q` or `dpkg -s` first, install via `dnf`,
  `yum` or `apt-get` only when missing. Files: content is base64-embedded,
  decoded to a temp file, and `install -m <mode>` runs only when `cmp`
  says the target differs. Services: `systemctl enable` / `start` only when
  not already enabled / active. Commands: `( <unless> ) || { <run>; }`, or
  the bare `run` when there is no `unless`.
- `remap_self_with_copied_assets(copied)`: replaces each `scripts` entry
  with its copied path when present in the mapping.

Inherited item fields:

| Base field | From | Default | Use in this plugin |
|---|---|---|---|
| `name` | `NameTyped` | required | Names the provisioner comment and the local bundle directory (`NN-<name>`). |
| `type` | `ModItemModel` | `default` | Foreign key to a `mod_builders:` entry (see above). |
| `description`, `aliases`, `tags` | `NameTyped` / `RootItem` | | Carried; not emitted. |
| `config` | `RootItem` | `{}` | Not read by this plugin. It takes part in the lineage content hash of the modification and nothing else. |
| `_model_id` | `ModItemModel` | set at load | The owning image's global id; `identified_model` resolves to the image. |

### A modification item with only `config:`

An item that declares `config:` and none of `script`, `scripts`, `ensure`
does not load: `BashModItemModel.__post_init__` raises the `ValueError`
above, so the configuration fails at load and nothing is generated. `config:`
alone is never a modification; nothing in this plugin reads it.

## The builder

`BashModBuilder`
([bash_builder.py](src/cs_image_system/bash_mod_plugin/bash_builder.py))
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

1. `copy_external_assets(block_dir, mod)`: copies each of the **item's**
   `scripts` (relative to the current working directory; a missing file
   raises `FileNotFoundError`; an absolute path is left in place) to
   `<block_dir>/<script path>` and returns `{script: script path}`.
2. `mod.remap_self_with_copied_assets(mapping)` on the item.
3. `generate_items_before_modification`: returns an empty asset set.
4. `generate_items_during_modification(image, mod, image_builder, phase, build_path)`:
   - `inline` = `ensure_lines()` followed by the `script` lines; `scripts`
     = the script files. When both lists are empty (an `ensure` whose
     lists are all empty), it logs a warning and emits nothing.
   - Appends `# Modifications for <item name> of type <item type> (shell)`.
   - Then, because Packer's shell provisioner takes either `scripts` or
     `inline` but never both, one or two `provisioner "shell"` blocks:
     first `scripts = ["..."]` when there are script files, then
     `inline = [ "...", ]` when there are inline lines. Each block carries
     `only = ["<source type>.<image>"]` and, when set on the builder model,
     `execute_command`, `environment_vars` and `expect_disconnect = true`.
   - Every string is rendered as an HCL literal: backslashes and double
     quotes are escaped, and `${` / `%{` become `$${` / `%%{` so shell text
     such as `dpkg-query -f='${Package}'` survives Packer's template parser.
5. `generate_items_after_modification`: returns an empty asset set.

The provisioners run on the build VM when the image builder's deferred
`packer build .` executes. Separately, the Packer plugin's local
modification bundle records the item: its directory
`csis-mods/<image>/NN-<name>/` receives a copy of each script file, an
`inline.sh` holding the `script` lines (with `set -eu`), a `run.sh` that
runs `sh '<script>'` per script file and then `sh ./inline.sh`, and a
`MANIFEST.yaml` with `operation: bash` and the item's `idempotent` value.
`ensure` lines are not part of the bundle.

## Emission

Nothing under `generated/` belongs to this plugin alone; its output is
embedded in the Packer plugin's files. From the golden emission for the
`derivative-setup` item of `imgfile-basic-dask` in
[pckr-ebs-ans-image-generation-block-000-build.pkr.hcl](../../tests/fixtures/v2_golden/generated/instance-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-build.pkr.hcl):

```hcl
# Modifications for derivative-setup of type bash-remote (shell)
provisioner "shell" {
  only = ["amazon-ebs.imgfile-basic-dask"]
  scripts = ["mod_image.sh"]
}
provisioner "shell" {
  only = ["amazon-ebs.imgfile-basic-dask"]
  inline = [
    "for p in git; do rpm -q \"$p\" >/dev/null 2>&1 || dpkg -s \"$p\" >/dev/null 2>&1 || { ... }; done",
    "printf '%s' 'dmVyc2lvbj0xLjAuMAo=' | base64 -d > /tmp/.csis-ensure && ( sudo cmp -s /tmp/.csis-ensure '/etc/derivative.conf' || sudo install -m 0644 /tmp/.csis-ensure '/etc/derivative.conf' ) && rm -f /tmp/.csis-ensure",
    "( test -d /opt/derivative/data ) >/dev/null 2>&1 || { sudo mkdir -p /opt/derivative/data; }",
    "echo 'derivative setup'",
    "sudo mkdir -p /opt/derivative && echo 1.0.0 | sudo tee /opt/derivative/VERSION",
  ]
}
```

The three `ensure` lines (package, file, command) come first, then the two
`script` lines. Files it causes to exist beside the Packer root
(`generated/instance-image/pckr-ebs-ans/image-generation/block-000/`):

| File | Origin |
|---|---|
| `mod_image.sh` | The item's script file, copied by `copy_external_assets`. |
| [csis-mods/imgfile-basic-dask/02-derivative-setup/](../../tests/fixtures/v2_golden/generated/instance-image/pckr-ebs-ans/image-generation/block-000/csis-mods/imgfile-basic-dask/02-derivative-setup/MANIFEST.yaml) `MANIFEST.yaml`, `run.sh`, `inline.sh`, `mod_image.sh` | The local bundle entry the Packer plugin writes for this item (`operation: bash`, `idempotent: unknown`, `files: [mod_image.sh, inline.sh]`). |

The GCE builder's root
([pckr-gce-ans/.../block-000](../../tests/fixtures/v2_golden/generated/instance-image/pckr-gce-ans/image-generation/block-000/pckr-gce-ans-image-generation-block-000-build.pkr.hcl))
carries the same two blocks with `only = ["googlecompute.imgfile-basic-dask"]`.

## Example configuration

The builder, from
[tests/fixtures/config/cfg/mod-builders.yml](../../tests/fixtures/config/cfg/mod-builders.yml):

```yaml
mod_builders:
  - name: bash-remote
    aliases:
      - bash
    is_default: false
    type: bash-remote
    executable: bash
    config:
      some_unknown_mod_builder_setting: "{{ ENV.USER }} and some_value"
```

The item that uses it, from
[tests/fixtures/config/images/image1.yaml](../../tests/fixtures/config/images/image1.yaml)
(the enclosing image is `imgfile-basic-dask`; comments removed):

```yaml
    modifications:
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

The script path is relative to the configuration root
([tests/fixtures/config/mod_image.sh](../../tests/fixtures/config/mod_image.sh)).

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
- Tests: [tests/test_bash_provisioner.py](tests/test_bash_provisioner.py)
  -- two blocks for files plus inline, builder options, script copying.
- No terraform modules and no hashicorp-utils usage: the plugin writes
  Packer provisioner lines directly.
