# 116. A runtime installed from outside

**Status: OPEN 2026-11-03; re-scoped by §126 (2026-11-06);
RE-PLANNED 2026-11-13 against develop at `a2c81f1`. Waits for "do
116", after [§112](STAGE-112.md) (this stage adds a repository to the
release walk) and preferably after [§113](STAGE-113.md) (so the
range a runtime pins on `cs-image-system-base` means the kit from its
first release; the name does not change either way).**

The end the decomposition is for: the umbrella `cs-image-system`
installs without any runtime, a runtime installs beside it from an
index, and one runtime lives in a repository of its own as the proof
(DESIGN §3P: "a separate repository for it once stable, with an
external plugin as the proof").

**What is already done.** The contract carries its own version (§125;
0.4.1 today), with a bump rule in its README and a release probe that
refuses an unbumped change (`scripts/own-versions-current`). The
runtimes are extras of the umbrella, `[aws]`, `[gcloud]`, `[docker]`,
`[okta]` and `[all]` (§126), and a bare install carries none.
`just init`, `just take` and CI's install line read a tree's extras
from its `cfg/` (`just extras`; one skeleton Justfile serves the five
starters). The §30 shims are gone (§125). What remains is the proof:
a runtime's two packages leave this workspace for a repository of
their own, and everything here that assumed every `cs-image-system`
package is a workspace member learns otherwise.

1. Which runtime moves first. §126's re-scope and the re-examination
   say docker first (no cloud account, no cost, a cycle that runs on
   the host and in CI), gcloud second into the repository that
   exists, aws last; this plan's first text defaulted to gcloud (the
   least coupled, already kept out of CI). **YOUR DECISION:** docker
   (the default, by the re-scope), or gcloud.
2. How much moves in this stage. **YOUR DECISION:** the first
   runtime's pair alone (the default: one proof, the smallest step;
   the second and third runtimes are each a later stage that repeats
   a proved walk), or all three in order here.
3. The pins of a package outside the workspace. Inside, every pin is
   `==` the workspace's version, moved by the release's bump. Outside,
   nothing can be: the docker pair pins `cs-image-system-base`,
   `cs-image-system-hashicorp-utils` and `cs-image-system-tofu-roots`
   exactly today, and the contract by range. The pair pins a range of
   each instead, stated in the external repository's README. **YOUR
   DECISION:** the kit, hashicorp-utils and tofu-roots keep moving
   with the workspace (the default; a runtime pins `>=` the release it
   was written against and `<` the next minor), or each carries a
   version of its own, as the contract does, with the same bump
   discipline and release probe.
4. Where the moved runtime's proof lives. Its two packages' own tests
   move with them. But this repository also proves the runtime in
   three other places: the frozen fixture declares it and the golden
   holds its emission (27 of the golden's 148 files name docker; 14
   test files under `tests/` import the docker pair, 26 the gcloud
   pair); `full-test` runs four docker legs (`test-docker-bake`,
   `test-docker-cycle` and the two Podman cycles); and the
   contract-example proof binds a docker root. The re-examination
   asks that every moved package have its own fixture tree, golden
   and tests. **YOUR DECISION:**
   - (b) the runtime leaves the frozen fixture (the default, by the
     re-examination): the golden here shrinks to what stays, in one
     deliberate regeneration; the legs, the fixture tree and a golden
     of its own move to the external repository; this repository
     keeps only the proof that the extra installs and loads (the
     `standard-docker` starter and its live test); or
   - (a) the fixture and the legs stay here and install the external
     pair from the index as a development dependency: nothing moves
     in the golden today, but a release of the pair can then move this
     repository's golden, which couples the two repositories' bars.
5. The release checks learn of a package outside the workspace.
   `scripts/dev-pin-resolves`, the first leg of `full-test`, holds
   every `cs-image-system` package of a resolution to the release's
   version unless the bump excludes its manifest; an outside package
   has no manifest here, so the leg would fail as it did for the
   contract. It reads the packages the umbrella names by range (not
   by `==`) as keeping their own version line, still required to come
   from the index asked. `scripts/publish-dist`,
   `publish-target-ready` and `own-versions-current` count workspace
   members and need nothing. The pin check (`pinned_release`) treats
   any `cs-image-system` distribution installed from a path or from
   git as a development install; that stays right, and the documents
   say that a tree run against an unreleased outside runtime needs
   `--allow-unpinned`.
6. The umbrella's extra. `[docker]` (and its part of `[all]`) names
   the external project by range; the bump's `==` rule no longer
   touches it; `cs_image_system.extras.WORDS` is unchanged. The two
   packages leave the workspace: twenty-two projects become twenty.
7. The repository. Public, with its own Justfile (the five contract
   targets), its own CI and its own release to PyPI and TestPyPI,
   written on the contract and the kit; never a copy of this
   repository's root `pyproject.toml` (the re-examination). Creating
   it, its index tokens and its first release are **USER** steps.
   **YOUR DECISION (the names):** the Google Cloud placeholder that
   exists is `cs-image-system-google-cloud`, where this plan said
   `cs-image-system-gcloud`; the default is that the plan follows the
   repository that exists, and docker's is `cs-image-system-docker`.
   The Azure and Google Cloud placeholders stay empty until a package
   can move whole.
8. The reference and the starters. The reference installs
   `[aws,gcloud,docker,okta]` as today, the moved pair now from its
   own project: its emission byte-identical, its dry run green,
   `perform` on `main` green with nothing baked. The `standard-docker`
   and `complete` starters install it through the extra. GCP is the
   operator's money: when gcloud's turn comes, a move is not a change
   to the GCP code, so no GCE cycle runs for it; if a move touches a
   plugin's logic, that is a finding and the operator decides.
9. The release walk. The external repository releases on its own
   cadence and the umbrella's extra pins a range, so `just release`
   and `just take` learn nothing; `release-watch`
   ([§112](STAGE-112.md) item 10) learns the third repository's run.
10. The documents: DESIGN §3P (the layered picture: contract, kit,
    engine, plugins; the deferred list is empty but for the contract's
    own repository), the README's package table, OPERATIONS (the
    plugin author's page: the external repository as the template,
    the one guide the re-examination asks for), DAILY_DRIVER, the
    skeleton's `CI_SETUP.md`, PARITY.
11. **YOUR DECISION, the last:** the contract's own repository. The
    shims it was tied to are gone and the weekly reminder is retired;
    with a runtime outside, the contract is pinned from outside and
    is stable by the measure of its own version. The default is a
    stage after this one (§117: the contract to its own repository),
    not this stage.

**Out of scope**: any plugin's logic; a GCE cycle; the contract's
repository (item 11's stage); trusted publishing (the tokens stay
until the names are stable, standing decision); the second and third
runtimes, unless item 2 says otherwise.

**Acceptance**: `uv tool install cs-image-system` installs no runtime
and `validate` on a tree declaring one says the extra (true today;
held); `uv tool install 'cs-image-system[docker]'` installs the
external project from PyPI; `scripts/dev-pin-resolves` passes with
the outside pair at its own version, and a test holds that rule both
ways; the reference on `[aws,gcloud,docker,okta]`: emission
byte-identical, dry run green, `perform` green with nothing baked;
the external repository's own CI green on its release tag, with its
own fixture tree and golden under item 4's default; the golden here
moves once, by item 4's regeneration and nothing else; the §66 proof
passes whole on the release that carries this (a starter copy's
`just init` names the release and its extras); the bar and
`just full-test-legs` are green here. Records: the squash message
here and the external repository's first release; this section goes
at "merge 116".
