# 125. The contract's surface, its services and its version

**Status: OPEN 2026-11-04. Waits for "do 125", after [§124](STAGE-124.md). Absorbs
[§114](STAGE-114.md) and [§115](STAGE-115.md); the commitment to the contract in substance.**

The contract holds 31 protocols; the runtime's has 49 methods and the
group's 41, the core's base classes mirrored rather than a contract a
third party would sign (REEXAMINE1 §5.4). [§115](STAGE-115.md) would hang lineage,
launch, secrets, files and commands on the context, the god object
acquiring an API. [§116](STAGE-116.md) item 1's compatibility version would freeze a
surface about to shrink. Beside the protocols, 356 `hasattr`/`getattr`
calls decide dispatch, a second type system a plugin author must also
satisfy. No test says what a plugin may import.

1. The import test first: each plugin imports only `contract`,
   `basic/*`, `models/*`, the two metadata abstractions and
   hashicorp-utils; today's exceptions are committed as a list and
   the stage ends when the list is empty (replaces [§115](STAGE-115.md) item 3).
2. Service protocols: lineage, launch, secrets, files, commands and
   meta-state (the four members [§114](STAGE-114.md) counted), each the size of what
   plugins use, counted at "do 125"; reachable as `ctx.services`; a
   plugin's test stubs one service, not the world. [§115](STAGE-115.md)'s four
   helpers become members of the service they belong to.
3. `RunContextProtocol` ([§114](STAGE-114.md) item 1) typed over
   [§124](STAGE-124.md)'s `RunContext`; `bind(ctx)` takes the protocol;
   no plugin and not hashicorp-utils names a kit class for the context
   ([§114](STAGE-114.md) item 4's test).
4. The surface review: a protocol method stays only if a plugin
   outside the core calls or implements it; the rest become kit
   base-class methods; counts before and after in the squash. The
   `hasattr`/`getattr` dispatch in `orchestrator`, `registry` and the
   context becomes the protocol check (`assert_conforms` at
   registration).
5. The contract's own version: `cs-image-system-contract` takes a
   semantic version independent of the workspace; the kit and the
   plugins pin a range. **YOUR DECISION:** 1.0.0 at the release that
   carries this (the default) or 0.x until an external consumer
   exists.
6. The §30 shims. **YOUR DECISION:** this stage is the commitment (TODO
   [§114](STAGE-114.md)'s own words) and the shims go here, the weekly
   reminder retires and DESIGN §3P's undo paragraph goes (the default,
   since [§114](STAGE-114.md) and [§115](STAGE-115.md) are absorbed and
   44 files in `base` already import the contract directly); or they
   wait for §117 as TODO.md says.
7. Documents: PLUGINS.md and one plugin author's page that assumes no
   access to this repository (REEXAMINE2's ask), DESIGN §3P, the
   contract README, contract-example-plugin README.

**Out of scope**: moving the contract to its own repository (§117).

**Acceptance**: emission byte-identical; the import test's list
empty; contract-example-plugin's builder reads the context and one
service through the protocols alone, in the dry `run --all` it already
runs in; `just test`; one squash, branch kept. Records: the squash;
this section and TODO.md's [§114](STAGE-114.md) and [§115](STAGE-115.md) go at "merge 125".
