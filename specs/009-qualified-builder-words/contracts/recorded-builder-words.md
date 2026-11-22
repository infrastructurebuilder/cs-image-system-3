# Contract: the word a builder is recorded by

**Feature**: [spec.md](../spec.md) | **Plan**: [../plan.md](../plan.md) |
**Data model**: [../data-model.md](../data-model.md)

Three documented rules change: what the system records for a builder's
`type:` (read by an operator and an adopting team, stated in
[CONFIGURATION.md](../../../docs/CONFIGURATION.md) section 1.2 and
[base's README](../../../packages/base/README.md#the-registry)); what a
model's `type_` holds once loaded (read by a plugin author); and where
the Terraform collector takes a backend's label from (stated in
[hashicorp-utils' README](../../../packages/hashicorp-utils/README.md)).
The plugin contract (`packages/contract`) does not change, no provider
plugin changes, and no member of a declared surface is added, removed or
altered.

## 1. A configuration's `type:` on a builder

What a tree may write is unchanged: the bare word while one installed
class answers to it, the qualified word `<namespace>/<word>` always.

| The tree writes | Loads | What the run emits and records |
| --- | --- | --- |
| a bare word one class answers to (`s3`) | that class | the bare word (unchanged) |
| that class's qualified word (`tf-s3-state/s3`) | that class | the bare word, as if the tree wrote it bare |
| a bare word two classes answer to (`local`) | refused, naming every qualified form (unchanged) | nothing |
| one of those classes' qualified words (`twin/local`) | that class | the qualified word, the one word that names it; an external tool still reads its own word (`backend "local"`) |
| a namespace no plugin has (`nobody/s3`) | refused, naming the extra that installs it where the umbrella knows (unchanged) | nothing |

The rule replaces "what a tree wrote is what is recorded: a bare word
stays bare, a qualified word keeps its namespace". The new statement,
for base's README and CONFIGURATION 1.2: *a builder's `type:` is read
once, at the load, as the word the registry lists its class by; what a
run emits and records holds that word, whichever form the tree wrote;
the configuration files keep the word as written, since the system
never rewrites them.* Under D1's default the sentence names its one
exception: a runtime's word keeps the form the tree wrote, because the
image-source catalog resolves it itself
([spec 006](../../006-qualified-runtime-type/contracts/image-source-keys.md)).

## 2. What a plugin author sees

| Member | Before | After |
| --- | --- | --- |
| a builder model's `type_` / `get_type()`, and its builder's | the word as the tree wrote it | the class's registered word: its `csis_name` while it alone answers to it, else `<namespace>/<csis_name>` |
| `BackendRegistration.type` (filled from `type_` by the plugin) | as written | the registered word |
| a root's backend label | `BackendRegistration.type` | the registration's `kind.type` (every kind here and in the Google Cloud family declares one, equal to its class's `csis_name`) |

Nothing a plugin does changes. A plugin that copies its model's
`type_` into output now writes a word that never carries a namespace
for one class per word. A plugin whose backend kind declares no `type`
keeps today's label, the registration's `type`.

## 3. The Terraform collector

[`TerraformCollector`](../../../packages/hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py):

| Output | Before | After |
| --- | --- | --- |
| `generate_terraform_block`: `backend "<label>"` | `reg.type` | `reg.kind.type`, else `reg.type` |
| `generate_remote_state_datasources`: `backend = "<type>"` | `reg.type` | `reg.kind.type`, else `reg.type` |
| `generate_backend_config`: the comment line | `reg.type` | unchanged (`reg.type`, the registered word) |
| `backend_record`: `type` | `reg.type` | unchanged (the registered word) |

Signatures are unchanged; the Terraform line takes a PATCH.

## 4. The bootstrap interview's facts

[`default_state_backend(facts, kind)` and `other_state_backends(facts, kind)`](../../../packages/engine/src/cs_image_system/engine/bootstrap/facts.py):
a declared state backend whose `type` is `kind`, or `<anything>/kind`,
is a backend of that type. The `FactsProtocol` a plugin's section reads
is the contract's and does not change; only what it answers does.
