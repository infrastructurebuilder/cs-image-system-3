# cs-image-system-contract-example-plugin

The proof of the plugin contract (stage 30, branch 2): a state backend
plugin written against [cs-image-system-contract](../contract/README.md)
and nothing else of the system. Its `pyproject.toml` depends on the
contract and `pydantic`; its sources import `cs_image_system.contract`
and the standard library; a test fails the moment any of them names
`cs_image_system.base`, `cs_image_system.system` or
`cs_image_system.hashicorp_utils`. The model and the builder subclass
none of the core's base classes: they satisfy the contract's protocols
structurally, and the registry, the mapper, the runner and the terraform
collector drive them exactly as they drive the three built-in state
plugins. Without this package the contract is a claim.

The backend it provides is OpenTofu's `inmem`: a workspace's state kept in
the running process's memory. No bucket, no file, no credentials, and
gone when the process ends, which makes it useless for a real tree and
exactly right for a proof -- every line is contract, nothing is
borrowed. It registers the `type:` key `inmem` for entries under
`state_backends:`. The package is a workspace member like every other
and is installed with the whole system (the dummy plugin's precedent),
but the published starters do not declare its key: a tree that binds a
root to it loses that root's state at the end of the process.

## What it registers

| What | Class | `csis_name()` | `csis_classifier()` |
| --- | --- | --- | --- |
| the model | [`InmemStateBackendModel`](src/cs_image_system/contract_example_plugin/models.py) | `inmem` | `STATE_BACKEND_MODEL` |
| the builder | [`InmemStateBuilder`](src/cs_image_system/contract_example_plugin/builder.py) | `inmem` | `STATE_BACKEND` |

The entry point `cs_image_system.plugins.state`
(`contract_example_plugin = cs_image_system.contract_example_plugin.main:initialize`)
returns the contract's `PluginMetadata` record with the two classes under
the service `inmem` and the model mapped to the builder
([`main.py`](src/cs_image_system/contract_example_plugin/main.py)). The
plugin's `version` is its distribution's.

## What it shows a plugin author

- **The model** is a pydantic dataclass under `CSIS_MODEL_CONFIG` that
  declares the nine fields every builder model carries (`name`, `type`,
  `description`, `aliases`, `executable`, `is_default`, `config`,
  `gitignore`, `tags`), their readers, `finalize`, `global_id`, the two
  class methods, and the kind's own answer, `to_backend_registration()`.
  Its `__post_init__` applies the two rules the core's models apply to a
  name: the key is `safe_name` of what was written, and no sentinel in
  `OOPS_DEFAULTS` may be a name.
- **The kind** (`InmemBackendKind`) is what the backend type knows:
  `location` (`inmem://memory/<workspace>.tfstate`, one per workspace so
  the collision check has something to compare), `backend_settings` (the
  `lock_id`, when declared) and `remote_state_settings` (nothing: an
  in-memory state has no address).
- **The builder** implements the contract's `StateBuilderProtocol`
  member by member: the names and the classification, the six universal
  lifecycle hooks and the three finalize-phase hooks (all returning their
  empty value: a state backend emits nothing and runs nothing), `finalize`,
  and the paths the runner files output under. It is the whole surface the
  core drives on any builder, with nothing inherited; a plugin that
  subclasses the core's `StateBuilderBase` instead gets all of it for free.
- **The registration reaches the collector without the plugin knowing the
  collector exists**: once the state backends are loaded the core hands
  every model's `to_backend_registration()` to `hashicorp-utils`.

## Prerequisites and integration

Nothing outside Python: the package needs Python 3.13 or later,
`cs-image-system-contract` and `pydantic`. OpenTofu's `inmem` backend
is built in; a root bound to it needs no bucket, file, credential or
network. The plugin is found through its entry point like every plugin.

## Configuration reference

An entry under `state_backends:` in `cfg/state-backends*.yml`:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `name` | str | required | The backend's name; a root's `state_configuration` names it. `safe_name` normalises it; not a word in `OOPS_DEFAULTS`. |
| `type` | str | `inmem` | The plugin's key. |
| `description` | str or null | null | Free text. |
| `aliases` | set of str | empty | Other names the backend answers to. |
| `executable` | str or null | null | The `executables:` entry the roots on this backend run, version-checked at validation; null for none. |
| `is_default` | bool | false | The backend `default` resolves to; one per configuration. |
| `config`, `gitignore`, `tags` | mapping, list, mapping | empty | Carried as on every builder model; this plugin reads none of them. |
| `lock_id` | str or null | null | OpenTofu's one `inmem` setting, written into the workspace's backend file when declared; an empty string is refused. |

Unknown keys are refused by `CSIS_MODEL_CONFIG`. Variations: none; a dry
run and a real run emit the same blocks, and the backend behaves the
same on every runtime.

```yaml
state_backends:
  - name: scratch
    type: inmem
    description: state that lives only while the process does
```

## What it tests and verifies

The plugin checks nothing of its own at load, validate, generation or
apply beyond the model's `__post_init__` (the name rules, the empty
`lock_id`). What verifies the plugin is
[tests/test_v2_contract_example.py](../../tests/test_v2_contract_example.py)
in the core's bar: the sources import nothing from the core; the
manifest declares the contract and `pydantic` alone;
`assert_conforms` over the model and the builder against the kind's
protocols, and the runtime `isinstance` checks the loader, the registry
and the orchestrator make; the plugin loads by entry point and the
registry holds its classes; an entry structures from YAML in a copy of
the frozen fixture; and a dry `run --all` over that copy, with the
storage roots bound to the entry, emits `backend "inmem" {}` in those
roots, their backend files, and `terraform_remote_state` data sources
with `backend = "inmem"` in the roots that read their state, and records
their `inmem://memory/...` locations.

## When it fails

- A test in `tests/test_v2_contract_example.py` naming an import of
  `cs_image_system.base`, `.system` or `.hashicorp_utils`: the proof is
  broken; the plugin must be written against the contract alone.
- `AssertionError: ... does not conform to StateBackendModelProtocol` or
  `StateBuilderProtocol`: the contract changed (it is upstream) and the
  plugin did not follow; add the member or match the signature.
- `state backend '<name>': lock_id is empty; omit it or name one` at
  load: the entry declared `lock_id: ""`.
- `Name cannot be in '[...]'` at load: the entry's name is a sentinel.
- A root bound to an `inmem` backend in a real run: `tofu init` succeeds,
  the apply's state is in the process's memory and is gone when it ends,
  so the next run plans everything again. That is the backend doing what
  it says; bind real roots to `s3`, `local` or `gcs`.

No failure of this package has happened in the field (2026-10-29): it is
the proof, not a backend for a real tree.

## Related

- [contract](../contract/README.md): the package this one is written
  against, and "Writing a plugin".
- [local-state-plugin](../local-state-plugin/README.md): the same kind
  written the convenient way, on the core's base classes.
- [docs/PLUGINS.md](../../docs/PLUGINS.md): the index of every package.
