# Past reminders

Items closed or gone stale in [REMINDERS.md](../REMINDERS.md), moved here
as they stood, newest first, each under the heading it had there. Nothing
here is current.

## From "Monthly General Items" (moved 2026-11-22)

### The §30 shims: removed in §125

**Closed 2026-11-05; nothing to raise.** The core's re-export paths of the
contract's names (`base/constants.py`, `models/model_config.py`,
`helpers/field_helpers.py`, `helpers/field_kinds.py`, `lifecycle.py`, the
data part of `lifecycles.py`, `basic/asset.py`, `models/executable_adds.py`,
the PSI enums in `models/provider_specific_image.py` and the name and HCL
helpers in `utils.py`) were removed in stage 125, every internal import
rewritten to the contract path, as the commitment to the contract the
operator's condition of 2026-10-29 named; the contract took a version of
its own (0.1.0) in the same stage. The annotated tags `s30-1-before`,
`s30-1-after`, `s30-2-before` and `s30-2-after` bracket the move of the
bodies into the contract, each tag's message carrying its recipe, and
stage 30 changed code alone (the emission byte-identical; no YAML key,
record or cloud state moved). The weekly reminder that stood here is
retired.
