# Data model: the words a builder is known by

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Research**: [research.md](research.md)

Nothing new is stored. This is the vocabulary the change works in, the
one rule that joins a builder's written word to the word every reader
after the load sees, and where each word lands. The terms extend
[spec 006's](../006-qualified-runtime-type/data-model.md).

## The words

| Term | What it is | Example | Where it lives |
| --- | --- | --- | --- |
| **Written word** | the `type:` a builder entry carries, as the tree wrote it | `s3` or `tf-s3-state/s3` | the configuration file only, after this change |
| **Bare word** | the class's own name, `csis_name()` | `s3` | the class; the name part of every key it is registered under |
| **Namespace** | what qualifies the class's words: from its distribution, or its metadata | `tf-s3-state`, `local-state`, `default-os` | `Registry.namespace_of_class(cls)` |
| **Registered word** | the word the registry lists the class by under its classification: the bare word while the class is the one that answers to it, else `<namespace>/<bare word>` | `s3`; `local-state/local` and `twin/local` for two classes of `local` | a key of `Registry.models_under(vct)`; after this change, the model's `type_` (`get_type()`), and so the builder's |
| **Own key** | the class's own registration key, read directly | `tf-s3-state/s3` | `<namespace_of_class(cls)>/<csis_name>` |
| **Tool word** | the word an external tool reads for the class | OpenTofu's backend type `s3` | a state backend's kind: `BackendKindProtocol.type` |

The registered word always resolves to its class, by construction of
`models_under`, in a tree and in any later lookup. With one class per
bare word (every fixture, starter and reference configuration) the
registered word is the bare word, so a bare tree reads exactly as
before.

## The rule, at the edge

For a builder entry structured under classification `V` (every builder
model classification; the runtime's only by D1's other answer):

1. Resolve the written word `W` under `V`, as today (`_resolve`): a
   qualified word directly; a bare word when one class answers; refused
   at load when none does (`UnknownTypeError`) or when several do
   (`AmbiguousTypeError`, naming every qualified form). The refusal
   names `W`.
2. Find the class's registered word `R` under `V`.
3. Structure the entry with `type: R`. The model's `type_` is `R`.
4. Build the model's builder from the class registered under the model
   class's own key in the builder classification.

Steps 2 and 3 replace today's "keep a written namespace" rewrite; step
4 replaces the lookup by the bare `csis_name`.

## Where each word lands, before and after

| Reader | Reads | Before | After |
| --- | --- | --- | --- |
| A state plugin's `to_backend_registration()` | `type=self.type_` | written | registered |
| The collector: a root's `backend "<label>"` and a consumer's `terraform_remote_state` `backend` | the registration | `registration.type` (written) | the kind's `type` (tool word); `registration.type` only for a kind that declares none |
| The collector: the backend file's comment, `meta-state/state-locations.yaml`'s `type` | `registration.type` | written | registered |
| The OS builder's update comment in the Packer build | `get_type()` | written | registered |
| `meta-state/storage.yaml`'s `plugin` | the storage builder's `get_type()` | written | registered |
| `meta-state/identity.yaml`'s `user_builders` | each user builder's `get_type()` | written | registered |
| The loader's builder class for a model | the model class | its bare `csis_name` (ambiguous in story 3) | its own key |
| The class of a builder's deferred items (`mod_builder_item_model` in the shared fixture) | the builder's `get_type()` | written | registered |
| The fingerprint, lineage | modification items' builder instance names | unchanged | unchanged |
| A message after the load | `get_type()` | written | registered |
| A refusal at load | `W` | written | written |
| The bootstrap interview's state-backend lookups | raw YAML `type` | equal to the section's word | equal, or its name part equal |

## Story 3, worked

Two installed plugins register different state backend classes under
`local`: the local state plugin (namespace `local-state`) and a
test-only twin (namespace `twin`).

| Tree writes | Load | Model `type_` | Root's label | Backend file comment | State-location `type` |
| --- | --- | --- | --- | --- | --- |
| `local` | refused: ambiguous, naming `local-state/local, twin/local` | | | | |
| `local-state/local` | the local state plugin's model and builder | `local-state/local` | `local` | `(local-state/local)` | `local-state/local` |
| `twin/local` | the twin's model and builder | `twin/local` | `local` | `(twin/local)` | `twin/local` |

The location each records (`local://state/<workspace>.tfstate`) is the
kind's rendering, the same as either plugin alone would record.

## Invariants

- A bare tree's emission, records and fingerprints do not change; both
  goldens stay unmoved.
- A tree that writes a qualified word emits and records what the bare
  tree does, wherever one class answers to the bare word.
- The written word is never written into the emission or a record.
- An external tool reads only a plugin's own word (the kind's type),
  never a configuration word.
- No provider plugin changes; a model's `type_` keeps its declared type
  (`str`) and meaning ("the word that names my class"), now always a
  word that resolves without ambiguity.
