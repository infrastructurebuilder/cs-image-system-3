# cs-image-system-hashicorp-utils

A library for cs-image-system plugins that emit HashiCorp configuration:
terraform (OpenTofu) roots and packer templates. It collects provider,
plugin, backend and variable requirements per workspace, renders HCL
blocks in memory, and gives a builder that owns a terraform root its
`init`, `plan`, gate and `apply` command sequence.

**This is a library, not a plugin.** It declares no
`cs_image_system.plugins.*` entry point, registers nothing in the registry
and contributes no builder of its own. Plugins import it. In the
workspace, the terraform-root plugins (`okta-opa-plugin`,
`tf-ebs-instance-plugin`, `tf-gcp-plugin`, `tf-s3-state-plugin`) depend on
it directly; the packer plugin uses its packer collector; the runtime
plugins use its formatter and quoting primitives; the base runner imports
the terraform collector, guarded by an `ImportError` fallback, to list the
state files each lifecycle's workspaces bind to.

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

## Modules

| Module | Provides |
| -------- | ---------- |
| [`collector.py`](src/cs_image_system/hashicorp_utils/collector.py) | `TerraformCollector`, `PackerCollector`, and the declaration dataclasses `ProviderRequirement`, `ConfiguredTerraformProvider`, `ProviderConfig`, `TerraformVariable`, `BackendRegistration`, `RemoteStateReference`, `PackerPluginRequirement`, `PackerVariableDecl`. |
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
| `require_provider(workspace, name, source=None, version=None, requested_by=None)` | Adds a provider requirement. An identical requirement is ignored. |
| `configure_provider(workspace, name, config, alias=None)` | Records a `provider "<name>" {}` block. The alias defaults to the sanitized workspace name, so provider blocks from different builders never collide when aggregated. Configuring the same name and alias twice with different arguments raises `HclConfigConflictError`. |
| `provider_bindings(workspace)` | `{provider name: "<name>.<alias>"}` for every configured provider, for a module call's `providers = { ... }` meta-argument. Module calls must bind explicitly, because every configured provider carries an alias. |
| `declare_variable(workspace, TerraformVariable(name, type="string", default=None, description=None, sensitive=False))` | Declares a `variable` block. Redefinition with different attributes raises `HclConfigConflictError`. |
| `register_backend(BackendRegistration(...))` | Makes a state backend available for the run (registered by a state plugin). Registering the same name with a different configuration raises. |
| `set_backend(workspace, backend_name="default")` | Binds a workspace to a backend; `default` resolves to the registration marked `is_default`. More than one default is a conflict. |
| `reference_remote_state(consumer_workspace, producer_workspace, backend_name=None, label=None)` | The consumer reads the producer's state through a `terraform_remote_state` data source. |
| `sensitive_ref(workspace, key, value)` | See [Sensitive values](#sensitive-values-by-reference). |

`BackendRegistration` fields: `name`, `type` (for example `s3`),
`settings` (the type's own, as an opaque mapping), `kind` (the type's
renderings, supplied by the state plugin that declares it) and
`is_default`. `state_location(workspace)` asks the kind for the
`StateLocation` (`<type>://<container>/<key>`, normalised, stage 46);
`backend_settings(workspace)` and `remote_state_settings(workspace)` for
the partial configuration and the data source (stage 47). The collector
names no field of any type.

### Dedupe, merge and conflicts

`merged_providers(workspace)` produces one entry per provider name. Version
constraints are merged: the emitted string is the comma-joined, deduplicated
originals (`">= 4.0.0, < 6.0.0"`) and their conjunction must be
satisfiable. Two sources for the same provider (`hashicorp/aws` and
`mycorp/aws`) are a conflict. `validate_all()` runs the same checks across
every workspace of the run; every generator calls it first, so a conflict
between two workspaces surfaces at generation even when each workspace is
consistent on its own.

### Backend emission and partial configuration

Backend and remote-state emission is gated by the global
`config: use_state_backends` flag (`backends_enabled()`); when it is off,
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
file, rendered by `generate_backend_config(workspace)` as top-level
`key = value` lines (`bucket`, `key`, `region`, `encrypt`, `use_lockfile`,
and `profile` when set) and supplied to `init -backend-config=<file>`.
That keeps bucket names and profiles out of the committed `terraform {}`
block and lets the same emission bind to different backends.

`generate_remote_state_datasources(workspace)` renders one
`data "terraform_remote_state" "<label>"` per reference, with `backend`
and a `config = { bucket, key, region[, profile] }` object; the label is
the sanitized producer name unless given. The backend is the reference's
named one, else the producer's, else the default; none at all is a
conflict.

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
   configured `external` provider alias when it has one (an identity root
   that also aliases the provider for the gid shim), else the default
   provider.

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
| `generate_provider_blocks(workspace)` | One `provider "<name>" { ...config, alias = "<alias>" }` per configured provider. |
| `generate_variable_blocks(workspace)` | One `variable "<name>" { type, default, description, sensitive }` per declared variable; a boolean default renders lower-case. |

## PackerCollector

`PackerCollector` is the packer counterpart, also a singleton with
`reset()`.

| Method | Effect |
| -------- | -------- |
| `require_plugin(workspace, name, source=None, version=None, requested_by=None)` | Adds a required plugin; identical requirements dedupe. |
| `declare_variable(workspace, PackerVariableDecl(name, type="string", default=None, description=None, env_var=None, sensitive=False))` | Declares a packer variable; redefinition with different attributes is a conflict. |
| `merged_plugins(workspace)` | One entry per plugin with merged constraints; disagreeing sources are a conflict. |
| `validate_all()` | Run-wide satisfiability per plugin name. |
| `generate_packer_block(workspace)` | `packer { required_plugins { <name> = { version, source } } }`. |
| `generate_variable_blocks(workspace)` | `variable "<name>" { type, default, description, sensitive }` blocks. With `env_var` the default is `env("<VAR>")`. |

## TerraformRootMixin

A builder whose workspace is a standalone terraform root (its own
`terraform {}` block, backend partial-configuration file and tofu command
sequence) mixes `TerraformRootMixin` in next to its `BuilderBase`
subclass. The mixin is duck-typed against `BuilderBase`: it relies on
`self.name`, `self.get_path_for_phase(phase, suffix=...)`,
`self.get_executable_copy()` and, when present, `self._get_context()`.

### Backend file and init arguments

`_backend_config_path(phase)` is
`<builder>/<phase>/<builder>-<phase>.tfbackend.hcl`, the file
`generate_backend_config` fills.

`_init_args(phase)` is the generation-time `init`:

| Run | Arguments | Why |
| ----- | ----------- | ----- |
| dry run | `init -backend=false` | Providers are installed and the emission validated without touching remote state, which holds decrypted values. A read-only CI role, a drift check and an operator's preview all stay off the state bucket. |
| real run, backend bound | `init -reconfigure -backend-config=<file>` | The bare file name, because tofu runs inside the phase directory. `-reconfigure` because a backend argument may differ from the one the root was last initialised with, and the state is remote, so there is nothing to migrate. |
| real run, no backend | `init` | |

`run_is_dry(builder)` reads the run context's `dry_run` flag; a builder
used outside a run (no context yet, as in unit tests) is not in a dry
run.

`_runner_init_args(phase)` is the `init` a committed runner script performs
for itself, always in the real-run form:
`init -input=false -reconfigure [-backend-config=<file>]`. A dry run's
generation-time init was backend-less and a fresh clone has no
`.terraform/` at all, so the script must initialise the root itself. It is
deferred like the plan it precedes, so an in-process real run repeats it
(idempotent, seconds) and the script stays a faithful record of what
finalization executes.

### Command materialization

`terraform_commands(phase, arg_lists, working_directory)` returns one
`ExecutableModel` per argument list, each a fresh `get_executable_copy()`
bound to the workspace directory. A fresh copy per command is mandatory:
`args` and `working_directory` are mutated per command, so sharing one
model would make every command run the last arguments.

### The gated plan, gate, apply sequence

`gated_apply_commands(phase, working_directory, apply, allow_destroy=(),
replace=(), pre_plan=(), apply_flag_key=None, apply_root=None,
apply_root_aliases=(), plan_extra_args=(), pre_commands=(),
require_unmounted=())` returns the deferred sequence for a terraform root,
in this order:

1. `rm -f tfplan` — a failed plan must leave nothing for the gate to read.
2. `<tofu> init -input=false -reconfigure [-backend-config=<file>]` — the
   runner's own init.
3. each `pre_plan` argument list (for example `state rm <address>` for a
   group leaving management).
4. each `pre_commands` executable (for example the unmount before a
   detach).
5. `<tofu> plan -input=false -out=tfplan [-replace=<address> ...]
   [plan_extra_args ...]` — `replace` addresses are forced replacements
   (an explicit upgrade); `plan_extra_args` carries flags such as
   `-var=ephemeral_present=false`.
6. `cs-image-system gate-plan --planfile tfplan --tofu <tofu>
   [--allow-destroy <address> ...] [--require-unmounted <pair> ...]` — the
   gate. Every `allow_destroy` address and every `replace` address is
   passed as `--allow-destroy`, so a replacement's destroy is whitelisted
   and any other planned destroy fails the gate. Each `require_unmounted`
   pair demands an unmount receipt.
7. only when `apply` is true:
   - when `apply_flag_key` is given, `cs-image-system apply-check
     --lifecycle <key> [--root <apply_root> --root-alias <alias> ...]
     [--overlay <file> ...] [--apply-runtime <rt>]`, re-checking the
     `apply_<key>` flag at execution time so a script generated under
     yesterday's flags cannot apply under today's; the run's overlays and
     `--apply-runtime` are carried from the run context;
   - `<tofu> apply -input=false tfplan` — the very plan that passed the
     gate.

`apply` is the value of the lifecycle's `apply_<lifecycle>` configuration
flag for this root (`apply_enabled(key, root, aliases)` in the base
library), so a root that is not allowed to apply still plans and gates.

## HCL rendering helpers

### Blocks

`blocks.py` is a declarative model for `resource`, `data`, `output` and
other top-level blocks, rendered through `python-hcl2`'s builder so no
plugin touches `hcl2.Builder` or `FormatterOptions` directly.

| Name | Meaning |
| ------ | --------- |
| `Raw(str)` | A string emitted unquoted: an address or expression the quoting policy cannot infer, such as `Raw("oktapam_group.x.id")`. |
| `hcl_value(v)` | The shared quoting policy. `Raw` and `QString` pass through; a string starting with `var.`, `data.`, `local.`, `module.`, `each.` or `count.` stays raw; any other string is quoted; booleans and numbers stay raw (booleans render lower-case); list elements and mapping values convert recursively. Mapping keys are the caller's responsibility (pre-quote a key such as `'"system.os_type"'`). |
| `BlockSpec(type, label, args, comment=None, commented_out=False, children=[], kind="resource", labels=None)` | A top-level block. The default labels are `"<type>" "<label>"`; `labels` overrides them for single-label kinds. `comment` prefixes a `# ...` line; `commented_out` emits the whole block as comments. `spec.block(name, **args)` appends a child block and returns it for fluent nesting. |
| `ResourceSpec`, `DataSpec` | `BlockSpec` with `kind` fixed to `resource` / `data`. |
| `OutputSpec(name, value, description=None, sensitive=False, comment=None)` | An `output "<name>" { value = ... }` block. |
| `NestedBlock(name, args, children)` | A child block; `block()` nests further. |
| `render_block(spec)` / `render_blocks(specs, separator="")` | HCL lines, in memory. |

### Primitives

`hashicorp.py` holds `FO` (`FormatterOptions(indent_length=4,
vertically_align_attributes=False)`), `QString(value, quoted=False,
quote_char='"')` (a `str` subclass whose `str()` quotes the value when
asked, except a `var.` reference, which always stays raw), the
`TerraformGenerator` protocol (`generate_terraform(setup)` and
`generate_terraform_data(setup)` returning lines), `packer_variable(builder,
name, type, default, description=None, env_var=None, sensitive=False,
validation=None)` which appends a packer `variable` block (an `env_var`
becomes `default = env("VAR")`; `validation` is a `(condition,
error_message)` pair), and the S3-backend field dataclasses
(`StateEndpoints` with `dynamodb`, `s3`, `sts`, `iam`, `sso`;
`AssumeRoleConfig` with `role_arn`, `duration`, `policy`, `policy_arns`,
`session_name`, `source_identity`, `tags`, `transitive_tag_keys`;
`AssumeRoleWithWebIdentityConfig` with `web_identity_token`,
`web_identity_token_file`).

Terraform **module calls** are rendered by the base library
(`render_module_call` and `hcl_expr` in `cs_image_system.base.utils`),
not here; this package renders blocks and the collector-level scaffolding.

## Versions

`versions.py` turns terraform and packer constraint strings into
`packaging` specifier sets for conflict analysis while preserving the
original strings for emission.

| Function | Behaviour |
| ---------- | ----------- |
| `normalize_constraint(spec)` | Comma-separated clauses. `~> X.Y.Z` becomes `>= X.Y.Z, < X.(Y+1).0`; `~> X.Y` becomes `>= X.Y, < (X+1).0`; `~> X` becomes `>= X, < (X+1)`; `= V` and a bare version become `== V`; `>=`, `<`, `!=`, `==` pass through. An empty or `None` spec is unconstrained. |
| `merge_constraints(specs)` | Returns `(emission, combined)`: the deduplicated originals comma-joined (terraform reads a comma as AND) and the conjunction of their normalized forms. |
| `is_satisfiable(combined)` | Whether some version satisfies the conjunction, tested against a finite witness set: every version literal in the clauses plus its micro, minor and major bumps, and `0`. This catches disjoint pins and non-overlapping ranges; unusual gap constructions may pass. |
| `assert_satisfiable(name, requirements)` | For `(constraint, requested_by)` pairs: returns the merged emission string or raises `HclConfigConflictError` naming the provider, each constraint and who requested it. |

`HclConfigConflictError` (a `RuntimeError`) is the one exception both
collectors raise for contradictory requirements.

## Tests

[`tests/`](tests/) pins the collector (workspace isolation, dedupe,
merged version emission, source mismatch, cross-workspace conflict, the
empty backend block and the `.tfbackend.hcl` contents, remote-state data
sources, provider aliases and bindings, variable redefinition), the packer
collector, the root mixin (dry-run and real-run init arguments, the
runner's own init, the backend path, one executable copy per command), the
block model and the version helpers.
