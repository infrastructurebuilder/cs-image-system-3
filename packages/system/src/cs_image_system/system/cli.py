# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""cs-image-system command line interface.

V2 (DESIGN §3A/§3C/§3G): the primary entry point is ``run``, which drives any
subset of the four lifecycles -- identity, storage, base-image,
instance-image -- in declared order, headlessly. The V1 commands remain as
aliases onto the same runner.
"""
import json
import logging
import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.logging import RichHandler

from cs_image_system.base.lifecycles import Lifecycle, all_lifecycles, parse_lifecycles
from cs_image_system.base.loader import load_plugins
from cs_image_system.base.utils import is_base

DEFAULT_CONFIG_FILE = "./image-actions.yml"


def setup_rich_logging(verbose: bool = False):
    # Logs go to STDERR: stdout is reserved for machine-readable output (the
    # run summary JSON, and the gid shim's JSON that terraform's external
    # provider parses -- a single stray log line there breaks the plan).
    from rich.console import Console
    logging.basicConfig(
        level="DEBUG" if verbose else "INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=Console(stderr=True))],
        force=True,
    )
    logging.getLogger('boto3').setLevel(logging.INFO)
    logging.getLogger('botocore').setLevel(logging.INFO)
    logging.getLogger('urllib3').setLevel(logging.INFO)  # boto3 uses urllib3 under the hood


log = logging.getLogger("rich")

app = typer.Typer(help="CLI for managing cloud sandbox image actions.",
                  context_settings={"help_option_names": ["-h", "--help"]})


def _run(lifecycles, apply: bool, commit: bool, state_query: bool = True,
         only: list[str] | None = None, force_bake: list[str] | None = None) -> None:
    """Run lifecycles; nonzero exit on any failure (DESIGN §3G)."""
    from cs_image_system.base.commands.run_lifecycles import run_lifecycles
    summary = run_lifecycles(lifecycles, apply=apply, commit=commit, state_query=state_query,
                             only=only, force_bake=force_bake)
    typer.echo(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    if not summary.ok:
        typer.secho(f"Run {summary.run_id} FAILED: {summary.error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho(f"Run {summary.run_id} completed: {', '.join(summary.requested) or 'nothing requested'}",
                fg=typer.colors.GREEN)


@app.command(name="run")
def run_command(
    ctx: typer.Context,
    lifecycles: Annotated[list[str] | None, typer.Argument(
        help="Lifecycles to run, any subset of: identity storage base-image instance-image "
             "(always executed in that order), or 'all'.")] = None,
    all_: Annotated[bool, typer.Option("--all", help="Run every lifecycle.")] = False,
    apply: Annotated[bool, typer.Option("--apply/--no-apply",
        help="After generation, execute the lifecycle runner scripts that exist "
             "(enumerated only under --dry-run, the default).")] = True,
    commit: Annotated[bool, typer.Option("--commit/--no-commit",
        help="Make the meta-state commit (read-models, pins, lineage, generated IaC) "
             "in the configuration repository after the run.")] = False,
    state_query: Annotated[bool, typer.Option("--state-query/--no-state-query",
        help="First ask reality (read-only: cloud images/storages, identity provider) and "
             "refuse to run on hard drift; --no-state-query keeps the existing report.")] = True,
    only: Annotated[list[str] | None, typer.Option("--only",
        help="Restrict the BAKE surface to the named image(s) (repeatable): sources, "
             "build blocks and bake runner scripts exist for nothing else. Terraform "
             "roots are untouched -- instances stay declarative. Unknown names fail. "
             "'--only none' bakes nothing: the terraform roots alone.")] = None,
    only_runtime: Annotated[str | None, typer.Option("--only-runtime",
        help="Restrict the run to this runtime: the BAKE surface becomes every image baked "
             "on it (the configuration-driven form of --only <image>@<runtime> ...) AND only "
             "its terraform roots (storage, instance) are generated and planned -- the roots "
             "of every other runtime emit nothing. Implied by --apply-runtime unless --only "
             "is given.")] = None,
    apply_runtime: Annotated[str | None, typer.Option("--apply-runtime",
        help="Let the storage and instance roots of this runtime apply (apply_storage / "
             "apply_instances as if they listed it); the generated apply-check carries it. "
             "Implies --only-runtime <rt> unless --only or --only-runtime is given.")] = None,
    force_bake: Annotated[list[str] | None, typer.Option("--force-bake",
        help="Bake the named image(s) even when current (repeatable; 'all' = every "
             "image in the run's surface). Images are otherwise baked only when "
             "their inputs changed, their parent moved under parent_policy: follow, "
             "or update.refresh_days is due (convergent bakes).")] = None,
    allow_unscoped_bakes: Annotated[bool, typer.Option("--allow-unscoped-bakes",
        help="Let a --no-dry-run run bake on runtimes OUTSIDE its apply scope (a list-valued "
             "apply_* flag or --apply-runtime). Without it such a run refuses before any bake; "
             "--apply-runtime <rt> already implies --only-runtime <rt> unless --only is given.")] = False,
    migrate_state: Annotated[list[str] | None, typer.Option("--migrate-state",
        help="MOVE the named terraform workspace's state to the backend it now resolves to "
             "(repeatable; needs --no-dry-run). The operation backs the old state up beside the "
             "root, copies it (init -migrate-state -force-copy), accepts only a clean plan at the "
             "new location and records the move in meta-state. There is deliberately no flag that "
             "merely proceeds past the move guard; giving resources up is a records correction.")] = None,
) -> None:
    """Run one or more lifecycles of the meta-workflow (V2)."""
    # registered lifecycles (release, retention) must exist before `all` /
    # a name is resolved -- found live: a fresh process resolved --all to
    # the four built-ins because the hooks loaded only inside the run
    from cs_image_system.base.commands.run_lifecycles import load_hook_plugins
    load_hook_plugins()
    try:
        selected = parse_lifecycles(lifecycles, all_)
    except ValueError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    if not selected:
        typer.secho("No lifecycles selected; pass names or --all "
                    f"({', '.join(lc.value for lc in all_lifecycles())}).", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    from cs_image_system.base.global_context import GlobalTypeContext
    gctx = GlobalTypeContext()
    gctx.explicit_bake_selection = bool(only or only_runtime)
    gctx.allow_unscoped_bakes = allow_unscoped_bakes
    workspaces = [w.strip() for w in (migrate_state or []) if w.strip()]
    if workspaces:
        if gctx.dry_run:
            typer.secho("--migrate-state moves state and needs --no-dry-run: a dry run never moves state",
                        fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        gctx.migrate_state = workspaces
    if apply_runtime:
        if apply_runtime not in gctx.runtime_builders:
            typer.secho(f"--apply-runtime: unknown runtime {apply_runtime!r}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        gctx.apply_runtime = apply_runtime
        for key in ("apply_storage", "apply_instances"):
            gctx.config[key] = [apply_runtime]
        if not only and not only_runtime:
            # stage 12.1: the apply scope implies the bake filter -- an ad-hoc run
            # without --only-runtime baked two AMIs on the other cloud (ledger 68)
            only_runtime = apply_runtime
            gctx.implied_scope = apply_runtime
    if only_runtime:
        from cs_image_system.base.commands.runtime_facts import images_on_runtime
        if only_runtime not in gctx.runtime_builders:
            typer.secho(f"--only-runtime: unknown runtime {only_runtime!r}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        only = list(only or []) + [f"{img}@{only_runtime}" for img in images_on_runtime(gctx, only_runtime)]
        if not only:
            only = ["none"]
        # ledger 70: a run scoped to one runtime's images plans no OTHER
        # runtime's terraform roots either (their plans can only fail or waste
        # time -- the GCE instance root's image-family lookup 404'd during a
        # scoped AWS bake after a cycle had disposed every GCE image)
        gctx.only_runtime_scope = only_runtime
    _run(selected, apply=apply, commit=commit, state_query=state_query, only=only,
         force_bake=force_bake)


@app.command(name="build-all")
def all(ctx: typer.Context) -> None:
    """Alias: run every lifecycle (with --base-only: the base-image lifecycle only)."""
    _run([Lifecycle.BASE_IMAGE] if is_base(ctx) else all_lifecycles(), apply=True, commit=False)


@app.command(name="validate")
def validate_command(ctx: typer.Context) -> None:
    """Validate the configuration (V1 checks plus every V2 rule); generates nothing."""
    from cs_image_system.base.commands.run_lifecycles import validate_only
    errors = validate_only()
    for err in errors:
        typer.secho(f" - {err}", fg=typer.colors.RED, err=True)
    if errors:
        typer.secho(f"Validation failed with {len(errors)} error(s).", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho("Validation successful.", fg=typer.colors.GREEN)


@app.command(name="generate")
def generate_command(ctx: typer.Context) -> None:
    """Alias: generate every lifecycle (base-image only with --base-only) without the apply step."""
    _run([Lifecycle.BASE_IMAGE] if is_base(ctx) else all_lifecycles(), apply=False, commit=False)


@app.command(name="upgrade")
def upgrade_command(
    ctx: typer.Context,
    kind: Annotated[str, typer.Argument(help="'instance' or 'image'")],
    name: Annotated[str, typer.Argument(help="The instance or instance-image name")],
    to: Annotated[str | None, typer.Option("--to",
        help="Target build id; default: the head of the relevant series in lineage")] = None,
    runtime: Annotated[str | None, typer.Option("--runtime",
        help="For images baked on several runtimes: which runtime's pin moves")] = None,
) -> None:
    """Move exactly one pin (DESIGN §3F5) -- the only way an instance or image
    changes the build it is bound to. Image pins are per runtime."""
    from cs_image_system.base.commands.upgrade import upgrade
    try:
        previous, target = upgrade(kind, name, to, runtime)
    except Exception as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho(f"{kind} {name}: pin moved {previous} -> {target}", fg=typer.colors.GREEN)


@app.command(name="preflight")
def preflight_command(
    typer_cntx: typer.Context,
    strict: Annotated[bool, typer.Option("--strict",
        help="Also exit 1 when a session expires within config.preflight.expected_run_minutes")] = False,
) -> None:
    """The credential sessions the configuration's runtimes need (AWS SSO
    profiles or static keys, GCP Application Default Credentials), read from
    the caches WITHOUT loading the configuration -- never a credential
    value. The Justfile's `full-test` gates its cloud-reading legs on this
    (stage 16). Exit 0 when every session is present; 2 when one is absent
    or EXPIRED (the configuration could not even load); 1 with --strict
    when one expires within the expected run length."""
    from cs_image_system.base.commands.preflight import raw_session_readiness
    root_dir, overlays = typer_cntx.obj["preflight_args"]
    from cs_image_system.base.commands.preflight import empty_environment_credentials
    lines, absent, expired, blocking = raw_session_readiness(root_dir, overlays)
    if not lines:
        typer.secho(f"preflight: no runtimes declared under {root_dir} (cfg/runtime-builders.yml)",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    for line in lines:
        colour = (typer.colors.RED if line in absent or line in expired
                  else typer.colors.YELLOW if line in blocking else None)
        typer.secho(line, fg=colour)
    # stage 43: a credential the environment sets but leaves EMPTY is a failure,
    # not an absence -- reported by name, never by value
    empty = empty_environment_credentials()
    for name in empty:
        typer.secho(f"environment: {name} is set but EMPTY -- a credential that exists with no value "
                    "is a failure, not an absence", fg=typer.colors.RED)
    if empty:
        typer.secho("preflight: an environment credential is set but empty (see above); "
                    "give it its value or unset it", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    if absent or expired:
        typer.secho("preflight: a session is absent or has EXPIRED -- the configuration cannot load "
                    "(aws sso login --profile <p> / gcloud auth application-default login)",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    if strict and blocking:
        typer.secho("preflight: a session expires before the expected run length (see above); "
                    "renew it or lower config.preflight.expected_run_minutes", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho("preflight: every session present", fg=typer.colors.GREEN, err=True)


@app.command(name="encrypt")
def encrypt_command(
    typer_cntx: typer.Context,
    value: Annotated[str | None, typer.Argument(help="a value to encrypt (or '-' for stdin); omit with --file")] = None,
    file: Annotated[list[Path] | None, typer.Option("--file", help="a YAML file to encrypt in place (repeatable)")] = None,
    field: Annotated[list[str] | None, typer.Option("--field", help="a field NAME whose scalar values and list elements are encrypted in each --file (repeatable)")] = None,
) -> None:
    """Encrypt a value, or fields of files in place, to the configuration's
    `encryption.recipients` (stage 33). Each value becomes its own
    ENC[age:...] marker -- a list entry by entry -- and everything else in a
    file is preserved byte for byte. Needs no identity."""
    from cs_image_system.base.encryption import encrypt_fields_in_text, encrypt_value, recipients_from_config
    root: Path = typer_cntx.obj["config_root"]
    try:
        recipients = recipients_from_config(root)
    except Exception as e:      # stage 63: a message, not a traceback
        typer.secho(f"encrypt: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    if file:
        if not field:
            typer.secho("encrypt: --file needs at least one --field", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        total = 0
        for f in file:
            text, n = encrypt_fields_in_text(f.read_text(), field, recipients)
            if n:
                f.write_text(text)
            total += n
            typer.secho(f"encrypt: {n} value{'s' if n != 1 else ''} in {f}", err=True)
        typer.secho(f"encrypt: {total} value{'s' if total != 1 else ''} encrypted to {len(recipients)} recipient{'s' if len(recipients) != 1 else ''}", err=True)
        return
    if value is None:
        typer.secho("encrypt: give a value (or '-' for stdin), or --file with --field", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    plain = sys.stdin.read().rstrip("\n") if value == "-" else value
    typer.echo(encrypt_value(plain, recipients))


@app.command(name="decrypt")
def decrypt_command(
    value: Annotated[str | None, typer.Argument(help="an ENC[age:...] marker (or '-' for stdin)")] = None,
    as_json: Annotated[bool, typer.Option(
        "--json", help="terraform `external` data source protocol (stage 34): read a JSON "
                       "object of markers on stdin, print it decrypted; unmarked values pass through")] = False,
    file: Annotated[list[Path] | None, typer.Option("--file", help="a YAML file to DECRYPT in place (repeatable); the inverse of `encrypt --file`")] = None,
    field: Annotated[list[str] | None, typer.Option("--field", help="a field NAME whose markers are written in clear in each --file (repeatable)")] = None,
) -> None:
    """Decrypt one marker with the identity in CSIS_CONFIG_IDENTITY and print
    the plaintext -- for the operator, never for a script that logs. With
    --json it is the program behind every generated root's
    `data "external" "sensitive"`, run by terraform at plan time."""
    from cs_image_system.base.encryption import decrypt_fields_in_text, decrypt_marker, is_marker
    try:
        if file:
            if not field:
                typer.secho("decrypt: --file needs at least one --field", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=2)
            total = 0
            for f in file:
                text, n = decrypt_fields_in_text(f.read_text(), field)
                if n:
                    f.write_text(text)
                total += n
                typer.secho(f"decrypt: {n} value{'s' if n != 1 else ''} in {f}", err=True)
            typer.secho(f"decrypt: {total} value{'s' if total != 1 else ''} written in clear", err=True)
            return
        if as_json:
            query = json.loads(sys.stdin.read() or "{}")
            if not isinstance(query, dict):
                raise ValueError("expected a JSON object of string values on stdin")
            result = {str(k): (decrypt_marker(v) if isinstance(v, str) and is_marker(v) else str(v))
                      for k, v in query.items()}
            typer.echo(json.dumps(result, sort_keys=True), nl=False)
            return
        if value is None:
            raise ValueError("a marker is required (or '-' for stdin, or --json)")
        marker = sys.stdin.read().strip() if value == "-" else value
        typer.echo(decrypt_marker(marker), nl=False)
    except ValueError as e:
        typer.secho(f"decrypt: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command(name="mask")
def mask_command(
    typer_cntx: typer.Context,
    minimum: Annotated[int, typer.Option("--min", help="the shortest plaintext to mask: a short common word masks unrelated log text")] = 8,
) -> None:
    """Print a ``::add-mask::`` line for every value the configuration carries
    encrypted, so a CI log never shows one (stage 49).

    Masking is a blocklist and cannot be complete -- a value that is wrapped,
    quoted or split across lines evades it -- so it is the last line of
    defence, not the first: the emission carries the ciphertext, and the
    committed tree is scanned for these same plaintexts before every commit."""
    import yaml
    from cs_image_system.base.encryption import decrypt_tree, decrypted_plaintexts, reset_decrypted_plaintexts
    from cs_image_system.base.materialize import PRIVATE_DIRNAME
    root = Path(typer_cntx.obj.get("config_root") or os.getcwd())
    reset_decrypted_plaintexts()
    # Stage 63 item 2: a masking pass that skipped a file is a pass that may
    # leak, so every per-file failure -- the identity that cannot open a marker,
    # a file that does not parse, a marker that is malformed -- ends the command
    # with exit 1 naming the file. Until 2026-09-23 each was swallowed, and a
    # missing identity printed nothing and exited 0.
    failures: list[str] = []
    for path in sorted(root.rglob("*.y*ml")):
        if ".git" in path.parts or "generated" in path.parts or PRIVATE_DIRNAME in path.parts:
            continue
        try:
            decrypt_tree(yaml.safe_load(path.read_text()), source=str(path))
        except Exception as e:
            failures.append(f"{path}: {e}")
    if failures:
        for f in failures:
            typer.secho(f"mask: {f}", fg=typer.colors.RED, err=True)
        typer.secho(f"mask: FAILED -- {len(failures)} file(s) could not be read for masking; nothing is masked "
                    "and the log would show every plaintext", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    for value in sorted(decrypted_plaintexts(include_public_by_decision=True)):
        if len(value) >= minimum:
            for line in value.splitlines():
                if len(line) >= minimum:
                    typer.echo(f"::add-mask::{line}")


@app.command(name="materialize")
def materialize_command(
    typer_cntx: typer.Context,
    source: Annotated[Path, typer.Argument(help="the generated directory (or file) to materialize")],
    destination: Annotated[Path | None, typer.Argument(
        help="where to write it (default: the mirror of SOURCE under the root's _private/)")] = None,
) -> None:
    """Copy a generated root into the private mirror, substituting every
    ENC[age:...] with its plaintext, and print where it landed (stage 49).

    The committed emission carries the ciphertext; the tools cannot read that,
    so every deferred command runs from the mirror instead. The mirror is
    never committed. Needs CSIS_CONFIG_IDENTITY; loads no configuration."""
    from cs_image_system.base.materialize import ensure_ignored, materialize, mirror_path, sync_back
    root = Path(typer_cntx.obj.get("config_root") or os.getcwd())
    src = source if source.is_absolute() else (Path(os.getcwd()) / source)
    try:
        dst = Path(destination) if destination else mirror_path(root, src)
        ensure_ignored(root)
        for name in sync_back(src, dst):
            log.info("materialize: synced back from the mirror: %s", name)
        written, substituted = materialize(src, dst)
        log.info("materialize: %d file(s), %d carrying ciphertext -> %s", written, substituted, dst)
        typer.echo(str(dst), nl=False)
    except (ValueError, OSError) as e:
        typer.secho(f"materialize: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command(name="init-config")
def init_config_command(
    destination: Annotated[Path, typer.Argument(help="the configuration repository to write (new, empty, or existing)")],
    starter: Annotated[str, typer.Option("--from", help="the starter tree: standard-aws (the default), standard-gce or complete")] = "standard-aws",
    force: Annotated[bool, typer.Option("--force", help="overwrite a release-owned file that exists and differs")] = False,
) -> None:
    """Write a starter configuration repository from this release (stage 64).

    A destination that does not exist or is empty takes the WHOLE starter: the
    YAML, the Justfile, the workflow, the hook, .gitignore, the terraform
    modules (module_source_base: tfmodules) and .csis-version pinned to this
    release. A destination that already holds a configuration takes only the
    parts the release owns (the same list without the YAML), so an existing
    repository gains or refreshes them; a release-owned file that exists and
    differs is refused by name unless --force. Loads no configuration."""
    from cs_image_system.system.starters import init_config
    try:
        report = init_config(destination, starter, force=force)
    except ValueError as e:
        typer.secho(f"init-config: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    except (OSError, RuntimeError) as e:
        typer.secho(f"init-config: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    for line in report.lines():
        typer.secho(line, fg=None if line.startswith("init-config: the") else typer.colors.RED,
                    err=not line.startswith("init-config: the"))
    if not report.ok:
        raise typer.Exit(code=1)
    if report.whole_tree:
        typer.echo("init-config: next: git init, just init, then replace every REPLACE-ME "
                   "(the tree's README says which values are yours)")


@app.command(name="public-safe")
def public_safe_command(
    typer_cntx: typer.Context,
    staged: Annotated[bool, typer.Option("--staged", help="scan the git index (what a commit would publish) instead of the tree")] = False,
    tree: Annotated[Path | None, typer.Option("--tree", help="the tree to scan (default: --root-dir or the current directory)")] = None,
    config: Annotated[Path | None, typer.Option("--config", help="the _config.yml whose public_safe.allow applies (default: the tree's, or the frozen fixture's in the system repository)")] = None,
) -> None:
    """Public-safe by construction (stage 35): refuse material that must never
    be public -- keys, tokens, PEM bodies, an age identity, a service-account
    file, plans and state by name; addresses and long tokens outside prose and
    tests -- in a tree or in the index. Exit 1 with every finding; allow a
    value by decision in cfg/_config.yml public_safe.allow."""
    from cs_image_system.base.public_safe import (
        allow_from_config, candidate_files, config_for, format_findings, git_toplevel, scan_staged, scan_tree, staged_paths,
    )
    root = Path(tree) if tree is not None else Path(typer_cntx.obj["config_root"])
    root = root.resolve()
    cfg = Path(config) if config is not None else config_for(root)
    allow = allow_from_config(cfg)
    if staged:
        top = git_toplevel(root)
        if top is None:
            typer.secho(f"public-safe: {root} is not inside a git repository", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        findings, count, scope = scan_staged(top, allow), len(staged_paths(top)), f"the index of {top}"
    else:
        files = candidate_files(root)
        findings, count, scope = scan_tree(root, allow, files), len(files), str(root)
    if findings:
        typer.echo(format_findings(findings))
        typer.secho(f"public-safe: REFUSED -- {len(findings)} finding{'s' if len(findings) != 1 else ''} in "
                    f"{count} file{'s' if count != 1 else ''} ({scope}); allow a value by decision in "
                    f"cfg/_config.yml public_safe.allow, never by silence", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho(f"public-safe: {count} file{'s' if count != 1 else ''} in {scope} hold nothing that must not be "
                f"public (allow list: {cfg if cfg else 'none'})", err=True)


@app.command(name="reencrypt")
def reencrypt_command(
    typer_cntx: typer.Context,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="report what would change; write nothing")] = False,
) -> None:
    """Rotate every encrypted value under the configuration root to the
    CURRENT `encryption.recipients`: decrypt each with CSIS_CONFIG_IDENTITY,
    re-encrypt to all recipients, write in place. Run after adding or
    removing a recipient. Nothing is written unless every value opens."""
    from cs_image_system.base.encryption import INLINE_MARKER_RE, identities_from_env, recipients_from_config, rotate_text
    root: Path = typer_cntx.obj["config_root"]
    try:
        recipients = recipients_from_config(root)
        identities = identities_from_env()
    except Exception as e:      # stage 63: a message, not a traceback
        typer.secho(f"reencrypt: NOTHING written -- {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    files = sorted({p for pat in ("*.yml", "*.yaml") for p in root.rglob(pat) if p.is_file() and ".git" not in p.parts and "generated" not in p.parts})
    rewrites: list[tuple[Path, str, int]] = []
    for f in files:
        text = f.read_text()
        if not INLINE_MARKER_RE.search(text):
            continue
        try:
            new_text, n = rotate_text(text, identities, recipients)
        except ValueError as e:
            typer.secho(f"reencrypt: NOTHING written -- {f}: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        rewrites.append((f, new_text, n))
    total = 0
    for f, new_text, n in rewrites:
        if not dry_run:
            f.write_text(new_text)
        total += n
        typer.secho(f"{'would rotate' if dry_run else 'rotated'} {n} value{'s' if n != 1 else ''} in {f}", err=True)
    typer.secho(f"{'would rotate' if dry_run else 'rotated'} {total} value{'s' if total != 1 else ''} to {len(recipients)} recipient{'s' if len(recipients) != 1 else ''}", err=True)


@app.command(name="test-mods")
def test_mods_command(
    ctx: typer.Context,
    image: Annotated[list[str] | None, typer.Option("--image", help="Only these instance images")] = None,
    force: Annotated[bool, typer.Option("--force", help="Re-test mods that already passed")] = False,
    strict: Annotated[bool, typer.Option("--strict", help="Exit nonzero when tests are skipped (no docker)")] = False,
) -> None:
    """Run every modification against a throwaway local container, twice
    (apply + idempotence); results in meta-state/mod-tests.yaml (EXPLORE)."""
    from cs_image_system.base.mod_tests import run_mod_tests
    results = run_mod_tests(__import__("cs_image_system.base.global_context", fromlist=["GlobalTypeContext"]).GlobalTypeContext(),
                            images=image, force=force)
    typer.echo(json.dumps([r.to_dict() for r in results], indent=2, sort_keys=True))
    failed = [r for r in results if r.status == "fail" or r.idempotent is False]
    skipped = [r for r in results if r.status in ("skipped", "unsupported")]
    for r in failed:
        typer.secho(f"FAIL {r.image}/{r.mod}: rc={r.first_run_rc}/{r.second_run_rc} idempotent={r.idempotent} "
                    f"{r.changes_on_rerun or r.detail[:200]}", fg=typer.colors.RED, err=True)
    if failed or (strict and skipped):
        raise typer.Exit(code=1)
    typer.secho(f"mod tests: {len(results) - len(skipped)} tested, {len(skipped)} skipped, 0 failed",
                fg=typer.colors.GREEN)
@app.command(name="release")
def release_command(
    ctx: typer.Context,
    image: Annotated[str | None, typer.Argument(help="The image series (instance or base image name)")] = None,
    build: Annotated[str, typer.Option("--build", help="Build id to release (default: the series head)")] = "",
    model: Annotated[str, typer.Option("--model", help="The model this build is released for")] = "default",
    note: Annotated[str, typer.Option("--note")] = "",
    runtime: Annotated[str | None, typer.Option("--runtime",
        help="Which runtime's series head to release when --build is not given")] = None,
    declared: Annotated[bool, typer.Option("--declared",
        help="Release every image's verified head per its declared `release: {model}` (stage 14); "
             "the release lifecycle's deferred step")] = False,
) -> None:
    """Mark a tested build as released for a model (EXPLORE release lifecycle)."""
    from cs_image_system.base.global_context import GlobalTypeContext
    from cs_image_system.base.release import ReleaseError, declared_release_targets, release
    gctx = GlobalTypeContext()
    if declared:
        targets = declared_release_targets(gctx)
        if not targets:
            typer.echo("release --declared: nothing to release (no verified head without a current release)")
            return
        done = []
        for name, rt, build_id, m in targets:
            try:
                release(gctx, name, build_id, model=m, note=f"declared release ({rt})")
            except ReleaseError as e:
                typer.secho(f"release refused: {e}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
            done.append(f"{name}@{rt} {build_id} -> {m}")
        typer.secho("released: " + "; ".join(done), fg=typer.colors.GREEN)
        return
    if not image:
        typer.secho("release: an image name is required (or --declared)", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    build_id = build or str((gctx.meta_state.series_head(image, runtime) or {}).get("build_id") or "")
    if not build_id:
        typer.secho(f"release: no build of {image!r} recorded in lineage", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    try:
        entry = release(gctx, image, build_id, model=model, note=note)
    except ReleaseError as e:
        typer.secho(f"release refused: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(entry, indent=2, sort_keys=True))
    typer.secho(f"released {image} {build_id} for model {model}", fg=typer.colors.GREEN)


@app.command(name="state-migration")
def state_migration_command(
    typer_cntx: typer.Context,
    action: Annotated[str, typer.Argument(
        help="begin: write the previous location beside the root, refuse a non-empty new location, back the "
             "old state up and leave the root initialised against the previous location; finish: record the "
             "move once the plan at the new location was clean; backup: pull the state at the root's location "
             "and keep it beside the root before a pre-plan `state rm` (stage 61 item 3)")],
    workspace: Annotated[str, typer.Option("--workspace", help="The terraform workspace (its builder's name)")],
    run: Annotated[str, typer.Option("--run", help="The id of the migrating run")],
    tofu: Annotated[str, typer.Option("--tofu", help="tofu/terraform binary")] = "tofu",
    backend_config: Annotated[Path | None, typer.Option("--backend-config",
        help="The root's .tfbackend.hcl (the NEW location); begin only")] = None,
    location: Annotated[str | None, typer.Option("--location",
        help="The new location as its type renders it (<type>://<container>/<key>); begin only")] = None,
) -> None:
    """One step of a state migration (stage 46.4.3), emitted into a root's runner by
    `run --migrate-state <workspace>`; never a by-hand command."""
    from cs_image_system.base.commands.state_migration import backup, begin, finish
    from cs_image_system.base.global_context import GlobalTypeContext
    gctx = GlobalTypeContext()
    # the root the runner entered, not the configuration root the load moved to
    cwd = Path(typer_cntx.obj.get("invoked_cwd") or os.getcwd())
    if action == "begin":
        code = begin(gctx, workspace, tofu, backend_config, run, cwd, new_location=location)
    elif action == "finish":
        code = finish(gctx, workspace, run, cwd)
    elif action == "backup":
        code = backup(gctx, workspace, tofu, run, cwd)
    else:
        typer.secho(f"state-migration: the action is begin, finish or backup, not {action!r}",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    if code:
        raise typer.Exit(code=code)


@app.command(name="prune-attachments")
def prune_attachments_command(
    typer_cntx: typer.Context,
    builder: Annotated[str, typer.Option("--builder", help="The identity (group) builder whose root this is")],
    run: Annotated[str, typer.Option("--run", help="The id of the running run")],
    tofu: Annotated[str, typer.Option("--tofu", help="tofu/terraform binary")] = "tofu",
) -> None:
    """Stage 61 item 3: one step of an identity root's runner, after its init
    and before its plan, in the initialised root -- drop from terraform state
    the membership attachments the declaration no longer has and the
    provider no longer holds, after a state backup. Never a by-hand command."""
    from cs_image_system.base.global_context import GlobalTypeContext
    gctx = GlobalTypeContext()
    gb = gctx.group_builders.get(builder)
    if gb is None:
        typer.secho(f"prune-attachments: no group builder named {builder!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    cwd = Path(typer_cntx.obj.get("invoked_cwd") or os.getcwd())
    code = gb.prune_stale_attachments(tofu, run, cwd)
    if code:
        raise typer.Exit(code=code)


@app.command(name="gate-plan")
def gate_plan_command(
    plan_json: Annotated[Path | None, typer.Argument(
        help="Output of `tofu show -json <planfile>` (omit when passing --planfile)")] = None,
    planfile: Annotated[Path | None, typer.Option("--planfile",
        help="A saved plan (`plan -out`); converted with `<tofu> show -json` locally")] = None,
    tofu: Annotated[str, typer.Option("--tofu", help="tofu/terraform binary for --planfile")] = "tofu",
    allow_destroy: Annotated[list[str] | None, typer.Option("--allow-destroy",
        help="Resource address (or address prefix) whose destruction is operation-driven "
             "and therefore whitelisted")] = None,
    require_unmounted: Annotated[list[str] | None, typer.Option("--require-unmounted",
        help="<instance>:<storage> pairs whose detach this plan carries; each needs a successful "
             "unmount receipt in ./unmount-receipts (stage 10.14)")] = None,
) -> None:
    """Apply gate: fail unless every planned destroy is whitelisted (DESIGN N19)
    and every detach was unmounted first (stage 10.14)."""
    from cs_image_system.base.commands.gate import gate_plan, plan_json_from_planfile, planfile_is_stale
    from cs_image_system.base.commands.unmount import read_receipt
    missing = []
    for pair in require_unmounted or []:
        inst, _, storage = pair.partition(":")
        receipt = read_receipt(Path.cwd(), inst, storage)
        if not receipt or not receipt.get("ok"):
            missing.append(pair)
    if missing:
        for pair in missing:
            typer.secho(f"DETACH NOT UNMOUNTED: {pair} has no successful unmount receipt "
                        "(unmount storage ..., or unmount storage --confirm)", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=3)
    if planfile is not None:
        stale_reason = planfile_is_stale(planfile)
        if stale_reason:
            # scoped-runs (finding 33): a failed plan once left the previous
            # sequence's tfplan behind and the gate judged the wrong plan.
            typer.secho(f"STALE PLANFILE: {stale_reason}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=3)
        plan = plan_json_from_planfile(planfile, tofu)
    elif plan_json is not None:
        plan = plan_json
    else:
        typer.secho("gate-plan: pass a plan JSON file or --planfile", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    violations = gate_plan(plan, allow_destroy or [])
    for v in violations:
        typer.secho(f"DESTROY NOT WHITELISTED: {v}", fg=typer.colors.RED, err=True)
    if violations:
        raise typer.Exit(code=3)
    typer.secho("Plan passes the apply gate.", fg=typer.colors.GREEN)


@app.command(name="apply-check")
def apply_check_command(
    lifecycle: Annotated[str, typer.Option("--lifecycle",
        help="The apply_<lifecycle> config key to check (identity, storage, instances, release)")],
    config_root: Annotated[Path | None, typer.Option("--config-root",
        help="Config tree root (default: walk up from the working directory "
             "to the nearest dir containing cfg/_config.yml)")] = None,
    apply_root: Annotated[str | None, typer.Option("--root",
        help="The terraform root (builder name) this apply belongs to; with a "
             "list-valued apply_<lifecycle> flag, only listed roots may apply")] = None,
    root_alias: Annotated[list[str] | None, typer.Option("--root-alias",
        help="Other names the root answers to in the flag list (e.g. its runtime)")] = None,
    overlay: Annotated[list[Path] | None, typer.Option("--overlay",
        help="Overlay file(s) the run was generated under; their 'config:' keys "
             "are re-read over cfg/_config.yml NOW, exactly as generation read them")] = None,
    apply_runtime: Annotated[str | None, typer.Option("--apply-runtime",
        help="The run was started with --apply-runtime: storage/instance roots of this runtime may apply")] = None,
) -> None:
    """Execution-time apply guard (scoped-runs, finding 24): re-reads the
    ``config: apply_<lifecycle>`` flag NOW and exits nonzero when it is off,
    so a runner script generated under yesterday's flags cannot apply under
    today's. Emitted by every gated apply sequence just before ``apply``.
    Per-root scoping (stage 7): the flag may be a list of root/runtime
    names, in which case only a listed root passes."""
    import yaml as _yaml
    from cs_image_system.base.utils import apply_flag_allows
    root = config_root
    if root is None:
        for cand in [Path.cwd(), *Path.cwd().parents]:
            if (cand / "cfg" / "_config.yml").is_file():
                root = cand
                break
    if root is None or not (root / "cfg" / "_config.yml").is_file():
        typer.secho("apply-check: no cfg/_config.yml found from the working directory up; "
                    "refusing to apply", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=3)
    cfg_root = root
    cfg = (_yaml.safe_load((cfg_root / "cfg" / "_config.yml").read_text()) or {}).get("config") or {}
    for path in overlay or []:
        if not path.is_file():
            typer.secho(f"apply-check: overlay {path} is gone; refusing to apply", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=3)
        cfg.update((_yaml.safe_load(path.read_text()) or {}).get("config") or {})
    flag = cfg.get(f"apply_{lifecycle}", False)
    if apply_runtime and lifecycle in ("storage", "instances"):
        flag = [apply_runtime]                      # the run's execution knob (stage 11.5)
    if not apply_flag_allows(flag, apply_root, root_alias or ()):
        scope = f" for root {apply_root!r}" if apply_root else ""
        shown = "false" if flag in (False, None) else repr(flag)
        typer.secho(f"apply_{lifecycle} is {shown} NOW in {cfg_root / 'cfg' / '_config.yml'}{scope} — "
                    "this runner script was generated when it allowed the apply; not applying.",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(code=3)
    typer.secho(f"apply_{lifecycle} allows{' root ' + repr(apply_root) if apply_root else ''}; proceeding.",
                fg=typer.colors.GREEN)


identity_app = typer.Typer(help="Identity-plugin utilities.")
app.add_typer(identity_app, name="identity")


@identity_app.command(name="export-gids")
def export_gids_command() -> None:
    """The gid shim (DESIGN N7): a terraform `data "external"` program.

    Reads the external-provider query (JSON object of strings: identity_type,
    org, team, api_host, groups) on stdin, asks the named identity plugin for
    the groups' gids via its queryable mechanism, and prints a JSON object
    {group: gid}. Credentials come from the environment, never from the query.
    """
    import sys
    from cs_image_system.base.commands.identity_gids import export_gids
    try:
        query = json.load(sys.stdin)
        result = export_gids(query)
    except Exception as e:
        typer.secho(f"export-gids: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(result, sort_keys=True))


runtime_app = typer.Typer(help="Configuration-driven facts about a runtime (stage 11.5).")
app.add_typer(runtime_app, name="runtime")


@runtime_app.command(name="describe")
def runtime_describe_command(
    name: Annotated[str, typer.Argument(help="The runtime builder name")],
) -> None:
    """Project/zone, ephemerality, retention, the images baked there, the
    declared storages with their cloud names, the instances -- as JSON, so
    recipes read facts from the configuration instead of hardcoding them."""
    from cs_image_system.base.commands.runtime_facts import describe_runtime
    try:
        typer.echo(json.dumps(describe_runtime(name), indent=2, sort_keys=True))
    except ValueError as e:
        typer.secho(f"runtime describe: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command(name="empty")
def empty_command(
    runtime: Annotated[str, typer.Option("--runtime", help="The runtime to check")],
) -> None:
    """Assert the runtime holds nothing beyond its declared storages (no
    instances, no custom images, no other disks or buckets) and that the
    strict state query agrees. Exit 1 naming every leftover."""
    from cs_image_system.base.commands.runtime_facts import emptiness
    from cs_image_system.base.global_context import GlobalTypeContext
    from cs_image_system.base.state_query import DRIFT_STALE, query_state, write_state_report
    try:
        result = emptiness(runtime)
    except (ValueError, NotImplementedError, RuntimeError) as e:
        typer.secho(f"empty: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    for kind, names in result["leftovers"].items():
        if names:
            typer.secho(f"empty: {kind} still present on {runtime}: {', '.join(names)}", fg=typer.colors.RED, err=True)
        else:
            typer.echo(f"empty: no {kind}" + (" beyond the declared storages" if kind in ("disks", "buckets") else ""))
    if not result["empty"]:
        raise typer.Exit(code=1)
    ctx = GlobalTypeContext()
    report = query_state(ctx)
    write_state_report(ctx, report)
    real = [d for d in report.drift if d.drift != DRIFT_STALE]
    for d in real:
        typer.secho(f"empty: state query drift: {d.kind} {d.name}: {d.detail}", fg=typer.colors.RED, err=True)
    if real or report.hard:
        raise typer.Exit(code=1)
    typer.secho(f"empty: {runtime} holds nothing beyond the declared storages; meta-state agrees",
                fg=typer.colors.GREEN)


lineage_app = typer.Typer(help="Lineage maintenance (stage 11.2).")
app.add_typer(lineage_app, name="lineage")


@lineage_app.command(name="restamp")
def lineage_restamp_command(
    runtime: Annotated[str, typer.Option("--runtime", help="Restamp the series heads baked on this runtime")],
    series: Annotated[list[str] | None, typer.Option("--series", help="Only these series (repeatable)")] = None,
    commit: Annotated[bool, typer.Option("--commit/--no-commit",
        help="Commit the meta-state change in the configuration repository")] = False,
) -> None:
    """Record the CURRENT input fingerprint on series heads whose recorded
    one predates a fingerprint-recipe change (§9), and re-tag the cloud
    image to match -- an operator statement that those builds are current.
    Under the global --dry-run it reports the plan."""
    from cs_image_system.base.commands.restamp import restamp
    from cs_image_system.base.global_context import GlobalTypeContext
    ctx = GlobalTypeContext()
    try:
        results = restamp(runtime, series)
    except (ValueError, RuntimeError) as e:
        typer.secho(f"restamp: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps([r.as_dict() for r in results], indent=2, sort_keys=True))
    if not results:
        typer.secho("restamp: every series head already carries the current fingerprint", fg=typer.colors.GREEN)
        return
    if ctx.dry_run:
        typer.secho(f"restamp (dry run): {len(results)} head(s) would be restamped; pass --no-dry-run",
                    fg=typer.colors.YELLOW)
        return
    if commit:
        from cs_image_system.base.meta_state import commit_meta_state
        sha = commit_meta_state(ctx.working_path, ctx.generation_path, ctx.run_id, ["restamp"], ctx.dry_run)
        if sha:
            typer.secho(f"meta-state committed: {sha}", fg=typer.colors.GREEN)
    typer.secho(f"restamped {len(results)} head(s) on {runtime}", fg=typer.colors.GREEN)


@lineage_app.command(name="relabel")
def lineage_relabel_command(
    runtime: Annotated[str, typer.Option("--runtime", help="Relabel the builds recorded on this runtime")],
    build: Annotated[list[str] | None, typer.Option("--build", help="Only these build ids (repeatable)")] = None,
) -> None:
    """Re-tag cloud images whose lineage tags disagree with their record
    (the state query's `changed` drift) from the record -- the tag side of
    zero-drift-report; `restamp` is the record side. No meta-state change.
    Under the global --dry-run it reports the plan."""
    from cs_image_system.base.commands.relabel import relabel
    from cs_image_system.base.global_context import GlobalTypeContext
    ctx = GlobalTypeContext()
    try:
        results = relabel(runtime, build)
    except (ValueError, RuntimeError, NotImplementedError) as e:
        typer.secho(f"relabel: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps([r.as_dict() for r in results], indent=2, sort_keys=True))
    if not results:
        typer.secho("relabel: every recorded image carries its record's tags", fg=typer.colors.GREEN)
        return
    if ctx.dry_run:
        typer.secho(f"relabel (dry run): {len(results)} image(s) would be relabelled; pass --no-dry-run",
                    fg=typer.colors.YELLOW)
        return
    failed = [r.build_id for r in results if not r.retagged]
    if failed:
        typer.secho(f"relabel: could not retag {failed}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho(f"relabelled {len(results)} image(s) on {runtime}", fg=typer.colors.GREEN)


unmount_app = typer.Typer(help="Unmount a storage on an instance before its detach (stage 10.14).")
app.add_typer(unmount_app, name="unmount")


@unmount_app.command(name="storage")
def unmount_storage_command(
    instance: Annotated[str, typer.Option("--instance", help="The launched instance")],
    storage: Annotated[str, typer.Option("--storage", help="The storage being detached")],
    mount_point: Annotated[str, typer.Option("--mount-point", help="Where it is mounted on the instance")],
    workdir: Annotated[Path | None, typer.Option("--workdir",
        help="The instance root's workspace (receipts go to <workdir>/unmount-receipts); default: cwd")] = None,
    confirm: Annotated[bool, typer.Option("--confirm",
        help="Do not run anything: record the OPERATOR's assertion that it is unmounted")] = False,
    timeout: Annotated[int, typer.Option("--timeout")] = 300,
) -> None:
    """Unmount the storage ON the instance through the runtime's session
    mechanism and write the receipt gate-plan --require-unmounted checks."""
    from cs_image_system.base.commands.unmount import unmount_storage
    wd = (workdir or Path.cwd()).resolve()
    try:
        result = unmount_storage(instance, storage, mount_point, wd, confirm=confirm, timeout=timeout)
    except (ValueError, NotImplementedError, RuntimeError) as e:
        typer.secho(f"unmount: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(result, indent=2, sort_keys=True))
    typer.secho(f"unmount receipt written for {instance}:{storage}", fg=typer.colors.GREEN)


workload_app = typer.Typer(help="Stage 56: what CI's workload login needs from the configuration.")
app.add_typer(workload_app, name="workload")


@workload_app.command(name="describe")
def workload_describe_command(
    env: Annotated[bool, typer.Option("--env", help="Print shell exports (OPA_WORKLOAD_CONNECTION, "
                                                    "OPA_WORKLOAD_ROLE, SFT_TEAM, OPA_ADDR) for the first builder")] = False,
) -> None:
    """Stage 56: what a workload login needs from the configuration -- the
    team's workload connection and role as named on the group builder, the
    team and the API address. Nothing secret; empty when none is named.
    Its own group, not `identity`: that group is exempt from loading the
    configuration (export-gids reads stdin), and this needs it loaded."""
    from cs_image_system.base.commands.login_proof import workload_facts
    from cs_image_system.base.global_context import GlobalTypeContext
    facts = workload_facts(GlobalTypeContext())
    if env:
        if not facts:
            typer.secho("workload describe: no group builder names a workload connection and role", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        f = facts[0]
        import shlex
        for key, val in (("OPA_WORKLOAD_CONNECTION", f["connection"]), ("OPA_WORKLOAD_ROLE", f["role"]),
                         ("SFT_TEAM", f["team"]), ("OPA_ADDR", f["api_host"])):
            typer.echo(f"export {key}={shlex.quote(val)}")
        return
    typer.echo(json.dumps(facts, indent=2, sort_keys=True))


verify_app = typer.Typer(help="Verify launched instances through the runtime (stage 10.2).")
app.add_typer(verify_app, name="verify")


@verify_app.command(name="instance")
def verify_instance_command(
    name: Annotated[str, typer.Argument(help="The declared instance to verify")],
    expect_build: Annotated[str | None, typer.Option("--expect-build",
        help="The build the instance must have booted (default: its pin / launch record)")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Seconds to wait for the startup scripts")] = 600,
    record_only: Annotated[bool, typer.Option("--record-only",
        help="Record the verdict but exit 0 even on failure (the `teardown` failure policy: the "
             "teardown proceeds and `verify assert` fails the run afterwards)")] = False,
) -> None:
    """Run the runtime's verification of a launched instance (serial console,
    booted image, data disks) and record the verdict in meta-state. Exits 1
    on failure -- the runner stops, and an ephemeral instance stays standing."""
    from cs_image_system.base.commands.verify_instance import VerificationFailed, verify_instance
    try:
        record = verify_instance(name, expected_build=expect_build, timeout=timeout, record_only=record_only)
    except VerificationFailed as e:
        typer.echo(json.dumps(e.record, indent=2, sort_keys=True))
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except (ValueError, NotImplementedError, RuntimeError) as e:
        typer.secho(f"verify: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(record, indent=2, sort_keys=True))
    if record.get("ok"):
        typer.secho(f"instance {name} verified", fg=typer.colors.GREEN)
    else:
        typer.secho(f"instance {name} FAILED verification (recorded; teardown proceeds)", fg=typer.colors.YELLOW, err=True)


@verify_app.command(name="login")
def verify_login_command(
    names: Annotated[list[str] | None, typer.Argument(help="Instances to log into (default: every standing one)")] = None,
    runtime: Annotated[str | None, typer.Option("--runtime", help="Only the standing instances on this runtime")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Seconds per client call")] = 120,
    record_only: Annotated[bool, typer.Option("--record-only",
        help="Record the verdicts but exit 0 even on failure")] = False,
) -> None:
    """Stage 56: log into each standing instance over `sft ssh` -- as the
    workload when OPA_TOKEN is set (scripts/opa-workload-token), else as the
    enrolled client -- and record the verdict in meta-state/login-proofs.yaml.
    A stopped machine is skipped, never started. Exits 1 on a failed login."""
    from cs_image_system.base.commands.login_proof import LoginProofFailed, login_proof
    try:
        records = login_proof(list(names or []) or None, runtime=runtime, timeout=timeout, record_only=record_only)
    except LoginProofFailed as e:
        typer.echo(json.dumps(e.records, indent=2, sort_keys=True))
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except (ValueError, NotImplementedError, RuntimeError) as e:
        typer.secho(f"verify login: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(records, indent=2, sort_keys=True))
    proved = [r["instance"] for r in records if r.get("ok")]
    skipped = [r["instance"] for r in records if r.get("skipped")]
    if proved:
        typer.secho(f"login proved for {', '.join(proved)}", fg=typer.colors.GREEN)
    if skipped:
        typer.secho(f"login SKIPPED for {', '.join(skipped)} (nothing proved)", fg=typer.colors.YELLOW, err=True)
    if not records:
        typer.secho("no standing instance to log into", fg=typer.colors.YELLOW, err=True)


@verify_app.command(name="assert")
def verify_assert_command(
    name: Annotated[str, typer.Argument(help="The instance whose last verification must have passed")],
) -> None:
    """Fail (exit 1) if the instance's last recorded verification failed --
    the closing step of the `teardown` failure policy."""
    from cs_image_system.base.commands.verify_instance import VerificationFailed, assert_last_verification
    try:
        assert_last_verification(name)
    except VerificationFailed as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho(f"instance {name}: last verification passed", fg=typer.colors.GREEN)


forget_app = typer.Typer(help="Drop a record of something that no longer exists (stage 54).")
app.add_typer(forget_app, name="forget")


@forget_app.command(name="instance")
def forget_instance_command(
    name: Annotated[str, typer.Argument(help="the instance whose records are to be dropped")],
) -> None:
    """Drop a destroyed instance's pin and launch parameters.

    A decommission through the gate does this itself. This is for the case
    where it did not and the records outlived the instance -- a pin with no
    instance is not merely untidy: with `config.require_released_builds` a
    DECLARED instance pinned to a build that was never released makes
    `validate` refuse every run, including the one that would release it.

    Refused while the instance is still declared: the way to remove a live
    instance is to undeclare it and let its destroy apply, which forgets the
    records for you. This only cleans up after that did not happen."""
    from cs_image_system.base.global_context import GlobalTypeContext
    ctx = GlobalTypeContext()
    if any(i.get_name() == name for i in ctx.instances):
        typer.secho(f"forget: instance '{name}' is still declared -- undeclare it and let its "
                    f"destroy apply (that forgets the records); this is for records that "
                    f"outlived their instance", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    ms = ctx.meta_state
    pin, params = ms.instance_pin(name), ms.launch_params().get(name)
    if pin is None and params is None:
        typer.echo(f"forget: nothing recorded for instance '{name}'")
        return
    ms.remove_instance_pin(name, ctx.run_id, op="forget")
    ms.remove_launch_params(name)
    typer.echo(f"forget: dropped instance '{name}'"
               + (f" (pin {pin})" if pin else "") + (" and its launch parameters" if params else ""))


dispose_app = typer.Typer(help="Dispose of recorded artifacts through the recorded path (stage 8.4).")
app.add_typer(dispose_app, name="dispose")


@dispose_app.command(name="image")
def dispose_image_command(
    build_ids: Annotated[list[str] | None, typer.Argument(
        help="Lineage build id(s) to dispose of (a GCE image name, an AMI id)")] = None,
    runtime: Annotated[str | None, typer.Option("--runtime",
        help="Restrict to builds baked on this runtime; with --all, every one of them")] = None,
    all_: Annotated[bool, typer.Option("--all", help="Every recorded build of --runtime")] = False,
    retention: Annotated[bool, typer.Option("--retention",
        help="Apply the declared retention (image retention.keep / runtime retention_keep; an "
             "ephemeral runtime keeps nothing): dispose of the builds it no longer keeps")] = False,
    commit: Annotated[bool, typer.Option("--commit/--no-commit",
        help="Commit the meta-state change (lineage, pins) in the configuration repository")] = False,
) -> None:
    """Delete RECORDED images from their runtime and drop their lineage
    record and any image pin at them, in one operation. Refuses unrecorded
    builds and builds an instance is pinned to or launched from. Under the
    global --dry-run (default) nothing is deleted: the plan is reported."""
    from cs_image_system.base.commands.dispose import dispose_images
    from cs_image_system.base.global_context import GlobalTypeContext
    ctx = GlobalTypeContext()
    try:
        results = dispose_images(build_ids, runtime, all_, retention=retention)
    except (ValueError, NotImplementedError, RuntimeError) as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps([r.as_dict() for r in results], indent=2, sort_keys=True))
    if not results:
        typer.secho("dispose: nothing recorded to dispose of", fg=typer.colors.YELLOW)
        return
    if ctx.dry_run:
        typer.secho(f"dispose (dry run): {len(results)} image(s) would be deleted; pass --no-dry-run",
                    fg=typer.colors.YELLOW)
        return
    if commit:
        from cs_image_system.base.meta_state import commit_meta_state
        sha = commit_meta_state(ctx.working_path, ctx.generation_path, ctx.run_id, ["dispose"], ctx.dry_run)
        if sha:
            typer.secho(f"meta-state committed: {sha}", fg=typer.colors.GREEN)
    typer.secho(f"disposed {len(results)} image(s): {', '.join(r.build_id for r in results)}",
                fg=typer.colors.GREEN)


state_app = typer.Typer(help="Systemic state: reality vs. meta-state (read-only).")
app.add_typer(state_app, name="state")


@state_app.command(name="query")
def state_query_command(
    strict: Annotated[bool, typer.Option("--strict",
        help="Exit 1 on any reality drift (missing/foreign/changed); `stale` -- a pin "
             "behind its series head -- is reported but is a policy state, not drift")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print the report as JSON")] = False,
) -> None:
    """Ask every plugin for its provider's view of what the system manages
    (images by lineage tags, storages by name, groups by gid) and diff it
    against meta-state. Writes generated/state-report.json; runs consult it
    and refuse to proceed on hard drift. Touches nothing."""
    from cs_image_system.base.global_context import GlobalTypeContext
    from cs_image_system.base.state_query import query_state, write_state_report
    ctx = GlobalTypeContext()
    report = query_state(ctx)
    path = write_state_report(ctx, report)
    if as_json:
        typer.echo(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        typer.echo(report.render())
    typer.secho(f"state report written to {path}", err=True)
    # stage 12.3: the sessions were printed by the callback before the load;
    # the strict verdict uses the same reading
    from cs_image_system.base.commands.preflight import session_lines
    _, blocking = session_lines(ctx)
    from cs_image_system.base.state_query import DRIFT_STALE
    if report.hard or (strict and any(d.drift != DRIFT_STALE for d in report.drift)):
        raise typer.Exit(code=1)
    if strict and blocking:
        typer.secho("preflight: a session expires before the expected run length (see above); "
                    "renew it (aws sso login --profile <p>) or lower config.preflight.expected_run_minutes",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@state_app.command(name="import")
def state_import_command(
    images: Annotated[bool, typer.Option("--images/--no-images", help="Adopt foreign tagged images into lineage")] = True,
    storages: Annotated[bool, typer.Option("--storages/--no-storages", help="Adopt foreign storages into storage-state")] = True,
) -> None:
    """Adopt *foreign* artifacts (tagged as ours, unrecorded) into meta-state
    -- the migration path. Writes meta-state only; never the cloud, OPA or
    tofu state (importing into tofu state stays a deliberate human step)."""
    from cs_image_system.base.global_context import GlobalTypeContext
    from cs_image_system.base.state_query import import_foreign, query_state, write_state_report
    ctx = GlobalTypeContext()
    report = query_state(ctx)
    done = import_foreign(ctx, report, images=images, storages=storages)
    for line in done:
        typer.secho(f"imported: {line}", fg=typer.colors.GREEN)
    if not done:
        typer.echo("nothing foreign to import")
    write_state_report(ctx, query_state(ctx))


@app.command(name="identity-attributes")
def identity_attributes_command(
    probe: Annotated[bool, typer.Option("--probe", help="Read the provider's current attributes (read-only)")] = False,
    dry_run_apply: Annotated[bool, typer.Option("--dry-run-apply", help="Print what an apply would change")] = False,
    apply_for_real: Annotated[bool, typer.Option("--apply", help="Write attributes (DISABLED: DESIGN Q7)")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print the (probed) plan as JSON")] = False,
) -> None:
    """Identity attributes (EXPLORE): show the plan written by the identity
    lifecycle, probe the provider read-only, and preview an apply. Writing is
    switched off until the stakeholder confirms DESIGN Q7."""
    from cs_image_system.base.global_context import GlobalTypeContext
    from cs_image_system.base.identity_attributes import (
        AttributeApplyDisabled, apply, attributes_plan, probe as probe_fn, read_attributes_plan)
    ctx = GlobalTypeContext()
    plan = read_attributes_plan(ctx) or attributes_plan(ctx)
    if probe or dry_run_apply or apply_for_real:
        plan = probe_fn(ctx, plan)
    if as_json:
        typer.echo(json.dumps(plan, indent=2, sort_keys=True, default=str))
    else:
        desired = plan.get("desired", {})
        for kind in ("groups", "users"):
            for name, attrs in sorted(desired.get(kind, {}).items()):
                typer.echo(f"{kind[:-1]} {name}: " + ", ".join(f"{k}={v}" for k, v in sorted(attrs.items())))
        for u in plan.get("unavailable", []):
            typer.secho(f"unavailable: {u}", err=True)
        if plan.get("conflicts"):
            typer.secho(f"provider conflicts: {plan['conflicts']}", fg=typer.colors.RED, err=True)
    if dry_run_apply or apply_for_real:
        try:
            lines = apply(ctx, plan, dry_run=not apply_for_real)
        except AttributeApplyDisabled as e:
            typer.secho(str(e), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=4)
        except ValueError as e:
            typer.secho(str(e), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=3)
        for line in lines:
            typer.echo(f"would set: {line}")
        if not lines:
            typer.secho("attributes already match", fg=typer.colors.GREEN)


# V1's `test`, `verify` and `cleanup` were placeholders for lifecycle phases V1
# planned and never built. V2 built each of them somewhere else and under another
# name, so the placeholders were retired on 2026-09-11: `verify` was deleted
# outright (the `verify` command GROUP above shadowed it -- it could never run),
# and these two now name their replacement and exit 2 instead of printing a
# warning and succeeding, which is what an old script needs.
_RETIRED = {
    "test": "V2 has no single 'test' phase: `test-mods` runs the modification tests in a "
            "container, `verify instance` runs an image's post-bake tests on a launched "
            "instance, and `just test` runs the suite.",
    "cleanup": "V2 disposes through the recorded path: the retention lifecycle (`run retention`) "
               "applies the declared policy, and `dispose image` removes a specific build.",
}


def _retired(name: str) -> None:
    typer.secho(f"{name}: retired in V2. {_RETIRED[name]}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=2)


@app.command(name="test")
def test_command(ctx: typer.Context) -> None:
    """Retired V1 command: names its V2 replacements and exits 2."""
    _retired("test")


@app.command(name="cleanup")
def cleanup_command(ctx: typer.Context) -> None:
    """Retired V1 command: names its V2 replacements and exits 2."""
    _retired("cleanup")


@app.callback(invoke_without_command=False)
def main(
    typer_cntx: typer.Context,
    root_dir: Path | None = typer.Option(
        None, "--root-dir", help="Location of root "
    ),
    verbose: Annotated[bool, typer.Option(help="Enable verbose output.")] = False,
    base_only: bool = typer.Option(
        False, "--base-only", help="Run only the base-image lifecycle (what `build-all`/`generate` select "
                                   "with this flag; the same as `run base-image`)"
    ),
    dry_run: bool = typer.Option(
        True, "--dry-run/--no-dry-run",
        help="Enumerate the deferred finalization commands (packer builds, "
             "tofu plan/apply) without executing them. On by default; pass "
             "--no-dry-run to actually execute finalization.",
    ),
    overlay: Annotated[list[Path] | None, typer.Option(
        "--overlay",
        help="Transient declaration file merged over the configuration tree for "
             "THIS invocation only (repeatable): 'config:' keys override, named "
             "'instances:'/'storages:' entries update or add. The tree on disk is "
             "never changed (stage 8: a change cycle's instance and teardown).",
    )] = None,
    undeclare: Annotated[list[str] | None, typer.Option(
        "--undeclare", metavar="KIND:NAME",
        help="Treat a declared tree entry as absent for THIS invocation only "
             "(repeatable), e.g. 'instance:gce-test': the instance decommissions "
             "through the gate exactly as if its entry had left the YAML (stage 28; "
             "the overlay 'undeclare' form as a flag).",
    )] = None,
):
    """
    Global parameters for the CLI.

    Parameters:
    ctx: typer.Context
        The Typer context object.
    root_dir: str
        Root directory for operations. Default is "."
        The working directory is changed to this value prior to execution
    verbose: bool
        Enable verbose output. Default is False.
    """
    setup_rich_logging(verbose)
    saved_dir = os.getcwd()

    def restore_dir():
        os.chdir(saved_dir)

    typer_cntx.call_on_close(restore_dir)
    typer_cntx.ensure_object(dict)
    # stage 61 item 3: loading the configuration below changes directory to
    # its root, so a command that runs FROM a root (the runner's
    # state-migration steps, in the private mirror) must be told where it
    # was invoked -- found live 2026-09-23 when a state backup pulled from
    # the configuration root instead of the mirror and kept nothing
    typer_cntx.obj["invoked_cwd"] = Path(saved_dir)
    if typer_cntx.invoked_subcommand in ("test", "cleanup"):
        return                      # retired V1 names: refuse without loading anything
    if typer_cntx.invoked_subcommand == "preflight":
        # stage 16: the sessions alone, from the raw tree -- nothing loads, no
        # plugin, no cloud call; the Justfile's full-test gates on this
        typer_cntx.obj["preflight_args"] = (Path(root_dir or os.getcwd()), [p.resolve() for p in (overlay or [])])
        return
    if typer_cntx.invoked_subcommand in ("gate-plan", "apply-check", "identity", "init-config"):
        # Utility commands invoked from runner scripts / terraform: no
        # configuration tree is loaded (plugins are loaded on demand;
        # apply-check reads only cfg/_config.yml itself). init-config (stage
        # 64) writes a tree; there is nothing to load yet.
        return
    if typer_cntx.invoked_subcommand in ("encrypt", "decrypt", "reencrypt", "public-safe", "materialize", "mask"):
        # stage 33: value tools -- encrypt reads only cfg/_config.yml's
        # recipients as text, so no identity and no load is needed.
        # stage 49: materialize joins them -- it runs from a generated root,
        # inside a run script, where there is no tree to load and no session.
        typer_cntx.obj["config_root"] = Path(root_dir or os.getcwd())
        return
    load_plugins()
    if not root_dir:
        root_dir = Path(os.getcwd())
    if typer_cntx.invoked_subcommand in ("run", "state"):
        # stage 12.3: sessions BEFORE the configuration loads -- the load
        # validates every runtime against its cloud and dies on an expired
        # session before any preflight could report it (found live 2026-09-09)
        from cs_image_system.base.commands.preflight import raw_session_lines
        lines, blocking, expired = raw_session_lines(Path(root_dir), [p.resolve() for p in (overlay or [])])
        for line in lines:
            typer.secho(line, fg=typer.colors.YELLOW if line in blocking else None, err=True)
        typer_cntx.obj["preflight_sessions"] = (lines, blocking)
        if expired:
            typer.secho("preflight: a session has EXPIRED; renew it (aws sso login --profile <p>) before "
                        "the configuration can even load", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    try:
        from cs_image_system.base.global_context import read_config_and_transform
        # V2 reads the whole configuration every time; --base-only only selects
        # the base-image lifecycle (it no longer changes what is read).
        read_config_and_transform(typer_cntx,
                                  root_dir,
                                  verbose,
                                  dry_run=dry_run,
                                  overlays=[p.resolve() for p in (overlay or [])],
                                  undeclare=list(undeclare or []))
        typer_cntx.obj["base_only"] = base_only
        # the load above REPLACES the context object; the invocation directory
        # is set again so a runner step still knows where it was started
        typer_cntx.obj["invoked_cwd"] = Path(saved_dir)
    except Exception as e:
        typer.echo(f"Error reading config file : {e}", err=True)
        raise e


if __name__ == "__main__":
    app()
