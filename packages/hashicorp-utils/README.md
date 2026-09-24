# cs-image-system-hashicorp-utils

A library for cs-image-system plugins that emit HashiCorp configuration:
terraform (OpenTofu) roots and packer templates. It collects provider,
plugin, backend and variable requirements per workspace, renders HCL
blocks in memory, and gives a builder that owns a terraform root its
`init`, `plan`, gate and `apply` command sequence.

**This is a library, not a plugin.** It declares no
`cs_image_system.plugins.*` entry point, registers nothing in the registry
and contributes no builder of its own. Plugins import it. In the
workspace, nine packages depend on it directly: the terraform-root plugins
(`okta-opa-plugin`, `tf-ebs-instance-plugin`, `tf-gcp-plugin`) mix in the
root mixin and drive the terraform collector; the state plugins
(`tf-s3-state-plugin`, `local-state-plugin`, `gcs-state-plugin`) register
their backends into it; `packer-plugin` uses the packer collector; the two
runtime plugins (`aws-runtime-plugin`, `gcloud-runtime-plugin`) import the
formatter options. The base library does not depend on it, but imports the
terraform collector guarded by an `ImportError` fallback to list the state
files each lifecycle's workspaces bind to, to record state locations and
to check for collisions at `validate`.

Licensed under Apache-2.0. Requires Python 3.13 or later. Declared
dependencies: `cs-image-system-system`, `cs-image-system-base`,
`packaging`, `python-hcl2`.

## Contents

- [Modules](#modules)
- [TerraformCollector](#terraformcollector)
- [PackerCollector](#packercollector)
- [TerraformRootMixin](#terraformrootmixin)
- [HCL rendering helpers](#hcl-rendering-helpers)
- [Versions](#versions)
- [Tests](#tests)
- [Prerequisites and integration](#prerequisites-and-integration)
- [Configuration reference](#configuration-reference)
- [What it tests and verifies](#what-it-tests-and-verifies)
- [When it fails](#when-it-fails)

## Modules

| Module | Provides |
| -------- | ---------- |
| [`collector.py`](src/cs_image_system/hashicorp_utils/collector.py) | `TerraformCollector`, `PackerCollector`, the declaration dataclasses `ProviderRequirement`, `ConfiguredTerraformProvider`, `ProviderConfig`, `TerraformVariable`, `BackendRegistration`, `RemoteStateReference`, `PackerPluginRequirement`, `PackerVariableDecl`, the `StateLocation` tuple and the `BackendKind` protocol. |
| [`roots.py`](src/cs_image_system/hashicorp_utils/roots.py) | `TerraformRootMixin` and `run_is_dry()`. |
| [`blocks.py`](src/cs_image_system/hashicorp_utils/blocks.py) | The declarative block model: `Raw`, `hcl_value`, `NestedBlock`, `BlockSpec`, `ResourceSpec`, `DataSpec`, `OutputSpec`, `render_block`, `render_blocks`. |
| [`hashicorp.py`](src/cs_image_system/hashicorp_utils/hashicorp.py) | The formatter options `FO`, the `QString` quoting wrapper, the `TerraformGenerator` protocol, `packer_variable`, and the S3-backend field dataclasses `TStateRoot`, `StateEndpoints`, `AssumeRoleBaseClass`, `AssumeRoleConfig`, `AssumeRoleWithWebIdentityConfig`. |
| [`hashicorp_models.py`](src/cs_image_system/hashicorp_utils/hashicorp_models.py) | `TFTofuPluginModel` and `PackerPluginConfig`, both `GenericPluginModel` subclasses (`name`, `version`, `source`, `config`) that builders use for their `required_providers:` / `required_plugins:` lists. |
| [`versions.py`](src/cs_image_system/hashicorp_utils/versions.py) | Constraint normalization, merging and conflict detection; `HclConfigConflictError`. |

Nothing in this package writes files. Every generator returns a list of
HCL lines; the consuming builder places them into an asset for the runner
to write.

## TerraformCollector

`TerraformCollector` is a process-wide singleton (`TerraformCollector()`
returns the same object) with `reset()` for a fresh run or test isolation.
Registrations persist for the run and are keyed by **workspace**, which is
a builder name and therefore one HCL root directory. Plugins declare what
they need; the collector dedupes, merges and validates, and renders.

### Registration

| Method | Effect |
| -------- | -------- |
| `require_provider(workspace, name, source=None, version=None, requested_by=None)` | Adds a provider requirement. An identical requirement is ignored. `requested_by` defaults to the workspace and is what a conflict message names. |
| `configure_provider(workspace, name, config, alias=None)` | Records a `provider "<name>" {}` block. The alias defaults to the sanitized workspace name, so provider blocks from different builders never collide when aggregated. Configuring the same name and alias twice with different arguments raises `HclConfigConflictError`. |
| `provider_bindings(workspace)` | `{provider name: "<name>.<alias>"}` for every configured provider, for a module call's `providers = { ... }` meta-argument. Module calls must bind explicitly, because every configured provider carries an alias. |
| `declare_variable(workspace, TerraformVariable(name, type="string", default=None, description=None, sensitive=False))` | Declares a `variable` block. Redefinition with different attributes raises `HclConfigConflictError`. |
| `register_backend(BackendRegistration(...))` | Makes a state backend available for the run (registered by a state plugin). Registering the same name with a different declaration raises. |
| `set_backend(workspace, backend_name="default")` | Binds a workspace to a backend; `default` resolves to the registration marked `is_default`. More than one default is a conflict. A second binding to a **different** backend is refused (a workspace keeps its state in exactly one location, stage 46); rebinding to the same one is a no-op, so a builder may bind per phase. |
| `effective_backend_name(*candidates)` | The chain a root's backend resolves through (stage 46.2): the first candidate outside the loader's absent sentinels (`default`, `self`, empty, unset), else `default`. Static. |
| `bind_workspace(workspace, *candidates)` | `set_backend` through the chain; returns the name bound. The terraform-root builders call it with `(own state_configuration, runtime's state_configuration)`; the identity roots, which have no runtime, with their own value alone. |
| `reference_remote_state(consumer_workspace, producer_workspace, backend_name=None, label=None)` | The consumer reads the producer's state through a `terraform_remote_state` data source. |
| `sensitive_ref(workspace, key, value)` | See [Sensitive values](#sensitive-values-by-reference). |

`BackendRegistration` fields: `name`, `type` (for example `s3`),
`settings` (the type's own, as an opaque mapping), `kind` (the type's
renderings, supplied by the state plugin that declares it) and
`is_default`. Equality is the declaration (name, type, settings, default);
the kind is behaviour and does not take part in the comparison.
`state_location(workspace)` asks the kind for the `StateLocation`
(`<type>://<container>/<key>`, normalised, stage 46);
`backend_settings(workspace)` and `remote_state_settings(workspace)` for
the partial configuration and the data source (stage 47). The collector
names no field of any type. A registration without a kind is accepted by
`register_backend` and refused the moment anything asks it for a
location, a backend file or a data source.

`StateLocation.of(type, container, prefix, workspace)` is the object-store
convention `<prefix>/<super_safe_name(workspace)>.tfstate`: repeated
slashes collapsed, leading and trailing ones stripped, case kept, a `.` or
`..` segment refused with `ValueError`. Two spellings of one place compare
equal, which is what the collision rule needs.

### Dedupe, merge and conflicts

`merged_providers(workspace)` produces one entry per provider name. Version
constraints are merged: the emitted string is the comma-joined, deduplicated
originals (`">= 4.0.0, < 6.0.0"`) and their conjunction must be
satisfiable. Two sources for the same provider (`hashicorp/aws` and
`mycorp/aws`) are a conflict; sources are compared case-insensitively and
the first spelling seen is the one emitted. `validate_all()` runs the same
checks across every workspace of the run **and** `validate_state_locations()`
(below); every generator calls it first, so a conflict between two
workspaces surfaces at generation even when each workspace is consistent
on its own.

### State locations and collisions

`state_locations()` resolves every bound workspace's `StateLocation`
through its registration, whether or not backends are enabled: the
collision rule is about the declaration, not the emission. Unbound and
unresolvable workspaces are absent from the result. `state_collisions(locations)`
returns one message per location two or more workspaces would share
(`workspaces A, B would share the state object s3://...`), and
`validate_state_locations()` raises `HclConfigConflictError("state location
collision: ...")` when there is one. `backend_record(workspace)` is what
meta-state keeps of where a workspace's state lives (stage 46.4): the
backend's name, type and location over its backend-file settings, enough to
write that file again for a migration's previous location.

### Backend emission and partial configuration

Backend and remote-state emission is gated by the global
`config: use_state_backends` flag (`backends_enabled()`, read from the
run context; any failure to read it counts as off). When it is off,
`workspace_backend()` is `None`, the backend block is omitted and
`generate_backend_config()` and `generate_remote_state_datasources()`
return nothing.

`generate_terraform_block(workspace)` renders

```hcl
terraform {
    required_providers {
        aws = {
            source = "hashicorp/aws"
            version = ">= 4.0.0"
        }
    }

    backend "s3" {

    }
}
```

with the backend block **empty**: this is terraform's partial
configuration. The settings live in the workspace's `.tfbackend.hcl`
file, rendered by `generate_backend_config(workspace)` as a comment line
(`# Backend '<name>' (<type>) partial configuration for workspace <ws>`)
followed by top-level `key = value` lines, booleans lower-case and
everything else quoted. Which keys appear is the kind's decision (stage
47): the S3 kind writes `bucket`, `key`, `region`, `encrypt`,
`use_lockfile` and `profile` when set; the `local` kind writes `path`.
The file is supplied to `init -backend-config=<file>`. That keeps bucket
names and profiles out of the committed `terraform {}` block and lets the
same emission bind to different backends.

`generate_remote_state_datasources(workspace)` renders one
`data "terraform_remote_state" "<label>"` per reference, with `backend`
set to the producer's backend **type** and a `config = { ... }` object
holding whatever the producer's kind returns from `remote_state_settings`
(for S3: `bucket`, `key`, `region` and `profile` when set, never `encrypt`
or `use_lockfile`); the label is the sanitized producer name unless given.
The backend is the reference's named one, else the producer's, else the
default; none at all is a conflict. A consumer in one backend reading a
producer in another gets the producer's settings, whichever type or bucket
that is.

`workspace_backend(workspace)` and `bound_workspaces()` are the
state-isolation evidence: the base runner writes a header line per
workspace (`# state: workspace <ws> -> s3://<bucket>/<key>`) into each
lifecycle's runner script from them.

### Sensitive values by reference

A configuration value may be encrypted (`ENC[age:...]`); the base library
decrypts it at load into a `Decrypted` string that remembers its marker.
Such a value must not appear in plaintext in the emission. The collector
therefore emits it by reference:

1. `sensitive_ref(workspace, key, value)` returns `value` unchanged when it
   carries no marker. When it does, it registers the ciphertext under `key`
   for the workspace, requires the `hashicorp/external` provider, and
   returns `Raw('local.sensitive["<key>"]')`, which renders unquoted.
   Registering a different ciphertext under the same key is a conflict.
   Because it requires a provider, it must be called before
   `generate_terraform_block`.
2. `generate_sensitive_blocks(workspace)` renders, when anything was
   registered, a comment line followed by:

   ```hcl
   data "external" "sensitive" {
       program = [
           "cs-image-system",
           "decrypt",
           "--json",
       ]
       query = {
           <key> = "ENC[age:...]",
       }
   }

   locals {
       sensitive = sensitive(data.external.sensitive.result)
   }
   ```

   Keys are sorted and rendered as written (a key must therefore be a
   valid HCL attribute name). The data source is bound to the workspace's
   configured `external` provider alias (`provider = external.<alias>`)
   when it has one (an identity root that also aliases the provider for
   the gid shim), else the default provider. Since stage 51 a query value
   may be a derived string that carries the marker inside it
   (`first.last@ENC[age:...]`); it is passed through as it is and the
   decrypt program resolves the embedded marker.

The committed emission carries the same ciphertext the configuration
carries. Terraform decrypts it at plan time by running the system's own
`decrypt --json` with the identity in `CSIS_CONFIG_IDENTITY` from the
runner's environment. Plans and state hold the plaintext, which is why they
are never committed (the base package's public-safe gate refuses them by
name). `sensitive_values(workspace)` returns the registered
`{key: ciphertext}` mapping.

### Other generators

| Method | Renders |
| -------- | --------- |
| `generate_provider_blocks(workspace)` | One `provider "<name>" { ...config, alias = "<alias>" }` per configured provider; the config values go through the shared quoting policy (`hcl_value`), so a decrypted value renders as its ciphertext and an address-like string stays raw. |
| `generate_variable_blocks(workspace)` | One `variable "<name>" { type, default, description, sensitive }` per declared variable; a boolean default renders lower-case, any other default goes through `hcl_value` (a string default is quoted, a number raw). |

## PackerCollector

`PackerCollector` is the packer counterpart, also a singleton with
`reset()`.

| Method | Effect |
| -------- | -------- |
| `require_plugin(workspace, name, source=None, version=None, requested_by=None)` | Adds a required plugin; identical requirements dedupe. |
| `declare_variable(workspace, PackerVariableDecl(name, type="string", default=None, description=None, env_var=None, sensitive=False))` | Declares a packer variable; redefinition with different attributes is a conflict. |
| `merged_plugins(workspace)` | One entry per plugin with merged constraints; disagreeing sources are a conflict. |
| `validate_all()` | Run-wide satisfiability per plugin name (sources are not compared run-wide, only per workspace). |
| `generate_packer_block(workspace)` | `packer { required_plugins { <name> = { version, source } } }`. |
| `generate_variable_blocks(workspace)` | `variable "<name>" { type, default, description, sensitive }` blocks through `packer_variable`. With `env_var` the default is `env("<VAR>")` and a `default` given beside it is dropped; a boolean default renders lower-case; a **string default renders unquoted** (see [When it fails](#when-it-fails)). |

## TerraformRootMixin

A builder whose workspace is a standalone terraform root (its own
`terraform {}` block, backend partial-configuration file and tofu command
sequence) mixes `TerraformRootMixin` in next to its `BuilderBase`
subclass. The mixin is duck-typed against `BuilderBase`: it relies on
`self.name`, `self.get_path_for_phase(phase, suffix=...)`,
`self.get_executable_copy()` and, when present, `self._get_context()` and
`self.model`. In the workspace the mixin is on `OktaTfGroupBuilder` (and
its read-only subclass), `OktaTfUserBuilder`, `TofuInstanceBuilder` and
`TofuStorageBuilder`; the GCE instance and GCP storage builders inherit
it from the AWS ones.

### Backend file and init arguments

`_backend_config_path(phase)` is
`<builder>/<phase>/<builder>-<phase>.tfbackend.hcl`, the file
`generate_backend_config` fills.

`_init_args(phase)` is the generation-time `init`:

| Run | Arguments | Why |
| ----- | ----------- | ----- |
| dry run | `init -backend=false` | Providers are installed and the emission validated without touching remote state, which holds decrypted values. A read-only CI role, a drift check and an operator's preview all stay off the state bucket. |
| real run, backend bound | `init -reconfigure -backend-config=<file>` | The bare file name, because tofu runs inside the phase directory. `-reconfigure` because a backend argument may differ from the one the root was last initialised with (`encrypt`, stage 39), and the state is remote, so there is nothing to migrate; without it tofu refuses with "Backend configuration changed". |
| real run, no backend | `init` | Backends disabled, or the workspace bound to nothing. |

"Backend bound" is decided by whether `generate_backend_config(self.name)`
returns lines, so the gate flag and the binding both count.

`run_is_dry(builder)` reads the run context's `dry_run` flag; a builder
used outside a run (no context yet, as in unit tests, where `_get_context`
is absent or raises `ValueError`) is not in a dry run. `_dry_run()` is the
method form.

`_runner_init_args(phase)` is the `init` a committed runner script performs
for itself, always in the real-run form:
`init -input=false -reconfigure [-backend-config=<file>]`. A dry run's
generation-time init was backend-less and a fresh clone has no
`.terraform/` at all, so the script must initialise the root itself. It is
deferred like the plan it precedes, so an in-process real run repeats it
(idempotent, seconds) and the script stays a faithful record of what
finalization executes.

### The runtime rung

`runtime_state_configuration()` returns the `state_configuration` of the
runtime the builder's model names (`model.get_runtime_provider()`), read
from that runtime builder's model in the run context. It is the second
rung of the chain a root's backend resolves through (stage 46.2): the
root's own value when it names a backend, else its runtime's, else the
default. It answers `None` for a root without a runtime (the identity
roots), for a runtime still at `default`, and outside a run. The storage
and instance builders pass it to `bind_workspace` beside their own
`state_configuration`.

### Plaintext reads and the private mirror

`plaintext_read_commands(phase, working_directory, arg_lists)` builds the
generation-time tofu commands that must read the **plaintext** emission.
The committed emission carries `ENC[age:...]` ciphertext (stage 49), and
since stage 51 a derived e-mail address carries it inside the string;
`fmt`, `init` and `validate` do not care, but a real run's generation-time
`plan` does -- the Okta user lookups search by that address. So, exactly as
the deferred runner does, the sequence is:

1. `cs-image-system --root-dir <config root> --no-dry-run [--overlay ...]
   materialize .` in the workspace directory, which copies the root to
   `_private/<the same relative path>` under the configuration root with
   every marker replaced by its plaintext (`mirror_path` in
   [`materialize.py`](../base/src/cs_image_system/base/materialize.py):
   `_private/` stands where `generated/` stands, at the same depth, so
   relative module sources and `local` state paths keep resolving);
2. `_runner_init_args(phase)` **in the mirror** (providers are not
   mirrored, so the copy is initialised there);
3. each of `arg_lists` in the mirror.

Without a configuration root to mirror under (the offline harness's bare
context has no `working_path`) the commands run where they always did. The
identity builders call it for their real-run generation-time `plan` (the
group root with `-refresh=false`); the storage and instance builders do
not plan at generation time at all.

### Command materialization

`terraform_commands(phase, arg_lists, working_directory)` returns one
`ExecutableModel` per argument list, each a fresh `get_executable_copy()`
bound to the workspace directory. A fresh copy per command is mandatory:
`args` and `working_directory` are mutated per command, so sharing one
model would make every command run the last arguments. A `None` working
directory is an assertion failure naming the phase and the builder class;
a builder whose `executable` names no entry in `cfg/executables.yml`
fails inside `get_executable_copy()` with
`Executable '<key>' not found for builder '<name>' of type '<type>'`.

### The gated plan, gate, apply sequence

`gated_apply_commands(phase, working_directory, apply, allow_destroy=(),
replace=(), pre_plan=(), apply_flag_key=None, apply_root=None,
apply_root_aliases=(), plan_extra_args=(), pre_commands=(),
require_unmounted=(), pre_plan_backup=False)` returns the deferred
sequence for a terraform root (DESIGN section 3C, N19), in this order:

1. `rm -f tfplan` -- a failed plan must leave nothing for the gate to read
   (ledger finding 33).
2. `<tofu> init -input=false -reconfigure [-backend-config=<file>]` -- the
   runner's own init. When the root is **migrating** this run (its name is
   in the run context's `migrate_state` list, from
   `run --no-dry-run --migrate-state <root>`), this step is instead
   `cs-image-system ... state-migration begin --workspace <ws> --tofu <bin>
   --backend-config <file> --location <new location> --run <id>` followed
   by `<tofu> init -input=false -migrate-state -force-copy
   -backend-config=<file>`.
3. only when `pre_plan` is non-empty and `pre_plan_backup` is true:
   `cs-image-system ... state-migration backup --workspace <ws> --tofu
   <bin> --run <id>`, which pulls the state the root is initialised
   against and keeps it as
   `_private/state-backups/<ws>.backup-<run>.tfstate` under the
   configuration root (stage 61 item 3: a `state rm` the system decided on
   is preceded by the backup a hand edit would take).
4. each `pre_plan` argument list (for example `state rm <address>` for a
   group leaving management).
5. each `pre_commands` executable, as given (for example the unmount before
   a detach, or the identity runner's `prune-attachments` step).
6. `<tofu> plan -input=false -out=tfplan [-detailed-exitcode]
   [-replace=<address> ...] [plan_extra_args ...]` -- `-detailed-exitcode`
   only when migrating (a change stops the runner: the move is accepted
   only clean); `replace` addresses are forced replacements (an explicit
   upgrade); `plan_extra_args` carries flags such as
   `-var=ephemeral_present=false`.
7. `cs-image-system gate-plan --planfile tfplan --tofu <tofu>
   [--allow-destroy <address> ...] [--require-unmounted <pair> ...]` -- the
   gate. Every `allow_destroy` address and every `replace` address is
   passed as `--allow-destroy`, so a replacement's destroy is whitelisted
   and any other planned destroy fails the gate. Each `require_unmounted`
   pair demands an unmount receipt.
8. only when migrating: `cs-image-system ... state-migration finish
   --workspace <ws> --run <id>`, which records the move in meta-state.
9. only when `apply` is true:
   - when `apply_flag_key` is given, `cs-image-system apply-check
     --lifecycle <key> [--root <apply_root> --root-alias <alias> ...]
     [--overlay <file> ...] [--apply-runtime <rt>]`, re-checking the
     `apply_<key>` flag at execution time so a script generated under
     yesterday's flags cannot apply under today's (ledger finding 24); the
     run's overlays and `--apply-runtime` are carried from the run
     context;
   - `<tofu> apply -input=false tfplan` -- the very plan that passed the
     gate.

The `cs-image-system ...` commands written with an ellipsis above are
built by `system_cli_executable_with_config` in the base library and carry
`--root-dir <configuration root> --no-dry-run [--overlay <file> ...]`
before their own arguments (the runner renders the root as `"$CSIS_ROOT"`);
`gate-plan` and `apply-check` need no configuration and are emitted bare.
`<tofu>` for the system commands is the executable entry's `binary`, else
its `name`.

`apply` is the value of the lifecycle's `apply_<lifecycle>` configuration
flag for this root (`apply_enabled(key, root, aliases)` in the base
library), so a root that is not allowed to apply still plans and gates.
The instance root's ephemeral-teardown sequence passes `apply=True`
because it is only built when the root may apply; `apply-check` still
stands in front of its apply.

## HCL rendering helpers

### Blocks

`blocks.py` is a declarative model for `resource`, `data`, `output` and
other top-level blocks, rendered through `python-hcl2`'s builder so no
plugin touches `hcl2.Builder` or `FormatterOptions` directly.

| Name | Meaning |
| ------ | --------- |
| `Raw(str)` | A string emitted unquoted: an address or expression the quoting policy cannot infer, such as `Raw("oktapam_group.x.id")`. |
| `hcl_value(v)` | The shared quoting policy. `Raw` and `QString` pass through; any other string is first passed through the base library's `emit()`, so a decrypted value becomes the `ENC[age:...]` ciphertext it was read from (stage 49); then a string starting with `var.`, `data.`, `local.`, `module.`, `each.` or `count.` stays raw and any other string is quoted; booleans and numbers stay raw (booleans render lower-case); list elements and mapping values convert recursively. Mapping keys are the caller's responsibility (pre-quote a key such as `'"system.os_type"'`). |
| `BlockSpec(type, label, args, comment=None, commented_out=False, children=[], kind="resource", labels=None)` | A top-level block. The default labels are `"<type>" "<label>"`; `labels` overrides them for single-label kinds (and `labels=[]` gives a label-less block such as `locals`). `comment` prefixes a `# ...` line; `commented_out` emits the whole block as comments. `spec.block(name, **args)` appends a child block and returns it for fluent nesting. |
| `ResourceSpec`, `DataSpec` | `BlockSpec` with `kind` fixed to `resource` / `data`. |
| `OutputSpec(name, value, description=None, sensitive=False, comment=None)` | An `output "<name>" { value = ... }` block. |
| `NestedBlock(name, args, children)` | A child block; `block()` nests further. |
| `render_block(spec)` / `render_blocks(specs, separator="")` | HCL lines, in memory. |

Attributes are set on the builder node after the block is created, so an
HCL attribute may carry any name, including one that collides with the
builder's own parameters (`labels`).

### Primitives

`hashicorp.py` holds `FO` (`FormatterOptions(indent_length=4,
vertically_align_attributes=False)`), `QString(value, quoted=True,
quote_char='"')` (a `str` subclass whose `str()` quotes the value when
`quoted` is set, except a `var.` reference, which always stays raw; the
constructor's effective default is `quoted=True` -- the `__new__` signature
says `False`, but the dataclass initialiser runs after it and wins, so
`QString("x")` renders `"x"`), the `TerraformGenerator` protocol
(`generate_terraform(setup)` and `generate_terraform_data(setup)` returning
lines), `packer_variable(builder, name, type, default, description=None,
env_var=None, sensitive=False, validation=None)` which appends a packer
`variable` block (an `env_var` becomes `default = env("VAR")` and
overrides `default`; `validation` is a `(condition, error_message)` pair),
and the S3-backend field dataclasses (`StateEndpoints` with `dynamodb`,
`s3`, `sts`, `iam`, `sso`; `AssumeRoleConfig` with `role_arn`, `duration`,
`policy`, `policy_arns`, `session_name`, `source_identity`, `tags`,
`transitive_tag_keys`; `AssumeRoleWithWebIdentityConfig` with
`web_identity_token`, `web_identity_token_file`). The S3 state plugin
imports the three dataclasses; the collector does not read them.

Terraform **module calls** are rendered by the base library
(`render_module_call` and `hcl_expr` in `cs_image_system.base.utils`),
not here; this package renders blocks and the collector-level scaffolding.
The same holds for `config: module_source_base`: the base library reads it
when it renders a module call, and nothing in this package does.

## Versions

`versions.py` turns terraform and packer constraint strings into
`packaging` specifier sets for conflict analysis while preserving the
original strings for emission. These are the **provider and plugin**
constraint helpers; the checks on the tools themselves (`tofu --version`
against `cfg/executables.yml`, stage 48) live in the base library, not
here.

| Function | Behaviour |
| ---------- | ----------- |
| `normalize_constraint(spec)` | Comma-separated clauses. `~> X.Y.Z` becomes `>= X.Y.Z, < X.(Y+1).0`; `~> X.Y` becomes `>= X.Y, < (X+1).0`; `~> X` becomes `>= X, < (X+1)`; `= V` and a bare version become `== V`; `>=`, `<`, `!=`, `==` pass through with their whitespace removed. An empty or `None` spec is unconstrained. A clause `packaging` cannot parse raises `ValueError`. |
| `merge_constraints(specs)` | Returns `(emission, combined)`: the deduplicated originals comma-joined (terraform reads a comma as AND) and the conjunction of their normalized forms. |
| `is_satisfiable(combined)` | Whether some version satisfies the conjunction, tested against a finite witness set: every version literal in the clauses plus its micro, minor and major bumps, and `0`. This catches disjoint pins and non-overlapping ranges; unusual gap constructions may pass. |
| `assert_satisfiable(name, requirements)` | For `(constraint, requested_by)` pairs: returns the merged emission string or raises `HclConfigConflictError` naming the provider, each constraint and who requested it. |

`HclConfigConflictError` (a `RuntimeError`) is the one exception both
collectors raise for contradictory requirements.

## Tests

[`tests/`](tests/) pins the collector (workspace isolation, dedupe,
merged version emission, source mismatch, cross-workspace conflict, the
empty backend block and the `.tfbackend.hcl` contents, remote-state data
sources across backends, provider aliases and bindings, variable
redefinition, the state-location tuple and its collisions, the binding
chain, the rebinding refusal, the backend record, a registration without a
kind), the packer collector, the root mixin (dry-run and real-run init
arguments, the runner's own init, the backend path, one executable copy
per command), the block model and the version helpers. The package's
tests borrow the S3 kind from `tf-s3-state-plugin` to build registrations,
so they need that package installed (the workspace always has it).

## Prerequisites and integration

**This is a library, not a plugin.** Nothing here is discovered through an
entry point, nothing here loads configuration, and no configuration file
names this package. It is installed as a workspace member from the root
[pyproject.toml](../../pyproject.toml) by `just init`, and every plugin
that emits HCL pins it at the same version. There is no account, role, API
or credential of its own. What its OUTPUT needs at execution time is
listed here, because the commands this package emits are the ones the
operator sees fail.

- **A tofu or terraform binary, found through the builder.** Every
  command the mixin emits is a copy of the executable the root's builder
  names in its `executable:` field (default `tofu` on the storage and
  instance models), which must be an entry in `cfg/executables.yml`
  ([CONFIGURATION section 3](../../docs/CONFIGURATION.md)). The entry's
  `binary` is what runs and what `gate-plan --tofu` and the
  `state-migration` steps are handed. This package sets no version floor;
  the entry's `version` requirement is what `validate` and every run
  check (stage 48), and the fixture's floor is `>1,<2` on
  `open-tofu-1`. The flags the mixin emits (`-backend=false`,
  `-reconfigure`, `-migrate-state -force-copy`, `-detailed-exitcode`,
  `-replace=`, `-input=false`, `-out=`) exist on OpenTofu 1.x and
  Terraform 1.x alike.
- **The system's own CLI on `PATH` at execution time.** The gate, the
  apply check, the materialisation, the state backup and the migration
  steps are emitted as the bare command `cs-image-system` (`SYSTEM_CLI` in
  [`utils.py`](../base/src/cs_image_system/base/utils.py)), and so is the
  `program` of the sensitive data source. A runner script or a plan that
  runs where the CLI is not installed fails at the first of them.
- **`rm` on `PATH`.** Step 1 of every gated sequence is `rm -f tfplan`.
- **The `hashicorp/external` provider, downloadable at `init`.** Any root
  with a sensitive value registers a requirement on it. `init` fetches it
  from the registry unless the root's `.terraform.lock.hcl` and the
  shared `TF_PLUGIN_CACHE_DIR` (exported by the
  [Justfile](../../Justfile) as `.tofu-plugin-cache/`) already hold it.
  The same holds for every provider a builder declares under
  `required_plugins`. One tofu process at a time on a machine: the cache
  is not safe under concurrent `init` (the recipes that execute roots
  hold `.tofu-plugin-cache/.lock` through
  [`scripts/with-tofu-lock`](../../scripts/with-tofu-lock)).
- **`CSIS_CONFIG_IDENTITY` in the environment of whoever runs `plan`.**
  The sensitive data source runs `cs-image-system decrypt --json`, which
  opens the ciphertext with that identity; `materialize` needs it too.
  Without it a real run's generation-time plan and every deferred plan
  fail on the roots that carry ciphertext. Where the identity comes from
  is the base library's contract (this repo's `.envrc`; the
  `CSIS_CONFIG_IDENTITY` repository secret in CI).
- **The state backend's own prerequisites.** The bucket, the AWS profile,
  the lock service and the credentials belong to the state plugin whose
  kind renders the backend file ([tf-s3-state-plugin](../tf-s3-state-plugin/README.md),
  [local-state-plugin](../local-state-plugin/README.md),
  [gcs-state-plugin](../gcs-state-plugin/README.md)). This package only
  writes what the kind returns into `.tfbackend.hcl` and hands the file
  to `init`. A real run's `init -reconfigure -backend-config=<file>`
  therefore needs a live session for that backend (an AWS SSO session
  for S3); a dry run's `init -backend=false` needs none.
- **The provider credentials.** `okta`/`oktapam` (`OKTA_API_*`,
  `TF_VAR_<team>_key`/`_secret`), AWS and GCP credentials are declared,
  wired and documented by the plugins that configure those providers;
  the collector passes their `config` through `hcl_value` and adds the
  alias.
- **A configuration root, for the mirror.** `plaintext_read_commands` and
  the `..._with_config` system commands read `working_path` and
  `generation_path` from the run context to compute `_private/...`.
  Outside a run (the bare harness) they degrade: the commands run in
  `generated/` and no `--root-dir` is rendered.

Integration points the rest of the system relies on, all read through the
collector singleton after the builders have registered:

| Reader | What it takes | Where it lands |
| --- | --- | --- |
| `lifecycle_state_bindings` in [`run_lifecycles.py`](../base/src/cs_image_system/base/commands/run_lifecycles.py) | `workspace_backend(ws).state_location(ws)` per builder | the `# state: workspace <ws> -> <location>` header lines of each runner script |
| `_record_state_locations` (same file) | `backend_record(ws)` for every bound workspace not migrating | `meta-state/state-locations.yaml` |
| `validate` in [`validate.py`](../base/src/cs_image_system/base/commands/validate.py) | `effective_backend_name`, `resolve_backend`, `state_location`, `state_collisions` | validation errors naming the workspace, the backend and the shared object |

## Configuration reference

This package owns no YAML key. What it reads, it reads through the
builders that call it. The table lists every configuration field whose
value reaches this package, the builder that hands it over, and what the
package does with it.

| Field (file) | Type | Default | Handed over by | What this package does with it |
| --- | --- | --- | --- | --- |
| `executables[].binary`, `.name`, `.prepended_arguments`, `.appended_arguments` (`cfg/executables.yml`) | see [section 3](../../docs/CONFIGURATION.md) | | the root builder's `get_executable_copy()` | Every tofu command is a deep copy of the entry named by the builder's `executable`; the mixin sets `args` and `working_directory` on the copy and passes `binary` (else `name`) to `gate-plan --tofu` and the `state-migration` steps. `version` is checked by the base library, not here. |
| `<builder>.executable` (instance, storage, group, user builders) | str or null | `tofu` | `BuilderBase.get_executable_copy()` | Selects the entry above. Missing from `cfg/executables.yml`: `ValueError` at the first command. |
| `<builder>.required_plugins[]` / `required_providers[]` (`name`, `version`, `source`, `config`) | list of `TFTofuPluginModel` | `[]` | instance and storage builders (`required_plugins`), the Okta workspace mixin (`required_providers`) | `require_provider(ws, name, source, version)` per entry; merged, conflict-checked, emitted into `required_providers {}`. `name` and `version` are required by `GenericPluginModel`; `source` is optional and omitted from the block when absent; `config` is read by the Okta builders (provider arguments) and ignored by the storage and instance builders. An empty list on a storage or instance root falls back to a bare `hashicorp/aws` requirement with no version. |
| `image_builders[].required_plugins[]` (`cfg/image-builders.yml`) | list of `PackerPluginConfig` | `[]` | `PackerBuilderBase.generate_items_before` | `require_plugin(ws, name, source, version)`; emitted into `packer { required_plugins {} }`, one file per block. |
| `<builder>.state_configuration` (instance, storage, group, user builders) | str | `default` | `bind_workspace(ws, own, runtime's)` | First rung of the chain. A value outside `default`, `self`, empty, unset names a backend registration; the name must exist (`validate` refuses one that does not). |
| `runtime_builders[].state_configuration` (`cfg/runtime-builders.yml`) | str | `default` | `runtime_state_configuration()` | Second rung, for storage and instance roots only. |
| `state_backends[]` (`cfg/state-backends*.yml`): `name`, `type`, `is_default`, the type's own settings | per type | | the state plugin's `register_backend(BackendRegistration(...))` | Stored by name; `is_default` decides what `default` resolves to; `settings` are rendered by the plugin's kind, never read by name here. |
| `config.use_state_backends` (`cfg/_config.yml`) | bool | `false` | `backends_enabled()`, read from the run context | The gate on every backend block, backend file, remote-state data source, header line and location record. Location **collisions** are still checked with it off. |
| `config.apply_identity`, `apply_storage`, `apply_instances` (`cfg/_config.yml`) | bool or list[str] | `false` | the builder, as the `apply` argument through `apply_enabled(key, root, aliases)` | Decides whether the sequence ends in `apply-check` + `apply`. Re-read at execution by `apply-check`, which this package emits with the lifecycle key, root and aliases. |
| `config.module_source_base` (`cfg/_config.yml`) | str | `../tfmodules` | nobody here | **Not read by this package.** The base library's `render_module_call` reads it. Listed because module calls sit beside the blocks this package renders. |
| run options `--dry-run`/`--no-dry-run`, `--migrate-state <root>`, `--overlay <file>`, `--apply-runtime <rt>` | CLI | dry run on | the run context (`dry_run`, `migrate_state`, `overlays`, `apply_runtime`) | See the variations below. |
| a builder's `OktaTfWorkspaceModelMixin.key` / `.secret` and any provider `config` value | str, possibly `ENC[age:...]` | | `sensitive_ref` and `hcl_value` | A value carrying a marker is emitted as its ciphertext (by reference through `local.sensitive[...]` for the Okta credentials; inline for any other block argument). |

### Variations

- **Dry run vs real run (generation-time init).** With `--dry-run` (the
  default) `_init_args` is `init -backend=false`: providers are installed,
  the emission is validated, and the state bucket is never opened. With
  `--no-dry-run` it is `init -reconfigure -backend-config=<file>` when the
  workspace has a backend and backends are enabled, else `init`. The
  identity builders also skip their generation-time `plan` in a dry run
  (the user builder logs `dry run, 'plan' not run at generation time`);
  the storage and instance builders never plan at generation time.
- **Dry run vs real run (the deferred sequence).** The sequence is
  emitted identically in both modes, always with the real-run init
  (`_runner_init_args`). A dry run only enumerates it; a real run
  executes it in process and the committed script carries it either way.
- **Backends enabled vs disabled.** Enabled: an empty `backend "<type>"
  {}` block, a `.tfbackend.hcl`, `-backend-config=<file>` on every real
  init, `terraform_remote_state` data sources, the runner header lines
  and the location record. Disabled: none of those; `init` runs bare and
  a consumer's remote-state read is not emitted at all, so a module that
  needs a producer's outputs cannot work.
- **Own `state_configuration` vs the runtime's vs the default.** The
  first value outside the absent sentinels wins; the identity roots skip
  the runtime rung. A root bound once cannot be rebound to a different
  backend in the same run.
- **Migrating vs not.** When the root's name is in `--migrate-state`, the
  runner's init becomes `state-migration begin` + `init -input=false
  -migrate-state -force-copy -backend-config=<file>`, the plan carries
  `-detailed-exitcode` so any change stops the runner, and
  `state-migration finish` follows the gate. Otherwise the init is
  `-reconfigure` ("do not migrate") and there are no migration steps. A
  dry run refuses the flag before this package sees it.
- **`replace` given vs empty.** Each address becomes `-replace=<address>`
  on the plan and `--allow-destroy <address>` on the gate, so the
  replacement's destroy passes and nothing else does. The instance builder
  fills it from pending upgrades and follow moves.
- **`allow_destroy` given vs empty.** Each address is whitelisted at the
  gate. Empty: every planned destroy fails the gate with
  `DESTROY NOT WHITELISTED`.
- **`require_unmounted` given vs empty.** Each `<instance>:<storage>` pair
  makes the gate demand a successful receipt in `./unmount-receipts`
  before it even reads the plan; missing, `DETACH NOT UNMOUNTED`, exit 3.
- **`pre_plan` given, with or without `pre_plan_backup`.** The argument
  lists run between init and plan as tofu commands. With
  `pre_plan_backup=True` a `state-migration backup` step precedes them;
  with `pre_plan` empty the backup flag does nothing, by decision (stage
  63 item 4, 2026-09-24): the flag covers the `pre_plan` lines alone, and
  a pre-command that removes state, such as the identity runner's prune
  step, takes its own backup, so a run never pulls state twice for one
  removal and never backs up a run that removes nothing. The group builder
  passes `state rm module.group_<name>` for a newly unmanaged group with
  the backup on.
- **`pre_commands` given vs empty.** Executables inserted verbatim after
  `pre_plan` and before the plan (the instance root's unmount steps, the
  identity root's `prune-attachments`).
- **`apply` true vs false.** False: the sequence ends at the gate (or at
  `state-migration finish`); the root plans and gates and nothing changes.
  True: `apply-check` (when `apply_flag_key` is given) and `apply
  -input=false tfplan` follow.
- **`apply_flag_key` with or without `apply_root`.** Without a root, the
  emitted `apply-check` re-checks the lifecycle flag as a whole; with a
  root and aliases, a list-valued flag is re-checked for that root by
  builder name or runtime. The run's `--overlay` files are carried as
  `--overlay <file>` and `--apply-runtime <rt>` as itself, so the
  execution-time check reads the flags as generation did.
- **In a run vs outside one.** Inside a run `plaintext_read_commands`
  materialises the root into `_private/` and runs there; outside one it
  runs in place. `run_is_dry` answers false outside a run.
- **A value with a marker vs a clear value.** Through `sensitive_ref`: a
  marked value is registered, the `external` provider is required and the
  reference `local.sensitive["<key>"]` is returned; a clear value is
  returned unchanged and nothing is registered. Through `hcl_value`: a
  marked value renders as its ciphertext, quoted; a clear value renders
  as itself.
- **Provider alias given vs derived.** `configure_provider(alias=...)`
  uses the alias; otherwise the sanitized workspace name. Either way the
  block carries `alias =` and module calls must bind through
  `provider_bindings`.
- **Packer variable with `env_var` vs `default`.** `env_var` wins and the
  block says `default = env("VAR")`; a bare `default` renders the value
  (lower-case for a boolean, raw for a string).

## What it tests and verifies

Nothing in this package runs at load: it has no pydantic model of its own
and no validator. Its checks run when a builder registers into a
collector, when a generator is called, and inside the commands it emits.

**At registration (generation, while builders declare).**

- `configure_provider`: the same provider name and alias configured twice
  with different arguments in one workspace -- `HclConfigConflictError`,
  raised into the generating builder, which fails the run (exit 1).
- `declare_variable` (both collectors): a variable redefined with
  different attributes in one workspace -- `HclConfigConflictError`.
- `register_backend`: the same backend name registered with a different
  declaration -- `HclConfigConflictError`.
- `set_backend` / `bind_workspace`: a workspace rebound to a different
  backend -- `HclConfigConflictError` naming the workspace and both
  backends.
- `sensitive_ref`: the same key registered with a different ciphertext --
  `HclConfigConflictError`.
- `StateLocation.of`: a `.` or `..` segment in the key -- `ValueError`;
  `validate` turns it into a validation error naming the workspace.
- `normalize_constraint`: a clause `packaging` cannot parse --
  `ValueError` from the first generator that merges it.

**At generation (every `generate_*` call, through `validate_all`).**

- Per provider name across ALL workspaces: sources agree
  (case-insensitively) and the conjunction of every constraint is
  satisfiable -- else `HclConfigConflictError` naming the provider, each
  constraint and its requester. The packer collector does the same per
  plugin name (satisfiability run-wide, sources per workspace).
- Every bound workspace's location is distinct --
  `HclConfigConflictError("state location collision: workspaces A, B would
  share the state object <location>")`.
- `resolve_backend`: more than one registration marked `is_default` --
  `HclConfigConflictError`.
- `generate_remote_state_datasources`: a reference whose backend resolves
  to nothing -- `HclConfigConflictError` naming the consumer and the
  producer.
- A registration without a kind, asked for its location, backend file or
  data source -- `HclConfigConflictError("State backend '<name>' (type
  '<type>') was registered without a kind ...")`.

The verdict of all of these is an exception out of the generating builder;
the run logs it and exits 1, `run-summary.json` carries it as `error`, and
nothing of that lifecycle is emitted.

**At `validate` (the base library, using this package).** Every root's
backend name resolves to a registration, every location is well-formed,
no two collide, and a root whose location differs from the record while
resources stand in it is refused. The verdicts are validation errors
(`validate` exit 1; `run` exit 1 before generation).

**At execution (the commands this package emits; the checks live in
[`gate.py`](../base/src/cs_image_system/base/commands/gate.py),
[`state_migration.py`](../base/src/cs_image_system/base/commands/state_migration.py)
and the [system CLI](../system/src/cs_image_system/system/cli.py)).**

| Step | Checks | Verdict |
| --- | --- | --- |
| `rm -f tfplan` then `plan -out=tfplan` | a failed plan leaves no file | the runner stops at the plan under `set -euo pipefail` |
| `gate-plan --planfile tfplan` | the planfile exists and is newer than the root's newest `*.tf`; every planned destroy is whitelisted; every `--require-unmounted` pair has a successful receipt | `STALE PLANFILE: ...`, `DESTROY NOT WHITELISTED: <address>`, `DETACH NOT UNMOUNTED: <pair>` on stderr, exit 3; `Plan passes the apply gate.` on success |
| `apply-check --lifecycle <key> ...` | `cfg/_config.yml` is found walking up from the working directory; every `--overlay` still exists; the flag allows this root NOW | `apply_<key> is false NOW in <file> for root '<root>' -- this runner script was generated when it allowed the apply; not applying.`, exit 3; `apply_<key> allows ...; proceeding.` on success |
| `state-migration backup` | the root is an initialised terraform root and its location holds state | `state backup for workspace '<ws>' REFUSED/FAILED ...` in the log, exit 1, nothing removed from state; on success an INFO line with the serial, the resource count and the backup path |
| `state-migration begin` | the new location is empty or holds this workspace's lineage; the old state pulls | refused as a collision, or the backup written beside the root and the move logged |
| `plan -detailed-exitcode` (migrating) | the plan at the new location reports no changes | exit 2 from tofu stops the runner before the gate |
| `state-migration finish` | the begin record exists | the move recorded in meta-state and the location record moved |
| `apply -input=false tfplan` | tofu's own | the runner stops on failure; the after-apply hooks never run |

**Not checked here.** The tool versions (stage 48, base library); the
existence of the providers a `required_plugins` entry names (tofu's `init`
finds out); the syntax of a `version` constraint beyond what `packaging`
parses; the validity of a `sensitive_ref` key as an HCL attribute name;
the plaintext guard over `generated/` (the base library's, at `validate`
and every commit).

## When it fails

Failures that have happened, newest first.

- **2026-09-23 -- the provider errored on refresh for an attachment whose
  membership was gone** (stage 61 item 3). The group root's
  generation-time `plan` refreshed state and `oktapam` failed with
  `user "x" is not present within group "g"` for an attachment the roster
  had dropped by hand. What changed in this package: `gated_apply_commands`
  gained `pre_commands` (the identity runner's `prune-attachments` step,
  between init and plan) and `pre_plan_backup` (a `state-migration
  backup` before any `state rm`), and the group builder's generation-time
  plan runs `-refresh=false` through `plaintext_read_commands`. If the
  runner's plan still shows such an error, the prune step's log lines name
  each attachment and why it was kept; the repair is a `state rm` after
  the backup the step already took.
- **2026-09-22 -- the first real identity run after stage 51 planned in
  `generated/` and every derived user lookup failed.** The committed
  emission carried `first.last@ENC[age:...]` in the `okta_user` lookups
  and the generation-time `plan` ran against that text. Symptom: the Okta
  provider found no user for every derived address. Fix:
  `plaintext_read_commands` materialises the root into `_private/`,
  initialises there and plans there, exactly as the runner does. If a
  generation-time plan reports unknown users whose addresses are derived,
  look at the command's working directory in the run log: it must be
  under `_private/`, and `CSIS_CONFIG_IDENTITY` must be set for the
  materialisation.
- **2026-09-19 -- `tofu init` in the mirror could not read its module.**
  Found by probing an AZ change: the mirror was nested one level too deep
  and every relative module source (`../../../../../cs-image-system-3/tfmodules/...`)
  counted up to the wrong directory. Fix in the base library
  (`mirror_path`): `_private/` replaces `generated/` at the same depth. A
  `Module not found` or `Unreadable module directory` from an init whose
  working directory is under `_private/` means the mirror stands at the
  wrong depth again; compare the path against the `generated/` one.
- **2026-09-16 -- `Backend configuration changed` after `encrypt: true`**
  (stage 39, ledger 94). Flipping a backend argument under roots that were
  already initialised made tofu refuse the real-run generation-time
  `init`. Fix: `_init_args` and `_runner_init_args` carry `-reconfigure`;
  the state is remote, so nothing needs migrating. The message can still
  appear from a hand `tofu init` in a root the system initialised; run
  the system's form (`init -reconfigure -backend-config=<file>`), never
  `-migrate-state` by hand (that flag is reserved for `--migrate-state`).
- **2026-09-16 -- a fresh clone's runner failed at its first `tofu plan`**
  (stage 38, ledger 93). After a dry run the root's `.terraform/` was
  backend-less, and in a fresh clone there was none, so the committed
  script's plan failed on an uninitialised root. Fix: every gated sequence
  begins with the runner's own `init -input=false -reconfigure
  [-backend-config=<file>]`. On the way, a generation-time `tofu init`
  failed because it ran concurrently with the bar's tests over the same
  `TF_PLUGIN_CACHE_DIR`: an `init` that fails with a provider-cache or
  lock error while something else runs tofu is that, and the fix is to
  run alone (the recipes hold `scripts/with-tofu-lock`).
- **Early September 2026, stage 1 live run -- a stale `tfplan` passed the
  gate** (ledger finding 33; the ledger carries no day). A plan failed,
  the previous sequence's `tfplan` remained, and `gate-plan` judged the
  wrong plan. Fix: `rm -f tfplan` is step 1 of every sequence and the gate
  refuses a planfile missing or older than the root's newest `*.tf`
  (`STALE PLANFILE`, exit 3). Seeing it means the plan step produced no
  file: read the plan's own error above it in the runner output.
- **Early September 2026, stage 1 live run -- a runner applied under
  yesterday's flags** (ledger finding 24). `apply_*` gated generation only;
  a previously generated runner kept its baked-in apply lines. Fix:
  `apply-check` is emitted before every `apply` and re-reads the flag at
  execution. `apply_<lifecycle> is false NOW in <file>` therefore means
  the script is older than the configuration, not that the script is
  wrong: regenerate, or turn the flag back on deliberately.

Failures the code raises that have not been seen live.

| Message or symptom | Meaning | Where to look, what to do |
| --- | --- | --- |
| `Irreconcilable version constraints for '<provider>': '<c1>' requested by <ws1>; '<c2>' requested by <ws2>` | two builders (or two entries in one) pin the same provider or packer plugin to versions no release satisfies | the named workspaces' `required_plugins` / `required_providers`; loosen one. Raised at the first generator call, before anything is written |
| `Provider '<name>' requested with different sources: [...] (requested by [...])` / `Packer plugin '<name>' requested with different sources` | the same name from two registries | make the `source` values agree (compared case-insensitively) |
| `Provider '<name>' (alias=<alias>) configured twice with different arguments in workspace '<ws>'` | a builder configured one provider twice | usually a runtime's region or profile changed between two registrations of one root; the builder's `generate_items_before` |
| `Variable '<name>' redefined with different attributes in workspace '<ws>'` (`Packer variable ...` for packer) | two declarations of one variable | the builder that declares it twice; the instance root declares one AMI variable per instance, so two instances that sanitize to one label collide here |
| `State backend '<name>' registered twice with different configurations` | two entries with one `name` across `cfg/state-backends*.yml` | rename one |
| `Multiple default state backends registered: [...]` | more than one `is_default: true` | keep one |
| `Workspace '<ws>' is bound to state backend '<a>' and cannot be rebound to '<b>': a workspace keeps its state in exactly one location` | a builder bound its workspace twice with different names | a plugin defect unless two builders share a name; the run log shows which registration came second |
| `state location collision: workspaces A, B would share the state object <location>` | two roots resolve to one state object (same bucket and normalised prefix under two backend names, two names that collapse under `super_safe_name`, `//` against `/`) | `validate` reports it before generation; change a prefix or a name |
| `state key '<key>' carries a '..' segment` | a backend prefix with `.` or `..` | the backend's `key`/`path`; `validate` names the workspace |
| `State backend '<name>' (type '<type>') was registered without a kind: the plugin that declares the type must supply its renderings` | a state plugin registered a `BackendRegistration` with `kind=None` | a plugin defect; the state plugin's `to_backend_registration` |
| `Workspace '<ws>' references remote state of '<producer>' but no backend is registered for it` | a consumer references a producer that is bound to nothing and there is no default | bind the producer (`state_configuration`) or mark a default backend |
| `Sensitive value '<key>' registered twice with different ciphertexts in workspace '<ws>'` | one key, two markers | the Okta workspace's `key`/`secret` registered from two models under one workspace name |
| `Executable '<key>' not found for builder '<name>' of type '<type>'` (`ValueError`) | the builder's `executable` names no entry in `cfg/executables.yml` | add the entry or fix the name; `validate` also reports unresolved foreign keys |
| `Working directory for commands in phase <phase> cannot be None for builder <class>` (`AssertionError`) | a plugin called `terraform_commands` with no directory | a plugin defect |
| `ValueError` from `packaging` naming an invalid specifier | a `version` constraint such as `>= 1.x` | the entry's `version`; use `>=`, `<`, `~>`, `=`, `!=` forms |
| tofu: `Backend configuration changed` | a hand `init` without `-reconfigure` after a backend argument changed | see 2026-09-16 above |
| tofu: `Error: Backend initialization required` or a plan in `generated/` that reads ciphertext | the root was not initialised where the command runs | the deferred sequence initialises itself; a generation-time plan runs in `_private/`; check the working directory in the log |
| `STALE PLANFILE: ...` (exit 3) | no `tfplan`, or one older than the newest `*.tf` | the plan failed or the root was regenerated after the plan; rerun the sequence |
| `DESTROY NOT WHITELISTED: <address>` (exit 3) | the plan destroys something no operation asked for | OPERATIONS "The apply gate": a decommission, an upgrade, a storage state change or a detach are the only whitelists; a zone or a module change that forces replacement is refused here by design |
| `DETACH NOT UNMOUNTED: <instance>:<storage> has no successful unmount receipt` (exit 3) | a detach planned without the unmount | `unmount storage ...` first (or `--confirm`), then rerun |
| `apply-check: no cfg/_config.yml found from the working directory up; refusing to apply` (exit 3) | the runner runs outside a configuration tree | run it from its own directory in the tree (`final_execution.sh` does) |
| `apply-check: overlay <path> is gone; refusing to apply` (exit 3) | an overlay the run was generated under was deleted | restore it or regenerate |
| `state backup for workspace '<ws>' REFUSED: <dir> is not an initialised terraform root` / `... the location holds no state, yet a state rm is due` (exit 1) | the backup that precedes a `state rm` cannot see the state | the root's init failed or bound to an empty location; nothing was removed; fix the binding, rerun |
| a migrating runner stops after `plan -detailed-exitcode` with exit 2 | the plan at the new location is not clean | OPERATIONS "Where state lives": the move is accepted only clean; the backup is beside the root, the old location untouched |
| a packer template fails to parse at `default = 1.0.0` | `packer_variable` rendered a plain string default unquoted until stage 63 item 3 (2026-09-24); it now quotes a `str` default as an HCL string | not since the fix; a `QString` default is passed through as given |
