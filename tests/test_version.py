"""Tests for version information."""

import re
from aiblock._version import (
    __version__,
    __version_tuple__,
    version,
    version_tuple
)

def test_version_format():
    """Test that version string follows semantic versioning."""
    assert isinstance(__version__, str)
    assert isinstance(version, str)
    assert __version__ == version
    # Version format: MAJOR.MINOR.devN+hash.date
    pattern = r'^\d+\.\d+(\.dev\d+\+[a-z0-9]+\.d\d+)$'
    assert re.match(pattern, __version__) is not None

def test_version_tuple():
    """Test version tuple format."""
    assert isinstance(__version_tuple__, tuple)
    assert isinstance(version_tuple, tuple)
    assert __version_tuple__ == version_tuple
    assert len(version_tuple) >= 2  # At least major and minor
    assert isinstance(version_tuple[0], int)  # Major version
    assert isinstance(version_tuple[1], int)  # Minor version 