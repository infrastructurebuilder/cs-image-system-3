# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
log = logging.getLogger(__name__)
import asyncio

async def _run_command_async(cmd):
    """Asynchronous worker that monitors the process and kills it if cancelled."""
    log.info(f"[START] Running: {cmd}")
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    try:
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"Command '{cmd}' failed (Exit {process.returncode}): {stderr.decode().strip()}")
        return stdout.decode()

    except Exception:
        # If this task fails OR is cancelled due to another task failing, kill the OS process
        if process.returncode is None:
            log.warning(f"[KILLING] Killing process due to workflow failure: {cmd}")
            try:
                process.kill()
                await process.wait()  # Reap the zombie process
            except ProcessLookupError:
                pass
        raise

def run_all_processes_sync(commands):
    """
    Synchronous entrypoint for your workflow. 
    Blocks until all processes finish, or kills all if one fails.
    """
    async def orchestrator():
        # TaskGroup ensures 'fail-fast' behavior: one dies, all get cancelled
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(_run_command_async(cmd)) for cmd in commands]
        return [t.result() for t in tasks]

    try:
        # asyncio.run handles loop lifecycle entirely inside this sync call
        return asyncio.run(orchestrator())
    except ExceptionGroup as eg:
        # Catch the failures, log them, and re-raise so your workflow knows it failed
        log.error("\n[WORKFLOW ERROR] One or more subprocesses failed. All aborted.")
        for exc in eg.exceptions:
            log.error(f" -> {exc}")
        raise RuntimeError("Subprocess execution group failed.") from eg

# --- How you call it inside your workflow ---
def my_workflow_step():
    log.info("Workflow step started...")
    
    commands_list = [
        "sleep 2 && echo 'Task A done'",
        "sleep 1 && echo 'Task B failing' && exit 1", 
        "sleep 5 && echo 'Task C done'"
    ]
    
    # This is a normal, blocking, non-async call
    try:
        results = run_all_processes_sync(commands_list)
        log.info("Workflow step succeeded!", results)
    except RuntimeError:
        log.error("Workflow step failed gracefully.")

if __name__ == "__main__":
    my_workflow_step()