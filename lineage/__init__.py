"""
Lineage Python SDK

A Python SDK for interacting with the Lineage blockchain.
"""

from lineage.blockchain import BlockchainClient
from lineage.wallet import Wallet
from lineage.config import get_config, validate_config, get_default_config
from lineage import utils

# Import key functions from key_handler
from lineage.key_handler import (
    generate_seed_phrase,
    validate_seed_phrase,
    generate_master_key,
    generate_keypair,
    encrypt_master_key,
    decrypt_master_key,
    encrypt_keypair,
    decrypt_keypair,
    validate_address,
    construct_address
)

try:
    from importlib.metadata import version as _pkg_version, PackageNotFoundError as _PkgNotFound
    try:
        __version__ = _pkg_version("lineage-sdk")
    except _PkgNotFound:  # running from a source tree that isn't installed
        __version__ = "1.0.0"
except ImportError:  # pragma: no cover - importlib.metadata is stdlib on 3.8+
    __version__ = "1.0.0"

__all__ = [
    'BlockchainClient',
    'Wallet', 
    'get_config',
    'validate_config',
    'get_default_config',
    'utils',
    # Key handler functions
    'generate_seed_phrase',
    'validate_seed_phrase', 
    'generate_master_key',
    'generate_keypair',
    'encrypt_master_key',
    'decrypt_master_key',
    'encrypt_keypair',
    'decrypt_keypair',
    'validate_address',
    'construct_address',
    '__version__'
]
