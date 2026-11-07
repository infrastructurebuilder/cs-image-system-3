# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""One tofu process at a time.

The lock under the provider cache refuses a second holder with exit 75 and
releases on any exit; another holder's lock is never removed. Acquiring
the lock creates the cache directory, so no recipe has to: the Justfile
exports the cache directory and depends on no recipe to make it.

history: bundle II item 6, III item 5.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

from harness import REPO


def test_the_tofu_lock_refuses_a_second_holder_and_releases_on_any_exit(tmp_path):
    """The wrapper script became `cs-image-system --locked`; the lock's shape
    and exit 75 are unchanged (the command's own tests are in
    tests/test_release_whole.py)."""
    from cs_image_system.base import tofu_lock
    assert not (REPO / "scripts" / "with-tofu-lock").exists()
    cache = tmp_path / "cache"
    env = {"TF_PLUGIN_CACHE_DIR": str(cache)}
    release = tofu_lock.acquire(env)
    assert (cache / ".lock" / "pid").is_file()                               # held while the command runs
    release()
    assert not (cache / ".lock").exists()                                    # released after it
    (cache / ".lock").mkdir()
    (cache / ".lock" / "pid").write_text("12345\n")
    with pytest.raises(tofu_lock.LockHeld) as e:
        tofu_lock.acquire(env)
    assert e.value.holder == "12345" and tofu_lock.EX_TEMPFAIL == 75
    assert (cache / ".lock").exists()                                        # another holder's lock is never removed


def test_the_lock_creates_the_cache_directory_and_no_recipe_has_to(tmp_path):
    from cs_image_system.base import tofu_lock
    cache = tmp_path / "never" / "made" / "cache"
    assert not cache.exists()
    release = tofu_lock.acquire({"TF_PLUGIN_CACHE_DIR": str(cache)})      # the lock makes the directory itself
    try:
        assert cache.is_dir()
    finally:
        release()
    just = shutil.which("just")
    if just is None:
        pytest.skip("`just` is not on PATH")
    recipes = subprocess.run([just, "--summary"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    assert "tofu-cache-dir" not in recipes, "the recipe is gone; `--locked` creates the cache directory"
    exported = subprocess.run([just, "--evaluate", "TF_PLUGIN_CACHE_DIR"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    assert exported.strip().endswith(".tofu-plugin-cache")          # still exported for every tofu init
