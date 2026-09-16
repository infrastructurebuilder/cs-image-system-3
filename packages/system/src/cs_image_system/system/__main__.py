# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import typer

from .cli import app

try:
    app()
except Exception as e:
    typer.echo(f"Error: {e}", err=True)
    local = e
    raise typer.Exit(code=1) from e
