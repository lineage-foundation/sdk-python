"""Tests for version information."""

import re

import lineage


def test_version_is_semver_string():
    """`lineage.__version__` is a semantic-version string."""
    assert isinstance(lineage.__version__, str)
    # MAJOR.MINOR.PATCH, optionally with a pre-release/build suffix.
    assert re.match(r"^\d+\.\d+\.\d+", lineage.__version__) is not None


def test_version_is_exported():
    assert "__version__" in lineage.__all__
