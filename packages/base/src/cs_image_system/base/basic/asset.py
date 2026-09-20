# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path
import tempfile
from typing import Any, overload
import logging



log = logging.getLogger(__name__)


class Asset:
    """Represents an asset to be included in the image build.  This is a tuple of
    (source_path, destination_path) where source_path is the path to the asset on
    the local filesystem and destination_path is the path where the asset should
    be placed in the image.  The source_path must exist and be a file or directory.
    The destination_path is relative to the root of the image and should not start
    with a leading slash.  This class provides validation and utility methods for
    working with assets, including ensuring that source paths exist and are valid,
    and that destination paths are well-formed.  It also provides a method to
    generate a dictionary representation of the asset for use in configuration files
    or other contexts where a structured representation is needed.  This class is
    designed to be used in conjunction with builders that need to include additional files or directories in the image, allowing for a clear and consistent way to specify and manage these assets throughout the build process.

    Note that the path should usually be relative, and on remote assets is rooted off the primary
    fileystem location ( i.e. / )
    """

    def __init__(self,
                 asset_tuple: tuple[Path, Any],
                 absolute: bool = False,
                 remote: bool = False) -> None:
        destination_path, val = asset_tuple
        self._tuple = asset_tuple
        self._binary =  isinstance(val, bytes)
        self._remote = remote or destination_path.is_absolute()
        if destination_path.is_absolute() and not absolute:
            log.warning(f"Destination path '{destination_path}' should probably not be absolute.")

    @property
    def path(self) -> Path:
        return self._tuple[0]
    @property
    def value(self) -> Any:
        return self._tuple[1]
    @property
    def str_value(self) -> str|None:
        return self.value if not self._binary else None
    @property
    def binary_value(self) -> bytes|None:
        return self.value if self._binary else None
    @property
    def is_remote(self) -> bool:
        return self._remote
    @property
    def is_binary(self) -> bool:
        return self._binary
    @property
    def str_tuple(self) -> tuple[Path, str] | None:
        return self._tuple if not self._binary else None
    @property
    def binary_tuple(self) -> tuple[Path, bytes] | None:
        return self._tuple if self._binary else None


class AssetSet(list[Asset]):
    """A set of assets to be included in the image build.  This class provides
    utility methods for working with sets of assets, including validation and
    generation of structured representations for use in configuration files or
    other contexts where a structured representation is needed.  This class is
    designed to be used in conjunction with builders that need to include multiple
    files or directories in the image, allowing for a clear and consistent way to
    specify and manage these assets throughout the build process.

    This returns a mapping of the remote assets to temp files containing those
    assets.  This allows the builder to work with remote assets as if they were local files,
    while still ensuring that the remote assets are properly included in the image build.
    """
    def __init__(self, default_path: Path | None = None) -> None:
        super().__init__()
        self.default_path = default_path

    def with_default_path(self, default_path: Path) -> "AssetSet":
        """Returns a new AssetSet with the given default path.  This allows for a more fluent interface when adding assets that share a common destination path."""
        if self.default_path is not None and self.default_path != default_path:
            raise ValueError(f"Cannot set default path to '{default_path}' because "
                             f"it is already set to '{self.default_path}'.")
        self.default_path = default_path
        return self

# 1. Overload names must match the implementation
    @overload
    def add(self, item: Path, value: Any) -> None: ...

    @overload
    def add(self, item: Any) -> None: ...

    # 2. The implementation names now match 'item'
    def add(self, item: Path | Any, value: Any = None) -> None:
        if isinstance(item, Path):
            path = item
            val = value
        else:
            if self.default_path is None:
                raise ValueError("Cannot add value without a default_path set.")
            path = self.default_path
            val = item
        # if val.endswith("\n"):
        #     log.warning(f"Value for asset at path '{path}' ends with a newline.  This may cause issues when writing the asset to a file.")
        if not val:
            if val is None:
                log.warning(f"Value for asset at path '{path}' is None.")
            return
        if isinstance(val, list):
            for v in val:
                if not isinstance(v, (str)):
                    raise ValueError(f"List values for asset at path '{path}' must be strings, got {type(v)}")
                self._appendx(path, v)
        else:
            self._appendx(path, val)

    def _appendx(self, item: Path, value: str ) -> None:
        self.append(Asset((item, value.strip("\n"))))

    # def __init__(self, default_path: Path | None = None, ) -> None:
    #     super().__init__()
    #     self.default_path = default_path

    # @dispatch(Path, Any)
    # def add(self,path: Path, value: Any) -> None:
    #     self.append(Asset((path, value)))

    # @dispatch(Any)
    # def add(self, value: Any) -> None:
    #     if not self.default_path:
    #         raise ValueError("Default path must be set to use add(value) method.")
    #     self.append(Asset((self.default_path, value)))


    # def add(self, path: Path, value: Any) -> None:
    #     assert isinstance(path, Path), f"Asset path must be a Path object, got {type(path)}"
    #     assert value is not None, "Asset value cannot be None"
    #     self.append(Asset((path, value)))

    @overload
    def add_list(self, item: Path, value: Any) -> None: ...

    @overload
    def add_list(self, item: Any) -> None: ...

    def add_list(self, item: Path, value: list[Any] | None = None) -> None:
        if isinstance(item, Path):
            path = item
            val = value
        else:
            if self.default_path is None:
                raise ValueError("Cannot add value without a default_path set.")
            path = self.default_path
            val = item
        if not val:
            if val is None:
                log.warning("Value for asset list is None")
            return
        if not isinstance(val, list):
            raise ValueError(f"Value must be a list, got {type(val)}")
        for v in val:
            self.add(path, v)

    def extend(self, assets: list[Asset]) -> None:
        for asset in assets:
            self.append(asset)


    def sort_and_write(self,
                       gen_path: Path | None = None,
                       temp_loc: Path = Path("./temp_assets"),
                       skip_remote: bool = False,
                       skip_writes: bool = False) -> dict[Path, Path]:

      if not gen_path:
        from ..global_context import GlobalTypeContext
        ctx = GlobalTypeContext() # Initialize the global context
        gen_path = ctx.generation_path
        gen_path.parent.mkdir(parents=True, exist_ok=True)

      remote_write_mapping: dict[Path, Path] = {}
      write_str_map: dict[Path, list[str]] = {}
      write_bin_map: dict[Path, list[bytes]] = {}
      write_remote_str_map: dict[Path, list[str]] = {}
      write_remote_bin_map: dict[Path, list[bytes]] = {}
      wrote_paths: set[Path] = set()
      for asset in self:
          if not asset.is_remote or (asset.is_remote and not skip_remote):
            if asset.is_remote:
              d = write_remote_str_map if not asset.is_binary else write_remote_bin_map
            else:
              d = write_str_map if not asset.is_binary else write_bin_map
            d.setdefault(asset.path, []).append(asset.value)
      if not skip_writes:
        for path, str_values in write_str_map.items():
            _gp = gen_path / path
            _gp.parent.mkdir(parents=True, exist_ok=True)
            mode = 'w' if _gp.exists() else 'a'
            with _gp.open(mode) as f:
                wrote_paths.add(_gp)
                f.write("\n".join(str_values))
        for path, bin_values in write_bin_map.items():
            _gp = gen_path / path
            _gp.parent.mkdir(parents=True, exist_ok=True)
            mode = 'wb' if _gp.exists() else 'ab'
            with _gp.open(mode) as f:
                wrote_paths.add(_gp)
                for bv in bin_values:
                    f.write(bv)
        if not skip_remote:
            _temploc = gen_path / temp_loc
            os.makedirs(_temploc, exist_ok=True)
            for path, str_values in write_remote_str_map.items():
                with tempfile.NamedTemporaryFile(dir=_temploc,
                                                mode='w+t',
                                                suffix = path.suffix,
                                                delete=False) as tmp_file:
                    tmp_file.write("\n".join(str_values))
                    tmp_file.flush()
                    wrote_paths.add(Path(tmp_file.name).absolute())
                    remote_write_mapping[path] = Path(tmp_file.name).absolute()
            for path, bin_values in write_remote_bin_map.items():
                with tempfile.NamedTemporaryFile(dir=_temploc,
                                                mode='w+b',
                                                suffix = path.suffix,
                                                delete=False) as tmp_file:
                    for bv in bin_values:
                        tmp_file.write(bv)
                    tmp_file.flush()
                    wrote_paths.add(Path(tmp_file.name).absolute())
                    remote_write_mapping[path] = Path(tmp_file.name).absolute()
      if wrote_paths: log.debug(f"Wrote assets to the following paths: {wrote_paths}")

      return remote_write_mapping


    