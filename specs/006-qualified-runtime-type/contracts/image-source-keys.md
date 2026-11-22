# Contract: the words an image source answers

**Feature**: [spec.md](../spec.md) | **Plan**: [../plan.md](../plan.md) |
**Data model**: [../data-model.md](../data-model.md)

Two interfaces change: what a tree may write as a key under
`image_sources[].sources` (read by an adopting team and an operator),
and what the kit's catalog answers for a runtime's word (read by the
kit's own models and the engine; not on the kit's declared surface).
The plugin contract (`packages/contract`) does not change, and no
plugin's part changes: a plugin keeps keying its blocks by its bare
runtime word.

## 1. A tree's `cfg/image-sources*.yml`

```yaml
image_sources:
  - family: debian
    sources:
      docker:                       # the bare word: every runtime of this word, either form
        publisher: ["library"]
        name: debian
        version: "{version}"
      docker-runtime/docker:        # a qualified word: this namespace's runtime only,
        version: "{version}-slim"   # landing on the bare block, key by key
```

| A key | Answers | Notes |
| --- | --- | --- |
| a runtime's bare word (`docker`) | every runtime of that bare word, whether the runtime is written `docker` or `docker-runtime/docker` | the documented form; unchanged for a bare tree |
| `<namespace>/<word>` of an installed runtime (`docker-runtime/docker`) | that runtime only, written either way; lands on the same entry's bare block | the one way to give two runtimes of one bare word (story 3) different blocks |
| a word no installed runtime registers (`awz`, `nobody/docker`) | nothing | `validate` prints one WARNING line naming the entry's OS family, the key and the installed runtime words. Not a refusal |

Keys are lowercased at load, as today. The landing order across
entries is unchanged: the release's generic entry, the release's entry
for the version, the tree's generic entry, the tree's entry for the
version; inside one tree entry, its bare block, then its qualified
block.

## 2. The kit's catalog: `ImageSourceCatalog`

[`packages/base/src/cs_image_system/base/image_sources.py`](../../../packages/base/src/cs_image_system/base/image_sources.py)

| Member | Before | After |
| --- | --- | --- |
| `block(family, version, runtime_type, *, beside_declared=False)` | `runtime_type` is the exact key in every layer | `runtime_type` is a written word, bare or qualified. It is resolved to the installed runtime it names; the release layer answers from that runtime's own part under its bare word, the tree layer under the keys of section 1. A word that names no installed runtime is looked up exactly, as before |
| `stand_in_block(family, version)` | the block keyed by the stand-in's `csis_name()` | the block of the stand-in runtime, found by its listed word; the same block for one class per bare word |
| `stand_in_types(classes)` (module function) | each stand-in's `csis_name()` | each stand-in's listed word (its key in `classes`) |
| `stand_in_runtime_type(classes, named=None)` | `named` must equal a `csis_name()` | `named` is read bare or qualified; the listed word it names is returned |
| new: the tree keys that name no installed runtime | absent | a read-only method over the tree's entries, for `validate`'s warning; its name is the implementation's |

Unchanged: `set_declared`, `effective_family`, `knows`, `families`,
`default_entries`, `tree_entries`, `layers`, `merge_entries`'s result
for parts that do not share a bare word, and every message's wording
of the runtime's word (as written).

## 3. `validate`

[`check_image_sources`](../../../packages/engine/src/cs_image_system/engine/commands/validate.py):

- no entry is refused for want of an image source when the bare word's
  block would answer it (FR-001);
- the refusal for an entry with no source in any layer stays, naming
  the runtime's type as written (FR-006);
- one WARNING per tree key that names no installed runtime (FR-004).

## 4. The bootstrap interview's facts

[`runtimes_of_type(facts, word)`](../../../packages/engine/src/cs_image_system/engine/bootstrap/facts.py)
and `first_runtime_name(facts, prefer=...)`: a declared runtime whose
`type` is `word`, or `<anything>/word`, is a runtime of that type. The
`FactsProtocol` a plugin's section reads is the contract's and does not
change; only what it answers does.
