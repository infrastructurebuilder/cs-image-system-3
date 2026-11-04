# 116. A runtime installed from outside

**Status: OPEN 2026-11-03. Waits for "do 116", after [§115](STAGE-115.md) and
preferably after [§112](STAGE-112.md) (the release walk; this stage adds a repository
to it). Kept apart from [§115](STAGE-115.md): it changes what a release ships, the
starters, the reference's install line and the release walk, and
makes a repository; [§115](STAGE-115.md) changes none of those.**

The end the four stages are for: the umbrella `cs-image-system`
installs without any runtime, a runtime installs beside it from an
index, and one runtime lives in a repository of its own as the proof
(DESIGN §3P: "a separate repository for it once stable, with an
external plugin as the proof"). Today [pyproject.toml](../pyproject.toml)
pins all twenty-one packages into the umbrella with `==`, and that pin
list is the only place "built-in" means anything: the loader is
entry-point driven and names no plugin.

1. The contract's compatibility version (the other deferred item of
   DESIGN §3P). An external plugin cannot pin `==` to a workspace it is
   not in; it pins a range of the contract and of the kit. The contract
   and the kit each carry a version that moves only when their surface
   moves (the contract's `assert_conforms` set and the kit's base
   classes), stated in their READMEs; the umbrella keeps `==` for what
   it ships. **YOUR DECISION:** the kit's version moves with the
   workspace (the default; a runtime pins `>=` the release it was
   written against and `<` the next minor) or carries its own.
2. The umbrella's dependencies: the engine, the kit, the contract,
   `system`, hashicorp-utils, and every non-runtime plugin (the OS,
   the modifications, the identity plugins, the state backends) stay
   in it; the three runtime pairs (aws + tf-ebs-instance, gcloud +
   tf-gcp, docker + tf-docker) become extras `[aws]`, `[gcloud]`,
   `[docker]` and `[all]`. `validate` names a declared runtime `type:`
   with no plugin installed and says the extra; the bootstrap's
   section discovery and `init-config` read what is installed, as the
   loader does. **YOUR DECISION:** which plugins stay in the bare
   umbrella (the default above: everything that is not a runtime).
3. The starters: each tree's `just init` and `just take` install the
   umbrella with the extras its `cfg/` declares (the runtime `type:`
   values map to extras; `complete` declares all three), and CI's
   install line does the same; `init-config` writes the line. The five
   Justfiles stay byte-identical (the extras are read, not written in).
4. The proof: `gcloud-runtime-plugin` and `tf-gcp-plugin` move to a
   repository of their own (`cs-image-system-gcloud`, public, with its
   own Justfile on the contract, its own CI and its own release to
   PyPI under the range pins of item 1); the umbrella's `[gcloud]`
   extra names its PyPI project; the two packages leave this
   workspace. The reference installs `[aws,gcloud,docker]` and its
   emission is byte-identical, its dry run green, `perform` on `main`
   green with nothing baked. GCP is the operator's money: a move is
   not a change to the GCP code, so no GCE cycle runs for this stage;
   if the move touches the plugin's logic, that is a finding and the
   operator decides. **YOUR DECISION:** gcloud as the proof (the
   default: the least-coupled runtime, already kept out of CI), or
   docker (no cloud at all, but the newest code).
5. The release walk: the external repository releases on its own
   cadence and the umbrella's extra pins a range, so `just release`
   and `just take` learn nothing; `release-watch` ([§112](STAGE-112.md)) learns the
   third repository's run. The [§112](STAGE-112.md) estimates stay.
6. The documents: DESIGN §3P (the layered picture: contract, kit,
   engine, plugins; the deferred list is empty), the README's package
   table, OPERATIONS (installing with extras; the plugin author's
   page: a runtime's repository from the proof as the template),
   DAILY_DRIVER, the five CI_SETUP copies, PARITY.
7. **YOUR DECISION, the last:** the §30 standing decision says the
   shims go together with the contract's own repository. With a
   runtime outside, the contract is pinned from outside and is stable
   by the measure of item 1; this is where that decision comes due.
   The default is a stage after this one (§117: the contract to its
   own repository, the shims removed, the weekly reminder retired),
   not this stage.

**Out of scope**: any plugin's logic; a GCE cycle; the shims and the
contract's repository (item 7's stage); trusted publishing (the
tokens stay until the names are stable, standing decision).

**Acceptance**: `uv tool install cs-image-system` installs no runtime
and `validate` on a tree declaring one says the extra; `uv tool
install 'cs-image-system[gcloud]'` installs the external project from
PyPI; the reference on `[aws,gcloud,docker]`: emission byte-identical,
dry run green, `perform` green with nothing baked; the external
repository's own CI green on its release tag; the §66 proof passes
whole on the release that carries this (a starter copy's `just init`
names the release and its extras). Records: the squash message here
and the external repository's first release; this section goes at
"merge 116".
