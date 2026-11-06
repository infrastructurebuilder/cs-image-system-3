# cs-image-system-hashicorp-utils

A library for cs-image-system plugins that emit HashiCorp configuration:
terraform (OpenTofu) roots and packer templates. It collects provider,
plugin, backend and variable requirements per workspace and renders HCL
blocks in memory. The terraform roots themselves (the root mixin with
its `init`, `plan`, gate and `apply` sequence, and the provider-neutral
instance and storage roots) are the sibling library
[tofu-roots](../tofu-roots/README.md), which builds on this one.

**This is a library, not a plugin.** It declares no
`cs_image_system.plugins.*` entry point, registers nothing in the registry
and contributes no builder of its own. Plugins import it. **It imports
only the contract**: nothing under its source imports the core
(`cs_image_system.base`), the CLI host, the terraform roots or any
plugin, lazily or not, and
[tests/test_v2_contract.py](../../tests/test_v2_contract.py) holds it to
that (`test_the_library_imports_only_the_contract`,
`test_the_import_order_is_a_dag`). What it needs of a run -- the global
`config:` map, the declared state backends and a slot to keep its
collectors in -- it names in a small protocol of its own (`CollectorContext` in
[`collector.py`](src/cs_image_system/hashicorp_utils/collector.py)),
which the core's run context satisfies and a bare holder in a test can
satisfy too.

In the workspace, nine packages depend on it directly: `tofu-roots`,
whose root mixin and neutral roots drive the terraform collector; the
identity root plugin (`okta-opa-plugin`) and the three provider root
plugins (`tf-ebs-instance-plugin`, `tf-gcp-plugin`, `tf-docker-plugin`),
which reach the collector and the block model beside the roots they
subclass from tofu-roots; `packer-plugin`, which uses the packer
collector; and the three runtime plugins (`aws-runtime-plugin`,
`gcloud-runtime-plugin`, `docker-runtime-plugin`), which import the
formatter options for their packer sources. The state plugins
(`tf-s3-state-plugin`, `local-state-plugin`, `gcs-state-plugin`) do not
depend on it: their models answer a registration the collector pulls
from the run context when it is first asked for, and they import the
contract alone. The base library neither depends on it nor imports it:
what the core used to read from the collector (the state header lines of
the runner scripts, the location record, the collision check at
`validate`) is answered by the run hooks of
[tofu-roots](../tofu-roots/README.md#the-run-hooks).

Licensed under Apache-2.0. Requires Python 3.13 or later. Declared
dependencies ([pyproject.toml](pyproject.toml)): `cs-image-system-contract`,
`packaging`, `pydantic` and `python-hcl2`. Nothing in the workspace
depends on `cs-image-system-system`, the CLI host.

## Contents

- [Modules](#modules)
- [TerraformCollector](#terraformcollector)
- [PackerCollector](#packercollector)
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
| [`collector.py`](src/cs_image_system/hashicorp_utils/collector.py) | `TerraformCollector`, `PackerCollector`, the per-run accessors `terraform_collector(ctx)` and `packer_collector(ctx)` with the `CollectorContext` protocol they take, the declaration dataclasses `ProviderRequirement`, `ConfiguredTerraformProvider`, `ProviderConfig`, `TerraformVariable`, `RemoteStateReference`, `PackerPluginRequirement`, `PackerVariableDecl`. `BackendRegistration`, the `StateLocation` tuple and the `BackendKind` protocol are the contract's (`cs_image_system.contract.state`) and stay importable from here. |
| [`blocks.py`](src/cs_image_system/hashicorp_utils/blocks.py) | The declarative block model: `Raw`, `hcl_value`, `NestedBlock`, `BlockSpec`, `ResourceSpec`, `DataSpec`, `OutputSpec`, `render_block`, `render_blocks`. |
| [`hashicorp.py`](src/cs_image_system/hashicorp_utils/hashicorp.py) | The formatter options `FO`, the `QString` quoting wrapper, the `TerraformGenerator` protocol, `packer_variable`, and the S3-backend field dataclasses `TStateRoot`, `StateEndpoints`, `AssumeRoleBaseClass`, `AssumeRoleConfig`, `AssumeRoleWithWebIdentityConfig`. |
| [`hashicorp_models.py`](src/cs_image_system/hashicorp_utils/hashicorp_models.py) | `GenericPluginModel` (`name`, `version`, `source`, `config`: a pydantic dataclass under the contract's model configuration, defined here since this package imports nothing of the core) and its subclasses `TFTofuPluginModel` and `PackerPluginConfig`, which builders use for their `required_providers:` / `required_plugins:` lists. |
| [`versions.py`](src/cs_image_system/hashicorp_utils/versions.py) | Constraint normalization, merging and conflict detection; `HclConfigConflictError`. |

Nothing in this package writes files. Every generator returns a list of
HCL lines; the consuming builder places them into an asset for the runner
to write.

## TerraformCollector

`TerraformCollector` is the run's collector of terraform requirements.
There is **one per run context and no process-wide object**: a builder,
a hook or a command reaches it as `terraform_collector(ctx)`, which keeps
the instance beside the context (`ctx.plugin_state`, the slot per key
the core's context offers a library) and makes it on the first ask --
with `backends_enabled` read from the tree's `config: use_state_backends`
and the tree's declared state backends pulled in (every state backend
model's `to_backend_registration()`, through `pull_declared_backends`).
Every later ask on that context returns the same object; a new context
starts with no collector at all, which is what used to need an explicit
reset between runs and tests. Nothing in a run constructs a collector;
`TerraformCollector(backends_enabled=False)` and `reset()` remain for a
test that wants an instance of its own.

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
| `register_backend(BackendRegistration(...))` | Makes a state backend available for the run. Registering the same name with a different declaration raises. A state plugin does not call it, and neither does the core: when `terraform_collector(ctx)` makes the run's instance it calls `pull_declared_backends(models)` with the context's state backend models, which registers what every one answers to `to_backend_registration()`; `register_backend` remains for a registration made by hand (the tests). |
| `set_backend(workspace, backend_name="default")` | Binds a workspace to a backend; `default` resolves to the registration marked `is_default`. More than one default is a conflict. A second binding to a **different** backend is refused (a workspace keeps its state in exactly one location); rebinding to the same one is a no-op, so a builder may bind per phase. |
| `effective_backend_name(*candidates)` | The chain a root's backend resolves through: the first candidate outside the loader's absent sentinels (`default`, `self`, `none`, empty, unset), else `default`. Static. A `none` never reaches it from a configuration: the core's `validate` refuses a state backend written `none` first, since reading it as unset would put the root on the default backend. |
| `bind_workspace(workspace, *candidates)` | `set_backend` through the chain; returns the name bound. The terraform-root builders of [tofu-roots](../tofu-roots/README.md) call it with `(own state_configuration, runtime's state_configuration)`; the identity roots, which have no runtime, with their own value alone. |
| `reference_remote_state(consumer_workspace, producer_workspace, backend_name=None, label=None)` | The consumer reads the producer's state through a `terraform_remote_state` data source. |
| `sensitive_ref(workspace, key, value)` | See [Sensitive values](#sensitive-values-by-reference). |

`BackendRegistration` fields: `name`, `type` (for example `s3`),
`settings` (the type's own, as an opaque mapping), `kind` (the type's
renderings, supplied by the state plugin that declares it) and
`is_default`. Equality is the declaration (name, type, settings, default);
the kind is behaviour and does not take part in the comparison.
`state_location(workspace)` asks the kind for the `StateLocation`
(`<type>://<container>/<key>`, normalised);
`backend_settings(workspace)` and `remote_state_settings(workspace)` for
the partial configuration and the data source. The collector
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
meta-state keeps of where a workspace's state lives: the
backend's name, type and location over its backend-file settings, enough to
write that file again for a migration's previous location.

### Backend emission and partial configuration

Backend and remote-state emission is gated by the global
`config: use_state_backends` flag: `backends_enabled()` answers the
value the instance was made with (`TerraformCollector(backends_enabled=...)`;
the accessor reads it from the run context's `config`, and a fresh tree's
absent flag counts as off). When it is off,
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
everything else quoted. Which keys appear is the kind's decision: the
S3 kind writes `bucket`, `key`, `region`, `encrypt`,
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
state-isolation evidence: the run hooks of
[tofu-roots](../tofu-roots/README.md#the-run-hooks) answer the core's
state-bindings question from them, and the core writes a header line per
workspace (`# state: workspace <ws> -> s3://<bucket>/<key>`) into each
lifecycle's runner script from that answer.

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
   the gid shim), else the default provider. A query value may be a
   derived string that carries the marker inside it
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

`PackerCollector` is the packer counterpart: one instance per run,
reached through `packer_collector(ctx)` (made on the first ask, the same
object after, gone with the context), with `reset()` for a test that
reuses one instance. The packer image builders reach it through their
run context; nothing constructs one in a run.

| Method | Effect |
| -------- | -------- |
| `require_plugin(workspace, name, source=None, version=None, requested_by=None)` | Adds a required plugin; identical requirements dedupe. |
| `declare_variable(workspace, PackerVariableDecl(name, type="string", default=None, description=None, env_var=None, sensitive=False))` | Declares a packer variable; redefinition with different attributes is a conflict. |
| `merged_plugins(workspace)` | One entry per plugin with merged constraints; disagreeing sources are a conflict. |
| `validate_all()` | Run-wide satisfiability per plugin name (sources are not compared run-wide, only per workspace). |
| `generate_packer_block(workspace)` | `packer { required_plugins { <name> = { version, source } } }`. |
| `generate_variable_blocks(workspace)` | `variable "<name>" { type, default, description, sensitive }` blocks through `packer_variable`. With `env_var` the default is `env("<VAR>")` and a `default` given beside it is dropped; a boolean default renders lower-case; a string default is quoted as an HCL string (a `QString` default is passed through as given). |

## HCL rendering helpers

### Blocks

`blocks.py` is a declarative model for `resource`, `data`, `output` and
other top-level blocks, rendered through `python-hcl2`'s builder so no
plugin touches `hcl2.Builder` or `FormatterOptions` directly.

| Name | Meaning |
| ------ | --------- |
| `Raw(str)` | A string emitted unquoted: an address or expression the quoting policy cannot infer, such as `Raw("oktapam_group.x.id")`. |
| `hcl_value(v)` | The shared quoting policy. `Raw` and `QString` pass through; any other string is first passed through the contract's `emitted()` (`cs_image_system.contract.hcl`; the base library's `emit` is the same function under its older name), so a decrypted value becomes the `ENC[age:...]` ciphertext it was read from; then a string starting with `var.`, `data.`, `local.`, `module.`, `each.` or `count.` stays raw and any other string is quoted; booleans and numbers stay raw (booleans render lower-case); list elements and mapping values convert recursively. Mapping keys are the caller's responsibility (pre-quote a key such as `'"system.os_type"'`). |
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
`quoted` is set, except a `var.` reference, which always stays raw).
`QString` is still a `str`, so it compares equal to its bare value
(`QString("abc") == "abc"`). `__new__` defaults `quoted=True`, matching
the class attribute, and sets `value` itself, so `QString("x")` renders
`"x"` and `QString("x", quoted=False)` renders `x`. Then comes the
`TerraformGenerator` protocol
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

Terraform **module calls** are rendered by the contract
(`render_module_call` and `hcl_expr` in `cs_image_system.contract.hcl`,
which the base library's `utils` re-exports), not by this package's
renderers; the terraform roots of [tofu-roots](../tofu-roots/README.md)
call it, and this package renders blocks and the collector-level
scaffolding.
The same holds for `config: module_source_base`: the base library reads it
when it renders a module call, and nothing in this package does.

## Versions

`versions.py` turns terraform and packer constraint strings into
`packaging` specifier sets for conflict analysis while preserving the
original strings for emission. These are the **provider and plugin**
constraint helpers; the check on the tool itself (`tofu --version -json`
against the `cfg/executables.yml` entry's `version`) is
[the version checker](../tofu-roots/README.md#the-version-checker) of
tofu-roots, run by the base library's version-check machinery.

| Function | Behaviour |
| ---------- | ----------- |
| `normalize_constraint(spec)` | Comma-separated clauses. `~> X.Y.Z` becomes `>= X.Y.Z, < X.(Y+1).0`; `~> X.Y` becomes `>= X.Y, < (X+1).0`; `~> X` becomes `>= X, < (X+1)`; `= V` and a bare version become `== V`; `>=`, `<`, `!=`, `==` pass through with their whitespace removed. An empty or `None` spec is unconstrained. A clause `packaging` cannot parse raises `ValueError`. |
| `merge_constraints(specs)` | Returns `(emission, combined)`: the deduplicated originals comma-joined (terraform reads a comma as AND) and the conjunction of their normalized forms. |
| `is_satisfiable(combined)` | Whether some version satisfies the conjunction, tested against a finite witness set: every version literal in the clauses plus its micro, minor and major bumps, and `0`. This catches disjoint pins and non-overlapping ranges; unusual gap constructions may pass. |
| `assert_satisfiable(name, requirements)` | For `(constraint, requested_by)` pairs: returns the merged emission string or raises `HclConfigConflictError` naming the provider, each constraint and who requested it. |

`HclConfigConflictError` (a `RuntimeError`) is the one exception both
collectors raise for contradictory requirements.

## Tests

[`tests/`](tests/) pins the collector (one instance per run context and
nothing shared between two, workspace isolation, dedupe, merged version
emission, source mismatch, cross-workspace conflict, the empty backend
block and the `.tfbackend.hcl` contents, remote-state data sources
across backends, provider aliases and bindings, variable redefinition,
the state-location tuple and its collisions, the binding chain, the
rebinding refusal, the backend record, a registration without a kind),
the packer collector (one per run context too), the block model and the
version helpers. The root mixin and the terraform roots are pinned by
[tofu-roots](../tofu-roots/README.md#tests). `QString`'s default quoting
(quoted unless `quoted=False`) is pinned by
[test_v2_defects_dead.py](../../tests/test_v2_defects_dead.py)
(`test_a_qstring_is_quoted_by_default_and_prints`) in the workspace
suite, and the direction of the imports (only the contract; the
package order is a DAG) by
[test_v2_contract.py](../../tests/test_v2_contract.py). The package's
tests borrow the S3 kind from `tf-s3-state-plugin` to build registrations
and the bare run holder from the workspace suite's `v2_support`, so they
run from the workspace (which always has both).

## Prerequisites and integration

**This is a library, not a plugin.** Nothing here is discovered through an
entry point, nothing here loads configuration, and no configuration file
names this package. It is installed as a workspace member from the root
[pyproject.toml](../../pyproject.toml) by `just init`, and every plugin
that emits HCL pins it at the same version. There is no account, role, API
or credential of its own, and it needs nothing of the core at import
time: a plugin written against the contract alone can use it. What its
OUTPUT needs at execution time is listed here; the commands the terraform
roots emit, and what they need, are
[tofu-roots](../tofu-roots/README.md#prerequisites-and-integration)'.

- **The system's own CLI on `PATH` at execution time.** The `program` of
  the sensitive data source is the bare command `cs-image-system decrypt
  --json`; a plan that runs where the CLI is not installed fails there.
  (The gate, the apply check, the materialisation and the migration steps
  the terraform roots emit need it too; they are
  [tofu-roots](../tofu-roots/README.md#prerequisites-and-integration)'.)
- **The `hashicorp/external` provider, downloadable at `init`.** Any root
  with a sensitive value registers a requirement on it. `init` fetches it
  from the registry unless the root's `.terraform.lock.hcl` and the
  shared `TF_PLUGIN_CACHE_DIR` (exported by the
  [Justfile](../../Justfile) as `.tofu-plugin-cache/`) already hold it.
  The same holds for every provider a builder declares under
  `required_plugins`. One tofu process at a time on a machine: the cache
  is not safe under concurrent `init` (the recipes that execute roots
  hold `.tofu-plugin-cache/.lock` through `cs-image-system --locked`).
- **`CSIS_CONFIG_IDENTITY` in the environment of whoever runs `plan`.**
  The sensitive data source runs `cs-image-system decrypt --json`, which
  opens the ciphertext with that identity (`materialize`, the roots'
  private mirror, needs it too). Without it a real run's generation-time
  plan and every deferred plan fail on the roots that carry ciphertext.
  Where the identity comes from is the base library's contract (this
  repo's `.envrc`; the `CSIS_CONFIG_IDENTITY` repository secret in CI).

**What depends on it.** The terraform roots of
[tofu-roots](../tofu-roots/README.md) and, beside them, the identity
roots of [okta-opa-plugin](../okta-opa-plugin/README.md) and the three
provider root plugins; [packer-plugin](../packer-plugin/README.md) for
the packer collector; the three runtime plugins for the formatter
options. The state plugins and the base library depend on nothing here.

Integration points the rest of the system relies on, all reached as
`terraform_collector(ctx)` on the run context after the builders have
registered:

| Reader | What it takes | Where it lands |
| --- | --- | --- |
| the root mixin and the two neutral roots in [tofu-roots](../tofu-roots/README.md) | `bind_workspace`, `generate_backend_config`, `generate_terraform_block`, `provider_bindings`, `workspace_backend` | the roots' `terraform {}` blocks, backend files and init arguments |
| `lifecycle_state_bindings` in tofu-roots' [`hooks.py`](../tofu-roots/src/cs_image_system/tofu_roots/hooks.py) | `workspace_backend(ws).state_location(ws)` per builder | the `# state: workspace <ws> -> <location>` header lines of each runner script and the run summary |
| `record_state_locations` (same file) | `backend_record(ws)` for every bound workspace not migrating | `meta-state/state-locations.yaml` |
| `state_location_problems` (same file), run by the core's `validate` | `effective_backend_name`, `resolve_backend`, `state_location`, `state_collisions` | validation errors naming the workspace, the backend and the shared object |

## Configuration reference

This package owns no YAML key. What it reads, it reads through the
builders that call it. The table lists every configuration field whose
value reaches this package, the builder that hands it over, and what the
package does with it; the fields the terraform roots read for themselves
(the executable, the apply flags, the run options) are in
[tofu-roots](../tofu-roots/README.md#configuration-reference).

| Field (file) | Type | Default | Handed over by | What this package does with it |
| --- | --- | --- | --- | --- |
| `<builder>.required_plugins[]` / `required_providers[]` (`name`, `version`, `source`, `config`) | list of `TFTofuPluginModel` | `[]` | instance and storage builders (`required_plugins`), the Okta workspace mixin (`required_providers`) | `require_provider(ws, name, source, version)` per entry; merged, conflict-checked, emitted into `required_providers {}`. `name` and `version` are required by `GenericPluginModel` ([`hashicorp_models.py`](src/cs_image_system/hashicorp_utils/hashicorp_models.py)); `source` is optional and omitted from the block when absent; `config` is read by the Okta builders (provider arguments) and ignored by the storage and instance builders. An empty list on a storage or instance root falls back to the provider's own bare requirement (`_provider_name()` from `_provider_source()`: `aws` from `hashicorp/aws` on the AWS roots, `google` from `hashicorp/google` on the GCE roots, `docker` from `kreuzwerker/docker` on the container roots) with no version. |
| `image_builders[].required_plugins[]` (`cfg/image-builders.yml`) | list of `PackerPluginConfig` | `[]` | `PackerBuilderBase.generate_items_before` | `require_plugin(ws, name, source, version)`; emitted into `packer { required_plugins {} }`, one file per block. |
| `<builder>.state_configuration` (instance, storage, group, user builders) | str | `default` | `bind_workspace(ws, own, runtime's)` | First rung of the chain. A value outside `default`, `self`, empty, unset names a backend registration; the name must exist (`validate` refuses one that does not). `none` is refused by `validate` by name: it would read as unset. |
| `runtime_builders[].state_configuration` (`cfg/runtime-builders.yml`) | str | `default` | `runtime_state_configuration()` of the root mixin, as the second argument of `bind_workspace` | Second rung, for storage and instance roots only. |
| `state_backends[]` (`cfg/state-backends*.yml`): `name`, `type`, `is_default`, the type's own settings | per type | | `pull_declared_backends(models)`, called by `terraform_collector(ctx)` when it makes the run's instance, with the context's state backend models, each answering `to_backend_registration()` | Stored by name; `is_default` decides what `default` resolves to; `settings` are rendered by the plugin's kind, never read by name here. |
| `config.use_state_backends` (`cfg/_config.yml`) | bool | `false` | `TerraformCollector(backends_enabled=...)`, read from the run context's `config` by `terraform_collector(ctx)` when it makes the instance | The gate on every backend block, backend file, remote-state data source, header line and location record. Location **collisions** are still checked with it off. |
| `config.module_source_base` (`cfg/_config.yml`) | str | `../tfmodules` | nobody here | **Not read by this package.** The base library's `render_module_call` reads it. Listed because module calls sit beside the blocks this package renders. |
| a builder's `OktaTfWorkspaceModelMixin.key` / `.secret` and any provider `config` value | str, possibly `ENC[age:...]` | | `sensitive_ref` and `hcl_value` | A value carrying a marker is emitted as its ciphertext (by reference through `local.sensitive[...]` for the Okta credentials; inline for any other block argument). |

### Variations

- **Backends enabled vs disabled.** Enabled: an empty `backend "<type>"
  {}` block, a `.tfbackend.hcl`, `terraform_remote_state` data sources,
  and from the roots `-backend-config=<file>` on every real init, the
  runner header lines and the location record. Disabled: none of those; `init` runs bare and
  a consumer's remote-state read is not emitted at all, so a module that
  needs a producer's outputs cannot work.
- **Own `state_configuration` vs the runtime's vs the default.** The
  first value outside the absent sentinels wins; the identity roots skip
  the runtime rung. A root bound once cannot be rebound to a different
  backend in the same run.
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
  (lower-case for a boolean, quoted for a string, raw for a number).

## What it tests and verifies

Nothing in this package runs at load beyond the pydantic validation of a
`required_providers:` / `required_plugins:` entry (`GenericPluginModel`:
`name` and `version` required, `source` optional, `config` a mapping).
Its checks run when a builder registers into a collector and when a
generator is called.

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
  data source -- the contract's `BackendWithoutKind` (a `RuntimeError`):
  `State backend '<name>'
  (type '<type>') was registered without a kind ...`.

The verdict of all of these is an exception out of the generating builder;
the run logs it and exits 1, `run-summary.json` carries it as `error`, and
nothing of that lifecycle is emitted.

**Not checked here.** The existence of the providers a `required_plugins`
entry names (tofu's `init` finds out); the syntax of a `version`
constraint beyond what `packaging` parses; the validity of a
`sensitive_ref` key as an HCL attribute name; the plaintext guard over
`generated/` (the base library's, at `validate` and every commit); the
commands the terraform roots emit and what they check at execution
([tofu-roots](../tofu-roots/README.md#what-it-tests-and-verifies)).

## When it fails

Incidents that have happened, with their cause and fix, are recorded on
[INCIDENTS.md](../../docs/INCIDENTS.md); what follows keeps each
failure's symptom, its meaning and what to do.

The table covers the exceptions the collectors raise and the one packer
rendering trap. The messages of the emitted terraform sequence (the gate,
the apply check, the migration steps, tofu's own) are
[tofu-roots](../tofu-roots/README.md#when-it-fails)'. Each row is the
symptom, what it means and what to do.

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
| `ValueError` from `packaging` naming an invalid specifier | a `version` constraint such as `>= 1.x` | the entry's `version`; use `>=`, `<`, `~>`, `=`, `!=` forms |
| a packer template fails to parse at `default = 1.0.0` | a string default reached the template unquoted; `packer_variable` quotes a plain `str` default as an HCL string and passes a `QString` default through as given | the caller handed a `QString(..., quoted=False)` or a `Raw`; let a plain string through instead |
