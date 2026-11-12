# 134. Hygiene bundle XXVII

**Status: OPEN 2026-11-12. The open bundle; takes items as they are
found. Waits for "do 134".**

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
   template (found by §133 item 30).
2. The CI runner image's sources (`ci/runner-image/Dockerfile` and
   `probe.sh`) carry eight narration tokens (a stage number and the
   dates its pins were read) that no area of the rule reads. A comment
   change in the Dockerfile changes the image's build context, so the
   cleanup goes with the next image change and its proof, not alone
   (found by §133 item 28).
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
5. `config_loader.py` passes `collect=decrypted_plaintexts()`, a fresh
   copy on every call, so the `collect` argument does nothing there
   (found by §133 item 21).

**Acceptance**: each item its own commit; `just test` green after
each batch and at the end; one squash, branch kept. Records: the
squash; this section goes at "merge 134".
