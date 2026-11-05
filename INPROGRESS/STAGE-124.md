# 124. The run context and the engine part ways

**Status: OPEN 2026-11-04. Waits for "do 124", after §123. [§113](STAGE-113.md) is
re-planned on this stage's numbers.**

`GlobalTypeContext` is 1,587 lines, 68 methods (49 properties),
thirteen public mutable attributes, and is at once the config loader
(a 331-line function), the run state, the scoping flags, the
finalization queue and executor, and the runner-script writer. It is
fetched with no argument 46 times in `base` and at 61 `_get_context()`
sites in the plugins, through a `@singleton` that replaces the class
with a factory typed as the class and defaults nine required
constructor arguments to `None` so the no-arg call type-checks
(REEXAMINE1 §3.3; REEXAMINE3 §1.2). 160 function-local imports close
one strongly connected component of 42 modules. [§113](STAGE-113.md)'s closure,
recomputed with those edges, is 95 modules, not 70, and five closure
members import twelve engine modules (REEXAMINE1 §5.2). [§114](STAGE-114.md)'s
protocol will be small only if the context stops being the loader
first.

1. The split: `RunContext` (read-only: the collections, the paths,
   the run id and start time, the scoping flags, a `services` handle)
   and, engine-side in their own modules, `ConfigLoader`
   (`read_config_and_transform` and its helpers,
   `process_and_register_builders`) and `Finalizer` (the queue,
   `final_execute`, the runner-script writer). The loader returns a
   context; nothing on the context loads or executes.
2. The context is passed: `BuilderBase.bind(ctx)` at registration
   (DESIGN's phrase); `_get_context()` returns the bound one and is a
   one-release shim; the 46 no-arg fetches in `base` go; the
   `@singleton` on the context goes. **YOUR DECISION:** `Registry` and
   the two collectors lose the singleton in the same stage (the
   default, if the suite's reset pattern allows) or in [§127](STAGE-127.md).
3. The lazy-import web: each of the 160 function-local imports
   becomes a top-level import where no cycle results, a parameter, or
   a hook; the SCC size is the measure, reported before and after.
4. The closure script (TODO [§113](STAGE-113.md) item 1's) is written here: top-level
   and lazy edges counted separately; the kit and engine closures;
   cross-plugin edges by family; the SCC. It runs as a test with the
   committed numbers as a floor that may only fall.
5. [§113](STAGE-113.md) is re-planned on item 4's numbers. The
   expectation: the engine side grows (loader, finalizer, orchestrator,
   template_utils, the meta-state writers) and the kit shrinks toward
   `basic/*`, `models/*` and the vocabulary; the engine package decision
   in [§113](STAGE-113.md) item 1 stands; the re-export shims
   [§113](STAGE-113.md) proposes must not import the engine from the kit
   (REEXAMINE3 flaw 2), so the old paths either move with their module
   or are dropped.
6. Documents: DESIGN §3P (the context is read-only; loading is the
   engine's), base/README's context section, PLUGINS.md.

**Out of scope**: the protocol in the contract ([§125](STAGE-125.md) types what this
stage builds); the loader's passes ([§127](STAGE-127.md)).

**Acceptance**: emission byte-identical; no `GlobalTypeContext()`
call outside the shim; the closure test green with its floor; `just
test`; one squash, branch kept. Records: the squash with the numbers;
this section goes at "merge 124".
