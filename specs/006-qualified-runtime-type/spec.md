# Feature Specification: A runtime written by its qualified word works as its bare word does

**Feature Directory**: `specs/006-qualified-runtime-type`

**Feature Branch**: `feature/006-qualified-runtime-type` (to be created from `develop` when planning starts)

**Created**: 2026-11-19

**Status**: Draft

**Input**: User description: "A runtime whose type: is written in its qualified form (for example gcloud-runtime/gcloud instead of gcloud) loads, but validation then refuses every OS builder entry on that runtime with 'no image source: the image-source catalog has no `gcloud-runtime/gcloud` block', because the image query asks the image-source catalog for a block under the type word exactly as the configuration wrote it, while the catalog keys its blocks by the bare runtime type. Every other qualified word (instance, storage, state builders) already works. Found by spec 005's test of qualified words (T028) in the Google Cloud family's repository; the cause is in this repository's core, not in any provider. A configuration that writes a qualified runtime type should validate, bake and emit exactly as the bare form does. Serves operators and an adopting team."

A qualified name is one with a '/' with the namespace being the part before the '/' and the name the part after.  Implicit qualifications based on the loading plugin are allowed.

**Users served**: operators (who write a qualified word to say which plugin they mean, or must once two plugins register one bare word); an adopting team (whose tree, copied from a starter or written by hand, may use either form).

## Why

Every word a configuration writes for a `type:` has two forms: the bare
word (`gcloud`), which is enough while one installed plugin registers it,
and the qualified word (`gcloud-runtime/gcloud`), which names the plugin's
namespace and always works. The system promises that the two forms are the
same declaration: a configuration that writes either loads the same class.
Specification 005 promises the Google Cloud family keeps this promise after
its move, and its test found the one place the promise breaks.

A runtime written by its qualified word loads, but every OS builder entry on
it is refused at validation: the vendor-image lookup asks the image-source
catalog for a block under the word as written, and the catalog keys its
blocks by the bare word. So the qualified form, the one that is supposed to
work always, is the one that does not. Nothing tells the operator that the
bare form would have worked, and the refusal names a catalog block as
missing that exists.

This matters most exactly when the qualified form is needed: once two
installed plugins register the same bare runtime word, the bare form is
refused as ambiguous, and the qualified form is then the only one a
configuration can write. Today that configuration cannot bake.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A qualified runtime word validates, bakes and emits as the bare word does (Priority: P1)

An operator writes `type: gcloud-runtime/gcloud` for a runtime instead of
`type: gcloud`, and every command behaves exactly as it does for the bare
word: the configuration validates, its bakes find their vendor images, and
what a run emits is identical.

**Why this priority**: this is the defect. It breaks the promise that the
two forms are one declaration, and it breaks it in the form that is meant to
work always.

**Independent Test**: one configuration, run twice, once with each runtime
written bare and once with each written qualified: both validate, and the
two emissions are identical file for file.

**Acceptance Scenarios**:

1. **Given** a tree whose runtime is written `gcloud-runtime/gcloud`,
   **When** it is validated, **Then** no OS builder entry on that runtime is
   refused for want of an image source, and the vendor-image query is the
   one the bare word gives.
2. **Given** the same tree written once with bare runtime words and once
   with qualified ones, **When** both are dry-run, **Then** the two
   emissions are identical.
3. **Given** every runtime type an installed plugin registers (AWS, Google
   Cloud, docker), **When** each is written qualified, **Then** each
   behaves as its bare word does.

---

### User Story 2 - A tree's own image sources answer either form (Priority: P2)

An adopting team keeps an image-source layer of its own
(`cfg/image-sources.yml`) whose blocks name runtime types, and a runtime
written by either form finds the tree's block as well as the release's.

**Why this priority**: the tree's layer is the second place a runtime type
is a key; a fix that mends the release's catalog and not the tree's would
leave the same refusal one step further on.

**Independent Test**: a tree with its own block for a runtime type, its
runtime written qualified: the tree's block overrides the release's, as it
does for the bare word.

**Acceptance Scenarios**:

1. **Given** a tree's own block under the bare word and a runtime written
   qualified, **When** the query is formed, **Then** the tree's block applies.
2. **Given** a tree's own block written under the qualified word, **When**
   the runtime is written bare, **Then** the tree's block applies too, or
   the tree is told plainly that the key must be the bare word; never is it
   silently ignored.

---

### User Story 3 - Two plugins, one bare runtime word (Priority: P3)

When two installed plugins register the same bare runtime word in
different namespaces, a configuration that writes each runtime by its
qualified word gets each plugin's own image sources, never the other's.

**Why this priority**: this is the situation the qualified form exists for;
the fix must not resolve the qualified word to "the bare word" and then
pick an arbitrary plugin's catalog.

**Independent Test**: two stand-in runtime plugins registering one bare
word, each shipping its own image-source block; a tree declaring one
runtime of each by its qualified word: each runtime's query is its own
plugin's.

**Acceptance Scenarios**:

1. **Given** two plugins that each register the bare word `rt` and ship a
   block for it, **When** a tree writes `one/rt` and `two/rt`, **Then** each
   runtime's query comes from its own plugin's block.
2. **Given** the same two plugins and a tree that writes the bare `rt`,
   **When** it loads, **Then** it is refused as ambiguous, as today, and the
   refusal names both qualified forms.

---

### Edge Cases

- A runtime written by a namespace that no installed plugin has is refused
  at load as today, naming the namespace; the image-source check never sees it.
- The runtime facts a load records (`meta-state/runtime-facts.yaml`) name a
  runtime's type; they must not differ between the two forms in a way that
  a later load reads as a change of runtime.
- The refusal for a runtime that truly has no image source (no catalog
  block, no query on the OS builder or the entry, no pinned image) still
  says so, and names the runtime's type in the form the configuration wrote
  it, so the operator recognises their own word.
- Messages and logs that name a runtime's type keep naming it as the
  configuration wrote it; only the catalog lookup is affected.
- The stand-in a modification test runs a bake on (the catalog's stand-in
  block) is reached the same way for either form.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The vendor-image query for an OS builder entry MUST be the
  same whether its runtime's type is written bare or qualified.
- **FR-002**: The image-source catalog MUST be consulted for the block of
  the runtime plugin the written word resolves to, in the release's layer
  and in a tree's own layer alike.
- **FR-003**: When two installed plugins register one bare runtime word, a
  runtime written by its qualified word MUST get its own plugin's image
  sources and never another plugin's.
- **FR-004**: A tree's own image-source block keyed by a runtime type MUST
  apply to a runtime written by either form of that type; a block keyed by
  a word no installed runtime plugin registers MUST be named as such, not
  silently ignored.
- **FR-005**: A dry run of a configuration MUST emit identically whether
  its runtimes are written bare or qualified.
- **FR-006**: The refusal for a runtime with no image source at all MUST
  remain, and MUST name the runtime's type as the configuration wrote it.
- **FR-007**: Every golden MUST stay unmoved: every existing configuration writes its
  runtimes bare, and the bare form's behaviour does not change
  (Constitution IV).
- **FR-008**: The Google Cloud family's test of qualified words
  (`tests/pipeline/test_qualified_words.py` in its repository, spec 005's
  T028) MUST be able to drive a whole run for the qualified form once this
  repository releases the fix, and the family's next release MUST say so.

### Key Entities

- **A type word**: the `type:` a configuration writes for a builder, bare
  (`gcloud`) or qualified (`gcloud-runtime/gcloud`); both resolve to one
  registered class.
- **The image-source catalog**: the release's layer (each runtime plugin
  ships the blocks for its own runtime types) under a tree's own layer;
  blocks are keyed by family, version and runtime type.
- **A runtime plugin's namespace**: what qualifies its words; derived from
  its distribution's name.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every runtime type the installed plugins register, a
  configuration written with the qualified word validates with zero
  image-source refusals that the bare word does not also produce.
- **SC-002**: A dry run of the shared fixture with every runtime written
  qualified emits a tree identical, file for file, to the golden.
- **SC-003**: With two stand-in plugins registering one bare runtime word,
  each qualified runtime's query is its own plugin's in 100% of runs.
- **SC-004**: No golden file in this repository moves.

## Assumptions

- The qualified form is already resolved correctly at load for every
  builder kind (the registry's lookup); only the image-source lookup reads
  the written word directly. The plan confirms that by search, since a
  second place reading a runtime's written word as a key would have the
  same defect.
- A tree's own image-source layer today keys blocks by bare words; keeping
  bare words as its documented form, and accepting a qualified key that
  names an installed plugin, is the default; the plan decides whether a
  qualified key is accepted or refused with a clear message (FR-004 allows
  either, never silence).
- The fix is in this repository's core; no provider plugin changes, and the
  contract does not change.
- This specification follows spec 005 and does not wait for it: it changes
  code spec 005 does not touch.
