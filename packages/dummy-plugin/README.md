# cs-image-system-dummy-plugin

The extension template and test double. It exists to show, in the smallest
working form, the two ways a package extends the system: a *builder plugin*
that registers model and builder classes selectable from YAML, and a *hook
plugin* that participates in the runner without any YAML at all. It
registers a `dummy` group builder and a `dummy` user builder that generate
almost nothing, an on-summary notifier, and an optional `notify` lifecycle.
Nothing in the frozen fixture selects its builders; the runner's tests
exercise its hooks. Copy it to start a new plugin.

## What it registers

Two entry points are declared in [pyproject.toml](pyproject.toml):

```toml
[project.entry-points."cs_image_system.plugins.runtime"]
dummy_plugin = "cs_image_system.dummy_plugin.main:initialize"

[project.entry-points."cs_image_system.plugins.hooks"]
dummy_hooks = "cs_image_system.dummy_plugin.hooks:initialize"
```

The first is a builder plugin. `initialize()` in
[main.py](src/cs_image_system/dummy_plugin/main.py) returns a
`DummyPluginMetadata` whose services map the key `dummy` to four classes
and whose `builders_for_models` binds each model to its builder. The
entry-point group is `runtime`, but the group only decides load order: the
loader registers each class under the classification its own
`csis_classifier()` reports.

| Class | `csis_name()` | `csis_classifier()` | Registered under |
|---|---|---|---|
| `DummyGroupBuilderModel` ([dummy_models.py](src/cs_image_system/dummy_plugin/dummy_models.py)) | `dummy` | `VCT.GROUP_BUILDER_MODEL` | `group_builder_model` |
| `DummyGroupBuilder` ([dummy_builders.py](src/cs_image_system/dummy_plugin/dummy_builders.py)) | `dummy` | `VCT.GROUP_BUILDER` | `group_builder` |
| `DummyUserBuilderModel` ([dummy_models.py](src/cs_image_system/dummy_plugin/dummy_models.py)) | `dummy` | `VCT.USER_BUILDER_MODEL` | `user_builder_model` |
| `DummyUserBuilder` ([dummy_builders.py](src/cs_image_system/dummy_plugin/dummy_builders.py)) | `dummy` | `VCT.USER_BUILDER` | `user_builder` |

A `group_builders:` entry selects the group pair with `type: dummy`; a
`user_builders:` entry selects the user pair with the same key. There are
no type aliases. The constant `DUMMY = "dummy"` in `dummy_models.py` is the
key; the AWS and GCE runtime plugins import it (and define unregistered
copies of these two models) from this package.

The second is a hook plugin. `initialize()` in
[hooks.py](src/cs_image_system/dummy_plugin/hooks.py) returns a `HookSet`
(defined in
[run_lifecycles.py](../base/src/cs_image_system/base/commands/run_lifecycles.py))
carrying:

| Hook | Registered | What it does |
|---|---|---|
| `on_summary`: `notify_summary` | always | When the environment variable `CSIS_NOTIFY_FILE` names a file, appends one JSON line per run: `{"run", "ok", "requested", "apply"}`. Unset, it logs and does nothing. |
| `lifecycles`: `LifecycleSpec(name="notify", after=None)` | only when `CSIS_DUMMY_LIFECYCLE` is set | A lifecycle with no phases and no builders, positioned last. It gets its own `generated/notify/` directory, joins `run --all`, and is a no-op at apply time because it defers nothing. |

The `HookSet` also accepts `validators`, `after_generate`, `before_apply`
and `after_apply` lists; the dummy plugin leaves them empty.

## Models

### `DummyGroupBuilderModel`

Extends `GroupBuilderModel` in
[group_builder.py](../base/src/cs_image_system/base/models/group_builder.py),
which extends `BuilderModel` and `NameTyped` in
[builder_model.py](../base/src/cs_image_system/base/models/builder_model.py).
The base adds no fields of its own beyond `BuilderModel`.

Fields it adds:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `org` | `str` | required | An organisation label. Nothing reads it. |
| `team` | `str` | required | A team label. Nothing reads it. |
| `key` | `str` | `DEFAULT` | Placeholder for a provider key name. Nothing reads it; a credential value never belongs in the tree. |
| `secret` | `str` | `DEFAULT` | Placeholder; same rule. |
| `api_host` | `str` | `DEFAULT` | Placeholder for a provider host. Nothing reads it. |

Base fields it inherits: `name`, `type`, `description`, `aliases`,
`executable`, `is_default`, `config`, `gitignore`, `tags`. It overrides
`csis_name()` to return `dummy`. It rejects unknown keys and the retired
`parameters:` key like every builder model.

### `DummyUserBuilderModel`

Extends `UserBuilderModel` in
[user_builder.py](../base/src/cs_image_system/base/models/user_builder.py).

Fields it adds:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `org` | `str` | required | An organisation label. Nothing reads it. |
| `team` | `str` | required | A team label. Nothing reads it. |

Base fields it inherits, and their meaning here:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `default_user_email_template` | `str` | `{{ user.name }}` | Template for a user's email when the user declares none. |
| `default_user_description_template` | `str` | `User {{ user.name }} / {{ user.email }}` | Template for a user's description. |
| `email_as_username` | `bool` | `True` | When true, `UserBuilderBase.add_user_to_builder()` requires `user.name` to equal `user.email` (case-folded) and fills a blank name from the email. |
| `name`, `type`, `description`, `aliases`, `executable`, `is_default`, `config`, `gitignore`, `tags` | | | From `BuilderModel`/`NameTyped`. |

It carries the class attribute `type = "dummy"` and overrides `csis_name()`
to return `dummy`. It does not narrow or add validation.

## The builder

Both builders implement the six generation hooks of `BuilderBase` in
[builder_base.py](../base/src/cs_image_system/base/basic/builder_base.py):
`generate_items_before`, `get_commands_to_run_before`,
`generate_items_during`, `get_commands_to_run_during`,
`generate_items_after`, `get_commands_to_run_after`. The runner calls each
with a lifecycle phase; a builder answers with assets to write (an
`AssetSet` of path and content) or commands to run (a `CFExecutables` of
commands now and commands at finalization).

### `DummyGroupBuilder`

Extends `GroupBuilderBase` in
[builder_base_group.py](../base/src/cs_image_system/base/basic/builder_base_group.py).
Every hook returns empty, in the order the group lifecycle runs them:

| Phase | Hook | Returns |
|---|---|---|
| `group-generation` | `generate_items_before` | An empty `AssetSet`. |
| `group-generation` | `get_commands_to_run_before` | No commands. |
| `group-generation` | `generate_items_during` | An empty list. |
| `group-generation` | `get_commands_to_run_during` | No commands. |
| `group-generation` | `generate_items_after` | An empty `AssetSet`. |
| `group-generation` | `get_commands_to_run_after` | No commands. |

It inherits the identity contract unchanged: `identity_type()` is `dummy`
(the default is the plugin's name), so a base image declaring
`identity_types: [dummy]` bakes nothing for it (`base_image_prerequisites`,
`verify_commands`, `activation_commands` and `launch_parameters` are the
empty base defaults); `gid_policy()` is `provider-assigned`;
`query_state()`, `query_attributes()` and `export_gids()` raise
`NotImplementedError`, so the state query and the gid shim skip it.

### `DummyUserBuilder`

Extends `UserBuilderBase` in
[builder_base_user.py](../base/src/cs_image_system/base/basic/builder_base_user.py).

| Phase | Hook | Returns |
|---|---|---|
| any | `query_existing_users()` | An empty list. |
| any | `get_subpath()` | `Path("Dummy-tf")`, the directory its assets go under. |
| `user-generation` | `generate_items_before` | One asset: `Dummy-tf/dummy_users.tf` containing a single comment line naming the builder class. |
| `user-generation` | `get_commands_to_run_before` | No commands. |
| `user-generation` | `generate_items_during` | An empty list. |
| `user-generation` | `get_commands_to_run_during` | No commands. |
| `user-generation` | `generate_items_after` | An empty `AssetSet`. |
| `user-generation` | `get_commands_to_run_after` | No commands. |

It inherits `add_user_to_builder()` with its `email_as_username` check,
`default_managed()` (`True`), `validate_user()` (nothing to say) and
`validate_attributes()` (any declared attributes are reported as
unsupported).

## Emission

With a `type: dummy` user builder in the tree, the identity lifecycle would
write `generated/identity/<builder name>/user-generation/Dummy-tf/dummy_users.tf`
with one comment line, and nothing else; the group builder writes nothing.
The frozen fixture declares neither, so the golden emission under
[tests/fixtures/v2_golden/generated](../../tests/fixtures/v2_golden/generated)
carries no dummy output.

The hook plugin's emission is outside `generated/`: one JSON line appended
to the file named by `CSIS_NOTIFY_FILE` after every run, and, with
`CSIS_DUMMY_LIFECYCLE` set, a `generated/notify/.gitignore` and a `notify`
section in `generated/final_execution.sh`.
[tests/test_v2_explore_plugin_hooks.py](../../tests/test_v2_explore_plugin_hooks.py)
pins both: the notifier records the run id and the requested lifecycles;
the `notify` lifecycle takes its place after the four built-in lifecycles,
runs, and reports `no-script` at apply time.

## Example configuration

The plugin is configured through its entry points (above) and two
environment variables:

| Variable | Effect |
|---|---|
| `CSIS_NOTIFY_FILE=/path/to/notify.jsonl` | The notifier appends a line per run. |
| `CSIS_DUMMY_LIFECYCLE=1` | The `notify` lifecycle is registered. |

No file under
[tests/fixtures/config/cfg](../../tests/fixtures/config/cfg) selects the
builders. An entry that would, shown only to illustrate the shape (the
fixture's real group and user builders are Okta ones in
[group-builders.yml](../../tests/fixtures/config/cfg/group-builders.yml)):

```yaml
group_builders:
  - name: dummy-groups
    type: dummy
    org: example-org
    team: example-team

user_builders:
  - name: dummy-users
    type: dummy
    org: example-org
    team: example-team
    email_as_username: false
    default_user_email_template: "{{ user.name }}@example.invalid"
```

## Using it as a template

To write a new builder plugin: copy this package, rename the `cs_image_system.<name>`
module, keep one model per builder type extending the base model for that
classification (`GroupBuilderModel`, `UserBuilderModel`,
`StorageBuilderModel`, ...), give each model and builder the same
`csis_name()` (the `type:` key), list them in the metadata's services and
`builders_for_models`, and declare the entry point under the
`cs_image_system.plugins.<kind>` group for the builder kind (`runtime`,
`state`, `modification`, `storage`, `group`, `user`, `image`, `os`,
`instance`, `other`; the list is `PLUGIN_TYPES` in
[constants.py](../base/src/cs_image_system/base/constants.py)). To write a
hook plugin: return a `HookSet` from an entry point in the
`cs_image_system.plugins.hooks` group. Registration is validated: a
lifecycle cannot reuse a built-in name, its `after` anchor must exist, and
registering the same name twice with a different definition is an error.
A second worked example lives under
[docs/example-plugin/plugin-b](../../docs/example-plugin/plugin-b).

## Related

- Base classes: [group_builder.py](../base/src/cs_image_system/base/models/group_builder.py), [user_builder.py](../base/src/cs_image_system/base/models/user_builder.py), [builder_base.py](../base/src/cs_image_system/base/basic/builder_base.py), [builder_base_group.py](../base/src/cs_image_system/base/basic/builder_base_group.py), [builder_base_user.py](../base/src/cs_image_system/base/basic/builder_base_user.py), [abstract_plugin_metadata.py](../base/src/cs_image_system/base/basic/abstract_plugin_metadata.py).
- Plugin loading: [loader.py](../base/src/cs_image_system/base/loader.py) (builder plugins), [run_lifecycles.py](../base/src/cs_image_system/base/commands/run_lifecycles.py) (hook plugins and `HookSet`), [lifecycles.py](../base/src/cs_image_system/base/lifecycles.py) (`LifecycleSpec`).
- The real identity plugin the fixture uses: [okta-opa-plugin](../okta-opa-plugin).
- [aws-runtime-plugin](../aws-runtime-plugin/README.md) and [gcloud-runtime-plugin](../gcloud-runtime-plugin/README.md), which import this package.
- [docs/PLUGINS.md](../../docs/PLUGINS.md) for the package index; [docs/DESIGN.md](../../docs/DESIGN.md) for the design.

- [The configuration reference](../../docs/CONFIGURATION.md) — every field of the YAML this plugin reads, with an example.
