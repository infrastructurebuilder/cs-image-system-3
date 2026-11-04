# 123. hashicorp-utils stops reaching back

**Status: OPEN 2026-11-04. Waits for "do 123", after [§120](STAGE-120.md).**

The library depends on `base` (eleven import statements) and `base`
imports the library back lazily at four sites with "always installed
here" comments (`global_context.register_declared_backends`,
`validate.py`, two in `run_lifecycles.py`), so DESIGN §3P's "the
library is optional to the core" is not true today (REEXAMINE1 §3.3;
REEXAMINE3 §3.1 flaw 2). `collector.py` and `roots.py` import
`GlobalTypeContext`. `TerraformCollector` is a process singleton the
okta plugin writes and the three root plugins read back by name, a bus
nothing documents or resets per plugin.

1. The four lazy back-imports go: registering declared backends is a
   state-backend hook; the collector is reached through the context
   ([§125](STAGE-125.md)'s services) or passed; `validate` and the runner ask the
   plugins, not the library.
2. `GlobalTypeContext` in `collector.py` and `roots.py` becomes a
   Protocol: a minimal local one now, replaced by the contract's in
   [§125](STAGE-125.md).
3. The collector bus is documented in hashicorp-utils README as the
   one shared registry of terraform workspaces, and its reset per run
   is tested. **YOUR DECISION:** it stays a singleton behind the
   context (the default) or becomes a per-run instance passed at
   bind.
4. The direction test (`test_v2_contract.py`) extends to the DAG:
   contract ← base ← hashicorp-utils ← plugins; base never imports
   hashicorp-utils. **YOUR DECISION:** the stronger form, the library
   a leaf on the contract alone (REEXAMINE1 §5.7 step C), waits for
   the builder base classes to leave `base`, and is not this stage
   (the default).
5. The [§120](STAGE-120.md) tofu root base now sits in a library the kit does not
   import, which [§120](STAGE-120.md) assumed.

**Out of scope**: the HCL builder's API; the engine split ([§124](STAGE-124.md)).

**Acceptance**: emission byte-identical; the direction test green;
`just test`; one squash, branch kept. Records: the squash; this
section goes at "merge 123".
