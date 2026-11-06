# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The umbrella's extras: which ``type:`` word needs which install.

``uv tool install cs-image-system`` carries no runtime. Each provider is
an extra of the umbrella package -- ``[aws]``, ``[gcloud]``, ``[docker]``,
``[okta]``, and ``[all]`` for every one -- and a tree that declares a
``type:`` word one of those plugins registers needs that extra installed.
This module is the table that answers "which extra?" when the plugin is
NOT installed, which is exactly when nothing else in the process can: the
registry knows only the words the installed plugins registered. So the
table is written out, statically, and a test regenerates it from the
installed workspace's registry and holds the two equal; the starters'
``Justfile`` carries the same words in its ``extras`` recipe, and another
test holds that copy to this one.

This module is the umbrella's own, the one module the ``cs-image-system``
distribution carries, because the table names providers and the core
(the contract, the base library, the command-line host) names none. The
core reaches it through the entry point the umbrella declares in the
group ``cs_image_system.extras`` (``cs_image_system.base.registry``
reads it when a ``type:`` word resolves to nothing); with no such entry
point installed the core's line names no extra and lists the words the
installed plugins register.

What the table covers is every word a tree writes under ``type:`` to name
a builder or a state backend (the ``*_builder``, ``*_builder_model``,
``state_backend`` and ``state_backend_model`` classifications). A version
checker is left out on purpose: the ``tofu`` checker is one class three
provider plugins carry, and an executable's checker is found by the
executable's name or type whichever of them is installed.
"""
from __future__ import annotations

#: extra -> the namespaces of the plugins it installs (a namespace is the
#: distribution's name with ``cs-image-system-`` and ``-plugin`` dropped,
#: ``cs_image_system.base.loader.namespace_of_distribution``).
EXTRAS: dict[str, tuple[str, ...]] = {
    "aws": ("aws-runtime", "tf-ebs-instance", "tf-s3-state"),
    "gcloud": ("gcloud-runtime", "tf-gcp", "gcs-state"),
    "docker": ("docker-runtime", "tf-docker"),
    "okta": ("okta-opa",),
}

#: The order the extras are named in: a tree's list is ``aws,gcloud,docker,okta``
#: in this order, whichever it declares.
EXTRA_ORDER: tuple[str, ...] = tuple(EXTRAS)

#: The umbrella's distribution name, the one the extras hang off.
UMBRELLA = "cs-image-system"


def is_type_word_classification(classification: str) -> bool:
    """Whether a tree names a class of ``classification`` by a ``type:``
    word: the builders, their models and the state backends. The version
    checkers and the injected item models are not written that way."""
    return classification.endswith(("_builder", "_builder_model")) or classification.startswith("state_backend")


def _words(extra: str, by_classification: dict[str, tuple[str, ...]]) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for classification, names in by_classification.items():
        for name in names:
            out[(classification, name)] = extra
            if classification.endswith("_builder") or classification == "state_backend":
                out[(classification + "_model", name)] = extra      # a builder and a backend each have a model twin
    return out


#: (classification value, bare ``type:`` word) -> the extra that installs the
#: plugin registering it. Written out, never derived at run time: it must
#: answer when the plugin is absent. ``tests/test_extras.py`` regenerates it
#: from the installed workspace and fails when the two differ.
WORDS: dict[tuple[str, str], str] = {
    **_words("aws", {
        "runtime_builder": ("aws",),
        "instance_builder": ("tofu",),
        "storage_builder": ("tf-aws", "tf-aws-ebs", "tf-aws-efs", "tf-aws-s3"),
        "state_backend": ("s3",),
    }),
    **_words("gcloud", {
        "runtime_builder": ("gcloud",),
        "instance_builder": ("tofu-gce",),
        "storage_builder": ("tf-gcp", "tf-gcp-filestore", "tf-gcp-gcs", "tf-gcp-pd"),
        "state_backend": ("gcs",),
    }),
    **_words("docker", {
        "runtime_builder": ("docker",),
        "instance_builder": ("tofu-docker",),
        "storage_builder": ("tf-docker-volume",),
    }),
    **_words("okta", {
        "group_builder": ("okta-tf", "okta-tf-ro"),
        "user_builder": ("okta-tf", "okta-tf-ro"),
    }),
}


def extra_for(classification: str, word: str) -> str | None:
    """The extra that installs the plugin registering ``word`` under
    ``classification`` (``"gcloud"`` for ``("runtime_builder_model",
    "gcloud")``), or ``None`` for a word no extra's plugin registers. A
    qualified word (``<namespace>/<name>``) is read by its name."""
    name = word.rpartition("/")[2]
    return WORDS.get((classification, name))


def words_by_extra() -> dict[str, list[str]]:
    """Each extra's bare words, sorted and once: what the starters'
    ``extras`` recipe maps, in the order the extras are named."""
    out: dict[str, set[str]] = {extra: set() for extra in EXTRA_ORDER}
    for (_classification, word), extra in WORDS.items():
        out[extra].add(word)
    return {extra: sorted(words) for extra, words in out.items()}


def install_line(extras: list[str] | tuple[str, ...], version: str | None = None) -> str:
    """The requirement that installs the umbrella with ``extras``, in the
    canonical order: ``cs-image-system[aws,okta]==0.2.0``."""
    chosen = ",".join(e for e in EXTRA_ORDER if e in extras)
    return f"{UMBRELLA}{f'[{chosen}]' if chosen else ''}{f'=={version}' if version else ''}"


def kind_of(classification: str) -> str:
    """The word a message calls a classification by: ``runtime`` for
    ``runtime_builder_model``, ``state backend`` for ``state_backend``."""
    return classification.removesuffix("_model").removesuffix("_builder").replace("_", " ")


def unknown_type_message(classification: str, word: str, registered: list[str]) -> str:
    """One line for a ``type:`` word no installed plugin registers under
    ``classification``: the extra to install when the table knows the
    word, else that the word is unknown and the words the installed
    plugins do register there."""
    kind = kind_of(classification)
    extra = extra_for(classification, word)
    if extra is not None:
        return (f"{kind} type {word!r} is registered by no installed plugin: install the extra: "
                f"uv tool install '{install_line([extra])}'")
    known = ", ".join(sorted(registered)) or "nothing"
    return (f"{kind} type {word!r} is unknown: no installed plugin registers it under {classification}, "
            f"and no extra of {UMBRELLA} carries it; the installed plugins register {known}")
