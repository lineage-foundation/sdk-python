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

__version__ = "0.2.9"

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
