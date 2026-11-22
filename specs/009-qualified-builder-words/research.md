# Research: Every builder written by its qualified word works as its bare word does

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Each item is marked **read** (a fact taken from the code as it stands on
`develop` at `35446e3f`, release 0.1.12, the kit and the Terraform
libraries at 0.2.1), **decided** (only where the spec's Clarifications
record the operator deciding it), or **chosen** (this plan's choice,
with the alternatives weighed). The operator's open decisions are named
**YOUR DECISION**, each with its default, and gathered in
[plan.md](plan.md#decisions-in-this-plan).

This specification is the sibling of
[spec 006](../006-qualified-runtime-type/plan.md), whose research R2
found its defect. It reuses that research's method (a copied fixture,
rewritten, dry-run and compared file for file) and its vocabulary
(written word, bare word, namespace, listed word:
[006's data model](../006-qualified-runtime-type/data-model.md)).

## R1. Where a builder's written class word lands today

**Read**, and **reproduced** read-only: the shared fixture
([tests/fixtures/config](../../tests/fixtures/config)) copied to a
temporary directory, every builder entry's own `type:` under
`state_backends`, `os_builders`, `storage_builders`,
`instance_builders`, `image_builders`, `group_builders`,
`user_builders` and `mod_builders` rewritten to the qualified form of
the key that registers it (`tf-s3-state/s3`, `local-state/local`,
`default-os/rhel`, `tf-ebs-instance/tf-aws-s3`, `packer/packer-ebs`,
`okta-opa/okta-tf-ro`, `posix-identity/posix`, `bash-mod/bash-remote`
and so on: 23 entries), runtimes left bare; then a dry run of every
lifecycle through the shared harness (`tests/harness.py`,
`uv run --no-sync python`), compared with the bare copy's run.

The qualified tree loads, validates and runs. 23 of its 117 emitted
files differ from the bare tree's (spec 006 counted 22 with fewer kinds
rewritten; the user builders add `meta-state/identity.yaml`):

| Builder kind | Files | Where the written word lands | Example |
| --- | --- | --- | --- |
| State backend | 18 files: the `.tf` and `.tfbackend.hcl` of nine roots; and `meta-state/state-locations.yaml` | the backend label, [collector.py](../../packages/hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py) line 492; the backend file's comment, line 505; the record's `type`, line 521; a consumer's `terraform_remote_state` `backend`, line 598. Each reads `BackendRegistration.type`, which every state plugin fills with its model's `type_` ([tf_s3_state_models.py](../../packages/tf-s3-state-plugin/src/cs_image_system/tf_s3_state_plugin/tf_s3_state_models.py) lines 222 to 225, [local_state_models.py](../../packages/local-state-plugin/src/cs_image_system/local_state_plugin/local_state_models.py) lines 109 to 110, the contract example's [models.py](../../packages/contract-example-plugin/src/cs_image_system/contract_example_plugin/models.py) lines 135 to 137, and the Google Cloud family's `gcs_state_models.py` lines 102 to 103 in its own repository) | `backend "tf-s3-state/s3" {`, `backend = "local-state/local"` |
| OS builder | 2 Packer build files | the OS update comment, [builder_base_os.py](../../packages/base/src/cs_image_system/base/basic/builder_base_os.py) lines 299 to 301, through `get_type()` ([builder_base.py](../../packages/base/src/cs_image_system/base/basic/builder_base.py) lines 53 to 54) | `pin={}, default-os/rhel)` |
| Storage builder | `meta-state/storage.yaml` | `plugin:`, [read_models.py](../../packages/engine/src/cs_image_system/engine/read_models.py) line 97 | `plugin: tf-ebs-instance/tf-aws-s3` |
| User builder | `meta-state/identity.yaml` | `user_builders:`, [read_models.py](../../packages/engine/src/cs_image_system/engine/read_models.py) line 69 | `posix-users: posix-identity/posix` |
| Instance, image, group and modification builders | none | nothing they emit or record names their class word | identical |

**Confirmed with OpenTofu** (v1.12.6, on your local machine, in a
scratch directory): a root holding `backend "local-state/local" {}`
passes `tofu init -backend=false` and `tofu validate`, and a full
`tofu init` refuses it with `Error: Unsupported backend type`. So a
check that the roots initialise must run a full `init` with the
backend; `-backend=false` and `validate` cannot see this defect.

## R2. What the registry and the converter do with the word

**Read**:

- Resolution is one rule,
  [`_resolve`](../../packages/base/src/cs_image_system/base/registry.py)
  (lines 208 to 227): a qualified word reads its key directly; a bare
  word resolves when exactly one class answers to it, and raises
  `AmbiguousTypeError` naming every qualified form when different
  classes do.
- Every class is keyed by its own `csis_name()` and nothing else
  ([registry.py](../../packages/base/src/cs_image_system/base/registry.py)
  line 464 for the models, line 706 for the services). The service
  group's name in a plugin's metadata is not a key. So a class has no
  alias word the registry resolves: the word a tree writes is the
  class's `csis_name`, bare or qualified.
- `models_under(vct)` ([`_names_under`](../../packages/base/src/cs_image_system/base/registry.py),
  lines 230 to 246) lists every class by the shortest word that
  resolves to it: the bare word while one class answers to it, the
  qualified word for each key where different classes do.
- The converter's dispatch,
  [`PydanticConverter._dispatch`](../../packages/engine/src/cs_image_system/engine/orchestrator.py)
  (lines 982 to 999), resolves the entry's `type`, then rewrites it to
  the class's `csis_name` but keeps a written namespace, by the rule
  its comment states (lines 990 to 994) and
  [base's README](../../packages/base/README.md#the-registry) states
  (lines 345 to 351): "never rewrites a bare word to its qualified
  form ... nor a qualified one to the bare word". The model's `type_`
  is therefore the word as written, and every reader after the load
  (R1's table) reads it. The branch that rewrites an alias to the
  `csis_name` (line 996) is never taken, by the point above.
- Every builder kind is structured through `_dispatch` (observed by
  instrumenting a load of the shared fixture: runtime, state backend,
  OS, storage, instance, image, group, user and modification builder
  models, 23 entries); items (images, storages, groups, users,
  modifications) are not, and their `type` names a builder instance,
  which the load already reads bare (`Registry.word_for`, lines 679 to
  693, spec 131).
- An OS builder that leaves `type` out takes the one type that serves
  its family, from `models_under`
  ([config_loader.py](../../packages/engine/src/cs_image_system/engine/config_loader.py)
  lines 727 to 733): the listed word already.

## R3. Story 3 is broken today beyond the written word

**Read**: after the model is built, the loader finds its builder class
by the model class's bare name,
[config_loader.py](../../packages/engine/src/cs_image_system/engine/config_loader.py)
lines 992 to 994:
`reg.get_builder_for_model(model_type.csis_name(), classification)`.

**Reproduced** read-only: a test-only twin of the local state plugin (a
different model class and builder class, both registering `local`,
installed beside the real one as an extra entry point with the
derived namespace `twin`, the way the test kit's
[neighbours.py](../../packages/system/src/cs_image_system/system/testing/neighbours.py)
installs its broken neighbour), over the shared fixture with
`local-dev` rewritten:

| `local-dev` written | Today |
| --- | --- |
| `local` | refused at load: `type 'local' is ambiguous under state_backend_model: 2 plugins register it; write one of local-state/local, twin/local` (story 3 scenario 2 already holds) |
| `local-state/local` | the model loads, then the builder lookup raises `type 'local' is ambiguous under state_backend` |
| `twin/local` | the same |

So two plugins that register one bare word cannot be used at all, in
either qualified form. The lookup reads a word where it holds the class.

## R4. Fingerprints and lineage

**Read**: the input fingerprint
([lineage.py](../../packages/base/src/cs_image_system/base/lineage.py),
`input_fingerprint`, lines 150 to 188) hashes each modification's
record (`mod_records`, lines 106 to 147), whose `type` is the
modification item's `type`: the name of a mod builder instance
(`bash-remote`, `ansible-default`), never a builder class word, and
read bare at the load. The base image's inputs are read from the OS
builder model's fields, not its `type`. In R1's reproduction no
`csis_fingerprint` in the emission moved: the only lines that changed in
the Packer files are the OS update comments.

So FR-005 and SC-003 hold today for every builder class word, and the
change keeps them: with one class per bare word the word recorded is
the bare word (R6).

## R5. What the records hold

**Decided** (spec Clarifications, 2026-11-21): every record a run keeps
holds the same word whatever form the tree wrote, the class's
registered word; the written word stays in the configuration files.

## R6. What "the class's registered word" is

**Chosen**: the word the registry lists the class by under its
classification (`models_under`): the class's `csis_name` while it is
the one class that answers to it (every fixture, every starter, the
reference configuration, and so every golden), and
`<namespace>/<csis_name>` where different classes share it (story 3),
the namespace being the class's own (`namespace_of_class`, the first in
sort order when several plugins carry the one class). It is the class
word's counterpart of `Registry.word_for`, which already reads an
instance word as the word the registry lists the instance by.

Experiment: with the converter patched in-process to this rule (no
repository file changed), the shared fixture with all 23 builder words
qualified emits the bare emission, 117 files of 117, and the bare
emission equals [tests/fixtures/golden](../../tests/fixtures/golden),
117 of 117.

**Alternatives considered**:

- *Always the bare `csis_name`*: meets the spec for one class per word,
  and in story 3 both twins would record `local`. Rejected: every later
  lookup of a model's word meets the bare word's ambiguity (the
  deferred item class,
  [orchestrator.py](../../packages/engine/src/cs_image_system/engine/orchestrator.py)
  lines 479 to 482; any plugin that resolves its own `type_`), and the
  records could not say which plugin's class a storage or a backend is.
- *Always the qualified word*: every golden and every live record would
  move (`plugin: tf-docker/tf-docker-volume`, `type: local-state/local`)
  for no user's benefit (Principle IV).

**The cost of the choice**: once a second installed plugin registers
the same bare word, a tree that wrote the first plugin's word qualified
records `local-state/local` where it recorded `local` before, and the
two comments of R1 say so. Nothing an external tool reads moves (R9),
no fingerprint moves (R4), and the state-location guard compares the
location (`local://state/...`, rendered by the kind), not the record's
`type` ([meta_state.py](../../packages/engine/src/cs_image_system/engine/meta_state.py)
lines 554 to 562). That situation is the one where spec 131 already
makes the neighbour's install change the tree (the bare word is refused).

## R7. Where the word is read: at the edge, once

**Chosen**: in the converter's dispatch. `_dispatch` resolves the
written word as today, then sets the entry's `type` to the class's
registered word (R6) before the model is built. Every reader after the
load, in the core and in every plugin, reads the registered word:
`BackendRegistration(type=self.type_)` in each state plugin, the OS
builder's comment, the storage and identity read models. This is the
rule spec 131 gave instance words ("the load reads it as the bare word
once, at the edge"), applied to class words.

**Alternatives considered**:

- *Mend each reader* (the collector, the OS builder base, the two read
  models): four places in the core today, and every plugin that copies
  its model's `type_` into output keeps leaking until it changes (each
  state plugin here, the Google Cloud family's `gcs` backend): fails
  FR-006 and SC-004.
- *Keep the written word on the model and add the registered word
  beside it*: two facts for one thing, and every reader must be taught
  which to read (Principle VIII).
- *Strip the namespace in each state plugin*: changes every provider
  plugin (FR-006).

## R8. The builder class is found by the model's own key

**Chosen**: the loader finds a model's builder class by the model
class's own registration key, `<namespace_of_class(model class)>/<csis_name>`,
read directly by `get_builder_for_model`
([config_loader.py](../../packages/engine/src/cs_image_system/engine/config_loader.py)
lines 992 to 994). It is never ambiguous, and for one class per word it
finds the class the bare word finds today.

Experiment: with R7 and R8 patched in-process, both of R3's qualified
trees load and run, each with its own plugin's builder
(`LocalStateBuilder`, the twin's builder).

**Alternative considered**: the model's registered word under the
builder classification. Rejected: the two classifications list their
words separately, so a word unique among models may be shared among
builders; the key is exact.

## R9. The external tool's word: the backend's kind

**Read**: a backend's kind already names its type
(`BackendKindProtocol.type`,
[state.py](../../packages/contract/src/cs_image_system/contract/state.py)
lines 67 to 80): `S3_KIND.type` is `s3`, `LOCAL_KIND.type` is `local`,
the contract example's is `inmem`, the Google Cloud family's is `gcs`,
and the kind renders the location from it (`s3://bucket/key`). The
collector reads the registration's `type` for the label instead.

With R6 the registration's `type` is the bare word for one class per
word, so the label is right without this item. Where two plugins share
the word it is qualified (`twin/local`), and the experiment shows the
root then carries `backend "twin/local"`, which OpenTofu refuses (R1).

**Chosen**: the collector writes the backend label (line 492) and a
consumer's remote-state `backend` (line 598) from the registration's
kind's `type`; a registration whose kind declares no `type` keeps
today's label, its own `type`. The backend file's comment (line 505)
and the record (line 521) keep the registration's `type`, the
registered word, which FR-007 asks of a record. Experiment: with this
patched in-process, both twins' roots carry `backend "local"`, and
their state-location records say `type: local-state/local` and
`type: twin/local`.

**Alternatives considered**:

- *Strip the namespace in the collector*: the Terraform library depends
  on the contract alone (its
  [pyproject.toml](../../packages/hashicorp-utils/pyproject.toml)), and
  would have to repeat the kit's separator rule (Principle VIII).
- *A new contract field for the tool's word*: a contract change and a
  bump for a fact the contract already carries.

## R10. The runtime's word

**Read**: spec 006 resolves a runtime's word inside the image-source
catalog and keeps the runtime's written word on the model, because its
FR-006 requires the refusal of a runtime with no image source to "name
the runtime's type as the configuration wrote it". Its R1 found that,
once the catalog is mended, a runtime's word reaches nothing else a run
emits or records.

**Found by experiment**: with R7's rule applied to the runtime
classification too, the shared fixture with every builder word
qualified, runtimes included, emits 117 files of 117 identical to the
bare tree's on today's code, without 006's catalog change: the catalog
is then asked for `aws` and `docker`. 006's own-part lookup and its
tree keys (its stories 3 and FR-004) are still needed for two runtimes
of one bare word and for a qualified key in a tree's image sources.

**YOUR DECISION D1**: does the edge rule cover the runtime word?
**Default: no; the runtime classification keeps its written word, as
spec 006 plans.** Why: 006's FR-006 names the written word in a
message, and reading the runtime word at the edge would make that
message name the registered word; the spec scopes this work to "every
other builder kind", and 006 makes the runtime word emit and record
identically (FR-004's runtime clause) on its own. The rule then has one
exception, written in base's README with its reason. The other way:
say "read runtimes at the edge too" to make the rule have no exception;
006's FR-006 is then amended to "names the runtime's type by a word that
names it", and 006's catalog change is still made for its story 3.

## R11. The bootstrap interview's state-backend lookups

**Read**: `default_state_backend` and `other_state_backends`
([bootstrap/facts.py](../../packages/engine/src/cs_image_system/engine/bootstrap/facts.py)
lines 207 to 217) compare the raw YAML `type` with a plugin section's
own bare word exactly, so a state backend written `tf-s3-state/s3` is
not found by the AWS family's section
([aws_runtime/bootstrap.py](../../packages/aws-runtime-plugin/src/cs_image_system/aws_runtime/bootstrap.py)
lines 163, 212 and 474). 006's R8 names these two as this work's.

**Chosen**: both match a written word that equals the section's word
or whose name part does, by the matcher spec 006 adds for
`runtimes_of_type`. The interview reads raw YAML with no registry, so
with story 3's pair each section sees both backends; the pair exists
only in tests, and the interview only proposes answers (006 R8).

## R12. The spec's edge cases

**Read**:

- *An alias of a class*: none exists to resolve (R2); a word resolves
  only as the class's `csis_name`, so the edge case holds by the same
  rule.
- *An implicit qualification* (a plugin's own declarations resolved
  within the loading plugin): no such resolution exists at `35446e3f`;
  every word goes through `_resolve`. Whatever form resolves, R7 records
  the registered word.
- *A namespace no plugin has*: refused at load by `UnknownTypeError`
  before `_dispatch` rewrites anything, naming the extra through the
  umbrella's table (`extra_for`,
  [extras.py](../../src/cs_image_system/extras.py) lines 101 to 107,
  which reads the name part). Unchanged.
- *A tree that mixes forms*: R7 is applied entry by entry, so a mixed
  tree is the bare tree after the load.
- *The external tools' words*: the backend label from the kind (R9);
  a Packer source type is the image builder plugin's own constant and
  R1 found the image builder's class word in no emitted line.

## R13. Messages

**Chosen**: a refusal at load (ambiguous, unknown) names the word as
written, as today, because it is raised before the rewrite. A message
after the load names the builder's type by its registered word, which
names the same class when written in the tree (`os_builder_model.py`
line 121, the preflight's `_type_word`, `validate`'s lines). No
requirement of this spec names the written word in a message; under
D1's default the runtime's messages are unchanged (006's FR-006).

## R14. The test vehicles, and how they survive specs 007 and 008

**Chosen**, each placed so it needs neither the AWS family nor the
Okta plugin:

| Test | Proves | Vehicle | After 007 and 008 |
| --- | --- | --- | --- |
| [tests/test_a_qualified_tree_emits_what_the_bare_tree_emits.py](../../tests/test_a_qualified_tree_emits_what_the_bare_tree_emits.py), the rewrite extended to every builder entry's own `type` | SC-001, stories 1 and 2: every builder kind's word (runtimes once 006 lands, or by D1's other answer) qualified emits the bare emission file for file | the shared fixture | the rewrite qualifies whatever builders the fixture then declares (the docker family, the local state backend, the OS, Packer, Ansible, bash and posix plugins) |
| [packages/system/tests/test_core_golden.py](../../packages/system/tests/test_core_golden.py), one more case | stories 1 and 2 with no provider: the core fixture with its OS, image, group, modification and state words qualified emits the core golden (the OS update comment and `meta-state/identity.yaml` among its files) | the core fixture and the test kit's double | unchanged |
| new `tests/test_qualified_builder_words.py` | R6 and R7 at the converter, per builder kind; story 3 through a whole run: a test-only twin of the local state plugin beside the real one, each qualified word emitting its own plugin's backend with the label `local`, each record naming its registered word, the bare word refused naming both, in both discovery orders (SC-005); a full `tofu init` of a root made of the emitted backend block and backend file (SC-002) | the shared fixture's `local-dev` roots (the docker family's), the local state plugin, the twin | unchanged: local state and the docker family stay in this repository |
| [tests/test_terraform_collector.py](../../tests/test_terraform_collector.py), one case | R9: the label and a consumer's `backend` are the kind's type when the registration's `type` is qualified | a registration by hand | unchanged |
| [tests/test_bootstrap.py](../../tests/test_bootstrap.py), one case | R11 | raw facts, no provider | unchanged |

The `tofu init` case is guarded as the suite's other real-OpenTofu
test is (`shutil.which("tofu")`), and runs offline: a `local` backend
and no provider. The S3 backend's qualified word is proven here by
byte identity while the AWS family is in this repository, and by the
AWS family's own repository after spec 007.

## R15. Versions and the release

**Read**: the kit and the Terraform libraries are 0.2.1, the contract
0.5.0, the workspace and engine 0.1.12. A version line's middle number
rises only when its declared surface loses or alters a member
([.bumpversion-terraform.toml](../../.bumpversion-terraform.toml), its
header); `TerraformCollector`'s methods keep their signatures.

**Chosen**: the change is in the engine (R7, R8, R11) and the Terraform
library (R9). The kit's code does not change (its README does, R16), so
the kit's version does not move; the contract is untouched. The
Terraform line takes a PATCH, `just sdk-bump terraform last` (0.2.1 to
0.2.2), with `just surface-check` green. The engine rides the release.

**YOUR DECISION D2**: the release that carries this. **Default: the one
final release the operator decided for specs 002, 003 and 006** (006's
D2), when this specification is merged before it is cut; otherwise the
next release after the merge. Why: this work's whole-tree proof waits on
006 (D1's default), and in one release the Google Cloud family's next
release (0.2.1) can carry a whole qualified run of all four of its words
(`gcloud-runtime/gcloud`, `tf-gcp/tofu-gce`, `tf-gcp/tf-gcp-pd`,
`gcs-state/gcs`) instead of 006's R11 keeping the storage and state
words at the load. The other way: say "a release of its own" to cut one
after 006's.

## R16. What the change makes false (Principle X)

**Read**, to correct in the same work:

- [packages/base/README.md](../../packages/base/README.md), "The
  registry", the Resolution paragraph (lines 345 to 351): the
  recorded-word rule, narrowed to "what a run emits and records holds
  the class's registered word" (FR-009), with D1's exception.
- [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) section 1.2
  (lines 88 to 109): "A plugin may register a model under several
  names; the canonical name is recorded" (false already: R2) and "What
  the entry wrote is what is recorded: a bare word stays bare, a
  qualified word keeps its namespace".
- [packages/engine/README.md](../../packages/engine/README.md) lines
  180 to 185: "An alias is canonicalized to the class's `csis_name()`
  first", in the paragraph that also still names
  `Registry().get_model` (no process registry exists).
- [packages/hashicorp-utils/README.md](../../packages/hashicorp-utils/README.md):
  `BackendRegistration`'s `type` "(for example `s3`)" (lines 127 to
  131: the registered word) and the remote-state `backend` "set to the
  producer's backend **type**" (lines 221 to 226: its kind's).
- [docs/WRITING_A_PROVIDER.md](../../docs/WRITING_A_PROVIDER.md), "The
  namespace" (lines 57 to 64): add that a model's `type_` holds the
  registered word whatever the tree wrote, and that a state backend's
  label is its kind's `type`.
- The code comments: `_dispatch`'s (orchestrator.py lines 990 to 994),
  and the collector's docstrings of `generate_terraform_block` and
  `generate_remote_state_datasources`.
- Spec 006's records: its research R2 and plan D1 say this fix
  "touches every state plugin"; it touches none (a note, not a
  rewrite). Its plan's Complexity Tracking row (the Google Cloud
  family's whole run keeping storage and state words at the load) ends
  when this lands.
- [specs/README.md](../README.md), row 009: its state.
- In the Google Cloud family's repository: `test_qualified_words.py`
  writes all four words qualified in its whole run, and its docstring
  and release notes say so.

The starters ([docs/examples](../../docs/examples)) and the reference
configuration write every builder word bare (searched): nothing there
becomes false.
