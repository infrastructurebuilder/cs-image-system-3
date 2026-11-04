# 126. The package shape

**Status: OPEN 2026-11-04. A decision stage; waits for "do 126".
Before [§112](STAGE-112.md) and [§116](STAGE-116.md), which it re-scopes.**

Twenty-two PyPI projects pinned to each other at `==` produce a 96-line
`release` recipe, 252 Justfile lines in the release family (58 percent
of the file), six scripts of 754 lines, 37 tags in 48 days, and [§112](STAGE-112.md),
which automates the walk the shape produced (REEXAMINE1 §3.4, §5.5;
REEXAMINE3 §1.5). `dummy-plugin` and `contract-example-plugin` are
installed by every consumer. `tfmodules/` ships as one directory from
one `module_source_base`, copied whole into every starter and the
reference, so a GCP module variable cannot change without the core
repository (REEXAMINE3 flaw 4). The three reviews disagree only on how
far to consolidate.

1. **YOUR DECISION, the one this stage exists for:** the distribution
   shape. The python import paths change in no option; only the
   distributions do.
   - (a) Provider bundles, the default: `cs-image-system-contract`;
     `cs-image-system` (kit, engine, system, hashicorp-utils,
     default-os, ansible, bash-mod, posix-identity, local-state,
     packer); `cs-image-system-aws` (aws-runtime, tf-ebs-instance,
     tf-s3-state); `cs-image-system-gcp` (gcloud-runtime, tf-gcp,
     gcs-state); `cs-image-system-docker` (docker-runtime,
     tf-docker); `cs-image-system-okta` (okta-opa). Six projects.
   - (b) Twenty-two stay; items 2 to 5 alone.
   - (c) One wheel and the contract.
2. `dummy-plugin` and `contract-example-plugin` leave the umbrella's
   and `system`'s dependencies; workspace-only, never published; the
   dry `run --all` tests and the §66 proof install them from the
   workspace.
3. Extras: `[aws]`, `[gcloud]`, `[docker]`, `[okta]`, `[all]`; the
   bare install carries no runtime; `validate` names the missing
   extra (TODO [§116](STAGE-116.md) items 2 to 4, unchanged).
4. The terraform modules live with their plugin: `aws_*` and
   `bootstrap_aws` with aws-runtime; `gce_instance`, `gcp_storage_*`
   and `bootstrap_gcp` with gcloud-runtime; `docker_*` with
   docker-runtime; `okta_opa_module` with okta-opa; the neutral ones
   with the core. A plugin declares its module root; `init-config`
   and the starters materialise the modules of the plugins a tree
   declares; the six copies become one. **YOUR DECISION:** package
   data (the default) or per-plugin module sources fetched by tofu.
5. The starters assembled from one skeleton
   (`docs/examples/_skeleton/` and per-starter overlays), rendered at
   test and publish time; the five committed trees go once the
   rendered trees are byte-identical to them. The published template
   repositories do not change shape.
6. [§112](STAGE-112.md) and [§116](STAGE-116.md) re-scoped on the
   decision. Under (a): [§112](STAGE-112.md) shrinks to its items 3 and
   4; [§116](STAGE-116.md) becomes the external-repository proof with
   docker first (no cloud account, no cost, a cycle that runs on the
   host and in CI), gcloud second into the repository that exists, aws
   last (REEXAMINE1 §5.6).
7. Documents: OPERATIONS (installing), README's package table, the
   CI_SETUP copies, DAILY_DRIVER, PARITY, the release walk.

**Out of scope**: the release recipe's rewrite as a tested script
([§130](STAGE-130.md)); the external repository itself ([§116](STAGE-116.md)).

**Acceptance**: `uv tool install cs-image-system` installs no runtime;
`'cs-image-system[docker]'` runs the docker cycle; the reference on
`[aws,gcloud,docker,okta]` emission byte-identical; the rendered
starters byte-identical to the committed copies before the copies go;
`just test`; one squash, branch kept; a TestPyPI release carries it as
the proof (under (a), five new projects against the index's limit of
about four new projects a day: two days). Records: the squash and the
release; this section goes at "merge 126".
