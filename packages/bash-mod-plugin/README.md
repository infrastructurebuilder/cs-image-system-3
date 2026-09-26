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
  `default`. The orchestrator
  ([orchestrator.py](../base/src/cs_image_system/base/orchestrator.py))
  looks the builder up by name or alias, reads the builder's own `type`
  (`bash-remote`) and loads the item into the class registered under that
  service key for `MOD_BUILDER_ITEM_MODEL`: `BashModItemModel`. The
  registry alone decides; the builder model's
  `get_target_deferred_type_by_VCT` method, which also named that class
  and had no caller, is gone (stage 63, 2026-09-25), as is the plugin's
  empty `helpers.py`.
- **The item's `type` is rewritten to the builder's `name` at load**
  (stage 63 item 15). The image builder later fetches the builder with
  `ctx.mod_builders.get(mod.get_type())`, a map keyed by builder NAME
  only, so an alias must not survive the load. An item declared
  `type: bash` (the fixture builder's alias) is loaded as
  `type: bash-remote`. Before 2026-09-25 the alias was kept, and
  generation stopped with
  `AssertionError: No mod builder bash found in context for <image>`.
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
| `execute_command` | `str \| None` | `None` | Emitted as `execute_command = "..."` on every shell provisioner of every item (Packer's command template, for example `sudo -E bash '{{.Path}}'`). The way to change how the script is invoked. May not be declared together with `configuration_user`. |
| `configuration_user` | `str \| None` | `None` | When set, every shell provisioner of this builder gets `execute_command = "chmod +x {{ .Path }}; sudo su - <user> -c '{{ .Vars }} {{ .Path }}'"`, so each item's lines run as that user; the bake user only launches them (stage 63; declared and not read until 2026-09-25). Declaring it together with `execute_command` is refused at load. |
| `environment_vars` | `list[str]` | `[]` | Emitted as `environment_vars = [...]` on every shell provisioner. |
| `expect_disconnect` | `bool` | `False` | Emits `expect_disconnect = true` on every shell provisioner. |

`extra_arguments` is not a field (stage 63): it was declared and never
read, so it is removed, and a builder that still declares it fails to load
with the unknown-key refusal. Use `execute_command` to change the
invocation.

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
| `scripts` | `list[str]` | `[]` | Script files, relative to the configuration root (the process's working directory, which the configuration load sets to the root), copied beside the Packer root and run as `scripts = [...]`. Blank entries are dropped. |
| `ensure` | `dict[str, Any]` | `{}` | The declarative form. Allowed keys: `packages` (list of names), `files` (list of `{path, content, mode}`; `mode` defaults to `0644`), `services` (list of unit names, enabled and started), `commands` (list of `{run, unless}`; `run` executes only when `unless` fails). Every entry is validated at load by `validate_ensure` (stage 63 item 16): a wrong shape, an unknown key, a bad mode or an all-empty mapping raises `ValueError` naming the item and the entry. |

Validation at load: at least one of `script`, `scripts`, `ensure` must be
non-empty, otherwise `ValueError` ("must supply 'script' (inline lines),
'scripts' (script files) and/or 'ensure' (declarative, idempotent)").

Derived behaviour:

- `idempotent`: `declared` when only `ensure` is given, `unknown`
  otherwise. This is what the lineage record and the local bundle's
  `MANIFEST.yaml` report.
- `ensure_lines()`: guarded shell for the declarative form, so re-running
  is a no-op. Packages: `rpm -q` or `dpkg -s` first; only when missing,
  install with the FIRST of `dnf`, `yum`, `apt-get` that exists on the
  host, and stop the bake if that one fails (the others are never tried).
  With none of the three, the line says so and fails. Files: content is base64-embedded,
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
   `scripts` to `<block_dir>/<script path>` and returns
   `{script: script path}`. The source is resolved against the process's
   current working directory; the configuration load has already changed
   directory to the configuration root (`--root-dir`, else
   `working_directory` in `cfg/_config.yml`, else `.`), so in practice the
   path is root-relative. A missing file raises `FileNotFoundError`; an
   absolute path is not copied and is left in place.
2. `mod.remap_self_with_copied_assets(mapping)` on the item. Because the
   mapping's value is the same relative path the copy was placed at, the
   item's `scripts` entries keep their text; the emitted `scripts = [...]`
   is relative to the Packer root, where the copy now lies.
3. `generate_items_before_modification`: returns an empty asset set.
4. `generate_items_during_modification(image, mod, image_builder, phase, build_path)`:
   - `inline` = `ensure_lines()` followed by the `script` lines; `scripts`
     = the script files. When both lists are empty it logs a warning and
     emits nothing; since stage 63 item 16 an all-empty `ensure` is
     refused at load, so an item can no longer reach this.
   - Appends `# Modifications for <item name> of type <item type> (shell)`.
   - Then, because Packer's shell provisioner takes either `scripts` or
     `inline` but never both, one or two `provisioner "shell"` blocks:
     first `scripts = ["..."]` when there are script files, then
     `inline = [ "...", ]` when there are inline lines. Each block carries
     `only = ["<source type>.<image>"]` and, when set on the builder model,
     `execute_command`, `environment_vars` and `expect_disconnect = true`.
     The `execute_command` written is the model's
     `effective_execute_command()`: the declared `execute_command`, else,
     with a `configuration_user`, `chmod +x {{ .Path }}; sudo su - <user>
     -c '{{ .Vars }} {{ .Path }}'` (Packer's `{{ .Vars }}`, the
     environment variables, travel inside the command because `su -`
     starts a fresh login environment), else none (stage 63).
   - Every string is rendered as an HCL literal: backslashes and double
     quotes are escaped, and `${` / `%{` become `$${` / `%%{` so shell text
     such as `dpkg-query -f='${Package}'` survives Packer's template parser.
5. `generate_items_after_modification`: returns an empty asset set.

The provisioners run on the build VM when the image builder's deferred
`packer build .` executes. Separately, the Packer plugin's local
modification bundle records the item: its directory
`csis-mods/<image>/NN-<name>/` receives a copy of each script file, an
`inline.sh` holding the item's guarded `ensure` lines followed by its
`script` lines (with `set -eu`; the same order the bake runs them), a
`run.sh` that runs `sh '<script>'` per script file and then
`sh ./inline.sh`, and a `MANIFEST.yaml` with `operation: bash` and the
item's `idempotent` value. `csis-mods rerun` on the image therefore
re-applies the declarative `ensure` form too (stage 63). Until 2026-09-25
the `ensure` lines were not in the bundle and a rerun replayed only the
script files and the `script` lines.

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
    "for p in git; do rpm -q \"$p\" >/dev/null 2>&1 || dpkg -s \"$p\" >/dev/null 2>&1 || if command -v dnf >/dev/null 2>&1; then ... fi || exit 1; done",
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
Note the quoted `mode: "0644"`. An unquoted `0644` also works: YAML reads
it as the integer 420, and the loader renders an integer back in octal
(`install -m 0644`). What does NOT work is an unquoted `644` without the
leading zero: YAML reads the decimal number 644, which is no mode a file
should have, and the loader refuses any integer above `0777` and asks for
quotes. Quoting is the habit that never needs the rule.

## Prerequisites and integration

Nothing beyond the core on the operator's machine, with one declaration the
core demands and two facts about where the shell actually runs.

**The `bash` executable entry.** The builder's `executable:` must name an
entry in `cfg/executables.yml`
([the fixture's](../../tests/fixtures/config/cfg/executables.yml) is
`name: bash`, `binary: /usr/local/bin/bash`, no `version`), because
`validate` checks every builder's `executable` against that list and every
run checks every declared entry (stage 48: the binary must exist as an
absolute path or a name on `PATH`, `BashVersionChecker` must parse a version
from `<binary> --version`, and when the entry declares `version:` the parsed
version must satisfy it). That is the whole extent of the plugin's use of a
local bash: it is looked at, never run. The fixture declares no floor;
`GNU bash, version 3.2.57` (macOS `/bin/bash`) and `5.3.15` both parse.

**The build VM.** The provisioners execute on the machine Packer boots for
the bake, reached the way the image builder's source reaches it (ssh over
Session Manager on AWS, IAP on GCE; see [packer-plugin](../packer-plugin)).
This plugin holds no credentials and opens no connection of its own. On that
VM it assumes:

- a POSIX `sh` for the inline lines (Packer's shell provisioner runs them
  through its `inline_shebang`, `/bin/sh -e` unless `execute_command` or the
  Packer defaults are changed) and whatever interpreter each script file's
  own shebang names;
- with `configuration_user` set, that user must exist on the VM, and the
  bake's ssh user must be able to `sudo su - <user>` without a password;
- passwordless `sudo` for the bake's ssh user: every `ensure` line that
  changes the system runs it through `sudo`;
- for `ensure.packages`: `rpm` or `dpkg` to query, and `dnf`, `yum` or
  `apt-get` to install, plus network reach to the image's package
  repositories when something is missing;
- for `ensure.files`: `base64`, `cmp` (diffutils) and `install`
  (coreutils);
- for `ensure.services`: `systemctl`.

**The modification tests.** `just test-mods` applies the same item twice in
a throwaway container on the operator's machine
([mod_tests.py](../base/src/cs_image_system/base/mod_tests.py)); it needs
`docker` on `PATH` and a daemon that answers `docker info`, no cloud
session. The container gets a `sudo` shim when it has none, so the `sudo`
in `ensure` lines works there too.

**How the plugin finds things.** The builder by the item's `type:` (the
builder's name); the item class by the builder's `type: bash-remote`; the
`bash` entry by the builder's `executable:`; script files by path relative
to the configuration root (the working directory the load selects from
`--root-dir`, else `cfg/_config.yml`'s `working_directory`, else `.`); the
build VM through the image builder that hosts the emission. No environment
variable, profile or file of its own.

## Configuration reference

### The builder (`cfg/mod-builders.yml`, `type: bash-remote`)

Every key the model accepts. An unknown key is refused at load
(`extra="forbid"` in the shared model config), and `parameters:` is refused
by name (retired in stage 26).

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | The builder's name; what an item's `type:` must say. Characters `/` and `\` are refused; `default` is refused as a name. |
| `type` | str | required | `bash-remote`. Selects this plugin's model and builder. |
| `description` | str or null | `null` | Free text. Accepted, not read. |
| `aliases` | list[str] | `[]` | Extra names an item's `type:` may use; the loader rewrites them to the builder's `name`. |
| `executable` | str or null | `null` | Must name an `executables:` entry (the fixture: `bash`), or `validate` fails. Never invoked by this plugin. |
| `is_default` | bool | `false` | Makes this the builder an item with `type: default` (or no `type`) resolves to. |
| `config` | mapping | `{}` | Accepted, not read. |
| `gitignore` | list[str] | `[]` | Accepted by the base model; nothing in this plugin reads it. |
| `tags` | mapping | `{}` | Accepted, not read. |
| `execute_command` | str or null | `null` | Emitted verbatim (HCL-escaped) as `execute_command` on every shell block of every item of this builder. Refused together with `configuration_user`. |
| `configuration_user` | str or null | `null` | Read since stage 63 (accepted and ignored until 2026-09-25): every shell block of this builder runs its lines as this user through `execute_command = "chmod +x {{ .Path }}; sudo su - <user> -c '{{ .Vars }} {{ .Path }}'"`. Refused together with `execute_command` (`... both say how the script runs; declare one`). |
| `environment_vars` | list[str] | `[]` | Emitted as `environment_vars = [...]` on every shell block. |
| `expect_disconnect` | bool | `false` | When true, `expect_disconnect = true` on every shell block. |
| `extra_arguments` | | | Refused at load as an unknown key (removed in stage 63; it was accepted and never read). Use `execute_command`. |

### The item (an image's `modifications:` entry whose `type:` names this builder)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | Unique within the image. Names the comment line, the bundle directory `NN-<name>` and the lineage record. |
| `type` | str | `default` | The builder's name, an alias, or `default` (or omitted). Rewritten to the builder's name at load (stage 63 item 15). Omitted or `default` with no `is_default: true` mod builder: refused at load (stage 63). |
| `description` | str or null | `null` | Accepted, not read. |
| `aliases` | list[str] | `[]` | Accepted, not read. |
| `tags` | mapping | `{}` | Accepted, not read. |
| `config` | mapping | `{}` | Not read by the plugin. Part of the modification's content hash, so a change re-bakes the image. Not passed to the shell. |
| `script` | list[str] | `[]` | Inline lines, literal, in order, after the `ensure` lines. Blank and whitespace-only entries are dropped. |
| `scripts` | list[str] | `[]` | Script files; each is copied beside the Packer root and run first, in order. Blank entries are dropped. An absolute path is not copied and is emitted as is. |
| `ensure` | mapping | `{}` | Only the four keys below are allowed; any other key is refused at load. Every entry's values are validated at load since stage 63 item 16 (`validate_ensure`; see "What it tests and verifies"). |

The `ensure` keys:

| Key | Type | Default | Meaning |
|---|---|---|---|
| `packages` | list[str] | `[]` | One `for` line: each name is queried with `rpm -q` then `dpkg -s`; only when both fail, installed with `dnf -y`, else `yum -y`, else `apt-get install -y`, under `sudo`. |
| `files` | list of mappings | `[]` | One line per entry: `path` (required), `content` (default empty), `mode` (default `0644`, quote it). Content is base64-embedded in the build file, decoded to `/tmp/.csis-ensure` and installed with `sudo install -m <mode>` only when `sudo cmp -s` says the target differs. |
| `services` | list[str] | `[]` | Two lines per unit: `sudo systemctl enable` unless already enabled, `sudo systemctl start` unless already active. |
| `commands` | list of mappings | `[]` | One line per entry: `run` (required) and optional `unless`. With `unless`: `( <unless> ) >/dev/null 2>&1 \|\| { <run>; }`. Without: the bare `run`, every time. |

### Variations

- **`script` only** is one `provisioner "shell"` with `inline`. **`scripts`
  only** is one block with `scripts`. **Both** are two blocks, the files
  first, because Packer refuses both arguments in one provisioner.
- **`ensure` only** is recorded as `idempotent: declared` (lineage and the
  bundle manifest); **`ensure` with `script` or `scripts`** is
  `idempotent: unknown`, the same as free-form alone. `ensure` lines always
  precede the `script` lines in the inline block.
- **`ensure` whose lists are all empty** (`ensure: {packages: []}`) is
  refused at load (stage 63 item 16). Before 2026-09-25 it passed load,
  counted as `declared`, and emitted nothing: the builder logged
  `Bash modification <name> has no script lines or files; nothing emitted`
  and the bake proceeded without a provisioner for it. The bundle directory
  still exists, with a `run.sh` that runs nothing.
- **`commands` with `unless`** is guarded; **without `unless`** the command
  runs on every bake and on every `csis-mods rerun`, so the item is
  idempotent only if the command is.
- **A relative script path** is copied to the same relative path beside the
  Packer root and emitted relative; **an absolute path** is emitted
  absolute and Packer reads it from the operator's machine at build time.
- **`execute_command` set** puts that template on every block of every
  item of the builder; **`configuration_user` set** instead puts
  `chmod +x {{ .Path }}; sudo su - <user> -c '{{ .Vars }} {{ .Path }}'`
  there, so the lines run as that user (stage 63); **both set** is refused
  at load; **neither**, Packer's default applies and the lines run as the
  bake user. The same for
  `environment_vars` (emitted only when non-empty) and `expect_disconnect`
  (emitted only when true).
- **`type: <builder name>`** reaches this plugin. **`type: default` or no
  `type`** reaches whichever mod builder is `is_default: true`; in the
  fixture that is `ansible-default`, so the item is loaded as an ANSIBLE
  item and its `script`/`scripts`/`ensure` keys are refused as unknown.
  With no `is_default: true` mod builder at all, the load is refused
  (stage 63): `No default builder found in mod_builder list.` first, and
  the orchestrator's `` modification '<name>' names no builder (`type`) ... ``
  for an item that reaches it anyway. Until 2026-09-25 such an item
  became an `AttributeError` at generation.
  **`type: <alias>`** behaves exactly as the builder's name: the loader
  rewrites it.
- **AWS versus GCE runtime**: the lines are identical; only the `only`
  label differs (`amazon-ebs.<image>` versus `googlecompute.<image>`), and
  the same blocks land in every image builder's root the image bakes on.
- **Dry run versus real run**: generation is the same, so the build file,
  the copied scripts and the bundle appear under `generated/` either way.
  A dry run never runs `packer build`, so nothing executes on a VM and no
  lineage record is written. `--no-apply` generates and skips
  finalization too.
- **Base image versus instance image**: a base image's `modifications:`
  are ignored with a warning by the image builder; only instance images
  reach this plugin.
- **Bake versus `test-mods`**: in the bake, the inline lines run under
  Packer's `/bin/sh -e` on the VM; under `test-mods` the same lines (ensure
  lines included) are written to an `inline.sh` with `set -eu` and run with
  `sh` inside the container, after each script file, as root behind a
  `sudo` shim. A line that passes in one and fails in the other usually
  differs on `sudo`, on `$HOME`, or on a package repository the container
  cannot reach.

## What it tests and verifies

**At load** (pydantic validators and `__post_init__`, before any command
does anything). Unknown keys on the builder or the item; `parameters:` on
the builder; `/` or `\` in a name or alias; `ensure` keys outside
`packages`, `files`, `services`, `commands`; every `ensure` entry's shape
(`packages`/`services` a list of non-empty names, `files` entries with a
`path` and only `path`/`content`/`mode`, `commands` entries with a `run`
and only `run`/`unless`, a mode of three or four octal digits, an
integer mode no higher than `0777`, and not every kind empty); an item
with none of `script`, `scripts`, `ensure`; an item `type:` that names no
builder; an item with no `type:` when no mod builder is the default; a
builder declaring both `configuration_user` and `execute_command`, or
the removed `extra_arguments` (stage 63). Each is a
`ValueError` (or `KeyError` for the type) that stops the load; the CLI
prints it and exits 1. Nothing loads, so nothing is generated.

**At `validate`** ([validate.py](../base/src/cs_image_system/base/commands/validate.py)).
The builder's `executable:` must name an `executables:` entry; the `bash`
entry's binary must exist, its version must parse and, when declared, meet
the requirement. Every failure is collected by name and printed; `validate`
exits 1 and `run` refuses before generation. One INFO line lists every
checked tool and the version found (`bash 5.3.15 (no requirement)` for the
fixture).

**At generation.** Two checks, both fatal to the run: a `scripts` entry
that is not a file (`FileNotFoundError`), and the assertion that the item's
`type` is a builder name. Neither is a validation error; the run summary
reports `ok: false` with an empty validation list and the traceback is in
the run log. The plugin does not validate the HCL it writes; the Packer
plugin's run-now commands (`packer fmt`, `init`, `validate`) do, and a
malformed block fails there before any bake. An empty emission is a WARNING
line, not a failure.

**At apply.** Nothing by this plugin. Packer runs the blocks in order; the
inline lines run under `-e`, so the first failing line aborts the
provisioner and the build, no image is produced and no lineage record is
written. The `ensure` lines are the only ones the plugin vouches for as
safe to re-run.

**After apply.** The Packer plugin's post-finalize hook records every
modification of the built image in `meta-state/lineage.yaml`
([lineage.py](../base/src/cs_image_system/base/lineage.py) `mod_records`):
`operation: bash`, `idempotent` (`declared` or `unknown`), and a
`content_hash` over the item's type, `config`, `script` lines, the CONTENT
of each script file and the `ensure` mapping. That hash feeds the image's
`input_fingerprint`, which is what makes an edited modification re-bake the
image on the next run. The on-image bundle under `/opt/csis/mods/` carries
the same record.

**In `test-mods`** ([mod_tests.py](../base/src/cs_image_system/base/mod_tests.py)).
The item is applied twice in a container of the image's OS family. Run one
must exit 0; run two must exit 0 and change no file outside the volatile
paths (`docker diff`). The verdict lands in the live configuration's
`meta-state/mod-tests.yaml`, keyed by the content hash, as
`status: pass|fail|skipped|unsupported` and `idempotent: true|false`; a
failure prints `FAIL <image>/<mod>: rc=...` on stderr and exits 1. A
`release` of a build whose recorded modification has `fail` or
`idempotent: false` is refused; a missing record is tolerated unless
`config.require_mod_tests` is true.

**In the state query.** Nothing. The plugin owns no provider resource, so
`state query` has nothing of its to diff.

## When it fails

Failures that have happened, in date order:

- **2026-08-27, three defects found in the pre-V2 builder**
  ([LEDGER](../../docs/history/LEDGER.md), "Finding 2026-08-27"). Every
  item resolved to the default mod builder (the lookup used the field name
  `modifications`, not the item's `type`), so a bash item was recorded as
  `ansible-default` with no content; the bash builder wrote raw lines and an
  `exit 0` straight into the build file, so any real bash item failed
  `packer validate`; and `scripts:` was not a field, so files were dropped.
  Fixed at gate 8; guarded by
  [test_v2_gate8_modifications.py](../../tests/test_v2_gate8_modifications.py)
  and [tests/test_bash_provisioner.py](tests/test_bash_provisioner.py). If
  a comment line ever appears outside a `provisioner "shell" {` block, or
  `exit 0` appears in a build file, this regressed.
- **2026-09-10, the first `full-test`'s mod-test leg could not start a
  container** for an EL 10 image: Docker Hub's `rockylinux` library stops at
  9. The stand-in for `rhel` 10 and above is `almalinux:<version>` since
  (`test_image_for` in [mod_tests.py](../base/src/cs_image_system/base/mod_tests.py)).
  Symptom then: `docker run` failed to pull and the bash item's test never
  ran. If `test-mods` reports `unsupported` with
  `no local test image for the root OS family`, the family/version has no
  stand-in; set `local_test_image` on the OS builder.
- **Found live, undated, in the sibling shell emitter for image tests**
  ([v2_provisioners.py](../packer-plugin/src/cs_image_system/packer_plugin/v2_provisioners.py)):
  an `rpm --qf '%{NAME}'` line broke `packer fmt`, because `%{` and `${`
  open Packer template directives. This plugin's `_hcl_string` escapes both
  the same way. If `packer fmt` or `validate` ever reports
  `Invalid template directive` or `Invalid template interpolation` on a
  line you wrote, the escape regressed; the line in `generated/` should
  read `%%{` / `$${`.
- **2026-09-20, an assertion that could not fail** (image `tests:`, not this
  plugin, but the same shell and the same trap;
  [OPERATIONS.md](../../docs/OPERATIONS.md), "What a green bake proves").
  Under `sh -e`, a command inside an AND-OR list other than the last does
  not abort the script, so a `script:` line written `check || { echo no; }`
  never fails the build however false `check` is. Two bakes went green
  asserting a package that did not exist. If a `script` line must be able
  to stop the bake, end it in something that exits nonzero (`|| exit 1`),
  not in a braced group that returns 0. The plugin's own `commands` form,
  `( unless ) || { run; }`, is deliberate: the group is the LAST element,
  so a failing `run` does abort.
- **2026-09-23, an item declared with the builder's alias failed at
  generation** (found while writing this README, on a copy of the fixture
  with `type: bash` on `derivative-setup`). Load and `validate` passed; the
  run log then showed
  `AssertionError: No mod builder bash found in context for imgfile-basic-dask`
  and the summary was `ok: false` with no validation errors. Fixed by
  stage 63 item 15 (2026-09-25): the loader rewrites the alias to the
  builder's name, and `tests/test_v2_defects_loading.py` generates that
  same fixture copy.

Failures the code raises that have not been seen outside tests:

| What you see | Where | Meaning and what to do |
|---|---|---|
| `Bash modification '<name>' must supply 'script' (inline lines), 'scripts' (script files) and/or 'ensure' (declarative, idempotent)` | load; CLI exit 1 | The item has none of the three (a `config:`-only item). Add one or remove the item. |
| `Bash modification '<name>': unknown ensure keys ['users']` | load; CLI exit 1 | Only `packages`, `files`, `services`, `commands` exist. Move anything else to `commands`. |
| A pydantic error naming a key (`Extra inputs are not permitted`) on the builder or the item | load; CLI exit 1 | A misspelt or foreign key (`playbooks:` on a bash item, `script:` on an ansible item). Check the item's `type:` reaches the builder you meant; `type: default` reaches the default builder, which in the fixture is ansible. |
| ``<builder>: `parameters` was retired (stage 26) ...`` | load; CLI exit 1 | Delete `parameters:` from the builder. |
| `KeyError: Could not resolve builder '<type>' referenced in Image(...)` | load; CLI exit 1 | The item's `type:` names no `mod_builders:` entry. |
| `` mod builder '<name>': `configuration_user` and `execute_command` both say how the script runs; declare one `` | load; CLI exit 1 | Stage 63. `configuration_user` writes its own `execute_command`; keep one. To run as another user with a custom command, put the `sudo su - <user>` in your `execute_command`. |
| A pydantic unknown-key error naming `extra_arguments` on a `bash-remote` builder | load; CLI exit 1 | Stage 63 removed the field (it was never read). Delete it; change the invocation with `execute_command`. |
| `No default builder found in mod_builder list.` | load; CLI exit 1 | No mod builder says `is_default: true`. Mark one, or give every item a `type:`. The orchestrator's own form, for an item that reaches it, is `` modification '<name>' names no builder (`type`) and no mod builder is `is_default: true`; name one with `type:` or mark a default `` (stage 63; it used to be an `AttributeError` at generation). |
| `Executable bash specified for provider bash-remote not found in executables list.` | `validate`; exit 1 | Add a `bash` entry to `cfg/executables.yml` or change the builder's `executable:`. |
| `bash: binary '/usr/local/bin/bash' not found (declared in cfg/executables.yml; an absolute path, or a name on PATH)` | `validate` and every run; exit 1 | The pinned path is wrong on this machine. Symlink the binary there or fix `binary:`. |
| ``bash: BashVersionChecker could not parse a version from `/usr/local/bin/bash --version` `` | `validate` and every run | The first line of `--version` has no `version N.N`. Something other than bash is at that path. |
| `bash 5.3.15 does not meet its requirement <spec> (cfg/executables.yml)` | `validate` and every run | The floor moved or the machine is behind. |
| `FileNotFoundError: Bash modification script mod_image.sh does not exist or is not a file` | generation; run `ok: false`, traceback in the log | The path is resolved from the configuration root, not from the image file's directory or the shell's. Fix the path or `--root-dir`. |
| `Bash modification '<name>': ensure declares [...] but every one is empty, so it would emit nothing` | load; CLI exit 1 | Every `ensure` list is empty. Fill one or drop `ensure`. |
| `Bash modification '<name>': ensure.files[N]: `path` is required` (or `ensure.commands[N]: `run` is required`) | load; CLI exit 1 | A `files` entry without `path`, or a `commands` entry without `run`. Before stage 63 this was a `KeyError` at generation. |
| `Bash modification '<name>': ensure.packages must be a list of package names, not str 'git'` | load; CLI exit 1 | `packages:` (or `services:`) given as a string; the old code iterated its letters. Write a list (`packages: [git]`). |
| `Bash modification '<name>': ensure.files[N].mode 644 is not a mode YAML could have read from octal` | load; CLI exit 1 | An unquoted `644`, which YAML reads as a decimal number. Write `mode: "0644"`. |
| `Bash modification '<name>': ensure.files[N]: unknown keys [...]` | load; CLI exit 1 | Only `path`, `content`, `mode` on a file and `run`, `unless` on a command. |
| `csis ensure: no dnf, yum or apt-get to install <pkg>` | apply / `test-mods` | The image has none of the three package managers. Use a `script` line with the one it has. |
| `dnf` (or `yum`, `apt-get`) error on a package step | apply / `test-mods` | The first package manager found could not install the package, and its message is the real one (no match, no repository, no network from the build subnet). Before stage 63 the line fell through to `apt-get` and showed `apt-get: command not found` last on an EL host. |
| `cmp: command not found` or `base64: command not found` | apply | The image lacks diffutils / coreutils. Add the package to an earlier item's `ensure.packages` or a `script` line. |
| `sudo: a terminal is required to read the password` | apply | The bake ssh user has no passwordless `sudo`. This is an OS builder / runtime matter, not the item's. |
| `Failed to enable unit: Unit <svc>.service does not exist` | apply | `services:` names a unit the image has not installed yet; install it earlier in the same item's `packages` (packages run before services). |
| `Build 'amazon-ebs.<image>' errored ...` and no new build in `meta-state/lineage.yaml` | apply (`run-instance-image.sh`, `set -euo pipefail`) | A line exited nonzero under `-e`. Packer's log names the provisioner by its position; match it to the `# Modifications for <name>` comment in the build file under `generated/`. Nothing is recorded for a failed bake; fix and re-run. |
| `FAIL <image>/<mod>: rc=1/None idempotent=None <tail of output>` | `test-mods`; exit 1 | Run one failed in the container. The output tail is the last 2000 characters; `meta-state/mod-tests.yaml` keeps it under the content hash. |
| `FAIL <image>/<mod>: rc=0/0 idempotent=False ['A /opt/x', ...]` | `test-mods`; exit 1 | Run two changed files. A `script` line that appends, or a `commands` entry without `unless`. Make it `ensure`, or add `unless`. |
| `mod tests: N tested, M skipped` with `docker is not available` in the JSON | `test-mods`; exit 1 only with `--strict` | Start docker. `just full-test` runs this leg with `--strict`. |
| `modification '<name>' of build '<id>' failed its local mod test (status=fail, idempotent=...)` | `release`; exit 1 | Fix the modification, re-bake, re-test. A release never overrides a failed record. |
| `modification '<name>' of build '<id>' has no local mod-test result (config.require_mod_tests)` | `release`; exit 1 | Run `just test-mods` on the live tree and commit `meta-state/mod-tests.yaml`. |
| `local mods: <src> for <name> not found; the bundle will lack it` | generation log (Packer plugin) | The bundle could not find a script file under the block dir, the working path or as given; the bake still emits the provisioner. Usually the same cause as the `FileNotFoundError` above, seen when the file was removed between copy and bundle. |

## Related

- Manuals: [CONFIGURATION.md](../../docs/CONFIGURATION.md) sections 3 and
  7 (executables, mod builders, the modification item),
  [OPERATIONS.md](../../docs/OPERATIONS.md) (the modification tests, what a
  green bake proves), [DESIGN.md](../../docs/DESIGN.md) M2 (the bash mod
  contract).
- Base models extended:
  [mod_builder.py](../base/src/cs_image_system/base/models/mod_builder.py),
  [moditem_type.py](../base/src/cs_image_system/base/models/moditem_type.py),
  [root_item.py](../base/src/cs_image_system/base/models/root_item.py),
  [builder_model.py](../base/src/cs_image_system/base/models/builder_model.py).
- Base builder class:
  [builder_base_mod.py](../base/src/cs_image_system/base/basic/builder_base_mod.py);
  the label helper `build_target_label_of` in
  [builder_base_image.py](../base/src/cs_image_system/base/basic/builder_base_image.py);
  the version checker base in
  [abstract_version_checker.py](../base/src/cs_image_system/base/basic/abstract_version_checker.py).
- The image builder that calls it and hosts its output:
  [packer-plugin](../packer-plugin)
  ([packer_ebs_builder.py](../packer-plugin/src/cs_image_system/packer_plugin/packer_ebs_builder.py),
  [v2_local_mods.py](../packer-plugin/src/cs_image_system/packer_plugin/v2_local_mods.py)).
- Lineage records for modifications:
  [lineage.py](../base/src/cs_image_system/base/lineage.py) (`mod_records`);
  the release gate in [release.py](../base/src/cs_image_system/base/release.py).
- Tests: [tests/test_bash_provisioner.py](tests/test_bash_provisioner.py)
  (two blocks for files plus inline, builder options, script copying);
  [test_v2_gate8_modifications.py](../../tests/test_v2_gate8_modifications.py)
  (both kinds emitted, unknown type refused, the load rule);
  [test_v2_explore_local_mods.py](../../tests/test_v2_explore_local_mods.py)
  (`ensure` guards, idempotence recorded, the bundle);
  [test_v2_explore_mod_tests.py](../../tests/test_v2_explore_mod_tests.py)
  (the container tests on the fixture's bash item);
  [test_v2_hygiene_three.py](../../tests/test_v2_hygiene_three.py)
  (`BashVersionChecker` found by name, versions judged).
- No terraform modules and no hashicorp-utils usage: the plugin writes
  Packer provisioner lines directly.
