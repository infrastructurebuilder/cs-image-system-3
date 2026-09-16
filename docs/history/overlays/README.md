> **Frozen record.** This document is history, kept verbatim as it was when frozen; nothing in it describes the present. Current documentation starts at [README.md](../../README.md).

# Live-proof overlays (stages 10–15)

The exact `--overlay` inputs of the live proofs recorded in
[docs/LEDGER.md](../../LEDGER.md) — ledger 68 (`proof-*`, 2026-09-09: §10.14
detach + unmount, §11.6 archived with data, §11.3 failure policy),
§11.4/§11.6 (`scratch-*`), §12.5 (`preflight-short`), §13.5
(`aws-ephemeral-test2`) and stage 15 (`aws-scratch-*`, 2026-09-10: a
transient EBS volume archived and restored with its data). They name
instances and storages that no longer exist and are kept as evidence, not
as configuration: nothing reads them, and since stage 28 the live
configuration carries no overlays at all (see `docs/OPERATIONS.md`,
"Transient declarations"). Moved here from the fixture's `overlays/` on
2026-09-13.
