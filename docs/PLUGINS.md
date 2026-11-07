# The packages

The uv workspace is twenty-two packages under `packages/`, twenty of
them published. Each has its own
README that describes it on its own terms: what it registers, its models
and how they extend the base models, its builder's hooks, what it emits,
and one example configuration. The core and the CLI are packages too.

The workspace root is the umbrella, `cs-image-system`: no sources of its
own, a `==` pin on the core -- the CLI, the engine, the libraries and
every plugin that needs no provider account -- and an extra per provider
(`[aws]`, `[gcloud]`, `[docker]`, `[okta]`, `[all]`), so
`uv pip install cs-image-system==<version>` carries no runtime and
`'cs-image-system[aws]==<version>'` adds one (see "Installing a release"
in [OPERATIONS.md](OPERATIONS.md); the table from a `type:` word to its
extra is `cs_image_system.extras`, the umbrella's one module). The dummy plugin and the
contract example plugin are workspace-only: classified `Private :: Do
Not Upload`, installed through the root's `dev` group, never on the
index. Every package declares exactly the
third-party distributions its sources import and pins its siblings at its
own version; `tests/test_package_metadata.py` holds it to that.

## The core

| Package | What it is |
| --- | --- |
| [contract](../packages/contract/README.md) | The plugin contract: the protocols a model and a builder satisfy, the constants and field helpers a model is declared with, the lifecycle phases a hook keys on, the data carriers a hook returns. Depends on nothing of the system; `base` depends on it. A plugin is written against this package. |
| [base](../packages/base/README.md) | The core: the base models and builder bases that implement the contract, the registry and the plugin loader (one registry per run, made by the loader), the lifecycles and phases, the run context (made by the loader and bound to every builder; nothing on it loads or executes), meta-state, encryption, the public-safe gate, lineage, releases, retention, launch parameters. Every built-in plugin depends on it; an external one need not. |
| [system](../packages/system/README.md) | The CLI host: the `cs-image-system` command and every subcommand. |
| [hashicorp-utils](../packages/hashicorp-utils/README.md) | A library, not a plugin, on the contract alone: the terraform and packer collectors (providers, plugins, backends, sensitive values by reference; one instance per run, reached through the run context, never a process singleton), HCL rendering. It imports nothing of the core. Nine packages use it. |
| [tofu-roots](../packages/tofu-roots/README.md) | A library, not a plugin: the terraform roots every OpenTofu root plugin subclasses -- the root mixin (init, the gated plan → gate → apply sequence), the provider-neutral instance and storage roots (`TofuInstanceBuilderBase`, `TofuStorageBuilderBase`, their models and the `tofu` version checker) and the run hooks that check and record state locations for the core, which knows no terraform. |

## The plugins

Discovered through Python entry points (`cs_image_system.plugins.*`); each
registers model and builder classes under the classifications it claims.

| Package | Kind | `type:` keys it answers to |
| --- | --- | --- |
| [aws-runtime-plugin](../packages/aws-runtime-plugin/README.md) | runtime | `aws` |
| [gcloud-runtime-plugin](../packages/gcloud-runtime-plugin/README.md) | runtime | `gcloud` |
| [docker-runtime-plugin](../packages/docker-runtime-plugin/README.md) | runtime | `docker` (a durable host's container daemon, reached through the Docker Engine API) |
| [tf-docker-plugin](../packages/tf-docker-plugin/README.md) | instance and storage builders | `tofu-docker` (containers through OpenTofu's `kreuzwerker/docker` provider) and `tf-docker-volume` (named volumes); a subclass of tofu-roots' neutral roots, with no dependency on the AWS root |
| [default-os-plugin](../packages/default-os-plugin/README.md) | OS families | the family names an OS builder declares |
| [packer-plugin](../packages/packer-plugin/README.md) | image builders | the one `packer` image builder, for every runtime (the older keys `packer-ebs`, `packer-gce` and `packer-docker` still load for one release) |
| [ansible-plugin](../packages/ansible-plugin/README.md) | modifications | `ansible` (playbooks) |
| [bash-mod-plugin](../packages/bash-mod-plugin/README.md) | modifications | `bash-remote` (script, scripts, ensure) |
| [okta-opa-plugin](../packages/okta-opa-plugin/README.md) | groups and users | the OPA group builder, the managed and read-only user builders |
| [posix-identity-plugin](../packages/posix-identity-plugin/README.md) | groups and users | `posix` (a group and a user builder: POSIX accounts with declared ids) |
| [tf-ebs-instance-plugin](../packages/tf-ebs-instance-plugin/README.md) | instances and storages | the AWS terraform roots: `tofu` (instances) and `tf-aws-ebs`, `tf-aws-efs`, `tf-aws-s3` (storages); a subclass of tofu-roots' neutral roots with the `aws` provider |
| [tf-gcp-plugin](../packages/tf-gcp-plugin/README.md) | instances and storages | the GCE terraform roots: `tofu-gce` (instances) and `tf-gcp-pd`, `tf-gcp-filestore`, `tf-gcp-gcs` (storages); a subclass of tofu-roots' neutral roots with the `google` provider, with no dependency on the AWS root |
| [tf-s3-state-plugin](../packages/tf-s3-state-plugin/README.md) | state backends | `s3` |
| [contract-example-plugin](../packages/contract-example-plugin/README.md) | state backends | `inmem` (OpenTofu's in-memory state; the proof of the contract: written against the contract alone, never a backend for a real tree) |
| [local-state-plugin](../packages/local-state-plugin/README.md) | state backends | `local` (a state file on disk) |
| [gcs-state-plugin](../packages/gcs-state-plugin/README.md) | state backends | `gcs` (a Google Cloud Storage bucket; declared in the fixture, bound to nothing) |
| [dummy-plugin](../packages/dummy-plugin/README.md) | extension template and test double | see its README |

The exact keys, aliases and classifications are in each README's "What it
registers" section, which is written from the package's `pyproject.toml`
and its `main.py`. The field-by-field reference for the YAML each plugin
reads is [CONFIGURATION.md](CONFIGURATION.md).

Every plugin registers under a **namespace**, and every class it registers
is keyed by its classification, that namespace and its canonical name. A
plugin names its namespace with `PluginMetadata(namespace="...")`, or
inherits it from its distribution: the distribution name with the
`cs-image-system-` prefix and the `-plugin` suffix dropped, so the
packages above register as `aws-runtime`, `gcloud-runtime`,
`docker-runtime`, `tf-docker`, `default-os`, `packer`, `ansible`,
`bash-mod`, `okta-opa`, `posix-identity`, `tf-ebs-instance`, `tf-gcp`,
`tf-s3-state`, `contract-example`, `local-state`, `gcs-state` and
`dummy`, and the core's own registrations as `base`. Two plugins may
therefore answer to one `type:` word: a tree writes the bare word while
one class answers to it, and the qualified form `<namespace>/<name>`
(`tf-ebs-instance/tofu`) when different classes do, which `validate`
says in one line. A plugin whose entry point has no distribution behind
it must name the namespace or is refused at discovery with the field
named. The reasoning is in [the stage index](CHANGES.md#s131); the
registry's tables and the resolution rule are in
[base's README](../packages/base/README.md#the-registry).

The three terraform root plugins (`tf-ebs-instance-plugin`,
`tf-gcp-plugin`, `tf-docker-plugin`) share one implementation of the
root: the provider-neutral bases in
[tofu-roots](../packages/tofu-roots/README.md#the-terraform-roots)
own the workspace, the variables, the state binding, the module calls,
the gated runner lines, the finalization hooks and the state query, and
each plugin subclasses them and answers the hooks with its provider,
its modules and its module arguments. No root plugin depends on another
provider's root plugin: `tf-gcp-plugin` and `tf-docker-plugin` do not
depend on `tf-ebs-instance-plugin`, so installing either installs
neither the AWS root nor `aws-runtime-plugin` nor `boto3`. The change is
recorded in the stage index under
[a provider-neutral terraform root](CHANGES.md#s120).

### What a runtime provides

A runtime plugin registers a runtime builder class under its `type:` key
(the contract's `RuntimeBuilderProtocol`, with defaults on the core's
`RuntimeBuilderBase`). Besides the instance hooks a tree's declarations
exercise, six things are asked of the CLASS itself, before or without a
tree, so that the core can name no runtime and still carry the release's
knowledge of each. Every one has a default that answers nothing, so a
runtime declares only what it has.

- `image_source_entries()`: the runtime's part of the release-owned
  image-source catalog (CONFIGURATION 5a), the blocks keyed by its own
  type, read from the plugin's package data (`data/image-sources.yml`
  beside its code). The core merges what every installed runtime answers,
  by family; a runtime that ships none answers an empty list.
- `local_test_target()`: a factory `factory(image, executables)` for the
  throwaway target the local modification tests run on, or `None` for a
  runtime that offers none. The core takes the factory of the first
  registered runtime, by name, that offers one, reads the tests' stand-in
  block from the catalog under that runtime's type, and hands the factory
  the tree's executables so the plugin can find its CLI. The docker
  runtime plugin is the one that offers a target today.
- `session_status(settings, executables)`: the session the runtime will
  use, read from its caches and never a credential value: a
  `SessionStatus` saying what was read, a fixed expiry when one is
  readable, whether the credential renews itself, the command that renews
  it, or that nothing was found. `settings` is the entry as written (or
  the model's fields), so `preflight` can ask before a tree loads. A
  runtime that needs no session answers `None` and prints nothing. A
  state-backend builder class answers the same question (the `s3` and
  `gcs` backends reach their cloud's reading through the registry by its
  type key, without importing the runtime's package).
- `credential_environment_prefixes()`: the prefixes of the environment
  variables its tools read credentials from; `preflight` adds them to its
  check for a variable that is set and empty, reported by name.
- `network_facts()` and `adopt_network_facts(facts)` (both optional; the
  core reaches them through `getattr`, so a runtime that has neither is
  neither asked nor judged): a loaded configuration never reaches a
  cloud, so the check of a runtime's networking declaration against its
  account is split in two. `network_facts()` is the ONLINE half, called
  by every real run and by `validate --online` on the builder instance:
  it checks the declaration (a `default` network resolves to the
  account's default; every declared subnet must be in it; on AWS every
  declared security group must exist) and answers the facts the
  declaration resolved to -- `network`, the declared `subnets` (and
  `security_groups`) it checked, `checked_at` -- which the core records
  under the runtime's name in `meta-state/runtime-facts.yaml`. Small and
  public-safe: the ids the tree already declares, never the account's
  inventory. A failure (lapsed credentials) propagates and is classified
  through `classify_failure` into the same one line a load-time failure
  gets. `adopt_network_facts(facts)` is the OFFLINE half, called by every
  load with the runtime's recorded entry (`{}` when none): it takes the
  recorded network into the model when the declaration says `default`
  and answers the problems the record leaves -- nothing recorded, a
  declared id the record never checked, a concrete network that differs
  from the recorded one -- which a validator reports, each naming
  `validate --online`. The helpers `facts_of` and `coverage_problems` in
  `cs_image_system.base.network_facts` build both answers; the cloud
  runtime plugins use them.
- `classify_failure(exc)`: the one-line form of a load-time failure that
  is this plugin's to explain (lapsed credentials, an unreachable daemon,
  a missing key pair), as a `LoadFailureReport` with its exit code. This
  one is every builder's, not only a runtime's: the OPA group builder
  names its missing key pair. The core asks every registered builder
  class about every exception in a failure's cause chain and prints the
  first answer.
- `secret_patterns()`: the shapes of the runtime's own secrets that must
  never reach a public repository, as named regular expressions (an
  access key id's prefix and length, a service-account key id). The
  public-safety scan adds them to the rules it carries itself (tokens,
  PEM bodies, an age identity, a literal `TF_VAR_*=` value).

### What a plugin may import

A plugin is written against `cs-image-system-contract`, and from the core
it imports three things only: the base classes under
`cs_image_system.base.basic` (the convenient way to satisfy a protocol),
the models under `cs_image_system.base.models` (what it subclasses or
attaches to) and the two metadata abstractions. Everything else it needs
of a run it reads from the context it is handed at `bind(ctx)`, typed as
the contract's `RunContextProtocol`: the collections and paths, the
meta-state, and the services under `ctx.services`, each a protocol sized
by what plugins use (`lineage`, `launch`, `secrets`, `files`, `commands`,
`images`, `identity`, `storage`, `workspaces`, `scope`, `cli`,
`lifecycles`, `meta_state`). The words a plugin reads and writes (tag
names, the enrollment variable, the mount mark, storage states, gid
policies, power states, the secret marker type) are the contract's
vocabulary modules; the hooks entry point and the bootstrap facts protocol
are the contract's too. `tests/test_plugin_imports.py` holds the rule over
every installed plugin and carries the exception list, four entries today,
each with its reason beside it (a model method with no context of its own;
a state backend's session check that runs before any run exists). The
contract's protocols hold what a plugin calls on the core's objects and
what the core calls on a plugin's, nothing mirrored from the base classes
for its own sake; a plugin that falls short of its kind's protocol is
refused when the plugins are discovered, by name and by member.

### What a plugin adds to the command line

The console script `cs-image-system` owns the root command and its
built-in sub-apps (`run`, `verify`, `state`, ...). A plugin whose work
needs a command of its own -- a token only its client can mint, a login
proof only its client can drive -- registers one entry point in the group
`cs_image_system.commands`. The entry point is a callable that returns a
list of the contract's `CommandMount` records
([`contract/commands.py`](../packages/contract/src/cs_image_system/contract/commands.py));
the console script reads every installed entry point when it starts and
mounts each record, so the command appears exactly when the plugin is
installed and is absent otherwise (`cs-image-system --help` lists what is
there). A mount is one of two things:

- a **sub-app**: `CommandMount(name="workload", app=<a typer.Typer>)`
  adds the whole sub-app under the root. With `deferred_load=True` the
  sub-app's commands decide for themselves whether the configuration tree
  loads: they find a `deferred_load` callable in the typer context's
  `obj` and call it when they need the tree (the okta-opa plugin's
  `workload token` takes its names from the environment, because the probe
  workflow runs on a checkout with no configuration, and loads only when a
  name is missing);
- a **command under an existing sub-app**: `CommandMount(name="login",
  path=("verify",), callback=<a function>)` adds `cs-image-system verify
  login`; the callback's signature and docstring make its options and help
  the way any typer command's do, and it loads the tree the way the
  enclosing sub-app does.

The shared-command rule: two plugins may mount the *same* callback (the
same function object) or the same sub-app object under the same name and
path, and the script mounts it once -- `verify login` is one callback in
the core (`cs_image_system.base.commands.login_proof.verify_login_command`)
that every identity plugin mounts, so the proof is there whichever
identity plugin a tree installs. A *different* callback or sub-app under a
name a built-in command or an earlier mount already took is refused when
the script starts: two owners of one command is a packaging error, never a
silent replacement. The examples: the okta-opa plugin's
[`cli.py`](../packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/cli.py)
mounts the `workload` sub-app (`describe`, `token`, `probe`) and `verify
login`; the posix-identity plugin's
[`cli.py`](../packages/posix-identity-plugin/src/cs_image_system/posix_identity_plugin/cli.py)
mounts `verify login`.

## The README contract

Every package README ends with the same four sections, in this order, so
a reader finds the same thing in the same place in every package; only a
`## Related` section may follow them.
[tests/test_docs_contract.py](../tests/test_docs_contract.py) holds
every README to the contract and checks that every relative link in the
READMEs, in this file, in the root README, in the starter trees'
CI setup guide and in [DAILY_DRIVER.md](DAILY_DRIVER.md) resolves.

| Section | Answers |
| --- | --- |
| `## Prerequisites and integration` | what must exist outside the system before the plugin works (accounts, roles, APIs, tools, credentials, network), and how the plugin finds it -- which field or variable; "nothing" is an answer |
| `## Configuration reference` | every field the plugin reads, with type, default and meaning, in tables; fields accepted but not read, named as such; then the variations: what the plugin does differently by declaration (ephemeral or durable, pinned or follow, ensure or script, encrypted or clear, one runtime or another, dry or real) |
| `## What it tests and verifies` | what the plugin checks, when (at load, validate, generation, apply, after apply, in the state query), and where the verdict lands; "nothing" is an answer |
| `## When it fails` | the failures the plugin produces, what each means, where to look, what to do; failures that have actually happened first, with their dates |

The sections are written from the package's models, builders, tests and
`pyproject.toml` and from the two manuals, never from memory; where a
README and the code disagree, the code wins and the README is corrected.
Where the choice is between a little more explanation and a little less,
the README errs on the side of more.
