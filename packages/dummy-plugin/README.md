# cs-image-system-dummy-plugin

The extension template and test double. It exists to show, in the smallest
working form, the two ways a package extends the system: a *builder plugin*
that registers model and builder classes selectable from YAML, and a *hook
plugin* that participates in the runner without any YAML at all. It
registers a `dummy` group builder and a `dummy` user builder that generate
almost nothing, an on-summary notifier, and an optional `notify` lifecycle.
Nothing in the frozen fixture selects its builders; the runner's tests
exercise its hooks. Copy it to start a new plugin.

Two things to know before copying it. First, the builders are a template
of the *shape*, not a working example: as of 2026-09-23 declaring either
one in a tree makes the identity lifecycle fail at generation (see
[When it fails](#when-it-fails)); the hook plugin is the part the tests
prove. Second, the package has no tests of its own; the repository's
[tests/test_v2_explore_plugin_hooks.py](../../tests/test_v2_explore_plugin_hooks.py)
covers the hooks and nothing covers the builders.

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
and whose `builders_for_models` names a builder class per model class.
The entry-point group is `runtime`, but the group only decides load order:
the loader ([loader.py](../base/src/cs_image_system/base/loader.py))
registers each class under the classification its own `csis_classifier()`
reports.

| Class | `csis_name()` | `csis_classifier()` | Registered under |
|---|---|---|---|
| `DummyGroupBuilderModel` ([dummy_models.py](src/cs_image_system/dummy_plugin/dummy_models.py)) | `dummy` | `VCT.GROUP_BUILDER_MODEL` | `group_builder_model` |
| `DummyGroupBuilder` ([dummy_builders.py](src/cs_image_system/dummy_plugin/dummy_builders.py)) | `dummy` | `VCT.GROUP_BUILDER` | `group_builder` |
| `DummyUserBuilderModel` ([dummy_models.py](src/cs_image_system/dummy_plugin/dummy_models.py)) | `dummy` | `VCT.USER_BUILDER_MODEL` | `user_builder_model` |
| `DummyUserBuilder` ([dummy_builders.py](src/cs_image_system/dummy_plugin/dummy_builders.py)) | `dummy` | `VCT.USER_BUILDER` | `user_builder` |

How a model finds its builder: not through `builders_for_models`. The
registry ([registry.py](../base/src/cs_image_system/base/registry.py))
stores that map (and refuses a model class bound twice), but the lookup
the context performs when it builds a declared builder
(`Registry.get_builder_for_model(type_name, classification)`) goes by the
service registry: the class registered under the same `csis_name()` and
the builder classification. That is why model and builder must report the
same name. `Registry.get_builder(model_type)`, the reader of the
`builders_for_models` map, has no callers.

A `group_builders:` entry selects the group pair with `type: dummy`; a
`user_builders:` entry selects the user pair with the same key. There are
no type aliases. The constant `DUMMY = "dummy"` in `dummy_models.py` is the
key. The AWS and GCE runtime plugins each carry an unregistered copy of
`DummyGroupBuilderModel` (in `aws_runtime_models.py` and
`gcp_runtime_models.py`) left from the template; they import nothing from
this package and do not depend on it.

The second is a hook plugin. `initialize()` in
[hooks.py](src/cs_image_system/dummy_plugin/hooks.py) returns a `HookSet`
(defined in
[run_lifecycles.py](../base/src/cs_image_system/base/commands/run_lifecycles.py))
carrying:

| Hook | Registered | What it does |
|---|---|---|
| `on_summary`: `notify_summary` | always | When the environment variable `CSIS_NOTIFY_FILE` names a file, appends one JSON line per run: `{"run", "ok", "requested", "apply"}`. Unset, it logs at debug level and does nothing. |
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
| `key` | `str` | `default` | Placeholder for a provider key name. Nothing reads it; a credential value never belongs in the tree. |
| `secret` | `str` | `default` | Placeholder; same rule. |
| `api_host` | `str` | `default` | Placeholder for a provider host. Nothing reads it. |

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
| `email_domain` | `str` or null | null | The domain half of a derived address: when set and the email template contains `{{ builder.email_domain }}`, `get_user_email_template()` substitutes it in Python before the template renders. |
| `email_as_username` | `bool` | `True` | When true, `UserBuilderBase.add_user_to_builder()` requires `user.name` to equal `user.email` (case-folded) and fills a blank name from the email. |
| `name`, `type`, `description`, `aliases`, `executable`, `is_default`, `config`, `gitignore`, `tags` | | | From `BuilderModel`/`NameTyped`. |

It carries the bare class attribute `type = "dummy"` and overrides
`csis_name()` to return `dummy`. The class attribute is inert: it is not
annotated, so pydantic does not treat it as a field, and the YAML `type:`
key is still required (a model built without it fails with
`type: Field required`). It does not narrow or add validation.

## The builder

Both builders implement the six generation hooks of `BuilderBase` in
[builder_base.py](../base/src/cs_image_system/base/basic/builder_base.py):
`generate_items_before`, `get_commands_to_run_before`,
`generate_items_during`, `get_commands_to_run_during`,
`generate_items_after`, `get_commands_to_run_after`. The runner calls each
with a lifecycle phase; a builder answers with assets to write (an
`AssetSet` of path and content) or commands to run (a `CFExecutables` of
commands now and commands at finalization). The base class returns an
`AssetSet` from every `generate_items_*` hook; the two dummy builders
return a plain `list` from `generate_items_during`, which is the defect
described under [When it fails](#when-it-fails).

### `DummyGroupBuilder`

Extends `GroupBuilderBase` in
[builder_base_group.py](../base/src/cs_image_system/base/basic/builder_base_group.py).
Every hook returns empty, in the order the group lifecycle runs them:

| Phase | Hook | Returns |
|---|---|---|
| `group-generation` | `generate_items_before` | An empty `AssetSet`. |
| `group-generation` | `get_commands_to_run_before` | No commands. |
| `group-generation` | `generate_items_during` | An empty `AssetSet` (since stage 63 item 1; a plain `list` until then, which the runner's `.sort_and_write()` call broke on). |
| `group-generation` | `get_commands_to_run_during` | No commands. |
| `group-generation` | `generate_items_after` | An empty `AssetSet`. |
| `group-generation` | `get_commands_to_run_after` | No commands. |

It inherits the identity contract unchanged: `identity_type()` is `dummy`
(the default is the plugin's name), so a base image declaring
`identity_types: [dummy]` bakes nothing for it (`base_image_prerequisites`,
`verify_commands`, `activation_commands`, `activation_verify_commands` and
`launch_parameters` are the empty base defaults, `enrollment_token_reference`
is `None`); `gid_policy()` is `provider-assigned`; `query_state()`,
`query_attributes()`, `attribute_conflicts()` and `export_gids()` raise
`NotImplementedError`, so the state query and the attributes probe leave it
out of the picture, while the gid shim reports the error (see
[What it tests and verifies](#what-it-tests-and-verifies)). The stage-55
server registry (`can_query_servers()` is `False`, `registered_servers()`
is `None`, `retire_servers_named()` raises), the stage-56 workload access
(`can_manage_workload_access()` is `False`, `workload_access_expected()`
and `workload_access_state()` are `None`, `ensure_workload_access()`
raises) and the stage-61 `prune_stale_attachments()` (returns 0, does
nothing) are likewise the base defaults.

### `DummyUserBuilder`

Extends `UserBuilderBase` in
[builder_base_user.py](../base/src/cs_image_system/base/basic/builder_base_user.py).

| Phase | Hook | Returns |
|---|---|---|
| any | `query_existing_users()` | An empty list. Plugin-local: nothing in the core calls it. |
| any | `get_subpath()` | `Path("Dummy-tf")`, the directory its assets go under. Plugin-local: only `generate_items_before` reads it. |
| `user-generation` | `generate_items_before` | One asset: `Dummy-tf/dummy_users.tf` containing a single comment line naming the builder class. |
| `user-generation` | `get_commands_to_run_before` | No commands. |
| `user-generation` | `generate_items_during` | An empty `AssetSet` (since stage 63 item 1). |
| `user-generation` | `get_commands_to_run_during` | No commands. |
| `user-generation` | `generate_items_after` | An empty `AssetSet`. |
| `user-generation` | `get_commands_to_run_after` | No commands. |

It inherits `add_user_to_builder()` with its `email_as_username` check,
`default_managed()` (`True`), `validate_user()` (nothing to say),
`validate_attributes()` (any declared attributes are reported as
unsupported) and `query_attributes()` (raises `NotImplementedError`).

## Emission

With a `type: dummy` user builder in the tree, the identity lifecycle's
before-phase hook writes `generated/identity/Dummy-tf/dummy_users.tf` with
one comment line. The path is relative to the lifecycle directory, not to
a builder directory: the dummy builder does not prefix its assets with
`get_builder_path()` or the phase the way the real plugins do (compare the
`<builder>/<phase>/...` convention in
[OPERATIONS.md](../../docs/OPERATIONS.md)). The group builder writes
nothing. The run then fails in the same phase's during step, so that file
is all a run with a dummy builder ever produces (reproduced 2026-09-23 over
a copy of the frozen fixture). The frozen fixture declares neither, so the
golden emission under
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
[group-builders.yml](../../tests/fixtures/config/cfg/group-builders.yml)).
Do not add it to a tree you intend to run: it loads and validates, and the
identity lifecycle then fails at generation (see
[When it fails](#when-it-fails)).

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
[constants.py](../base/src/cs_image_system/base/constants.py)). Return an
`AssetSet` from every `generate_items_*` hook, not a list. To write a
hook plugin: return a `HookSet` from an entry point in the
`cs_image_system.plugins.hooks` group. Registration is validated: a
lifecycle cannot reuse a built-in name, its `after` anchor must exist, and
registering the same name twice with a different definition is an error.
A second worked example lives under
[docs/example-plugin/plugin-b](../../docs/example-plugin/plugin-b).

## Prerequisites and integration

Nothing beyond the core. The plugin touches no account, cloud API, IAM
role, external tool, credential or network; it never calls
`get_executable_copy()`, so it needs no executable declared. What it does
need:

- **The package installed** in the same environment as the CLI. Both entry
  points are discovered through `importlib.metadata`, so an uninstalled
  package registers nothing: `type: dummy` is then an unknown type and the
  `notify` lifecycle does not exist. In this repository it is a workspace
  member pinned by the root `cs-image-system` metapackage; `just init`
  installs it. Its own requirements ([pyproject.toml](pyproject.toml)) are
  Python 3.13 or newer, `cs-image-system-system` at the same version (the
  CLI package, which brings the base) and `pydantic` 2.13 or newer.
- **Two environment variables**, both optional, both read by
  [hooks.py](src/cs_image_system/dummy_plugin/hooks.py) straight from
  `os.environ`:

  | Variable | Read when | Effect |
  |---|---|---|
  | `CSIS_NOTIFY_FILE` | at the end of every run, inside `notify_summary` | The path of a file the notifier appends to (`open(path, "a")`). The directory must already exist; the file is created on first use. Unset or empty: the notifier logs `dummy notifier: CSIS_NOTIFY_FILE unset; nothing to do` at debug level and returns. |
  | `CSIS_DUMMY_LIFECYCLE` | once per process, when `load_hook_plugins()` first runs `initialize()` | Any non-empty value registers the `notify` lifecycle. It is read at load, not at run: setting it after the hooks have loaded changes nothing until a new process (the loader keeps a `_HOOK_PLUGINS_LOADED` flag; only `force=True`, which the tests use, reloads). |

- **When the hooks load.** `load_hook_plugins()` runs at the start of
  `run_lifecycles()` and `validate_only()` in
  [run_lifecycles.py](../base/src/cs_image_system/base/commands/run_lifecycles.py),
  and the `run` command in
  [cli.py](../system/src/cs_image_system/system/cli.py) calls it before it
  resolves lifecycle names, so `notify` is a valid name for `run notify`
  and part of `run --all` in the same process (the reason is a failure
  that happened; see [When it fails](#when-it-fails)).
- **The `key`, `secret` and `api_host` fields are not credentials.** They
  are accepted and never read; the plugin has no provider to talk to. A
  credential value never belongs in the tree, encrypted or not.

## Configuration reference

The plugin owns two list entries of the configuration tree, one under
`group_builders:` and one under `user_builders:`, both selected by
`type: dummy`. The manual's general builder fields are in
[CONFIGURATION.md](../../docs/CONFIGURATION.md) section 4.1; what follows
is every field these two models accept and what, if anything, reads it.

### Common builder fields (both models)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | The builder's name; normalised by `safe_name`, must not contain `/` or `\`, must not be `default`, `self` or empty, and must be unique within its list. Users and groups name it in their own `type:` to attach to it. |
| `type` | str | required | Must be `dummy` to select this plugin's pair. Any other value selects another plugin or is unknown. |
| `description` | str or null | null | Accepted, not read by anything in this plugin's path. |
| `aliases` | set of str | empty | Alternative names, normalised like `name` and registered at load; an alias already registered under the same classification is refused. |
| `executable` | str or null | null | Accepted, not read: the dummy builders run no commands and never resolve an executable. |
| `is_default` | bool | `false` | Whether users (or groups) that declare no `type:` attach to this builder. Exactly one builder per list must be the default, dummy or otherwise; two is an error, none is an error. |
| `config` | dict | empty | Accepted, not read. |
| `gitignore` | list of str | empty | Accepted, not read. |
| `tags` | dict of str | empty | Accepted, not read. |

### `group_builders:` entry (`DummyGroupBuilderModel`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `org` | str | required | Accepted, not read. |
| `team` | str | required | Accepted, not read. |
| `key` | str | `default` | Accepted, not read. Never a credential. |
| `secret` | str | `default` | Accepted, not read. Never a credential. |
| `api_host` | str | `default` | Accepted, not read. |

### `user_builders:` entry (`DummyUserBuilderModel`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `org` | str | required | Accepted, not read. |
| `team` | str | required | Accepted, not read. |
| `default_user_email_template` | str | `{{ user.name }}` | Read by the core's template resolution for a user that declares no `email`. |
| `default_user_description_template` | str | `User {{ user.name }} / {{ user.email }}` | Read by the core's template resolution for a user that declares no description. |
| `email_domain` | str or null | null | Folded into the email template in place of `{{ builder.email_domain }}` by `get_user_email_template()`; ignored when the template has no placeholder. |
| `email_as_username` | bool | `true` | Read by the inherited `add_user_to_builder()` at load. |

### Items that attach to these builders

Users ([user.py](../base/src/cs_image_system/base/models/user.py)) and
groups carry a `type:` whose default is `default`. The context
([global_context.py](../base/src/cs_image_system/base/global_context.py))
resolves `default` to the list's default builder and any other value to a
builder by name or alias, then calls the builder's `add_user_to_builder()`
or `add_group_to_builder()`. So `type: dummy-users` on a user attaches it
to the example builder above; a user with no `type:` goes to whichever
user builder is `is_default: true`.

### Environment

| Variable | Type | Default | Meaning |
|---|---|---|---|
| `CSIS_NOTIFY_FILE` | path | unset | See [Prerequisites and integration](#prerequisites-and-integration). |
| `CSIS_DUMMY_LIFECYCLE` | any non-empty string | unset | See [Prerequisites and integration](#prerequisites-and-integration). |

### Variations

- **When `CSIS_DUMMY_LIFECYCLE` is set**, `initialize()` returns a
  `HookSet` carrying `LifecycleSpec(name="notify", after=None)` and the
  runner registers it: `notify` appears last in `all_lifecycles()`, joins
  `run --all`, is accepted by `run notify`, gets `generated/notify/`
  (wiped and regenerated with a `.gitignore` each time it is requested)
  and a `notify` section in `final_execution.sh`. Unset, the `HookSet`
  carries no lifecycle, `run notify` is refused as an unknown lifecycle,
  and `run --all` is the built-ins plus whatever other plugins register.
- **When `CSIS_NOTIFY_FILE` is set**, every run (successful, failed, dry or
  real, validation-refused included, because the summary hooks run in the
  runner's `finally`) appends one line to it and logs
  `dummy notifier: appended run <id> to <path>` at info level. Unset, it
  logs at debug level and does nothing.
- **Dry run versus real run**: the notifier writes whatever the summary
  holds, so the line's `apply` map shows `dry-run` per lifecycle under the
  default dry run and `executed` under `--no-dry-run`; the `notify`
  lifecycle itself reports `no-script` either way because it defers no
  command and so writes no runner script. With apply switched off
  (`apply=False` in the runner) every lifecycle reports `not-attempted`.
- **`email_as_username: true` (the default)** makes the load refuse a user
  whose `name` differs from its `email` (case-folded) and fill a blank name
  from the email; `false` attaches the user as declared.
- **`email_domain` set** substitutes into the email template only when the
  template contains `{{ builder.email_domain }}`; otherwise it is ignored.
- **`is_default: true`** on a dummy builder routes every user (or group)
  without a `type:` to it; `false` leaves the builder with only the items
  that name it. In a tree whose only user builder is a dummy one, it must
  be the default or the load fails.
- **Declared versus not declared**: with no `type: dummy` entry the
  builder plugin does nothing at all; the four classes sit in the registry
  and no code path reaches them. With one declared, the load and
  validation succeed and the identity lifecycle fails at generation.
- **One runtime versus another, `--only-runtime`, `--apply-runtime`**:
  no effect. The models carry no `runtime` field and identity builders are
  not runtime-scoped, so a scoped run treats them like any identity
  builder.
- **Encrypted versus clear values**: the plugin has no encryption-specific
  behaviour; it reads none of its own fields, so a marker in `org` or
  `team` is decrypted or not by the core alone.
- **`validate` versus `run`**: both load the hook plugins, so the `notify`
  lifecycle exists for both when the variable is set; neither exercises
  the notifier differently.

## What it tests and verifies

The plugin adds no checks of its own: its `HookSet` has empty
`validators`, `after_generate`, `before_apply` and `after_apply` lists,
its builders validate nothing and its `validate_user()` returns nothing.
What is checked around it, and where the verdict lands:

- **At load (pydantic, model construction).** `org` and `team` must be
  present (`org: Field required`); an unknown key is refused
  (`Unexpected keyword argument`, `extra="forbid"`); the retired
  `parameters:` key is refused with the stage-26 message; `name` and
  `aliases` are checked for `/`, `\` and the reserved words; the YAML
  reader refuses a duplicate `name` in the list and template markers in
  `name` or `type`. After construction the context refuses two defaults
  (`Multiple default builders found`), no default
  (`No default builder found in <classification> list.`), a user or
  group naming a builder that is not declared
  (`users builder '<type>' specified for '<name>' not configured`), and,
  through `add_user_to_builder()`, a name/email mismatch under
  `email_as_username`. Every one of these is a `ValueError` (pydantic's
  `ValidationError` is one) raised while the configuration loads, before
  any lifecycle: the CLI exits non-zero with the message; no run summary
  is written because there is no run.
- **At `validate` (and at the start of every run).** The core's
  `validate_identity_items` in
  [identity_attributes.py](../base/src/cs_image_system/base/identity_attributes.py)
  asks the owning builder about each user and group. For a dummy builder
  that yields one error string per item that declares `attributes:`
  (`user '<name>': builder <builder> (dummy) supports no attributes
  (declared [...])`) and nothing otherwise. `validate_base_images` in
  [v2_validation.py](../base/src/cs_image_system/base/v2_validation.py)
  accepts `identity_types: [dummy]` on a base image exactly when a dummy
  group builder is declared (its `identity_type()` is `dummy`), and
  `validate_capabilities` accepts an instance image whose group is
  attached to a dummy builder when its root base declares `dummy`. Errors
  land as `validation: <message>` log lines, in `validation_errors` of the
  run summary (`generated/run-summary.json`), in the run's entry in
  `meta-state/runs.yaml` (`error: LifecycleRunError: Validation failed
  with N error(s)`) and in the notifier's line (`"ok": false`).
- **At generation.** Nothing is verified. The dummy builders' before and
  after hooks return empty or one asset and no commands; the during step
  currently fails (below).
- **At apply.** Nothing. The builders defer no commands, so no runner
  script names them; the `notify` lifecycle has no phases and no script
  and reports `no-script` in the summary's `apply` map.
- **After apply.** No `after_apply` hooks. The `on_summary` notifier runs
  after every run, including failed ones; it never changes the verdict
  and cannot fail the run (the runner logs a failing notifier and moves
  on).
- **In the state query** ([state_query.py](../base/src/cs_image_system/base/state_query.py)):
  `query_state()` raises `NotImplementedError`, which the query treats as
  "not part of the picture": groups under a dummy builder appear nowhere
  in `generated/state-report.json`, not even under `unavailable`. The
  identity attributes probe lists them instead:
  `groups/<name>: dummy cannot query attributes` under `unavailable`, and
  skips `attribute_conflicts()`. The identity read-model written after
  the identity lifecycle records each attached group with
  `identity_type: dummy` and `gid_policy: provider-assigned`, and each
  dummy user builder as `<name>: dummy`.
- **The gid shim** (`cs-image-system identity export-gids`, in
  [identity_gids.py](../base/src/cs_image_system/base/commands/identity_gids.py))
  does not skip it: a query naming `identity_type: dummy` finds
  `DummyGroupBuilder`, whose `export_gids()` raises, and the command
  prints `export-gids: DummyGroupBuilder does not implement a gid shim;
  its terraform root must expose gids some other queryable way (N7)` on
  stderr and exits 1. Nothing emits such a query for a dummy builder;
  this is what would happen if something did.
- **Lifecycle registration** ([lifecycles.py](../base/src/cs_image_system/base/lifecycles.py)):
  when the `notify` spec is installed, `register_lifecycle` verifies the
  name is not a built-in, not `all`, not empty and has no `/`, that the
  `after` anchor (here none) exists, and that a spec already registered
  under the name is equal. Re-registering the identical spec (the tests'
  `force=True` reload) is a no-op.

## When it fails

Failures that have happened, first.

- **2026-08-27, the `notify` lifecycle leaked into every run.** The first
  version of [hooks.py](src/cs_image_system/dummy_plugin/hooks.py)
  registered `notify` unconditionally; because a registered lifecycle
  joins `run --all`, every golden and gate run of the exploration branch
  grew a `generated/notify/` directory and a fifth lifecycle. Symptom: an
  unexpected `notify` entry in run summaries and golden diffs. Fix: the
  lifecycle is opt-in behind `CSIS_DUMMY_LIFECYCLE`. Recorded in
  [docs/history/EXPLORE.md](../../docs/history/EXPLORE.md) ("Expanding
  What Else Plugins Could Do", findings). If `notify` appears in a run you
  did not ask for it in, the variable is set in that shell.
- **2026-09-08, hook plugins loaded after the lifecycle names resolved
  (finding 62).** A fresh CLI process resolved `run --all` to the four
  built-ins because `load_hook_plugins()` ran only inside
  `run_lifecycles()`; every plugin-registered lifecycle (`release` then,
  `notify` alike) was silently absent from `--all` and `run <name>` was
  refused with `Unknown lifecycle '<name>'; expected one of [...]` and
  exit code 2. Fix: the `run` command loads the hooks before parsing
  names. Recorded in [docs/history/LEDGER.md](../../docs/history/LEDGER.md)
  (Stage 1 live-run findings, 61 to 64) and in the same ledger's release
  cycle, where the registration test of the `release` lifecycle turned
  out to pass only after another test had loaded the hook plugins; it now
  loads them itself. If `run notify` is refused although the variable is
  set, check that the command path loads the hooks before it resolves
  names (a library caller must call `load_hook_plugins()` before
  `parse_lifecycles()`).
- **A declared `type: dummy` builder used to fail the identity lifecycle**
  (reproduced over a copy of the frozen fixture on 2026-09-23; never live,
  since no tree declares one). Both builders' `generate_items_during`
  returned a plain `list` where the contract wants an `AssetSet`, and the
  during step ([gen_users.py](../base/src/cs_image_system/base/commands/gen_users.py),
  [gen_groups.py](../base/src/cs_image_system/base/commands/gen_groups.py))
  died on `.sort_and_write()`:

  ```text
  ERROR cs_image_system.base.commands.run_lifecycles:AttributeError: 'list' object has no attribute 'sort_and_write'
  ```

  Fixed in stage 63 item 1 (2026-09-24): both return `AssetSet()`, and a
  declared dummy builder with a group on it now loads, validates and runs
  the identity lifecycle dry, emitting nothing (`tests/test_v2_defects_low_hanging.py`).
## Related

- Base classes: [group_builder.py](../base/src/cs_image_system/base/models/group_builder.py), [user_builder.py](../base/src/cs_image_system/base/models/user_builder.py), [builder_base.py](../base/src/cs_image_system/base/basic/builder_base.py), [builder_base_group.py](../base/src/cs_image_system/base/basic/builder_base_group.py), [builder_base_user.py](../base/src/cs_image_system/base/basic/builder_base_user.py), [abstract_plugin_metadata.py](../base/src/cs_image_system/base/basic/abstract_plugin_metadata.py).
- Plugin loading: [loader.py](../base/src/cs_image_system/base/loader.py) (builder plugins), [run_lifecycles.py](../base/src/cs_image_system/base/commands/run_lifecycles.py) (hook plugins and `HookSet`), [lifecycles.py](../base/src/cs_image_system/base/lifecycles.py) (`LifecycleSpec`).
- The real identity plugin the fixture uses: [okta-opa-plugin](../okta-opa-plugin).
- [aws-runtime-plugin](../aws-runtime-plugin/README.md) and [gcloud-runtime-plugin](../gcloud-runtime-plugin/README.md), which carry an unregistered copy of the group model.
- [docs/PLUGINS.md](../../docs/PLUGINS.md) for the package index; [docs/DESIGN.md](../../docs/DESIGN.md) for the design.
- [The configuration reference](../../docs/CONFIGURATION.md) -- every field of the YAML this plugin reads, with an example.
