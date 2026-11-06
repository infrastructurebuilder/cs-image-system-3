# 131. Registrations carry their plugin's namespace

**Status: OPEN 2026-11-04; RE-EVALUATED 2026-11-05 after §125. Waits
for "do 131". Any time now; the contract is versioned (0.1.0), so the
field this stage adds to `PluginMetadata` is a MINOR bump of the
contract to 0.2.0 (0.x: additive, said in its README's Version
section) and the dependents' range `>=0.1,<0.2` moves with it.**

**Re-evaluated 2026-11-05.** Three facts moved under the plan. The
registry is one instance per run since §124 (`ctx.reg`, made by the
loader; `current_registry()` the shim for context-less code), so the
typed key of item 2 keys the per-run registry and the replay of the
plugins' registrations into it (`load_plugins(reg)`), not a
singleton; the sentence "the registry stays a singleton here" below
is superseded. The `hasattr` dispatch item 2 left to §125 is gone
(registry 5 -> 0), and §125 checks every discovered plugin's classes
against their kind's protocol at discovery (`_discovered_plugins`,
once per process): the namespace is derived there, beside the
conformance check, and a plugin without one is refused in the same
message. Item 5's alternative changes: the tofu version checker
(`tofu_roots.tofu_instance_builder.TofuVersionChecker`) is still
registered by the three root plugins, but tofu-roots is a plugin now
(a hooks entry point, §123) while hashicorp-utils is a leaf library
by decision; so the alternative is "tofu-roots registers it once
under its own namespace", which makes no library a plugin. The
decisions of items 1 and 3 are unchanged.

The registry keys every table by the classification and the plugin's
`csis_name` alone: `models[classifier][name]`,
`registry[name][classifier]`, `classified_aliases[classifier]`,
`defaults_registry[classifier]`. Two installed plugins that chose one
word under one classification are a `Type Collision` at load and
nothing runs; the author of a plugin outside this repository cannot
know which words are taken (`tofu`, `aws`, `s3`, `local`, `docker`,
`packer`, `posix` are all spent), and the registration order is the
sorted entry-point name, so where no check exists (`register_service`
writes `registry[name][classifier]` without one) the alphabetically
later plugin wins silently. §120 met the first real
case: the tofu version checker, one class carried by three root
plugins, and taught the registry that the same class twice is one
registration; a fork of a root plugin that keeps the checker's name
still collides. A `type: tofu` in a tree says which word, never
whose.

1. A namespace per plugin. The loader derives it from the entry
   point's distribution (`plugin.dist.name`) with the
   `cs-image-system-` prefix and the `-plugin` suffix dropped:
   `aws-runtime`, `tf-ebs-instance`, `okta-opa`, `contract-example`;
   the core's own registrations (`base`'s generic checker and storage
   mapping) take `base`. `PluginMetadata` gains an optional
   `namespace` field that overrides the derivation; a plugin with no
   distribution (a test's in-process metadata) must name one.
   **YOUR DECISION:** the derivation from the distribution name (the
   default), the entry point's name (`aws_plugin`, `gcloud`,
   `dummy_hooks`: today's are inconsistent), or the field alone,
   mandatory.
2. The key. Every registry table is keyed by one typed key
   (classification, namespace, name), a named tuple, not a joined
   string; `register_plugin_metadata` and `register_service` take the
   namespace from the loader; the collision is the same
   classification, namespace and name with a different class, and
   the same class under several namespaces is one registration
   (the §120 rule, generalised); `register_service`
   refuses what it used to overwrite. The loader's second
   registration of a cloud or container service as a runtime carries
   the namespace with it.
3. Resolution. A bare `type:` word resolves when exactly one class
   answers to it under the classification, whatever the namespaces
   that carry it (three roots, one checker: not ambiguous); when
   different classes answer, `validate` refuses the word and prints
   every qualified form. The qualified form is
   `<namespace>/<name>` (`tf-ebs-instance/tofu`) and resolves
   directly; `default` keeps its meaning. **YOUR DECISION:** `/`
   (the default), `:` or `.` as the separator; none occurs in a name
   today. An alias resolves the same way (CONFIGURATION's "register a
   model under several names").
4. What is recorded. A model's `type_` keeps the bare word when the
   tree wrote one: the mod fingerprint hashes `get_type()`
   (`lineage.py`), so the qualified form written back would move
   every fingerprint and the golden. A tree that writes the qualified
   form keeps it; the registry answers either. The load log says, per
   namespace, what registered; the `--version` line is unchanged.
5. Version checkers resolve through the same path (`validate.py`
   looks the executable's name up, then its type). The one checker
   three roots carry stays three registrations of one class.
   **YOUR DECISION:** that (the default), or hashicorp-utils gains an
   entry point and registers it once under its own namespace, which
   makes the library a plugin (§123 decides what the
   library is; the default leaves that to it).
6. Tests. Two synthetic plugins register `tofu` under one
   classification in two namespaces: the load succeeds, the bare word
   is refused with both qualified forms in the message, each
   qualified form resolves to its class, `register_service` refuses
   the second class; the same class under three namespaces is one
   registration and its bare word resolves (replaces
   §120's identity test); a plugin without a
   distribution and without the field is refused at load with the
   field named.
7. Documents: the contract README (`PluginMetadata`'s field; the
   collision rule and its failure line), the base README (the
   registry's tables and the `Type Collision` entry), CONFIGURATION
   (the qualified form beside the canonical name and aliases),
   PLUGINS.md (a plugin names its namespace, or inherits it), the
   GLOSSARY (namespace), the starters' `# DECISION` comment on the
   checker unchanged.

**Against the reviews**: REEXAMINE1 §3.3 counts string-keyed dispatch
(`PLUGIN_TYPEMAP`) and the registry's `hasattr` checks as a second
type system; this stage keys the tables by a typed tuple and adds no
string dispatch, and leaves the `hasattr` dispatch to
§125 item 4 (landed: the registry has none). The registry is
per-run since §124; the typed key applies to it and to the shim
alike.
The namespace is derived from packaging, not from a provider word
(§121). Nothing worsens; no question before
solidifying.

**Out of scope**: the names a tree gives its builders and their
aliases (the `instances` tables; collisions there are the operator's
own and are right to refuse); the entry-point groups
([§130](STAGE-130.md) item 8); the singleton (§124).

**Acceptance**: emission byte-identical (the golden; the reference's
`config-drift`); the tests of item 6; §120's
isolation test still green; `just test`; one squash, branch kept.
Records: the squash; this section goes at "merge 131".
