> **Frozen record.** This document is history, kept verbatim as it was when frozen; nothing in it describes the present. Current documentation starts at [README.md](../../README.md).

# Plans

Running log of implementation plans for this repo. Newest first.

---

## §15–§18 stages (2026-09-10)

*Status: **§15 and §16 DONE 2026-09-10 (ledger 72, 73); §17–§18 planned,
not started by the operator's instruction of 2026-09-10** — written to
[TODO.md](TODO.md) from the
target goals ([GOALS.md](GOALS.md), [EXPLORE.md](EXPLORE.md) "Systemic
Purpose") against what has landed; no new GCP work by the operator's
decision. In the operator's order (2026-09-10): §15 storage lifecycle
parity on AWS — `archived` for EBS, data lifecycles for S3/EFS (N19's
state machine is realized only on GCP pd; §3H's deferred data
lifecycles); §16 the Justfile's full contract — `build`, `full-test`,
`release`; §17 end to end in CI (GOALS.md's CI/CD goal; today's CI runs
lint/typecheck/test only); §18 the first real model image, released and
in use (the systemic purpose — every mechanism it needs exists, nothing
has been delivered to a scientist). The configuration-repository stage
drafted alongside these was deferred by the operator the same day and is
kept verbatim below ("Configuration repository separation") so it can be
picked up. §15 started and landed 2026-09-10 (feature/aws-storage-archive;
its worksheet entry is in the archive below).*

Considered and not chosen now: container and Azure images (breadth,
deferred with the clouds); multi-group image ownership (Q4, the
stakeholder's later revision); identity-attribute writes (Q7, waits on
the stakeholder) and `manual-add` identity types (N20); plugin developer
tooling from EXPLORE (scaffolding, `from_pairs`, dead code, ruff
rules — hygiene; the stale packer fixtures go with the deferred
configuration-repository stage); CloudFormation and LDAP/AD (§3H); and
every GCP item (the §12 candidates a/b/d, Okta on GCE, egress) by
decision.

## Stage 29 — Protocols become base classes (drafted 2026-09-13, SUPERSEDED)

*Status: **superseded by [TODO.md §30](TODO.md) on 2026-09-13**, the
same day it was drafted; nothing below was done. The operator's stated
goal — a plugin author writes against one package and never inherits a
base class — is the opposite direction: the protocols are the contract
and the base classes implement them. §30 carries §29's still-valid
residue (the dead `StateManagementRootProtocol`, the two accidental
structural implementers, the nine `_model_id` copies, the anonymous
TypeVar on `RuntimeBuilderBase`, the four protocol-caused type-escape
hatches). Kept verbatim for the measurement it records.*

### 29. Protocols become base classes (as drafted)

**Why**: the code carries eight `typing.Protocol` definitions (the
`base/protocols/` package: `NameTypedProtocol`, `BuilderModelProtocol`,
`PluginArtifactProtocol`, `PluginMetadataProtocol`,
`SelfInjectedNameProtocol`, `ParentPropertyHoldingProtocol`,
`SubItemOverrideProtocol`, `StateManagementRootProtocol`) and uses none of
them structurally except in two load-bearing places (measured
2026-09-13): `ProviderSpecificImage` reproduces the `NameTypedProtocol`
surface on purpose without inheriting it (`models/provider_specific_image.py`,
with a test asserting the `isinstance`), and every `BuilderBase` passes
`Registry.register_built_instance`'s runtime check by duck typing
(`builder_base.py` says so: `global_id` is load-bearing for that gate).
Both must be given the nominal base explicitly, or the registry quietly
empties. Everything else lists the protocol as a base.
What they do instead costs twice. `BuilderModelProtocol` restates six
methods `BuilderModel` defines, so every interface change lands in two
places (§26 removed `get_parameters` from both); `NameTypedProtocol` has
one implementer, `NameTyped`; all twelve plugin-metadata classes inherit
`AbstractPluginMetadata` AND `PluginMetadataProtocol`, so the loader's
check against the protocol is satisfied by the abstract base alone, and
more strictly. The three markers the orchestrator dispatches on with
`isinstance` (self-injected name, parent-holding, sub-item overrides)
are nominal tags, which an empty mixin expresses directly; as
`runtime_checkable` protocols the check is looser (any object with a
same-named method passes, whatever its signature) and slower. Pure duck
typing is not the alternative: the orchestrator genuinely dispatches on
class identity for the markers and the loader genuinely rejects a plugin
that fails the check, so a nominal type must exist — abstract base
classes and mixins give a signature check at definition time and one
place per interface.

1. **Fold each duplicate into its base.** `BuilderModelProtocol` →
   `BuilderModel` (abstract where the protocol declared a method the base
   does not implement); `NameTypedProtocol` → `NameTyped`;
   `PluginMetadataProtocol` → `AbstractPluginMetadata`;
   `PluginArtifactProtocol` → a small mixin/ABC (`PluginArtifact`), since
   both cloud builders and models claim it; `StateManagementRootProtocol`
   is dead — zero implementers, one annotation — and is deleted.
2. **Markers become empty mixins**: `SelfInjectedName` and
   `SubItemOverride` plain empty classes (under `extra="forbid"` any field
   a base adds is a schema change on ~100 models, so markers carry
   nothing); `ParentPropertyHolding` a pydantic-dataclass mixin carrying
   `_model_id` (`init=False`) ONCE — today the protocol cannot hold a
   field, and the declaration is copied verbatim at nine sites. The
   orchestrator's `isinstance` checks keep dispatching, now exact.
   Also give `BuilderBase` and `ProviderSpecificImage` the nominal
   `NameTyped` surface they duck-type today, and fix
   `RuntimeBuilderBase`'s anonymous inline TypeVar (it was never generic).
3. **Repoint the ~100 annotation sites** outside `base/protocols/` (a
   rename pass, mechanical) and the one test that names a protocol; delete
   the `protocols` package and every `runtime_checkable` import.
4. **Plugins loaded by entry point** (`loader.py`): the check becomes
   `isinstance(md, AbstractPluginMetadata)`. Note `cs_image_system.base`
   exports nothing today (`__init__.py` is empty): a plugin imports each
   base from its module, as it imports each protocol now. The single
   contract module every plugin imports from is a separate, larger stage
   (measured 2026-09-13: ~40 symbols in two tiers — pydantic-dataclass
   model bases and plain-ABC builder/metadata bases — plus a declared
   interface for the ~55-member run context that plugins reach through
   the `GlobalTypeContext` singleton at ~50 sites; the context is the
   part that makes an external plugin real, and the expensive part).
5. Behaviour-neutral by construction: golden byte-identical, bar green,
   pyright at 0 errors. Records: ledger; DESIGN's plugin-contract paragraph
   names the base classes. Feature branch `feature/protocols-to-bases`,
   squash-merged, kept.

## Configuration repository separation (drafted 2026-09-10, SUPERSEDED)

*Status: **superseded by [TODO.md §28](TODO.md) on 2026-09-13.** Deferred
by the operator on 2026-09-10 and kept verbatim below; nothing below was
done. §28 takes the same goal by a different route decided 2026-09-13:
no submodule and no `git subtree split` (the config repo
`cs-image-system-testconfig` already exists with its own history), the
`tfmodules/` stay in this repo (the sibling's `module_source_base`
already reaches them, so step 2's "vendor tfmodules" is struck), the
live configuration carries no overlays, and `test_folder/` is removed
rather than relocated.*

### The configuration becomes its own repository; the suite gets its own fixture

**Why**: GOALS.md's configuration goal is "an independent git repo that
holds the entire configuration … the system reads it from the repository
and updates it by pulling". The 2026-08-25 ruling made the relocation
"operational, not a feature", and gate 3 proved relocation readiness in
tests — but it never happened: `test_folder/` is still both the live
sandbox configuration and the suite's fixture (DESCRIPTION.md's first
honest observation). The cost showed every day this week: each live
config change (`family_version`, the dask playbook, `release:`, instance
comments) churned the golden and the gate-1 baseline; the harness installs
fixture subjects over tree entries; `test`/`test2` are commented out of the
live tree because the suite needs them; one e2e test asserted over the live
meta-state. Separating them is the last structural residue of
DESIGN §3B, and it de-risks the model-image stage, which changes the live config a lot.

1. **A frozen fixture tree** under `tests/fixtures/config/` (copied from
   today's `test_folder`, then owned by the tests: its own instances —
   test, test2, gce-test — its own meta-state seeds, no live pins).
   `copy_config`, the golden and the V1 baseline read it; nothing under
   `tests/` reads the live tree any more. The stale hand-written
   `test_folder/packer-ebs-ansible/` fixtures (pre-generator,
   DESCRIPTION.md) go.
2. **USER — the configuration repository**: name and location (e.g.
   `cs-image-config`); visibility — the standing constraint says the
   config repo is public by design (no secrets ever; membership data is
   public by that ruling); and the `tfmodules` coupling (the §3B residue):
   vendor `tfmodules/` into the config repo, or reference them by git
   source with a pinned ref (`module_source_base` already resolves
   relative to the config root).
3. **The move**: `test_folder/` becomes the root of that repository, its
   history carried by `git subtree split` so the meta-state commits keep
   their lineage; this repo's `--root-dir` default and the Justfile
   (`gce_cli`, `cloud-*`) take `CSIS_CONFIG_ROOT` (a sibling checkout by
   default); `run --commit` commits into the config repo and pushes
   nothing (the operator pushes).
4. **Docs**: OPERATIONS "the config tree" and CI shape; DESCRIPTION's
   observation retired; a README in the config repo (what the tree is,
   the credential contract, how `just` from this repo drives it).
5. **Tests**: the suite green with the live tree absent (CI has none); a
   relocation test that runs a dry `run --all` from a temp checkout of the
   config repo's shape.
6. **Live proof (no GCP)**: from the relocated checkout, `state query
   --strict` clean, a dry `run --all`, and the AWS ephemeral proof
   (`aws-ephemeral-test2.yaml`: launch, verify over SSM, teardown), its
   meta-state committed into the config repo.
7. Feature branch `feature/config-repo` here plus the new repository;
   squash-merged, kept.

## §12–§14 stages (2026-09-09)

*Status: **§12, §13 and §14 DONE 2026-09-09/10** (feature/run-scoping,
feature/aws-el10, feature/post-bake-tests; ledger 69–71; archived in
[PLAN.md worksheet archive stage 12–6.14](docs/DESIGN.md)); nothing queued — written to [TODO.md](TODO.md) as
stages §12 (run scoping safe by construction: `--apply-runtime` implies
the bake filter, out-of-scope bakes refuse, session lifetime in the
preflight), §13 (the AWS EL10 migration plus the first live AWS
disposal and ephemeral proof) and §14 (post-bake image tests recorded
per build and required by `release`, with a release-versus-retention
rule to decide). Operator rulings the same day: terraform state stays
in the AWS S3 backend by design even for machines created elsewhere,
so a GCS backend / per-runtime networking validation are the very last
priorities; a runtime session identity other than the operator's key
is deferred.*

## §12 candidates (2026-09-09)

*Status: **triaged 2026-09-09** — (c) and (e) became stage 12; (a) and
(b) are the very last priorities by the operator's ruling (state stays
in AWS by design); (d) is deferred. Raised by the §11 live proofs
(ledger 65–68). The landed worksheet for stages 1–11 is archived in
[PLAN.md worksheet archive](PLAN.md).*

**§12 candidates raised by 11**: (a) a GCS state backend for the GCE
roots so GCE work does not depend on an AWS session; (b) networking
validation scoped to the runtimes a command touches (today every
runtime model validates against its cloud at configuration load, so
`empty --runtime gcloud-east1` needs AWS credentials); (c) a credential
lifetime check in `cloud-preflight` (warn when the AWS SSO session
expires within the expected run length); (d) a session identity that is
not the operator's login key — the GCE session hook is a non-interactive
`gcloud compute ssh` as the operator, so it depends on an agent-loaded
or passphrase-less key (ledger 68; OS Login with the runner service
account is the candidate); (e) `--apply-runtime <rt>` implying
`--only-runtime <rt>` unless `--only` is given — today it scopes the
applies only, and an ad-hoc run without the bake filter baked two AWS
AMIs (ledger 68).

Still open from earlier lists, unchanged in priority:

- **Okta/ASA on GCE** (§11 item 7, lowest priority by the §7 decision):
  OPA enrollment on GCE, the identity read-model, sftd on Alma 10 —
  nothing done since removes what it needs.
- **Egress discipline** ([GCP-READINESS.md](docs/history/GCP-READINESS.md)): bakes
  download only; unmeasured. Informational, no code.
- ~~**AWS EL10 migration**~~ — DONE 2026-09-10 as stage 13 (AlmaLinux 10
  on both clouds, ledger 70).

## §11 candidates (2026-09-08)

*Status: **DONE 2026-09-08** — items 1–6 built, tested and proven live
on feature/section-11 (item 7, Okta on GCE, excluded by the operator);
ledger 65–68 hold the live proofs (68: §11.6 with data, §11.3, §10.14
detach on 2026-09-09) and the findings on the way (recipe option order,
the AWS session dependency of GCE work, GCE relabelling, the teardown
policy's stale record, the operator key); §12 candidates in the section above.*

Seven items in the order I would take them: AWS parity for
`dispose_image` / `verify_instance` (so AWS images are disposed through
the recorded path and AWS instances can be ephemeral); the one-time AWS
re-bake the §9 fingerprint change implies (accept, or re-stamp
fingerprints); the configurable ephemeral failure policy (`on_failure`,
`keep` default; DESIGN §3H); transient storages destroyed by the closing
phase itself; configuration-driven cycle recipes (`runtime describe`,
`empty --runtime`) so `just cloud-cycle <runtime>` is generic; the two
informational readiness leftovers (a live `archived` transition would
tick one); Okta/ASA on GCE at the lowest priority.

## Convergent bakes (stage 9) and declared ephemerality (stage 10) (2026-09-07)

*Status: **§9 and §10 COMPLETE 2026-09-08** (feature/convergent-bakes,
feature/declared-ephemerality). §10 live proof: one `run --all` regenerated
the declared storages, baked, launched/verified/tore down the declared
ephemeral instance and disposed every GCE image; ledger 61–64. The
operator's storage semantics (§10.11–15) are the model now.*

The operator's observation after §8: the change cycle had become a
procedure (`just gce-cycle` with overlays, `--only`, a manual pin move)
rather than "declare, then one lifecycle run makes it so". The root
cause is one gap: bakes are not convergent — nothing consumes the
recorded `input_fingerprint` to skip a current image, so every run
re-bakes, the child's pin lags its parent, and superseded images
accumulate. **§9 (convergent bakes)** adds the bake decision at the
`get_images` choke point (no build / fingerprint changed / parent moved
under a declared `parent_policy: follow` / update-policy age / forced by
`--only`), journals the bake plan, and keeps N17 for `pinned`. **§10
(declared ephemerality and retention)** turns rule 58 into
configuration: `ephemeral: true` instances (launch → runtime
verification hook → whitelisted destroy in one run), `retention:
{keep: N}` per series driving `dispose image`, and `ephemeral: true`
on a runtime (closing phase: storages destroyed, images disposed, gated
and scoped like everything else). After both, `run --all` is the whole
GCE cycle and a second run on a converged tree is a no-op; the `gce-*`
cleanup recipes stay by operator decision. Full steps, tests, live
proofs and the ⚠️ USER decisions are in [TODO.md §9–§10](TODO.md).

## GCE change cycle (2026-09-07)

*Status: **COMPLETE 2026-09-07** — code on feature/gce-cycle; the first
live `just gce-cycle` ran bake → launch → verify → teardown → empty and
ended with GCE holding nothing csis created (ledger 55–58; two fixes
found live on the way, three transient upstream failures retried).
Operator decision: no GCE resource is kept between cycles.*

The operator pays for GCP personally: a change that touches the gcloud
side is proven and then leaves nothing behind. `just gce-cycle` chains
sanctioned commands only. Three pieces had to exist first: transient
declarations (`--overlay`, so the cycle's instance and the teardown
requests never touch the live YAML, and the generated `apply-check`
re-reads the same overlay), an explicit empty bake surface (`--only
none`), and a sanctioned image disposal (`dispose image`: cloud delete
+ lineage record + image pins, one committed operation, with the
refusals that keep a blind delete impossible). Verification is the
serial console plus the strict state query, not an operator session.

## Per-root apply scoping (2026-09-06)

*Status: **COMPLETE 2026-09-06** — code on feature/per-root-apply-scoping;
stage 7 records it and the deprioritizations decided alongside (Okta on
GCE lowest priority, nothing removed that it needs; AWS EL10 deferred).*

One rule, `apply_flag_allows(value, root, aliases)` in
[utils.py](packages/base/src/cs_image_system/base/utils.py): a bool is
the whole lifecycle, a list names the roots (builder name or runtime)
allowed to apply. Generation asks it per root when it decides whether to
emit the apply; the emitted `apply-check` carries `--root`/`--root-alias`
so the execution-time re-check reads the list identically; and the four
after-apply hooks (`record_storage_transitions`, `mark_launched`,
`forget_decommissioned`, the instance builder's `post_finalize_phase`)
ask it per storage/instance root so a root that only planned records
nothing — a decommissioned instance is forgotten only when the root of
the runtime it was baked on applied (the decommission whitelist's rule,
via `roots_on_runtime`). Tests: the rule table, the emitted scripts
under list-valued flags (only the listed roots apply, every root still
plans and gates), `apply-check` refusing an unlisted root, and both hook
families under a list. Docs:
[OPERATIONS.md](docs/OPERATIONS.md) "Applies are opt-in".

## GCE gaps 49–51 (+54) (2026-09-05)

*Status: **COMPLETE 2026-09-06** — code on feature/gce-gaps-49-51
(squash-merged as 4337d3e), live proof on feature/gce-gaps-proof
(squash-merged): 10 GB bakes through IAP, the 200 GB pair disposed, one
gated launch of gce-test with the pd mounted and the pin bound from the
booted image, gated teardown, state query "no drift". Ledger 49–51 and
54 carry the evidence. Disk size settled at the vendor image's 10 GB
floor (the user asked for 5; a boot disk cannot be smaller than its
source image).*

stage 6, cheapest-first as planned: **51** — the GCE runtime declares
`default_disk_size` (40 GB) and the googlecompute source emits it
runtime-first, so every image (and therefore every instance boot disk)
stops inheriting the OS builder's 200 GB default. **50** — the
startup script was always emitted; the real cause was the pd attached
as device_name `gce_data` while the launch params mounted
`/dev/disk/by-id/google-gce-data`, so the script died at the missing
device — one sanitization now serves both sides. **49** — a runtime
hook reads the image an instance actually booted (GCE: boot disk →
`source_image`); after a real apply a deferred-parent instance binds
from it, and the state query flags a pinned instance whose booted image
differs as `changed`.

Found on the way, **54**: packer reached build VMs over their external
IP on tcp:22, which only ever worked because the default VPC's
`default-allow-ssh` rule existed; the moment that rule was deleted
(§4.5 hygiene) every bake timed out "waiting for SSH" — the serial
console showed the VM up and sshd listening. IAP runtimes now bake
through the IAP tunnel (`use_iap = true`), keeping the ephemeral
external IP for package egress only. Operator prerequisite (the system
generates no IAM changes): `roles/iap.tunnelResourceAccessor` for the
runner service account packer impersonates.

Proof plan once the grant exists: re-bake base + dask at 40 GB through
IAP → dispose the superseded pair (authorization pending) → one gated
launch of gce-test (transient declaration) with an IAP session showing
`/mnt/gce-data` mounted on its own device and the pin bound from the
booted image → gated teardown → finish the branch.

## Post-launch housekeeping (2026-09-05)

*Status: **COMPLETE 2026-09-05** (feature/post-launch-housekeeping,
squash-merged). The deferred GCE gaps (ledger 49–51) are queued as the
next stage in [TODO.md §6](TODO.md).*

Five operator decisions, executed in order: (1) gaps 49–51 deferred to
be the next stage; (2) `test`/`test2` commented out of the live
`instances.yaml` — a dormant declaration relaunches two t3.medium
instances the next time `apply_instances` flips — with the test suite
re-declaring them in its own config copies
(`tests/fixtures/aws_test_instances.yaml`, prepended by `copy_config`
so positional tests keep working); (3) `default-allow-ssh` and
`default-allow-rdp` deleted from csis-sandbox's default network (IAP's
`allow-iap-ssh` is the only SSH path the design needs); (4) budget
alerts and reminders — see below; (5) the identity run: the five live
`tcmet` attachments (added out-of-band in the ASA console) imported
into tofu state (`oktapam_user_group_attachment` import id is
`group|username`, e.g. `tcmet_user|parker`), plan "No changes", then
the gated run under a TEMP `apply_identity: true` — the key now exists
in `_config.yml`, off — zero OPA writes, meta-state commit 713ca39,
state query "no drift".

**Budget alerts — how to know they are read.** GCP records that an
alert was *sent*, never that it was *read*, so the check is on the
receiving side: in Billing → Budgets & alerts → the csis-sandbox
budget, confirm the recipients (by default "billing admins and users"
— make sure that resolves to a real, monitored mailbox, or add an
explicit Cloud Monitoring email channel and use its "Send test
notification" to prove delivery end to end); give that mailbox a filter
that labels `CloudPlatform-noreply@google.com` mail (the real budget-alert
sender, proven 2026-09-06; not `billing-alerts@google.com`) and never archives it
unread; and keep the thresholds (50/90/100 % of the budget) so a real
overrun produces three distinct mails, not one. The evidence of "read"
is a human acting on it, hence the reminders below.

**Apple Reminders set (each with an alert time):**

- *Weekly, e.g. Monday 09:00* — "csis billing review": Billing →
  Reports filtered by the `csis_*` labels; every non-zero line must map
  to a known, intended resource (stage 4.6 / readiness §10).
- *Monthly, 1st* — "csis budget-alert recipients": open the budget,
  confirm the recipient list and that the last test/threshold mail
  arrived in the monitored inbox.
- *Once, ≈ 2026-11-26 (trial credit day ~85)* — "GCP trial credit
  review": **withdrawn 2026-09-06** — the Credits page is empty, there is
  no trial or any other credit on the account, so every charge is real
  from day one. Replaced by a one-off "prove budget mail delivery"
  reminder; see [BILLING_REMINDERS.md §2a and §3](BILLING_REMINDERS.md).
- *After every bake day* — "csis orphan sweep": `state query` must show
  no `foreign` images/disks; `gcloud compute images list` and
  `disks list` should match the recorded chain.
- *Whenever a GCE instance is launched* — "csis instance running":
  the boot disk bills ≈ $8/month until torn down (finding 51).

## GCE teardown through the gate (2026-09-05)

*Status: **COMPLETE 2026-09-05** (feature/gce-test-teardown,
squash-merged; ledger findings 52–53). gce-test destroyed via the
sanctioned decommission with the operator's authorization; zero
instances remain in csis-sandbox.*

stage 4.2. The decommission is "undeclare, then run `instance-image`
with `apply_instances: true`": recorded-but-undeclared instances are
whitelisted at the gate and the apply destroys them. Two gaps surfaced
the moment the LAST instance on a runtime was undeclared and were
fixed first: the runtime's root vanished with its last declaration, so
no plan could carry the destroy (52 — the root is now emitted whenever
a recorded instance is undeclared, whitelist scoped per runtime via the
pinned build's lineage), and the N19 forget ran at generation, so the
dry runs erased the record before any destroy (53 — now an after-apply
hook behind the flag, the finding-21 shape). The declarations were
restored afterwards, dormant with the flag off — the stage-1 shape,
which keeps the shared fixture and its tests intact. Follow-up
(feature/image-disposals, same day, operator-authorized): the
superseded pre-fix dask image `...111543` disposed with its lineage
record (finding-46 shape, state query "no drift"); the finding-36 AWS
AMIs and snapshots verified already gone — the sweep list is empty.

## GCE first launch + IAP proof (2026-09-05)

*Status: **COMPLETE 2026-09-05** (feature/gce-launch-proof,
squash-merged). Instance launched through the gate; findings 47–48
fixed, tested, re-baked; **IAP session proven end to end by the
operator** (`gcloud compute ssh --tunnel-through-iap` into the running
gce-test — the free-tier 1 GB e2-micro kept the guest agent alive).
gce-test was torn down through the gate later the same day (see "GCE
teardown through the gate" above).*

Correction to the first read of the IAP failure: the two automated
SSH probes ran non-interactively against a passphrase-protected
`~/.ssh/google_compute_engine`, so the client never offered the key —
"Permission denied (publickey)" from the harness proved nothing
server-side. The serial console's finding-47 error was real (the
agent's INITIAL metadata-ssh-key setup aborted), but the agent's later
metadata-change path provisioned the operator's key anyway; the
finding-47 finalize step therefore stands as first-boot hardening, and
no instance replace was needed for the proof.

stage 3. Three tasks were requested: dispose the two superseded Alma
intermediates (**done**, drift-verified), reconcile the `tcmet` group
into the identity read-model (**done** — the full "no drift" report is
back; members read read-only from the OPA user API at
`{org}.pam.okta.com`), and launch+prove the GCE `gce-test` instance.

The launch itself succeeded through the full gate chain (e2-micro, no
external IP). The IAP session then failed, root-caused from the running
VM's serial console to **finding 47** (the guest agent aborts ssh-key
provisioning when it cannot cleanly remove the bake user from
`google-sudoers`). Fixing it required re-baking, which surfaced
**finding 48** (packer's ansible provisioner connecting as the
operator's local login). Both are fixed with per-runtime hooks
(GCE-only; AWS bakes untouched) and tested; a new dask image
`imgfile-basic-dask-pckr-gce-ans-20260905-045403` carries both fixes.

**Left open (finding 49, logged):** the running gce-test boots the
pre-fix image `...111543` while its pin silently moved to `...045403`
during the re-bake run — the module's `ignore_changes` on the boot
image means instances move only by a deliberate `-replace`, and the
pin move recorded no pending replacement, so `upgrade instance` is a
no-op; `state query` does not compare booted image to pin, so it
reports clean. Harmless for the proof; worth fixing before instances
are expected to track image upgrades. The in-instance evidence added
two more (ledger 50–51): the `gce_data` pd is attached but not mounted
(GCE has no equivalent of the AWS user-data mount realization), and the
boot disk inherits the image's 200 GB — ≈ $8/month of pd-standard while
gce-test exists, so the "≈ $0 launch" assumption was wrong. §4
(evidence captured here and in the ledger; teardown; orphan sweep)
awaits the operator's teardown authorization.

## Alma 10 on GCE: basic-rh-10 (2026-09-04)

*Status: **COMPLETE 2026-09-04** (feature/gce-alma-10, squash-merged;
findings 42–46 in the [docs/LEDGER.md](docs/LEDGER.md) ledger).*

User decisions: AlmaLinux 10 replaces RHEL on the GCE chain (no
license premium — the e2-micro launch becomes genuinely free-tier);
the lineage series renamed `basic-rhel-8` → `basic-rh-10` ("Red
Hat-family, EL10", distro-agnostic so Alma/Rocky/RHEL source swaps
keep the name); cross-chain version parity deliberately ignored (the
AWS rhel-8 line migrates forward later); the two RHEL GCE images
destroyed (authorized).

Live results, all through the gated meta-workflow: base
`basic-rh-10-gcloud-east1-20260904-105520` (family `basic-rh-10`,
Alma 10 vendor source, baked as the unified `packer` ssh user) and
`imgfile-basic-dask-pckr-gce-ans-20260904-111543` (parent pinned via
explicit `upgrade image ... --runtime gcloud-east1`, twice — the
standing parent pin wins over "parent built this run" by design). The
frozen V1 baseline is untouched: the rename and the finding-42 guard
are declared normalizers in gate 1. RHEL images deleted + lineage
records removed in one commit; dual-cloud `state query` shows **zero
image drift** before and after (the only drift is the out-of-band
`tcmet` identity-group membership change, pre-existing). Superseded
intermediates `basic-rh-10-...-103257` and
`imgfile-basic-dask-...-110544` remain recorded and live (~$0.58/mo)
pending disposal authorization. `just verify` green throughout
(412 passed).

## GCP readiness (planned 2026-09-02)

*Status: planned, not started.*

Checklist for taking the merged GCP support (increments 1–3) to a real
Google Cloud target at near-zero cost — free-tier region/machine
choices, budget guardrails, credential contract, placeholder
replacement, dry-run proof, and a stage-1-style gated first live run.
The full action list lives in [GCP-READINESS.md](docs/history/GCP-READINESS.md)
(kept as its own file at the stakeholder's request; this entry is the
plan-log pointer). Sequencing note: it depends on the `scoped-runs` and
`truthful-recorders` stages below landing first.

## Zero-drift report (planned 2026-09-02)

*Status: DONE 2026-09-02 (feature/zero-drift-report, squash-merged); the one-time live repair of ami-0f6307532eb04338b runs after merge.*

*Step-3 follow-up finding: an image whose parent is baked in the SAME
run gets generation-time tags `csis_parent=series:<name>` and a
fingerprint computed against the unresolved parent; the post-bake
lineage record resolves both, so `state query` reports a permanent
benign `changed` line (live: ami-0f6307532eb04338b). A report with a
"known benign" line trains people to skim past drift — the goal is a
report that is empty because reality is right, not because the check
looks away.*

1. Runtime-builder hook: `retag_image(image_id, tags) -> bool` on the
   runtime builder base (default: log-and-False, e.g. GCP until label
   updates are implemented); the AWS runtime builder implements it with
   `ec2.create_tags` (tag writes on our own AMIs only).
2. Post-bake reconciliation at the one place both truths meet:
   after `record_build(...)` in
   [packer_ebs_builder.py](packages/packer-plugin/src/cs_image_system/packer_plugin/packer_ebs_builder.py)
   compare the returned record's `parent` / `input_fingerprint[:16]`
   with the generation-time `lineage_tags` values and, when they
   differ, `rtb.retag_image(ami, {csis_parent, csis_fingerprint})`.
   Runs only where record_build runs — a real bake's manifest
   processing — so dry runs and tests never tag.
3. Tests: journal/monkeypatch `retag_image` — a same-run-chained image
   (cloudflow-from-dask in the fixture) triggers exactly one retag with
   the RESOLVED values; an image with a pre-resolved parent triggers
   none. Existing state-query tests already cover the tag-vs-lineage
   comparison itself.
4. One-time live repair (operator or gated command):
   `aws ec2 create-tags --resources ami-0f6307532eb04338b --tags
   Key=csis_parent,Value=ami-073d81cd9b3eec54b
   Key=csis_fingerprint,Value=<lineage prefix16>` — then `state query`
   reads truly empty (the GCP placeholder's `unavailable` line is a
   config decision, out of scope).
5. `just verify` green; docs/LEDGER.md ledger note on the step-3 follow-up
   finding; OPERATIONS state-query section gains one line: the
   report is expected EMPTY — any line is actionable.

## Truthful recorders (planned 2026-09-02)

*Status: DONE 2026-09-02 (feature/truthful-recorders, squash-merged).*

*Meta-state is the system's recorded truth; a recorder that writes
"reality happened" on a run where nothing did is the worst class of bug
here. Proven live (finding 21): the storage transition recorder wrote
`None -> active` on a run whose flag key was missing, so zero applies
executed — the state query's HARD drift caught the lie after the fact.
The rule this plan enforces: **a recorder may write a reality-claiming
record only when its lifecycle's apply was actually enabled**, exactly
the guard [tf_instance_builder.post_finalize_phase](packages/tf-ebs-instance-plugin/src/cs_image_system/tf_ebs_instance_plugin/tf_instance_builder.py)
already applies before first-bind pinning.*

1. Guard the storage transition recorder:
   [read_models.record_storage_transitions](packages/base/src/cs_image_system/base/read_models.py)
   is registered `after_apply` but never checks the flag — add an early
   return unless `utils.apply_enabled("storage")`, mirroring
   `post_finalize_phase`. The read-model write at its tail stays
   unconditional (read-models are derived from configuration, not
   claims about reality).
2. Audit every other reality-claiming recorder (verified 2026-09-02
   while planning: exactly two `register_after_apply` hooks exist —
   `mark_launched`, already guarded at launch_params.py, and
   `record_storage_transitions`, the step-1 bug; `release.py` line 113
   and `post_finalize_phase` are also already guarded). The audit's
   remaining work is the non-hook writers: pin/upgrade writers in
   `tf_instance_builder` and any meta-state writer reachable from a
   runner script. Add the guard wherever a reality-claiming write is
   found unguarded; leave derived-data writes (read-models,
   launch-parameter *structure*) unguarded.
3. Deliberate exception, kept and commented: the `state query` import
   path ([state_query.py](packages/base/src/cs_image_system/base/state_query.py)
   `record_storage_transition(..., action="import")`) records reality
   it just *observed*, not an apply — it is correct without the flag.
4. Tests: in `tests/test_v2_explore_state_query.py` /
   `tests/test_v2_gate*` style, drive the storage lifecycle with the
   apply flag OFF and assert `storage-state.yaml` records **nothing**;
   with the flag ON (journaled executor) assert the transition IS
   recorded. One test per recorder guarded in step 2.
5. Regression shape of finding 20: a fixture-missing flag key must
   behave as OFF — assert `utils.apply_enabled` treats an absent key as
   False (it does today; pin it with a test so it cannot drift).
6. `just verify` green; update the stage-1 ledger entry for finding 21
   in [docs/LEDGER.md](docs/LEDGER.md) with "fixed: truthful-recorders";
   note the guard rule in docs/OPERATIONS.md "Meta-state".

## Scoped runs (planned 2026-09-02)

*Status: DONE 2026-09-02 (feature/scoped-runs, squash-merged).*

*Findings 23, 24, 33 are one theme: the run must do exactly what was
asked, and its gate must judge exactly what was planned. Live cost:
`run instance-image --no-dry-run` re-baked all six images and launched
an instance nobody asked for; stale storage runners re-applied under
`apply_storage: false`; `gate-plan` accepted a leftover planfile after
a failed plan.*

1. **No stale planfile can pass the gate** (finding 33, smallest and
   sharpest): in
   [roots.gated_apply_commands](packages/hashicorp-utils/src/cs_image_system/hashicorp_utils/roots.py)
   emit `rm -f tfplan` as the first command of every plan → gate →
   apply sequence, so a failed plan leaves nothing for the gate to
   read; `gate-plan` (commands/gate.py) additionally errors when the
   planfile's mtime predates the newest `*.tf` file in the root, with a
   message naming the failed-plan cause.
2. **Execution-time flag enforcement** (finding 24): add a tiny CLI
   command `apply-check --lifecycle <name>` (beside `gate-plan` in the
   commands package) that re-reads `cfg/_config.yml` and exits nonzero
   — with a clear "apply_<lifecycle> is false NOW" message — when the
   flag is off at execution time. `gated_apply_commands` emits it
   immediately before the `apply` command, so a runner script generated
   under yesterday's flags cannot apply under today's.
3. Same enforcement for packer — **decided 2026-09-02: no bake-side
   flag.** A bake is additive (an AMI, never a destroy), already opt-in
   via `--no-dry-run`, and the step-4 selector is its scoping control;
   an `apply_bakes` flag would gate nothing the gate protects and add a
   second knob to forget. Recorded here per the plan's own instruction.
4. **Bake selector** (finding 23): `run` gains `--only <series>`
   (repeatable). Scope: it filters which *bake* runner scripts are
   emitted/executed (base-image and instance-image lifecycles) to the
   named series and their same-run chain parents; it does NOT filter
   the terraform roots — the instance root stays declarative (every
   non-destroyed instance exists; that is correct terraform, recorded
   as the finding-23 nuance). Unknown series names are a hard
   validation error.
5. Document the declarative-instances nuance and `--only` in
   docs/OPERATIONS.md ("The one command" and the apply-gate sharp
   edges — rewrite the finding-23/24 caveat paragraph to describe the
   new behavior instead of the hazard).
6. Tests: journaled-executor tests asserting (a) a stale tfplan is
   removed before plan / refused by the gate; (b) `apply-check` refuses
   when the flag is off in the CURRENT config even though the script
   carries apply lines; (c) `--only imgfile-basic-dask` executes
   exactly that bake script and no other; (d) `--only` with an unknown
   name fails validation. `just verify` green; update the docs/LEDGER.md
   ledger entries for 23/24/33.

## IaC-managed server enrollment tokens (designed 2026-09-02)

*Status: **COMPLETE 2026-09-02** (findings 32–33 below). Step 5: the
state query probes token liveness per managed group (read-only listing,
descriptions only — values never fetched); a missing IaC-owned token is
HARD drift whose message names the `state rm` repair, and a silent API
adds no claim. Verified live (all five present, no noise). Step 6: the
operator var is retired from `.envrc`; docs/OPERATIONS.md now
records the reference-first precedence with `TF_VAR_sft_enrollment_token`
as override/fallback only.*

*User directive (2026-09-01, [TODO.md](TODO.md) queued item): minting an
enrollment token per project by hand is not a thing a user should do.
Tokens are generated by IaC, stored in state, destroyed when their IaC
is destroyed; an admin deleting one out-of-band must have understood,
verified semantics.*

### Shape

One enrollment token per `<group>_rg_login` project, owned by the
identity root, consumed by instance roots by remote-state reference —
the same by-reference pattern as gids (DESIGN N7). *How* a token is
minted is plugin-dependent: the group-builder contract gains one hook,
and each identity plugin answers with its own mechanism (or declines).
The terraform/OPA plugin answers with oktapam resources.

### 1. Module (`tfmodules/okta_opa_module`)

The installed provider (oktapam 0.7.1, verified from the initialized
root's schema) carries the resource-group-scoped resource:

```hcl
resource "oktapam_resource_group_server_enrollment_token" "login" {
  resource_group = oktapam_resource_group.rg.id
  project        = oktapam_resource_group_project.rg_login.id
  description    = "cs-image-system launch enrollment for ${var.group_id} (IaC-owned; do not delete by hand)"
}

output "enrollment_token" {
  value     = oktapam_resource_group_server_enrollment_token.login.token
  sensitive = true # the provider does NOT mark `token` sensitive; we must
}
```

Lifecycle coupling is automatic: the token is created with the project
and destroyed with it (group/project destroys themselves remain
forbidden by the §5 standing constraint — the token rides along, it
does not change that rule).

### 2. Identity root emission (okta-opa group builder)

The root aggregates per-group module outputs into one sensitive output
map, alongside `group_gids`:

```hcl
output "group_enrollment_tokens" {
  value     = { for g, m in module.groups : g => m.enrollment_token }
  sensitive = true
}
```

### 3. Plugin contract (generation is plugin-dependent)

`GroupBuilderBase` gains:

```python
def enrollment_token_reference(self, group: str) -> HclRaw | None:
    """A terraform expression yielding the group's launch enrollment
    credential, or None when this identity plugin does not mint one."""
    return None
```

The okta-opa builder returns
`HclRaw('data.terraform_remote_state.<identity-ws>.outputs.group_enrollment_tokens["<group>"]')`.
A future identity plugin may mint differently (API call, vault, GCP
secret) — the instance side only ever sees an HCL expression.

### 4. Instance root consumption

`tf_instance_builder._launch_args` currently binds
`sft_enrollment_token` to `var.sft_enrollment_token` (operator-supplied,
DESIGN N26). New precedence, emitted as one expression:

```hcl
var.sft_enrollment_token != "" ? var.sft_enrollment_token
  : data.terraform_remote_state.oktagroups.outputs.group_enrollment_tokens["<group>"]
```

The operator var stays as an explicit override and as the fallback when
the group's plugin returns None. The token value never appears in
generated text, meta-state, or the config repo — it flows
state-to-state (N26 narrows to "never recorded in meta-state or
generated IaC"; both statefiles live in the private S3 bucket).

### 5. Out-of-band deletion semantics (analysis to verify live)

| Event | Expected behaviour | Verify by |
|---|---|---|
| Admin deletes token in OPA UI | Already-enrolled servers unaffected (enrollment is one-time; sftd holds per-server credentials) | delete a scratch token; existing server session still works |
| New launch during the gap | user-data writes a dead token; sftd enrollment fails silently; instance otherwise healthy (mounts/AccessAddress precede it) | launch with a revoked token |
| Next identity plan | token resource gone -> plan shows 1 to add (recreate), zero destroys — gate-friendly | tofu plan after deletion |
| After recreate | NEW token value -> remote-state ref changes; running instances untouched (`ignore_changes = [user_data]`); new launches enroll with the new token | plan on the instance root shows no changes |

Deliberate rotation = `tofu apply -replace` on the token resource (gate
whitelists it) — same mechanics as accidental deletion, on purpose.

**Live results (2026-09-02, the `basic` token deleted in the OPA UI):**
the "next identity plan" row was WRONG — provider 0.7.1 does not
degrade an out-of-band deletion to drift. (Finding 32) `tofu plan`
**errors** on refresh ("Server Enrollment Token does not exist"),
blocking every plan on the identity root until an operator runs
`tofu state rm module.group_<g>.oktapam_resource_group_server_enrollment_token.login`;
the next plan then shows exactly 1 to add and the gated apply recreates
with a NEW value (verified by hash: 5e2fd4d5… → 26795fde…; the other
four tokens untouched). This RAISES the stakes for the step-5 probe:
plan-based drift detection cannot see a deleted token — it trips over
it — so `state query` must be the witness and its message must name the
`state rm` repair. (Finding 33, harness note) a failed plan left the
previous run's `tfplan` on disk and `gate-plan` accepted it; the
generated runners chain plan→gate with failure propagation so the
system path is safe, but the gate should additionally refuse a planfile
older than its plan's inputs. Rows "enrolled servers unaffected" and
"launches during the gap fail silently" remain expected-but-unverified
(no server is currently enrolled via these tokens; no launches ran).

**Detection decision:** `state query` gains a token-liveness probe: the
identity builder's read-only hook lists enrollment tokens per project
(existing OPA API client, service-token auth) and reports a
recorded-but-missing token as HARD drift, exactly like storage. The
silent-enrollment-failure window otherwise has no witness.

### 6. Execution plan (each apply individually gated)

1. Module + builder emission + plugin hook + instance-root consumption
   + tests/golden (no live change; `just verify` green).
2. **Identity apply (explicit go):** plan must show exactly N tokens to
   add, zero destroys, zero group/user changes.
3. Regenerate instance root; confirm the plan is a no-op for running
   instances (none currently — stage 1 tore them down; the next launch
   simply needs no `TF_VAR_sft_enrollment_token` in the environment).
4. **Deletion experiment (explicit go):** run the §5 table against a
   scratch token; record findings here and in TODO.md.
5. State-query token-liveness probe.
6. Retire the operator token from `.envrc` once 3 proves the reference
   path (kept until then as the override).

## GCP increment 3 — storage, instances, session parity (planned 2026-08-27)

*Status:* **implemented** on `feature/v2-gcp-increment-3` (2026-08-27,
pushed, awaiting merge). Gates 1–6 and 8 done; gate 7 delivered as
overlay tests plus a local `tofu validate` of the four generated GCE
roots (`tests/test_v2_gcp_increment3.py`) instead of a second golden
tree — the AWS golden is byte-identical. New package
`packages/tf-gcp-plugin` (`tf-gcp-pd`, `tf-gcp-filestore`, `tf-gcp-gcs`,
`tofu-gce`), modules `tfmodules/gcp_storage_{pd,filestore,gcs}` and
`tfmodules/gce_instance`, `session_mechanism: iap` on the GCP runtime.
Known limits: Filestore/GCS state queries report *unavailable* (no
client libraries yet); base-image `tests:` are not per runtime (the GCE
overlay drops the fixture's AWS-only package test); provider credentials
come from the environment only (`GOOGLE_APPLICATION_CREDENTIALS`/ADC),
never generated IaC. Nothing touched GCP, AWS or Okta. Decisions 2026-08-27: storage types **pd + filestore + gcs**;
session mechanism **IAP**; image sharing **deferred** (with Q2a);
project/zone/network **placeholders** (fixture values) until the real
target exists — every gate is generation + validate only, so real values
drop in without code change. Decision 2026-08-27: a real GCP target
is in sight, so increment 3 of the GCP exploration
([EXPLORE.md](EXPLORE.md), "GCP Support — exploration") gets a
plan. Increments 1–2 (provider-neutral packer builder, `packer-gce`) are on
`feature/v2-explore-gcp`; the pins-per-runtime prerequisite is on
`feature/v2-pins-per-runtime`. Nothing here touches AWS, GCP, or Okta:
every gate is proven by generation tests over a GCE overlay fixture and
`validate` of the generated roots.

### Scope

One GCE runtime alongside the AWS one, driving the four lifecycles end to
end for the fixture: identity unchanged (OPA is cloud-agnostic), storage
and instance roots on GCP, base/instance images already baked by
`packer-gce`, session parity for debug access.

### Gates

1. **Per-runtime prerequisites** (base image). `storage_types` declared on
   a base image are filtered at bake to the storage plugins whose
   runtime is the bake's runtime (`StorageBuilderBase.runtime_of()`), so a
   GCE bake stops installing `amazon-efs-utils`/AWS CLI. Same for
   identity types (all runtime-neutral today). Test: the GCE build file
   carries only `gcp-pd`/`filestore` prerequisites.
2. **`tf-gcp-pd` storage plugin** (single-attach, POSIX; capability type
   `pd`): `google_compute_disk` + tags→labels mapping (`gce_label`), the
   storage state machine's transitions (`archived` = snapshot + delete
   disk, `destroyed` = whitelisted destroy), `destroy_whitelist`,
   `query_state` via `compute.disks.get` for the state report.
   Gid-by-reference: `data.terraform_remote_state.oktagroups` exactly as
   the AWS roots. Test: storage lifecycle root generates and validates
   (`tofu validate -backend=false`) for a `pd` storage.
3. **`tf-gcp-filestore` storage plugin** (many-attach, POSIX; type
   `filestore`): one Filestore instance per storage, per-group subtree
   created at first mount (same launch-param pattern as EFS access
   points, but Filestore has no access points: the subtree is chgrp'ed at
   launch). `base_image_prerequisites`: `nfs-utils`. Object storage
   (`gcs`, non-POSIX, many) follows the S3 plugin shape if wanted; not in
   this increment.
4. **`tf-gce` instance plugin**: `google_compute_instance` from the pinned
   build (`image = <build id>` — the GCE image name; `ignore_changes` on
   the image like the AMI rule), `metadata.user-data`/`startup-script`
   from `user_data_template` (cloud-init on the RHEL family; the ansible
   emitter from `base/ansible_launch.py` is the alternative executor),
   attachments from the storage read-model (`attached_disk` for pd, mount
   entries for filestore), `launch_params` `device` naming for GCE
   (`/dev/disk/by-id/google-<name>` instead of `/dev/xvdf`),
   `replace` for pending upgrades, decommission whitelist.
5. **Session mechanism** `iap` (or `oslogin`): `session_mechanism()`
   returns `iap`, `session_agent_commands()` enables the guest agent /
   OS Login metadata, `session_verify_commands()` checks it; runbook
   entry mirrors the SSM one. No IAM changes are generated by the system
   (recorded as an operator prerequisite, like the SSM instance profile).
6. **State query parity**: `GCPCloudBuilder.query_images()` via
   `compute.images.list` filtered by `labels.csis_series:*`; storage
   `query_state` per plugin; `build_id_from_artifact` already done.
7. **Fixture and golden**: the GCE overlay used by
   `tests/test_v2_explore_gcp.py` grows one `pd` storage, one
   `filestore` storage and one instance on `gcloud-east1`; a second
   golden tree `tests/fixtures/v2_golden_gce` is generated from the
   overlay so the AWS golden stays untouched.
8. **Lineage/pins**: nothing new — pins are keyed per runtime after
   `feature/v2-pins-per-runtime`; the instance plugin binds
   `<instance>` to the GCE build id at first launch as AWS does.

### Order and estimate

1 → 2 → 4 (pd + instance is the smallest end-to-end slice) → 3 → 5 → 6 →
7 runs alongside each gate. Each gate is one commit with tests; `just
verify` green throughout. Rough size: gates 2 and 4 are each about the
size of the AWS EBS/instance plugins (the module shapes copy over); the
rest is small.

### Open questions for the stakeholder

- Project/zone/network for the real target, and whether Filestore (min
  1 TiB, cost) is wanted at all or `pd` + GCS suffices.
- IAP vs OS Login as the debug session mechanism (IAP tunnels work with
  no public IP; OS Login ties to Google identities, not OPA).
- Whether the GCE images should be shared to other projects (the
  artifact-level access question, DESIGN Q2a, deferred for AWS too).

---

## V2 execution — feature/v2-lifecycles (2026-08-26)

*Executes [docs/DESIGN.md](docs/DESIGN.md) rev 20 end to end on a persistent
feature branch. Constraints for this pass: **no changes to Okta or AWS**
(every test stubs cloud and tool execution; nothing runs `--no-dry-run`
against the live account), one commit per gate, `just verify` green at
every commit, gate evidence as `tests/test_v2_gate*.py` (run with
`just v2-test`).*

### Live run (2026-08-31 → 2026-09-02)

*Stage 1 of [TODO.md](TODO.md) took the system live for the first time;
per-step details and findings 1–31 live there and in the develop
history. The stubbed-execution constraint above applied to the 2026-08
test pass; the live run used explicit apply gates per docs/LEDGER.md.*

- **Bakes**: 6 base + 12 instance builds in lineage, all over the SSM
  communicator on t3.medium; first live `upgrade image` moved one pin.
- **Identity**: zero destructive OPA writes for the whole run — live
  group memberships were reconciled by six `tofu import`s that also
  registered the `group_gids` outputs (gid-by-reference chain, N7).
- **Storage**: first real applies — `mnt_data`
  (vol-0fe1e27716f86c2f2), a created EFS (fs-02d658f1561aab44b, access
  points per group with gids by reference), and a uniquely named
  bucket; transitions recorded truthfully after finding 21.
- **Instances**: `test` and `test2` launched (t3.medium, private
  subnet, no public IPs, own `csis-instances` SG plus the existing
  OKTA-GATEWAY group by configuration), `mnt_data` mounted with
  `/mnt/data/coops` at gid 180007 mode 2770, both enrolled under
  `coops_rg_login`.
- **Gate 5 criterion met 2026-09-02**: `sft ssh test`/`test2` logins
  succeed via the Okta gateway relay under the owning group's policy.
- **Closed 2026-09-02**: `imgfile-basic-dask ami-09759842591f8e481`
  released for model `default`; both instances torn down through the
  gate (4 resources destroyed, storages kept); meta-state
  truth-restored (launched: false, pins unbound); the 11 orphan AMIs +
  12 snapshots verified ours and handed to the operator to deregister.
  Next: IaC-managed enrollment tokens (queued as the very next item).

### Gate map (DESIGN §4) → deliverables

| Gate | Delivered as | Evidence |
| --- | --- | --- |
| 1 A lifecycle decomposition | `base/lifecycles.py` (Lifecycle enum, phase/builder partition), `commands/run_lifecycles.py` (runner), lifecycle-scoped `GlobalTypeContext.generation_path`, `cs-image-system run <lifecycle>... / --all`, V1 commands as aliases | `test_v2_gate1_layout_equivalence.py`: `run --all` reproduces the frozen V1 snapshot (`tests/fixtures/v1_baseline`) content-identically under the declared path mapping |
| 2 C runner scripts + gating | `generated/<lc>/run-<lc>.sh` per lifecycle (only when it defers work), root `final_execution.sh` = the shell form of GOALS.md 5.5 gating, apply step iterates lifecycle dirs | `test_v2_gate2_runner_gating.py`: absent-script no-op, stale script executed, Q5 wipe isolation, per-lifecycle terraform state bindings disjoint |
| 3 B relocation + meta-state | `module_source_base` relative to the config root (resolved per workspace depth; absolute/URL pass through), `base/meta_state.py` (public-safe YAML store outside `generated/`, secret-scanned on every write), `run --commit` meta-state commit | `test_v2_gate3_relocation_meta_state.py`: config + tfmodules relocated to a temp dir generate resolvable module sources; meta-state survives wipes; the commit carries read-models + generated IaC in a temp git repo |
| 4 D+E read-models, gid reference chain, storage state machine | `OutputSpec` + single-label blocks (LEDGER.md item 6); identity root emits `group_gids` via a `data "external"` **gid shim** (`cs-image-system identity export-gids` → okta plugin's read-only OPA lookup; the oktapam provider/SDK expose no group gid, N7's pre-authorized "other mechanism"); storage schema (`groups`/`public_read`/`share_mode`/`state`, `ALL` retired); EFS access points + S3 prefixes with gids **by remote-state reference only**; per-plugin cardinality/prerequisites/transition actions; `base/storage_state.py` state machine; tombstones; `unmanaged: true` groups → `state rm`; every terraform root defers `plan -out` → `gate-plan` → apply-only-if-`apply_<lifecycle>` | `test_v2_gate4_identity_storage.py` (+ `okta-opa-plugin/tests/test_opa_gid_shim.py`); `test_v2_golden.py` pins the exact emission (`just golden-regen`) |
| 5 F1+F2 capability plumbing + activation + launch params | OS builders (the base-image definitions) declare `identity_types`/`storage_types` + `admin_user`/`admin_public_keys` (global `config.admin_public_keys`, per-base override; public-key schema, private material refused, no-key-no-session dead end hard-fails); `base/capabilities.py` resolves effective capabilities through pins to the stamped root build (N11/N24); plugins supply prerequisites (`okta`: sftd dormant; `efs`/`s3`/`ebs`) and the AWS runtime's `session_mechanism: ssm` agent; instance images bake the owning group's activation (`sftd.tx.group` label) after their mods; `base/launch_params.py` generates user-data templates (mounts, group subtree by gid reference, enrollment token via sensitive var), records them in `meta-state/launch-params.yaml`, enforces immutability after launch, whitelists decommissions; `aws_instance` module gains `ignore_changes=[ami]`, EBS attachments, user_data, instance profile | `test_v2_gate5_capabilities_activation.py` |
| 6 F3–F5 + M lineage, pins, mods | `base/lineage.py`: every source carries `csis_*` lineage tags (series, parent, run, fingerprint, stamped capabilities); unique `ami_name` now actually renders the run timestamp (V1 emitted the literal template); packer manifests → `meta-state/lineage.yaml` records (build id, parent, input fingerprint, capabilities, mods with content hashes per N23c) and first-bind pins (image → base build built this run; instance → launched build); rebuilds bake FROM the pinned base (`image-id` filter, never `most_recent`); first bind of an unpinned consumer goes to the recorded series head; pinned instances emit a literal AMI; `upgrade instance` / `upgrade image` moves exactly one edge, an instance upgrade plans `-replace` and whitelists that destroy; `aws_instance` ignores AMI drift | `test_v2_gate6_lineage_pins.py` |
| 7 G headless | interactive finalization countdown deleted (nothing waits on a TTY; `sleep_before_finalization` ignored); `run`/`validate`/`gate-plan`/`upgrade` exit nonzero on failure with `generated/run-summary.json` always written; per-lifecycle credential contract, apply flags, meta-state files and operating procedures in [docs/OPERATIONS.md](docs/OPERATIONS.md); docs/LEDGER.md items 3 and 6 closed, item 9 (verify the OPA gid field) opened | `test_v2_gate7_headless.py` (drives the real CLI through typer's runner with no input); `just v2-dry-run` for the live read-only dry run |

### Findings while executing (pre-existing, fixed in passing)

- `GlobalTypeContext._finalization_phase` was class-level mutable state:
  a second context in one process inherited the first run's deferred
  commands. Now allocated per instance, bucketed per lifecycle.
- Packer build files listed sources in Python *set* iteration order —
  different per process. Sorted now (deterministic diffs).
- `ami_name` was emitted with a literal `{{ execution.timestamp }}` (the
  `_final_name` template never resolved) — unique naming was broken. Fixed
  under gate 6.
- The `tests/test_config_resolution_e2e.py` tests loaded `test_folder`
  against live EC2 (VPC discovery) — they now stub it and need no
  credentials.

---

## Retrospective: the Okta/OPA detours (2026-08-25)

*Observations on the August identity/access work — what the wrong turns
were and what pattern they share. Recorded as input to future planning,
not as a complete account of concerns.*

### The shared shape

Mechanism was repeatedly built before custody was decided, and contracts
were locked against the repo's **model** of the world instead of the
**deployed** world. Each detour came from answering "how should
terraform do X?" before "who owns X at all?" — while the live Okta/OPA
installation (March-era, half-documented, partially hand-edited) already
had answers waiting to be discovered.

### The three detours

1. **Capability built before custody was decided** (user-creation
   pipeline, ~08-12/13). A complete, verified pipeline for *creating*
   Okta identities was built before settling whether a machine should
   ever create identities. The answer was no — a person owns that, in
   the admin UI — which made the resource-emission half permanently dead
   on arrival. The other half survived as production code: the
   credential chain, the workspace mixin, and the lookup emitters.
2. **Safety expressed as incapability instead of as invariants**
   (read-only wiring, 08-17). The real requirement was an invariant —
   never destroy identities or groups — but it was implemented as a
   blanket prohibition (make everything read-only), which over-rotated
   past the actual goal (policies and membership were always meant to be
   managed) and aimed at the wrong product besides ("Okta group" is one
   word for two objects; the RO lookups queried the org directory while
   everything that mattered lived in OPA). The end state is the correct
   expression: managed groups + hard never-destroy rules + gated,
   manifest-checked applies.
3. **A contract ratified against the model rather than the world**
   (`email_as_username`, locked 08-13, fully reversed 08-21). A "locked"
   decision with a config migration behind it, un-migrated a week later
   when the live OPA team showed usernames are bare. Same root cause as
   the seven apply collisions on 08-24 (memberships and policies that
   discovery never enumerated): the production system's existing beliefs
   were learned in installments.

### Kept honest

- The detours were mostly the **cost of discovery, not waste** — the
  live state was undocumented and its terraform state lost; each wrong
  turn surfaced the fact that corrected it, and each left durable assets
  (the RO user builder IS the production design; the runbook, mixin,
  gid/uid constraints, and gated-apply discipline all came out of detour
  work).
- The sharper framing is **allocation, not correctness**: roughly two
  weeks went into the access-control corner of a system whose name and
  core purpose is *images*. The image → instance pipeline still has
  placeholder playbooks, stubbed lifecycle phases (test / execute /
  verify / cleanup), and a deliberately disarmed instance apply. If the
  end goal is "scientists get working sandbox machines," the doorway got
  finished before the building.

### The prevention rule

Before locking any contract that touches a live system, **enumerate what
the live system already believes** — all of it, including the object
types the plan doesn't intend to manage (for OPA: groups, users,
memberships, resource groups, projects, AND security policies). This is
the generalized form of the local-migration discovery lesson.

---

## Local migration: OPA groups managed, users read-only (COMPLETE)

*Status: **complete** (2026-08-24). Both roots plan "No changes" against
live infrastructure. Formerly the standalone `LOCAL_MIGRATION.md`
(created 2026-08-21, removed after completion); code and config comments
referencing "PLAN.md local-migration Qn" point here. Full decision/
execution history is in that file's git log (last at commit d4e29a1).*

### Final architecture (as applied)

- **Users**: created by hand in the Okta admin UI; every user item is a
  `data "okta_user"` lookup via the `okta-tf-ro` builder. Identity
  contract (Q3): `user.name` is the **bare OPA username** (exact OPA
  casing, e.g. `Blake.Bravo`) and feeds membership attachments;
  `user.email` (explicit, else `default_user_email_template` →
  `{{ user.name }}@noaa.gov`) is used **only** for the org lookup.
  `email_as_username: false` — this superseded locked decision 7 below;
  decision 9 (required first/last names) stands.
- **Groups**: managed OPA (oktapam) resources via
  `tfmodules/okta_opa_module`. Per group NAME: `${NAME}_admin`/`_user`
  groups; `${NAME}_rg` whose delegated resource admin is the group's
  **own** `${NAME}_admin` (Q1 — builder emits empty
  `delegated_admin_group_ids`, module fallback supplies it);
  `${NAME}_rg_login` project with `gateway_selector` from
  `config.okta_gateway_selector` = `environment=staging` everywhere (Q6 —
  `OktaGroupBuilderModel.effective_gateway_selector` falls back to global
  config; a templated model default was rejected because the
  TemplateResolver has no `config` scope); user+admin policy pair bound
  to the rg. Root group's admins merge into every group's admins unless
  `include_root_group_in_admins: false` (Q2). Groups: basic (root),
  coops, secofs (re-adopted, Q5), stofs, tcmet.
- **No Okta org groups are ever created.** Org-directory
  `coops_*`/`stofs_*` twins are read-only `APP_GROUP` mirrors pushed by
  the OPA app (`0oa1wekqjy2fJGry61d8`) in a 2026-03-19 batch (Q4).
- **Base images are orthogonal**: pre-prepped receivers that never
  contain system-managed groups/users — a name collision there is a
  base-image bug, not a terraform concern.

### Execution record

- **2026-08-21 (Phases 0–4, read-only + state-only)**: S3 state backed up
  (`s3://noaa-ioos-cloud-sandbox-tfstate/statefiles/csia-image-system-test/oktagroups.tfstate`);
  stale lockfile cleared; `.envrc` fixed to the three read scopes; OPA
  discovery via the oktapam API; conformance changes (builder back to
  `okta-tf`, identity reversal, Q1/Q2 in `_group_module_call` with
  pinning tests); four pre-existing OPA groups imported by name
  (`coops_admin` a0d15f8e…, `coops_user` 07b5ce02…, `stofs_admin`
  817f97e4…, `stofs_user` e39f660f…). Gated plan: 21 add / 2 change /
  0 destroy; regeneration proved byte-identical.
- **2026-08-24 (Phase 5, applies on explicit go)**: manifest-gated apply
  landed 16/23 (both updates + all creates that had no collision).
  **Seven creates were refused with "already exists"** — a March-era run
  of the pre-module emitters (state since lost) had already created the
  admin memberships and four ACTIVE policies
  (`coops/stofs_v1_security_policy_{admin,user}`) bound to
  **long-deleted** resource groups (ghost references — granting nothing).
  All seven were imported (`group|username` for attachments, UUID for
  policies). The four ghost-bound policies planned as
  `replace_because_cannot_update` on `resource_group`; on explicit
  authorization the replacement applied: 4 added / 4 destroyed. Final:
  **both roots "No changes"**, 39 objects in the group state.
- **Damage record**: across the entire migration the only destroys ever
  executed were those four inert policies, explicitly authorized. No
  group, no user, and no membership was removed at any point. State
  backups in `~/state-backups/` (2026-08-21 and two on 2026-08-24).

### Lessons

- **Discovery must enumerate security policies AND group memberships**,
  not just groups/users/resource groups — that gap caused all seven
  collisions (though terraform's refuse-don't-modify behavior made them
  harmless).
- `oktapam_security_policy` cannot be rebound to another resource group —
  `resource_group` is a force-new attribute; rebinding means replacement.
- Import formats: `oktapam_group` by name; `oktapam_user_group_attachment`
  as `group|username`; `oktapam_security_policy` by UUID.
- gids: OPA assigns them; existing groups keep theirs only if never
  destroyed/recreated — collisions become imports, never replaces.

---

## Okta credential chain verified; group-side design fork (session notes)

*Status: **credentials resolved, read-only end to end** (2026-08-19). The user
root plans clean against the live org. The group root is blocked on two items
and one unmade design decision, all recorded below.*

### Credential chain — resolved

- API Services app, client id `0oa2604feo1AuyHi01d8`, private-key JWT with the
  rotated key (kid `rnQ2me1o-u6K2-Elo9g6TuIyv-jd1hAzeXVOwYqPMH8`) is accepted
  by `https://noaa.okta.com/oauth2/v1/token`. No DPoP obstacle.
- Granted scopes (verified by direct token probes, one scope at a time):
  `okta.users.read`, `okta.groups.read`, `okta.roles.read`. The `*.manage`
  scopes are **not** granted — deliberate, matching the read-only design.
- `okta.roles.read` is required because `data "okta_user"` fetches each user's
  admin roles by default. Alternative (deferred emitter change): emit
  `skip_roles = true` (and `skip_groups = true`) in the lookup blocks, then
  revoke `okta.roles.read`.
- Gotchas: `.envrc` must be sourced **from the repo root** (the private key is
  read via a relative path; sourced elsewhere it silently exports an empty
  key). `.envrc` still exports `OKTA_API_SCOPES='okta.users.manage'`, which is
  ungranted — change it to
  `OKTA_API_SCOPES='okta.users.read okta.groups.read okta.roles.read'`.
  *(Annotation 2026-08-27: done on 2026-08-21; since 2026-08-26 the lookups
  emit `skip_roles`/`skip_groups`, `okta.roles.read` is revoked, and
  `.envrc` exports only `okta.users.read okta.groups.read`.)*
- **User root verified green**: `tofu plan` on
  `okta-tf-users/user-generation` resolves all 11 `data "okta_user"` lookups
  ("No changes"). The identities already exist in the org.

### Group root — blocked, two items

1. **Orphaned managed state.** `oktagroups.tfstate` holds 14 oktapam objects
   from old applies (full `module.group_basic` and `module.group_secofs`
   trees: groups, resource groups, resource-group projects, security policies,
   user-group attachments). The RO config no longer declares the oktapam
   provider, so `plan` refuses ("Provider configuration not present").
   Options, undecided: `tofu state rm` all 14 (state surgery only — the real
   OPA objects stay alive, permanently unmanaged), or point the RO root at a
   fresh state key and keep the old file as a record.
2. **Group name contract.** Probing `/api/v1/groups` in the org: `basic` and
   `tcmet` do not exist under any spelling; `coops` and `stofs` exist only as
   `coops_admin`/`coops_user` and `stofs_admin`/`stofs_user` (the old managed
   builder's naming). The okta provider's group-name search is prefix-based,
   so a lookup of `coops` is *ambiguous* (matches `coops_admin`), not merely
   missing. Unexplained: those `*_admin`/`*_user` groups are in the **org
   directory**, yet the old builder created same-named groups in **OPA** —
   check in the console whether the org copies carry a managed-by-app marker.

### The design fork: Okta group vs OPA group (decision pending)

> **Resolved 2026-08-21: Option B (PAM-centric).** Users stay read-only
> (manual in the Okta admin UI); groups are managed OPA (oktapam) resources;
> no org groups are ever created. The migration to that end state — including
> the orphaned-state and naming problems below — is governed by
> the local-migration section at the top of this file (formerly
> `LOCAL_MIGRATION.md`).

The two "group" objects live in different products:

- An **Okta org group** (`okta_group`, has a data source) is a directory
  object: app assignment/SSO, org-wide policy targeting (sign-on, MFA,
  password, group rules), provisioning/push, and the thing OPA can **sync
  from** when the group is assigned to the OPA app. It knows nothing about
  servers.
- An **OPA/oktapam group** (`oktapam_group`, **no** data source) is a
  Privileged Access object: principal in security policies (SSH/RDP, admin
  level), member of resource groups/projects, delegated resource admin, and
  drives account provisioning on enrolled servers. Invisible to the
  directory.

"Membership managed by the generated terraform" must pick a home:

- **Option A — directory-centric**: terraform manages `okta_group` +
  membership in the org; groups are assigned to the OPA app and sync into
  OPA; OPA-side terraform manages only policies/resource groups referencing
  the synced groups. Membership is set once and effective everywhere Okta
  reaches. Consequence: org *groups* are no longer read-only — the RO
  contract narrows to *users*.
- **Option B — PAM-centric** (what the old managed builder did): terraform
  manages `oktapam_group` + `oktapam_user_group_attachment`. Membership
  affects servers only; the `data "okta_group"` lookups wired in the section
  below serve no purpose for it.

### Housekeeping

- Stale state lock on `okta_tf_users.tfstate` from the aborted 2026-08-14
  plan run — clear with
  `tofu force-unlock 78c5b1d1-49f5-d8bf-b08c-3def63386034` (read-only checks
  meanwhile used `-lock=false`).
- 2026-08-18 `just verify` on develop: 241/244; the 3 failures are
  `tests/test_config_resolution_e2e.py` hitting live AWS with an expired SSO
  session (`aws sso login` fixes) — unrelated to any change here.

---

## test_folder: all Okta groups and users managed read-only

*Status: **implemented** (2026-08-17), branch `okta_users_groups_to_ro`,
squash-merged to develop. `just verify` green (244). Regenerated okta roots are
data-only: 11 `data "okta_user"` + 4 `data "okta_group"` lookups, zero
`resource`/`module` blocks.*

### Decision

Actual Okta identities — users and groups — are **not** created or modified by
this system. A person adds them manually through the Okta admin web interface,
so a human stays in charge of that process. The test configuration references
them read-only. Group and user *policies* and *membership*, by contrast, WILL
be managed by the generated terraform (consuming the read-only lookups) for
possible downstream use — that emission does not exist yet: under the RO group
builder no module calls are emitted, so the `oktapam_user_group_attachment`
path in `tfmodules/okta_opa_module` is currently bypassed. Designing
membership/policy emission on top of the lookups is the next piece of work
once credentials are fixed.

### What changed (config only, no code)

- `test_folder/cfg/group-builders.yml`: both default builders switched to the
  read-only type — `oktagroups` from `okta-tf` to `okta-tf-ro` with
  `required_providers` moving from `okta/oktapam` to `okta/okta >= 6.0`
  (RO group lookups use the okta provider's `data "okta_group"`), and
  `okta-tf-users` from `okta-tf` to `okta-tf-ro`. Since no user/group YAML
  entry sets a `type:`, everything routes to these defaults.
- `test_folder/groups/test-group.yaml`: stale default-type comment updated.

### Findings

- **First real authenticated API contact happened here.** With `OKTA_API_*`
  exported, the RO user root's credential-gated `tofu plan` ran its eager
  lookups and failed with `failed to list users: empty access token` — the
  key → token exchange does not work yet (being fixed; see the credentials
  runbook below). With the credential vars unset, `plan` is skipped and full
  `generate` exits 0.
- RO user lookups are eager (`lookup_depends_on=False`), so `plan` also
  requires the referenced identities to actually exist in the org. They were
  never applied (see the previous section), so they must be created manually
  before the RO roots can plan cleanly.

### Remaining

*(Annotation 2026-08-27: this list is fully complete/superseded — 1 by the
credential-chain section, 2–3 by the completed local migration (managed OPA
groups + read-only users), 4 by commit 7c4be96. Kept as a historical record.)*

1. Fix the Okta API credential chain (in progress).
2. Create the users/groups manually in the Okta admin console.
3. Membership/policy emission consuming the RO lookups.
4. `User.as_profile()` docstring annotation (R6, two sections down) — deferred
   until the API key works.

---

## Read-only (data-source-only) Okta group/user builders

*Status: **implemented** (2026-08-14). All okta-opa-plugin tests green (44).*

### Context

The managed okta-tf builders create Okta identities (`okta_user` resources) and
group infrastructure (module calls against `tfmodules/okta_opa_module`); there
was no way to *reference* existing Okta users/groups without managing them. This
adds read-only builder variants that emit **only terraform `data` blocks**.

Decisions: group lookups use the okta/okta provider's `data "okta_group"` (the
oktapam provider has no group data source — its placeholder block is emitted
`commented_out=True` today), so RO group instances declare okta/okta in
`required_providers`, not oktapam. New type string **`okta-tf-ro`** (the
registry allows one builder per type-string per VCT classification).

### Shape

- `okta_tf_models.py`: `OKTATF_RO = "okta-tf-ro"`; `OktaTFGroupLookup` emitter
  (`data "okta_group"` by name; NOTE the okta provider's name search is
  prefix-based — exact YAML group names are the contract).
- `OktaTfUserRoBuilderModel` / `OktaTfGroupRoBuilderModel`: subclass the managed
  models in the per-type models files, overriding `csis_name()`/`type`.
- `okta_opa_tf_user_ro_builder.py`: `OktaTfUserRoBuilder(OktaTfUserBuilder)` —
  inherits scaffolding and credential-gated commands; `generate_items_during`
  emits only `-users-data.tf` with eager lookups (`lookup_depends_on=False`).
- `okta_opa_tf_group_ro_builder.py`: `OktaTfGroupRoBuilder(OktaTfGroupBuilder)`
  — adds the skip-when-empty guard the managed group builder lacks, emits
  `-groups-data.tf` lookups instead of module calls, gates `plan` on
  `okta_credentials_present()`.
- `main.py`: all four RO classes registered (services list + model→builder map).
- Routing: a YAML builder instance with `type: okta-tf-ro`; users/groups route
  to it by instance name via their `type:` field, or by default when it is the
  default builder. test_folder wiring landed 2026-08-17 (see the section above):
  both default builders are now `okta-tf-ro`.

---

## Okta user generation: `hashicorp-utils` additions + `okta-opa-plugin` changes

*Status: **implemented and verified** (2026-08-13), steps 1–8 committed on
`execute_plan_branch_from_feature_retry`. Verification: `just verify` fully green (232);
full `generate` exits 0 with zero applies; `tofu plan` on the user root (DPoP off,
private-key JWT creds from `.envrc`): **11 to add, 0 to change, 0 to destroy**. Remaining:
the apply itself, deliberately not run — nothing may change in Okta yet. Note the plan's
data lookups defer via depends_on, so this plan may not have exercised a live authenticated
API call; the credential chain (key → token → admin role → scopes) gets its first hard
proof at first real API contact. Implementation note: `super_safe_name` now also folds `@`
to `_`, since user names are emails under `email_as_username` and `@` is not a valid
terraform label character.*

### Context

`OktaTfUserBuilder` produces exactly one artifact today — a single comment line in
`test_folder/generated/okta-tf-users/user-generation/okta-tf-users-user-generation.tf`.
No user Terraform is emitted **anywhere** in the system:

- `OktaTfGroupBuilder.generate_items_during` has a `for user in self.get_users_for_builder()`
  loop ([okta_opa_tf_group_builder.py](packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/okta_opa_tf_group_builder.py))
  that always iterates **zero** times: the `users` ItemKind attaches to `VCT.USER_BUILDER`
  ([global_context.py:1203-1206](packages/base/src/cs_image_system/base/global_context.py#L1203-L1206)),
  so `GroupBuilderBase.local_users` is never populated. Confirmed on disk — no `*-users.tf` exists.
- The emitters it would call are hard-coded `commented_out=True` because the provider's
  `oktapam_user` resource "does not currently function"
  ([okta_tf_models.py:63-64](packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/okta_tf_models.py#L63-L64)).
- `OktaTfUserBuilderModel` is not Terraform-ready: no `register_hcl_requirements`, no
  `transform_provider`, no credential fields, and `required_providers` is typed
  `list[dict[str, str]]` where the group model uses `list[ConfiguredTerraformProvider]`.

Outcome: the okta user builder owns a real Terraform root that creates Okta identities,
mirroring `OktaTfGroupBuilder`, with the group root left untouched.

### Locked decisions

1. **Own TF root** — `okta-tf-users/user-generation/` with its own `terraform{}`,
   provider, vars, `.tfbackend.hcl`, and `fmt`/`init`/`validate`/`plan`.
2. **Both resources and data lookups**, in separate files.
3. **`okta/okta` provider's `okta_user`**, not `oktapam_user`. New credential path
   (Okta API token) separate from the oktapam key/secret.
4. **Attachment stays in `tfmodules/okta_opa_module`** via `oktapam_user_group_attachment`
   with `for_each = toset(var.members)`. The user root creates identities only → **no**
   `terraform_remote_state` wiring, no cross-root dependency.
5. **`status = "STAGED"` by default**, tunable via a new `default_user_status` model field,
   so the first apply does not email real people.
6. **`login = user.email`**.
7. **`email_as_username: bool = True`** on the user-builder config. When true, `user.name`
   must be identical to `user.email` — see step 2. This is what makes decision 4 safe: the
   group module passes `user.name` as `oktapam_user_group_attachment.username`, and forcing
   it to equal the Okta login removes the mismatch risk entirely. When false, no enforcement
   and the mismatch risk is knowingly absorbed.
8. **`User.public_keys` is intentionally not emitted** by `okta_user` (the resource has no
   home for it). Reserved for later consumption by the modification builders; document in
   the `OktaTFUser` docstring so it reads as deliberate rather than dropped.
9. **`first_name` and `last_name` become required, and `split_name()` is deleted.**
   `okta_user` requires both, so they become data rather than something parsed out of `name`.
   This removes the name-parsing failure mode entirely instead of patching it — see step 2.
   **Implemented** (2026-08-12): both fields are non-default (missing → construction/structure
   failure) and `__post_init__` additionally rejects blank/whitespace values, since a required
   field can still be structured from an explicit `first_name:` null or `""` in YAML;
   `groups/users.yaml` carries explicit names (parser-equivalent lowercase values — correct
   casing at will); pinned by `packages/base/tests/test_user_required_names.py`.
   Consequence: a separator-less `name:` (e.g. `jdoe`) is now legal — the old parser's
   `ValueError` was its only other effect, and nothing reinstates that check.

### Corrections to the naive approach

These were found during design and are load-bearing:

1. **Root-level resources need an explicit `provider =` meta-argument.**
   `configure_provider` *always* aliases (defaults to `ssn(workspace)`,
   [collector.py:161-183](packages/hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py#L161-L183)),
   so no default `okta` provider block is emitted. Every root-level `okta_user` must carry
   `provider = okta.okta_tf_users`, taken from `provider_bindings(self.name)["okta"]` — never
   hand-written. Existing roots get away without this because all their resources live in modules.
2. **`data "okta_user"` for users created in the same root breaks `plan` on a fresh workspace**
   (data sources read at plan time; the user doesn't exist yet). Add
   `depends_on = [okta_user.<label>]` to defer the read to apply.
3. **`okta_user.user_type` is a User Type *id*, not `"human"`/`"service"`.** Do not emit
   `OKTA_USER_TYPE`. Service-account-ness has no home on this resource.
4. **`"DISABLED"` is not a valid `okta_user` status.** Valid: `ACTIVE`, `STAGED`,
   `SUSPENDED`, `DEPROVISIONED`. Map `is_enabled=False` → `SUSPENDED`.
5. **Do not use `User.as_profile()`** — see the R6 explanation at the bottom of this plan.
6. **`email_as_username` breaks the email template**, which must be fixed with it. See step 2.
7. **`"required": True` metadata is not enforcement.** `field_is_required`
   ([orchestrator.py:99](packages/base/src/cs_image_system/base/orchestrator.py#L99)) is called
   from exactly one place, `upgrade_deferred_fill_defaults`, and only back-fills the default
   when the value is `None` — it never rejects a missing value. Making a field genuinely
   required means a dataclass field with **no default**, so cattrs raises. `User` is
   `kw_only=True`, so adding non-default fields after defaulted ones is legal.

Plus one mechanical trap: `AssetSet.add()` silently drops falsy values
([asset.py:110-112](packages/base/src/cs_image_system/base/basic/asset.py#L110-L112)), so
`render_blocks(..., separator="")` loses its separators. Use `separator="\n"`.

### Implementation, as independently-green commits

Each step must pass `just verify` on its own.

#### 1. `hashicorp-utils` — nothing *required*, two cleanups worth doing

Everything user generation needs already exists (`require_provider`, `configure_provider`,
`declare_variable`, `set_backend`, `provider_bindings`, the four `generate_*`, plus
`ResourceSpec`/`DataSpec`/`Raw`/`render_blocks` with `NestedBlock` for the data source's
`search {}`). Workspace-keyed state paths come free from `BackendRegistration.state_file_path`.

- **Collapse `collector._hcl_value` into `blocks.hcl_value`.**
  [collector.py:118-124](packages/hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py#L118-L124)
  is a weaker duplicate — no `Raw`, no list/dict recursion. `blocks.py` imports only
  `.hashicorp`, so the import is acyclic. Keep the `_hcl_value` name as an alias so the two
  call sites are untouched.
- **New `hashicorp_utils/roots.py` with `TerraformRootMixin`.** `_backend_config_path` and
  `_init_args` are already duplicated in `OktaTfGroupBuilder` and `TofuStorageBuilder`; the
  user builder would be copy #3. API: `_backend_config_path(phase)`, `_init_args(phase)`,
  `terraform_commands(phase, arg_lists, working_directory)`. Duck-typed; keep pyright happy
  with the `if TYPE_CHECKING: _Base = BuilderBase[Any] else: _Base = object` idiom.
  **Adopt it in the two okta builders only** — `tf_storage_builder.py`/`tf_instance_builder.py`
  have uncommitted working-tree edits.
- **Set `sensitive=True`** on the credential variables. `TerraformVariable.sensitive` already
  exists and is honored; the group model just never set it.

**Explicitly deferred as scope creep:** generalizing `render_block`'s hard-coded two labels
([blocks.py:114-115](packages/hashicorp-utils/src/cs_image_system/hashicorp_utils/blocks.py#L114-L115))
to single-label kinds, and an `OutputSpec`. Decision 4 removes the only reason this change
would need `output` blocks. When it *is* needed: add `labels: list[str] | None` to `BlockSpec`
and default it to today's two-label form.

#### 2. `email_as_username` + required names — the R1 fix (base + config)

**The flag.** Add `email_as_username: bool = True` to `UserBuilderModel`
([user_builder.py](packages/base/src/cs_image_system/base/models/user_builder.py)), beside
the existing `default_user_email_template`, plus a matching accessor property on
`UserBuilderBase` mirroring `default_user_email_template`
([builder_base_user.py:22-26](packages/base/src/cs_image_system/base/basic/builder_base_user.py#L22-L26)).
Generic to all user builders, not okta-specific.

**Enforcement** in `UserBuilderBase.add_user_to_builder` — the only place holding both the
builder (the flag) and the user, and it runs after template resolution, so `user.email` is
already expanded (`_read_item_kind` order is structure → resolve templates → register →
resolve builder → attach):

```python
if self.email_as_username:
    if not user.name:
        user.name = user.email
    elif user.name != user.email:
        raise ValueError(
            f"Builder {self.name} sets email_as_username, but user name "
            f"{user.name!r} != email {user.email!r}"
        )
```

**The email template would double-append**, and must be fixed in the same commit.
`default_user_email_template: "{{ user.name }}@noaa.gov"` with `name =
"avery.alpha@example.invalid"` yields `avery.alpha@example.invalid@example.invalid`. The template must become the
identity `"{{ user.name }}"` when `email_as_username` is true (or emails must be given
explicitly per user).

**Required `first_name`/`last_name`, and delete `split_name()`** (decision 9 — **already
implemented**, ahead of the rest of this step). It is what makes `email_as_username` safe
rather than merely tolerable:

- `split_name()` ([user.py:104-114](packages/base/src/cs_image_system/base/models/user.py#L104-L114))
  splits the whole `name` on `.`, so an email-shaped name gives `first_name="avery"`,
  `last_name="alpha@example invalid"` — verified by running it. That value would land directly in
  `okta_user.last_name`. It has a second latent bug independent of this change:
  `" ".join(parts[1:])` turns `p.mac.cready` into `last_name="mac cready"`.
- Both fields have **zero readers** anywhere in the repo outside `user.py` — not even
  `as_profile()`, which omits them. So `split_name()`'s only load-bearing effect today is its
  `raise ValueError` when `name` contains neither `.` nor `_`; it is a **validator wearing a
  parser's costume**. Deleting it legalizes `name: jdoe`. If that check is still wanted, keep
  it as an explicit one-liner in `__post_init__`, decoupled from first/last.
- Blast radius is config-only: there are **no** `User(...)` constructions in any source or
  test file — users come only from YAML. So this is `user.py` plus two added lines per user
  entry in `groups/users.yaml` (11 active entries; the two that already carry `first_name`
  are commented out). Zero test churn. It *is* a breaking change for any config outside
  this repo.
- Payoff: `okta_user` requires both fields, so step 5 gets them guaranteed by construction
  instead of depending on a parser that can raise or produce garbage. Under
  `email_as_username` the `name` is an email anyway, so deriving a human name from it was
  becoming semantically wrong.

**Config migration** (all in `test_folder/`, since name is now the login):
`groups/users.yaml` names become full emails (explicit `first_name`/`last_name` are **already
in place** from decision 9); every `groups/*.yaml` `members:`/`admins:` list becomes emails
(`_validate_groups` asserts each member matches a defined user); and `cfg/group-builders.yml`
drops the `@noaa.gov` suffix from both email templates.

**Where the check actually has teeth.** With the template reduced to the identity
`{{ user.name }}`, email is *derived from* name for the 9 users who declare no email, so the
comparison is vacuous for them. It bites exactly the 3 users in `groups/users.yaml` who
declare an off-domain email — `blake.bravo` / `Blake.Bravo@example.com`,
`i.india` / `i.india@example.com`, `kendall.kilo` / `kendall.kilo@example.com` —
each of which currently has `name != email` and would abort until its `name:` is migrated to
the full email. That is the intended behavior, and those three are the real content of the
migration.

**Make the comparison case-insensitive.** `Blake.Bravo@example.com` is mixed case, so a
literal `!=` would force the migrated `name:` to reproduce that casing exactly or abort.
Okta logins are case-insensitive; compare casefolded and it stops being a trap. Note the
generated Terraform label is unaffected either way, since `ssn()` lowercases.

**One caveat on the blank-name branch: it is unreachable, and deleting `split_name()` does
not change that.** `RootItem.__post_init__`
([root_item.py:28-29](packages/base/src/cs_image_system/base/models/root_item.py#L28-L29))
raises when `name in OOPS_DEFAULTS`, and that list is `[DEFAULT, None, "", SELF]` — so a blank
name dies before any builder sees the user, independently of the parser. Implement the branch
as specified for defensiveness, but making it actually live requires moving the coercion ahead
of that `RootItem` check.

*Cheaper alternative, if the config migration is unwelcome:* compare `user.name` to the
email's local part (`email.split("@")[0]`) instead of the whole email. Every existing config
keeps working untouched and the OPA username still provably derives from the Okta login —
but the two strings are no longer literally identical, which is weaker than what decision 7
asks for.

#### 3. Instance-level `local_users` — the R4 fix (base)

`local_users` is a **class**-level mutable list on `UserBuilderBase`
([builder_base_user.py:13](packages/base/src/cs_image_system/base/basic/builder_base_user.py#L13)),
and `local_users` + `local_groups` likewise on `GroupBuilderBase`
([builder_base_group.py:13-14](packages/base/src/cs_image_system/base/basic/builder_base_group.py#L13-L14)).
`self.local_users.append(...)` mutates the class attribute, so every instance of a given base
shares one list. With one user builder this is invisible; with two, both roots emit **all**
users, producing duplicate `okta_user` resources in two state files fighting over the same
Okta identities.

Fix: allocate per instance in `__init__` (calling `super().__init__(model)` first), following
the `TofuInstanceBuilder.__init__` precedent
([tf_instance_builder.py:32-34](packages/tf-ebs-instance-plugin/src/cs_image_system/tf_ebs_instance_plugin/tf_instance_builder.py#L32-L34)).
Keep the class-level annotation for typing, drop the shared default.

Do this **before** step 7 — the new builder tests otherwise need the leak-workaround fixture,
and this removes the need for it.

#### 4. New `okta_tf_workspace.py` — `OktaTfWorkspaceModelMixin`

Hoists the group model's Terraform wiring so the user model doesn't duplicate it. Moves
**verbatim** out of `okta_opa_tf_models.py`: `register_hcl_requirements` (:35-60),
`transform_provider` (:62-80), `finalize` (:82-105), `required_providers` +
`state_configuration` (:25-29); plus `org`/`team`/`key`/`secret`/`api_host` out of
`OktaGroupBuilderModel` and `org`/`team` out of `OktaUserBuilderModel`.

New fields: `okta_base_url: str = "okta.com"`, `default_user_status: str = "STAGED"`.
Reuse `org` for the okta provider's `org_name` rather than adding a field.
**No `api_token` field and no `TF_VAR_<team>_api_token` variable** — okta credentials are
OAuth private-key JWT read by the provider directly from `OKTA_API_*` environment variables
(see the credentials runbook below). Nothing secret enters HCL, and the user root declares
**zero** terraform variables (skip writing an empty vars file).

New methods: `provider_names()` (tolerant of dict-or-dataclass entries),
`provider_variables(provider)` (oktapam → `<team>_key`/`_secret`, `sensitive=True`;
okta → **none**), `transform_provider` dispatching on `provider.name`
(okta → `org_name` + `base_url`, merged under YAML-declared `config:` keys),
`_require_tfvar(suffix, ...)` (oktapam only).

**Start the okta provider's config from the YAML-declared `config:`** and only fill in
defaults for keys the YAML omits — so anything the provider supports in HCL (`client_id`,
`scopes`, `private_key_id`, …) is expressible in `group-builders.yml` without code changes.

`finalize()` asserts credentials **per configured provider**: the group builder keeps
demanding the oktapam `TF_VAR` pair; for okta it only **warns** when neither
`OKTA_API_PRIVATE_KEY` nor `OKTA_API_TOKEN` is exported, and the builder then omits `plan`
from its command list (`fmt`/`init`/`validate` still run). Exporting the credentials enables
`plan` with no code change — this is the adopted R2 behavior. Mixin goes **first** in the
bases so its `finalize()` precedes `BuilderModel.finalize()` in the MRO; everything is
`kw_only=True` so the diamond has no field-ordering problem. Both concrete models shrink to
`type`, `csis_name`, `csis_classifier`.

*Fallback if the dataclass/cattrs interaction misbehaves:* make the mixin behavior-only (no
fields) and re-declare the credential fields on `OktaUserBuilderModel`.

#### 5. Rewrite `OktaTFUser` ([okta_tf_models.py:37-86](packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/okta_tf_models.py#L37-L86))

**Replace** the commented `oktapam_user` output rather than keeping both — one identity should
not have two contradictory representations in the generated root. Move the
"does not function" note into the class docstring, along with the `public_keys` note from
decision 8.

- `get_resource_name()` → `okta_user.<label>`; `label = ssn(user.name)`.
- Args in order: `provider` (Raw) → `first_name`, `last_name`, `login`, `email` → `status`
  → each set optional from a `_OKTA_USER_OPTIONAL_ATTRS` tuple whose entries are
  simultaneously valid `okta_user` argument names and `User` field names. Emit only truthy
  values; read with `getattr(user, a, None)` so `SimpleNamespace` test stubs keep working.
- `first_name`/`last_name` are guaranteed present because step 2 made them required fields.
- `custom_profile_attributes` **off by default** (needs `jsonencode(...)` and org schema
  changes); gate behind a model flag.
- Data variant: `DataSpec("okta_user", label)` + `spec.block("search", name="profile.login",
  value=login, comparison="eq")` + `depends_on`. There is no top-level `login` argument.

#### 6. Fix `gen_users.py` (base)

[gen_users.py](packages/base/src/cs_image_system/base/commands/gen_users.py) is wired into the
lifecycle (`LIFECYCLE_FUNCTIONS` derives the name; `commands/__init__.py` exports it) but
`predefined_user_generation` just logs a warning, and the orphaned `generate_users` is broken
independent of this feature — it collects assets into a discarded local list, never calls
`sort_and_write()`, and never executes its `build_executables`.

Mirror `gen_groups.py` exactly: iterate `ctx.user_builders` (property confirmed at
[global_context.py:300](packages/base/src/cs_image_system/base/global_context.py#L300)) in
sorted order → `generate_items_during` → `sort_and_write()` → `get_commands_to_run_during`
→ `extend_finalization_phase` → execute. Align the parameter order with
`generate_groups(phase, gbb)`. Drop the stale "short-circuited" comment at
[lifecycle.py:57-59](packages/base/src/cs_image_system/base/lifecycle.py#L57-L59).
Nothing asserts on the removed warning.

#### 7. Implement `OktaTfUserBuilder` + remove group dead code

Five distinct artifact paths — **required**, because `sort_and_write` uses
`mode = 'w' if exists else 'a'` ([asset.py:201](packages/base/src/cs_image_system/base/basic/asset.py#L201)),
so a second write to one path truncates:

| Content | Suffix / discriminator |
| --- | --- |
| `terraform{}` + providers + `provider "okta"` | `.tf` |
| variables — **none for the user root** (creds are env-side); write the vars file only if the collector returns any | `-<safe_name>-vars.tf` |
| backend partial config | `.tfbackend.hcl` |
| `resource "okta_user"` × N | `USERS`, `.tf` |
| `data "okta_user"` × N | `USERS`, `-data.tf` |

- `generate_items_before(USER_GENERATION)` — scaffolding; guard on
  `phase != USER_GENERATION or not self._users()`.
- `generate_items_during(USER_GENERATION)` — per-user resource + data files (needs step 6).
- `get_commands_to_run_after(USER_GENERATION)` — `fmt`/`init`/`validate`/`plan` via
  `terraform_commands`, skipped entirely when there are no users so tofu never runs against
  an unwritten directory.
- Add the `model` property override mirroring the group builder so pyright sees the concrete
  type; add `_users()` returning **sorted** users (`sort_and_write` does *not* sort — insertion
  order is file order).
- Keep `query_existing_users()` as the documented seam for lookup-only users.

**Delete in `OktaTfGroupBuilder`:** the commented user sketch (:51-66), the dead user loop
(:115-132), and collapse the two consecutive `if phase == GROUP_GENERATION` blocks. `USERS`,
`User` and `OktaTFUser` stay imported (the user builder in the same module uses them) — confirm
with `ruff check`, not by eye.

*No-base-changes fallback:* put all five files in `generate_items_before` and skip step 6
entirely. One hook, one `AssetSet`, five distinct paths, no truncation.

#### 8. Config — `test_folder/cfg/group-builders.yml`

The `user_builders` entry swaps `oktapam` for `name: okta`, `source: okta/okta`.
`state_configuration` omitted → default backend → `okta_tf_users.tfstate`, distinct from
`oktagroups.tfstate`. **Verify the version constraint against the registry** —
`assert_satisfiable` validates intersection satisfiability, not that a downloadable version exists.
The email-template and users/groups changes from step 2 land here too.

### Okta management-API credentials — operator runbook (resolves R2 + R5)

The root-level Okta service (user creation) authenticates with an **API Services app
integration** using OAuth 2.0 client-credentials with a **private-key JWT** — not an SSWS
admin token, and not a client secret. The deciding constraint: the `okta/okta` terraform
provider's auth arguments are `api_token` (SSWS), or `client_id` + `scopes` + `private_key`
/`private_key_id` (OAuth), or `access_token`. **There is no `client_secret` argument**, so
the integration's Client ID + Client Secret pair cannot be consumed by Terraform as-is.

Console steps, on the existing API Services app integration:

1. **Client authentication → switch to "Public key / Private key".** Add a key and paste the
   contents of `.public_key.json` (the public JWK; its `kid` is
   `U_qr_L4zUeQT09rkTP31s4uHvp2l0yySsbOmx8jU_94`). The Client Secret becomes unused.
   The private key never enters the Okta console.
2. **Proof of possession → turn OFF "Require DPoP header in token requests".** Verified
   against the provider's docs (master): the okta/okta provider has **no DPoP support** —
   with the requirement on, every token request fails. If org policy mandates DPoP for API
   integrations, that policy and this provider are currently incompatible.
3. **Grant type: leave "Client acting on behalf of itself" (client credentials) ON.**
   That is the flow the provider uses. Leave **Token Exchange OFF** — not needed.
4. **Okta API Scopes tab → grant `okta.users.manage`** (add `okta.users.read` for
   completeness; manage includes read). If groups ever move to this provider, that's
   `okta.groups.manage`, later.
5. **Assign an admin role to the integration** (Security → Administrators → add the app, or
   the app's "Admin roles" tab). Scopes alone are not sufficient — Okta requires API service
   integrations to hold an admin role for management-API calls, or every request 403s.
   Least-privilege: a custom role with user create/manage; expedient: Super Administrator.
6. **Local environment** (the provider reads these natively; nothing goes into HCL or
   `TF_VAR`s):

   ```bash
   export OKTA_API_CLIENT_ID='<Client ID from the app page>'
   export OKTA_API_SCOPES='okta.users.manage'   # historical; now 'okta.users.read okta.groups.read' (2026-08-27)
   export OKTA_API_PRIVATE_KEY="$(cat .private_key.pem)"
   export OKTA_API_PRIVATE_KEY_ID='U_qr_L4zUeQT09rkTP31s4uHvp2l0yySsbOmx8jU_94'
   ```

   `org_name` (`noaa`) and `base_url` (`okta.com`) are emitted in the generated provider
   block, so they need no env vars. `.envrc` is already gitignored if you prefer direnv.
7. **Key hygiene.** `.private_key.pem` / `.private_key.json` / `.public_key.json` are now
   gitignored (they were previously unignored at the repo root — a `git add -A` would have
   staged the private key). They are untracked, so nothing needs history scrubbing. Since
   the key material has been handled outside a secrets manager, plan to **rotate it** once
   the integration works: generate a fresh pair, add the new public JWK, remove the old kid.

Sufficiency check: Client ID (public identifier) + private key + kid + granted scopes +
admin role is the complete credential set. The Client Secret is not needed and can be
deleted once the key-based auth is confirmed.

Provider-doc facts verified (okta/terraform-provider-okta, master docs): auth arguments are
exactly `api_token` / `access_token` / `client_id` / `scopes` / `private_key` /
`private_key_id` — no `client_secret`, no DPoP; `api_token` is mutually exclusive with the
OAuth set; private key must be PKCS#1 or PKCS#8 **unencrypted** (`.private_key.pem` here is
PKCS#8 unencrypted — compatible as-is).

### Tests

New: `test_user_resource_emitter.py` (real `User` objects work with no global context),
`test_user_builder_root.py` (group assets by path; assert the exact path set, `provider =
okta.okta_tf_users` on every block, `sensitive = true`, no `oktapam`),
`test_okta_workspace_mixin.py` (provider dispatch, per-provider credential asserts),
`test_roots.py`, plus base tests for `email_as_username` (all three branches, including the
casefolded comparison). Required-name enforcement is **already pinned** by
`packages/base/tests/test_user_required_names.py` (construction, structuring, blank rejection,
and the email-shaped-name regression).

After step 3, tests no longer need a `local_users` reset fixture — but add one assertion that
two user-builder instances keep **separate** lists, so the class-attribute bug cannot return.

Breaks: **`test_resource_emitters.py:24-30` `test_user_emits_commented_resource` — delete it**
(it pins the exact replaced behavior). `test_group_module_call.py` should pass untouched.

### Verification

1. `just verify` — 189 existing + ~20 new; no pre-existing test changes status but the one deletion.
2. Export `TF_VAR_<team>_key`, `_secret` (oktapam) and the `OKTA_API_*` variables from the
   credentials runbook below, then `uv run cs-image-system --root-dir test_folder generate`.
3. Expect 5 files in `okta-tf-users/user-generation/` and one `okta_user` block per user.
4. Confirm every `login`/`email`/`name` triple is the same string, and that `last_name`
   contains no `@` — the regression `split_name()` used to cause.
5. `tofu fmt -check .` (**not** plain `fmt` — proves the emitters produce canonical HCL),
   then `init -backend-config=...` and `validate`.
6. `tofu plan` **against a throwaway/preview Okta org first.**
7. **Snapshot `test_folder/generated/oktagroups/` before regenerating** (it's untracked) and
   diff after: expected deltas are `sensitive = true` on two variables and emails replacing
   bare names in every module call's `members`/`admins`. Anything else means the mixin
   refactor changed group behavior.

### Resolved risks

- **R1 login vs OPA username — resolved** by decision 7 / step 2. Forcing `name == email`
  makes the group module's `username` and the Okta login the same string by construction.
- **R2 missing credentials — resolved** by the env-var design in step 4 plus the runbook
  above: okta credentials never appear in HCL or `TF_VAR`s; when `OKTA_API_PRIVATE_KEY` /
  `OKTA_API_TOKEN` are absent, `finalize()` warns and the user root runs
  `fmt`/`init`/`validate` but skips `plan`. Exporting the credentials enables `plan` with
  no code or config change.
- **R4 shared `local_users` — resolved** by step 3.
- **R5 auth mode — resolved**: OAuth 2.0 client-credentials with private-key JWT, per the
  runbook. SSWS remains available as a fallback (`OKTA_API_TOKEN`), and any provider auth
  argument is expressible via the YAML `config:` passthrough in step 4.

### Open risks

- **DPoP** (from the runbook, step 2): the okta/okta provider has no DPoP support (verified
  against its docs), so the integration's DPoP requirement must stay off. If org policy
  mandates DPoP for API integrations, that policy and this provider are incompatible until
  the provider adds support.

### R6 explained: why `User.as_profile()` must not feed `okta_user`

`as_profile()` ([user.py:116-173](packages/base/src/cs_image_system/base/models/user.py#L116-L173))
builds the **Okta REST API** request body — the JSON you would `POST /api/v1/users` if you
called Okta directly with no Terraform involved. The comment block right below it
([user.py:176-185](packages/base/src/cs_image_system/base/models/user.py#L176-L185)) shows
exactly that shape, nested under a `"profile"` key.

The Terraform `okta_user` **resource** is a different serialization of the same data, one
layer up: flat, snake_case HCL *arguments*, which the provider itself translates into that
API call. So the two are not interchangeable:

| Same datum | `as_profile()` (API wire) | `okta_user` (HCL argument) |
| --- | --- | --- |
| mobile phone | `mobilePhone` | `mobile_phone` |
| zip | `zipCode` | `zip_code` |
| cost center | `costCenter` | `cost_center` |
| manager | `managerId` | `manager_id` |

The trap is that `as_profile()` looks *perfectly* reusable — it lives on the `User` model, it
has "profile" in the name, and it produces almost exactly the field set `okta_user` wants. The
natural move when implementing step 5 is to reach for it. But passing it into `ResourceSpec`
emits `mobilePhone = "..."` where Terraform requires `mobile_phone`, and Terraform rejects
unrecognized arguments — so you get ~25 "Unsupported argument" errors at `validate`, not a
silent mismatch.

Two further ways it is wrong for this use, beyond key casing:

- It sets **`login = self.name`** ([user.py:119](packages/base/src/cs_image_system/base/models/user.py#L119)),
  whereas decision 6 sets `login = email`. (Under decision 7 these coincide — but the
  disagreement is baked into a function that does not know about the flag.)
- It **omits `firstName`/`lastName`**, which `okta_user` *requires* — even though its own
  comment block lists them as belonging in the body.

So it is simultaneously the wrong key style, the wrong `login` value, and missing the two
mandatory fields. And it has **zero callers repo-wide**, so nothing exercises it and nothing
would catch the drift.

The action is deliberately *not* deletion — it is plausibly intended for a future
direct-API path such as filling in `query_existing_users()`. Instead, annotate its docstring:
"Okta REST API wire shape (camelCase, for `POST /api/v1/users`) — **not** the terraform
`okta_user` resource argument shape." The earlier instinct to "fix" it by adding
`firstName`/`lastName` is the actively harmful move: it makes the function look even more
like the resource shape while still being unusable for it.

---

## Execution worksheet archive (TODO.md stages 1–18, 20–28, 31–36, 38 and 39)

*Formerly §6 of the document that became [docs/DESIGN.md](docs/DESIGN.md) (moved here 2026-09-10, content unchanged). References of the form "stage N", and old ones of the form "V2_PLAN §6.N", mean stage N below. Each stage is kept verbatim as it left the worksheet: its landed summary, its decisions, its original plan or candidate list.*

`TODO.md` was reset to its opening paragraph on 2026-09-09 after every
stage it carried had landed (stages 1–11, 2026-09-04 → 2026-09-09). Each
stage is kept here verbatim — its landed summary, its decisions, its
original plan or candidate list — so that references elsewhere of the
form "stage N" / "stage N.M" mean §6.N / §6.N item M of this file. The
stage that was current when the worksheet closed:

Current stage: **§§1–11 DONE (2026-09-08)** — the GCE cost cycle is a
declaration (`ephemeral: true` on gce-test and on the gcloud-east1
runtime; storages persist as long as declared), the recipes are generic
(`just cloud-cycle <runtime>` = one `run --all` + `cloud-empty`), and
§11 items 1–6 are proven live. **Open, none started**: §11 item 7
(Okta/ASA on GCE, lowest priority by the operator's decision), the
§12 candidates listed at the end of §11, and one informational readiness box
(egress, unmeasured). Steps marked **⚠️ USER** require operator
intervention — decisions or console/IAM actions the system must not take
itself.

Decisions recorded 2026-09-04 (user): **AlmaLinux 10 replaces RHEL**
for the GCE chain (closes the §9 license blocker — no license premium,
the e2-micro launch becomes genuinely free-tier); the existing GCE
RHEL builds are to be removed and rebuilt on Alma if needed.
Version-parity differences with the other chains (the AWS rhel-8
line) are **deliberately ignored** — the user expects to migrate
those forward later. Scope note: removal reads conservatively as the
**two GCE images only** — the AWS RHEL chain from stage 1 is
untouched until the user says otherwise.

### 1. Switch the GCE chain to AlmaLinux 10 — DONE 2026-09-04

**Landed on feature/gce-alma-10** (squash-merged; PLAN.md entry +
findings 42–46 in [docs/LEDGER.md](docs/LEDGER.md)). Live chain:
`basic-rh-10-gcloud-east1-20260904-105520` →
`imgfile-basic-dask-pckr-gce-ans-20260904-111543`; RHEL images
destroyed and disposal-recorded; dual-cloud state query zero image
drift; `just verify` 412 green. The leftover decision (disposal of the
superseded intermediates `...-103257` and `...-110544`) was authorized
and done under §3 on 2026-09-05. Original plan follows for reference:

1. **Point the GCE os-builder at Alma 10 vendor images**: in
   [test_folder/cfg/runtime-builders.yml](test_folder/cfg/runtime-builders.yml),
   replace the RHEL source for the `gcloud-east1` runtime with
   `source_image_family: almalinux-10` /
   `source_image_project: almalinux-cloud`. First confirm the family
   name and architecture with
   `gcloud compute images list --project almalinux-cloud --filter="family~almalinux-10" --format="table(name,family,architecture)"`
   — the finding-39 lesson applies: Alma publishes an aarch64 line
   too, and the family pinned must be the x86_64 one.
2. **Naming — DECIDED (user, 2026-09-04): the series renames to
   `basic-rh-10`** — `rh-10` denotes "Red Hat-family, EL10" without
   naming a distro, so the same series name survives an Alma ⇄ Rocky
   ⇄ RHEL source swap. The name is lineage — the GCE image family,
   the meta-state series, and the parent pin
   (`imgfile-basic-dask@gcloud-east1`) all at once — so the rename
   touches config, pins, fixture, and tests together.
3. Verify the in-bake `tests:` (per-runtime overridable since finding
   40) hold on Alma 10 — a bigger jump than a rebadged RHEL 8: EL10
   moves python, dnf, and kernel majors, so confirm every emitted
   assertion (and the ansible mods' package names) against an EL10
   userland, don't assume.
4. Re-run the free proof: `just verify` green, dry-run `run --all`,
   `packer validate` clean for the Alma base + dask blocks. (Fold in
   the already-failing stale assertion at
   [tests/test_v2_explore_gcp.py:148](tests/test_v2_explore_gcp.py#L148),
   which still expects `e2-micro` for the dask bake that finding 41
   moved to `e2-medium`.)
5. Re-bake on GCE, one lifecycle at a time (the 2026-09-03 shape):
   Alma base image, then the dask instance image; dual-cloud
   `state query` **no drift**. **Pin gotcha (verified in
   [lineage.py:162](packages/base/src/cs_image_system/base/lineage.py#L162)):**
   the standing parent pin `imgfile-basic-dask@gcloud-east1` still
   points at the RHEL base and WINS over "parent built this run" — a
   naive re-bake would bake dask from the old RHEL image. Between the
   base bake and the dask bake, move the pin explicitly (N17):
   `upgrade image imgfile-basic-dask --to <new basic-rh-10 build id> --runtime gcloud-east1`.
6. **Remove the two RHEL GCE images** —
   `basic-rhel-8-gcloud-east1-20260903-112019` and
   `imgfile-basic-dask-pckr-gce-ans-20260903-134635` (~$0.58/month
   combined while they live). They are **meta-state-recorded**, so an
   out-of-band `gcloud compute images delete` would manufacture
   drift: first check what disposal path the system offers for
   recorded images (GOALS.md disposal semantics); if none exists, record
   the disposal transition explicitly and note the gap as a finding.
   **Deletion AUTHORIZED (user, 2026-09-04)** — destructive and
   irreversible (rebuild = re-bake cost only); executes at this point
   in the sequence, through the recorded path above.
7. All of the above on a feature branch per git-flow, squash-merged,
   branch kept.

### 2. IAP access: full command set — DONE 2026-09-05

**No — the firewall rule alone is not sufficient.** Three legs, all
free: the network path (firewall), the identity grant (IAM), and the
tunnel itself. The IAP API is already enabled (§2 of the readiness
file, 2026-09-02). Note the tunnel authenticates as **your gcloud user
account**, not the impersonated csis-runner ADC — the ADC
impersonation matters for terraform/packer, not for `gcloud compute
ssh`.

1. **DONE (user, 2026-09-04; verified via gcloud)** — firewall rule
   `allow-iap-ssh` exists on the `default` network (once per network;
   the §1.2 example was correct and complete for this leg):

   ```sh
   gcloud compute firewall-rules create allow-iap-ssh \
     --project csis-sandbox --network default --direction INGRESS \
     --action ALLOW --rules tcp:22 --source-ranges 35.235.240.0/20
   ```

2. **DONE (user, 2026-09-04; verified via gcloud)** — IAM binding
   `user:mykel.alvis@gmail.com` holds
   `roles/iap.tunnelResourceAccessor` on csis-sandbox (the operator's
   Google email for future grants is `mykel.alvis@gmail.com`):

   ```sh
   gcloud projects add-iam-policy-binding csis-sandbox \
     --member="user:YOUR_GOOGLE_EMAIL" \
     --role="roles/iap.tunnelResourceAccessor"
   ```

   Console equivalent: IAM & Admin → IAM → **Grant access** → your
   Google email → role **"IAP-secured Tunnel User"** → Save. Verify:
   `gcloud projects get-iam-policy csis-sandbox --flatten="bindings[].members" --filter="bindings.role:iap.tunnelResourceAccessor" --format="value(bindings.members)"`.

3. **DONE (user, 2026-09-05)** — session proven under §3. Shell in
   (after the instance exists, section 3):

   ```sh
   gcloud compute ssh INSTANCE_NAME \
     --project csis-sandbox --zone us-east1-b --tunnel-through-iap
   ```

   First run generates `~/.ssh/google_compute_engine` and pushes the
   key via instance metadata automatically; no external IP is needed
   or wanted. If it hangs, `gcloud compute start-iap-tunnel
   INSTANCE_NAME 22 --local-host-port=localhost:2222 --project
   csis-sandbox --zone us-east1-b` isolates the tunnel leg from the
   SSH leg.

4. **DONE 2026-09-05** — documented as operator prerequisites in
   [docs/OPERATIONS.md](docs/OPERATIONS.md) "IAP sessions on GCE"
   (the SSM-instance-profile analogue); readiness §5 bullet ticked.

### 3. Launch the instance and prove the IAP session path — DONE 2026-09-05

**Landed on feature/gce-launch-proof** (squash-merged; PLAN.md entry,
ledger findings 47–51). gce-test launched through the full gate chain
(e2-micro, no external IP); **IAP session proven by the operator**
(`id` → `uid=1002(avery.alpha)` in `google-sudoers`, AlmaLinux 10.2,
guest agent + sftd active). Two fixes found live and landed
(47 google-sudoers finalize step, 48 ansible provisioner user); three
gaps logged, not fixed (49 silent instance-pin move / state-query
blind to booted image; 50 `gce_data` attached but NOT mounted at
`/mnt/gce-data`; 51 boot disk inherits the image's 200 GB → ≈ $8/month
of pd-standard while the instance exists). Also done here: the two
superseded Alma intermediates disposed, and `tcmet` reconciled into the
identity read-model (full "no drift" report restored). Original plan
for reference:

1. Refresh both credential legs in one environment:
   `aws sso login --profile noaa` (S3 state backend) **and**
   `gcloud auth application-default login --impersonate-service-account=csis-runner@csis-sandbox.iam.gserviceaccount.com`.
2. Pre-flight: `state query` clean (dual-cloud, no drift), then a full
   dry run; read `generated/final_execution.sh` end to end and price
   every deferred command against §§3 and 6 of
   [GCP-READINESS.md](docs/history/GCP-READINESS.md) — the still-open §8 item —
   **before** any `--no-dry-run`.
3. Flip **only** the instance-lifecycle apply flag (all others off);
   scope the run so nothing re-bakes (the scoped-runs selector).
   Confirm `default_machine_type: e2-micro` for the launch; the
   documented fallback is `e2-small` / the finding-41 chain — never a
   silent upsize.
4. Apply through the full gate chain (plan → gate → apply-check →
   apply): the `gce-test` instance, e2-micro, **no external IP**.
5. **⚠️ USER — prove the session end to end** with the §2.3 command.
   This doubles as the live 1 GB validation (the AWS lesson: a 1 GB
   t2.micro couldn't keep the SSM agent alive) — if the guest/IAP
   path dies on 1 GB, fall back per step 3 and record it as a
   finding.
6. Post-apply `state query`: transitions recorded, **no drift**, no
   `foreign` resources.

### 4. Capture evidence, tear down, record findings — DONE 2026-09-07

The stage-1 close-out shape ([GCP-READINESS.md §9–10](docs/history/GCP-READINESS.md)).

1. Evidence captured 2026-09-05: state query "no drift" with the
   launched instance recorded (run 2026_09_05t06_53_10); the operator's
   IAP session transcript (in the ledger, finding 47 entry). **Billing
   is NOT ≈ $0 while gce-test exists**: 230 GB pd-standard (200 GB boot
   inherited from the image + 30 GB `gce_data`) ≈ $8/month (finding 51),
   plus three stored images ≈ $0.9/month; compute is free-tier.
2. **DONE 2026-09-05 (authorized)** — gce-test destroyed through the
   gate (transient undeclare → plan "1 to destroy" → whitelisted gate →
   apply-check → apply; 200 GB boot disk gone with it; `gce-data` and
   `gce_bucket` kept, the stage-1 shape; declarations restored
   afterwards, dormant, flag off). Two gaps found and fixed on the way
   (ledger 52–53): the last instance on a runtime could never plan its
   own destroy, and a dry run forgot the record before any destroy ran.
   Post-teardown state query: "no drift". GCP now bills only image
   storage (3 images ≈ $0.9/month) + the free-tier 30 GB pd.
3. **DONE 2026-09-05 (authorized)** — orphan sweep: the superseded
   pre-fix dask image `...111543` deleted with its lineage record removed
   in the same commit (finding-46 shape); state query "no drift"; GCE
   holds exactly the live chain (`basic-rh-10-...105520` →
   `imgfile-basic-dask-...045403`). The finding-36 AWS AMIs
   (`ami-00df8ec808cb7576b`, `ami-0efa14466de7fa459`) and their
   snapshots were verified **already gone** from us-east-2 (nothing in
   the account references those ids); no deletion was needed.
4. **DONE 2026-09-07** — findings 42–54 are in [PLAN.md](PLAN.md) and
   the [docs/LEDGER.md](docs/LEDGER.md) ledger; the RHEL→Alma decision is
   noted in [GCP-READINESS.md §9](docs/history/GCP-READINESS.md), and every readiness
   box with recorded evidence is ticked (the boxes still open there are
   listed in §8 below).
5. **DONE 2026-09-05 (authorized)** — `default-allow-ssh` and
   `default-allow-rdp` deleted from csis-sandbox's `default` network;
   remaining rules: `allow-iap-ssh`, `default-allow-icmp`,
   `default-allow-internal`.
6. **DONE (user, 2026-09-07)** — §10 hygiene loop: the Apple Reminders
   from [BILLING_REMINDERS.md §3](BILLING_REMINDERS.md) are in place, the
   budget-alert emails are verified as arriving (the Google Chat
   notification is not useful and is ignored), and BILLING_REMINDERS.md
   is the operator's reference for cost queries. The trial-credit review
   was withdrawn on 2026-09-06 (the account has no credits).

### 5. Post-launch housekeeping — DONE 2026-09-05

**Landed on feature/post-launch-housekeeping** (squash-merged). In the
user's order: `test`/`test2` commented out of the live config (a
dormant declaration relaunches on the next apply) with the suite
keeping them as its AWS subjects through a test-only overlay
(`tests/fixtures/aws_test_instances.yaml`, applied by `copy_config`);
the two default-VPC ingress rules deleted; the identity run done — the
five live `tcmet` `oktapam_user_group_attachment` records imported
(`tofu import`, id shape `group|username`), plan "No changes", then the
gated run under a TEMP `apply_identity: true` (the key now exists in
`_config.yml`, off, like `apply_storage`): zero OPA writes, meta-state
commit 713ca39, state query "no drift". The `gce-test` question was
settled: commented out 2026-09-06 and confirmed test-only 2026-09-07
(§7).

### 7. DONE 2026-09-06 — per-root apply scoping

Decisions taken with §6 closed: **Okta/ASA on GCE** is targeted but is
now the LOWEST priority (substantial work: OPA enrollment on GCE, the
identity read-model, sftd on Alma 10); nothing done here removes what
it needs — `identity` stays a lifecycle, the identity root and its
read-model are untouched, GCE instances keep their Okta capability
declaration. **AWS EL10 migration** (basic-rhel-9 → the rh-10 series on
the AWS chain) is deferred. **develop** left as is.

Code on feature/per-root-apply-scoping. `config: apply_<lifecycle>`
accepts, besides `true`/`false`, a **list of root names and/or runtime
names**: only the listed terraform roots emit an apply (each guarded by
`apply-check --lifecycle <key> --root <name> --root-alias <runtime>`,
which re-reads the list at execution time); every other root of the
lifecycle still plans and gates. The after-apply hooks (storage
transitions, launched marks, decommission forgetting, the first bind
from the booted image) read the same rule per root, so a root that only
planned records nothing. Motivation: with both clouds declared, one
cloud could only be touched by undeclaring the other's instances
(finding 52 territory) or applying everything at once.

- **USER decision (2026-09-07)**: `test`, `test2` and `gce-test` are
  test-only fixtures; they stay commented out of the live
  `instances.yaml` (the operator may uncomment/re-comment them over
  time). The test harness keeps prepending them from
  `tests/fixtures/test_instances.yaml`.

### 6. DONE 2026-09-06 — the deferred GCE gaps (ledger 49–51, + 54)

Code on feature/gce-gaps-49-51 (squash-merged by a peer session as
4337d3e), live proof on feature/gce-gaps-proof (squash-merged). All
proven live with the operator's authorizations: **51** — the GCE bake
disk is now the vendor image's **10 GB floor** (user asked for 5; a boot
disk cannot be smaller than its source image), base
`basic-rh-10-gcloud-east1-20260906-033730` and dask
`imgfile-basic-dask-pckr-gce-ans-20260906-034343` re-baked, the 200 GB
pair disposed (finding-46 shape). **54** — those bakes ran through the
IAP tunnel after the runner service account received
`roles/iap.tunnelResourceAccessor` (packer had been reaching build VMs
over public tcp:22, which died with the §4.5 firewall hygiene).
**50** — gce-test launched through the gate on the 10 GB image; its
serial console showed the startup script finding
`/dev/disk/by-id/google-gce-data`, `mkfs.xfs` on the 30 GiB pd, and
"Finished running startup scripts" (the device-name mismatch was the
real cause, not a missing script). **49** — the pin was bound from the
booted image at launch and the state query's new booted-image
comparison reported "no drift" with the GCE probe answering. **47**
also proven at instance boot: the guest agent removed the stale
`packer` user cleanly and provisioned the operator's key. Torn down
through the gate (whitelisted destroy, "1 to destroy", record kept
through the dry run); post-teardown state query "no drift"; zero
instances, `gce-data` kept. Original plan for reference:

1. **51 — boot disk size**: instances inherit the image's 200 GB
   `disk_size` (≈ $8/month of pd-standard each). Decide: a smaller
   bake-time `disk_size` on the GCE runtime (the 200 GB was the RHEL
   vendor minimum carried forward — check Alma 10's minimum), and/or an
   instance-level boot-disk size on the `gce_instance` module.
2. **50 — `gce_data` never mounts**: the launch params already carry
   the mount (`/dev/disk/by-id/google-gce-data` → `/mnt/gce-data`);
   the GCE launch lacks the user-data mount realization the AWS path
   has (finding 28's by-id shape). Emit a startup-script from the same
   launch params.
3. **49 — pins and booted images**: (a) a re-bake's instance apply
   re-binds an already-launched instance's pin to the new series head
   without replacing it; (b) `state query` never compares an
   instance's booted image with its pin. Make (a) an explicit
   `upgrade instance` only, and add the booted-image comparison to the
   instance query.

### 8. DONE 2026-09-07 — GCE change-cycle cost discipline

**Built and proven live on feature/gce-cycle (2026-09-07; ledger
55–58).** The first `just gce-cycle` baked both GCE images, launched
gce-test through the gates under the launch overlay, verified it
without an operator session, and tore everything down: instance,
`gce-data`, the bucket and all four GCE images — **`gce-empty`: GCE
holds nothing csis created; meta-state agrees.** Operator decision
(58): no GCE resource is ever kept between cycles. Found live and
fixed on the branch: the guest agent's completion wording (56) and the
empty-bucket wipe (57); three transient upstream failures (55) cost
retries only. Per leg:

- **1 — the recipe**: `just gce-cycle` = `gce-preflight` (strict state
  query) → `gce-bake` (base bake → explicit pin move → dask bake) →
  `gce-launch` → `gce-verify` → `gce-teardown` (`gce-decommission` →
  `gce-teardown-storage` → `gce-dispose-images`) → `gce-empty`. Every
  leg takes `yes` as its first argument for a dry run. Only sanctioned
  commands underneath: the gated runs, the state query, the new
  disposal command, gcloud read-only listings.
- **2 — transient declarations**: global `--overlay <file>`
  (repeatable) merges a file over the tree for one invocation — `config:`
  keys override, named `instances:`/`storages:` entries update or add;
  recorded in the run journal; the generated `apply-check` re-reads the
  same overlay (a vanished overlay refuses). Files in
  `test_folder/overlays/` (never auto-loaded). `run --only none` is the
  explicit empty bake surface (replaces the valid-but-empty-selector
  hack).
- **3 — automatic verification**: `gce-verify` polls the serial console
  for `startup-script exit status 0` (the script runs under `set -e`:
  pd found by-id, formatted, mounted), then the strict state query
  (booted image vs pin, finding 49); `just gce-verify iap` adds a
  `findmnt`/`id` probe over the tunnel as the operator.
- **4 — sanctioned image disposal**: `dispose image <build-id>…` /
  `--runtime <rt> --all`: deletes the cloud image (runtime hook
  `dispose_image`, GCE implemented), drops the lineage record and any
  image pin at it (`op: dispose`), `--commit`. Refuses unrecorded builds
  (adopt with `state import` or leave to the orphan sweep — never delete
  blind), builds an instance is pinned to or launched from, runtimes
  that cannot dispose. Under the global `--dry-run` it reports the plan.
- **5 — storage teardown**: the storage-teardown overlay requests
  `gce_data`/`gce_bucket` `destroyed` (bucket wiped first by the plugin's
  transition action) with the GCE storage roots alone applying; runs
  after the instance is gone.
- **7 — added**: AWS `dispose_image` (deregister + snapshots) is not
  implemented — the command refuses AWS builds cleanly. Not needed for
  the GCE cycle; do it when an AWS cycle is wanted.
- **6 — readiness leftovers** (done with the cycle): spot build VMs —
  the GCE runtime's `bake_preemptible: true` makes packer's build VM
  preemptible (a killed bake re-runs; ≈ 60–90 % off bake minutes);
  GCS state-query parity — the bucket is now looked up through
  `gcloud storage buckets describe` (no new client library), so the
  query claims present/absent instead of staying silent; GCS class /
  versioning verified (regional `us-east1`, uniform access, versioning
  off, `force_destroy` false with the wipe in front); the prerequisite
  filter re-checked on the real bake (no AWS tooling in the Alma
  bake). Still open, informational only: the snapshot free allotment
  (nothing is archived) and egress (bakes download only).
- **8 — added (finding 55)**: `tofu init` re-fetches provider
  checksums from GitHub for every regenerated root. The Justfile now
  exports `TF_PLUGIN_CACHE_DIR` (repo-local, gitignored) so a provider
  downloaded once is reused; with a root's kept `.terraform.lock.hcl`
  the init is then offline-safe. Runs started outside `just` need the
  variable in their environment (documented).

Original proposal for reference:

Operator statement (2026-09-07): the AWS account is not the operator's
money; **GCP is paid personally** and must never carry running services
beyond the bare minimum. When a change is likely to affect the gcloud
side, the cycle is: build → verify it works → **delete every created
storage, instance and image**. Cleanup is tier-2 (below "make it
work") but its effects are long-lasting, so it gets a sanctioned path,
possibly an out-of-workflow `just` recipe. Nothing here is built yet;
what would satisfy it:

1. **A cycle recipe** (`just gce-cycle` or `just cloud-cycle gcloud-east1`)
   wrapping only sanctioned commands, in this order: pre-flight
   `state query` (must be "no drift"); bake the GCE chain scoped —
   `run base-image instance-image --only basic-rh-10@gcloud-east1
   --only imgfile-basic-dask@gcloud-east1 --no-dry-run`; a gated launch
   under `apply_instances: [gcloud-east1]` (per-root scoping, §7, is
   what makes the AWS root stay plan-only); a verification step; then
   the teardown below; finally a **"GCE is empty" assertion**:
   `gcloud compute instances list`, `images list --no-standard-images`
   and `disks list` all empty, `state query` no `foreign`, and the §2c
   billing query showing only image-storage tails.
2. **Transient instance declaration** without editing the live
   `instances.yaml`: the suite already prepends
   `tests/fixtures/test_instances.yaml` via `copy_config`; the recipe
   needs the same for a real run (an overlay flag such as
   `run --with-instances <file>`, or the recipe copying the config tree
   the way the tests do). Until then the recipe uncomments/re-comments
   `gce-test` — which the operator does by hand today.
3. **Verification that is automatic, not an operator SSH session**: the
   serial-console read (finding 50's evidence) and the booted-image /
   pd-mounted checks the state query already makes; an IAP probe from
   the runner service account is optional.
4. **Sanctioned image disposal as a command**: today a superseded image
   is deleted and its lineage record removed by hand in one commit
   (finding-46 shape, done four times). A `dispose image <build-id>`
   (or `decommission image`) command that deletes the cloud image and
   records the disposal in lineage/pins closes the last hand-edited
   step and is what the recipe calls for **every** GCE image at the end
   of a cycle (the operator wants images gone too, not just instances —
   a fresh cycle re-bakes from the vendor image, ≈ cents).
5. **Storage teardown through the existing transition**: `gce_data` and
   `gce_bucket` go to `state: destroyed` through the gated storage
   lifecycle (the tombstone/whitelist path exists); the recipe needs a
   way to request it transiently (same overlay mechanism as item 2) and
   the bucket must be empty or the wipe action must run first.
6. **Readiness boxes still open** (none block the recipe): spot/
   preemptible build VMs (§6 packer bakes — a real saving on bake days),
   snapshot free-allotment check, GCS class/versioning check, egress
   discipline (unmeasured), `state query` parity for GCS
   (`unavailable`), and the prerequisite-filtering re-check on the real
   config (no AWS tooling in the Alma bake — checkable from the last
   bake log).
7. **Cost of a full cycle** at today's rates: two bakes (≈ 10–15 min of
   e2-small/e2-medium ≈ $0.02–0.05), a short e2-micro launch (free
   tier), image storage for the hours the images exist (≈ $0.00x); the
   only recurring cost after cleanup is the three Network Intelligence
   Center lines that net to $0.

### 9. DONE 2026-09-08 — convergent bakes

**Built on feature/convergent-bakes and proven live 2026-09-08 (ledger
59–60).** From an empty GCE: pass 1 baked base + dask (plan: `no build …
yet`); pass 3 — the same run again over both lifecycles — emitted **no
bake surface at all** (`skip: current` for both, `no-script` for both
lifecycles); pass 4 — one comment appended to `setup_dask.yml` —
re-baked the dask image alone (`inputs changed`), the base `skip:
current`. Decisions in force: `--only` is a pure filter, `--force-bake`
forces; `image_policy: follow` on instances included; `stale` is
reported by `state query --strict` but does not fail it (a pin-policy
state, not reality drift — five AWS pins are stale today, ledger 59).
Found live: the plan-time base-image stand-in had to mirror the five
attributes the verify commands read from the object (ledger 59) —
pass 2 re-baked the base once for that; and **rule 58 collides with
N19 tombstone permanence** (ledger 60): with `gce_data`/`gce_bucket`
recorded `destroyed`, the live tree's `state: active` declarations are
refused as resurrections, so every run needs the storage-teardown
overlay until §10.6 lands. Original plan for reference:


**The gap** (operator's observation, 2026-09-07): a `--no-dry-run run`
re-bakes every image whose script exists. The system never decides
"this image is current, skip it", although lineage already records an
`input_fingerprint` per build for exactly that. Everything procedural
in §8 routes around this one gap: `--only` picks what bakes, the
explicit `upgrade image` between base and child bakes exists because
the child's pin still points at the old base, and superseded images
pile up. After §9 a second `run --all` on a converged tree bakes
nothing, and a changed base re-bakes its children in the same run by a
declared policy. The §8 cleanup recipes stay as they are (operator
decision 2026-09-07: they are fine); they become shorthand, not the
only way.

1. **Audit what `input_fingerprint` covers** —
   [lineage.py](packages/base/src/cs_image_system/base/lineage.py):
   it must include everything that changes the artifact: the OS
   builder's settings, the runtime's bake settings that end up in the
   image (disk size, source family), every mod's content hash, the
   in-bake `tests:`, and — decisive for parent tracking — the resolved
   **parent build id** (or `vendor:<resolved image name>` for a base:
   the vendor family moving is a real input change). Anything that is
   only execution detail (machine type, preemptible, IAP) stays out.
   Write the list into the docstring; a gate test pins it (a change to
   each listed input changes the fingerprint; a change to each excluded
   one does not).
2. **The bake decision, per image per runtime** — one function,
   `bake_reason(ctx, image, runtime) -> str | None`, consulted at the
   `get_images` choke point
   ([builder_base_image.py](packages/base/src/cs_image_system/base/basic/builder_base_image.py)),
   returning why the image bakes or `None` to skip. Bake when: (a) the
   series has no build on this runtime; (b) the series head's recorded
   fingerprint differs from the current one; (c) the parent policy
   (step 3) moved the parent; (d) the base image's update policy asks
   for a refresh (`effective_update_policy`: e.g. a max age — the
   fingerprint cannot see package updates); (e) the operator forced it.
   **DECIDED (user, 2026-09-07): `--only <image>` stays a pure
   filter; forcing is a separate `--force-bake <image>` (repeatable;
   with no name = every image in the run's surface).** `--only X` on a
   current image therefore bakes nothing and says so in the bake plan.
3. **Parent policy, declared** — on an instance image (per runtime
   override allowed): `parent_policy: pinned | follow`, default
   `pinned` (N17 unchanged). `follow`: when the parent series' head on
   that runtime is newer than the pin — built earlier in this run or by
   a previous one — the pin moves to the head automatically, recorded as
   `op: follow` in `pins.yaml` upgrades, and the child bakes from it;
   the explicit `upgrade image` remains for `pinned` images. This is the
   step that removes `gce-bake`'s manual pin move.
4. **The bake plan is visible and journaled** — every run (dry or not)
   prints one line per image/runtime: `bake` + reason, or `skip: current
   (build …)`; the run summary and `runs.yaml` carry it, so "why did
   this bake?" is always answerable after the fact.
5. **Instances after a re-bake** — unchanged by default (pins move only
   by `upgrade instance`, finding 49). Optional, same shape as step 3:
   `image_policy: pinned | follow` on an instance; `follow` plans the
   gated replacement when its image's head moves. **DECIDED (user,
   2026-09-07): included in §9** — the replacement is the existing
   `upgrade instance` path (pending replacement → whitelisted
   destroy/recreate), triggered by policy instead of by hand and logged
   as `op: follow`.
6. **State query** — a pinned child whose parent head has moved is
   already reportable; make sure it reads as `stale` (informational,
   never hard drift), and that a skipped-as-current image is not
   reported at all.
7. **Tests** (gate-style, cloud-free): a second run on a converged copy
   emits zero bake scripts; a changed mod re-bakes only the images that
   carry it; a changed base fingerprint re-bakes the base and, under
   `follow`, the child in the same run with the pin moved and logged;
   under `pinned`, the base alone with the child reported `stale`;
   `--only` forces a current image; the max-age policy triggers with a
   frozen clock. Golden fixture regenerated if emission changes.
8. **Live proof, cheapest form**: `just gce-cycle` with no changes to
   the config must bake nothing on its second pass (the first pass
   after §9 still bakes: no images exist on GCE by rule 58); then one
   mod change must re-bake the dask image only. Records: PLAN.md
   status, ledger entry, OPERATIONS "when does an image bake".
9. Feature branch `feature/convergent-bakes`, squash-merged, kept.

### 10. DONE 2026-09-08 — declared ephemerality and retention

**Built on feature/declared-ephemerality and proven live 2026-09-08
(ledger 61–64): one `run --all` regenerated the declared storages as
generation 2, baked both GCE images, launched/verified/tore down the
declared ephemeral `gce-test`, and disposed every GCE image through the
closing `retention` lifecycle — `gce-empty` green with `gce_data` and
`gce_bucket` standing. Two bugs found live and fixed (63 verification
without a pin, 64 the IAP tunnel wait); the standing-ephemeral rule and
its recovery were exercised for real.** What landed, in the order built: **12** storage
generations (a tombstoned declared storage regenerates; the live
`gce_data`/`gce_bucket` records become generation 2 on the next storage
apply — no workaround overlay any more); **11** undeclared = destroy
(the root is emitted for a recorded storage whose entry left the YAML,
wipe first, tombstone with action `undeclared`; N22 gone); **13** the
cardinality refusal names the multi-host builders; **1–2** ephemeral
instances (module `count` on `var.ephemeral_present`; launch → `verify
instance` → teardown plan/gate/apply in one sequence; a failed verdict
leaves it standing and the state query says so; `verify_instance`
runtime hook, GCE implemented; `verifications.yaml`); **3–6** retention
(`retention: {keep: N}`, runtime `retention_keep`, runtime `ephemeral:
true` keeps nothing) applied by the closing registered `retention`
lifecycle (`dispose image --retention`, recomputed at execution); **14**
detach with a required unmount (runtime `run_session_command` — GCE
IAP ssh, AWS SSM; `unmount storage` writes a receipt; `gate-plan
--require-unmounted`; `--confirm` records the operator; the AWS
attachment destroy whitelisted as a detach; the launch record drops the
mount after the apply; N26 narrowed to mount removal only); **15**
applied: `gce_data`/`gce_bucket` declared and persistent, `gce-empty`
accepts them, `gce-teardown` has no storage leg. Found live on the way:
a fresh CLI process resolved `run --all` to the four built-ins because
the hook plugins loaded only inside the run — `release` had never
joined `--all` from the command line; fixed. Live declarations (10.8):
`gce-test` is declared `ephemeral: true` in the tree, `gcloud-east1`
declares `ephemeral: true`; `just gce-cycle` is now one `run --all`
under the execution-knob overlay `gce-apply.yaml` plus `gce-empty`.


**The gap**: the GCE cost rule (58: nothing is kept between cycles)
is enforced by a procedure (`just gce-cycle` with overlays) rather
than by the configuration. The model has no way to say "this instance
exists to be verified and then removed", "keep at most N builds of
this series", or "this runtime holds nothing between runs". After §10
the config says those things and a single `run --all` does the whole
cycle: bake what changed (§9), launch, verify, tear down, dispose,
converge to empty. Overlays stay as a test-harness and operator tool;
the `gce-*` recipes keep working and stay (they are the cleanup path
the operator wants), but nothing *depends* on them.

1. **Ephemeral instances** — `instances[].ephemeral: true`. The
   instance-image lifecycle launches it through the gate, runs the
   runtime's verification hook, records the verdict in meta-state
   (`verifications.yaml`: instance, build, run, checks, pass/fail,
   evidence excerpt), then plans and applies the whitelisted destroy
   in the same run (whitelist reason `ephemeral`). Launch params and
   pin are recorded during the run and forgotten at the end, like a
   decommission. **DECIDED (user, 2026-09-07): on a failed
   verification the instance is LEFT UP for inspection and the run
   fails**; the state query then reports it as a standing ephemeral
   ("resources standing on ephemeral runtime X", step 5) until the
   operator decommissions it (undeclare, or `just gce-decommission`).
   Whether that should be configurable per instance/runtime is an
   investigation item in [docs/DESIGN.md §3H](docs/DESIGN.md).
2. **Verification as a runtime hook** — `verify_instance(name) ->
   Verification` on the runtime builder base; GCE implements what
   `gce-verify` does today (serial console: startup scripts finished,
   no failure line; booted image equals the pin; the pd mount evidence),
   AWS gets the SSM/console equivalent later (refuses cleanly until
   then). `just gce-verify` becomes a thin wrapper over
   `cs-image-system verify instance gce-test`.
3. **Image retention, declared** — on an image (and as a runtime-level
   default): `retention: {keep: N}` = the newest N builds of the series
   on that runtime survive; older ones are disposed at the end of a
   successful run through `dispose image` (never a build an instance is
   pinned to or launched from — those are refused and logged as
   retention debt by the retention lifecycle; the state query does not
   list them, ledger 67). Default: keep everything
   (today's behaviour). This is the garbage collector §8.4 lacked.
4. **Ephemeral runtimes** — `runtime_builders[].ephemeral: true`: at
   the end of a successful run, everything the run created on that
   runtime goes — its ephemeral instances are already gone; its
   storages transition to `destroyed` (bucket wiped first) and its
   images are disposed regardless of retention — through the same gated
   paths, in that order. This is rule 58 as one line of config on
   `gcloud-east1`, and it is what makes `just gce-cycle` equal to
   `run --all`. **DECIDED (user, 2026-09-07): the AWS runtime stays
   non-ephemeral** — untouched by the closing phase.
5. **Ordering inside one run** — identity → storage (create) →
   base-image → instance-image (bake what §9 says, launch, verify,
   destroy ephemerals) → retention/ephemeral teardown as a closing
   phase (storage destroy, image disposal). The closing phase runs
   only when every earlier lifecycle succeeded; on failure the run
   stops and reports what is still standing (the `gce-empty` shape as
   a state-query section: "resources standing on ephemeral runtime X").
6. **Apply flags** — the closing phase honours the same per-root
   `apply_*` scoping (§7): a dry run enumerates the teardown, a run with
   the storage/instance flags on executes it. No new flag.
7. **Tests**: an ephemeral instance's run emits launch, a verification
   record, and the whitelisted destroy in one runner sequence; failed
   verification behaves per the step-1 decision; retention `keep: 1`
   plans the disposal of exactly the older builds and refuses a pinned
   one; an ephemeral runtime's closing phase tombstones its storages
   and disposes its images, and never touches the other runtime; a dry
   run records nothing. Golden regenerated as needed.
8. **Live proof**: with `gce-test` declared `ephemeral: true` in the
   live `instances.yaml` and `gcloud-east1` declared `ephemeral: true`,
   one `run --all --no-dry-run` (flags on for the GCE roots) must end
   with `just gce-empty` green — the same evidence as §8, produced by
   the configuration alone. **DECIDED (user, 2026-09-07): the live
   proof re-declares `gce-test` in the live tree as `ephemeral: true`**
   (it never persists; the test-only fixture decision of §7 is
   superseded for this one instance).
9. Feature branch `feature/declared-ephemerality`, after §9 lands,
   squash-merged, kept.
10. **Added 2026-09-08 (ledger 60) — tombstone permanence vs rule 58.**
    N19 makes a destroyed storage permanent: the same name cannot come
    back as `active`. Rule 58 destroys `gce_data`/`gce_bucket` every
    cycle, so the first run after a cycle is refused ("cannot be
    resurrected as active") until the declarations are hidden behind
    the storage-teardown overlay (today `gce-bake` carries that overlay
    for exactly this reason). **Superseded the same day by the operator's
    storage semantics, items 11–15 below**, which replace "forget on an
    ephemeral runtime" with a model in which a storage's existence IS
    its declaration.

#### Storage semantics (operator, 2026-09-08) — how the config denotes persistence

The operator's rules, verbatim in substance: **a storage is persistent as
long as its config exists.** A storage created within config — outside a
pure testing action — is permanent until it is removed from config, and
that removal is its demise. Some storages may attach to several
instances, but that is a configuration error unless the storage type is
multi-host capable. Removing a storage from an instance detaches it; the
storage stays in managed state.

11. **Existence is the declaration; demise is the un-declaration.** A
    storage entry in `storages/*.yaml` means "this exists" — the storage
    lifecycle creates it if reality lacks it and keeps it otherwise
    (already the case). Deleting the entry means "destroy it": the next
    storage run plans the destroy, the gate whitelists it as an
    **undeclared** storage (the same operation-driven shape as an
    instance decommission, finding 52: the root is emitted even when it
    holds nothing else, so the destroy can plan), and the apply records
    the demise. The explicit `state: destroyed` request goes away for
    ordinary use — it becomes a *testing* device (overlays) and the way
    an operator can stage a destroy before deleting the entry if they
    want to see the plan first; `archived` (snapshot + delete the live
    resource) stays an explicit state because it is not a demise.
    Denotation in the file is therefore nothing new: presence/absence of
    the entry, plus the optional `state:` for archive/test cases.
12. **Tombstones keep history, not names.** Today's tombstone makes the
    *name* unusable forever ("cannot be resurrected"). Under item 11 a
    name that reappears in config after its demise is simply a **new
    storage** that happens to share the name — no data continuity is
    implied or offered. `storage-state.yaml` records this as a new
    **generation** (`generation: 2`, the earlier generation's history
    kept below it), so the state query, the read-model and the gate all
    know which physical resource a record describes; N19's permanence
    applies to a *generation*, never to the name. This is also what
    unblocks the live tree now: `gce_data`/`gce_bucket` are declared and
    recorded destroyed, so the next storage run creates generation 2 and
    the storage-teardown overlay stops being necessary for bakes.
13. **Attachment cardinality is a configuration error (already true).**
    `attachment_cardinality()` on every storage plugin says single or
    many (EBS and pd: single; EFS, S3, GCS, Filestore: many), and
    `v2_validation` refuses a single-attach storage attached by more than
    one instance (N16). Item: make the refusal name the capable
    alternatives ("pd is single-attach; filestore or gcs are multi-host")
    and add the same check to the launch overlay path (an overlay adding
    a second attacher must fail the same way).
14. **Detach leaves the storage in managed state.** Removing a storage
    from an instance's `storages:` is a change to that instance's mounts,
    which today trips launch-parameter immutability (N26: the mount list
    is part of the immutable launch parameters). Resolution: a mount
    *removal* is the one launch-parameter change that is allowed in
    place — the instance root plans the detachment (the attachment
    resource's destroy, whitelisted automatically as **detach** because
    the storage is still declared), the launch parameters are re-recorded
    without the mount, and the storage's read-model record loses that
    instance from `attachments` while its state stays `active`. Adding a
    mount stays a replacement (the machine must boot with it).
    **DECIDED (user, 2026-09-08): an unmount action is REQUIRED before
    a detach applies.** How the system requires it:
    - *14a — the unmount is a runtime transition action.* The instance
      builder computes the **detachments** of a run (mounts recorded in
      the instance's launch parameters that its declaration no longer
      lists). For each, the runtime plugin emits an `unmount_storage`
      command sequence, run through its session mechanism as a deferred
      step of the instance runner BEFORE the root's plan: AWS → `aws ssm
      send-command` (`AWS-RunShellScript`) to the instance; GCE →
      `gcloud compute ssh --tunnel-through-iap --command` as the runner
      service account (IAP is already granted to it, finding 54). The
      script is generated from the same launch parameters that mounted
      the storage: `fuser -km <mount_point> || true`, `umount
      <mount_point>`, drop the `<device> <mount_point>` line from
      `/etc/fstab`, `rm -d <mount_point>`, then `findmnt <mount_point>`
      must fail — the script exits nonzero if anything is still mounted.
    - *14b — the gate requires the proof.* The unmount step writes an
      **unmount receipt** into the run journal (`runs.yaml`: instance,
      storage, mount point, command id / session exit status, time).
      `gate-plan` gains `--require-unmounted <instance>:<storage>` for
      each planned detachment: it refuses the plan unless a receipt for
      that pair exists in THIS run (a dry run enumerates the unmount
      step and the receipt requirement without executing either, so the
      operator can read exactly what will happen). Without a session
      mechanism (a runtime that has none, or an instance recorded as
      stopped — the state query's instance probe knows its status), the
      alternative proofs are: the instance is `TERMINATED`/`stopped` in
      reality, or the operator passes `--confirm-unmounted
      <instance>:<storage>` — recorded as an operator receipt with
      their identity from the environment, never silent.
    - *14c — order inside the run.* Unmount (session) → plan (the
      attachment destroy appears) → gate (`--allow-destroy` for the
      attachment as **detach** + `--require-unmounted`) → apply-check →
      apply → launch parameters re-recorded without the mount (the one
      permitted in-place change, N26) → the storage read-model's
      `attachments` updated. If the unmount fails the run stops before
      the plan and nothing is detached; the storage stays attached and
      declared-detached, which the state query reports as
      `changed` (detach pending) until the next run succeeds.
    - *14d — re-attach is a mount add, i.e. a replacement*: the instance
      must boot with the mount (user-data / startup script), so adding
      a storage back is the existing replacement path, never a hot
      attach.
15. **Where the ephemeral runtime fits after items 11–14.** Rule 58
    ("nothing kept on GCE") and item 11 ("declared means persistent")
    meet cleanly once the GCE storages are declared only where they are
    meant to live: **either** keep `gce_data` and `gce_bucket` in the
    permanent config and accept that they persist between cycles (30 GB
    pd-standard is inside the free tier and an empty bucket bills $0 —
    the cost is nil, and the cycle's launch gets its mount without
    re-creating anything), **or** move them into the launch overlay so
    they exist only for a cycle (a "pure testing action", forgotten
    afterwards — no tombstone, no generation). The ephemeral-runtime
    closing phase (item 4) then only ever destroys storages that a
    testing action created; it never touches a declared one.
    **DECIDED (user, 2026-09-08): keep them declared, under the existing
    rules.** A test may declare a temporary storage (through an overlay)
    and delete it at its end; a test that USES a config-declared storage
    treats it like any other declared storage — it never destroys it.
    Consequences applied the same day: `just gce-teardown` no longer has
    a storage leg (`gce-teardown-storage` retired); the storage-teardown
    overlay remains only as the ledger-60 tombstone workaround for bakes
    until item 12 lets `gce_data`/`gce_bucket` be re-created as
    generation 2 (their current records say destroyed because the
    2026-09-07 cycle destroyed them before this rule existed); the
    launch overlay attaches `gce_data` as a declared storage. Item 4's
    "its storages transition to destroyed" is therefore struck: an
    ephemeral runtime's closing phase disposes images and destroys only
    overlay-declared temporary storages. **Until item 12 lands,
    `just gce-launch` and `just gce-cycle` are blocked**: `gce_data` is
    recorded destroyed and a destroyed storage cannot be attached; the
    bake, decommission, disposal and empty legs work (the tombstone
    workaround overlay is carried by `gce-bake` and `gce-decommission`).
    Item 12 is therefore the first thing §10 builds.

### 11. DONE 2026-09-08 — items 1–6 (Okta on GCE excluded by the operator)

**Built on feature/section-11, every item proven by tests.** 1 — AWS
parity: `query_instance_boot_image`, `dispose_image` (deregister +
snapshots), `verify_instance` over SSM reading the new user-data
completion marker `/var/lib/csis/launch-applied`; an AWS instance may
be ephemeral. 2 — `lineage restamp --runtime`: current fingerprints on
series heads after the §9 recipe change, cloud images re-tagged;
**applied live to the eight AWS heads** (meta-state e76b49f) — the
decision: re-stamp rather than re-bake, since nothing about those
builds changed but the hash recipe; `--force-bake` re-bakes on purpose.
3 — `on_failure: keep | teardown`, `teardown_after: <duration>` on
instances and runtimes (`verify … --record-only` + `verify assert`; a
due standing instance is torn down without re-verifying; the standing
report states the policy). 4 — the closing phase destroys transient
(overlay-declared) storages on an ephemeral runtime itself (a storage
run without the declaring overlay as its second deferred step). 5 —
`runtime describe`, `empty --runtime`, `run --only-runtime` /
`--apply-runtime` (carried into `apply-check`); generic `cloud-*`
recipes, `gce-*` as aliases; no recipe hardcodes a project. 6 —
`archived` for persistent disks: snapshot + whitelisted destroy,
restore from the snapshot on `active`, the archive deleted after the
apply; builders that cannot archive refuse the state.

**Resolved (2026-09-08, operator approved; corrected 2026-09-09, ledger
68)**: `ami-0829ccceee6db194e` (the old `basic-rhel-8` base pinned by
`imgfile-basic-dask@aws-east2-runtime`) had been deregistered OUTSIDE
the system. What actually happened: the `upgrade image` ran under the
CLI's default `--dry-run` and never persisted (no run entry, no commit);
`dispose image ami-0829ccceee6db194e` dropped the record AND the pin at
it (8e654dd), so the dask image on AWS was left unpinned and the strict
preflight passed. On 2026-09-09 the first run whose bake surface was not
filtered to GCE baked `basic-rh-10@aws-east2-runtime` (no build yet:
the series was renamed from basic-rhel-8 on 09-04 and had no AWS build)
and, following it, `imgfile-basic-dask@aws-east2-runtime`, and
first-bound the pin to the new base — the tree's declared state.
**DECIDED (user, 2026-09-09): the two AWS AMIs are kept.**

**Live legs, DONE 2026-09-08 (ledger 65–67)**: the generic `cloud-cycle
gcloud-east1` (5) ran to `cloud-empty` green with no bake (both images
current), the ephemeral launch/verify/teardown and retention disposing
both images; the transient scratch disk was created, archived (snapshot
+ gated destroy), restored from the snapshot (snapshot deleted after the
apply) and finally destroyed by the closing phase of a run carrying its
overlay (4, 6). Found on the way: the recipe option-order bug, now
pinned by a Justfile-versus-CLI test (65); the AWS SSO session lapsing
mid-run and the GCE roots' S3 state dependency (65); the GCE runtime
never re-labelling a follow image after its bake, so a survivor showed
`changed` drift — `retag_image` on GCE + `lineage relabel` / `just
cloud-relabel` as the standing remedy (66).

**Evidence grades (2026-09-09, ledger 68)**: proven LIVE — items 2, 4,
5, 6 (now WITH data: a file written before the archive came back with
the same checksum on a relaunch from the restored disk), 3 (`on_failure:
teardown` on a real failing startup; found and fixed on the way: the
torn-down instance kept its launch record because `verify assert`
failed the script before the forgetting hook ran), and §10.14 detach +
unmount (session unmount, receipt, gated in-place detach). Tests only —
item 1 (AWS parity: the SSM verification and AMI disposal hooks have
fakes; the AWS runtime stays non-ephemeral by decision). Added for the
proofs: instance `userdata` (a declared-but-unused field now runs as the
startup script's last act, immutable like every launch parameter) and
the overlay `undeclare: true` entry form.

**§12 candidates raised by 11**: (a) a GCS state backend for the GCE
roots so GCE work does not depend on an AWS session; (b) networking
validation scoped to the runtimes a command touches (today every
runtime model validates against its cloud at configuration load, so
`empty --runtime gcloud-east1` needs AWS credentials); (c) a credential
lifetime check in `cloud-preflight` (warn when the AWS SSO session
expires within the expected run length); (d) a session identity that is
not the operator's login key — the GCE session hook is a non-interactive
`gcloud compute ssh` as the operator, so it depends on an agent-loaded
or passphrase-less key (ledger 68; OS Login with the runner service
account is the candidate); (e) `--apply-runtime <rt>` implying
`--only-runtime <rt>` unless `--only` is given — today it scopes the
applies only, and an ad-hoc run without the bake filter baked two AWS
AMIs (ledger 68).


Original candidate list for reference:

1. **AWS parity for the sanctioned paths.** Two runtime hooks refuse
   cleanly on AWS today: `dispose_image` (deregister the AMI and delete
   its snapshots — the finding-46 shape done by hand for AMIs on
   2026-09-05) and `verify_instance` (the SSM/console equivalent of
   the GCE serial-console verification: `ssm send-command` for the
   mount/booted-image checks, or the EC2 console output). Without them
   an AWS image can only be disposed by hand and an AWS instance cannot
   be declared `ephemeral`. `run_session_command` already exists for AWS
   (SSM), so `verify_instance` is small; `dispose_image` is a
   deregister + snapshot cleanup with the same refusals as GCE.
2. **AWS fingerprints re-bake once.** §9 changed what the input
   fingerprint covers, so every recorded AWS build's fingerprint now
   differs from what the tree computes: the first AWS bake run will
   re-bake all six AWS images once (and the five stale AWS pins, ledger
   59, follow or stay pinned per policy). Decide before any AWS bake
   run: accept the one-time re-bake (cents of t3 minutes, new AMIs to
   dispose — item 1 first), or `state import`-style re-stamping of the
   recorded fingerprints from the current tree (a one-off command,
   honest only if nothing else changed since those builds).
3. **Ephemeral failure policy** (DESIGN §3H, added 2026-09-07): the
   decided behaviour is *keep* (leave the instance standing, fail the
   run, report it). The candidate is `on_failure: keep | teardown |
   teardown-after <duration>` on an instance and/or runtime, `keep`
   the default — with the questions §3H lists (where the knob lives
   and its precedence, the run's verdict under teardown, no scheduler
   for a timed teardown so the next run's closing phase does it, and
   how a standing ephemeral shows in `gce-empty`). Small; touches the
   closing phase.
4. **Transient storages in the closing phase.** A storage a test
   declares through an overlay is destroyed by the *next* run that omits
   the overlay (§10.11); the closing `retention` lifecycle only reports
   one standing on an ephemeral runtime. Making the closing phase plan
   that destroy itself needs the storage root regenerated without the
   overlay inside the same run — a second storage generation pass at
   the end. Worth it only if tests start declaring temporary storages;
   today none do (`gce_data`/`gce_bucket` are declared and persistent).
5. **Recipes driven by the configuration.** The `gce-*` recipes still
   hardcode this project's facts (`csis-sandbox`, `us-east1-b`,
   `basic-rh-10`, `imgfile-basic-dask`, the declared disk and bucket
   names for `gce-empty`). A `cs-image-system runtime describe
   gcloud-east1` (project, zone, declared storages' cloud names, the
   images baked on it) would let the recipes read those facts, and a
   `cs-image-system empty --runtime gcloud-east1` would make `gce-empty`
   a system command rather than a gcloud script. Then the recipes
   become generic (`just cloud-cycle <runtime>`).
6. **Readiness leftovers, informational.** The GCP readiness file has
   two unticked boxes that need no code: the snapshot free allotment
   (nothing is archived yet — the `archived` state is untested live)
   and egress discipline (bakes download only; unmeasured). A live
   `archived` transition of `gce_data` (snapshot + delete, then
   `active` again — data continuity is the point of `archived`, unlike
   a regeneration) would tick the first and prove that state machine
   leg for real.
7. **Okta/ASA on GCE** stays the lowest priority (§7 decision): OPA
   enrollment on GCE, the identity read-model, sftd on Alma 10 —
   nothing done since removes what it needs.

### 12. DONE 2026-09-09 — run scoping safe by construction

**Built on feature/run-scoping and proven live 2026-09-09 (ledger 69).**
`--apply-runtime <rt>` implies `--only-runtime <rt>` unless images are
selected explicitly (bake plan: `skip: outside the apply scope`); a
`--no-dry-run` run whose apply scope is a proper subset refuses before
any bake when the plan would bake outside it (`--allow-unscoped-bakes`
or an explicit selection lets it through; a dry run warns); the
preflight prints one `session:` line per credential source, read from
the raw runtime-builders.yml BEFORE the configuration loads (an expired
session refuses there; `state query --strict` refuses on one shorter
than `config.preflight.expected_run_minutes`, default 30). Proven live:
the previous day's ad-hoc command now skips every AWS image; the strict
preflight refused under the proof overlay and passed without it; a real
cycle baked only on GCE and ended empty. Found on the way: the
configuration load itself dies on an expired session, hence the raw
pre-load check; the headless tests had read the developer's real cache,
hence `tests/conftest.py`. Original plan for reference:


**Why**: on 2026-09-09 an ad-hoc `run … --apply-runtime gcloud-east1`
without `--only-runtime` baked two AMIs on AWS (ledger 68), and on
2026-09-08 a cycle failed mid-run when the AWS SSO session lapsed after
the preflight had passed (ledger 65). Both are one theme: a run must
bake only where it is meant to, and must know before starting whether
it can finish. Former §12 candidates (e) and (c).

1. **`--apply-runtime <rt>` implies `--only-runtime <rt>`** unless
   `--only` / `--only-runtime` is given explicitly. The bake plan says
   so per image (`skip: outside the apply scope`). The `cloud-*`
   recipes keep passing both (belt and braces; the Justfile test
   already checks their shape).
2. **A bake outside the apply scope refuses under `--no-dry-run`.** The
   apply scope is the union of `--apply-runtime` and the runtime/root
   lists in the `apply_*` flags. When the bake plan would bake on a
   runtime outside that scope, the run stops before any bake and names
   the images and the flag that allows it (`--allow-unscoped-bakes`,
   or an explicit `--only`). A dry run only warns. Bakes are additive
   and never gated by apply flags (decision 2026-09-02) — this is a
   *scope* check, not a bake flag.
3. **Session lifetime in the preflight.** `cloud-preflight` (and the
   run's own preflight) reads the SSO cache for the runtime's profile
   and, when the session expires within `preflight.expected_run_minutes`
   (config, default 30), warns loudly with the expiry time; with
   `--strict` it refuses. GCP ADC lifetime is reported the same way
   where it can be read. Read-only; no credential value is ever
   printed or recorded.
4. **Tests**: the bake plan under implied scoping; the refusal and the
   allow flag; the preflight with a faked cache (expired, expiring,
   fresh); the Justfile-versus-CLI test extended to the new options.
   Docs: OPERATIONS "The one command" and "Runtime facts and scoping".
5. **Live proof (cheap)**: a dry `just cloud-cycle gcloud-east1`
   showing the scope in the bake plan, then one real cycle; the
   preflight warning provoked once by a session close to expiry, or
   by a low `expected_run_minutes` in an overlay.
6. Feature branch `feature/run-scoping`, squash-merged, kept.

### 13. DONE 2026-09-10 — AWS EL10 migration and the AWS live proof

**Built on feature/aws-el10 and proven live 2026-09-10 (ledger 70).**
The AWS `basic-rh-10` base bakes AlmaLinux 10 (the operator's choice
over RHEL 10; owner 764336703387), `family_version` 10 on both runtimes;
live heads `ami-01a9a00286f1631af` (base) and `ami-07519c62eb365d850`
(dask, pin followed); the EL8 pair disposed through the first live AWS
`dispose image` (authorized); the first live AWS ephemeral verified over
SSM and torn down. Found and fixed on the way: `--only-runtime` now
scopes the terraform roots too (the GCE family lookup 404'd during a
scoped AWS bake), and a `follow` child re-bakes when its parent bakes
in the same run (the rule lives in the bake decision, never in the
fingerprint's parent reference). Original plan for reference:


**Progress 2026-09-10 (feature/aws-el10, ledger 70)**: items 1–4 DONE —
AlmaLinux 10 decided and applied (owner 764336703387, `family_version:
10` on both runtimes, the RHEL family plugin accepts EL10); the scoped
live bake built `ami-01a9a00286f1631af` (base) and, on retry,
`ami-07519c62eb365d850` (dask, pin followed); the EL8 pair disposed
through `dispose image` (deregister + snapshots, commit 34c7b6a). Found
and fixed on the way: a scoped run planned the OTHER runtime's terraform
root (the GCE family lookup 404'd) — `--only-runtime` now scopes roots;
and a `follow` child read "current" while its parent re-baked in the
same run — the bake decision now sees it. Item 5 (the AWS ephemeral
proof) in progress; 6–7 pending.

**Why**: the AWS chain bakes `basic-rh-10` from the RHEL 8.10 vendor
query — the series renamed on 2026-09-04 while the AWS source stayed —
and since 2026-09-09 an AMI named `basic-rh-10` built from EL8 exists
(`ami-075901e1bd7965da7`, kept by decision). The name now lies on one
cloud. Deferred by the §7 decision; brought forward because the
artifact is concrete. The same run is the first LIVE exercise of §11
item 1 (AWS parity), which is test-only today.

1. **USER — the EL10 source on AWS**: AlmaLinux 10 (free, parity
   with GCE; community AMIs from the AlmaLinux OS Foundation) or RHEL 10
   (licence premium per hour, as RHEL 8 billed on GCE before §1).
   Recommended: AlmaLinux 10. Confirm the owner id and the image name
   pattern with a read-only `aws ec2 describe-images` before editing the
   query, and pin the architecture to x86_64 (the finding-39 lesson).
   **DECIDED (user, 2026-09-09): AlmaLinux 10.**
2. Point the AWS os-builder entry for `basic-rh-10` at the chosen
   source. Dry run: the bake plan must show `inputs changed` for
   `basic-rh-10@aws-east2-runtime` (the vendor source is part of the
   fingerprint) and, under `parent_policy: follow`, the dask child; the
   in-bake `tests:` hold on EL10 (the dnf5 guard of finding 42 applies
   on both clouds); `packer validate` clean.
3. Live bake, scoped: `run base-image instance-image --only-runtime
   aws-east2-runtime` (no apply). Two AMIs, lineage-recorded, relabelled
   after the bake (the AWS retag path), preflight "no drift".
4. **USER — dispose the superseded EL8 pair** (`ami-075901e1bd7965da7`,
   `ami-085eeafc0b8efbebc`) through `dispose image` — the first live
   AWS disposal: deregister + snapshots, records dropped, the dask
   parent pin already moved by `follow`. **AUTHORIZED (user,
   2026-09-09)** — executes after step 3's bakes are recorded.
5. **AWS ephemeral proof (§11.1 live)**: under an overlay declaring
   `test2` `ephemeral: true` (the AWS runtime stays non-ephemeral, §10
   decision; an instance may be ephemeral on it), `run instance-image
   --apply-runtime aws-east2-runtime`: launch → `verify instance` over
   SSM (`/var/lib/csis/launch-applied`, mounts, AMI) → gated teardown
   → records forgotten. Cost: minutes of t3.medium on the AWS account.
   Nothing touches existing network configuration (standing constraint).
6. The four stale AWS pins (cloudflow / dask-two, ledger 59) stay
   stale by policy (`pinned`); note them, do not move them.
7. Records: ledger entry; PLAN status; the readiness/operations notes
   that still say "RHEL 8 on AWS". Feature branch
   `feature/aws-el10`, squash-merged, kept.

### 22. DONE 2026-09-12 — declarations that never land

**Built on feature/declarations-that-never-land and proven 2026-09-12
(ledger 75).** Six ways a declared or passed value was discarded in
silence, all fixed with the golden byte-identical on both runtimes:
`default_image_builder` is structurable at last (every runtime had
silently held DEFAULT); nine keys left two internal dicts that had no
fields for them; `output_image_name`'s seven fixture declarations were
commented out by the operator's decision rather than made real, because
making them real renames every future image on both clouds; two ansible
`source:` keys and fourteen further dead keys were commented out with
individual reasons so they can return; and the template-scoping test
stopped asserting through a key the models discard. The fixture now
carries zero unknown keys, which is what §21 needs. Original plan for
reference:

**Why**: TRIAL-002 forbade unknown keys and the configuration stopped
loading six times, each on a different way a declared or passed value is
silently discarded. These are live defects independent of that rule, and
§21 cannot ship until they are fixed. None of them moved the golden,
which is the point: they are invisible until something looks.

1. **`default_image_builder` is never read from YAML** — it is declared
   `init=False`, so cattrs never structures it and every runtime silently
   holds `DEFAULT` no matter what the configuration says. The live fixture
   declares `pckr-ebs-ans` and `packer-gcloud-ansible`; neither ever
   reached a model. Make it an init field and check nothing downstream
   depended on the wrong value.
2. **Nine keys in two internal dicts are not fields on their targets.**
   The OS-builder resolver hands cattrs a `BaseImage` dict carrying
   `machine_type`, `architecture`, `auto_generate_storage`,
   `modifications` and `default_groups`, and a nested subconfig dict
   carrying `source_image`, `default_machine_type`,
   `default_primary_disk_size` and `query`. All nine are dropped. Decide
   per key whether the field should exist or the key should go —
   **`modifications` on a base image is the one worth a real answer**, the
   resolver has always believed it passes them.
3. **`output_image_name` at the per-runtime level is shadowed** by a
   computed property of the same name, so those fixture declarations can
   never take effect; at the os-builder level the field had been commented
   out and should be restored. The two readers in `aws_utils` and
   `gcp_utils` resolve to the property, and `output-image-name` appears
   nowhere in the golden, so neither line is reached today.
4. **Ansible modification items use `source:`**, which no model accepts,
   so the two items declaring it in `images/image2.yaml` have always had
   zero playbooks — the validator already warns, and nobody read it.
   Either model the key or convert those items to `playbooks:`.
5. **The dead keys in both configuration trees**: sixteen in the external
   repository (TRIAL-001) and twenty-seven in the fixture (TRIAL-002),
   including a junk `jethro: bodine` and a `dask_version` whose value is a
   joke. They are harmless today and errors under §21.
6. **One test asserts through a discarded key**:
   `test_string_stage_resolves_config_document` proves template scoping
   (`this`, `this.parent`) using a runtime-level `output_image_name`. It
   reads the raw resolved document and never checks the value survives
   into a model, so it passes on a key the models throw away. Repoint it
   at a field that does survive.
   Feature branch `feature/declarations-that-never-land`, squash-merged,
   kept.

### 26. DONE 2026-09-13 — `parameters` retired; `variables` typed per provider

**Built on feature/arguments-and-variables, proven 2026-09-13 (ledger 82).**
The overloaded field is gone from every builder model and the protocol; a
stale declaration is refused at load with the replacement named. A storage
builder's `variables:` is a typed per-provider model of its module's own
tunables (EBS `volume_type`/`encrypted`/`tags`, EFS
`performance_mode`/`encrypted`/`tags`, S3 `force_destroy`/`tags`, the GCP
builders `tags` as labels), merged under what the builder computes from
the item and over the module defaults, tags item-over-builder. The argv
meaning was dropped by operator decision (the packer plugin assembles its
own command line), so `arguments` does not exist. Steps 1–3 left the
golden byte-identical; restoring the declarations moved it by exactly the
three AWS module calls. The EBS declaration matches the live volume (gp3,
100 GB) by operator decision after a snapshot (snap-08b1ebbccfbdd7570) was
taken of the detached, never-snapshotted `mnt_data`. Original plan for
reference:

**Why**: one field name has carried two unrelated meanings, and its type
fits only one of them. The image builders declare `parameters: ["build",
"."]` beside `executable: packer` — argv for a wrapped tool, which is what
the declared `list[str]` says. The storage builders declared `parameters:`
as a MAPPING whose keys are the terraform modules' own variable names
(EBS `volume_type`, `size`, `encrypted`, `tags`; EFS `performance-mode`,
`encrypted`, `tags`) — inputs to an IaC module call, which the list type
silently mangles: a mapping iterated as a list yields its key names and
drops every value (§25, ledger 79). Neither form is read today: nothing
calls `get_parameters()`, and the packer plugin hardcodes `build` when it
assembles its command line (`packer_builder.py`, `packer_ebs_builder.py`),
so the image builders' declarations describe what the plugin already
does rather than feed it. §25 commented the storage declarations out of
the fixture with that reasoning and left the field untouched in code so
the capability could be reworked deliberately. The rework is to
distinguish the two meanings by name and type, not to retype one field:
retyping `parameters` to a mapping would make the three image-builder
declarations the next thing to break, and since unknown keys are refused
(§21) a mismatch is a hard load failure, not a silent one.

1. **Two fields, named for their intent; `parameters` retired.**
   `variables: dict` — inputs to the IaC module call, merged over what the
   builder computes so a declaration wins and an absent one keeps today's
   behaviour; the word is terraform's own (`-var`). `arguments: list[str]`
   — extra argv appended to the wrapped executable's command. `parameters`
   is removed from `BuilderModel`, `InstanceBuilderModel`, the OS runtime
   subconfig and the protocol, so a stale declaration is refused at load
   with a message naming the two replacements.
2. **USER — does `arguments` exist at all?** The packer plugin decides its
   own argv and nothing has needed to override it; an unread override hook
   is the kind of field §22 spent a day removing. Decide: keep `arguments`
   and make the plugins honour it (appended after the plugin's own
   subcommand, never replacing it), or drop the argv meaning entirely and
   delete the three image-builder declarations. The default, absent a
   need, is to drop it.
3. **`variables` typed per provider**, the way §17 did for credentials: a
   typed object catches `volume-type` versus `volume_type` and
   `performance-mode` versus `performance_mode` (the fixture had both
   spellings), which a free-form mapping never will. One model per storage
   module (EBS, EFS, S3, PD, GCS, Filestore) declaring exactly the module's
   variables, with the module's `variables.tf` (§27) as the source of
   truth; the instance builders and the OS runtime subconfig get theirs
   when a declaration needs them, not speculatively.
4. **Wire `variables` into the module calls.** Each storage builder's
   `module_args` merges the declared variables over what it computes; the
   emitted module call carries them; a test per provider asserts the
   emission and the merge order.
5. **⚠️ USER — the migration is the hard part.** On EBS, `volume_type` and
   `size` force REPLACEMENT: honouring the fixture's `gp2` at 8 GB would
   plan a destroy and recreate of the live `mnt_data` volume, which is
   gp3 at 100 GB today and holds data. Decide per live storage whether to
   adopt the declaration (with an archive/restore cycle around it, the
   §15 shape) or to change the declaration to match reality, BEFORE any of
   this reaches an apply. The gate (§3C) will refuse an unwhitelisted
   destroy regardless, which is the backstop, not the plan.
6. **Both configurations in the same step**: the frozen fixture and the
   live repository (`cs-image-system-testconfig`) change together with the
   models — the storage declarations restored under `variables:` with the
   values decided in step 5, the image builders' `parameters:` renamed or
   deleted per step 2 — because a load failure in either is a hard stop.
   Restoring the fixture's declarations is the acceptance evidence: the
   emitted module calls must carry them, and the golden diff must be read
   deliberately rather than accepted — unlike every stage since §22, this
   one is MEANT to move emitted output (step 4), while steps 1–3 alone
   must leave it byte-identical, since neither form reaches the emission
   today.
7. Records: ledger; OPERATIONS "the configuration tree" names both fields
   and what each feeds. Feature branch `feature/arguments-and-variables`,
   squash-merged, kept.

### 27. DONE 2026-09-13 — `tfmodules` split by block kind

**Built on feature/tfmodules-split, proven 2026-09-13 (ledger 81).** Every
module now has the four files `aws_instance/` already had: `provider.tf`
(the `terraform { required_providers }` block), `variables.tf`, `main.tf`
(data sources, locals, resources) and `outputs.tf`; the Okta module's
prefixed file names were renamed to the same convention. Blocks moved
verbatim with their leading comments — a script proved the multiset of
top-level blocks identical before and after — so nothing a plan sees
changed; every module passes `tofu validate` and the bar is green.
Original plan for reference:

**Why**: The current structure of `tfmodules` mixes different types of module resources in a single file, making it harder to locate, maintain, and understand the purpose of each module. Best Naming Practices recommend organizing elements by their function and purpose, with clear and consistent naming.

1. **Split existing modules.** Where only a `main.tf` exists, create separate files for `variables.tf`, `outputs.tf`, and any other logical grouping of resources within the module. This improves readability and maintainability by clearly separating the different aspects of the module's configuration.
2. **Refactor module contents.** Each new module file should sit at the same level as the original `main.tf` within the module, ensuring that all related files are grouped together logically.
3. **Follow consistent naming conventions.** Ensure that the new files follow a consistent naming convention across all modules, making it easier for developers to navigate and understand the structure of the `tfmodules` directory.

### 18. DONE 2026-09-15 — end to end in CI (the live job gated on secrets)

**Built on feature/ci-end-to-end, proven 2026-09-15 (ledger 87).** CI had
never been green: 245 runs, zero successes, because three configuration
tests inherited the Okta workspace's `TF_VAR_*` credentials from the
developer's shell. They stub them now, and run 34967316313 is the first
green run — `verify` (the bar, typecheck blocking, 562 passed) and
`live` (the live configuration checked out beside the system, federated
read-only AWS and GCP identities, a profile shim, then validate,
config-drift, the strict state query and the docker mod tests) as two
jobs, the second gated on seven secrets and printing a SKIPPED line per
missing one until the operator provides them. A test pins the shape:
every command is a `just` target, `verify` needs no secrets, `live` is
gated, scheduled nightly and never passes `--no-dry-run` or `--commit`.
Step 2 (the federated credentials) remains the operator's; the
real-run-on-master job is a later stage. Original plan for reference:

**Why**: GOALS.md: "the system should be capable of being operated end-to-end,
including multiple lifecycles, without any user interaction, within a
CI/CD pipeline". Gate 7 proved headlessness with a test that drives the
CLI, and the CI workflow (2026-08-14) runs lint, typecheck and the fast
tests on every push — and nothing else: no headless dry run of the
meta-workflow, no drift check, no docker-backed mod tests. Builds on §16's
targets.

1. **CI on every push and PR**: one step, `just verify` — the acceptance
   bar has one name; the docker-backed mod tests when the runner offers
   docker (`just full-test`'s credential-free legs).
2. **USER — federated credentials for a scheduled job**: a read-only IAM
   role in the AWS account trusting GitHub's OIDC provider (EC2 describe
   for the configuration load, read on the state bucket, image and storage
   describes for the state query) and the Okta read scopes — or the
   decision that the scheduled job stays credential-free and runs `verify`
   only. GCP is out of scope for this stage.
3. **Scheduled job**: nightly `state query --strict` (the orphan-sweep
   reminder, automated — drift becomes a failed run in the inbox) and a
   dry `run --all` against the live configuration (the emitted IaC still
   validates). Reads only; never `--no-dry-run`. Since stage 28 "the live
   configuration" is the `cs-image-system-testconfig` repository: the job
   checks it out beside this one (its `module_source_base` reaches
   `../cs-image-system-3/tfmodules`) and drives it through `CSIS_CONFIG_ROOT`;
   the fast suite needs no configuration at all. The dry run's question
   is `just config-drift` (2026-09-14): not only "does the emission still
   validate" but "is the committed emission current with the
   declarations" — a non-zero exit is the drift becoming a failed run.
4. Tests: the workflow file calls only `just` targets, so the
   Justfile-versus-CLI test and the targets themselves are its test; a
   badge/run link in the README.
5. Feature branch `feature/ci-end-to-end`, squash-merged, kept.

### 39. DONE 2026-09-16 — hygiene bundle: state encryption, the release target, the fixture's instances

**Built on feature/hygiene-state-encrypt, proven 2026-09-16 (ledger 94).**
Every S3 state backend, live and fixture, declares `encrypt: true`; the
emitted partial backend configurations say so (nine golden files moved) and
the real-run generation-time init carries `-reconfigure`, since a backend
argument changed under roots already initialised and the state is remote.
The release publish target is the tag alone by decision (2026-09-15); the
`release` recipe and OPERATIONS say so, and an index is stage 41. The
suite's instance subjects (`test`, `test2`, `gce-test`) are declared in the
fixture's own `instances/instances.yaml`; the harness injects nothing and
`tests/fixtures/test_instances.yaml` is gone — the golden did not move for
the fold, the proof that the injection had been a copy. Sibling commit
a56306b (pushed), config-drift current. The plan as it left the
worksheet:


Three items each too small for a stage of its own, bundled, each moving
the golden once by design.

1. **`encrypt: true` on the S3 state backends** — accepted `false` on
   2026-09-15 (publication note), flipped now: the live
   `cfg/state-backends.yml` and `state-backends-2.yml` and the fixture's
   two copies (the field already exists on the model,
   `tf_s3_state_models.py:27`); each live root re-inits with
   `-reconfigure` (a backend argument changed; same bucket and key, no
   migration), and an existing state object is re-encrypted server-side
   only when next written — S3 encrypts every new object by default since
   2023, so the flag is a declaration as much as a change. Golden moves
   (the backend config files).
2. **`just release`'s publish target — decided 2026-09-15: the tag alone,
   for now.** §16's open item is closed; the publish leg and its
   `UV_PUBLISH_URL` guard stay as they are (they become §41's mechanism),
   and only the SKIPPED wording changes, from "no registry decided" to
   "the tag is the release; an index is §41"; OPERATIONS says the same.
3. **The test-only instance subjects fold into the fixture**: stage 28
   kept `tests/fixtures/test_instances.yaml` (`test`, `test2`,
   `gce-test`) prepended by `copy_config` as "a later tidy that would
   move the golden"; they move into the fixture's
   `instances/instances.yaml`, `copy_config` stops prepending, and the
   fixture is one tree again. Golden moves.

Records: ledger. Feature branch `feature/hygiene-state-encrypt`,
squash-merged, kept. Half a day.

### 38. DONE 2026-09-16 — self-contained run scripts

**Built on feature/portable-run-scripts, proven 2026-09-16 (ledger 93).** A
committed `run-<lifecycle>.sh` names no machine's path: its header defines
`CSIS_ROOT` as the configuration root relative to the script and every
root-based argument (`--root-dir`, `--overlay`) renders through it, while the
executable keeps the absolute argument for the in-process real run; every
terraform root's block begins with its own `tofu init -input=false
-reconfigure -backend-config=<file>`, the real-run form whatever the run's
mode. The config-drift normaliser lost both root rules and the golden its
`<config-root>` token, so an absolute path in the emission is drift and a
golden failure, not noise; the golden moved once (the five run scripts).
Proof: the live configuration's dry `--commit` run (testconfig 79bb18e) and
a fresh clone of it at another path, with no `.terraform/` anywhere, that ran
`generated/identity/run-identity.sh` to completion — backend initialised,
plan against the S3 state "No changes", gate passed, nothing applied.
The plan as it left the worksheet:


**Why** (ledger 91, "noted, not done"): a `run-<lifecycle>.sh` the run
commits carries `--root-dir /Volumes/…/cs-image-system-testconfig` — one
machine's absolute path — in its `release` and `retention` lines
(`system_cli_executable_with_config` in `base/utils.py`,
`transient_storage_teardown_command` in `base/retention.py`), and the
config-drift normaliser blanks the value to hide it. And every script
assumes an initialised root: `init` is a generation-time command that
runs in-process, so after a dry run (`-backend=false`, stage 18) or in a
fresh clone (`.terraform/` is never committed) the script's first `tofu
plan` fails. A committed script should run on any machine that holds the
tree and the credentials.

1. **The root, relative to the script**: `script_lines`
   (`base/global_context.py`) writes
   `CSIS_ROOT="$(cd "$(dirname "$0")/<relpath>" && pwd)"` in the header,
   `<relpath>` computed at generation from the script's directory to the
   configuration root, and the two command builders render `--root-dir
   "$CSIS_ROOT"` as a shell reference, not a quoted literal (an
   `--overlay` path the same way; the live configuration carries none).
2. **The init, in the script**: each terraform root's block begins with
   its own `tofu init -input=false -reconfigure -backend-config=<file>`
   (`-reconfigure` because a dry run's backend-less `.terraform/` may be
   present; the committed lock file pins the providers). The
   generation-time init stays: it is what validates the emission.
3. **The normaliser loses its `--root-dir` rule** in `just config-drift`
   (Justfile) — the emission is machine-independent now — and the golden
   moves once (`just golden-regen`: the fixture's `run-identity.sh` gains
   its init lines and the header variable). The gate-1 test that the
   runner scripts CARRY the V1 deferred commands still holds (a superset).
4. **Proof**: a fresh clone of the live configuration at a path that is
   not the operator's, `source .envrc`, and
   `generated/identity/run-identity.sh` plans and gates (no apply:
   `apply_identity` is false) with no run before it; CI's config-drift
   green without the normaliser rule.
5. Records: ledger; the OPERATIONS/memory note that a hand run needs its
   own init replaced. Feature branch `feature/portable-run-scripts`,
   squash-merged, kept. A day.

### 36. DONE 2026-09-15 — synthetic personas in the frozen fixture

**Built on feature/synthetic-personas, proven 2026-09-15 (ledger 92).** The
nineteen real people the fixture carried since stage 28 are nineteen
personas with phonetic-alphabet surnames, in the roster's exact shape (the
same explicit/derived split, the one mixed-case username, the same
memberships), encrypted to the same committed TEST identity; the fixture's
`default_user_email_template` is `{{ user.name }}@example.invalid` and its
`public_safe.allow` no longer names `@noaa.gov`, so `just public-safe` refuses
a real address anywhere outside prose and tests — it caught the roster's own
comment on the first run. The golden moved once (the eight identity files);
the V1 baseline carries the same substitution beside its stage-35 note; ten
test modules, PLAN.md, EXPLORE.md, one OPERATIONS example and one code comment
name personas now; [tests/test_fixture_personas.py](tests/test_fixture_personas.py)
decrypts the rosters and pins that a real roster cannot return. The live
configuration is untouched. The substitution table is the operator's,
outside the repository. The plan as it left the worksheet:


**Why**: the fixture's rosters are the 19 real users and the real group
rosters copied from the live tree at stage 28
(`tests/fixtures/config/README.md`), and stage 33 encrypted them to a
TEST identity that is itself committed (`tests/fixtures/config/.age-identity`),
so anyone holding the repository can decrypt them: the encryption
exercises the mechanism and protects nothing. Stage 34 left every
DERIVED address in clear by decision, so the golden's `users-data.tf`
and `meta-state/identity.yaml` carry real usernames as `<name>@noaa.gov`;
the same people appear in the V1 baseline, in about ten test modules that
use them as test data (`test_group_module_call.py`,
`test_v2_explore_identity_mgmt.py`, `test_user_required_names.py`,
`test_user_builder_root.py`, `test_user_ro_builder_root.py`,
`test_group_gid.py`, `test_v2_gate4_identity_storage.py`,
`test_v2_detach.py`, `test_v2_encrypted_values.py`,
`test_v2_gate1_layout_equivalence.py`), in [PLAN.md](PLAN.md),
[EXPLORE.md](EXPLORE.md), [BILLING_REMINDERS.md](BILLING_REMINDERS.md),
one [docs/OPERATIONS.md](docs/OPERATIONS.md) import example and one
comment in `ansible_builder.py`. The publication note lists this
redaction as a precondition of the swapover (§40); it is a stage because
it moves the golden by design and touches every test that pins a name.
The live configuration is untouched: its rosters are real by decision.

1. **The personas**: an invented roster with the same SHAPE as today's —
   19 users, ten with an explicit `email:` and nine derived, the one
   "exact OPA username casing" case, the two commented-out example users
   kept, the same members/admins per group — encrypted to the same TEST
   identity with `cs-image-system encrypt`. The fixture's
   `default_user_email_template` becomes `{{ user.name }}@example.invalid`
   so a derived address can never be a real one, and the fixture's
   `public_safe.allow` loses `@noaa.gov`: from then on the gate over this
   repository (`just public-safe`, CI) catches a real address returning
   anywhere outside `docs/`, `*.md` and the tests. The substitution table
   (real → persona) is NOT committed; it lives with the operator.
2. **Everything that pins a name follows**: `just golden-regen` moves the
   golden once (`users-data.tf`, `meta-state/identity.yaml`, the five
   `group-*.tf`); the V1 baseline's `users-data.tf` and `group-*.tf` get
   the same substitution with a header note, the way stage 35's redaction
   did, and the gate-1 tests (line-order survival, byte-identity of
   unchanged files) still pass; the test modules above switch to the
   personas; the two documents, the OPERATIONS example and the code
   comment lose the real names. The operator's own address in
   PLAN.md/BILLING_REMINDERS.md is the operator's call.
3. **The check that keeps it so**: a test decrypts the fixture's rosters
   with the TEST identity and asserts every address is on an example
   domain and no username appears in `docs/` or the root documents; stage
   34's invariant test (no declared plaintext in the emission) keeps
   running over the new roster.
4. Records: ledger; the fixture README's provenance paragraph rewritten
   (layout from the live tree at 5420f7b, people synthetic since this
   stage); the redaction item in the publication note struck. Feature
   branch `feature/synthetic-personas`, squash-merged, kept. About a day.

### 35. DONE 2026-09-15 — a commit-time gate over everything staged

**Built on feature/public-safe-gate, proven 2026-09-15 (ledger 90).** One
scanner ([public_safe.py](packages/base/src/cs_image_system/base/public_safe.py))
reads bytes, zipped plans included, refuses plans, state, tfvars and key
material by name and the secret shapes everywhere; addresses and long
tokens outside prose and tests; allowances by decision in `cfg/_config.yml`
`public_safe.allow`. It runs in `commit_meta_state` before the index is
touched, in the plain `.githooks/pre-commit` of both repositories, as
`just public-safe` (CI's `verify` job runs it) and `just public-safe-live`.
Both trees scan clean; the hook refused a fake key and a forced plan in the
live repository and passed its real commit. Item 1's email rule is scoped by
§34's decision (derived addresses allowed); the GCP marker fires only beside
a private key, so documentation may name the shape. Original plan for
reference:

**Why**: `assert_public_safe` (meta_state.py:48–79) is the only guard,
and it could not have stopped a single finding of the 2026-09-15 audit:
it runs only on the seven meta-state YAML writes, walks the Python
object rather than the bytes, and knows five patterns (PEM header, AKIA,
ASIA, Slack, GitHub tokens) — not a JWT, not a UUID-shaped key, not a GCP
service-account JSON, not an email, and never a `tfplan`. The leak was in
`generated/`, in binary, at commit time. The gate has to sit where the
commit happens, see every staged path, and read bytes.

1. **The scanner**: one module, `base/public_safe.py`, with the extended
   pattern set (JWT `eyJ[A-Za-z0-9_-]{20,}`, PEM bodies, AWS keys, GCP
   `"type": "service_account"`, `private_key_id`, Slack/GitHub tokens,
   `TF_VAR_*=` assignments with values, email addresses, an entropy
   check for long base64/hex strings) and a hard refusal list by path
   (`tfplan`, `*.tfstate*`, `*.tfvars` with values, `.envrc`,
   `*.pem`, `.private_key.*`, `.public_key.json`); it opens zip/DEFLATE
   members (a `tfplan` is a zip) so a compressed plan is scanned, not
   skipped. `assert_public_safe` becomes a thin call into it.
2. **Where it runs**: (a) `commit_meta_state` scans the staged set after
   `git add` and before `git commit`, refusing with the path and the
   pattern — the run never records a secret; (b) a `just public-safe`
   recipe scans a whole tree (the live repository or this one) and is
   what the operator runs before a swapover; (c) a plain git hook
   (decided 2026-09-15: a committed `.githooks/pre-commit` that
   `just init` installs with `git config core.hooksPath`; no framework)
   in both repositories so a hand commit is gated too; (d) the CI
   `verify` job runs it over the checkout.
3. **Allowlist by decision, not by silence**: identifiers the operator
   accepted as public (account id, project number, resource ids) are
   listed in `cfg/_config.yml` under `public_safe.allow` with the reason,
   so the scanner's email rule does not fire on `csis-runner@…iam.gserviceaccount.com`
   and the entropy rule does not fire on AMI ids; anything else that
   matches refuses.
4. **Tests**: each pattern with a positive and a negative; a zipped
   `tfplan` fixture carrying a fake JWT is refused; the refusal list by
   path; the allowlist; `commit_meta_state` refusing and leaving the
   index untouched (the relocation test's shape). Records: ledger;
   OPERATIONS "public-safe by construction" replacing the sentence about
   the meta-state scan. Feature branch `feature/public-safe-gate`,
   squash-merged, kept. Two days.

### 34. DONE 2026-09-15 — sensitive values never enter the emission

**Built on feature/emit-by-reference, proven 2026-09-15 (ledger 89).**
The emitted HCL carries the SAME `ENC[age:…]` ciphertext the YAML
carries: a `Decrypted` value keeps its marker, the collector's
`sensitive_ref` turns it into `local.sensitive["key"]` and emits one
`data "external" "sensitive"` per root running `cs-image-system decrypt
--json`; user lookups and declared-encrypted workspace credentials go
through it; `commit_meta_state` never stages plans, state, tfvars or key
material. Decided on the way (2026-09-15): a DERIVED email is public by
construction and stays plaintext — the rule is "no declared-encrypted
value but a username in clear", not item 1's "emails never in plaintext";
item 3's user-data change was already true (the token reaches user data
by reference since the IaC-managed tokens); item 4 was already true
(identity.yaml holds usernames). Golden moved in the two identity-root
files; live regenerated, planned for real and pushed. Original plan for
reference:

**Why**: the configuration repository commits `generated/` by design
(stage 28), and the audit found the leak lives there: 19 real email
addresses materialised in `okta-tf-users-user-generation-users-data.tf`
(the `data "okta_user"` lookups), rosters in `meta-state/identity.yaml`,
and — in the history — enrollment tokens in plan files and a rendered
token in `aws_instance.user_data`. Encrypting a field (§33) does not
help if the plaintext is then emitted. The Okta workspace already shows
the pattern that does: its credentials are wired as terraform variables
(`var.<team>_key`), "so nothing secret enters HCL", and the values reach
terraform only through `TF_VAR_*` at apply time. This stage generalises
that: any value classed sensitive is emitted as a variable reference,
and the run supplies the value through the environment from the
decrypted configuration.

1. **Classify** (decided 2026-09-15): member **emails** — declared or
   derived from the template — are private data and must never be
   emitted in plaintext; so are any other user-record fields the lookups
   emit, and anything §33 decrypts; enrollment tokens (already variables
   on the instance root; the rendered user-data copy in state is the
   gap). Usernames stay public (the 2026-08-25 membership ruling).
   **Infrastructure identifiers stay in plaintext** (the account id,
   project number, VPC/subnet/SG ids, AMIs, bucket names): accepted as
   public for now; if the operator later wants one hidden it becomes a
   loaded environment variable or an encrypted value through the same
   machinery, which is why the type is generic.
2. **Emit as a decryptable string** (decided 2026-09-15, replacing
   "emit by variable reference"): the emitted HCL carries the SAME
   `ENC[age:<base64>]` ciphertext the YAML carries, and terraform
   decrypts it at plan time through an `external` data source whose
   program is `cs-image-system decrypt --json` (one call per root,
   decrypting a map of ciphertexts, the identity from
   `CSIS_CONFIG_IDENTITY` in the runner's environment); the results are
   wrapped in `sensitive()` and the user lookups (`data "okta_user"`) read
   them. So the committed emission is readable by anyone and decryptable
   only by a recipient, the source and the emission carry one ciphertext
   per value, and a rotation re-encrypts both by regeneration. Plans and
   state then hold the plaintext as they do today for variables — which
   is why they are never committed (§35). `launch_params` and the
   read-models record names by reference, as they already do for gids.
3. **Plans and state**: `tfplan`/`*.tfstate*` are already ignored in the
   live repository; the runner also refuses to stage them under
   `--commit` (belt and braces with §35). The rendered `user_data`
   containing a token is replaced by a `templatefile` whose token input
   is a sensitive variable, so state carries the reference — verify with
   a `tofu show -json` of a dry plan that no `eyJ` or email literal
   appears.
4. **Meta-state**: `identity.yaml`'s rosters become usernames only (the
   design ruling of 2026-08-25 on membership stands unless the
   publication decision changes it); `verifications.yaml` keeps hostnames
   and build ids, no addresses.
5. Golden: this stage MOVES the golden by design (references replace
   literals in the user lookups); read the diff and accept it. Live:
   `just config-drift` after the live repository regenerates; a dry
   `--commit` run's staged set contains no email literal (a test greps the
   emission). Records: ledger; OPERATIONS. Feature branch
   `feature/emit-by-reference`, squash-merged, kept. Three to four days.

### 33. DONE 2026-09-15 — encrypted configuration values

**Built on feature/encrypted-values, proven 2026-09-15 (ledger 88).**
`EncryptedStr` ([encryption.py](packages/base/src/cs_image_system/base/encryption.py),
a `PlainValidator` — the only validator kind that keeps a `str`
subclass) decrypts `ENC[age:<base64>]` at load with the identity in
`CSIS_CONFIG_IDENTITY`, refuses by name when there is none, passes
unmarked values through, and yields a `Decrypted` str whose repr hides
it. Element-level on the rosters (`members`/`admins`; `name`,
`first_name`, `last_name`, `email`) and the Okta workspace's
`key`/`secret`; recipients in `cfg/_config.yml`; the pure-Python `age`
package in the standard format. The CLI grew `encrypt`, `decrypt` and
`reencrypt` (a command of its own, not `encrypt --reencrypt` as written
below), exempt from the configuration load. The fixture's rosters are
encrypted to a committed TEST identity with the golden byte-identical;
the live rosters (87 values) are encrypted to the four recipients and
pushed; the bar is green with no identity in the shell. Left for §34:
the derived email is plain in the loaded model and the plaintext still
reaches the emission. Original plan for reference:

**Why**: a value that belongs in the configuration but must not be
public — an API key or secret the identity root needs, an email a user
lookup needs — has no home today except `.envrc`, which the live tree
cannot carry. The model layer can give it one: Pydantic runs validators
before a value lands in a field, so an annotated type can recognise an
encrypted value, decrypt it with a key from the environment, and hand
the field its plaintext; the loader needs no other change, since the
converter structures every model through the same validators (stage
23). The cryptography must not be invented: the pattern — anyone with
the public key encrypts, only the holder of the private key decrypts — is
a sealed box, and age (X25519 identities, Python bindings) or libsodium's
sealed boxes (PyNaCl) are made for it. The public key lives in the
repository so anyone can add a value; the identity lives in `.envrc`
locally and in a repository secret in CI, the channel every other
credential already uses. Asked and answered 2026-09-15. What this stage
does NOT fix on its own: the emission (§34) and the commit gate (§35);
an encrypted field whose plaintext is then written into committed
terraform has moved the leak, not closed it.

1. **The scheme — age, decided 2026-09-15.** The standard age format
   (`age-encryption.org/v1`, X25519 recipients `age1…`, identities
   `AGE-SECRET-KEY-1…`), so the operator can also encrypt by hand with the
   `age` CLI and rotate with `age-keygen`. The implementation is the
   **pure-Python `age` package** (PyPI `age`, 0.5.1 at the time of
   writing, on PyNaCl and `cryptography`) — verified 2026-09-15 to
   generate a keypair and round-trip a value in the standard format; a
   Rust binding is not worth its build cost for a handful of decryptions
   performed once per run. Each element is its own age file: ~200 bytes
   of ciphertext per value, carried base64 on one line as
   `ENC[age:<base64>]` so YAML stays readable, a diff shows which entry
   changed, and an unmarked value is passed through untouched. The
   identity comes from `CSIS_CONFIG_IDENTITY` (the key itself or a path
   to an identity file) — a GitHub repository secret for CI, `.envrc` for
   a developer (decided 2026-09-15). **Multiple recipients, decided
   2026-09-15**: every value is encrypted to ALL recipients at once — one
   identity per person plus one for CI, never a shared private key — and
   the recipient public keys are committed in `cfg/_config.yml` as
   `encryption.recipients: [age1…, …]` with a comment naming each holder,
   so `just cli encrypt` needs no argument for them. Adding or removing a
   recipient re-encrypts every value (`just cli encrypt --reencrypt`, one
   pass over the declared field paths); a removed person's identity can
   no longer open the new ciphertext, which is the whole point. **The
   four identities exist (generated 2026-09-15 with the pure-Python
   library, never committed): CI, Mykel Alvis <mykel.alvis@gmail.com>,
   Mykel Alvis Lynker <malvis@lynker.com>, Zach Wills
   <zwills@lynker.com> — identity files under
   `~/.config/cs-image-system/age/` (mode 0600) on the operator's
   machine, public keys in `recipients.txt` beside them, to become
   `encryption.recipients` when this stage lands.** The CI identity goes
   into the `CSIS_CONFIG_IDENTITY` repository secret; a person's into
   their `.envrc`; Zach's must be handed over out of band (or he
   generates his own and sends the public key, which is the better
   practice from the second person on).
2. **The type**: `EncryptedStr = Annotated[str, BeforeValidator(...)]` in
   `base/models/` (and the contract package when §30 lands): a marked
   value is decrypted at load; a marked value with no identity in the
   environment is a load-time refusal naming the variable, never a
   silent plaintext; an unmarked value passes. **Field-level, element by
   element** (operator requirement, 2026-09-15): the type is the element
   type wherever a collection is encrypted — `members: list[EncryptedStr]`
   encrypts each member separately with the public key and decrypts each
   on its own at read time, a list may mix marked and unmarked elements,
   and the same holds for a mapping's values (`dict[str, EncryptedStr]`);
   never a whole list or file as one ciphertext, so one entry can be
   added, rotated or removed without touching the others and a diff shows
   which entry changed. A `SecretStr`-style repr
   so a decrypted value never appears in a log, a run summary, a
   validation error or the meta-state (`assert_public_safe` stays as the
   backstop). `just cli encrypt <value>` (and `decrypt`, for the
   operator only) wrap the library so nobody hand-rolls the format; the `age` CLI
   produces the same ciphertext, so either tool works.
3. **Where it is used first**: the live repository's rosters — every
   `members:`/`admins:` element in `groups/group-*.yaml` and every
   `name`/`first_name`/`last_name`/`email` in `groups/users.yaml`, which
   stay in place in plaintext through the swapover and are encrypted in
   place, entry by entry, here; the group builder's credential fields
   (`key`/`secret`, today DEFAULT + `TF_VAR_<team>_*` from the
   environment via `_require_tfvar`); anything else the audit classed
   (P) or (S) that the configuration must carry. `just cli encrypt`
   takes a file and a list of field paths so the roster encryption is one
   command, not a hand edit per entry. `default_user_email_template`
   stays (decided 2026-09-15): it exists so lookups can derive an address
   rather than list one; the derived address is private data and §34
   emits it as a decryptable string like any declared one.
   The existing environment path keeps working — a declared encrypted
   value wins over the environment, an absent one falls back to it.
4. **The fixture**: a TEST keypair committed with the frozen fixture
   (`tests/fixtures/config/.age-identity`, synthetic data only), the
   fixture's synthetic personas encrypted with it, the harness setting
   the identity variable; the golden is byte-identical when nothing
   emitted changes (the decrypted plaintext reaches the emission exactly
   as before — which is §34's problem, made visible here).
5. Records: ledger; OPERATIONS "Credential contract" gains the encrypted
   form and the key-management rule (rotation = re-encrypt; the identity
   is never committed). Feature branch `feature/encrypted-values`,
   squash-merged, kept. Two to three days.

### 32. DONE 2026-09-15 — the base-only generation path and the V1 run residue

**Built on feature/retire-base-only-path, proven 2026-09-15 (ledger 86).**
The triage decided the loader's base-only mode was a leftover: with the
switch on it read no item kinds at all, no command could request it, and
the two tests that passed it assert equally on a full load. Gone with it:
the base-image generation directory (created on every load, written by
nothing), both state markers, the base final-execution path, the
between-phases sleep and its `sleep_between_steps` key (dropped from
both configurations in the same step), five unread constants, and the
loader's positional `base_only` parameter — whose removal shifted the
CLI's positional call by one, caught by pyright. `--base-only` keeps its
one meaning. Golden byte-identical; the live configuration validates
without the key and no longer grows the directory. Original plan for
reference:

**Why**: the same family as §31, found while answering "do `basic` and
`generated_base_image` have any use?" in the live tree (2026-09-15; the
stray empty `basic/` was removed by hand). `generated_base_image/` is
created on every configuration load —
[global_context.py:735](packages/base/src/cs_image_system/base/global_context.py#L735)
makes the parent of a base-image state marker that nothing writes — and
never written to: the V2 loader always passes `base_only=False`
([cli.py:905](packages/system/src/cs_image_system/system/cli.py#L905)),
so the context's `_base_only` switch is never on from the CLI, the
base-image lifecycle emits under `generated/base-image/` like every
other, and `--base-only` now means only "run the base-image lifecycle
alone". What the switch still steers is dead or test-only: the
generation path
([:265](packages/base/src/cs_image_system/base/global_context.py#L265)),
the state marker
([:317](packages/base/src/cs_image_system/base/global_context.py#L317)),
the final-execution path
([:445](packages/base/src/cs_image_system/base/global_context.py#L445)),
and which item kinds the loader reads
([:748](packages/base/src/cs_image_system/base/global_context.py#L748)),
a mode two tests in
[test_config_resolution_e2e.py](tests/test_config_resolution_e2e.py)
exercise by passing `True` although no command can. Alongside it, the
residue ledger 85 deferred: `sleep_between_phases` (a property with no
reader now that §31 deleted the loops; fed by the `sleep_between_steps`
config key) and the two state-marker paths (`.image-action-state.txt`,
`.base-image-state.txt`: created-and-deleted at load, written by nothing
since §31), plus four constants that nothing reads
(`BASE_IMAGE_FINAL_EXECUTION_PATH`, `FINAL_EXECUTION_PATH`,
`BASE_IMAGE_STATE_MARKER`, `STATE_MARKER`). **Live and untouched**:
`final_execution_path` (the gating script) and
`sleep_before_finalization` (read by `finalization.py`, pinned by the
headless test).

1. **Triage the base-only load first.** The loader's `base_only`
   parameter gates `_read_item_kind` at
   [global_context.py:748](packages/base/src/cs_image_system/base/global_context.py#L748);
   the two e2e tests that pass `True` assert on a partial load. Decide
   whether a "read only the base item kinds" mode is a capability (then
   it needs a command that reaches it) or a V1 leftover (then the tests
   load fully and the parameter goes). The resolver's own `is_base` is
   NOT this switch — it comes from the lifecycle
   ([run_lifecycles.py:178](packages/base/src/cs_image_system/base/commands/run_lifecycles.py#L178))
   and stays.
2. **The base-image generation path goes**: the `base_image_generation_directory`
   config key and its default, the context's `_base_image_generation_path`,
   `_base_image_state_marker`, `_base_image_final_execution_path`,
   `base_image_generation_path`, the `_base_only` branches in
   `generation_path`/`state_marker`/`final_execution_path`, the
   equal-directories check at
   [:1274](packages/base/src/cs_image_system/base/global_context.py#L1274),
   and the mkdir. After this a load creates nothing under the root but
   `generated/`; the empty `generated_base_image/` in the live tree is
   then deleted by hand (it is untracked) and the ignore for it in this
   repo's `.gitignore`, if any remains, goes.
3. **The state markers go**: `_state_marker`, the `state_marker` property,
   `_make_parent_and_delete` of both at load, the stage-22.5 comment line
   in both `_config.yml` files that still documents the old key.
4. **`sleep_between_phases` goes** with its `sleep_between_steps` config
   key — removed from the model AND from both configurations in the same
   step (an unknown key is refused at load); `sleep_before_finalization`
   stays.
5. **The four unread constants go**; the `is_base(ctx)` CLI helper and
   `--base-only` keep their one remaining meaning (select the base-image
   lifecycle) and their help text says so.
6. Records: ledger; OPERATIONS' flag table already describes `--base-only`
   as lifecycle selection — confirm; DESCRIPTION's "generated_base_image"
   mention, if any. Golden byte-identical (nothing emitted came from this
   path); bar green; pyright at 0 errors; `just cli validate` and
   `just config-drift` against the live repository after its
   `sleep_between_steps` line is dropped. Feature branch
   `feature/retire-base-only-path`, squash-merged, kept. About an hour.

### 31. DONE 2026-09-15 — the V1 step machinery behind the lifecycle phases

**Built on feature/retire-v1-steps, proven 2026-09-15 (ledger 85).** One
phase enum remains, all 34 members kept as extension points and
documented as such; the base-image enum, the step/state/function-type
classes, the two step lists and two function-name mappings, the V1 phase
loops, five V1 stub command modules, the dead default-image-resolution
module, the orphaned run-result type, the eight base-prefixed wrappers,
V1's validation function, the config model's `predefined_lifecycle`
field and its all-comment file in both configurations are gone — 989
lines, 22 files. The one live function in the old build module moved to
its only caller. Golden byte-identical; the live configuration validates
without the file. Original plan for reference:

**Why**: [lifecycle.py](packages/base/src/cs_image_system/base/lifecycle.py)
carries two phase enums that must mirror each other by hand — the FIXME at
line 187 says so — plus a `LifecycleStep` class, state and function-type
enums, two step lists and two function-name mappings built by filtering
enum values on their `pre-`/`post-` string prefix. All of it served the V1
phase loops in
[commands/build.py](packages/base/src/cs_image_system/base/commands/build.py)
(`build_base_image_lifecycle`, `build_execution_lifecycle`), which have had
**zero callers** since `build-all` became a V2 alias
([cli.py:146](packages/system/src/cs_image_system/system/cli.py#L146)).
Measured 2026-09-15: the V2 runner's `_run_phase`
([run_lifecycles.py:183](packages/base/src/cs_image_system/base/commands/run_lifecycles.py#L183))
uses its own phase→function table and exactly one function from build.py,
`execute_before_or_after_phase` (every builder's before/after hooks); the
14 `predefined_base_*` functions are referenced once each, by the dead
mapping; the `predefined_lifecycle:` configuration key's only file,
[predefined-lifecycle.yml](tests/fixtures/config/cfg/predefined-lifecycle.yml),
is entirely commented out; and nothing in the emission comes from that
path, so the golden cannot move. The enum's 34 members themselves stay:
a plugin-registered lifecycle may bind any of them (`LifecycleSpec.phases`)
and the finalization script orders deferred commands by enum position, so
the unused members are extension points, not dead weight (decided
2026-09-15 after the question "might plugins need those phases").

1. **build.py goes.** Delete `build_base_image_lifecycle`,
   `build_execution_lifecycle`, `run_for_phase`, `write_to_state`,
   `set_state`; move `execute_before_or_after_phase` into
   `run_lifecycles.py` (its only caller); delete the module.
2. **lifecycle.py keeps one enum.** Delete `BaseImageLifecyclePhase`,
   `BASE_IMAGE_LIFECYCLE_STEPS`/`_FUNCTIONS`, `LIFECYCLE_STEPS`/`_FUNCTIONS`,
   `LifecycleStep`, `ExecutionLifecycleState`,
   `ExecutionLifecycleFunctionType`, `DEFAULT_PLACEHOLDER_FUNCTION` and the
   FIXME; `ExecutionLifecyclePhase` stays with all 34 members and gains a
   docstring saying which the built-in lifecycles claim and that the rest
   are bindable by registered lifecycles.
3. **The config model and context.** Delete the `predefined_lifecycle`
   field and the `lifecycle` / `base_image_lifecycle` properties from
   [ia_config.py](packages/base/src/cs_image_system/base/models/ia_config.py)
   and the `_lifecycle` / `_base_image_lifecycle` holders from
   `global_context.py`; remove `cfg/predefined-lifecycle.yml` from the
   frozen fixture AND the live repository in the same step (an unknown key
   is refused at load, so a stale file would be a hard stop — the file is
   all comments today, but the key must not be re-introduced).
4. **The predefined functions.** Delete the 14 `predefined_base_*`
   functions. For the six non-base ones with three references each
   (`validation`, `test`, `commit`, `execution`, `verify`, `cleanup`),
   list the callers first; delete those whose only callers were the
   mapping and the dead loops, keep any the V2 runner or a test invokes.
   `predefined_resolve`, the five `predefined_*_generation`,
   `predefined_default_image_resolution` and `predefined_finalization` are
   live and untouched.
5. **Records**: ledger; [DESCRIPTION.md:93](DESCRIPTION.md#L93) stops
   calling test/commit/execute/verify/cleanup "currently stubs" (they are
   enum members with no code behind them, bindable by a plugin lifecycle);
   OPERATIONS' lifecycle paragraph names the extension point. Golden
   byte-identical, bar green, pyright at 0 errors. Feature branch
   `feature/retire-v1-steps`, squash-merged, kept. About half a day.

### 28. DONE 2026-09-13 — the live configuration is independent of testing

**Built on feature/config-independence, proven 2026-09-13 (ledger 80).**
The tests own a frozen fixture (`tests/fixtures/config/`, a byte copy of
the 47 tracked non-meta-state files, golden byte-identical over it) and
nothing under `tests/` reads a live tree — enforced by
`tests/test_fixture_independence.py` and a structural rule in the Justfile
contract. The live configuration is the `cs-image-system-testconfig`
repository checked out beside this one (`CSIS_CONFIG_ROOT` overrides;
`config-guard` exits 2 with the clone command when it is absent, never on
`just test`); `test_folder/` is gone. The live configuration carries no
overlays: `--undeclare <kind>:<name>` replaced the one operational
overlay, the tests' copies stay in the fixture, the 13 live-proof overlays
moved to `docs/history/overlays/`. `full-test` copies the live sibling
into the sibling shape without its `.git`; `release` commits the mod-test
evidence into the live repository; a run's commit carries only the paths
it staged. Proven live: `validate`, a headless dry `run --all`, `state
query --strict` (only `stale`), a dry `--commit` landing one commit in the
sibling with meta-state and 82 generated files, and a dry
`gce-decommission` through the flag. Original plan for reference:


**Why**: `test_folder/` is both the suite's fixture and the live sandbox
configuration — the last structural residue of DESIGN §3B, and the cost
shows daily: every live config change churns the golden and the gate-1
baseline, the harness installs fixture subjects over live entries, and
`test`/`test2` are commented out of the live tree because the suite
needs them. Decided 2026-09-13 (superseding the deferred
[PLAN.md](PLAN.md) "Configuration repository separation"): the sibling
checkout `cs-image-system-testconfig` — already committed, clean, and
carrying `module_source_base: ../cs-image-system-3/tfmodules` — becomes
the live configuration and a viable live example; the tests own a
frozen copy that no live run touches; `just verify` passes with no live
configuration on the machine; no submodule; `test_folder/` is removed.
`.claude/CLAUDE.md` names that repo as the source of configuration for
testing purposes; this stage reads it as: the fast suite owns a frozen
copy, and every recipe that needs a *real* tree reads the sibling.
See [GOLDEN.md](GOLDEN.md) for why the golden is the proof at each step.

1. **The frozen fixture** at `tests/fixtures/config/`: the 47 tracked
   non-meta-state files of today's `test_folder` (use `git ls-files` as
   the manifest, not `cp -R`, which drags in `.DS_Store` and the provider
   cache). No meta-state seeds: `copy_config` already drops them, the
   tests that need records seed their own, and zero seeds is what keeps
   the golden byte-identical — the proof the copy is faithful. Drop the
   self-referential `working_directory: ./test_folder` from its
   `_config.yml`; keep `module_source_base: ../tfmodules`. A README
   records provenance (source sha), that it is frozen and owned by the
   tests, and where the live configuration lives. Keep the harness's
   instance injection from `tests/fixtures/test_instances.yaml` unchanged;
   folding those subjects into the fixture is a later tidy that would
   move the golden.
2. **Every reader repointed.** `FIXTURE_CONFIG` in `tests/v2_support.py`
   moves 34 files at once. The direct live-tree readers import it
   instead: `tests/test_config_resolution_e2e.py` (five sites, including
   its two private copytrees), `tests/test_v2_gate1_layout_equivalence.py`
   (the module-level playbook read), `tests/test_v2_justfile_contract.py`
   (the preflight invocation). Purge the literal `test_folder` from test
   docstrings, drop the dead `packer-ebs-ansible` ignore pattern, and add
   `tests/test_fixture_independence.py`: the literal appears zero times
   under `tests/`, and `FIXTURE_CONFIG` is the frozen path. The GCE-cycle
   overlay test validates the fixture's copies (step 3 leaves no overlay
   in the live configuration for it to check).
3. **The live configuration carries no overlays.** The one overlay a
   recipe still passes, `gce-cycle-decommission.yaml`, does two things:
   sets the apply knob, which `--apply-runtime` has covered since stage
   12, and undeclares `gce-test` for one invocation so a leftover
   standing instance is destroyed rather than re-verified (ledger 71).
   The undeclare form is eleven lines in `global_context.py`
   (`apply_overlays`) that pop the name from the declaration dict; it
   became an overlay form (ledger 68) only because overlays were the
   mechanism to hand. Replace it with a repeatable global option,
   `--undeclare instance:<name>` / `storage:<name>`, applied at the same
   point, and make `just gce-decommission` flags only. The overlay
   `undeclare` form stays for the tests that use it. Then the remaining
   overlays sort by role: `gce-apply.yaml`, `gce-cycle-launch.yaml` and
   `gce-cycle-decommission.yaml` are superseded and go, with the overlays
   README corrected; the 13 proof records (`proof-*`, `aws-scratch-*`,
   `scratch-*`, `aws-ephemeral-test2`, `preflight-short`) move to
   `docs/history/overlays/` beside the ledger that cites them;
   `gce-cycle-storage-teardown.yaml` and whatever the tests copy stay in
   the fixture. The rule this leaves, recorded in the overlays README and
   OPERATIONS: an overlay does nothing unless an invocation names it with
   `--overlay`; a named overlay that is missing is a refusal, not a skip
   (`load_overlay`, and the generated apply-check); after this stage no
   recipe names one. The live repo may carry overlays for one-off
   operations or none at all; the system behaves identically either way.
   Overlays remain a testing and proof device, resolved from the working
   directory, so any move is followed by regeneration.
4. **The Justfile takes a live root.** `config_root :=
   env("CSIS_CONFIG_ROOT", "../cs-image-system-testconfig")`; `gce_cli`,
   `test-mods`, `v2-dry-run` and `cli` use it, and `gce-decommission`
   passes `--undeclare instance:gce-test` instead of an overlay path. A
   `[private] config-guard` fails with exit 2 and a clear message (what
   is missing, how to clone the sibling, the `CSIS_CONFIG_ROOT`
   alternative, and that `just verify` does not need it) and gates only
   the recipes that read the live root — never `test`/`verify`.
   `full-test`'s dry-run leg copies the live sibling into the sibling
   shape (`$copy/cs-image-system-testconfig` beside
   `$copy/cs-image-system-3/tfmodules`) so its module paths resolve, and
   passes no `--commit`. `release`'s dirty-tree exemption for
   `test_folder/meta-state/mod-tests.yaml` becomes a requirement that the
   evidence exists in the live root and that root is clean. The contract
   test's `cp -R test_folder tfmodules` needle is replaced, and it gains
   the structural rule that `test`'s dependency closure never names the
   live root.
5. **Remove `test_folder/`.** After 1–4 are green: `git rm -r
   test_folder`, drop the `.gitignore` line for its generated trees, the
   ruff and pyright excludes, and the two `.vscode/launch.json` entries;
   move the doc references (`README.md`, `DESCRIPTION.md`,
   `docs/DESIGN.md` §3B ruling and the relocation blocker,
   `docs/OPERATIONS.md`, `EXPLORE.md`) to "the live configuration" and
   "the frozen fixture". Meta-state history stays in git; the live repo
   already carries the same records.
6. **The live repo made viable as a live example**: remove its stale
   `working_directory: ./test_folder`; give it the hoisted ignore policy
   (`**/.terraform/`, `!**/.terraform.lock.hcl`, `**/target/`,
   `*.tfstate*`, `tfplan`) rather than a blanket `generated*/` — `--commit`
   is meant to commit the emitted IaC and gate 3 asserts it, and this
   repo's blanket ignore is why every live commit so far silently dropped
   that half; delete the orphaned pre-lifecycle directories under its
   `generated/`; a README stating what the tree is, the credential
   contract, that `../cs-image-system-3/tfmodules` is where its modules
   resolve, and that `--commit` commits there. Then the proof: from this
   repo, `just cli validate`, `just v2-dry-run` and `just cli state query
   --strict` against it, and one dry `--commit` run that lands a commit
   in the sibling carrying **both** `meta-state/*.yaml` and
   `generated/identity/*.tf`.
7. **Fix `commit_meta_state` while here**: it stages two pathspecs then
   runs a bare `git commit`, which sweeps in anything the operator had
   staged. Commit with the pathspecs. The live repo becomes the place
   people edit config, so this bug becomes likely.
8. Records: ledger entry; §18's dry run "against the live configuration"
   now means the sibling. Feature branch `feature/config-independence`,
   squash-merged, kept.

**Acceptance**, in order: `just verify` green after step 2; `just
golden-regen` byte-identical after step 2 (a diff means an unfaithful
copy — fix the copy, never accept the diff); `just verify` green in a
fresh clone with no sibling present after step 5;
`CSIS_CONFIG_ROOT=/nonexistent just cli validate` exits 2 with the
guard's message; step 6's proof run.

**Open before starting**: does `full-test`'s end-to-end leg target the
live sibling (as `.claude/CLAUDE.md` reads, and as step 4 is written) or
the frozen fixture? And fixture drift is the price of the split: nothing
tells you when the live configuration grows a construct the suite never
exercises until §18's dry run against the live configuration exists —
record it as accepted.

### 25. DONE 2026-09-13 — storage `parameters:` are a mapping against a list

**Built on feature/storage-parameters, proven 2026-09-13 (ledger 79).**
The declarations name the terraform modules' own variables exactly, so
they were plainly meant to take effect, but the field is `list[str]` and
nothing reads it — the live mnt_data volume is gp3 at 100 GB (model and
module defaults) rather than the gp2 at 8 GB the fixture asks for. By the
operator's decision they were commented out with that reason and the
field was left untouched in code, so the capability can be reworked
properly as §26 rather than wired up as a side effect. Original plan for
reference:

**Why**: found while moving the mapper (§23) and preserved rather than
decided, because deciding it is a semantic change. The EFS and EBS storage
builders declare `parameters:` in the fixture as a MAPPING
(`performance-mode`, `encrypted`, `volume_type`, `tags`), the field is
`list[str]`, and iterating a mapping yields its KEYS — so the system has
only ever held `['performance-mode', 'encrypted', 'tags']` and discarded
every value. §23's converter reproduces that exactly so the port stayed
behaviour-neutral.

1. **Nothing reads it**: `get_parameters()` has no callers outside the
   model and protocol, and `parameters` reaches no emitted output. So this
   is free to decide either way.
2. **Decide what it means**: a mapping of provider-specific settings (make
   the field `dict[str, Any]` and use it), or dead (comment it out of the
   fixture with a reason, as §22 did with its findings).
3. If it becomes real, check whether those settings SHOULD reach the
   emitted terraform — `encrypted` and `volume_type` look like they were
   meant to.
4. Feature branch `feature/storage-parameters`, squash-merged, kept.

### 24. DONE 2026-09-12 — the query-result remap was dead

**Built on feature/query-result-remap, proven 2026-09-12 (ledger 78).**
Written as "eight of thirteen keys are dropped", which was true and not
the point: the dict had no `runtimes`, which Image has required since the
repository's second commit, so the call always raised and a bare except
always swallowed it. The function never returned an Image on either
cloud, and its only caller had no callers. Deleted by the operator's
decision, with a note at each site. Nothing observable changed. Original
plan for reference:

**Why**: found while doing §22 and left alone on purpose, because fixing
it changes what an `Image` built from a cloud query carries.
`image_from_query_result` (in both `aws_utils` and `gcp_utils`) builds a
thirteen-key dict and structures it into `Image`, which accepts five of
them. The other eight are written in **kebab-case where every model field
is snake-case**: `output-image-name`, `machine-type`, `image-identifier`,
`primary-disk-size`, `auto-update`, `source-image`, `runtime`, `os`. All
eight are dropped in silence, exactly as §22's other findings were.

1. **It is live on GCE and dead on AWS**: `gcp_runtime_builders` calls it;
   the AWS caller is commented out. So a fix changes GCE behaviour first,
   which is why it was not folded into §22.
2. **Decide per key** whether the model should gain the field or the key
   should go, as §22 did — `image-identifier` and `source-image` look like
   they were meant to matter.
3. **Expect emitted output to move.** Unlike §22, this one cannot be
   assumed neutral: regenerate the golden and read the diff before
   accepting it, and check the GCE bake path end to end.
4. Feature branch `feature/query-result-remap`, squash-merged, kept.

### 23. DONE 2026-09-12 — pydantic as the mapping and validation framework

**Built on feature/pydantic-models then feature/pydantic-mapping, proven
2026-09-12 (ledger 76).** Branch one swapped the decorator in 64 modules
and nothing else; branch two replaced the converter's ~190 lines with a
PydanticConverter behind the same two verbs, reproducing every old hook
deliberately. The golden regenerated byte-identical throughout, which is
the only reason a change this wide could be trusted. §20's alias remains,
by decision, as its own stage. Original plan for reference:

**Why**: TRIAL-003 (2026-09-12, `feature/trial-003-pydantic`) ported the
model layer and measured it. The fixture validates, a full `run --all`
generates, **the golden regenerates byte-identical**, `just typecheck`
reports 0 errors, and the suite is 535 passed / 6 failed from two causes
that are themselves findings. The port cost **one import line in each of
68 files**, because `pydantic.dataclasses.dataclass` preserves everything
this codebase reflects on — `is_dataclass()`, `fields()`,
`field(metadata=...)`, inheritance and `__post_init__`. That is the whole
reason it is cheap: the orchestrator's 323-line `TemplateResolver`, which
walks `fields(obj)` and the `fk_field` / `templated_field` /
`deferred_list_field` metadata, **survives untouched**. Only the 194-line
converter section is replaced. It also subsumes §20, most of §21 and the
hard half of §17.

Take it in two branches; do not do both at once.

### Branch one — validation (`feature/pydantic-models`)

1. **Add the dependency**: `uv add pydantic` (2.13.5 in the trial), then
   `uv sync --all-extras`. No YAML or JSON additions are needed — PyYAML
   still loads the documents and Pydantic validates the dicts.
2. **Audit the 24 files with `__post_init__` FIRST.** Pydantic validates
   field types *before* `__post_init__` runs, so any guard whose trigger
   is a type-level violation is pre-empted and its wording lost. The
   trial saw this live: the `User` model's "non-blank first_name" message
   became Pydantic's generic "Input should be a valid string". Move those
   guards to `field_validator`s to keep their wording — the instance
   `groups` migration guard (§22) is the one that matters most.
3. **Swap the decorator** in the 68 non-test modules that declare a
   dataclass: `from dataclasses import dataclass, field` becomes
   `from dataclasses import field` plus
   `from pydantic.dataclasses import dataclass`. Nothing else changes: no
   class restructured, no field renamed, no inheritance altered. All three
   forms in use are accepted unchanged (`@dataclass(kw_only=True)` ×80,
   bare `@dataclass` ×38, `@dataclass(frozen=True)` ×9).
4. **Do not port `hashicorp-utils`** (20 dataclasses). Its `type` is HCL's
   own and its models never come from YAML; they are emission helpers.
5. **Acceptance**: `validate --root-dir test_folder` succeeds,
   `just golden-regen` leaves the golden **byte-identical**, and
   `just typecheck` reports 0 errors. Expect two test groups to fail and
   treat both as findings, not regressions: four in `test_item_kinds.py`
   pass a class that violates `ItemKind.model_cls`'s declared subclass
   contract (cattrs never checked; Pydantic does), and two in
   `test_user_required_names.py` assert the wording step 2 pre-empts.

### Branch two — mapping (`feature/pydantic-mapping`)

6. **Replace the converter's 194 lines.** `conv.structure(data, Model)`
   becomes `TypeAdapter(Model).validate_python(data)`; the rename hook
   becomes `Field(alias="type")` (this is §20); the unknown-key policy
   becomes `ConfigDict(extra="forbid")` (this is §21); `credentials:`
   becomes a model instead of `dict[str, str]` (this is §17 step 3).
7. **Reproduce the plugin dispatch** — the piece most likely to block the
   port, proven in the trial. One `model_validator(mode="wrap")` per base
   class: when the class being validated is the base, look the `type` key
   up in the registry and validate against the subclass it names;
   otherwise build, then register the instance as the side effect
   `structure_model` performs today. That keeps inheritance and rejects
   both an unknown `type` and an unknown key on the subclass.
8. **Keep write-back alias-shaped**: `dump_python(by_alias=True)` emits
   `type` again and round-trips equal, so meta-state is safe. Every
   unstructure path (`builder_model.py`'s `unstructure(self)`) must pass
   `by_alias=True`, or recorded state silently changes key.
9. **Decide the ambiguities the port makes explicit**: coercion is on by
   default, so `"30"` becomes `30` for an `int` field, and
   `primary_disk_size: str | int` accepts either without normalising;
   and the `DEFAULT` sentinel cannot be told from a literal "default" by
   validation alone. Both were true under cattrs; the port is the moment
   to choose. Per-field strict mode is available where coercion is wrong.
10. **Acceptance**: the golden stays byte-identical, and the fixture loads
    with `extra="forbid"` on — which cannot happen until **§22** lands,
    because those are the defects that stop the load.

### Sequencing

- **§22 first, regardless of this decision** — those are live defects, and
  §21 (or step 10 above) cannot pass until they are fixed.
- If §23 is adopted: **§20 and §21 are not separate stages**, they are
  steps 6–7, and §17 keeps only its base-class design work.
- If §23 is refused: §20, §21 and §17 stand as written, and the reason for
  refusing belongs in [docs/LEDGER.md](docs/LEDGER.md) so the measurement
  is not repeated.

### 21. DONE 2026-09-12 — forbid unknown keys

**Landed with §23 branch two (ledger 76).** One word in the shared
CSIS_MODEL_CONFIG covering 103 model decorators, which is what the stage
becomes once pydantic owns the mapping. It loads only because §22 had
emptied the fixture of unknown keys first. Original plan for reference:

**Why**: Allowing unknown keys in configuration objects can lead to silent failures and unexpected behavior. By forbidding unknown keys, we enforce strict validation, ensuring that only recognized and intended configuration options are used. This prevents spurious guarding activities and helps maintain the integrity of the configuration system.

1. **Disallow Unknown Keys**: Ensure that any credentials configuration object does not accept unknown keys, enforcing strict validation and preventing spurious guarding activities.
2. **Comment out any unknown keys** in the `test_folder` configuration objects to prevent them from being processed and to maintain strict validation.
3. **Update the schema definitions** to explicitly list all allowed keys, ensuring that any unknown keys are automatically rejected during validation.
4. **Review and refactor existing configuration objects** to ensure that they conform to the updated schema and do not contain any unknown keys.
5. **Depended on §22**, which LANDED 2026-09-12 (ledger 75): the fixture now carries zero unknown keys, so this stage is unblocked for the fixture. The external configuration repository (step 6) has not had the same pass. TRIAL-002 (2026-09-12, `feature/trial-002-type-field`)
   turned the rule on and the fixture would not load until six classes of
   defect were fixed; those are §22. Turning the rule on before §22 lands
   means the system cannot read its own configuration.
6. **Both trees, not just the fixture**: the rule must also be run against
   the external configuration repository, which TRIAL-001 measured as
   carrying sixteen unknown keys of its own.
7. **It stops at a dict boundary**: a field typed as a plain mapping is
   not checked, so this rule never catches a typo inside a runtime's
   `credentials:` — that is §17's base class, not this stage.
8. **Under §23 this is one config line**, `ConfigDict(extra="forbid")`,
   and the dict-boundary limit in step 7 disappears because the dict
   becomes a model. If Pydantic is adopted, this stage is §23 step 5 and
   not separate work. Note what TRIAL-003 proved: swapping the decorator
   alone does NOT deliver this rule — cattrs builds its keyword arguments
   from known fields, so an unknown key never reaches `__init__` and
   `extra="forbid"` never fires. The mapping has to move, not just the
   validation.
9. Feature branch `feature/forbid-unknown-keys`, squash-merged, kept.

### 20. DONE 2026-09-12 — the `type` field becomes `type_`

**Built on feature/type-field-rename, proven 2026-09-12 (ledger 77).**
13 declarations became `Annotated[str, Field(alias="type")]`; no
configuration file changed and the golden regenerated byte-identical,
because the alias carries the YAML key in and §23's unstructure writes it
back with by_alias. Far cheaper than TRIAL-002 measured: populate_by_name
means the interpreter accepts either name, so the 41 keyword arguments
moved only for the type checker. Original plan for reference:

**Why**: every configuration model carries a field named `type`, which
shadows the builtin, reads badly under a type checker, and forces
`# type: ignore` noise. TRIAL-002 (2026-09-12,
`feature/trial-002-type-field`) did the whole rename and measured it:
**the golden fixture regenerated byte-identical**, type-check clean, and
the only failing test failed for an unrelated reason (§22.6). The rename is
invisible in output because the YAML key never changes.

1. **The field becomes `type_`** (PEP 8's trailing underscore for a
   builtin clash; `_type` would read as private). Measured footprint: 16
   dataclass declarations, 68 attribute reads, 4 `getattr(..., "type")`
   strings, 24 test keyword arguments, 50 files.
2. **The YAML key stays `type`.** The orchestrator's rename hook maps the
   field onto that key when structuring AND when unstructuring, so no
   configuration file changes and no emitted output moves. This is not
   optional — the operator's constraint is that the YAML keeps `type`.
3. **`BuilderBase.type` becomes `type_`** as well, so the model and its
   builder share one name.
4. **Leave three things alone**: `hashicorp-utils`
   (`TerraformVariable`, `BackendRegistration`, `PackerVariableDecl`,
   `BlockSpec` — their `type` is HCL's own), `ModTestResult` (an internal
   record, never from YAML), and any credentials model from §17.
5. Tests: the golden must regenerate byte-identical — that is the
   acceptance proof, and it already held once.
6. **§23 landed 2026-09-12, so this is now the alias form.** Under Pydantic the rename is
   `Field(alias="type")` — one declaration per field, no converter hook at
   all — so §20 becomes part of §23 step 5. TRIAL-002's bidirectional hook
   would be thrown away. `populate_by_name` is already on, so no constructor call changes -- only the 16 declarations, 68 attribute reads and 4 getattr strings.
   Feature branch `feature/type-field-rename`, squash-merged, kept.

### 17. DONE 2026-09-12 — credentials configuration objects

**Built on feature/credentials, proven 2026-09-12 (ledger 76).**
`credentials:` stopped being `dict[str, str]`: CredentialsBase is the
declared base each provider narrows, so `credentials.profile_nme` is a
validation error naming its path — the gap §21 provably could not reach.
A mapping-shaped `get_credentials()` and `__bool__` keep every consumer
working. Original plan for reference:

**Why**: GOALS.md: "the system should manage credentials configuration objects in a consistent and secure manner". Also, certain issues exist with having
spurious guarding activities that makes it necessary to not allow unknown
keys into the configuation.

1. **Base Credentials Class**: Make a base class that handles credentials
   that can be extended for a plugin's models. Any model could have a
   corresponding credentials configuration object that inherits from this base class.
2. **Validation and Testing**: Implement comprehensive tests to ensure that
   the credentials configuration objects behave as expected, including
   rejecting unknown keys and correctly handling valid credentials.
3. **Credentials are a dict today, so §21's rule cannot reach them**: a
   runtime's `credentials:` is typed `dict[str, str]`, so cattrs treats it
   as a plain mapping. A typo inside it (`profile_nme:`) is silent now and
   would stay silent after §21, ending as a `None` profile and a fallback
   to `AWS_PROFILE` or none at all. The base class in step 1 is what closes
   that gap — forbidding unknown keys does not.
4. **§23 closes step 3 for free** if Pydantic is adopted: typing
   `credentials:` as a model rather than `dict[str, str]` makes
   `credentials.profile_nme` a validation error. TRIAL-003 caught exactly
   that on the live fixture entry. Read §23 before building the base class
   by hand.
5. Feature branch `feature/credentials`, squash-merged, kept.

### 16. DONE 2026-09-10 — the Justfile's full contract: `build`, `full-test`, `release`

**Built on feature/justfile-contract and proven 2026-09-10 (ledger 73).**
`build` packages every workspace member under `dist/`; `test` is now the
blocking fast suite (lint, typecheck, unit tests — `verify` its alias);
`full-test` adds the docker-backed modification tests and, only when the
new `preflight` command finds every runtime session present, a headless
dry `run --all` over a private copy of the fixture with `state query
--strict`, each leg reporting SKIPPED with its reason when its
prerequisite is absent; `release <version>` is gated on `full-test`,
bumps every package, commits, tags, builds and publishes only when
`UV_PUBLISH_URL` is set (the registry stays a **USER** decision; nothing
is pushed). Proven by `just release 0.1.1 yes` (20 min): the fast suite, the
modification tests on AlmaLinux 10 under docker, preflight, a dry `run
--all` and strict state query over a fixture copy, then the fifteen
would-be bumps. The first run found the EL10 mod-test container did not
exist and that a fixture copy needs `tfmodules/` beside it. Original plan for reference:

**Why**: the Justfile is the single entry point for the build lifecycle
(the contract every repo follows: `init`, `build`, `test`, `full-test`,
`release`), and it lacks three of the five. "Everything that must pass
before a release" therefore has no name, and §17's CI has nothing to
call for it. Small, no cloud.

1. **`build`**: package the workspace (`uv build` for the system and its
   plugin packages), artifacts under `dist/`; a no-op is not acceptable —
   the system is a set of installable packages.
2. **`full-test`**: everything `test` does (`verify` = lint + typecheck +
   the fast suite, the golden included) plus the slow and external legs:
   `test-mods --strict` under docker, and — only when credentials are
   present in the environment — a headless dry `run --all` against the
   fixture tree followed by `state query --strict`; each leg reports
   `skipped` loudly with its reason when its prerequisite is absent.
3. **`release`**: gated on `full-test`; version bump, tag, `build`,
   publish (the target registry is a **USER** decision — the package index
   or a git tag alone).
4. Tests: the Justfile-versus-CLI test covers the new recipes; `just
   --list` documents the five contract targets first.
5. Docs: OPERATIONS "CI shape" and the repo README name the contract.
   Feature branch `feature/justfile-contract`, squash-merged, kept.

### 15. DONE 2026-09-10 — storage lifecycle parity on AWS: `archived` for EBS, data lifecycles for S3 and EFS

**Built on feature/aws-storage-archive and proven live 2026-09-10 (ledger
72).** EBS takes the pd shape: `archive-<label>.sh` snapshots the volume
(tag `Name=csis-<label>-archive`) before the whitelisted destroy,
`active` again re-creates it FROM the snapshot (`snapshot_name` → a
tag lookup at plan time, `snapshot_id` under `ignore_changes`) and
`restore-<label>.sh` deletes the snapshot; `destroyed` from `archived`
deletes the archive; the state query expects the snapshot, not the
volume. Data lifecycles are a `lifecycle:` declaration the S3 and EFS
builders realize (bucket rule; IA/archive policy), refused elsewhere,
recorded in the read-model and reported `stale` until the resource
carries them. The live proof ran the whole cycle on a transient volume
with a checksummed file — archived, restored, remounted on a relaunch,
same checksum — plus the no-replace re-run and the undeclared demise;
the fixture's bucket and EFS lifecycles applied and read back. Found on
the way: an SSM invocation race in `run_session_command` (fixed).
**Open USER question**: AWS Backup for EFS instead of a refused
`archived`. Original plan for reference:

**Why**: GOALS.md's first goal is managing storage of various types, and N19
gave storages a real state machine (`active ⇄ archived → destroyed`).
`archived` is realized only by the GCP pd builder (§11.6); every AWS
builder answers `supports_archive() = False`, so the state is a validation
error on the account that actually holds data. DESIGN §3H still defers
"systemic data lifecycles for storages (S3 transitions to Glacier,
age-based policies)". Both are non-GCP, on the AWS account, and complete a
designed mechanism.

1. **EBS `archived`**, the pd shape: snapshot (`csis-<volume>-archive`)
   before the whitelisted destroy of the volume; `active` again re-creates
   the volume from the snapshot (`aws_ebs_volume.snapshot_id` under
   `ignore_changes`) and deletes the snapshot after the apply; `destroyed`
   from `archived` deletes the archive; `supports_archive()` true; the
   state query expects the volume absent and the snapshot present.
2. **Data lifecycles as declarations** (§3H): S3 `lifecycle:
   {transition_days, storage_class, expire_days}` → bucket lifecycle
   rules; EFS `lifecycle: {ia_days}` → a `lifecycle_policy` transition to
   IA; recorded in the storage read-model and reported by the state
   query. `archived` for S3 and EFS stays refused (no snapshot primitive)
   — **USER**: whether AWS Backup is wanted for EFS instead.
3. Tests: transition scripts and gate whitelists per shape, validation of
   the declarations, the read-model; golden regenerated.
4. **Live proof (AWS, cheap)**: a transient EBS volume declared by overlay,
   mounted on an ephemeral `test2`, a proof file written over SSM,
   archived, restored, remounted on a relaunch with the same checksum (the
   §11.6 with-data shape); one lifecycle rule applied to the fixture
   bucket and read back.
5. Feature branch `feature/aws-storage-archive`, squash-merged, kept.

### 14. DONE 2026-09-10 — post-bake image tests and a release that means "known correct"

**Built on feature/post-bake-tests and proven live 2026-09-10 (ledger
71).** `tests.post_bake` on an image runs ON the launched instance by
`verify instance` ("declared tests"), recorded per build in
`meta-state/image-tests.yaml`; `release` refuses a build without a
passing record (`require_image_tests`); released builds are kept by
retention and an ephemeral runtime's disposal (the operator's decision
(a)) and count as declared for `empty --runtime`; and — found live, the
last gap — an image may declare `release: {model}` so the run's own
release lifecycle releases the verified head before retention runs.
The first live suite failed the "dask" image honestly (the fixture's
playbook was a placeholder; it now installs dask). Also found and
fixed: `gce-decommission` did not undeclare a tree-declared gce-test;
the ansible `pip` module needs `packaging` on the pinned interpreter;
a transient "Script disconnected" at the OS-update transaction's close
(watch item). Original plan for reference:


**Why**: EXPLORE's image-tests item stopped, deliberately, before
the post-bake layer ("launch an ephemeral instance, run the declared
tests over the session mechanism, record, and let `release` require
it") until a real instance apply existed. Ephemeral instances, the
verification hook and `run_session_command` now exist on both clouds
(GCE proven live; AWS after §13), so the missing layer is small — and
it is the Systemic Purpose made concrete: images formally released as
correct for a model.

1. **Declared post-bake tests**: a `post_bake:` section under an image's
   `tests:` (same goss-style vocabulary as the in-bake checks: files,
   packages, commands, services, users, plus `mounts`), validated at
   generation. Runs ON the ephemeral instance over the runtime's session
   command as one more check of `verify instance` ("declared tests":
   each assertion's outcome in the detail).
2. **Recorded per build**: `meta-state/image-tests.yaml` keyed by build
   id (run, instance, checks, pass/fail), written by the same
   apply-gated path as `verifications.yaml`; a build never launched has
   no record.
3. **Release requires it**: `release <image> --build <id>` refuses a
   build whose image declares post-bake tests but has no passing record
   (`require_image_tests`, default on where tests are declared);
   `require_released_builds` keeps working unchanged.
4. **USER — release versus retention on an ephemeral runtime.** An
   ephemeral runtime disposes every image at the end of a run, released
   ones included, so today a release on `gcloud-east1` would be
   disposed by the same run that made it. Options: (a) released builds
   are exempt from retention and ephemeral disposal (kept, reported like
   retention debt, disposed only by an explicit `dispose image`);
   (b) `release` is refused on an ephemeral runtime. Recommended: (a) —
   a release is the one thing a cost-bound runtime should keep.
   **DECIDED (user, 2026-09-09): (a) — released builds are kept.**
5. **Tests**: post-bake tests emitted into the verification, recorded
   only after a real apply, refused releases, the retention rule of
   step 4; golden regenerated if emission changes.
6. **Live proof on GCE**: `imgfile-basic-dask` declares a small
   post-bake suite (the dask import, the pd mount); one `cloud-cycle`
   runs it on the ephemeral gce-test and records it; `release
   imgfile-basic-dask --build <id> --model default` on gcloud-east1;
   then the run's retention behaves per the step-4 decision, and
   `cloud-empty` reports accordingly (a kept released image is declared
   there, not a leftover).
7. Records: ledger, PLAN status, OPERATIONS ("Releases"). Feature
   branch `feature/post-bake-tests`, squash-merged, kept.



## The former V2_PLAN.md, split on 2026-09-10 (migrated here 2026-09-11)

That document held three things for six weeks; each now lives where its
readers look for it, and the document itself is gone:

- the **design record** — the stakeholder Q&A (Q1–Q7, N1–N26), the plan
  sections (§3A–H, M, M2) and the gate table (§4) — in
  [docs/DESIGN.md](docs/DESIGN.md), numbering unchanged, so an old
  citation "V2_PLAN §3F5" reads as "DESIGN §3F5";
- the **findings ledger and standing constraints** (formerly §5, entries
  1–71) in [docs/LEDGER.md](docs/LEDGER.md) — "ledger 68" and "TODO.md
  item N" resolve there;
- the **execution worksheet archive** (formerly §6, TODO stages 1–14) as
  the last section of [PLAN.md](PLAN.md) — "stage 10.14" resolves there.
