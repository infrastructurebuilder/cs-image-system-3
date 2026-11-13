# 134. Hygiene bundle XXVII

**Status: IN PROGRESS since "do 134", 2026-11-13 (the decisions are
under each item). The operator's rule for this run: anything found
that would need a new hygiene stage is asked first, fix it here or
not.**

The findings carried out of [§133](../docs/CHANGES.md#s133)
(hygiene bundle XXVI), found while its last batch ran; none is
blocking, each its own commit on the bundle's branch.

1. An OS builder's image-builder subconfig
   (`OSBuilderBaseImageBuilderSubconfig`, and the image's own
   subconfig in `models/image.py`) declares `type_` as a templated
   field whose replace template is `{{ identified_model.name }}`; no
   `identified_model` is in the subconfig's context, so the template is
   kept as written and five subconfigs end the load holding the raw
   text. The output does not move, so nothing reads it today. Find
   what the template was meant to name and render it, or drop the
   template (found by §133 item 30). The operator, 2026-11-13: the
   templates become `{{ this.identified_model.name }}` (a bare name
   is a context variable, and only dataclass fields are contributed to
   the context, not the parent property). That alone fails the load,
   and a trace found why, asked and folded in on the operator's "go":
   the five subconfigs are resolved once, in the resolver's first
   call, and never again, and during that call their parent reference
   is empty and then the registry's DEFAULT OS builder by bare name
   (`basic-rh-10`), wrong for three of the five; the parent reference
   is declared as a foreign key whose unset value the resolver fills
   with the default, and the OS builder repairs it only after
   resolution. So: a parent reference is never defaulted; each
   subconfig gets its real parent before the first resolution; the
   templates render each entry's own parent's name; a test pins both.
2. The CI runner image's sources (`ci/runner-image/Dockerfile` and
   `probe.sh`) carry eight narration tokens (a stage number and the
   dates its pins were read) that no area of the rule reads. A comment
   change in the Dockerfile changes the image's build context, so the
   cleanup goes with the next image change and its proof, not alone
   (found by §133 item 28). The operator, 2026-11-13: done now; the
   image is rebuilt locally and probed as the proof (the full-test
   leg), and publishing a new image tag for CI stays the operator's.
3. Several skeleton recipes' `just --list` lines show only the last
   line of a wrapped comment (`cloud-relabel`, `ci-login-proof`,
   `bootstrap`, `cloud-upgrade`), as the system's own recipes did
   before each got a `[doc]` attribute; the skeleton's get one too
   (found by §133 item 28).
4. The store of opened encryption markers (`encryption._OPENED` and
   `_OPENED_KEYS`) is shared by every run in a process and outlives
   each: safe today (one identity per process, and an extra plaintext
   only makes every reader hide more), but a long-lived process keeps
   every plaintext it ever opened. Making it per run means the
   resolver's `mark_plaintexts` and the YAML representer (registered
   globally, with no run) take the run's store (found by §133 item 21).
   The operator, 2026-11-13: the store stays shared (the safety
   machinery stays untouched); the reason is recorded where the store
   is defined.
5. `config_loader.py` passes `collect=decrypted_plaintexts()`, a fresh
   copy on every call, so the `collect` argument does nothing there
   (found by §133 item 21). It goes.
6. Groups and users are parented to the builder their `type` names.
   Item 1's fix showed the same flaw in four identity items of the
   fixture (the groups `pxgroup` and `readers`, the users
   `taylor_tango` and `unity_uniform`): their `type` names a builder
   other than the default, and nothing sets their parent reference to
   it, so it held the default builder's bare name (never resolvable)
   and now holds nothing. Each group and user is parented to its own
   builder before the first resolution, and a test pins it (found by
   item 1; the operator, 2026-11-13: fixed in this stage).
7. Three of the same kind, found by item 6 (the operator,
   2026-11-13: all fixed in this stage):
   a. default-typed groups and users are keyed in the resolver's map
      as `<classification>::None::<name>`, because the key is taken
      before their parent is set (the registry's own index is right):
      they are parented at item 6's early point too, so the key is
      right from the start;
   b. `Storage.type_` declares that it also sets `model_id`, but a
      storage holds no parent, so the resolver writes a stray plain
      attribute onto it, and the field's description says "For User
      items". Not harmless: a storage left at the default `type` (the
      fixture's `mnt_data`) then has an item id that names its builder
      while its keys in the map and the registry use the short form,
      so its own id finds nothing. The setter goes and the description
      says what the field is (the operator, 2026-11-13);
   c. the two image subconfig models declare on their parent field
      that it also sets `model_id`, the field itself. Not a no-op, as
      first written: the declaration is what gives an image entry's
      templates the name `builder` (the owning image). It stays, and
      the base README says so (the operator, 2026-11-13).
8. Three more of the same kind, found by item 7 (the operator,
   2026-11-13: all fixed in this stage):
   a. the parent setter (`ParentPropertyHolding.model_id`) swallows
      every registration error with a silent `except`, which hid the
      alias collision item 7(a) met: real errors surface;
   b. registering the same runtime builder model again raises a name
      collision in the runtime namespaces, the flaw item 7(a) fixed
      for aliases: the same instance under its own name is not a
      collision, a different one still is;
   c. an item's id (`NameTyped.global_id`) reads any attribute named
      `model_id` through `hasattr`, so a stray one changes the id (the
      root of 7(b)): the id reads a parent only from a model that holds
      its parent by reference.
9. Four more of the same kind, found by item 8 (the operator,
   2026-11-13: all fixed in this stage):
   a. a builder's id (`BuilderBase.global_id`) reads any attribute
      named `model_id`, the pattern 8(c) removed from items; builders
      hold no parent;
   b. OS builder entries are keyed in the resolver's map under their
      model's id, while their own id later moves to the builder's, so
      key and id disagree (five entries in the fixture; the registry
      still finds them);
   c. `TemplateResolver._enter_deferred_item` still wraps setting a
      deferred item's parent in a catch-all, so a registration
      collision there is a warning, not a failure;
   d. `register_built_instance` writes the name into the item's own
      namespace before the runtime-namespace check, so a colliding
      registration overwrites that entry and then raises.

**Acceptance**: each item its own commit; a golden move is shown to
the operator before it is regenerated; `just test` green at the end,
then `just full-test-legs` once (the operator, 2026-11-13); one squash, branch kept. Records: the
squash; this section goes at "merge 134".
