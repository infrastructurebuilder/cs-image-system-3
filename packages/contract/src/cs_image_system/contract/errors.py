# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The exceptions a plugin raises that the core catches by type."""


class ContainerStartError(RuntimeError):
    """The test container could not be started: the image could not be
    pulled (the registry or the daemon did not answer, after the retries)
    or the run command refused. Carries the tool's own last line, which
    is what a reader needs (an exit status under eighty lines of
    traceback said nothing of a registry that was down)."""

    def __init__(self, image: str, stage: str, rc: int, words: str) -> None:
        self.image, self.stage, self.rc, self.words = image, stage, rc, words
        super().__init__(f"cannot start a container from {image}: {stage} exited {rc}: {words or '(nothing on stderr)'}")
