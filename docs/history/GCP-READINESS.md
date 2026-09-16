> **Frozen record.** This document is history, kept verbatim as it was when frozen; nothing in it describes the present. Current documentation starts at [README.md](../../README.md).

# GCP Readiness Checklist

**All Work Complete As of 2026-09-12**

*Written 2026-09-02 from a read of [PLAN.md](../../PLAN.md) ("GCP increment 3"),
[EXPLORE.md](../../EXPLORE.md) ("GCP Support — exploration"),
[DESCRIPTION.md](../../DESCRIPTION.md), [GOALS.md](../../GOALS.md), [TODO.md](../../TODO.md) and
[docs/OPERATIONS.md](../OPERATIONS.md).*

Goal: get the repo, the operator, and a Google Cloud project ready for a
first **real** GCP run of the four-lifecycle meta-workflow, spending as
close to $0 as possible by leaning on the GCP Always-Free tier and the
new-account trial credit.

Where the code already stands (all merged to `develop`):

- The packer builder is provider-neutral; `packer-gce` bakes via the
  `googlecompute` source with GCE labels/image-families as lineage/series
  (EXPLORE increments 1–2).
- `packages/tf-gcp-plugin` provides `tf-gcp-pd`, `tf-gcp-filestore`,
  `tf-gcp-gcs`, `tofu-gce`; modules exist under `tfmodules/gcp_storage_*`
  and `tfmodules/gce_instance`; `session_mechanism: iap` is wired
  (PLAN.md "GCP increment 3", gates 1–6 + 8 done).
- Everything was proven by **generation + `tofu validate` only** — the
  fixture's `gcloud-east1` runtime still carries placeholder
  project/zone/network values, and nothing has ever touched a real GCP
  account.

Price notes below are ballpark from documentation and MUST be re-verified
against the live pricing pages before any apply — see section 3.

---

## 1. Decisions to close first (stakeholder)

These are the open questions recorded in [PLAN.md](../../PLAN.md) "GCP
increment 3 → Open questions". Each blocks a later section.

- [x] **Project (decided 2026-09-02): `csis-sandbox`, number
      86233086783** — a fresh, dedicated project, created by the
      operator. (An earlier candidate, `cs-image-system-3-test` /
      783381521490, was superseded the same day.)
- [x] **Region/zone (decided 2026-09-02): `us-east1` / `us-east1-b`**
      — Always-Free-eligible, and what the runtime YAML now carries.
- [x] **Filestore: NO (user decision 2026-09-02).** `pd` + `gcs`
      suffice; `tf-gcp-filestore` stays generation-proven only, and
      `file.googleapis.com` stays un-enabled (see §2 note).
- [x] **IAP confirmed (user, 2026-09-02), not OS Login.**
      `session_mechanism: iap` is set on the live runtime entry.
- [x] **Image sharing stays deferred (user, 2026-09-02)** — images
      remain private to `csis-sandbox`.
- [x] **Decide the terraform state backend for GCP roots.** Today every
      root's state lives in the S3 backend (tf-s3-state), which means a
      GCP run needs *both* AWS and GCP credentials in the environment.
      Options: (a) keep S3 state for GCP roots (zero new code, dual
      credentials); (b) add a `tf-gcs-state` backend plugin (a GCS
      bucket within the 5 GB free allotment costs nothing). Recommend
      (a) for the first run — it is free and already works — and record
      (b) as a follow-up.
      **Decided (user, 2026-09-02): (a) — the existing S3 backend for
      now.** Consequence: every GCP run needs BOTH `aws sso login
      --profile noaa` (state backend) and GCP ADC in the environment.

## 2. Google Cloud account, project, and billing groundwork

- [x] Google account / organization identified (operator, 2026-09-02).
- [x] Project created (operator, 2026-09-02): **`csis-sandbox`**,
      number 86233086783 — already wired into the runtime YAML.
- [x] Billing account attached (operator, 2026-09-02).
- [x] Budget created (operator, 2026-09-02).
- [x] Enable only the APIs the system needs — **done by the operator
      2026-09-02** ("everything down to file.googleapis.com"):
  - [x] `compute.googleapis.com`
  - [x] `storage.googleapis.com`
  - [x] `iam.googleapis.com` + `iamcredentials.googleapis.com`
  - [x] `iap.googleapis.com`
  - [x] **`file.googleapis.com` NOT enabled — and that requires no
        action.** The operator "could not find it": correct — it never
        appears anywhere until someone enables it, and un-enabled is
        exactly the desired guardrail state. Verify anytime with
        `gcloud services list --enabled --project csis-sandbox`
        (file.googleapis.com must be absent).
- [x] Check default quotas in `us-east1` — **nothing to SET**: this item
      is a read-only confirmation that defaults suffice (they do at this
      scale). To look: Console → IAM & Admin → Quotas & System Limits,
      filter Service = Compute Engine API and Region = us-east1; or
      `gcloud compute regions describe us-east1 --project csis-sandbox`
      (each quota prints `usage`/`limit`). Only ever ACT on this if a
      later apply fails with a QUOTA_EXCEEDED error naming the quota.
- [x] Billing export to BigQuery — **done 2026-09-02 (STANDARD)**.
      **Answer for the record:
      STANDARD export is enough** — it carries daily cost per service,
      SKU, project and **label**, which is all the §10 hygiene queries
      need. Detailed adds per-resource rows (individual VM/disk ids);
      free at this volume but unnecessary — the csis labels already map
      costs to resources. Either way exports begin at setup time, never
      retroactively, so if wanted, set it up before the first bake.

## 3. Verify current free-tier terms and prices (verified 2026-09-02)

Verified against the live pages/current sources on 2026-09-02; the two
starred rates are ballpark-confirmed and worth a one-minute glance at
the pricing console before any large image is kept:

- [x] Always-Free compute confirmed: **1 non-preemptible `e2-micro` per
      month** in `us-east1`/`us-west1`/`us-central1`, **30 GB-months
      standard PD**. NOTE: the free page no longer lists a snapshot
      allotment — assume snapshots bill from byte one.
- [x] Always-Free storage confirmed: **5 GB-months regional GCS** in the
      same regions, 5,000 class-A + 50,000 class-B ops/month.
- [x] Egress: **BETTER than assumed** — the free allowance is now
      **100 GB/month** outbound from North America (excl. China/
      Australia); ingress free. Egress discipline stays trivial.
- [x] External IPv4 in use: **$0.005/hr** standard VMs, $0.0025/hr on
      spot (since 2024-02). No free-tier exemption relied upon: our
      instances launch with no external IP anyway; only bake VMs hold
      an ephemeral one for minutes.
- [x] *Custom image storage ~**$0.05/GB-month** (archive size) and
      snapshot storage ~**$0.05/GiB-month** regional (archive-class
      snapshots ~$0.019 + retrieval fee + 90-day minimum) — snapshot
      rate is HIGHER than this file first assumed ($0.026); pd-standard
      ~$0.04/GB-month.*
- [x] Spot VM discount confirmed: **60–91%** below on-demand (floor
      60%), price can move up to once per 30 days — fine for build VMs.
- [x] Cloud NAT confirmed avoidable and worth avoiding: $0.0014/VM-hr
      gateway (cap $0.044/hr) + **$0.045/GiB processed both directions**
      + the external IP. Ephemeral bake-VM IPs stay the cheap path.
- [x] Filestore confirmed as the trap the "no" decision assumed:
      Basic HDD **$0.16–0.20/GiB-month with a 1 TiB minimum** ≈
      **$165–200/month idle**. `file.googleapis.com` stays un-enabled.

## 4. Credentials (environment-only, per the credential contract)

The contract in [docs/OPERATIONS.md](../OPERATIONS.md): no
credential ever enters the config tree, generated IaC, or meta-state —
everything arrives via the environment. PLAN.md's increment-3 record
confirms GCP follows suit (`GOOGLE_APPLICATION_CREDENTIALS`/ADC).

- [x] Service account created 2026-09-02:
      `csis-runner@csis-sandbox.iam.gserviceaccount.com`.
- [x] Least-privilege roles granted 2026-09-02:
      `roles/compute.instanceAdmin.v1`, `roles/compute.storageAdmin`,
      `roles/storage.admin` (project-level for now; bucket-scoping is a
      follow-up) on the project, and `roles/iam.serviceAccountUser` on
      the account itself. No org-level roles, no owner/editor.
- [x] **Credential form decided 2026-09-02: impersonated ADC — no key
      file, ever.** Concretely, a one-time grant plus a one-time login:
      1. Grant YOUR user *Service Account Token Creator* on csis-runner
         (Service Accounts → csis-runner → Permissions → Grant access →
         your Google email → role `Service Account Token Creator`).
      2. `gcloud auth application-default login \
           --impersonate-service-account=csis-runner@csis-sandbox.iam.gserviceaccount.com`
      Everything (terraform google provider, packer googlecompute, the
      state-query python clients) then acts AS csis-runner via
      short-lived tokens — the least-privilege roles get exercised for
      real, and there is no long-lived secret on disk. Plain
      `gcloud auth application-default login` (acting as your own
      account) is the acceptable quick fallback for dry runs only.
- [x] **Fixture credential leak-shape fixed (2026-09-02)**: the
      `service_account_key_file` field is removed from
      [test_folder/cfg/runtime-builders.yml](../../test_folder/cfg/runtime-builders.yml);
      credentials are environment-only (ADC or
      `GOOGLE_APPLICATION_CREDENTIALS`). The plugin resolves project
      from config and falls back to default credentials.
- [x] (done 2026-09-02) Add the GCP row to the credential-contract table in
      [docs/OPERATIONS.md](../OPERATIONS.md) once the form is
      chosen.
- [x] (confirmed 2026-09-02: impersonated ADC verified live — token mints and a compute read as csis-runner listed the empty project) Confirm the dual-credential story for the first run: AWS
      credentials for the S3 state backend **and** GCP ADC in the same
      environment (per the section-1 backend decision).

## 5. Config tree: replace the placeholders

All of these are fixture values in
[test_folder/cfg/runtime-builders.yml](../../test_folder/cfg/runtime-builders.yml)
(the increment-3 record says real values drop in without code change):

- [x] Replace `projects/my-project/...` subnet identifiers — **done
      2026-09-02**: `projects/csis-sandbox/regions/us-east1/subnetworks/default`;
      `project_id`, `zone`, `session_mechanism: iap` and real tags set.
- [x] Network: the auto-created **`default` VPC** for readiness (this is
      OUR project — the AWS shared-VPC constraint doesn't transfer); a
      dedicated `csis` VPC stays an optional follow-up.
- [x] (proven 2026-09-05/06: gce-test on 1 GB e2-micro kept the guest
      agent and IAP session alive — stage 3, stage 6) Confirm `default_machine_type: e2-micro` stays (it is the
      free-tier type) — but note the AWS lesson (finding: 1 GB t2.micro
      couldn't keep the SSM agent alive): validate that the IAP/guest
      agent path survives on 1 GB, and document the fallback
      (`e2-small`, ~$12/month or spot) rather than silently upsizing.
- [x] (set 2026-09-02; the export attributes images by `csis_series`,
      BILLING_REMINDERS §2c) Set real `tags:` (they become GCE labels via the `gce_label`
      mapping — lowercase, `[a-z0-9_-]`, 63 chars) so **every** GCP
      resource is label-attributable for cost tracking: at minimum
      `project`, `environment`, and the csis lineage labels the bake
      already applies.
- [x] (done 2026-09-05; both legs created and verified live 2026-09-04)
      Add the firewall prerequisite for IAP to the runtime's networking
      notes: an ingress rule allowing tcp:22 from IAP's range
      `35.235.240.0/20` to csis-labeled instances (firewall rules are
      free). PLAN.md gate 5 records that the system generates **no IAM
      changes** — IAP grants (`roles/iap.tunnelResourceAccessor`) are an
      operator prerequisite like the SSM instance profile was; written
      into [docs/OPERATIONS.md](../OPERATIONS.md) ("IAP sessions
      on GCE").
- [x] GCP storage entries defined (2026-09-02): `gce_data` (pd, 30 GB —
      the whole free allotment) and `gce_bucket` (gcs,
      `csis-sandbox-86233086783-default-bucket`); **no filestore entry**;
      plus the `pckr-gce-ans` bake DAG (basic-rhel-8 +
      imgfile-basic-dask on GCE, e2-small for bakes) and the `gce-test`
      instance declaration (free-tier e2-micro).

## 6. Cheapest-resource configuration choices

- [x] (2026-09-07: the runtime's `bake_preemptible: true` makes the build VM
      preemptible; machine type per bake since finding 41) **Packer bakes**: the `googlecompute` source launches a temporary
      build VM per image. Configure the smallest machine type that
      completes the build (`e2-micro`/`e2-small`) and prefer
      **spot/preemptible** for build VMs (60–91% discount; a killed
      build just re-runs). Verify `gcp_packer_source.py` exposes (or
      should expose) machine type and preemptibility.
- [x] (as built: ephemeral external IP for egress only, IAP tunnel for
      SSH since finding 54; no Cloud NAT) **Build-VM networking**: avoid Cloud NAT (an always-on hourly
      charge). For the short life of a bake, an ephemeral external IP on
      the build VM is the cheap path (cents); instances proper launch
      with **no external IP** and are reached via free IAP tunnels.
- [x] (two images on GCE, superseded ones disposed each cycle —
      findings 46, 51) **Keep the image DAG minimal for readiness**: one base image + one
      instance image on the GCE runtime. Each stored custom image bills
      ~$0.05/GB-month on archive size — with two small images this is
      cents, but six images × every re-bake is how it grows. Note that
      the scoped-runs finding (a `--no-dry-run` run re-bakes **every**
      image whose script exists) is a *cost* bug on GCP, not just a
      safety bug — see section 7.
- [x] (pd-standard: 10 GB boot since finding 51, 30 GB `gce-data`)
      **Disks**: standard PD (`pd-standard`), smallest workable sizes;
      the free 30 GB covers the first pd storage. No SSD types.
- [x] (proven live 2026-09-08/09, ledger 67–68: a 30 GB pd archived to
      `csis-scratch-archive`, restored from it with its data intact — same
      file, same checksum on a relaunch — snapshot deleted after the
      restore — minutes of snapshot storage, inside the free allotment;
      archive only disks whose size fits it, the snapshot bills per GB
      while it lives) **Snapshots** (the `archived` storage state =
      snapshot + delete disk): fine — snapshots are cheaper than live
      disks — but verify the small free snapshot allotment before
      archiving anything large.
- [x] (verified 2026-09-07: regional `us-east1`, STANDARD, uniform access,
      versioning off; the bucket is destroyed at the end of every cycle)
      **GCS**: regional class in `us-east1`, under 5 GB, no
      multi-region, no versioning (or a lifecycle rule to purge
      noncurrent versions).
- [x] (allowance verified 2026-09-02 in
      [§3](#3-verify-current-free-tier-terms-and-prices-verified-2026-09-02),
      which concluded "egress discipline stays trivial": the design
      already holds to it — bakes only download, instances carry no
      external IP, and Cloud NAT's $0.045/GiB in both directions is
      avoided. Never measured; a billing-export query filtered to the
      csis labels for a network-egress SKU would confirm it, and that
      belongs to the §10 weekly review.)
      **Egress discipline**: bakes should *download* (free ingress);
      keep anything that pushes data out of GCP under the 100 GB/month
      free North-America egress.  
- [x] (torn down through the gate 2026-09-05 and 2026-09-06; zero
      instances) **Nothing idle**: mirror the stage-1 AWS discipline — tear
      instances down when the readiness evidence is captured; a stopped
      GCE instance still bills its disk (free-tier-covered if ≤ 30 GB
      standard).

## 7. Code gaps to close before a live GCP apply

From the increment-3 "known limits" and the stage-1 findings:

- [x] **`scoped-runs` LANDED 2026-09-02** (feature/scoped-runs):
      `run --only <image>` bake selector, execution-time `apply-check`,
      stale-planfile-proof gate — the cost controls this section wanted.
- [x] **`truthful-recorders` LANDED 2026-09-02**
      (feature/truthful-recorders); `zero-drift-report` landed the same
      day (post-bake retagging), so GCP bakes will carry resolved
      lineage tags from the first run.
- [x] (GCS closed 2026-09-07: looked up through `gcloud storage buckets
      describe`; Filestore stays excluded) **State-query parity for Filestore/GCS is `unavailable`** (no
      client libraries yet). Acceptable for readiness *if* Filestore is
      excluded (section 1); if `gcs` storage is used, either accept the
      `unavailable:` lines (the query makes no claim) or add the GCS
      client to close it. Disk/image/instance queries work via
      `compute.*`.
- [x] Base-image `tests:` — **decided and built 2026-09-03 (finding
      40)**: per-runtime override on the os builder's runtime entry.
- [x] Pins **confirmed per-runtime** on develop: live
      `meta-state/pins.yaml` keys are already
      `imgfile-basic-dask@aws-east2-runtime`-shaped (stage 1 exercised
      them).
- [x] (verified 2026-09-07 on the live Alma bake's emitted provisioners:
      `gcloud` only, no EFS utils / AWS CLI) Confirm per-runtime **prerequisite filtering** holds in the real
      generated output: the GCE bake must not install
      `amazon-efs-utils`/AWS CLI (increment-3 gate 1 — re-check on the
      real config, not just the overlay fixture).
- [x] (foreign detection + sanctioned disposal proven — finding 46
      shape; booted-image comparison added, finding 49) Extend `state query` pre-flight expectations: the first GCP run
      starts from genuinely empty reality; any `foreign` GCE images
      after a failed bake should be disposed of promptly (they bill
      monthly — the AWS orphan-AMI lesson, but with a price tag).

## 8. Free dry-run verification (no GCP account needed, $0)

- [x] `just verify` green on `develop` (2026-09-02, 409 tests; the
      real csis-sandbox values are in the fixture and the stubs derive
      subnet/SG facts from config instead of restating them).
- [x] Gate tests green with the GCE DAG in the real fixture (409
      tests; overlays made idempotent; per-runtime pin refusals and
      capability stamps updated for the wider declaration).
- [x] Real-value validation passes (2026-09-02) — including the live
      GCP network check (the subnet validator now accepts terraform's
      canonical `projects/...` path form).
- [x] `run --all` dry-run completed (2026-09-02): GCE packer blocks
      for base + instance images `packer validate` clean (after a live
      finding: googlecompute needs an explicit `ssh_username`; the
      emitter now falls back to "packer"), and all three GCP tofu roots
      (`gcp-pd`, `gcp-gcs`, `tofu-gce`) `tofu validate` clean with the
      real project/zone/network.
- [x] (done 2026-09-05 before the launch, stage 3.2) Read `generated/final_execution.sh` end to end and price every
      deferred command against sections 3 and 6 **before** any
      `--no-dry-run`.

## 9. First live run (minimal-cost, gated)

Mirror the stage-1 AWS discipline recorded in PLAN.md / docs/LEDGER.md:

- [x] All `apply_*` flags off; flip exactly one lifecycle at a time
      (every live step 2026-09-03 → 09-06 ran that way; since 2026-09-06
      a flag may also list roots/runtimes — stage 7).
- [x] `state query` pre-flight clean before and after each step
      ("no drift" recorded after every live step; stage 3, stage 4, stage 6).
- [x] Identity lifecycle: unchanged (OPA is cloud-agnostic) — the
      2026-09-05 gated identity run made zero OPA writes (stage 5).
- [x] Storage applied 2026-09-03 (three attempts, findings 34–37):
      `gce-data` (30 GB **pd-standard**, READY — the disk_type had to be
      pinned; the builder default pd-balanced bills) and
      `gs://csis-sandbox-86233086783-default-bucket`, both created
      through plan → gate → apply-check → apply, transitions recorded,
      state query clean for both. Cost check: $0. Findings: (34)
      `apply-check` crashed as a non-config-free CLI command — guard
      failed closed, fixed + CLI-level test; (35) GCE resource names
      forbid underscores — pd/filestore/lookup/device paths now
      sanitize via the `gce_name` rule; (36, the big one) the apply
      step executed OTHER lifecycles' leftover runner scripts via bare
      bash — no lifecycle hooks, so it baked two UNRECORDED AMIs
      (ami-00df8ec808cb7576b, ami-0efa14466de7fa459 + 2 snapshots, for
      operator disposal); GOALS.md 5.5 semantics amended: stale scripts of
      unrequested lifecycles are skipped loudly, and
      `generated_lifecycles` resets per run; (37) the storage drift
      comparator now accepts GCE's READY as live. Test copies also
      normalize transient `apply_*` flags (a live TEMP flip had leaked
      into four tests).
- [x] Base-image bake DONE 2026-09-03 (five attempts, findings 38–40):
      `basic-rhel-8-gcloud-east1-20260903-112019`, family
      `basic-rhel-8`, 12 in-bake assertions, lineage-recorded
      (meta-state commit 9e1f10e), post-bake dual-cloud state query
      **no drift**. Cost: ~40 min of e2-small attempts + image storage
      cents (spot for build VMs remains the §6 follow-up). Findings:
      (38) build VMs must run AS the configured service account —
      `service_account_email` on the runtime (packer's default compute
      SA is exactly what least privilege forbids); (39) vendor query
      `rhel-8-*` matched the arm64 line — an ARM disk on an x86 VM
      times out silently; pinned to `rhel-8-v*`; (40) the §7 tests
      choice, decided: in-bake `tests:` are per-runtime overridable on
      the os builder's runtime entry (the AWS nfs-utils assertion
      failed GCE bakes twice — the second time because the first fix
      extended the wrong subconfig class with no emitted-commands test;
      that test exists now).
- [x] Instance-image bake DONE 2026-09-03 (two attempts, finding 41 —
      the bake fell through to the 1 GB runtime default and OOMed;
      e2-medium + the AWS-parity machine-type fallback chain fixed it):
      `imgfile-basic-dask-pckr-gce-ans-20260903-134635`, parent the GCE
      base build, both mods with content hashes, 5 assertions,
      per-runtime parent pin `imgfile-basic-dask@gcloud-east1`
      recorded; dual-cloud state query **no drift**.
- [x] **DONE 2026-09-05** — gce-test launched (e2-micro, no external
      IP) through plan → gate → apply-check → apply, and the **IAP
      session proven end to end by the operator** (`gcloud compute ssh
      --tunnel-through-iap`; the 1 GB machine kept the guest agent
      alive). The two blockers resolved as: (a) firewall rule + IAM
      grant created 2026-09-04; (b) AlmaLinux 10 replaced RHEL (PLAN.md
      "Alma 10 on GCE"), so no license premium. Findings 47–51 in the
      docs/LEDGER.md ledger; note 51: the boot disk inherits the image's
      200 GB, so the launch is ≈ $8/month in pd-standard, not ≈ $0 —
      tear down promptly, and size the bake disk for the workload.
- [x] **DONE 2026-09-05** — evidence captured (state query "no drift"
      with the launched instance recorded; the operator's IAP session
      transcript in the ledger; billing honestly NOT ≈ $0 while the
      instance existed — finding 51's 200 GB boot disk); then the
      instance **torn down through the gated decommission** (findings
      52–53 fixed on the way), storages kept. Post-teardown: zero
      instances, `gce-data` 30 GB (free tier) + image storage only.
- [x] Record findings in [PLAN.md](../../PLAN.md) and the docs/LEDGER.md ledger,
      as stage 1 did — ledger 42–54, PLAN.md sections per stage.

## 10. Ongoing cost hygiene

- [x] Weekly: billing report filtered by the csis labels; anything
      non-zero must map to a known, intended resource — the query and
      acceptance rule are [BILLING_REMINDERS.md §2c](../../BILLING_REMINDERS.md);
      Apple Reminder in place 2026-09-07.
- [x] After every failed bake: check for and delete orphan GCE images /
      disks (`foreign` in state-query terms) — the "orphan sweep" Apple
      Reminder (2026-09-07); disposal through the recorded path only.
- [x] Budget alert emails route to someone who will actually read them —
      delivery proven 2026-09-06, confirmed by the operator 2026-09-07
      (the Google Chat notification is not useful; email is the path).
- [x] ~~Before the trial credit expires (day ~85): re-run the billing
      review and decide what, if anything, is worth keeping past $0.~~
      Moot 2026-09-06: the account has no credits at all (see
      [BILLING_REMINDERS.md §2a](../../BILLING_REMINDERS.md)); spend control is
      the budget plus the weekly review.
