"""`test-ordinal-ratchet`: test names that overwrite each other or reuse an ordinal."""

from importlib.metadata import PackageNotFoundError, version as _installed_version

from .scanner import CLASSES, RATCHETED, Collision, Definition, collisions, count, definitions, scan  # noqa: F401

try:
    __version__ = _installed_version("test-ordinal-ratchet")
except PackageNotFoundError:  # a source checkout: no distribution metadata to read
    __version__ = "0+unknown"
