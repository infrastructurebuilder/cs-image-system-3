> **Frozen record.** This document is history, kept verbatim as it was when frozen; nothing in it describes the present. Its standing constraints live on as rules in the operating manual. Current documentation starts at [README.md](../../README.md).

# Findings ledger and standing constraints

*Formerly `LEDGER.md` (moved 2026-09-10, content unchanged). References of the form "LEDGER.md" / "ledger N" mean this file; "TODO.md item N" means the closed list below.*

`TODO.md` was retired as a findings log on 2026-08-27 (it is now the
execution worksheet for stages of work taken from the plans). Its nine
items were all closed; the findings that lived nowhere else are kept
here. References elsewhere of the form "TODO.md item N" mean this list.

1. **`skip_roles`/`skip_groups`, `okta.roles.read` revoked — DONE
   2026-08-26.** `OktaTFUser.generate_terraform_data` emits both; the
   scope is revoked on the API services app; `.envrc` exports
   `OKTA_API_SCOPES='okta.users.read okta.groups.read'`. Verified
   read-only: the users root plans No changes, the groups root plans
   only its `group_gids` outputs.
2. **Client Secret on the Okta API services app — DONE 2026-08-27
   (nothing to delete).** App `0oa2604feo1AuyHi01d8` uses Public key /
   Private key client authentication and holds no client secret;
   key-based auth is the only credential.
3. **Instance-builder apply guard re-armed — DONE (V2 gate 5/7).**
   `plan -out=tfplan` → `gate-plan` → `apply tfplan`, the apply emitted
   only under `config.apply_instances` (see
   [docs/OPERATIONS.md](OPERATIONS.md)).
4. **Read-only GROUP builder (`okta-tf-ro` group type) — KEEP
   (decision 2026-08-26).** No consumer today; not to be removed. Sharp
   edge: the okta provider's group-name search is prefix-based, so a
   lookup of `<name>` is ambiguous whenever `<name>_admin`/`<name>_user`
   exist (PLAN.md "Read-only … builders").
5. **Legacy per-runtime state map in `executables.yml` — DONE
   2026-08-27.** Nothing read it (no `key_root` consumer); removed, with
   a pointer to the state-backends mechanism; generated output unchanged.
6. **hashicorp-utils generalizations — DONE (V2 gate 4).**
   `BlockSpec.labels` single-label kinds and `OutputSpec`; the identity
   root emits `group_gids`/`groups` outputs consumed by remote state (N7).
7. **`query_existing_users()` seam — a placeholder**, see below.
8. **Stale PLAN.md passages — DONE 2026-08-27** (annotated in place).
9. **OPA gid source — RESOLVED 2026-08-26.** The OPA Attributes API
   (`GET /v1/teams/{team}/groups/{group}/attributes`, `unix_gid`);
   `okta_opa_plugin/opa_gids.py` reads it (both response shapes).

## Kept on purpose (deliberate placeholders, not to-dos)

- `OktaTfUserBuilder.query_existing_users()` (empty seam, no callers)
  and `User.as_profile()` (the Okta REST *wire shape*, camelCase — not
  the `okta_user` resource shape; PLAN.md R6) are the intended home of a
  future direct-Okta-API lookup path. Do not delete as cruft; they stop
  being placeholders when that feature is built or explicitly abandoned.
  *Update 2026-08-27:* the "mothballed okta-tf managed user builder" is
  no longer mothballed — `managed:` per user (EXPLORE identity item)
  made it the live emission path; attribute *writes* stay disabled
  pending Q7.

## Standing constraints (never "complete")

- Never destroy OPA groups (server gids) or users (uids); membership
  removals only by explicit decision.
- Applies require: explicit go, same-day S3 state backup, fresh plan,
  manifest gate, then `tofu apply <verified-plan-file>`.
- DPoP must stay OFF on the API services app — the okta/okta provider
  does not support it (PLAN.md "Open risks").
- The `*.manage` Okta scopes stay ungranted under the read-only design.
- Discovery before any OPA reconciliation must enumerate **security
  policies and group memberships**, not just groups/users/resource
  groups (local-migration lesson; `state query` now does memberships,
  policies still by hand).
- **Never modify existing network configuration** (stage 1 directive,
  2026-09-02): existing security groups, subnets, and routes are
  untouchable. Creating NEW SGs is fine; instances may *wear* existing
  groups (e.g. OKTA-GATEWAY) by configuration.
- **Never open ingress to the shared networks' address space** (the
  VPC's NOAA-routable CIDR associations, 137.75.x/140.90.x): SSH
  ingress is granted by security-group reference only
  (`ssh_ingress_security_group_ids`).
- Instances launch in the **private subnet with no public IPs**; sftd
  advertises the private address (user-data `AccessAddress`) because
  the VPC has no internet gateway.
- Environment-specific identifiers (SG ids, subnet ids, machine types)
  are **configuration, never code literals** — test stubs must not
  restate them (they accept any configured value).


## Finding 2026-08-27: modifications must work for BOTH shell scripts and ansible playbooks (moved from GOALS.md, 2026-09-10)

Stakeholder question: does the image builder actually allow modifications using both shell scripts and ansible playbooks? Verified answer on `feature/v2-lifecycles`: **no — only ansible worked.** Three pre-existing defects, none introduced by V2:

1. **Every modification resolves to the default mod builder.** The deferred-list structuring looked the builder up by the *field name* (`modifications`) instead of the item's `type:`, so `type: bash-remote` was silently treated as `ansible-default`. The fixture's bash mod shows up in the golden output and lineage as `ansible-default` with no content.
2. **The bash builder emits invalid HCL.** It wrote the script's raw lines (and an `exit 0`) straight into the packer build file, not inside a `provisioner "shell"` block; any build carrying a real bash mod would fail `packer validate`.
3. **`scripts:` (script files) was not a recognized bash field** — only inline `script:` lines — so the fixture's `scripts: [...]` was dropped.

The requirement this restated stays in [../GOALS.md](../GOALS.md) ("Modifications: shell scripts AND ansible playbooks"); plan and execution: [DESIGN.md](DESIGN.md) §3M2 / gate 8.

## Stage 1 live-run findings ledger (moved from TODO.md, 2026-09-02)

Stage 1 (first real end-to-end run, 2026-08-31 → 2026-09-02) landed and
its worksheet section was deleted per TODO.md's convention; the durable
record is PLAN.md "V2 execution → Live run" plus this ledger. Findings
1–15 (step 2, the first bakes) are summarized collectively; 16+ are
individually numbered in the develop history.

**Step highlights.** 6 base + 12 instance builds in lineage over the
SSM communicator; first live `upgrade image`; identity reconciled by
six `tofu import`s (zero OPA writes); first storage applies (mnt_data
vol-0fe1e27716f86c2f2, EFS fs-02d658f1561aab44b, unique bucket);
`test`/`test2` launched, verified in-instance and by `sft ssh` (gate 5
criterion met 2026-09-02), released
(`imgfile-basic-dask ami-09759842591f8e481`, model default), then torn
down through the gate; 11 orphan AMIs + 12 snapshots verified ours and
deregistered by the operator; IaC-managed enrollment tokens designed,
built, applied, and rotation-proven the same day.

**Findings (condensed).** 1–15 (step 2): HCL `%{`/`${` escaping; packer
needs the named `profile`; no-IGW VPC forced the SSM communicator
(session_manager, QuickSetup profile, NAT subnet, user_data agent
bootstrap); user_data newline/quote escaping; RHUI vs
subscription-manager guard; Debian tooling bootstrap + apt lock
timeout; t2.micro OOM at bake (t3.medium + machine_type fallback
chain); dnf clean-and-retry; /tmp collision; gitignored meta-state
commit; csis-mods mkdir; ansible python prep + pinned interpreter;
vendor SSH user by chain root; per-family root device (two-root-volume
no-boot AMIs). 16–19 (step 3): instance-image chaining fixes, branch
`feature/v2-stage1-step3`; the step-3 follow-up (same-run-resolved
parents leave stale `csis_parent`/fingerprint tags) is FIXED by
zero-drift-report (2026-09-02): every recorded build is post-bake
retagged with lineage's resolved values. 20: fixture never carried
`apply_storage`/`apply_identity` keys — a silent flag-set failure ran
plan+gate with zero applies. 21: the transition recorder recorded
`None -> active` on that apply-less run — the state query's HARD drift
caught the lie (FIXED by truthful-recorders, 2026-09-02: the after-apply
hook is gated on `apply_enabled("storage")` like mark_launched; audit
confirmed every other reality-claiming writer guarded or deliberately
observed-reality).
22: the S3 state-query lookup demanded a Name tag the module never
sets. 23: `run instance-image --no-dry-run` re-bakes every image with a
runner script and launches EVERY non-destroyed instance — no
per-instance selector exists. 24: `apply_*` flags gate *generation*;
previously generated runners keep their baked-in apply lines. 25:
per-instance `machine_type` (t2.micro OOM-killed the SSM agent). 26:
module-default public IPs poisoned sftd's advertised address —
no-public-IP + user-data `AccessAddress`. 27: instances wore only the
VPC default SG; the root now creates `csis-instances`. 28: Nitro EBS
device naming (by-id fallback from the volume id). 29: opening the
VPC's associated CIDRs is FORBIDDEN — SG-source-only ingress. 30: SG
replacement needs create-before-destroy. 31: the gateway relay also
requires the target to WEAR the OKTA-GATEWAY group
(`addl_security_groups`). 32: oktapam 0.7.1 ERRORS on plan refresh
after out-of-band token deletion — `state rm` is the repair, making the
state-query token-liveness probe load-bearing. 33: `gate-plan` accepted
a stale planfile after a failed plan (the generated runners propagate
failure; the gate should also refuse stale planfiles). 34–37 (GCP
readiness live run, 2026-09-03, details in GCP-READINESS.md §9):
apply-check needed to be a config-free CLI command; GCE names forbid
underscores (plugins sanitize via gce_name); the apply step executed
unrequested lifecycles' stale runner scripts hook-lessly — GOALS.md 5.5
amended to skip them loudly (two unrecorded AMIs were the proof);
GCE's READY is a live storage state.
42–46 (Alma 10 migration, feature/gce-alma-10, 2026-09-04 — the series
renamed basic-rhel-8 → basic-rh-10, GCE source
almalinux-cloud/almalinux-10): 42: dnf5 (EL10) exits 1 on
`update <pkg>` when the package is already current — targeted-package
updates now run behind a `check-update` guard (exit 100/0 semantics
stable across dnf4/dnf5), rc-safe under packer's `/bin/sh -e`. 43: the
GCE base bake defaulted to ssh user "ec2-user" (AWS-ism) while the
instance bake fell back to "packer"; the new-generation guest agent
aborts ALL metadata key provisioning when removing the stale
other-name user fails — one declared `ssh_username` per GCE chain, and
`OSBuilderBaseImageBuilderSubconfig.get_ssh_username()` no longer
unconditionally returns None (latent: the field was a no-op).
Diagnosed by capturing the packer build VM's serial console during the
sanctioned bake. 44: mod_image.sh matched os-release id "alma" but
AlmaLinux reports "almalinux". 45: the instance root's root-level
`aws_vpc`/`aws_security_group` blocks bound the DEFAULT unconfigured
aws provider (the collector aliases every configured provider) — they
only ever planned from shells with ambient AWS credentials; they now
bind `provider = aws.<alias>` explicitly. 46 (gap): no first-class
image-disposal operation exists — the authorized RHEL image removal
was a manual gcloud delete + lineage-record removal in one commit
(zero image drift verified before and after).
47–49 (GCE first launch + IAP proof, feature/gce-launch-proof,
2026-09-05): 47: a GCE image boots the guest agent (manager +
core-plugin generation) which removes users absent from metadata, and
if the bake user's `google-sudoers` membership is missing (the agents
race over it during bakes) `gpasswd` exits 3 and the agent ABORTS its
whole metadata-ssh-key setup — so NO operator key is provisioned and
every SSH/IAP session is refused (found live: the gce-test launch).
Fix: a runtime `bake_finalize_commands` hook emits a final bake
provisioner guaranteeing the build user is a clean google-sudoers
member; GCE-only, AWS bakes untouched. 48: packer's ansible
provisioner defaults `ansible_user` to the operator's LOCAL login,
never the build VM's ssh user, so ansible builds `~/.ansible/tmp`
paths under `/home/<local-user>` and every task dies "unreachable"
(intermittent: packer's use_proxy auto-detection masked it until it
flipped to direct mode). Fix: a runtime `bake_ssh_username` hook — GCE
pins the ansible provisioner `user` to "packer"; AWS returns None and
keeps its working behavior. 49 (gaps, deferred): (a) running
`instance-image` with apply re-binds an already-launched instance's
pin to the new series head WITHOUT replacing it — meta-state then
claims the new build while reality keeps the old, and (b) `state
query` does not compare an instance's booted image against its pin, so
the mismatch is invisible; the sanctioned move (`upgrade instance` →
gated `-replace`) is a no-op once the pin has silently moved. Both
observed on gce-test; neither fixed. **IAP proven 2026-09-05** by the
operator's interactive session (the harness's own probes were
confounded by a passphrase-protected client key, so 47's finalize step
stands as first-boot hardening — the agent's metadata-change path had
recovered). Two more from the in-instance evidence, logged not fixed:
50: the `gce_data` pd is ATTACHED (device `gce_data`) but NOT mounted —
`df /mnt/gce-data` resolves to the root fs; the AWS launch realizes
mounts through user-data (by-id device resolution, finding 28) and the
GCE launch has no equivalent, so a declared `mount_point` is unrealized
on GCE. 51 (cost): the instance boot disk inherits the IMAGE's 200 GB
`disk_size` — with the 30 GB `gce_data` that is 230 GB of pd-standard
against a 30 GB free allowance, ≈ $8/month while the instance exists
(stopped or running); the readiness plan's "≈ $0 launch" assumed a
free-tier-sized boot disk. Fix direction: a bake-time disk size that
matches the workload (200 GB was the RHEL vendor image's minimum
carried forward), or an instance-level boot disk size override.
52–53 (gce-test teardown, feature/gce-test-teardown, 2026-09-05,
operator-authorized): 52: undeclaring the LAST instance on a runtime
made its instance root vanish entirely, so nothing ever planned the
destroy — the decommission whitelist had a name and no plan to
whitelist it in, and the VM would have stayed orphaned in tofu state
and the cloud. The root is now emitted (terraform + provider + backend
only) whenever a recorded instance is undeclared, and the whitelist is
scoped per runtime through the pinned build's lineage runtime.
53: the N19 "forget launch params and pin" ran at GENERATION, so a
DRY run erased the record before any destroy — after which the gate had
nothing to whitelist (the finding-21 truthful-recorders shape). The
forget is now an after-apply hook behind `apply_instances`, like
mark_launched. Proven live: dry run → whitelist + "1 to destroy" with
the record intact; gated apply → gce-test destroyed (200 GB boot disk
with it, `gce-data` kept), decommission recorded, state query "no
drift".
49–51 FIXED + 54 (feature/gce-gaps-49-51, 2026-09-05/06): 51: the GCE
runtime declares `default_disk_size` (40 GB on gcloud-east1) and the
googlecompute source emits it runtime-first — the image's 200 GB was
the OS builder's default. 50, cause corrected: the launch DID emit the
startup script; the module attached the pd as device_name `gce_data`
while the launch params mounted `/dev/disk/by-id/google-gce-data` —
GCE exposes `google-<device_name>` — so the script died at the missing
device; one sanitization now serves both. 49: a runtime hook reads the
image an instance actually booted (GCE: boot disk → source_image);
after a real apply a deferred-parent instance binds from it, and the
state query flags a pinned instance whose booted image differs as
`changed` (unsupported clouds make no claim). 54 (new, found live):
packer reached build VMs over their external IP on tcp:22, which only
worked while `default-allow-ssh` existed; with that rule deleted every
bake timed out waiting for SSH. IAP runtimes now bake through the IAP
tunnel (`use_iap = true`); operator prerequisite:
`roles/iap.tunnelResourceAccessor` for the runner service account.
**Proven live 2026-09-06** (feature/gce-gaps-proof, operator-authorized
throughout): the runner's `roles/iap.tunnelResourceAccessor` granted;
base `basic-rh-10-gcloud-east1-20260906-033730` and dask
`imgfile-basic-dask-pckr-gce-ans-20260906-034343` baked at the vendor
image's **10 GB floor** through the IAP tunnel (51 + 54; the 200 GB
pair disposed, finding-46 shape, state query "no drift"); gce-test
launched through the gate on the 10 GB dask image, and its serial
console showed the startup script finding `/dev/disk/by-id/google-gce-data`,
running `mkfs.xfs` on the 30 GiB pd and reaching "Finished running
startup scripts" under `set -e` (50), while the guest agent updated the
operator's key and removed the stale `packer` user with no error (47 at
instance boot); the pin was bound from the booted image and the state
query's new booted-image comparison reported "no drift" with the GCE
probe answering (49). Torn down through the gate afterwards (whitelisted
destroy, plan "1 to destroy", record kept through the dry run — 52/53
holding).
Side lesson for the shared checkout: a peer session's `git flow
feature start/finish` switched HEAD mid-run and broke the run's own
meta-state commit (exit 128) — committed manually; see the
`shared-working-tree` memory note.
55–58 (feature/gce-cycle, 2026-09-07, the first `just gce-cycle`):
55: three transient failures in one hour, all in the window GitHub's
release downloads were returning 504 — a dask bake timed out waiting
for SSH through the IAP tunnel (its retry booted, provisioned in ~90 s
and imaged cleanly, serial console captured), and two `tofu init`s
failed to fetch a provider's SHA256SUMS. Every regenerated root
re-fetches provider checksums, so a run is only as reliable as GitHub
that minute; mitigation queued as stage 8.8 (plugin cache + kept lock
files). 56: `gce-verify` waited for `startup-script exit status 0`,
which guest agent 20260715 never logs — its completion line is
"Finished running startup scripts" (the pd mount shows as the kernel's
`XFS (sdb): Ending clean mount`); the instance was healthy the whole
time. 57: the GCS destroyed-transition wipe ran a bare
`gcloud storage rm --recursive gs://bucket/**`, which exits 1 when the
bucket is EMPTY — the normal end-of-cycle case — so the teardown died
before terraform's destroy; the wipe is now a generated script treating
"matched no objects" as success. 58 (decision, operator): NO GCE
resource is kept between cycles — `gce-data` and the bucket go with the
instance and the images; the recorded path (`dispose image`, the
storage `destroyed` transition) handles it. **Proven live**: base
`basic-rh-10-gcloud-east1-20260907-083934` and dask
`imgfile-basic-dask-pckr-gce-ans-20260907-085523` baked; gce-test
launched under the launch overlay through plan → gate → apply-check
(`--root tofu-gce --overlay …`) → apply; verified without an operator
session (serial console + strict state query "no drift", booted image
= pin); decommissioned, both storages destroyed through the gate (the
empty bucket wiped as a no-op), all four GCE images disposed through
`dispose image` (children first, the parent pin dropped as
`op: dispose`); `gce-empty`: no instances, custom images, disks or
buckets, state query agrees.
59–60 (feature/convergent-bakes, 2026-09-08): 59: convergent bakes
proven live — from empty GCE, pass 1 baked base + dask; pass 3 (same
run, same inputs, both lifecycles) emitted no bake surface (`skip:
current` ×2, `no-script` ×2); pass 4 (one comment in setup_dask.yml)
re-baked the dask image alone. Found on the way: the plan-time
base-image stand-in must carry the five attributes the verify commands
read from the object (identity/storage types, admin user/keys, tests)
or plan-time and record-time fingerprints diverge — pass 2 re-baked
the base once for that. Also: `stale` (a pin behind its series head)
is reported by `state query --strict` but does not fail it — five AWS
pins from the stage-1 re-bakes are stale today, by design (N17). 60:
**rule 58 collides with N19 tombstone permanence** — after a cycle
destroys `gce_data`/`gce_bucket`, the live `state: active` declarations
are refused as resurrections and no run can start; the storage-teardown
overlay (declaring them destroyed) is the honest workaround, and the
fix is stage 10.10 (ephemeral-runtime storages are forgotten after
their destroy applies).
61–64 (feature/declared-ephemerality, 2026-09-08): 61: stage 10 proven
live as ONE `run --all` under an execution-knob overlay — `gce_data` and
`gce_bucket` re-created as **generation 2** (their tombstones from the
09-07 cycle regenerated, never refused), both GCE images baked, the
DECLARED ephemeral `gce-test` launched through the gate, verified
(startup scripts finished, pd mounted, booted image a recorded dask
build), torn down by its own sequence and forgotten, the closing
`retention` lifecycle disposing every GCE image (ephemeral runtime),
`gce-empty` green with the two declared storages standing. The
operator's storage semantics (§10.11–15) hold: a storage exists exactly
as long as its declaration; a cycle never destroys a declared one.
62: a fresh CLI process resolved `run --all` before the hook plugins
loaded, so registered lifecycles (`release`, now `retention`) never
joined `--all` from the command line — `release` had silently never
run live; fixed (hooks load before lifecycle names resolve). 63: the
first verification of gce-test FAILED on "booted image" and, by the
operator's rule, left it standing (the state query reported
`ephemeral instance is STANDING`, as designed): an instance whose image
was baked in the same run has no pin and a launch record of `unbound`,
which the check compared literally; verification now requires the
booted image to be a recorded build of the instance's image series on
its runtime. The recovery was the model working: the next
instance-image run resumed the sequence (plan no-change → verify ok →
teardown). 64: a bake that follows another build in the same run hit
IAP's instance-lookup lag ("4047: Failed to lookup instance") for longer
than packer's default 30 s tunnel wait, so SSH timed out against a
healthy VM (four reproductions; serial consoles showed sshd up in 30 s,
PACKER_LOG showed the tunnel retries) — yesterday's "SSH timeout"
(finding 55) was this, not GitHub. IAP bakes now set
`iap_tunnel_launch_wait = 120`. Cost of the whole proof: ≈ 4 base
bakes + 2 dask bakes of spot minutes, cents; nothing left running.
65 (feature/section-11, 2026-09-08): the generic `cloud-cycle` recipe's
first live use failed in seconds — `--apply-runtime` (an option of
`run`) had been placed before the subcommand, where only global options
go; a dry `cloud-cycle gcloud-east1 yes` never reached the CLI's option
parser, so it was not a proof of the recipe. Fixed in the three recipes
and pinned by a test that walks EVERY `{{gce_cli}}` invocation in the
Justfile against the real command tree (global options before the
subcommand, the subcommand's own after it; unknown commands and options
fail) — the operator's rule that a recipe must be effective now has a
test. The rerun then baked both GCE images (basic-rh-10 12:57, dask
13:02, both recorded and pinned) and FAILED on the `tofu-gce` instance
plan: "No valid credential sources found … backend s3 … the SSO session
has expired" — the AWS SSO session lapsed during the fifteen-minute
run, after `cloud-preflight` had passed at its start. Two facts worth
keeping: (a) the GCE roots keep their state in the S3 backend, so AWS
credentials are a hard dependency of every GCE lifecycle (an expired
AWS session stops GCE work even when GCP is fully authenticated);
(b) `empty --runtime gcloud-east1` also needs AWS credentials, because
every runtime model validates its networking against its cloud when the
configuration loads (`update_networking` at finalize, AWS and GCP alike)
— a runtime-scoped command cannot be answered from one cloud's
credentials alone. Neither is fixed here (candidates in stage 12: a GCS
state backend for the GCE roots, and lazy networking validation scoped
to the runtimes a command touches). Left on GCE: the two baked images,
nothing running; the next successful cycle's retention phase disposes
them. Read-only inventory by `gcloud … list` confirmed no instance, no
snapshot, only the declared `gce-data` disk.
66 (feature/section-11, 2026-09-08): with the AWS session back, the
strict preflight refused the rerun: the dask image from the failed run
showed `changed` drift — "parent: lineage=basic-rh-10-…-124809
tag=series-basic-rh-10; fingerprint differs". Cause: a `parent_policy:
follow` image baked in the SAME run as its parent gets its labels from
packer at generation time (parent still `series:…`, a placeholder
fingerprint), while its lineage record is written after the bake with
the parent build known; the packer builder then re-tags the image from
the record through the runtime's `retag_image` hook — implemented for
AWS since the zero-drift-report work, a logged no-op on GCE. Every
earlier GCE cycle disposed its images before any state query looked, so
the gap never surfaced. Fixed: `GCPCloudBuilder.retag_image` (setLabels
with the image's label fingerprint, merged with the labels packer wrote,
through the same `gce_label` sanitizer), and the harness journals GCE
retags like AWS ones. Remedy for images already standing: `lineage
relabel --runtime <rt>` (`just cloud-relabel <rt> no`; dry by default)
re-tags every recorded build whose real tags disagree with its record —
the tag side of zero-drift-report, `restamp` being the record side; no
meta-state change. Proven live: the dry plan named the one image and the
two differences, the relabel set the labels (gcloud describe confirmed),
the strict preflight passed with only the four informational stale
lines, at zero bake cost.
67 (feature/section-11, 2026-09-08): stage 11 items 4, 5 and 6 proven
live. (5) `just cloud-cycle gcloud-east1` — one `run --all` scoped and
applied to the runtime by `--only-runtime`/`--apply-runtime`, no recipe
naming a project — ran to `cloud-empty` green: both GCE images were
CURRENT (convergence held live: "skip: current"), so no bake; the
declared ephemeral `gce-test` launched from the recorded dask build,
verified (15:38) and was torn down and forgotten by its own sequence;
retention disposed both images (ephemeral runtime keeps nothing);
emptiness: no instances, no images, no disks or buckets beyond the
declared storages, meta-state agrees. (6)+(4) a TRANSIENT pd `scratch`
declared only by an overlay: created (active, generation 1) →
`archived` (archive-scratch.sh snapshotted `csis-scratch-archive`, the
disk destroyed through the whitelisted gate, record archived with the
archive name in its facts) → active again (the module carried
`snapshot = "csis-scratch-archive"`, the disk came back FROM the
snapshot — `sourceSnapshot` confirmed by gcloud — and
restore-scratch.sh deleted the snapshot after the apply) → a
`run storage retention` carrying the declaring overlay, whose closing
phase ran the nested `run storage --only none --no-state-query
--no-commit --apply-runtime gcloud-east1` WITHOUT that overlay: scratch
undeclared there, destroyed through the gate, tombstone action
`undeclared`, generation 1; no snapshot left; `cloud-empty` green. Four
meta-state commits (b45aade, bfe6ed4, 62557aa, d93262e) plus the cycle's
(38e1b9e). Cost: zero bakes; one 30 GB pd and one snapshot for minutes.
Observed, not fixed: the record of an ACTIVE pd carries the `archive`
name fact too (harmless — the name the archive would take).
68 (feature/live-proofs-68, 2026-09-09): the three test-only items
proven live on gcloud-east1, on a STANDING (non-ephemeral, overlay-
declared) gce-test and a transient scratch pd, with two mechanisms added
on the way. **§11.6 archived WITH data**: a proof file written on the
mounted scratch disk over IAP (sha256 9d152f91…3171), the disk detached,
archived (snapshot `csis-scratch-archive`, gated destroy, record
archived as generation 2 — yesterday's tombstoned name regenerated,
§10.12), restored from the snapshot (`sourceSnapshot` on the new disk,
snapshot deleted after the apply), the instance decommissioned and
relaunched with the disk mounted: the same file with the same checksum,
and `journalctl -u google-startup-scripts` showing no `mkfs` — the
`blkid` guard held. **§10.14 detach + unmount**: dropping the mount from
the declaration ran the unmount over the runtime's IAP session (receipt
`unmount-receipts/gce-test__scratch.json`, method `session`, exit 0),
the gate required it (`--require-unmounted gce-test:scratch`, no
`--allow-destroy` — a GCE attached_disk is an in-place attribute), the
apply detached it, the launch record dropped the mount; on the instance
`findmnt` failed, the fstab line and mount point were gone, the disk
showed no users. **§11.3 failure policy**: the ephemeral gce-test with
`on_failure: teardown` and `userdata: "false"` launched, its startup
script failed ("an explicit failure line"), the verdict was recorded
(`verifications.yaml`: startup scripts false, booted image true, mounts
true), the teardown planned/gated/applied in the same sequence, the run
failed (exit 1), nothing standing. Found there: the runner's last step
`verify assert` failed the SCRIPT before the after-apply hook ran, so
the torn-down instance kept its launch record (invisible to the state
query, which only flags ephemerals that still exist) — fixed: the
assertion moved into `forget_ephemerals`, which forgets first and then
raises the verdict; the ordering test had checked steps, not records.
Mechanisms added: (a) instance `userdata` was a declared-but-unused
field — it now runs as the startup script's last act under `set -e`,
before the completion marker, and joins the immutable launch parameters
(present only when declared, so older records stay comparable); it is
the sanctioned way to force a failing verification; (b) an overlay entry
`{name: X, undeclare: true}` removes a tree declaration for one
invocation — the standing instance was decommissioned twice with it
(tree untouched). Operator-side finding: the 2024 `google_compute_engine`
key was passphrase-protected and this session cannot prompt
(`read_passphrase: can't open /dev/tty`), and the passphrase was lost;
with the operator's approval a fresh ED25519 key (no passphrase, 2024
pair kept as `.bak-2024`) replaced the project's `ssh-keys` metadata
entry, and the guest agent re-provisioned the user within seconds. The
runtime's session hook is the same non-interactive `gcloud compute ssh`,
so it needs an agent-loaded or passphrase-less key — a stage 12
candidate: a session identity that is not the operator's login key
(OS Login with the runner service account). Side effect, recorded: a
`--troubleshoot` run enabled the Network Management and Monitoring APIs
and created a connectivity test, deleted the same minute. Also seen: the
GCE post-bake relabel (66) ran live on both bakes. Cost: two bakes, one
e2-micro standing ≈ 90 minutes, one pd + one snapshot for minutes.
Closing leg: `just cloud-cycle gcloud-east1` with no overlay — the
storage lifecycle destroyed scratch as UNDECLARED (`--allow-destroy
module.storage_scratch`, tombstone action `undeclared`, generation 2),
both images `skip: current`, the tree's ephemeral gce-test launched,
verified and torn down (the fixed hook forgot the leg-9 stale record on
the way), retention disposed both images, `cloud-empty` green with only
`gce-data` and the bucket standing; meta-state ab0f805.
Side effect, found afterwards through a failing state-dependent test:
leg 1 (`run storage base-image instance-image --apply-runtime
gcloud-east1`, NO `--only-runtime`) also BAKED ON AWS —
`ami-075901e1bd7965da7` (`basic-rh-10@aws-east2-runtime`, its first
build: the series renamed from basic-rhel-8 on 09-04 had none) and
`ami-085eeafc0b8efbebc` (`imgfile-basic-dask@aws-east2-runtime`, its
parent pin first-bound to the new base), 200 GB snapshots each, ≈ 25
minutes of t3.medium, on the account that is not the operator's money.
Two lessons: (a) `--apply-runtime` scopes tofu applies, never packer
bakes — the bake filter is `--only-runtime`, and every live recipe
carries it; an ad-hoc run must too (a stage 12 candidate: `--apply-
runtime` implying `--only-runtime` unless `--only` is given); (b) the
"duplicate log lines" seen during leg 1 were those bakes. Correction to
ledger 65/stage 11: yesterday's `upgrade image` was a dry run and never
persisted; the dispose dropped the pin, leaving the dask image unpinned
on AWS until today's first-bind. The test that caught it
(`test_image_to_source_emits_psi_backed_data_block`) asserted over the
LIVE meta-state that some AWS base still needed a bake; it now works on
a copy with lineage/pins stripped, like its sibling. Operator decision
(2026-09-09): KEEP the two AMIs — the tree's declared state on AWS;
nothing re-bakes on the next unfiltered run.
69 (feature/run-scoping, 2026-09-09): stage 12 — run scoping safe by
construction. (1) `--apply-runtime <rt>` implies `--only-runtime <rt>`
unless images are selected explicitly; the bake plan reads `skip:
outside the apply scope (--apply-runtime <rt>)` — proven live with the
exact ad-hoc command that baked on AWS the day before (`run --all
--apply-runtime gcloud-east1`, dry): every AWS image skipped for that
reason, both GCE images `bake:`. (2) A `--no-dry-run` run whose apply
scope (the runtimes named by `--apply-runtime` and list-valued `apply_*`
flags; a root name counts as its runtime; a bool `true` or no flag is
no scope) would still bake outside that scope refuses BEFORE any bake,
naming the images and the ways out (`--allow-unscoped-bakes`, or an
explicit `--only` / `--only-runtime`); a dry run warns. Tests cover the
implied plan, the refusal with nothing generated, the allow flag, the
explicit selection, the dry-run warning and the scope rules. (3) The
preflight reads the credential caches — never a value — and prints one
`session:` line per credential source (an SSO profile's token expiry
from `~/.aws/sso/cache`, keyed by sha1 of `sso_session` or
`sso_start_url`; static keys have no readable expiry; the GCP ADC only
reports presence, it refreshes itself) against
`config.preflight.expected_run_minutes` (default 30); `state query
--strict` refuses on a session that will not outlast the run, a run
only warns. Found live the same hour: the AWS session had expired
again, and the configuration load itself died in the AWS networking
validation before the new check could run — so the sessions are now
read from the RAW `runtime-builders.yml` in the app callback for `run`
and `state`, and an EXPIRED session refuses before the load (the
"expiring" verdict stays with `--strict`). The headless CLI tests then
failed on the developer's real expired cache: `tests/conftest.py` now
isolates every test from `~/.aws` and the ADC (an empty AWS dir, no ADC),
tests that fake their own caches override it. Proven live: the strict
preflight under the proof overlay (`preflight-short.yaml`,
`expected_run_minutes: 100000`) refused with "expires in 479 min --
SHORTER than the expected run"; without it, passed with the session
lines; the dry `cloud-cycle` showed the recipe's explicit filter as
`skip: not selected (--only)` (the recipe passes both flags on purpose).
Closing leg: `just cloud-cycle gcloud-east1` for real — both GCE images
baked (from empty, ≈ 15 min), the ephemeral gce-test launched, verified
and torn down, retention disposed both, `cloud-empty` green; lineage
holds NO build from this run on AWS (the previous day's cycle had two).
Meta-state b3f6160.
70 (feature/aws-el10, 2026-09-10): stage 13 — the AWS chain moves to
AlmaLinux 10. The AWS entry of `basic-rh-10` queries the AlmaLinux OS
Foundation's official x86_64 AMIs (owner 764336703387, name `AlmaLinux OS
10*x86_64`, arm64 excluded by name and architecture — the finding-39
lesson) instead of RHEL 8.10; `family_version` moves to 10 on both
runtimes, the RHEL family plugin accepts EL10 (it had refused anything
but 8/9) and emits `rhel-10-*` subscription-manager repo names — a
no-op on an unregistered image; the vendor ssh user stays `ec2-user`.
Consequence recorded: `family_version` is a bake input on BOTH runtimes,
so the next GCE cycle re-bakes its base once (cents). Gate-1 normalizer,
targeted-updates assertion, mod-test container (`rockylinux:10`) and the
golden follow. The scoped live bake (`run base-image instance-image
--only-runtime aws-east2-runtime`) built `ami-01a9a00286f1631af`
(basic-rh-10, from `ami-043ff9e9bce4faf8c` = AlmaLinux OS 10.2.20260817.0,
tags = record) and then FAILED before the dask bake — not on AWS: the
instance-image lifecycle planned the GCE instance root too, whose
image-family lookup (`family/imgfile-basic-dask`, the ephemeral
gce-test's deferred image) returned 404 because the previous day's cycle
had disposed every GCE image. Two gaps, both fixed and tested: (a) a run
scoped to one runtime's images (`--only-runtime`, explicit or implied by
`--apply-runtime`) generates and plans no OTHER runtime's terraform root
— their plans can only fail or waste time; list-valued `apply_*` flags
stay apply-only scopes, the §7 decision (every root plans and gates
under them) untouched; (b) under `parent_policy: follow` the dask child
read `skip: current` while its parent was being re-baked in the SAME run
— the pin/head comparison sees only recorded heads, and the parent's new
head is recorded after its bake — so a parent that bakes this run is now
a move in the bake DECISION ("parent … re-bakes this run"), deliberately
kept out of `effective_parent_build`: the fingerprint hashes the parent
reference, and a bake decision must never move a fingerprint (the first
attempt at (b) did exactly that and churned every follow child's
fingerprint — caught by the converged-tree test). The failed run's
records (the base build, the journal) were committed by hand (023aeef),
since the run's own commit never happened. Dry retry: base `skip:
current`, dask `bake: parent moved ami-075901e1bd7965da7 ->
ami-01a9a00286f1631af`, no terraform root in the instance runner.
Live retry (05:22): the dask child baked from the Alma base
(`ami-07519c62eb365d850`, parent `ami-01a9a00286f1631af`) and its parent
pin moved by `follow` (`op: follow`, ami-075901e1bd7965da7 →
ami-01a9a00286f1631af); the run's own meta-state commit landed (46b1089);
strict preflight clean. §13.4 (operator-authorized 2026-09-09): `dispose
image ami-085eeafc0b8efbebc ami-075901e1bd7965da7 --no-dry-run --commit`
— the first live AWS disposal — deregistered both EL8 AMIs and deleted
their snapshots, dropped the records (nothing to unpin: the pin had
already followed), commit 34c7b6a; `describe-images` on both ids now
returns an empty list. The AWS chain's series head is EL10 on both
clouds.
§13.5 — the first LIVE AWS ephemeral (§11.1 had been test-only): under
`aws-ephemeral-test2.yaml` (test2 declared ephemeral for one
invocation, no EBS mount; the AWS runtime stays non-ephemeral) `run
instance-image --apply-runtime aws-east2-runtime` — implied bake
filter, both AWS images current, no bake — launched test2 from
`ami-07519c62eb365d850`, verified it over SSM ("launch parameters
applied" from `/var/lib/csis/launch-applied`; booted image = expected),
tore it down through the gate (`--allow-destroy module.instance_test2`)
and forgot its records (no launch record, no pin; the instance is
`terminated` on AWS); meta-state f3ae5cf. §13.6: the four stale AWS pins
stay stale by policy. §13.7: no live doc said "RHEL 8 on AWS" any more
except the plan bullet, corrected; the readiness and billing files keep
their RHEL 8 lines as history. Cost: two t3.medium bakes (≈ 25 min), one
t3.medium for ≈ 3 min; two 200 GB AMI snapshots removed, two added.
71 (feature/post-bake-tests, 2026-09-10): stage 14 — post-bake image
tests and a release that means "known correct". `tests.post_bake` on an
image (the in-bake vocabulary plus `mounts`, validated at generation)
runs ON the launched instance: `verify instance` sends one session
script over the runtime's `run_session_command` that reports every
assertion (`CSIS_TEST <n> PASS|FAIL`, never aborting, so a dead session
shows as "no result") and adds a "declared tests" check to the
verification; the result is recorded per BUILD in
`meta-state/image-tests.yaml` (a build never launched has no record).
`release` refuses a build whose image declares post-bake tests but has
no passing record (`config.require_image_tests`, default on). §14.4
(operator decision (a)): a released build is exempt from retention and
from an ephemeral runtime's disposal — reported as debt, kept — and
`empty --runtime` counts it as declared; only an explicit `dispose
image` removes it. The fixture's dask image declares the suite the live
proof uses (`python3 -c 'import dask'`, the launch marker file, the
`/mnt/gce-data` mount); the harness answers PASS to every assertion
unless a test says otherwise. Existing tests that release the dask
build now seed a passing record first.
Live, first cycle (06:29): the GCE base bake died after 3 min 24 s with
packer's "Script disconnected unexpectedly" at the LAST scriptlet of the
security-update transaction (56 steps: pam, dbus-broker, libssh, curl,
python3 … tar) — the session over the IAP tunnel dropped as the
transaction closed; packer cleaned its build VM, nothing left on GCE.
The inputs were yesterday's (vendor image almalinux-10-v20260811, the
same policy; the only emitted delta is the `rhel-10-*` repo names inside
the branch that never runs on Alma). A scoped retry of the base alone
(`run base-image --only basic-rh-10@gcloud-east1`) baked cleanly
through the same 56-step transaction — transient, not reproducible; no
provisioner change made (one reproduction would be a guess). Recorded
as a watch item: if it recurs at the transaction's close, the fix shape
is packer's `expect_disconnect` / a pause on the OS-update provisioner
of IAP runtimes. Base recorded (a521f04); the cycle relaunched with the
base current.
Second cycle (06:43): dask baked, the ephemeral gce-test launched and the
first live post-bake suite ran over the IAP session — and FAILED the
image honestly: `python3 -c 'import dask'` exited 1 on the "dask" image
(the launch marker and the `/mnt/gce-data` mount passed). On the
standing instance no python had dask: the fixture's `setup_dask.yml`
had been a placeholder (one `debug` task — DESCRIPTION.md had said so)
since the first V2 bakes, and nothing before §14 could see it. The
mechanism did exactly what the stage promised: the verdict is recorded
per build (`image-tests.yaml`: build …-064332, ok false, the failing
assertion named) and `release` would refuse that build. Under the
tree's `on_failure: keep` the instance stood for inspection; the
decommission then exposed a second gap: `just gce-decommission`'s
overlay only set the apply knob, so with gce-test DECLARED in the tree
(§10.8) the run resumed the ephemeral sequence — verify again, fail
again — instead of decommissioning; the overlay now carries the
`undeclare` form (ledger 68), and the standing instance was destroyed
through the gate, records forgotten (34bb86b). Fix to the image: the
playbook installs `python3-pip` and `pip3 install dask` (idempotent
ansible modules); its content hash moves, so the dask image re-bakes as
`inputs changed`; the gate-1 baseline gained a declared normalizer for
the copied playbook (configuration copied through, not emission), the
golden regenerated. Left on GCE for the next cycle's retention: the two
images of this cycle.
Third cycle (07:12): the dask re-bake failed in the new playbook —
ansible's `pip` module imports the `packaging` library on the target's
ansible interpreter, and the bake's pinned interpreter
(`/usr/local/bin/csis-ansible-python`, the stage-1 ansible prep) lacks
it ("Failed to import the required Python library (packaging)"); the
`package` task before it had passed. Fix: plain `pip3 install dask`
through `command`, guarded on `python3 -c 'import dask'` (idempotent by
construction, `changed_when`/`failed_when` honest). Packer cleaned its
build VM; nothing left running.
Fourth cycle (07:20): the dask image baked WITH dask, the ephemeral
gce-test ran the suite live — all three assertions passed (dask import,
launch marker, `/mnt/gce-data` mounted), the verdict recorded per build
(`image-tests.yaml`: …-072018 ok) — and then the same run's retention
disposed that verified build, as an ephemeral runtime must: the
operator's explicit `release` had NO moment to happen between the
verification and the closing phase. That is the last §14 gap and it is
a design one: release intent must be declared, not raced. Added:
`release: {model: <m>}` on an image — the `release` lifecycle (already
ordered between instance-image and retention) emits one deferred step,
`release --declared`, which at execution releases each runtime's series
head that has a PASSING post-bake record and is not yet the model's
current release (`declared_release_targets`, recomputed after this
run's bakes and verifications); retention then keeps it (§14.4a) and
`empty --runtime` counts it as declared. The operator's `release`
command is unchanged and gained `--runtime` (the runtime-blind series
head was the wrong default on a two-cloud series). The fixture's dask
image declares `release: {model: default}`. Found on the way: the
registration test of the release lifecycle was order-dependent (it
passed only after an earlier test had loaded the hook plugins); it now
loads them itself, as the CLI does.
Fifth cycle (09:14), the proof: from empty GCE both images baked, the
ephemeral gce-test verified with all three declared assertions passing
(`image-tests.yaml`: …-091415 ok), the release lifecycle's deferred
`release --declared` released that head for model `default`
(`releases.yaml`), the closing retention disposed the base and KEPT the
released dask build (debt line: "a RELEASED build (kept by decision)"),
and `cloud-empty` reported the runtime empty with the released image
standing — declared, not a leftover; meta-state 2fd7cd2. Cost of §14's
live legs: five cycles' worth of bakes on spot (≈ 8 bakes, cents), four
ephemeral e2-micro launches, one standing ≈ 15 min for inspection.
Standing on GCE by decision: one released image (≈ $0.05/GB-month of
archive size). What the stage proved beyond its own mechanics: a
post-bake test is the only thing in the system that can see that an
image does not deliver what its name promises.
72 (feature/aws-storage-archive, 2026-09-10): stage 15 — storage
lifecycle parity on AWS. **EBS `archived`** takes the pd shape: an
`archive-<label>.sh` deferred before the plan snapshots the volume
(found by its Name tag; the snapshot carries `Name=csis-<label>-archive`
and `csis_storage=<name>`; a completed archive left by an earlier
attempt is reused; `wait snapshot-completed` before the destroy), the
gate whitelists the volume's module, the record keeps the archive name;
declared `active` again the module takes `snapshot_name` and resolves
the snapshot by tag at plan time (`data "aws_ebs_snapshot"`, `snapshot_id`
under `ignore_changes` — a creation-time fact), and `restore-<label>.sh`
deletes the snapshot after the apply; `destroyed` from `archived` runs
`unarchive-<label>.sh` and whitelists nothing; the state query's EBS
lookup for an archived record expects the snapshot, not the volume
(gone = HARD missing). Snapshots on AWS are id-addressed, so the archive
NAME is a tag — the scripts and the module resolve it; the recorded
fact stays the name, as on GCE. **Data lifecycles** (§3H, N19) are a
`lifecycle:` declaration a builder realizes on the resource: S3
`{transition_days, storage_class, expire_days, prefix}` → one
`aws_s3_bucket_lifecycle_configuration` rule; EFS `{ia_days,
archive_days}` → `lifecycle_policy` blocks (module-created filesystems
only); every other builder refuses the key (`validate_lifecycle` on the
storage builder base, default refuse); the read-model records it; the
S3/EFS lookups report the observed rules/policies, and an active
storage whose declared lifecycle the resource lacks reads `stale`
("run storage"). The fixture declares both (`default-bucket`: IA after
30 days; `efs-storage`: IA after 30 days) — cost-reducing on the
sandbox and the live proof's read-back. Tests: the three EBS transitions
(script order, whitelist, module arg, record), the archived lookup
against a fake EC2, per-builder lifecycle validation, module args, the
read-model, the state-query stale line; golden regenerated (the two
lifecycle args). AWS `archived` for S3/EFS stays refused — no snapshot
primitive (AWS Backup for EFS is the open USER question).

Proven live 2026-09-10 on AWS (us-east-2, the §11.6 with-data shape,
seven gated runs on the feature branch): (A) a storage run under
`overlays/aws-scratch-standing.yaml` created `scratch-ebs` (100 GB gp3)
and the instance run launched a standing `test2` (t3.medium,
imgfile-basic-dask) with it mounted at `/mnt/scratch` (first mount:
mkfs xfs); a proof file was written over SSM (sha256 `4020c024…39e3d`).
(B) under `aws-scratch-detached.yaml` the instance run unmounted through
the session (receipt: method `session`, exit 0), dropped the mount from
the launch record and detached — the volume read `available`. (C) under
`aws-scratch-archived.yaml` the storage run's `archive-scratch_ebs.sh`
snapshotted the volume (`snap-07441e2ddad7fc9a8`, 100 GB, completed,
`Name=csis-scratch-ebs-archive`) and the gate destroyed the volume; the
record reads archived with its history; the same run applied the
fixture's data lifecycles, read back as the bucket rule `csis`
(STANDARD_IA after 30 days) and the EFS policy `TransitionToIA
AFTER_30_DAYS`; the state query then reported no drift for the archived
record (found by its snapshot, the volume gone as expected) and no
`stale` for the bucket or the filesystem. (D) declared `active` again,
the module took `snapshot_name`, the volume came back FROM the snapshot
(`vol-071f2205be58054a6`, SnapshotId = the archive) and
`restore-scratch_ebs.sh` deleted the snapshot; the record's history:
active → archived → active (the archive fact stays on the record as the
name it would use again — inert, the snapshot argument keys on the
recorded state). (E) `test2` decommissioned through the gate
(`aws-scratch-decommission.yaml`: `undeclare: true`) and relaunched
under the standing overlay: the fresh instance mounted the restored
volume as the existing xfs from `/dev/nvme1n1` (no mkfs) and the SSM
read-back returned the same content and checksum; then an ordinary
storage run with the volume active went through plan, gate, apply-check
and apply and left the same volume id — `ignore_changes = [snapshot_id]`
proven where a replace would have destroyed the data. (F) decommissioned
again, a storage run WITHOUT the overlay took the §10.11 demise
(recorded, no longer declared → whitelisted destroy): AWS afterwards
holds no `test2`, no `scratch-ebs` volume, no archive snapshot; the
fixture bucket and `efs-storage` keep their lifecycles (declared). Found
on the way: `run_session_command` on AWS raised `InvocationDoesNotExist`
when `get_command_invocation` ran before SSM had registered the
invocation — the poll now tolerates that code until its deadline (test:
raises twice, then Success; other codes still raise). Cost: two
t3.medium launches (≈ 45 min), a 100 GB gp3 volume for ≈ 1 h, one 100 GB
snapshot for ≈ 5 min — cents. GCP untouched (no instances, no
snapshots; the declared `gce-data` disk and bucket and the one released
image stand by decision). Open USER question carried to PLAN.md: AWS
Backup for EFS instead of a refused `archived`.
73 (feature/justfile-contract, 2026-09-10): stage 16 — the Justfile's
full contract. The five reserved targets now exist in lifecycle order
and bare `just` lists them first (`--list --unsorted`, `default`
private): `init` (unchanged), **`build`** = `uv build --all-packages`
(every workspace member as sdist + wheel under `dist/`, the virtual root
not built — 28 artifacts), **`test`** = lint + typecheck + the unit
tests, every check blocking (the contract's meaning of the name; it was
`pytest` alone, and `verify` — the acceptance bar in every note — is now
its alias; the unit tests alone are `pytest`), **`full-test`** = `test`
plus the slow and external legs, and **`release <version> [yes]`** gated
on `full-test`. `full-test`'s legs: the modification tests under docker
(`test-mods --strict`, skipped loudly when `docker info` fails) and,
only when the new **`preflight` command** finds every runtime session
present, a headless dry `run --all` over a private COPY of the fixture
(so the working tree stays clean — a release refuses a dirty tree) and
`state query --strict` over the same copy; a leg whose prerequisite is
absent reports SKIPPED with its reason and does not fail the run, a leg
that runs and fails does. `preflight` reads the credential caches from
the raw tree WITHOUT loading the configuration (the §12.3 reading, plus a
`present` notion the sessions lacked: a profile with no cached SSO token,
no ADC, no profile at all — none of which was "expired" or "blocking"
before): exit 0 every session present, 2 absent or expired, 1 with
`--strict` on one expiring within the expected run length. Identity
credentials are not gated — a dry run without `OKTA_API_*` warns and the
identity roots skip their plan (the plugin's existing behaviour).
`release`: refuses a dirty tree, `uv version` on the root and every
package, `uv lock`, one commit, an annotated `v<version>` tag, `just
build`, and publish only when `UV_PUBLISH_URL` is set (the registry is
the open USER decision — a git tag alone, or an index) — otherwise
SKIPPED, loudly; nothing is pushed (`git push --follow-tags` is the
operator's act); `yes` as the second argument is the dry form: full-test,
then the bump each package would take. Tests: the contract order from the
source and from `just --list --unsorted` when `just` is on PATH; the
gates and the SKIPPED shapes; the `preflight` command with absent
sessions (exit 2, each reason named) and with static keys plus an ADC
(exit 0); and the Justfile-versus-CLI test now parses the `uv run
cs-image-system …` form too (it caught nothing new; the `cli *ARGS`
passthrough is skipped as the operator's argv). Docs: OPERATIONS "CI
shape" names the contract; a repository README (there was none) names it
and the layout. The CI workflow is unchanged (§17, not now). The first
`full-test` found two things the fast suite could not: the EL10 mod-test
container `rockylinux:10` does not exist (Docker Hub's `rockylinux`
library stops at 9) — from major 10 the stand-in is `almalinux:<v>`,
which is what the AWS chain bakes; and a private copy of the fixture
must carry `tfmodules/` beside it, because the generated roots reach it
by a relative path that climbs out of the tree (the identity roots run
`tofu init` at generation, dry run or not). Proven 2026-09-10 by `just release 0.1.1 yes` (20 min): `test` (545
passed, 1 skipped; ruff and pyright clean), the docker leg (5
modifications tested on almalinux:10, 0 skipped, 0 failed), preflight
(the noaa SSO session with 370 min left, the impersonated ADC), the dry
`run --all` over the copy (all six lifecycles completed) and `state query
--strict` over the copy (clean) — then the fifteen version bumps the
release would make and publish SKIPPED for want of `UV_PUBLISH_URL`.
Also found there: `full-test`'s docker leg writes the mod-tests record
into the live tree, so `release`'s clean-tree check exempts that one
file and its commit carries it — the evidence that the released
modifications passed.

74 (feature/reference-rename + feature/retire-v1-remnants, 2026-09-11):
the V2 label leaves the code, and V1 is retired. Two operator-chosen
items from QUESTIONS.md. **The rename**: `TODO §N` became `stage N` (303
citations) because the stage's home moves to PLAN.md's archive once it
lands, and the `V2` prefix left the document names (GOALS.md, EXPLORE.md,
QUESTIONS.md, docs/DESIGN.md, docs/OPERATIONS.md) with a pointer stub at
each old name. The operator removed those stubs the same day and folded
the former V2_PLAN.md -- by then only a pointer -- into PLAN.md, so no
V2_* document remains and every citation in the tree names a live file;
old commit messages that name the removed files are left as they are. Two exclusions found by regenerating the golden:
provisioned modification content is HASHED into the image fingerprint, so
rewriting a citation in `setup_dask.yml` changed two content hashes and
four fingerprints and would have re-baked every dask image on both clouds
for a comment — reverted, and meta-state records were left alone for the
same reason (they are history). Bare `§N` was left alone as ambiguous:
some name a stage, some a design section. **The retirement**: the
`verify` placeholder was deleted (the `verify` command group shadowed it,
so it could never run); `test` and `cleanup` now name their replacements
and exit 2, handled before the configuration loads, instead of warning
and succeeding — the old behaviour was the opposite of failing loudly;
gate 1's five V1-equivalence tests carry a skip marker naming date and
reason, with the frozen baseline kept as evidence and the golden pinning
emission instead. The `groups` guard was KEPT, on the condition the
option itself set: the converter still does not refuse unknown keys, so
it remains the only thing between a V1-era `groups:` and a silent drop
(TRIAL-001, 2026-09-11, measured what removing it costs). No V1 code path
executes after this.

75 (feature/declarations-that-never-land, 2026-09-12): stage 22 — the
declarations that never land. Six ways a declared or passed value was
being discarded in silence, found by TRIAL-002 and fixed here without
moving a single byte of emitted output (the golden is the proof; both
runtimes). **(1)** `default_image_builder` was declared `init=False`, so
cattrs never structured it and EVERY runtime silently held `DEFAULT`
however the YAML read; both cloud plugins consume it through
`get_default_image_builder()`, so AWS and GCE were equally affected. It
is an ordinary init field now and the runtimes hold what they declare
(`pckr-ebs-ans`, `packer-gcloud-ansible`) — and the golden did not move,
so nothing downstream had come to depend on the wrong value. **(2)** Nine
keys in two internal dicts were not fields on their targets: the
`BaseImage` dict carried `machine_type`, `architecture`,
`auto_generate_storage`, `modifications` and `default_groups`, its nested
subconfig dict `source_image`, `default_machine_type`,
`default_primary_disk_size` and `query`. The `modifications` question
stage 22 asked for answers itself in the code beside it: base images
receive none BY DESIGN, the resolver warns when an OS builder declares
any, and `mods_list` was therefore always empty — passing it only made
the resolver look as though it carried them. All nine are gone.
**(3, operator's decision)** `output_image_name` is declared seven times
in the fixture with real templates and has never named anything: live
AMIs and the GCE image carry the `_final_name` shape
(`imgfile-basic-dask-pckr-gce-ans-20260910-091415`), not the NOSCSB
templates. At the per-runtime level a computed property of the same name
shadows any declared value outright. Making it real would rename every
future image on both clouds, so the operator chose to comment the seven
out with the reason and the revival recipe; renaming is its own stage if
it is ever wanted. **(4)** Two ansible modification items declared
`source:`, which no model accepts — so both have always had zero
playbooks and the validator has always said so. **(5)** Fourteen further
dead keys in the fixture, each commented out with its own reason rather
than deleted, because they may return: `state_marker` (the path is
hardcoded), `runtime_classifier` ×4 (zero references anywhere),
`executables` and `profile` on a runtime (the modelled key is
`credentials.profile_name`), `default_user_email_template` on a GROUP
builder (it belongs to the user builder), `modifications` on an instance
BUILDER, `script` on a mod BUILDER (it belongs to the mod ITEM), and at
image level `machine_type`, `image_builder`, a bare `dask_version` and
`jethro: bodine`. **(6)** The template-scoping test asserted `this` and
`this.parent` THROUGH `output_image_name` — a key the models discard —
by reading the raw resolved document, so it could be broken by a fixture
edit. It owns its input now. Afterwards: the fixture carries **zero**
unknown keys, `validate` succeeds, the golden regenerates byte-identical,
`just verify` is green (541 passed, 0 type errors) and the live state
query is clean apart from four pre-existing stale parent pins. Found on
the way and NOT fixed here: `image_from_query_result` builds a 13-key
dict of which `Image` accepts five — the other eight are written in
kebab-case where the models are snake-case (`output-image-name`,
`machine-type`, `image-identifier`, `primary-disk-size`, `auto-update`,
`source-image`, `runtime`, `os`). It runs on the GCE path; the AWS caller
is commented out. Same class as this stage, recorded as stage 24.

76 (feature/pydantic-models + feature/pydantic-mapping + feature/credentials,
2026-09-12): stages 23, 21 and 17 — pydantic replaces cattrs, and two
stages fall out of it. **Branch one** swapped the decorator in 64 modules
(`pydantic.dataclasses.dataclass`) and nothing else: no class
restructured, no field renamed, no inheritance altered. It is that cheap
because pydantic dataclasses preserve everything this codebase reflects
on — `is_dataclass()`, `fields()`, `field(metadata=...)`, inheritance and
`__post_init__` — so the orchestrator's 323-line TemplateResolver, which
walks fields and the fk/templated/deferred metadata, never moved.
hashicorp-utils was left on stdlib dataclasses: its `type` is HCL's own
and its models never come from YAML. TRIAL-003 predicted six test
failures "as findings"; both causes were fixed instead. Pydantic
validates field types BEFORE `__post_init__`, which replaced the User
model's "non-blank first_name" with a generic type error — a
`field_validator(mode="before")` carries that wording now, and it is the
only guard in the tree with a type-level trigger, which is the audit the
stage asked for. And `ItemKind.model_cls` is declared `type[NameTyped]`
with a docstring saying so, but the item-kind test passed a stand-in that
duck-typed the protocol; nothing checked until pydantic enforced the
declaration. **Branch two** replaced the converter's ~190 lines with a
`PydanticConverter` behind the same two verbs, so the six structure call
sites were untouched, and it reproduces every old hook deliberately
because the acceptance test is that emitted output does not move: VCT
dispatch with alias canonicalisation; the registry side effect **only**
for `reg.builder_keys()` (registering every model double-registers nested
ones and trips the alias-collision guard); the two collection hooks; and
the two scalar hooks. Those scalar hooks belong to the MAPPER — cattrs
ran them only while structuring, so a directly constructed Group still
saw its raw string, and putting them on the model made `"1_024"` parse to
1024 before the model could reject it (an existing test caught it).
**Stage 21 came with branch two** as one word in a shared
`CSIS_MODEL_CONFIG` covering 103 decorators, and it loads only because
stage 22 had emptied the fixture; the same config carries
`coerce_numbers_to_str`, without which the fixture stops loading, since
YAML writes `family_version: 11` and AWS account ids unquoted and cattrs
coerced those. **Stage 17** then typed `credentials:` instead of leaving
it `dict[str, str]`: `credentials.profile_nme` is an error naming its
path, which is the gap stage 21 provably could not reach. `__bool__` and
a mapping-shaped `get_credentials()` keep every consumer working. Across
all three the golden regenerated BYTE-IDENTICAL on both runtimes every
time, which is the only reason a change this wide could be trusted. Six
tests changed in total, every one of them asserting which library's
exception class carried a refusal rather than the refusal itself; the
domain messages are unchanged and the tests assert those now. Found and
preserved rather than decided: the fixture's storage `parameters:` are a
mapping against a `list[str]` field, so iterating it has only ever kept
the key NAMES and discarded every value — nothing reads them and they
reach no output (recorded as §25). Stage 20's `type` -> `type_` alias
stays its own stage by the operator's decision; `populate_by_name` means
no constructor call has to change, which makes it much cheaper than
TRIAL-002 measured.

77 (feature/type-field-rename, 2026-09-12): stage 20 — the `type` field
becomes `type_`, and the YAML keeps saying `type`. 13 declarations became
`Annotated[str, Field(alias="type")]`, 68 attribute reads and 4 getattr
strings followed, and `BuilderBase.type` became `type_` so model and
builder share one name. **No configuration file changed and the golden
regenerated BYTE-IDENTICAL**, which is the whole acceptance proof: the
alias carries the YAML key in, and §23's unstructure writes it back out
with `by_alias=True`, so meta-state is untouched too. It was far cheaper
than TRIAL-002 measured, because `populate_by_name` means a constructor
accepts either name at runtime — 41 keyword arguments were renamed only
to satisfy the type checker, not the interpreter. Three classes of thing
keep `type` and each bit once during the pass: `dataclasses.Field.type`
is the ANNOTATION, not a model field, and renaming it in the converter's
own reflection broke the load with "'Field' object has no attribute
'type_'"; the hashicorp-utils records (`BackendRegistration`,
`TerraformVariable`, `PackerVariableDecl`, `BlockSpec`) carry HCL's own
`type` and are not ours to rename, so their CALLERS in the tf plugins had
to be put back; and `ModTestResult` is an internal record that never
comes from YAML. `ExecutableModel` is ours, so its one call inside
hashicorp-utils did move. Stage 23 is complete with this.

78 (feature/query-result-remap, 2026-09-12): stage 24 — the query-result
remap was dead, and had been from the start. The stage was written as
"eight of thirteen keys are dropped", which was true and not the point.
`image_from_query_result` built a dict with **no `runtimes`**, and
`Image.__post_init__` has required at least one since 2026-07-03 (the
repository's second commit), so the structure call always raised and a
bare `except Exception: return None` always swallowed it. **The function
never returned an Image, on either cloud, ever.** Its only caller,
`resolve_image_for_os_builder`, was defined on the GCE runtime builder
alone, had no base-class declaration and no callers of its own; the AWS
twin had already been commented out. Stage 21 made the failure worse
without making it visible: before, twelve of the seventeen keys were
dropped in silence and the model then rejected the result; after, the
structure call raised earlier — and the same bare `except` hid that too.
Also true, and worth keeping: twelve keys were written kebab-case against
snake-case fields, and three of those (`source_image`,
`primary_disk_size`, `auto_update`) ARE real Image fields that were
plainly meant to land, while four more were underscore-prefixed side
channels (`_networking`, `_region`, `_credentials`,
`_original_image_data`) that nothing ever read off the result. By the
operator's decision the whole chain was deleted rather than revived,
because nothing consumes it and reviving it would be new behaviour
needing a caller and a live GCE run to mean anything; a note at each of
the three sites says what stood there and why. Nothing observable
changed: lint, typecheck and 547 tests pass and the golden regenerates
byte-identical, which is exactly what "it never worked" predicts. The
lesson is the bare `except` around a structure call: it turned a
permanent structural error into "no image found" and kept it invisible
for two months.

79 (feature/storage-parameters, 2026-09-13): stage 25 — a storage
builder's `parameters:` never reached terraform. The field is `list[str]`
on `BuilderModel`, so a mapping written there iterates to its KEY NAMES
and every value is discarded; `get_parameters()` has no callers outside
the model and protocol anyway, and `parameters` appears nowhere in
emitted output. What makes this more than dead config is that the
declarations name the modules' own variables EXACTLY — EBS
`volume_type`, `size`, `encrypted`, `tags`; EFS `performance-mode`,
`encrypted`, `tags` — so an operator writing them reasonably expects them
to apply. They never have: the emitted EBS call carries `size = 100` from
the storage builder model, and volume_type and encrypted fall through to
the module defaults, which is why the live `mnt_data` volume is gp3 at
100 GB and not the gp2 at 8 GB the fixture declares. Wiring them up
naively would be destructive, not merely a behaviour change: on EBS both
`volume_type` and `size` force REPLACEMENT, so honouring the fixture
would plan a destroy and recreate of a live volume that holds data. By
the operator's decision the declarations were commented out with that
reasoning recorded at each site and **the field was left untouched in
code**, so the capability is reworked deliberately as stage 26 (which
also covers `parameters` on the instance builder and the OS runtime
subconfig, equally unread) rather than arriving as a side effect of a
cleanup. Nothing observable changed: the golden regenerates
byte-identical and the bar is green.

80 (feature/config-independence, 2026-09-13): stage 28 — one tree served
as both the suite's fixture and the live configuration, and the cost was
daily: every live change churned the golden and the gate-1 baseline, the
harness installed fixture subjects over live entries, and `test`/`test2`
were commented out of the live tree because the suite needed them. The
operator first proposed mounting `cs-image-system-testconfig` as a
submodule at `test_folder/`; the analysis (2026-09-13) found the
mechanism already supported — `commit_meta_state` resolves the repository
from the config root — but the framing wrong: a submodule keeps the dual
role and adds a second repository to it (144 commits had written into
`test_folder/meta-state/`, each would have left the gitlink stale). The
decision: split the roles, no submodule, remove `test_folder/`. Findings
on the way: (1) `packer-ebs-ansible/` was already gone (d78d623) — the
ignore pattern and two doc lines were stale; (2) the decommission overlay
did two things, the apply knob (`--apply-runtime` since stage 12) and an
undeclare that is eleven lines popping a name from the declaration dict,
so it became `--undeclare <kind>:<name>` and the live configuration needs
no overlay file at all; of the 17 overlays one was operational, two were
superseded and the README still claimed recipes used them, one was a
test device, and 13 were the recorded inputs of the stage 10–15 live
proofs (now `docs/history/overlays/`); (3) the parent's
`test_folder/generated*/` ignore was why every live `--commit` so far
silently dropped the generated half — the live repo carries the emitted
ignore policy hoisted to its root instead, and the first dry `--commit`
against it landed meta-state AND 82 generated files; (4) the base-only
pipeline test loaded the fixture in place, and the loader creates the
generation directories where it runs — invisible while the tree was
ignored, it wrote into the frozen fixture on the first run and now runs
over a copy; (5) the contract test's header regex never parsed variadic
recipes (`cli *ARGS`), so `cli`, `v2-dry-run` and `test-mods` had been
outside its view, and the new structural rule (every recipe that names
the live root has `config-guard` in its chain or checks inline) found six
`cloud-*` recipes with no guard; (6) `commit_meta_state` staged two
pathspecs then ran a bare `git commit`, which would have swept an
operator's staged config edit into a run's commit once the live repo
became where configuration is edited — fixed with pathspecs and a test.
The golden regenerated byte-identical over the frozen fixture, which is
the proof the copy is faithful; the bar is green with the live root
pointed at a nonexistent path. Not done here: the sibling's three new
commits (viability edits and two dry runs) are unpushed — pushing is the
operator's act; the old tree's 6.7 GB of untracked provider cache is
parked at `../test_folder.pre-stage28`, deletable.

81 (feature/tfmodules-split, 2026-09-13): stage 27 — seven of the nine
terraform modules kept everything in one `main.tf` (the `terraform`
block, variables, data sources, locals, resources and outputs
interleaved; in `aws_storage_ebs` the locals sat between two variables),
`aws_instance/` had already been split by the operator into
`provider.tf` / `variables.tf` / `main.tf` / `outputs.tf`, and the Okta
module was split under its own prefixed names. Every module now has the
`aws_instance` shape. The move is by top-level block, each carrying the
comment lines above it, in original order within each file; a script
asserted the multiset of blocks identical before and after, and the
byte-level check that every original block appears verbatim in exactly
one new file — the split is a re-filing, not an edit, so no plan can
differ. `tofu fmt -check` is clean over the nine modules (the ignored
`tftest/` harness was already unformatted and is not a module); `tofu
init -backend=false && tofu validate` succeeds in each (run directly:
the Justfile has no target for it, and this stage was confined to
`tfmodules/` and the tracking documents — a `tf-validate` target is a
candidate for the next Justfile change); the init's lock files were
removed rather than committed. Nothing outside `tfmodules/` reads a
module's file layout except one test that asserts the instance
module's `ignore_changes` and volume attachment in its `main.tf` — both
are resources and stayed there. The golden is untouched by construction
(it pins module CALLS, not module contents) and the bar is green.

82 (feature/arguments-and-variables, 2026-09-13): stage 26 — `parameters`
carried two unrelated meanings under one name and one type. The image
builders declared `parameters: ["build", "."]` beside `executable:
packer` (argv, which the declared `list[str]` fits); the storage builders
declared a MAPPING of their terraform modules' own variable names (inputs
to a module call, which the list type silently mangled — §25). Neither
was read: nothing called `get_parameters()`, and the packer plugin
hardcodes `build` when it assembles its command line, so the image
builders' declarations described the plugin rather than fed it. The
operator chose to drop the argv meaning (no `arguments` field; the three
declarations deleted from both configurations with the reason) and to
distinguish the module-input meaning as `variables:`, typed per provider
from the module's `variables.tf` (§27): a misspelt key — the fixture's
own `performance-mode` — is refused at load instead of dropped. The field
is a nested model like §17's credentials; precedence is what the builder
computes from the storage item (name, groups, lifecycle, restore snapshot,
placement) over declared variables over module defaults, with tags merged
item-over-builder; sizing knobs stay builder fields, and EBS `size`
became a real field (it had been an untyped class attribute, so a YAML
`size:` on the EBS builder was refused while `getattr` read the default).
A `parameters:` declaration is refused by a before-validator naming the
replacement — which had to handle both the converter's dict and the
constructor's keyword arguments, since a pydantic dataclass hands a
before-validator `ArgsKwargs` when built in code. The golden was
byte-identical after the field removal and the wiring (nothing declared),
then moved by exactly the three AWS module calls when the declarations
were restored: `volume_type`/`encrypted`/`tags` on EBS,
`performance_mode`/`encrypted`/`tags` on EFS, the builder's default tags
merged under the bucket's own on S3 — read and accepted as the stage's
evidence. The live volume: `mnt_data` (vol-0fe1e27716f86c2f2) was found
detached since the stage-1 teardown, never snapshotted, with no recorded
write; the operator had it snapshotted first (snap-08b1ebbccfbdd7570,
volume kept, tagged csis-mnt_data-archive) and chose to declare what
exists (gp3, 100 GB) rather than replace it, so the next real storage
apply changes tags in place and nothing else. Both configurations changed
in the same step; the live one validates and dry-runs with the variables
in its emitted module calls.

83 (feature/retire-groups-field, 2026-09-14): the last V1 field. The
instance model's `groups` was kept on 2026-09-11 (ledger 75) on the
condition that the converter did not refuse unknown keys; stage 21
removed that condition the next day, and stage 23's plan to move the
guard into a validator pointed at stage 22, which never touched it — so
the field outlived its reason by two days and a stage. Retired the way
stage 26 retired `parameters`: a `model_validator(mode="before")` on
`Instance` raises the same migration message when a `groups:` key is
present, so the wording the retirement stage cared about survives and
the field does not. The test asserting the message passes unchanged;
nothing read the field. Golden untouched (the field never reached
emission); bar green.

84 (feature/config-drift, 2026-09-14): `just config-drift` — the
question "is the committed emission current with the declarations" had
no command. `validate` says the tree loads; the strict state query
compares records with the clouds; and a bare `git status` after a run
says only that a run happened, because every run stamps its id into the
emission (`csis_run` tags, `# run id` comments), date-stamps image names,
and rewrites the run summary, the state report and the run journal. The
recipe is the golden mechanism pointed at the live configuration: a
headless dry `run --all` over a private copy in the sibling shape (no
`.git`, no generated trees), compared with `git archive HEAD generated`
of the live repository, after normalising run ids (`<RUN>`), the image
date stamps (`<STAMP>`), the absolute root (`<ROOT>` — the copy's root
resolved with `pwd -P`, because the CLI resolves macOS's `/var` to
`/private/var`) and dropping tool residue, the three run-local files and
the staging directories git cannot hold (`temp_assets`,
`release/release`, `retention/retention`, all empty). Exit 0 current, 1
with the diff, 2 when the dry run fails (a preflight refusal shows the
log excerpt). Proven both ways on the live repository: first BEHIND by
nine files, all real — the three storage module calls stage 26 changed
and the instance-image tree, whose recorded form was the dry
decommission with `gce-test` undeclared while the declarations include
it; then, after one dry `--commit` run recorded the emission (ea89f7f),
CURRENT. Pinned by the Justfile contract test (the recipe is guarded,
normalises, diffs, and never passes `--commit`); noted in OPERATIONS
"CI shape" and in stage 18, whose dry run against the live configuration
now has a sharper question to ask.

85 (feature/retire-v1-steps, 2026-09-15): stage 31 — the phase enum
file carried two enums that had to mirror each other by hand (a FIXME
said so), a `LifecycleStep` class with state and function-type enums,
two step lists and two function-name mappings built by filtering enum
values on their `pre-`/`post-` prefix. All of it served the V1 phase
loops in `commands/build.py`, which had had no caller since `build-all`
became a V2 alias; the V2 runner walks `LifecycleSpec`/`LIFECYCLE_PHASES`
and its own phase→function table, and imported exactly one thing from
that module, `execute_before_or_after_phase`, now in the runner itself.
Tracing callers found more dead than the stage text expected: the five
V1 stub modules (`testify`, `commit`, `execute`, `verify`, `cleanup`)
held nothing but a predefined function and its base-prefixed wrapper,
referenced only by the commands package's re-export list and each
other; `default_image_resolution.py` — which the stage text had called
live — had no caller at all outside a comment; `run_result.py` was
imported only by the step class; V1's `predefined_validation` (wipe the
generation path, write `.gitignore`, collect errors — each of which V2
does itself, per lifecycle) had only its wrapper. Eight modules deleted,
eight wrappers removed, the config model's `predefined_lifecycle` field
and holders gone, the all-comment `predefined-lifecycle.yml` removed
from the frozen fixture and the live repository together (an unknown
key is refused at load). The enum's 34 members STAY — decided
2026-09-15 on the question "might plugins need those phases": a
plugin-registered lifecycle may bind any member and the finalization
script orders deferred commands by enum position, so the unused members
are extension points; the enum's docstring and OPERATIONS now say so,
and DESCRIPTION.md stops calling the V1 phases "currently stubs". Left
for a later pass, noted rather than done: `sleep_between_phases` and
the state-marker path in the context, which only the deleted loops
wrote (`sleep_between_steps` is still a config key, so removing the
field would refuse the fixture). Nothing in the emission came from the
deleted path: the golden regenerated byte-identical, the live
configuration validates without the file, and the bar is green.

86 (feature/retire-base-only-path, 2026-09-15): stage 32 — asked "do
`basic` and `generated_base_image` have any use?" in the live tree: the
first was an empty stray from the copy-and-setup morning (removed by
hand), the second was created on every configuration load and never
written to. The loader always passed `base_only=False` from the CLI, so
the context's switch never steered the generation path, the state
marker or the final-execution path anywhere but the normal tree; what
kept the directory appearing was `_make_parent_and_delete` of a
base-image state marker that nothing wrote since stage 31. The triage
the stage asked for: the loader's base-only mode read NO item kinds (a
"builders only" load), no command could request it, and the two e2e
tests that passed it assert on builders a full load also has — a V1
leftover of the two-run spec (base run, then execution run) that the V2
lifecycles replaced. Removed: the switch and the loader's positional
parameter (the CLI's call still passed it, shifting every later
positional by one — pyright caught "dry_run already assigned" before
any test ran), the base-image generation directory and its config key,
both state markers and their create-and-delete at load, the base
final-execution path, `sleep_between_phases` with the
`sleep_between_steps` key (dropped from the frozen fixture and the live
repository together, since an unknown key is refused), the stale
stage-22.5 comment lines beside it, five constants nothing read, and
the `generated_base_image` excludes in pyproject, the Justfile copies,
the harness and GOLDEN.md. Kept: `final_execution_path`,
`sleep_before_finalization`, the item-kind `base_only` flag (a different
concept: the base_images collection is registered but not auto-read),
the resolver's lifecycle-derived `is_base`, and `--base-only` itself
with its one remaining meaning. Golden byte-identical; the live
configuration validates without the key and a load no longer creates
the directory.

87 (feature/ci-end-to-end, 2026-09-15): stage 18 — CI had never been
green. Asked "18 or 19 next?", the first fact checked was the workflow's
history: 245 runs since 2026-08-14, zero successes, on every branch. Every
one failed the same three tests in `test_config_resolution_e2e.py`: a
configuration load finalizes the Okta workspace, which asserts its two
`TF_VAR_*` credentials exist (`okta_tf_workspace._require_tfvar`); the V2
harness stubs them for every harness-driven test, but these three set
only `USER` and inherited the rest from the developer's shell, where
`.envrc` supplies them. Every "bar green" report of the last two weeks was
true and blind to it, because the bar runs in that shell; stage 32 had
widened it from one test to three by making them load fully. They stub
the same four variables now, proven with the shell's variables unset.
The workflow is two jobs. `verify` runs `just init` and `just verify` on
every push and pull request with no configuration and no credentials
(the type-check is blocking now that pyright is at 0 errors; the old
`continue-on-error` is gone). `live` runs after it on pushes and a
nightly schedule, never on pull requests: the live configuration checked
out BESIDE the system so both the Justfile's default root and the
configuration's `../cs-image-system-3/tfmodules` resolve, federated
read-only AWS and GCP identities, a `[profile noaa]` shim because the
runtimes name their profile and the preflight reads a static-key profile
as present, the pinned tools symlinked where `executables.yml` expects
them, then `validate`, `config-drift`, `cloud-preflight` and
`test-mods --strict` — all gated on seven secrets, none of which exist
yet, so the job prints one SKIPPED line per missing item and passes.
Three things the reconnaissance found that the stage text had not: the
configuration repository is PRIVATE on GitHub (the standing constraint
calls it public by design; either a read token or a visibility change is
the operator's call), a configuration load reaches GCP for network
discovery so "GCP out of scope" cannot hold for the live job, and the
runtimes' named profile means federated credentials need the shim. The
first push's run failed on a type error in the new workflow test — the
blocking type-check working as intended — and run 34967316313 is the
first green run: `verify` 562 passed, `live` success with four SKIPPED
lines. `tests/test_v2_ci_workflow.py` pins the shape. What remains is
the operator's: the seven secrets, and the real-run-on-master job of the
CI model (branches verify, master applies), which is a stage of its own.

88 (feature/encrypted-values, 2026-09-15): stage 33 — a value the
configuration must carry but must not publish has a home in the tree.
The type is `EncryptedStr`, an `Annotated[str, PlainValidator]` in
`base/encryption.py`: a value of the form `ENC[age:<base64>]` is
decrypted at load with the identity in `CSIS_CONFIG_IDENTITY` (the
`AGE-SECRET-KEY-1…` string, an identity file, or a directory of them),
an unmarked value passes through, and a marker with no identity is a
load-time refusal that names the variable. The result is `Decrypted`,
a `str` whose repr is `Decrypted('***')` and which PyYAML writes as a
plain scalar, so the read-model files still serialise. Element-level,
as required: `set[EncryptedStr]` on group `members`/`admins`,
`EncryptedStr` on user `name`/`first_name`/`last_name`/`email` and on
the Okta workspace's `key`/`secret`, each element its own age file to
every recipient in `cfg/_config.yml` `encryption.recipients`. The
implementation is the pure-Python `age` package (0.5.1) in the standard
format, so the `age` CLI and the three `bin/*_age.sh` scripts
interoperate. The CLI grew `encrypt VALUE` / `encrypt --file F --field
NAME…` (textual, in place, comments kept, list-item scalars included),
`decrypt`, and `reencrypt [--dry-run]`; the three run before the
configuration loads, since the tree may be unreadable without them.
Proven: nine tests in `tests/test_v2_encrypted_values.py` (marked and
unmarked values, element-wise sets and dicts, the hidden repr, the
missing- and wrong-identity refusals, file and directory identities,
multiple recipients, textual field encryption, rotation); the frozen
fixture's rosters encrypted to a committed TEST identity with the
golden byte-identical (125 files, 0 changed); the live repository's
rosters — 87 values — encrypted to the four recipients (CI, both of
the operator's identities, Zach Wills; not the fifth key found beside
them), validated with one identity, refused without, `config-drift`
current, committed and pushed (testconfig 741b5f6). Bar green (572
passed) in a shell with no identity variable at all. Four things the
plan had not said. Pydantic flattens a `str` subclass returned by a
Before/After validator back to `str`; only a `PlainValidator` keeps
`Decrypted`. The converter's collection coercion matched the type by
`str(type).endswith("set[str]")`, which `set[EncryptedStr]` no longer
is; it now inspects the annotation, and the fix briefly landed the
`@singleton` decorator on the new helper instead of the converter,
which one test caught. A list-item scalar (`- name: x`) needed its own
regex case. And the derived email (`default_user_email_template` over a
decrypted name) is a plain string in the loaded model, so a repr shows
it — §34's problem, made visible here. The CI `live` job gates on one
more secret, `CSIS_CONFIG_IDENTITY`; the operator's `.envrc` does not
export it yet, so every recipe that loads the live configuration
refuses until it does.

89 (feature/emit-by-reference, 2026-09-15): stage 34 — a declared-encrypted
value never reaches the emission in clear. A `Decrypted` value now carries
the `marker` it was read from, and the terraform collector keeps one
sensitive map per root: `sensitive_ref(workspace, key, value)` registers a
decrypted value's ciphertext, requires `hashicorp/external` and returns
`local.sensitive["key"]`; `generate_sensitive_blocks` emits one
`data "external" "sensitive"` whose program is `cs-image-system decrypt
--json` (the external protocol: a JSON object of markers in, the decrypted
object out, unmarked values through) and `locals { sensitive =
sensitive(...) }`. `OktaTFUser` routes first_name, last_name, email and
login through it (one registered value when the login is the email), both
Okta builders register before the terraform block and emit the blocks
after the providers, and a declared-encrypted workspace credential reaches
its provider block the same way instead of being quoted into HCL — a leak
§33 had opened and nothing exercised. `commit_meta_state` never stages
`tfplan`, `*.tfstate*`, `*.tfvars`, `.envrc` or key material: the names
are excluded by pathspec on both `add` and `commit`, so a hand-staged plan
is not swept either, and a warning names what was left out. The rule,
decided when the plan's "same ciphertext as the YAML" met the nine
derived addresses (age encryption is randomised, so encrypting at
generation would move the emission on every run): no declared-encrypted
value other than a username in clear; an address derived from the email
template is public by construction (username + template) and stays
plaintext — the operator's choice over materialising it into the source
or deriving it inside HCL, neither of which hides more. Proven: 19 tests
in `tests/test_v2_emit_by_reference.py` (marker retention, the
collector's refs and blocks, the lookup by reference against the literal,
the credential by reference, the decrypt protocol and its refusals, the
fixture emission carrying only source ciphertexts with all ten declared
emails absent, the whole-run invariant over generated/ and meta-state, the
never-staged list, and a run commit that leaves a plan and a state file
out of both the commit and the index); the golden moved in the two
identity-root files only. Live: a dry `--commit` run regenerated the
emission (testconfig 048b079, 21 files, no plan or state among them),
`config-drift` current, and a real `tofu init` and `tofu plan` of the
user root with the identity exported ran the decrypt program and read all
19 Okta users, ten through `local.sensitive[...]`: exit 0; the plan JSON
holds the 21 addresses in clear, as designed, and is ignored. Two notes
for the next reader: the invariant test matches whole tokens, because a
last name is part of the public username, and skips values under three
characters, because an initial matches the world; and the derived nine
are still literals in `generated/`, by decision, so §35's scanner must
allow them (or the operator declares them encrypted, which takes one
`encrypt --field email` after adding the lines).

90 (feature/public-safe-gate, 2026-09-15): stage 35 — a commit-time gate over
everything staged. One scanner, `base/public_safe.py`, reads BYTES (a zipped
`tfplan` is opened and its members scanned, a gzip member likewise), refuses
by NAME whatever a plan, state file, tfvars file, `.envrc` or key material is
called, and by SHAPE — everywhere, prose and test code included — a JWT, a
PEM private-key body, an AWS access key, a Slack or GitHub token, an age
identity, a GCP service-account file and a `TF_VAR_*=` assignment with a
literal value; two softer shapes, an address and a long mixed-case base64
string, are refused in configuration and emission but not in Markdown or
Python test modules. Public structures pass on sight (`ENC[age:…]`, age
public keys, lock-file hashes, SSH public keys, scp-style git URLs, example
domains); everything else is allowed by decision with the reason beside it,
in `cfg/_config.yml` `public_safe.allow` — a substring or `path:<glob>` —
declared on the model so a load refuses an unknown key like everywhere
else, and read as text so a tree that cannot load is still gated. Where it
runs: `commit_meta_state` scans every file it is about to stage, with the
configuration's allowances, BEFORE the index is touched and refuses the
whole commit on a finding (`assert_public_safe`, the first gate, is now a
thin call into the same scanner's hard rules); the plain
`.githooks/pre-commit` runs `public-safe --staged` on every hand commit in
both repositories, installed through `core.hooksPath` by `just init` here
and `just hooks-live` there; `just public-safe` scans this checkout
(tracked files plus untracked files that are not ignored, the frozen
fixture's allow list) and CI's `verify` job runs it after the bar; `just
public-safe-live` scans the live configuration. A finding names the path,
the rule and the first characters, never the value. Proven: 15 tests
in `tests/test_v2_public_safe.py` (every hard shape refused in prose and
test code too, the negatives, the soft shapes and their exemptions, the
public structures, the allow list by substring and by path, a zipped plan
opened, the refused paths, a tree scan that sees untracked but not ignored
files, the index scanned as it would be committed, a run commit refusing
and leaving the index untouched then honouring the configuration's allow
list, the meta-state backstop, and the whole checkout scanned as CI does
it); this checkout 620 files clean, the live configuration 121 files
clean; and live, in the configuration repository: a commit carrying a
fake PEM header refused by the hook, a plan forced into the index refused
by name, the real changes committed through it (testconfig ff91941) and
pushed. What the gate found on its first pass, all fixed here: the
recipients' comments §33 had written into the live `cfg/_config.yml`
carried two people's addresses; the frozen V1 baseline carried six
declared addresses in clear (redacted — its comparisons were demoted on
2026-09-11 and it is evidence, not a gate); five test modules and the key
script's help text carried literal fake shapes (now built by
concatenation, so a fake never looks real); a docstring carried example
addresses on a real domain; and the Justfile's scp-style clone URL read as
an address until git URLs were made structural. The JWT rule lost its word
boundary because a plan's binary glues a token to anything. The derived
addresses in `generated/` pass by the allow list, as §34 decided.

91 (feature/ci-profile-credentials, 2026-09-15): the live job's first real
runs, all eight secrets in place. Three things stood between the gate and a
green run, found one per run. GitHub's OIDC subject for this organisation
carries the owner and repository ids
(`repo:infrastructurebuilder@50206755/cs-image-system-3@1316173871:ref:…`),
so the role's `repo:infrastructurebuilder/cs-image-system-3:*` condition
never matched — CloudTrail's `principalId` on the denied
`AssumeRoleWithWebIdentity` showed it; the trust policy now accepts both
forms. botocore drops the environment credential provider whenever a
profile is named explicitly, and the runtimes name `noaa`, so the
federated keys the credentials step exported were invisible to
`boto3.Session(profile_name=…)`: the shim step now writes them into
`~/.aws/credentials` under `[noaa]` beside the config section. And a dry
run executed each root's `tofu init` WITH the S3 backend at generation
time, which a read-only role without the state bucket cannot do — and
should not: state holds decrypted values. A dry run's init is now
`-backend=false` (providers installed, emission validated, nothing after
it needs state); a real run keeps `-backend-config=`. Consequence for an
operator: after a dry run, a hand-run of a `run-*.sh` script needs its
own `tofu init -backend-config=…` first, which the scripts never carried.
The AWS role itself: `csis-github-readonly`, trusted only from this
repository's tokens, `ec2:Describe*`, `elasticfilesystem:Describe*` and
the caller-identity check, nothing on S3. GCP: workload identity pool
`github` with a provider admitting only this repository, service account
`csis-github-readonly` with `roles/compute.viewer`, impersonable only by
that repository's principal set — all free of charge, no billable
resource. A fourth thing, on the run that
reached the comparison: `config-drift` normalises the absolute
configuration root it knows, and CI's checkout is not the machine that
generated the committed emission, whose `run-release.sh` and
`run-retention.sh` carry `--root-dir /Volumes/…/cs-image-system-testconfig`;
the normaliser now blanks any `--root-dir` value. Noted, not done: a
committed run script that names one machine's absolute path is not
portable — a root relative to the script would be — which is an emission
change that moves the golden, for a stage of its own.

92 (feature/synthetic-personas, 2026-09-15): the frozen fixture's people
are synthetic. The rosters under `tests/fixtures/config/groups/` were the
nineteen real users and the real group rosters copied at stage 28, encrypted
since stage 33 to a TEST identity that is itself committed — the encryption
exercised the mechanism and protected nobody — and stage 34's decision to
leave DERIVED addresses in clear put real usernames into the golden, the V1
baseline, ten test modules, PLAN.md, EXPLORE.md, an OPERATIONS example and a
code comment. Now: nineteen personas with phonetic-alphabet surnames in the
roster's exact shape (the same explicit/derived split, the mixed-case
username, the same memberships), encrypted to the same TEST identity; the
fixture's `default_user_email_template` is `{{ user.name }}@example.invalid`
and its `public_safe.allow` no longer names `@noaa.gov`, so the gate over
this repository refuses a real address outside prose and tests — on the
first run it caught the roster file's own comment, which still named the
real derived domain. The golden moved once (the eight identity files); the
V1 baseline carries the same substitution beside its stage-35 redaction
note; `tests/test_fixture_personas.py` decrypts the rosters and pins that
every name is from the persona lists, every address is on an example
domain, every member is a roster user and the template cannot deliver. The
live configuration is untouched: real, encrypted to the four recipients.
The substitution table is the operator's, outside the repository
(`_uncommitted/`). The operator's own addresses in PLAN.md and
BILLING_REMINDERS.md stay by the stage's terms.

93 (feature/portable-run-scripts, 2026-09-16): a committed runner script
is self-contained. Ledger 91 noted what tied `run-<lifecycle>.sh` to one
machine: `--root-dir /Volumes/…` in the release and retention lines, hidden
by a config-drift normaliser rule, and the assumption of an initialised
root — `init` is a generation-time command, so after a dry run
(backend-less since ledger 91) or in a fresh clone (no `.terraform/`) the
script's first `tofu plan` failed. Now the header defines
`CSIS_ROOT="$(cd "../.." && pwd)"` (the root relative to the script, computed
at generation), every root-based argument renders through it
(`--root-dir "$CSIS_ROOT"`, `--overlay "$CSIS_ROOT/…"`) while the executable
keeps the absolute argument for the in-process real run, and every
terraform root's deferred block begins with its own `tofu init -input=false
-reconfigure -backend-config=<file>` — the real-run form regardless of the
run's mode, deferred like the plan so the in-process run repeats it
(idempotent, seconds) and the script stays a faithful record. The normaliser
lost both root rules and the golden its `<config-root>` token: an absolute
path in the emission is now drift and a golden failure, not noise. The
golden moved once (the five run scripts). Proof: the live configuration's
dry `--commit` run (testconfig 79bb18e, pushed) carries the new scripts with
no machine's path; a fresh clone of it at another path, with no
`.terraform/` anywhere, ran `generated/identity/run-identity.sh` to
completion — backend initialised, plan against the S3 state "No changes",
gate passed, nothing applied. Two findings on the way: the first sibling
run failed at a generation-time `tofu init` because it ran concurrently
with the bar's tests over the same plugin cache (alone, it passed — one
tofu-using process at a time on a machine); and a script header line that
ends in a comment cannot be joined to a following command with `&&`.

94 (feature/hygiene-state-encrypt, 2026-09-16): three small things,
bundled. (1) `encrypt: true` on every S3 state backend, live and fixture
(`cfg/state-backends*.yml`): the emitted partial backend configurations
say `encrypt = true` (nine golden files moved), and the real-run
generation-time init now carries `-reconfigure` — a backend argument
changed under roots that were already initialised, the state is remote so
there is nothing to migrate, and without it tofu refuses with "Backend
configuration changed"; an existing state object is re-encrypted
server-side when next written (S3 encrypts new objects by default since
2023, so the flag is a declaration as much as a change).
`tests/test_v2_state_encryption.py` pins the declarations and the emission.
(2) The release publish target, §16's open decision, is the tag alone
(decided 2026-09-15): the `release` recipe's SKIPPED wording and OPERATIONS
say so; an index through `uv publish` is stage 41. (3) The suite's instance
subjects (`test`, `test2`, `gce-test`) are declared in the fixture's own
`instances/instances.yaml`; the harness had injected them from
`tests/fixtures/test_instances.yaml` since 2026-09-05, when the LIVE tree
stopped declaring them — the fixture is test-owned and never applied, so a
dormant declaration costs nothing there, and the live tree keeps its
decisions (test/test2 absent, gce-test ephemeral). The golden did not move
for the fold: the declarations were identical, the proof that the
injection had been a copy. Sibling commit a56306b (pushed) carries
the encrypted backend configurations; config-drift current.

95 (feature/publish-tree, 2026-09-16): the publishable tree is built by a
recipe, not by hand. `just publish-tree <root> <dest>` (TODO §40.2) exports
the tracked files of `<root>` at HEAD — `git archive`, so nothing ignored
can enter and a dirty root is refused — drops a `PUBLISH_EXCLUDE` list
(default none), runs the public-safe gate over the result with the root's
own allow list (the fixture's for this repository), checks the ignore file
for the eight lines that keep environment files, key material, plans and
state out, then makes ONE commit on `master`; it never pushes and never
adds a remote. This repository's `.gitignore` gained `tfplan`, `*.tfstate`
and `*.tfstate.backup` (already refused paths) so both roots pass the same
check. `tests/test_v2_publish_tree.py` proves it over a throwaway git
repository built from the frozen fixture: one commit with exactly the
tracked files, an exclusion left behind, and four refusals (a finding
before any commit, a missing ignore line, a dirty root, an existing
destination). Dry proofs over both real roots produced one-commit trees
with the tracked file count and no environment file, scratch directory or
tool residue, and were deleted. The remote is the operator's act (§40.4).
