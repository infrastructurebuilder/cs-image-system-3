# 135. Registered instances carry a namespace

**Status: OPEN 2026-11-13, from [§134](../docs/CHANGES.md#s134) item 10(d).
A plan: waits for "do 135", before [§113](STAGE-113.md) (the
operator, 2026-11-14). Its decisions were asked 2026-11-14 and are
answered under each one; the cadence is the bar per batch and at the
end, then the full-test legs.**

[§131](../docs/CHANGES.md#s131) gave every registered CLASS a
namespace: the plugin it comes from, joined to its name as
`<namespace>/<name>` (`NAMESPACE_SEPARATOR` in
[registry.py](../packages/base/src/cs_image_system/base/registry.py)).
Registered INSTANCES have none. An instance is entered in its
classification's own namespace under its bare name, and in the
global-id index under its global id. For a top-level item the bare
name is unique; for a child item it is unique only within its parent,
so children of different parents overwrite each other.

**What §134 found.** It made registration refuse an id held by a
different instance in every place but this one (item 10(d)), and
stopped there, because real loads rely on the overwrite in two ways:

- **Child items keyed by bare name.** Every image of the frozen
  fixture has an image-builder entry named `pckr-ebs-ans`
  (`ImageImageBuilderSubconfig`), registered by that name, so nine
  entries take turns under one key; a base image's runtime entries
  (`BaseImageImageBuilderSubconfig`, `aws-east2-runtime`) and
  storage mappings (`efs-storage` in two instances, `gce_share` in an
  overlay) do the same. Nothing reads those classifications by name
  today, so each entry is last-writer-wins and
  `get_all_instances_by_classification` collapses them. Refusing the
  overwrite would fail the fixture's own load.
- **Provider-specific images replaced on purpose.** A runtime
  builder's `create_provider_specific_image_deferred` and
  `create_provider_specific_image_resolved` register a fresh image
  for the same `<source>::<runtime>`, replacing the old one under its
  name and its id; a test pins the replacement
  (`TestRegistryRoundTrip::test_reregistration_overwrites`).

**The design (the operator, 2026-11-13):** "an implicit namespace
acquired due to configuration ancestry level, with a plugin namespace
setting the most significant discriminator." So an instance's
registered name is qualified, most significant first, by the plugin
that serves it and then by its ancestry in the configuration (the
parent chain the parent references now hold correctly, §134 items 1
and 6 to 10), and finally its own name. A top-level item's ancestry
is empty; a child's is its parent's qualified name.

1. **The instance key.** Define the key of a registered instance as a
   typed tuple, the way §131 keys a class (`RegistrationKey`: a
   `NamedTuple` of classification, namespace and name, "never a joined
   string: the tables are read by the key's fields"): the
   classification, the serving plugin's namespace (§131's, from the
   class the instance is an instance of), the instance's ancestry and
   its name, each a field of its own. The registry's instance tables
   are keyed by it and every lookup reads its fields; nothing parses a
   string apart. The model is untouched: its `name` stays the name a
   tree wrote, and its `global_id` stays
   `<classification>::<model id>::<name>`, the `::` separator being the
   global id's alone. The joined form, `<namespace>/<ancestry>/<name>`
   with `NAMESPACE_SEPARATOR`, exists only at the edges: a message that
   names an ambiguity, and a tree's reference when it writes the
   qualified form (item 2); the load already refuses `/` in a name or
   an alias, so splitting a written form is never ambiguous.

   **The ancestry is the parent's global id.** A global id already
   carries the whole ancestry: its middle part is the parent's own
   global id, chained up to a top-level item, and §134 made that chain
   right at every moment of a load. So the ancestry field is the
   parent's global id (empty for a top-level item), not a second copy
   of the chain, and the only part of the key that is new is the
   plugin namespace. **YOUR DECISION:** the ancestry is the parent's
   global id (the default), a chain built from the parent references,
   or the configuration's file structure as written. **The operator,
   2026-11-14: the parent's global id.**
2. **Lookups by the names a tree writes.** A tree names a top-level
   instance by its bare name or an alias, and that keeps working: a
   bare name finds the instance whose ancestry is empty within the
   classification, as today; an ambiguous bare name (two plugins
   serving one classification under the same name) is a validation
   error naming both qualified forms, as §131 made it for classes.
   **YOUR DECISION:** whether a tree may also write the qualified form
   for an instance (the default: yes, as §131 allows for a `type:`
   word), or only the bare one. **The
   operator, 2026-11-14: yes.**
3. **Children are entered under their qualified key.** Image
   entries, base image entries, storage mappings and every other
   child item stop overwriting each other; a test holds that a load
   of the fixture and of every starter tree enters every child once
   under its own key, and that
   `get_all_instances_by_classification` returns them all.
4. **Replacement is explicit.** The provider-specific image is the
   one instance that is replaced on purpose. Its registration says so
   (a replacing registration that removes the old instance's name, id
   and aliases before entering the new one), and every other
   registration of a different instance under a held key is refused,
   by key and by global id, in `_check_registration` (§134 item 9's
   check before write). This is §134 item 10(d).
5. **A duplicate declared in the configuration is refused at
   registration.** A duplicate state backend in a tree is written over
   in the registry before its collision is reported elsewhere (seen
   in `tests/test_config_loading.py::
   test_a_registry_collision_is_named_without_the_models_repr`);
   with item 4 the registry itself refuses it, naming both
   declarations (found by §134 item 10).
6. **A leftover comment.** `TemplateResolver._enter_deferred_item`
   still opens with "6. CRITICAL:", a step number of older inline
   code; it says what the step does (found by §134 item 10).
7. **The documents.** packages/base/README.md (the registry's
   section and the parent-reference rows §134 wrote), docs/DESIGN.md
   where it describes names and namespaces, docs/PLUGINS.md if a
   plugin author needs to know how an instance is keyed.

**Out of scope**: any YAML key, record or emission; the class
namespaces of §131 (unchanged); the parent references themselves
(§134).

**Acceptance**: the golden is byte-identical (a key is the
registry's, never written out); a load of the fixture and of every
starter tree enters each instance once under its qualified key, with
no overwrite but the provider-specific image's explicit replacement;
every refusal case of item 4 has a test that leaves the registry as
it was; a bare name and an alias still find a top-level instance; the
bar and `just full-test-legs` are green. Records: the squash message;
this section goes at "merge 135".
