# Research: A runtime written by its qualified word works as its bare word does

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Each item is marked **read** (a fact taken from the code as it stands on
`develop` at `35446e3f`, release 0.1.12), **decided** (only where the
spec's Clarifications record the operator deciding it; the spec has
none yet, so nothing here is **decided**), or **chosen** (this plan's
choice, with the alternatives weighed). The operator's open decisions
are named **YOUR DECISION**, each with its default, and gathered in
[plan.md](plan.md#decisions-in-this-plan).

## R1. Where the defect is

**Read**:

- An OS builder's runtime entry forms its query in one place,
  `image_query()` in
  [os_builder_runtime_config.py](../../packages/base/src/cs_image_system/base/models/os_builder_runtime_config.py)
  (lines 210 to 235). It asks the catalog for the block of
  `runtime_type()` (lines 203 to 208), which is the runtime model's
  `get_type()`: the `type:` word exactly as the tree wrote it
  (`aws-runtime/aws`).
- The catalog's lookup,
  [`ImageSourceCatalog.block`](../../packages/base/src/cs_image_system/base/image_sources.py)
  (lines 357 to 369), hands that word to `ImageSource.block` (lines 101
  to 103), which reads `sources[word]` exactly. Every block is keyed by
  the bare word (`aws`), in the release's parts and in a tree's layer,
  so a qualified word finds nothing.
- The catalog already knows how to read a qualified word: the loader's
  `set_declared` (lines 290 to 304, called from
  [config_loader.py](../../packages/engine/src/cs_image_system/engine/config_loader.py)
  line 532) matches every declared word to an installed runtime through
  `_names_the_same` (lines 397 to 406). So what a family IS is already
  right for a qualified tree; only the block lookup is wrong.
- The refusal is
  [validate.py](../../packages/engine/src/cs_image_system/engine/commands/validate.py)
  `check_image_sources`, lines 652 to 657: an empty query is refused,
  naming the word as written.

**Reproduced** (read-only, a copied fixture in a temporary directory,
`uv run --no-sync python`):

| Tree | Bare | Every runtime qualified |
| --- | --- | --- |
| The shared fixture ([tests/fixtures/config](../../tests/fixtures/config): AWS family and docker family runtimes) | 0 refusals | 3 refusals (`basic-rh-10` and `my-deb-12` on `aws-runtime/aws`, `rh10-container` on `docker-runtime/docker`) |
| The same, the effective query of each of the 4 unpinned entries | the catalog's block under the declarations | all 4 differ; 3 are empty, and `basic-rhel-9` passes validation with a thinner query (its catalog `virtualization: hvm` lost), so its fingerprint and emission would move with no refusal |
| The core fixture ([packages/system/tests/fixture](../../packages/system/tests/fixture): the test kit's double runtime, no provider) | the run passes | 1 refusal (`base-10` on `testing/test-double`: the tree's own `test-double` block not found) |

The silent case matters as much as the refusals: an entry whose OS
builder declares part of its query validates under a qualified runtime
and bakes from a different query.

**Confirmed by experiment**: with only the lookup patched to read the
bare part of the word, a dry run of the shared fixture with every
runtime written qualified emits the bare fixture's emission, 117 files
of 117, identical. The runtime's written word reaches no other part of
a run's emission.

## R2. The defect's reach: every place a runtime's written word is compared

**Read**, by search of every `get_type()`, `type_`, raw `type` read and
runtime-type literal under `packages/*/src` and `src`:

| Place | What it does with the word | Verdict |
| --- | --- | --- |
| `ImageSourceCatalog.block`, `image_sources.py:357-369`, through `image_query()` | reads the block under the word as written | **the defect** (R3 to R5) |
| `set_declared`, `image_sources.py:290-304` | matches the word to an installed runtime (`_names_the_same`) | works for either form |
| The stand-in, `stand_in_types` and `stand_in_runtime_type`, `image_sources.py:219-249`; [mod_tests.py](../../packages/engine/src/cs_image_system/engine/mod_tests.py) lines 118 to 121 | names the stand-in by the class's `csis_name()`, never by a tree's word | works for either form of the tree's word. A latent fault beside it: two stand-in runtimes sharing one bare word collapse to one name, and `classes[runtime_type]` (mod_tests.py:121) then misses, because the registry lists them by their qualified words (R7) |
| Validation's messages, `validate.py:641-667` | names the runtime's type as written | already what FR-006 asks |
| The runtime facts, [network_facts.py](../../packages/base/src/cs_image_system/base/network_facts.py) lines 28 to 34 | keyed by the runtime's **name**, not its type | not reached: the two forms record the same facts (the spec's edge case holds) |
| `extra_for`, [extras.py](../../src/cs_image_system/extras.py) lines 101 to 107 | reads a qualified word by its name part | works for either form |
| `declared_classes`, [load_failures.py](../../packages/engine/src/cs_image_system/engine/commands/load_failures.py) lines 108 to 113 | which classes are asked to classify a load failure: matched by bare name | works with one class per bare word; with two (story 3) it asks one class more, never fewer. Left (R8) |
| The bootstrap interview's facts, [bootstrap/facts.py](../../packages/engine/src/cs_image_system/engine/bootstrap/facts.py) lines 197 (`runtimes_of_type`) and 245 (`first_runtime_name`) | compares the raw YAML `type` with the plugin section's own bare word | **the same defect**, in `cs-image-system bootstrap`: a runtime written `aws-runtime/aws` is not found by the AWS family's section, nor `docker-runtime/docker` by the docker family's (R8) |
| `describe_runtime`, [runtime_facts.py](../../packages/engine/src/cs_image_system/engine/commands/runtime_facts.py) line 105 | prints the word as written | a message: as written, as the spec asks |
| The goldens ([tests/fixtures/golden](../../tests/fixtures/golden), 117 files; [packages/system/tests/golden](../../packages/system/tests/golden), 32 files) | every fixture writes its runtimes bare | unmoved (FR-007) |

No OS builder compares a runtime's type: `get_osrtconfig_by_type`
([os_builder_model.py](../../packages/base/src/cs_image_system/base/models/os_builder_model.py)
line 167) compares the entry's `image_builder`, an instance name, which
the load already reads bare.

**Found beyond the runtime word** (by the same experiment, the other
builders' class words written qualified, the runtimes bare): the
spec's Input says every other qualified word "already works". It loads,
but it does not emit as the bare word does. 22 of 117 files move:

| Builder kind | Where the written word lands | Example |
| --- | --- | --- |
| State backend | each root's `backend "<type>"` label and `.tfbackend.hcl` comment ([collector.py](../../packages/hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py) lines 492, 505, 521, from each state plugin's `BackendRegistration(type=self.type_)`); `meta-state/state-locations.yaml` | `backend "tf-s3-state/s3"`, which OpenTofu does not accept |
| OS builder | the OS update comment in the Packer build ([builder_base_os.py](../../packages/base/src/cs_image_system/base/basic/builder_base_os.py) line 301) | `pin={}, default-os/rhel)` |
| Storage builder | `meta-state/storage.yaml`'s `plugin:` ([read_models.py](../../packages/engine/src/cs_image_system/engine/read_models.py) line 97) | `plugin: tf-ebs-instance/tf-aws-s3` |
| Instance builder, image builder | nothing | emit as bare |

This is not a runtime's word, so it is outside what this specification
says; it is the same promise broken, and it reaches FR-008 (R11): the
Google Cloud family's test of qualified words writes its storage and
state words qualified too.

**YOUR DECISION D1**: the class words of state backends, OS builders
and storage builders. **Default: a specification of its own**, written
next, and this one stays on the runtime word as the spec says. Its fix
touches every state plugin (the spec's assumption is that no provider
plugin changes) and reverses part of the recorded-word rule of
[base's README](../../packages/base/README.md#the-registry) ("nor a
qualified one to the bare word"), which is a design choice of its own.
The other way: amend this spec (`/speckit-clarify`) to cover every
builder's class word, and re-plan.

## R3. Where the word is resolved

**Chosen**: in the catalog, by the rule it already holds. `block`
resolves the word it is given to the one installed runtime class it
names (`_names_the_same` over `runtime_builder_classes()`, the rule
`set_declared` uses), and reads that runtime's blocks under the words
that name it (R4, R5). A word that names no installed runtime keeps
today's exact lookup: the load refuses such a word before any query is
formed, so only a direct caller (a test) reaches it.

**Alternatives considered**:

- *Resolve in the model* (`runtime_type()` answers the registry's
  listed word): a second place resolving words, and the catalog would
  still need the class to choose a part (R4).
- *Rewrite the word at load* (record `aws` where the tree wrote
  `aws-runtime/aws`): reverses the rule that what the tree wrote is
  recorded, and the messages would no longer name the operator's own
  word (FR-006).
- *Strip the word to its bare part in `block`*: mends stories 1 and 2
  and fails story 3: two runtimes sharing a bare word would read the
  merged release layer, where their two blocks collide and neither is
  used, or one plugin's block would serve the other's runtime (FR-003).

## R4. The release's layer: each runtime's own part

**Read**: the release layer a query reads today is the merge of every
declared runtime's part (`_release`, lines 306 to 317;
`merge_entries`, lines 151 to 201). The merge keys blocks by the bare
word, so two declared runtimes that share it collide: neither block is
used, and an ERROR line says so. Discovery already skips both plugins
when one ships a block for a runtime type the other registers
([loader.py](../../packages/engine/src/cs_image_system/engine/loader.py)
lines 453 to 466), so a block for a bare word in any declared part is
the part of a runtime that registers that word.

**Chosen**: a block is read from the part of the runtime the word
resolves to, under that runtime's bare word (`csis_name()`), and from
no other part. What a family IS (`is`, description, versions) is still
read from the merge of the declared parts, as today. The rule "an
undeclared runtime's blocks are not in the run's layer" is kept: a
resolved runtime that the tree does not declare contributes no block,
unless the reader is the stand-in (`beside_declared`).

The merge keeps its collision line for a block a part gives for another
runtime's type, and does not say it for two runtimes that share a bare
word and each own their block: the query reads those from their own
parts, so the line would be false.

**Why the goldens cannot move**: with one runtime class per bare word
(every fixture, every starter, the reference), the merged layer's
block for a word is that runtime's own part's block, because no other
declared part may carry it (the discovery rule above; held for this
repository's parts by `tests/test_image_sources.py`,
`test_each_runtime_ships_only_its_own_blocks`). The landing order
inside a part (generic, then the version's entry) is the same function.

**Alternatives considered**: *keep the merged layer* (fails story 3,
R3); *stop merging blocks at all* (the merged listing loses its
`sources`, and the five tests that prove the split catalog against the
one file it was, still true facts, would be rewritten for no
behaviour).

## R5. The tree's layer: which keys answer a runtime

**Read**: a tree's `cfg/image-sources*.yml` keys its blocks by
runtime type
([CONFIGURATION.md section 5a](../../docs/CONFIGURATION.md), `sources`
row), lowercased at load (`ImageSource.__post_init__`, lines 82 to 91).
Today only the exact word answers, and a key that names no runtime is
silently never read.

**Chosen**: for the runtime a word resolves to, the tree's entry
answers with

1. its block under the runtime's bare word, which applies to every
   runtime of that bare word, whichever form the tree wrote it in; then
2. its block under a qualified key `<namespace>/<word>` whose namespace
   is the runtime's own (the registry's `namespace_of_class`, and the
   listed word's namespace where the registry lists it qualified),
   landing on the bare key's block key by key.

So a bare key is the documented form and stays enough; a qualified key
is accepted and gives one plugin's runtime a block of its own, which is
the only way a tree can tell two runtimes of one bare word apart
(story 3). FR-004's first half, both directions of story 2.

**Alternatives considered**: *refuse a qualified key with a message*
(FR-004 allows it, and the spec's assumption names it as the plan's
choice): rejected, because the qualified form is the one that must
always work, and in story 3 a tree could then give the two runtimes no
separate blocks. *A qualified key replaces the bare one* rather than
landing on it: rejected, every other layer lands key by key.

## R6. A tree's key that no installed runtime registers

**Chosen**: `validate` names it, in one WARNING line per key, with the
family and the installed runtime words: `image sources: cfg/image-sources:
family 'debian': block 'awz' names no installed runtime type (installed:
aws, docker); it is never read`. A key names an installed runtime when
it is an installed runtime's bare word, or `<namespace>/<word>` for an
installed runtime of that namespace. It is a warning, not a refusal.

**Alternatives considered**: *a refusal*: rejected, because a tree may
carry a block for a runtime whose plugin is not installed where it is
read, and declares no runtime of that type there (the families install
as separate extras, and the Google Cloud and AWS families leave this
workspace); refusing would turn an absent, unused plugin into a broken
tree. The warning is FR-004's "named as such, not silently ignored".

## R7. The stand-in's name

**Chosen**: `stand_in_types` returns the words the registry lists the
stand-in runtimes by (the keys of `runtime_builder_classes()`), not
their `csis_name()`, and `stand_in_runtime_type` reads a named
stand-in (`--stand-in`) by the same rule as any word, so `docker` and
`docker-runtime/docker` both name the docker family's runtime. With
one class per bare word the listed word is the bare word, so every
message and test that names `docker` is unchanged. Two stand-ins of one
bare word are then two names, and `mod_tests.py:121` finds each.

**Alternatives considered**: *leave it* (the constitution lets a defect
wait until its code is touched; this code is touched by R3 and R4, and
the spec's edge case asks that the stand-in be reached the same way).

## R8. Two other readers of the word

**Chosen**:

- **The bootstrap interview** (R2): `runtimes_of_type` and
  `first_runtime_name` match a written runtime word that equals the
  section's word or whose name part does. Story 1 says every command
  behaves as the bare word does, and `bootstrap` is one. The interview
  reads raw YAML with no registry (the module docstring says why), so it
  cannot tell two plugins of one bare word apart; with such a pair each
  section sees both runtimes. That pair exists only in tests, and the
  interview only proposes answers. The two state-backend lookups beside
  them (lines 209 and 217) are a state backend's word, D1's.
- **`declared_classes`** (R2): left. It chooses which classes are asked
  to classify a load failure, reads a qualified word by its name as its
  docstring says, and asks one class more only in story 3's pair.

## R9. Messages and the refusal

**Read and chosen**: unchanged. Every message names the runtime's type
as written (`validate.py:643`), and the refusal of an entry with no
source at all stays (FR-006). After the fix it is said only when no
block answers the runtime in either layer, so it no longer names a
block as missing that exists.

## R10. The test vehicles, and how they survive spec 007

**Chosen**, each test placed so that it needs no AWS family:

| Test | Proves | Vehicle | After spec 007 |
| --- | --- | --- | --- |
| Catalog cases in [tests/test_image_sources.py](../../tests/test_image_sources.py), beside `test_where_two_plugins_share_a_runtime_word_the_qualified_word_reads_its_own_part` | R3 to R6: either form reads the same block; two runtimes of one bare word each read their own part; the tree's bare and qualified keys; the unknown key | stand-in parts over a stand-in registry (the file's `_part` and `_catalog`), no provider | unchanged: no provider in them |
| New `packages/system/tests/test_qualified_runtime_words.py` | story 3 through a load: two runtimes of one bare word from two namespaces, each entry's query its own plugin's; the bare word refused naming both qualified forms | two test-only runtime plugins built on the test kit's double runtime ([double.py](../../packages/system/src/cs_image_system/system/testing/double.py)), over the core fixture | unchanged: the test kit is this repository's |
| [packages/system/tests/test_core_golden.py](../../packages/system/tests/test_core_golden.py), one more case | stories 1 and 2 and FR-005 with no provider: the core fixture with its runtime written `testing/test-double` emits the core golden, file for file; the tree's own block is the one read | the core fixture and the test kit's double | unchanged. This is the vehicle spec 007's research R6 keeps here |
| [tests/test_a_qualified_tree_emits_what_the_bare_tree_emits.py](../../tests/test_a_qualified_tree_emits_what_the_bare_tree_emits.py), the rewrite extended to `runtime_builders[].type` | SC-001, SC-002, story 1 scenario 3: every runtime type the installed plugins register, written qualified, validates and emits the bare emission | the shared fixture: today the AWS family's and the docker family's runtimes | the rewrite qualifies whatever runtimes the fixture declares, so after spec 007 it covers the docker family alone, and the AWS family's repository carries its own proof |
| [tests/test_bootstrap.py](../../tests/test_bootstrap.py), one case | R8: a qualified runtime word is found by its section's word | raw facts, no provider | unchanged |

The Google Cloud family is not in this venv; its proof is FR-008's
(R11).

## R11. FR-008: the Google Cloud family's whole run

**Read**: the Google Cloud family's
[test_qualified_words.py](https://github.com/infrastructurebuilder/cs-image-system-google-cloud/blob/develop/tests/pipeline/test_qualified_words.py)
(in its own repository, read-only here) writes four words qualified
(`gcloud-runtime/gcloud`, `tf-gcp/tofu-gce`, `tf-gcp/tf-gcp-pd`,
`gcs-state/gcs`) and proves only the load, because of this defect
(spec 005, tasks T028).

**Chosen**: once this repository has released the fix, the Google Cloud family's
test gains a whole dry run: its fixture with the words qualified
validates, and emits its bare emission file for file. With D1's
default, that run writes the runtime word and the instance word
qualified (here neither moves the emission once the fix is in, by R1 and R2; the run itself is the proof there) and
keeps the storage and state words at the load, because those move the
emission until D1's specification lands (R2); the test says so in its
docstring, naming that specification. The Google Cloud family's next release notes
say the qualified runtime word now drives a whole run (FR-008's
second half).

## R12. Versions and the release

**Read**: the workspace and the engine are at 0.1.12, the kit
(`cs-image-system-base`) at 0.2.1, the contract at 0.5.0. The kit's
middle number rises only when its declared surface loses or alters a
member ([base's README](../../packages/base/README.md), its opening
paragraph); `image_sources` is not on the surface
([surface-baseline.txt](../../packages/base/surface-baseline.txt)
lists only the runtime bases' `image_source_entries`).

**Chosen**: the contract is untouched (no change, no bump). The kit
takes a PATCH, 0.2.1 to 0.2.2, its baseline unchanged. The workspace,
engine and system follow the release.

**YOUR DECISION D2**: the release that carries the fix. **Default:
0.1.13**, a final release of this repository, cut by the operator once
the branch is merged (`just release patch pypi` on `main`), then the
Google Cloud family's next release (0.2.1) with R11's test. FR-008
cannot be met without both, and the definition of done (its fifth
condition) then names them. The other way: carry the fix in the next
release spec 007 cuts, and FR-008 waits for it.

## R13. What the change makes false (Principle X)

**Read**, the statements to correct in the same work:

- [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) section 5a: the
  `sources` row (a block per runtime TYPE: add that a bare key answers
  either form, a qualified key one plugin's runtime, and that `validate`
  names a key no installed runtime registers); "The stack", step 1 ("the
  release catalog's block for the runtime's type": the block of the
  runtime the word names, from its own plugin's part); the paragraph
  that says the core merges the declared parts (still true of what a
  family IS, not of a block).
- [packages/base/README.md](../../packages/base/README.md), "Image
  sources": "A runtime type's block that two parts give differently is
  a collision: neither is used" (true only of a block for another's
  runtime), and the stand-in's "block keyed by the type of the one
  registered runtime".
- [image_sources.py](../../packages/base/src/cs_image_system/base/image_sources.py):
  the module docstring ("A block is looked up by (family, version,
  runtime type)"), `merge_entries`'s collision paragraph, `block`'s
  and `stand_in_types`'s docstrings.
- [os_builder_runtime_config.py](../../packages/base/src/cs_image_system/base/models/os_builder_runtime_config.py)
  `runtime_type()`'s docstring ("the image-source catalog's key for
  it").
- [bootstrap/facts.py](../../packages/engine/src/cs_image_system/engine/bootstrap/facts.py)
  `runtimes_of_type`'s docstring (`type: <type_word>` exactly).
- The record of spec 005 ([plan.md](../005-relocate-gcp-provider/plan.md)
  line 47, [tasks.md](../005-relocate-gcp-provider/tasks.md) T028): a
  note that spec 006 mends the defect, not a rewrite.
- [specs/README.md](../README.md), row 006: its state.
- The Google Cloud family's `test_qualified_words.py` docstring (R11),
  in its own repository.

The starters ([docs/examples](../../docs/examples)) keep empty tree
layers and bare words: nothing there becomes false.
