# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The commands only this plugin can drive, mounted on the system's console
script through the contract's ``cs_image_system.commands`` entry-point
group (``command_mounts`` below): the ``workload`` sub-app (``describe``,
``token``, ``probe``: what CI's workload login needs, the token OPA issues
for a GitHub Actions run, and the probe of the role's reach) and ``verify
login``, the login proof (over ``sft ssh`` for this plugin's groups). The
``workload`` sub-app exists exactly when this plugin is installed; ``verify
login`` is the core's one callback, shared with every identity plugin and
mounted once whichever of them is installed.

The ``workload`` sub-app loads the configuration only when a command needs
it (``deferred_load`` in the context object, which the console script
provides for a sub-app mounted with ``deferred_load=True``): ``workload
token`` takes its four names from the environment, because the probe
workflow runs on a checkout with no configuration, and loads the tree
only when one is missing.
"""
from __future__ import annotations

import json
import os
from typing import Annotated

import typer

from cs_image_system.contract.commands import VERIFY_LOGIN, CommandMount
from .workload_token import workload_facts, WorkloadTokenError, mint_token, NAME_VARS, WorkloadNames
from . import workload_token as wt

workload_app = typer.Typer(help="Stage 56: what CI's workload login needs from the configuration.")


@workload_app.command(name="describe")
def workload_describe_command(
    typer_cntx: typer.Context,
    env: Annotated[bool, typer.Option("--env", help="Print shell exports (OPA_WORKLOAD_CONNECTION, "
                                                    "OPA_WORKLOAD_ROLE, SFT_TEAM, OPA_ADDR) for the first builder")] = False,
) -> None:
    """What a workload login needs from the configuration -- the
    team's workload connection and role as named on the group builder, the
    team and the API address. Nothing secret; empty when none is named.
    Its own group, not `identity`: that group is exempt from loading the
    configuration (export-gids reads stdin), and this needs it loaded."""
    facts = workload_facts(_loaded(typer_cntx))
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


@workload_app.command(name="token")
def workload_token_command(typer_cntx: typer.Context) -> None:
    """This GitHub Actions run's OIDC token, presented to the team's workload
    connection; the OPA token it yields is the ONLY thing printed on standard
    output.

    Both tokens are masked in the job log (`::add-mask::` lines on standard
    error, which the runner scans as it scans standard output), the OIDC
    token's public claims and the client's verdict follow there. The four
    names -- OPA_WORKLOAD_CONNECTION, OPA_WORKLOAD_ROLE, SFT_TEAM, OPA_ADDR --
    come from the environment; any that is missing comes from the
    configuration's first group builder that names a workload connection,
    which loads the configuration. Needs a job holding `id-token: write`
    (ACTIONS_ID_TOKEN_REQUEST_URL / _TOKEN) and the `sft` client. Exit 2 when
    not in such a job or a name cannot be found, 1 when OPA issued nothing."""
    env = dict(os.environ)
    names = _workload_names(typer_cntx, env, "workload token")
    try:
        token = mint_token(names, env, say=lambda line: typer.echo(line, err=True))
    except WorkloadTokenError as e:
        typer.secho(f"workload token: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=e.exit_code)
    typer.echo(token, nl=False)


def _loaded(typer_cntx: typer.Context):
    """The configuration's context: loaded now through ``deferred_load``
    (which returns it -- the sub-command's context object predates the
    load), else the one the console script's callback already put in the
    context object (the context is passed, never fetched)."""
    load = typer_cntx.obj.get("deferred_load")
    return load() if load is not None else typer_cntx.obj["ctx"]


def _workload_names(typer_cntx: typer.Context, env: dict[str, str], what: str):
    """The four names from the environment, else from the configuration's
    first group builder that names a workload connection (loads it)."""
    names = WorkloadNames.from_environment(env)
    if names is not None:
        return names
    facts = workload_facts(_loaded(typer_cntx))
    if not facts:
        typer.secho(f"{what}: no group builder names a workload connection and role, and the "
                    f"environment lacks {', '.join(v for v in NAME_VARS if not env.get(v))}",
                    fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    f = facts[0]
    return WorkloadNames(connection=env.get("OPA_WORKLOAD_CONNECTION") or f["connection"],
                         role=env.get("OPA_WORKLOAD_ROLE") or f["role"],
                         team=env.get("SFT_TEAM") or f["team"],
                         api_host=env.get("OPA_ADDR") or f["api_host"])


@workload_app.command(name="probe")
def workload_probe_command(typer_cntx: typer.Context) -> None:
    """The workload probe (`just opa-workload-probe`):
    present this run's OIDC token to the team's workload connection as
    `workload token` does, discard the token it issues, and say two
    things: `connection: accepted this run's token and issued one`, and
    whether that token CARRIES THE ROLE -- `role: granted` when `sft
    resolve` of a standing machine of a managed group exits 0 as the
    workload, `role: not granted` when it does not (the connection issues
    its token from any branch; only the second line proves the role's
    branch pin), `role: not judged` when no such machine stands. Exit 0
    once the connection accepted the token, whatever the role verdict; the
    exits of `workload token` otherwise."""
    env = dict(os.environ)
    names = _workload_names(typer_cntx, env, "workload probe")
    try:
        token = wt.mint_token(names, env, say=lambda line: typer.echo(line, err=True))
    except wt.WorkloadTokenError as e:
        typer.secho(f"workload probe: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=e.exit_code)
    typer.secho(f"workload probe: connection {names.connection}: accepted this run's token and issued one (masked)",
                fg=typer.colors.GREEN)
    target = wt.probe_target(_loaded(typer_cntx))
    verdict, detail = wt.probe_role(names, token, target[0] if target else None)
    colour = {"granted": typer.colors.GREEN, "not granted": typer.colors.YELLOW}.get(verdict)
    typer.secho(f"workload probe: role {names.role}: {verdict} -- {detail}"
                + (f" (group {target[1]})" if target else ""), fg=colour)


def command_mounts() -> list[CommandMount]:
    """The entry point: the ``workload`` sub-app (its commands load the
    configuration themselves) and ``verify login`` under the system's
    ``verify`` sub-app -- the core's one callback, which every identity
    plugin mounts (a shared command: mounted once, whoever is installed)."""
    return [
        CommandMount(name="workload", app=workload_app, deferred_load=True),
        CommandMount(name="login", path=("verify",), kit_command=VERIFY_LOGIN),
    ]
