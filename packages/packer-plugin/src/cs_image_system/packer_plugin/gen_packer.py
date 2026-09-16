# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from cs_image_system.base.models.image import Image



"""Generate packer scripts from Image objects.

This module provides functionality to create templated packer scripts
for building machine images using HashiCorp Packer.
"""


# DeprecationWarning
class PackerScriptGenerator:
    """Generates packer scripts from Image objects."""

    def __init__(self, image: Image):
        """Initialize generator with an Image object.

        Args:
          image: Image object containing build configuration.
        """
        self.image = image

    def generate_template(self) -> dict[str, list[str]]:
        """Generate a packer template dictionary.

        Returns:
          Dictionary representing the packer template.
        """
        template = {
            "variables": self._generate_variables_from_image(self.image),
            "builders": self._build_builder_config(),
            "provisioners": self._generate_provisioners_from_image(self.image),
        }
        return template

    def _generate_provisioners_from_image(self, image: Image) -> list[str]:
        """Generate packer provisioners from Image object.

        Returns:
          List of provisioner definitions.
        """

        provisioners = []

        return provisioners

    def _generate_variables_from_image(self, image: Image) -> list[str]:
        """Generate packer variables from Image object.

        Returns:
          List of variable definitions.
        """
        variables = []
        for var_name, var_value in image.variables.items():
            variables.append(f"{var_name} = {var_value}")
        return variables

    def _build_builder_config(self) -> dict:
        """Build the builder configuration based on builder type.

        Returns:
          Dictionary with builder configuration.
        """
        config = {}
        return config

    def generate_json(self) -> str:
        """Generate packer template as JSON string.

        Returns:
          JSON string of the packer template.
        """
        template = self.generate_template()
        return json.dumps(template, indent=2)

    def write_template(self, output_path: Path) -> None:
        """Write packer template to file.

        Args:
          output_path: Path where template file will be written.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.generate_json())


def gen_packer(image: Image, output_dir: Path | None = None) -> str:
    """Generate packer scripts for an Image object.

    Args:
      image: Image object containing build configuration.
      output_dir: Optional directory to write template files.

    Returns:
      JSON string of generated packer template.
    """
    generator = PackerScriptGenerator(image)

    if output_dir:
        template_path = output_dir / f"{image.name}.pkr.json"
        generator.write_template(template_path)

    return generator.generate_json()
