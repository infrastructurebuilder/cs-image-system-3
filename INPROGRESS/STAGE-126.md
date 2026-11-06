# 126. The package shape

**Status: OPEN 2026-11-04; RE-EVALUATED 2026-11-05 after §125;
DECIDED in part 2026-11-05: the shape is (b), the twenty-two projects
stay, so the stage is items 2 to 7. Item 4's second decision (package
data or fetched sources) is still open and is asked at "do 126".
Before [§112](STAGE-112.md) and [§116](STAGE-116.md), which it
re-scopes.**

**Re-evaluated 2026-11-05.** The stage stands as written, with these
facts moved under it. The workspace is 22 projects (tofu-roots joined
at §123 and is the one unreleased new project; PyPI takes about four
new projects a day). The contract already carries its own version
(0.1.0, §125; dependents pin `>=0.1,<0.2`), so under (a) the bundles
pin that range and nothing of item 1 waits on a version. Under (a)
the index sees four new projects (aws, gcp, docker, okta): one day's
quota exactly, and tofu-roots and hashicorp-utils fold into the core
bundle and never need a project of their own, so the acceptance's
"two days" becomes one. §125's `tests/test_plugin_imports.py` is the
tool that keeps a bundle's boundary honest: under (a) it gains the
bundle rule (a bundle's members import the contract, the core and
each other, never another bundle; `tf_gcp -> gcloud_runtime` and the
two other cross-plugin edges the closure test counts become
in-bundle edges). Item 4 (the modules with their plugin) is the one
item that moves YAML-facing material (`module_source_base`); its
proof stays the reference's `config-drift`.

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
   Whichever is chosen, an override is first-class (the operator's
   ask, 2026-11-05: "if I want to use a different module, how would I
   do that?"): today the one knob is `config: module_source_base`,
   which moves every module at once, and a module edited in the
   tree's copy is overwritten by the next `init-config --force`. So:
   (i) `config: module_sources`, a map from a module's directory name
   to a path or URL (`module_sources: {aws_instance: ../my-modules/
   aws_instance}`); a named entry wins over the base for that module
   alone, the resolver (`utils.module_source`) already takes a path or
   a remote source, and the emission moves only for the overridden
   module; CONFIGURATION documents the key beside `module_source_base`.
   (ii) Every materialised copy carries a stamp (`.csis-module`: the
   plugin, the release, the content hash), so `init-config` refreshes
   only unmodified copies and refuses to overwrite a changed one,
   naming it and the override that would keep the change; a tree that
   wants the plugin's version back deletes the copy. (iii) A test per
   rule: an override resolves for one module and the base for the
   rest; a changed copy survives a refresh and is named.
5. The starters assembled from one skeleton
   (`docs/examples/_skeleton/` and per-starter overlays), rendered at
   test and publish time; the five committed trees go once the
   rendered trees are byte-identical to them. The published template
   repositories do not change shape.
6. [§112](STAGE-112.md) and [§116](STAGE-116.md) re-scoped on the
   decision. Under (b), decided: [§112](STAGE-112.md) stays whole (the
   release walk keeps its twenty-two projects, so its boxes are the
   recipes' to shrink); [§116](STAGE-116.md) becomes the
   external-repository proof with docker first (no cloud account, no
   cost, a cycle that runs on the host and in CI), gcloud second into
   the repository that exists, aws last (REEXAMINE1 §5.6), and item 3's
   extras are what the proof installs.
7. Documents: OPERATIONS (installing), README's package table, the
   CI_SETUP copies, DAILY_DRIVER, PARITY, the release walk.

**Out of scope**: the release recipe's rewrite as a tested script
([§130](STAGE-130.md)); the external repository itself ([§116](STAGE-116.md)).

**Acceptance**: `uv tool install cs-image-system` installs no runtime;
`'cs-image-system[docker]'` runs the docker cycle; the reference on
`[aws,gcloud,docker,okta]` emission byte-identical; the rendered
starters byte-identical to the committed copies before the copies go;
`just test`; one squash, branch kept; a TestPyPI release carries it as
the proof (under (b) no new project: one release, the operator's box).
Records: the squash and the release; this section goes at "merge 126".
