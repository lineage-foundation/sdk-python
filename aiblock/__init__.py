"""
AIBlock Python SDK

A Python SDK for interacting with the AIBlock blockchain.
"""

from aiblock.blockchain import BlockchainClient
from aiblock.wallet import Wallet
from aiblock.config import get_config, validate_config, get_default_config
from aiblock import utils

# Import key functions from key_handler
from aiblock.key_handler import (
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
