# Data model: the words a query is looked up by

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Research**: [research.md](research.md)

Nothing new is stored. This is the vocabulary the lookup works in, and
the one rule that joins a runtime's written word to the blocks that
answer it.

## The words

| Term | What it is | Example | Where it lives |
| --- | --- | --- | --- |
| **Written word** | the `type:` a runtime entry carries, as the tree wrote it | `docker` or `docker-runtime/docker` | the runtime model's `type_` (`get_type()`); recorded as written, read by every message |
| **Bare word** | the class's own name, `csis_name()` | `docker` | the class; the key of its blocks in its plugin's part |
| **Namespace** | what qualifies the class's words: from its distribution, or what its metadata names | `docker-runtime`, `aws-runtime`, `testing` | `Registry.namespace_of_class(cls)` |
| **Listed word** | the word the registry lists the class by: the bare word while one class answers to it, the qualified word where two different classes do | `docker`; `one/rt` and `two/rt` for a shared `rt` | the keys of `Registry.runtime_builder_classes()` |
| **Resolved runtime** | the one installed runtime class a written word names, with its listed word | (`docker`, `DockerRuntimeBuilder`) | found by `_names_the_same(written, listed)` over the listed words |

`_names_the_same` is the existing rule
([image_sources.py](../../packages/base/src/cs_image_system/base/image_sources.py)
lines 397 to 406): a word matches its own spelling; a bare word or a
bare listed word matches the other's bare part; two qualified words
match only when equal. A written word that the load accepted names
exactly one listed word (a bare word two classes share is refused at
load as ambiguous, and a namespace no plugin has is refused as
unknown).

## The two layers

| Layer | Made of | Blocks keyed by | What a block lookup reads (after this change) |
| --- | --- | --- | --- |
| **Release** | each installed runtime plugin's **part**, `image_source_entries()` of its builder class | the runtime's bare word | the resolved runtime's own part only, under its bare word, when the runtime is declared (or the reader is the stand-in) |
| **Tree** | `cfg/image-sources*.yml`, key `image_sources` | a bare word (the documented form) or a qualified word | the entry's block under the resolved runtime's bare word, then its block under `<its namespace>/<bare word>` landing on it |

What a family IS (`is`, description, versions) is read from the merge
of the declared runtimes' parts under the tree's layer, as today; only
the per-runtime block changes how it is found.

## The lookup, in order

For an OS builder entry on a runtime whose written word is `W`, family
`F`, version `V`:

1. Resolve `W` to the runtime (listed word `L`, class `C`, bare word
   `b`, namespaces `N`). If `W` names no installed runtime, the lookup
   is today's: `sources[W]` in every layer.
2. Release layer: the entries of `C`'s own part that match `F` and `V`
   (the generic entry, then the version's), each giving its `b` block.
3. Tree layer: the matching entries the same way, each giving its `b`
   block, then its `n/b` block for each `n` in `N`, in that order.
4. Every block found lands on the one before it, key by key; `{version}`
   is filled.
5. The OS builder's own `query`, the entry's `query` and the declared
   publishers land on that, as today (`image_query()`).

With one class per bare word, steps 2 and 3 read exactly what today's
lookup reads for the bare word, so a bare tree is unchanged.

## The tree's keys, checked

A key under a tree entry's `sources` **names an installed runtime**
when it is an installed runtime's bare word, or `<namespace>/<word>`
for an installed runtime of that namespace and bare word. `validate`
says one WARNING line for each key that names none, with the entry's OS family and
the installed words. Nothing is refused for it.

## The stand-in

| Before | After |
| --- | --- |
| `stand_in_types(classes)`: the `csis_name()` of each class with a local target | the listed word of each such class (the key in `classes`) |
| `stand_in_runtime_type(classes, named)`: `named` must equal one of them | `named` is read by `_names_the_same`, and the listed word it names is returned |

With one class per bare word the listed word is the bare word: the
docker family's runtime is still `docker` everywhere it is printed.

## Invariants

- A bare tree's queries, fingerprints and emission do not change.
- A written word is never rewritten: messages, logs and records name it
  as the tree wrote it.
- A block is read from one plugin's part only, the part of the runtime
  the word names; another plugin's part never answers it.
- `meta-state/runtime-facts.yaml` is keyed by a runtime's name, so the
  two forms record the same facts.
