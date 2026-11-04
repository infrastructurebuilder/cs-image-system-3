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
  `AnsibleModItemModel`, which is the class the item is loaded into. The
  orchestrator then rewrites the item's `type` to the builder's *name*
  (an item that omitted `type:` shows `ansible-default` afterwards, and
  that is the name the emitted comment carries).
- An `executables:` entry named `ansible-playbook` is version-checked by
  `AnsibleVersionChecker` (regex `\s+\[core\s([\d\.]+)` over the first
  line of `ansible-playbook --version`).

## Models

### `AnsibleBuilderModel` and `AnsiblePackerModBuilderModel` (`ansible`)

Defined in [ansible_models.py](src/cs_image_system/ansible_plugin/ansible_models.py).
`AnsibleBuilderModel` extends
[`ModBuilderModel`](../base/src/cs_image_system/base/models/mod_builder.py),
which adds nothing to
[`BuilderModel`](../base/src/cs_image_system/base/models/builder_model.py)
(`name`, `type`, `description`, `aliases`, `executable`, `is_default`,
`config`, `gitignore`, `tags`). `AnsiblePackerModBuilderModel` is the
registered subclass; it adds no fields. The full field table is
[CONFIGURATION 7.1](../../docs/CONFIGURATION.md#71-ansible); the keys
this plugin adds, and what it does with them:

- `extra_arguments`: prepended to every emitted `provisioner "ansible"`'s
  `extra_arguments`; each entry is HCL-escaped.
- `expect_disconnect`: emits `expect_disconnect = true` on every
  provisioner.
- `ansible_connection`: when set, the ansible variable
  `ansible_connection=<value>` is passed in `--extra-vars` (for example
  `docker`), winning over what the runtime answers through
  `bake_ansible_vars`. It travels as a variable because packer's
  provisioner has no option for it (a `connection_type` line is not one
  packer knows).
- `configuration_user`: when set, the `user` of every `provisioner
  "ansible"` this builder emits, beating the bake-user resolver
  ([CONFIGURATION 5.1.1](../../docs/CONFIGURATION.md#511-the-bake-ssh-user));
  the one place a modification connects as someone other than the bake
  user.

There is no builder-level `playbooks` field: a list on the builder would
be copied beside the Packer root and referenced by no provisioner, so the
playbooks that run are the items' own. Every model in the system refuses
unknown keys, so a builder that declares `playbooks:` fails to load.

Base fields this plugin constrains: `executable` should name the
`ansible-playbook` executable (the fixture does), though the emission does
not invoke it; Packer runs Ansible. `parameters:` is refused at load (a
base-model rule). `config:` on the builder is carried but never read.

### `AnsibleModItemModel`

Same file. Extends
[`ModItemModel`](../base/src/cs_image_system/base/models/moditem_type.py)
(`SubRootItem` -> `RootItem` -> `NameTyped`). The item's full field table
is [CONFIGURATION 7.3](../../docs/CONFIGURATION.md#73-the-modification-item-inside-an-images-modifications);
what this plugin adds and what it does with the inherited fields:

- `playbooks` (this plugin's own key): playbook files, relative to the
  configuration root, run in order. One `provisioner "ansible"` per
  entry. An item with none is refused at load (see below).
- `name`: names the provisioner comment and the local bundle directory
  (`NN-<name>`).
- `type`: foreign key to a `mod_builders:` entry (see above).
- `description`, `aliases`, `tags`: carried; not emitted.
- `config`: not read by this plugin. It takes part in the lineage content
  hash of the modification and nothing else.
- `_model_id` (set at load, not a YAML key): the owning image's global id
  (the orchestrator assigns it while structuring the image's
  `modifications:`). `identified_model` (and `builder`) therefore resolve
  to the *image*, not to the modification builder.

`remap_self_with_copied_assets(copied)` de-duplicates the item's own
`playbooks` (first occurrence wins, order kept) and rewrites any entry
present in `copied` to its copied path. Because the builder's
`copy_external_assets` returns an empty mapping, in practice this call
only de-duplicates.

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
([packer_ebs_builder.py](../packer-plugin/src/cs_image_system/packer_plugin/packer_ebs_builder.py))
calls, in order:

1. `copy_external_assets(block_dir, mod)`: returns `{}`. Nothing is copied
   here; the item's playbooks are copied in step 4.
2. `mod.remap_self_with_copied_assets({})` on the item (see above).
3. `generate_items_before_modification`: returns an empty asset set.
4. `generate_items_during_modification(image, mod, image_builder, phase, build_path)`:
   for each playbook of the item, in order:
   - if the path is relative and the file exists (relative to the process
     working directory, which the run sets to the configuration root),
     copies it to `<generation root>/<block dir>/<playbook>` so Packer
     finds it next to the HCL. An absolute path is emitted as given and
     not copied. A relative path that is not a file is refused here,
     before packer runs, with a `FileNotFoundError`: `modification
     '<name>': playbook '<path>' does not exist (a relative path is read
     from the configuration root)`;
   - appends to the build file a comment
     `# Modifications for <item name> of type <item type>`;
   - a `provisioner "shell"` with `only = ["<source type>.<image>"]` whose
     single inline command creates `/usr/local/bin/csis-ansible-python`
     if absent: it tries `python3.12`, `python3.11`, `python3.9` (installing
     with `sudo dnf` when needed), then the newest `/usr/bin/python3.N`, then
     `python3`, and symlinks the winner. The command is guarded on
     `test -x`, so the second and later playbooks of an image re-run it
     as a no-op;
   - a `provisioner "ansible"` with `only`, `playbook_file = "<playbook>"`,
     `user = "<name>"` (the builder's `configuration_user` when set;
     otherwise the user the runtime names to provisioners
     through `bake_ssh_username(image)`, where the GCE runtime answers the
     user the packer source resolves for that image and the AWS runtime
     answers nothing, so no line), `extra_arguments = [<builder
     extra_arguments>..., "-e",
     "ansible_python_interpreter=/usr/local/bin/csis-ansible-python"]`,
     `"--extra-vars", "ansible_connection=... ansible_host=..."` when
     the runtime's `bake_ansible_vars` answers (the docker runtime: the
     build container's name, reached through the daemon) or
     `ansible_connection` is set, and `expect_disconnect = true` when
     set. Every string written into these lines (`playbook_file`,
     `user`, each `extra_arguments` entry) goes through `_hcl`: backslashes and
     double quotes are escaped and packer's template openers `${` and
     `%{` are doubled to `$${` and `%%{`, so the value reaches ansible
     literally and a `"` in any of them cannot break the build file.
5. `generate_items_after_modification`: returns an empty asset set.

The `only` label comes from `build_target_label_of(image_builder, image)`:
the image builder's `build_target_label(image)` when it has one
(`amazon-ebs.<image>` for packer-ebs, `googlecompute.<image>` for
packer-gce), else the legacy `amazon-ebs.<image>`.

The provisioners run on the build VM when the image builder's deferred
`packer build .` executes. Separately, the Packer plugin's local
modification bundle
([v2_local_mods.py](../packer-plugin/src/cs_image_system/packer_plugin/v2_local_mods.py))
records the item: its directory `csis-mods/<image>/NN-<name>/` receives a
copy of each playbook, a `run.sh` that runs
`ansible-playbook -i localhost, -c local '<playbook>'` per playbook (after
checking that `ansible-playbook` exists on the image, exit 3 when it does
not), and a `MANIFEST.yaml` with `operation: ansible` and
`idempotent: ansible`. Both values come from
[lineage.py](../base/src/cs_image_system/base/lineage.py)'s `mod_records`,
which classifies any item carrying `playbooks` as an ansible operation and
hashes the playbook files' contents (or the path string, when the file is
not found) together with the item's `type` and `config`.

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
    source_image: my-deb-12
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
The same file's `imgfile-basic-dask` names the builder explicitly
(`type: ansible-default`) and carries an ansible item next to a bash one;
[setup_dask.yml](../../tests/fixtures/config/setup_dask.yml) is a playbook
that has been through a live bake and shows the shape that works on the
pinned interpreter (see "When it fails").

## Prerequisites and integration

The plugin has no credentials, accounts or network of its own and reads
no environment variable. What must exist outside the system:

- **`ansible-core` on the machine that runs `packer build`** (the
  operator's machine, or the CI runner when performing). Packer's ansible
  provisioner runs `ansible-playbook` locally and connects to the build
  VM through the communicator packer already has; the target only needs
  Python (which the emitted shell step supplies). The plugin finds it
  through the configuration: `cfg/executables.yml` declares an entry named
  `ansible-playbook` (`binary` = path or a name on PATH, `version` = a PEP
  440 requirement; the fixture pins `/usr/local/bin/ansible-playbook`
  `>=2.16`), and the mod builder's `executable: ansible-playbook` names
  that entry. `validate` and every run check the entry with this plugin's
  `AnsibleVersionChecker`; the checker reads the `[core x.y.z]` figure, so
  the floor is an ansible-core version, not the `ansible` meta-package's.
  The CI perform job installs `ansible-core` where `cfg/executables.yml`
  pins it, after the record is pushed
  ([docs/OPERATIONS.md](../../docs/OPERATIONS.md), "CI performs on main").
- **Packer's `ansible` plugin** on the same machine. It is declared per
  image builder under `required_plugins:` in `cfg/image-builders.yml`
  (fixture: `name: ansible`, `source: github.com/hashicorp/ansible`,
  `version: '>= 1.0.0'`); the Packer plugin emits it into the root's
  plugins file and `packer init` installs it. This plugin does not check
  that the declaration exists: an image builder without it fails at
  `packer build` with packer's own "unknown provisioner" error.
- **On the build VM**: passwordless `sudo` for the communicator's user
  (the emitted interpreter step and `become` in playbooks both use it),
  and for EL-family images a reachable package repository, because the
  interpreter step may `sudo dnf -y install python3.N`. When no `dnf`
  exists or every install fails, the step falls back to the newest
  `/usr/bin/python3.N` present, then `python3`; a target with no Python at
  all fails at fact gathering.
- **The build VM's SSH user**, on runtimes that fix one: the GCE runtime
  builder's `bake_ssh_username(image)`, the user the packer source bakes
  that image as (the bake-user order, CONFIGURATION 5.1.1), is written as
  the provisioner's `user`. It is the resolved user, not the runtime's
  `ssh_username` alone, so that an entry-level user bakes as itself and
  ansible connects as that same user. The AWS runtime returns `None` and
  the provisioner keeps packer's default (the communicator's user). Nothing
  else is needed from the runtime.
- **Reaching the build VM** is the runtime's and the image builder's
  business (Session Manager on AWS, IAP on GCE), not this plugin's.

Python side: Python 3.13 or later, `pydantic>=2.13`, and
`cs-image-system-contract` and `cs-image-system-base` at the same version
([pyproject.toml](pyproject.toml)).

## Configuration reference

### `mod_builders:` entry with `type: ansible`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | The builder's name; what an item's `type:` names. Normalised by `safe_name` (no `/` or `\`; never `default`). |
| `type` | str | required | `ansible`. |
| `description` | str or null | null | Carried; not read by this plugin. |
| `aliases` | list[str] | `[]` | Extra names an item's `type:` may use. |
| `is_default` | bool | `false` | The builder an item with no `type:` (or `type: default`) resolves to. At most one mod builder should say so. |
| `executable` | str or null | null | The `executables:` entry for `ansible-playbook`. `validate` refuses a name that is not declared there; the emission never invokes it. |
| `config` | mapping | `{}` | Accepted, not read. |
| `gitignore` | list[str] | `[]` | Accepted, not read by this plugin. |
| `tags` | mapping | `{}` | Accepted, not read by this plugin. |
| `extra_arguments` | list[str] | `[]` | Emitted first in every provisioner's `extra_arguments`, before the system's `-e ansible_python_interpreter=...`. Each value is written as an escaped HCL string (backslash and `"` escaped, `${`/`%{` doubled). |
| `expect_disconnect` | bool | `false` | When true, every provisioner carries `expect_disconnect = true`. |
| `ansible_connection` | str or null | null | When set, every provisioner's `extra_arguments` carry `--extra-vars ansible_connection=<value>` (escaped as above), over the runtime's own answer. |
| `configuration_user` | str or null | null | When set, every provisioner this builder emits carries `user = "<value>"`, whatever the runtime would answer: ansible connects as that user instead of the bake user. Unset, the `user` comes from the runtime's bake SSH user. The user must exist on the build VM and accept the bake's SSH key. |
| `parameters` | | | Refused at load (a base-model rule). |
| `playbooks` | | | Refused at load as an unknown key: the playbooks that run are the items' own. |

### Modification item under an image's `modifications:` (ansible builder)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | Unique within the image; appears in the emitted comment and as the bundle directory `NN-<name>`. |
| `type` | str | `default` | The mod builder: its name, an alias, `default`, or omitted. Rewritten to the builder's name at load. An unknown name is a `KeyError` at load. Omitted with no `is_default: true` mod builder: refused at load. |
| `playbooks` | list[str] | `[]` | One `provisioner "ansible"` per entry, in order; duplicates collapse to the first occurrence. Paths are relative to the configuration root (the run's working directory) or absolute; a relative path that does not exist is refused at generation. Required in effect: an empty list is refused at load. |
| `description` | str or null | null | Accepted, not read. |
| `aliases` | list[str] | `[]` | Accepted, not read. |
| `tags` | mapping | `{}` | Accepted, not read. |
| `config` | mapping | `{}` | Not read by this plugin and not passed to ansible. It is part of the modification's lineage content hash, so changing it makes the image due for a re-bake. |

### Variations

- **Runtime.** When the image builder's runtime declares a bake SSH user
  (GCE: the image's resolved bake user), the provisioner carries
  `user = "<that>"`; when it does not (AWS), no `user` line is emitted and
  packer's default applies.
- **`configuration_user` declared** on the builder: every
  provisioner carries `user = "<configuration_user>"` on every runtime,
  AWS included, replacing whatever the runtime would have answered.
  Undeclared: the Runtime bullet above. The `only` label follows the image builder's
  source type (`amazon-ebs.` or `googlecompute.`).
- **`extra_arguments` declared** on the builder: they precede the
  system's two entries; otherwise the list is exactly `["-e",
  "ansible_python_interpreter=/usr/local/bin/csis-ansible-python"]`.
- **`ansible_connection` declared**, or the runtime answering
  `bake_ansible_vars` (the docker runtime does): two extra
  `extra_arguments` entries, `"--extra-vars"` and the `key=value` pairs;
  neither, packer picks the connection (ssh for the cloud sources).
- **`expect_disconnect: true`**: one extra `expect_disconnect = true` line
  per provisioner; false emits nothing.
- **Item `type:` present vs absent.** Present: resolved by name or alias,
  and an unknown name is a hard failure at load. Absent or `default`: the
  `is_default: true` mod builder. When no mod builder is default, the
  load is refused: in practice the builder-list check refuses
  first with `No default builder found in mod_builder list.`, and the
  orchestrator's own refusal (`` modification '<name>' names no builder
  (`type`) and no mod builder is `is_default: true`; name one with
  `type:` or mark a default ``) covers an item that reaches it anyway.
  Either refusal names what is missing at load, so the image builder's
  modification loop never meets an item that was left a plain mapping.
- **Relative vs absolute playbook path.** Relative and existing: copied
  beside the HCL and referenced by that relative path. Absolute: referenced
  verbatim, never copied (packer then reads it from that path on the
  machine running the bake; a missing absolute path still fails only at
  packer). Relative and missing: refused at generation, naming the
  modification and the path, so the mistake surfaces before `packer
  build` validates the provisioner.
- **Several playbooks on one item**: one shell + ansible pair per
  playbook; the shell step is guarded, so only the first does work.
- **Several ansible items on one image**: emitted in declaration order,
  each with its own comment line; the local bundle numbers them `01-`,
  `02-`, ... in that order together with the image's bash items.
- **Dry run vs real run.** Generation is identical. The provisioners
  execute only when the image builder's `packer build` runs, which the
  image builder defers to its `run-<lifecycle>.sh` and executes only with
  `--no-dry-run`. This plugin has no dry-run branch of its own.
- **Apply flag on vs off.** No difference in what this plugin emits; the
  bake itself is gated by the image builder and the run scope.
- **Base images.** The image builder ignores `modifications:` on a base
  image (a warning, "base images do not receive modifications"); this
  plugin is never called for one.
- **Encrypted values.** The plugin has no encryption-aware code: it emits
  the strings it is given (HCL-escaped). Nothing in its fields is expected to be an
  `ENC[age:...]` marker.
- **`config:` on the item changed, playbooks unchanged**: the content hash
  moves and the image re-bakes, but the emitted provisioner is byte for
  byte the same.

## What it tests and verifies

- **At load** (pydantic, every command that loads the configuration):
  field types; unknown keys refused (`extra="forbid"`); `parameters:`
  refused (a base-model rule); `name`/`aliases` free of `/` and
  `\` and never `default`; this plugin's own rule, an ansible item
  without `playbooks:` is refused by name; and (base's) an item
  with no `type:` when no mod builder is `is_default: true` is refused. The verdict is the exception
  text on the command's output and a non-zero exit; no file is written.
- **At `validate`** (and at the start of every run): base's version check
  runs this plugin's `AnsibleVersionChecker` for the executable named
  `ansible-playbook`: the binary must exist, its `--version` first line
  must match `[core x.y.z]`, and the version must satisfy the declared
  requirement. Base also checks that the mod builder's `executable` names
  a declared entry. Verdicts: one `   - <message>` error line per failure
  and a failed validation; one INFO line listing every tool and version
  checked when all pass.
- **At generation**: a relative playbook path that does not exist is
  refused with a `FileNotFoundError` naming the modification and the path
  (see Variations). The strings written into the provisioner are
  escaped, so no configured value can break the build file's syntax. The emitted text is
  pinned by the golden fixture and by `tests/test_v2_gate8_modifications.py`
  (one `provisioner "ansible"` per item, correct `only`, `playbook_file`)
  and `tests/test_v2_explore_gcp.py` (the GCE label), so a change in the
  emission fails `just test`.
- **At apply**: packer runs the provisioners; a failing task fails the
  bake. This plugin adds no check; the image's own `tests:` (base's
  in-bake verification, emitted as the last provisioner) and
  `tests.post_bake` are where a playbook's effect is asserted.
- **After apply, in the state query, in meta-state**: nothing. The plugin
  has no post-finalize hook and writes no meta-state file. What records
  the modification is base's lineage (`mods` in the build record, content
  hash and `operation: ansible`) and the Packer plugin's bundle
  `MANIFEST.yaml` on the image.
- **Before a bake, on request**: `just test-mods` (base's
  `mod_tests.py`) runs every ansible item twice in a throwaway container of
  the image's OS family through `ansible-playbook -c docker`, after the
  same interpreter preparation the bake uses; the first run must exit 0
  and the second must change nothing (filesystem diff, plus ansible's own
  `changed=` recap). Results land in `meta-state/mod-tests.yaml` keyed by
  content hash. That harness is base's; this plugin contributes nothing to
  it beyond the item's `playbooks`.

## When it fails

Incidents that have happened, with their cause and fix, are recorded on
[INCIDENTS.md](../../docs/INCIDENTS.md); what follows keeps each
failure's symptom, its meaning and what to do.

Failures by symptom: what each means and what to do.

- **`ansible-playbook <found> does not meet its requirement <spec>
  (cfg/executables.yml)` at `validate`.** The version checker is looked
  up by the executable's name, so the `ansible-playbook` entry's floor is
  enforced at `validate` and before every run; the ansible-core on the
  machine is older than the floor. Install the required ansible-core
  where the entry's `binary` points, or move the floor in
  `cfg/executables.yml` if the floor is the thing that is wrong.
- **A builder that declares `playbooks:` fails to load** with pydantic's
  unknown-key error (`extra_forbidden`) naming `playbooks`. The builder
  has no playbook field: a list there would be copied beside the Packer
  root and referenced by no provisioner. Move the playbook onto each item
  that should run it.
- **`Ansible modification '<name>' declares no playbooks: it has nothing
  to modify with (config alone provisions nothing). Give it 'playbooks:'
  ... or remove it.` at load.** An item with only `config:` would render
  no provisioner while lineage, the on-image bundle and the modification
  tests recorded it as applied, so it is refused by name. Give the item a
  playbook or delete it; the image's fingerprint changes either way and
  it re-bakes.
- **`Failed to import the required Python library (packaging)`** in
  packer's output for the ansible provisioner. Ansible's `pip` module
  imports `packaging` on the target's interpreter, and the pinned
  `/usr/local/bin/csis-ansible-python` (a bare `python3.N` the shell step
  installed) does not have it; a `package` task before it passes. The
  bake fails and no build is recorded. Fix in the playbook, not the
  plugin: run `pip3` through `ansible.builtin.command` guarded on an
  import check, as
  [setup_dask.yml](../../tests/fixtures/config/setup_dask.yml) does.
  Any module that needs a library on the target interpreter has the same
  problem.
- **A playbook that does nothing passes the bake.** A placeholder
  playbook (one `debug` task) bakes successfully, and the launched
  instance lacks what it was meant to install (`python3 -c 'import
  dask'` fails). This plugin cannot tell an empty playbook from a full
  one; the image's `tests.post_bake` can. Where it lands:
  `meta-state/image-tests.yaml` (ok false, the failing assertion named)
  and `release` refusing the build.
- **Every task `unreachable` / `Failed to create temporary directory`.**
  Packer's ansible provisioner defaults `ansible_user` to the operator's
  LOCAL login, never the build VM's SSH user, so ansible builds
  `~/.ansible/tmp` under `/home/<local-user>` on the VM. Intermittent,
  because packer's `use_proxy` auto-detection masks it until it flips to
  direct mode. The `user = "<bake ssh user>"` line, emitted when the
  runtime declares one (GCE), is what prevents it. If the symptom appears
  on a runtime that returns `None` from `bake_ssh_username(image)`, that
  runtime needs the hook, not the playbook.
- **Fact gathering dies with "The module interpreter..."** on an
  EL-family base whose only Python (3.6 on RHEL 8) the controller's
  ansible-core no longer supports. The emitted `provisioner "shell"`
  installs a newer Python and pins it at
  `/usr/local/bin/csis-ansible-python`, and the
  `-e ansible_python_interpreter=...` argument names it. If a new OS
  family has no `python3.12`/`3.11`/`3.9` package and no `dnf`, the step
  falls back to whatever `python3` exists; check the family's Python
  against the ansible-core support matrix before blaming the playbook.

Failures the code raises:

- `Could not resolve builder '<type>' referenced in <image>` (a
  `KeyError` at load): the item's `type:` names no mod builder by name or
  alias. Check `cfg/mod-builders.yml`.
- `<name>: binary '<path>' not found (declared in cfg/executables.yml; an
  absolute path, or a name on PATH)` at `validate`: `ansible-playbook` is
  not where the entry says. Install it there or fix `binary`.
- `ansible-playbook: AnsibleVersionChecker could not parse a version from
  '<binary> --version'` at `validate`: the first line of the output has
  no `[core x.y.z]` (a wrapper script, or a very old `ansible` whose
  output has a different shape). The regex is fixed; point `binary` at the
  real `ansible-playbook`.
- `ansible-playbook: could not read its version (...)`: the binary exists
  but running it failed (permissions, a broken virtualenv). The exception
  text follows the colon.
- `Executable ansible-playbook specified for provider ansible-default not
  found in executables list.` at `validate`: the builder's `executable`
  names an entry `cfg/executables.yml` does not have.
- `modification '<name>': playbook '<path>' does not exist (a relative
  path is read from the configuration root)` (a `FileNotFoundError` at
  generation): a relative playbook named on an item is not a file under
  the configuration root. Fix the path or add the file. An ABSOLUTE path
  that does not exist is not checked at generation: a warning `local
  mods: <file> for <item> not found; the bundle will lack it` from the
  Packer plugin, then `packer build` fails validating `playbook_file`.
- `No default builder found in mod_builder list.` at load: no mod builder
  says `is_default: true`. Mark one, or give every item a `type:`. The
  orchestrator's own form of the same refusal, for an item that reaches
  it, is `` modification '<name>' names no builder (`type`) and no mod
  builder is `is_default: true`; name one with `type:` or mark a
  default ``.
- A value containing a double quote, a backslash or `${`/`%{` (an
  `extra_arguments` entry, `ansible_connection`, a playbook path) cannot
  malform the build file: every such string is written HCL-escaped.
- A playbook task fails on the VM: packer reports the ansible recap and
  exits non-zero; the image builder's `run-<lifecycle>.sh` propagates the
  exit code, no build is recorded and packer cleans up its build VM. The
  playbook's own output is the place to look; `just test-mods` reproduces most task failures in a
  container without a cloud.
- The interpreter step cannot make `/usr/local/bin/csis-ansible-python`
  (no `sudo`, no writable `/usr/local/bin`): the shell provisioner exits
  non-zero and the bake stops before the first playbook. Look for the
  `test -x /usr/local/bin/csis-ansible-python || { ... }` line in packer's
  output.

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
- The version check and the modification test harness:
  [validate.py](../base/src/cs_image_system/base/commands/validate.py),
  [mod_tests.py](../base/src/cs_image_system/base/mod_tests.py).
- Manuals: [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) (section 7,
  `cfg/mod-builders.yml`), [docs/OPERATIONS.md](../../docs/OPERATIONS.md),
  [docs/DESIGN.md](../../docs/DESIGN.md) (M2).
- No terraform modules and no hashicorp-utils usage: the plugin writes
  Packer provisioner lines directly.
