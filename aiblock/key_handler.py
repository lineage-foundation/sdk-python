"""Key handling module for the AIBlock SDK."""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple, Union
from mnemonic import Mnemonic
import base64
import hashlib
import nacl.signing
import nacl.secret
import uuid
from nacl.exceptions import BadSignatureError
import base58
from bip32utils import BIP32Key
from nacl.signing import SigningKey, VerifyKey
from nacl.secret import SecretBox
from nacl.utils import random
from nacl.exceptions import CryptoError

from aiblock.interfaces import (
    IErrorInternal,
    IKeypair,
    IMasterKey,
    IMasterKeyEncrypted,
    IKeypairEncrypted,
    IResult
)
from aiblock.utils.general_utils import (
    get_hex_string_bytes,
    get_hex_string_from_bytes,
    get_random_bytes,
    get_random_string,
    get_uuid_bytes,
    get_uuid_from_bytes,
    get_string_bytes,
    throw_if_err,
    truncate_by_bytes_utf8,
)
from aiblock.constants import ADDRESS_VERSION, ADDRESS_VERSION_OLD, TEMP_ADDRESS_VERSION

logger = logging.getLogger(__name__)

def get_address_version(
    public_key: Optional[bytes] = None,
    address: Optional[str] = None,
    version: Optional[int] = None
) -> IResult[int]:
    """Get the address version from a public key and address pair, or validate a version.
    
    Args:
        public_key: Optional public key bytes
        address: Optional address string
        version: Optional version to validate
        
    Returns:
        IResult[int]: The address version or an error
    """
    # Validate public key and address pair
    if public_key is not None and address is not None:
        temp_address = construct_address(public_key, TEMP_ADDRESS_VERSION)
        if temp_address.is_err:
            return temp_address
        
        default_address = construct_address(public_key, ADDRESS_VERSION)
        if default_address.is_err:
            return default_address
            
        if address == temp_address.get_ok():
            return IResult.ok(TEMP_ADDRESS_VERSION)
        elif address == default_address.get_ok():
            return IResult.ok(ADDRESS_VERSION)
        else:
            return IResult.err(IErrorInternal.InvalidAddressVersion)
            
    # Validate version directly
    elif version is not None:
        if version in (TEMP_ADDRESS_VERSION, ADDRESS_VERSION):
            return IResult.ok(version)
        return IResult.err(IErrorInternal.InvalidAddressVersion)
        
    return IResult.err(IErrorInternal.InvalidParametersProvided)

def generate_seed_phrase() -> str:
    """Generate a new BIP39 seed phrase.
    
    Returns:
        str: The generated seed phrase
    """
    try:
        mnemo = Mnemonic("english")
        return mnemo.generate(strength=128)
    except Exception as e:
        logger.error(f"Error generating seed phrase: {str(e)}")
        raise ValueError("Failed to generate seed phrase") from e

def validate_seed_phrase(seed: str) -> bool:
    """Validate if a seed phrase is valid.
    
    Args:
        seed: The seed phrase to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not seed:
        return False
    try:
        mnemo = Mnemonic("english")
        return mnemo.check(seed)
    except Exception:
        return False

def get_passphrase_buffer(passphrase: Optional[str] = None) -> IResult[bytes]:
    """
    Convert a passphrase to bytes. If no passphrase is provided or if it's empty,
    returns an empty byte string.

    Args:
        passphrase (Optional[str], optional): The passphrase to convert. Defaults to None.

    Returns:
        IResult[bytes]: The passphrase as bytes or an error
    """
    try:
        # Use empty string as default if no passphrase provided
        passphrase = passphrase or ''
        return IResult.ok(passphrase.encode('utf-8'))
    except Exception as e:
        return IResult.err(IErrorInternal.UnableToGenerateBuffer, str(e))

def generate_master_key(seed: str, passphrase: str = None) -> IResult[IMasterKey]:
    """Generate a master key from a seed phrase.

    Args:
        seed (str): The seed phrase to generate the master key from
        passphrase (str, optional): Optional passphrase for additional security. Defaults to None.

    Returns:
        IResult[IMasterKey]: Result containing the master key or an error
    """
    if not seed:
        return IResult.err(IErrorInternal.InvalidParametersProvided)

    # Default passphrase to empty string if not provided
    if passphrase is None:
        passphrase = ""

    try:
        # Initialize mnemonic
        mnemo = Mnemonic("english")
        
        # Validate seed phrase
        if not mnemo.check(seed):
            return IResult.err(IErrorInternal.InvalidSeedPhrase)

        # Generate seed bytes from mnemonic
        seed_bytes = mnemo.to_seed(seed, passphrase)
        # Create master key
        master_key = IMasterKey(secret=seed_bytes, seed=seed)
        return IResult.ok(master_key)
    except Exception as e:
        logger.error(f"Failed to generate master key: {e}")
        return IResult.err(IErrorInternal.UnableToGenerateKeypair)

def generate_keypair(version: int = ADDRESS_VERSION, seed: Optional[bytes] = None) -> IResult[IKeypair]:
    """Generate a keypair with optional seed.
    
    Args:
        version: Address version to use
        seed: Optional 32-byte seed for deterministic key generation
        
    Returns:
        IResult[IKeypair]: The generated keypair or an error
    """
    try:
        # Match JS SDK exactly - no version validation
        if seed and len(seed) != 32:
            seed = seed[:32]  # Truncate to 32 bytes
            
        # Generate keypair using nacl
        keypair_raw = nacl.signing.SigningKey(seed) if seed else nacl.signing.SigningKey.generate()
        verify_key = keypair_raw.verify_key
        
        # Get address based on version
        address_result = construct_address(verify_key.encode(), version)
        if address_result.is_err:
            return address_result
            
        # Revert to storing the 32-byte seed from encode()
        return IResult.ok(IKeypair(
            address=address_result.get_ok(),
            secret_key=keypair_raw.encode(),  # Store the 32-byte seed
            public_key=verify_key.encode(),
            version=version
        ))
        
    except Exception:
        return IResult.err(IErrorInternal.UnableToGenerateKeypair)

def get_next_derived_keypair(master_key: IMasterKey, depth: int, version: int = ADDRESS_VERSION) -> IResult[IKeypair]:
    """Get the next derived keypair from a master key.
    
    Args:
        master_key: The master key to derive from
        depth: The derivation depth
        version: Address version to use
        
    Returns:
        IResult[IKeypair]: The derived keypair or an error
    """
    try:
        # Validate version
        version_result = get_address_version(version=version)
        if version_result.is_err:
            return IResult.err(version_result.error())
            
        # Derive child key
        seed_key_raw = master_key.secret.derive_child(depth, True)
        seed_key = get_string_bytes(seed_key_raw.xprivkey)
        return generate_keypair(version, seed_key)
    except Exception:
        return IResult.err(IErrorInternal.UnableToDeriveNextKeypair)

def construct_address(public_key: bytes, version: Optional[int]) -> IResult[str]:
    """Constructs an address from the provided public key.

    Args:
        public_key (bytes): The public key to construct the address from
        version (Optional[int]): The version of the address to construct

    Returns:
        IResult[str]: The constructed address on success, error message on failure
    """
    try:
        if version == ADDRESS_VERSION_OLD:
            # Match JS SDK: Truncate to 32 chars
            array_one = bytes([32, 0, 0, 0, 0, 0, 0, 0])
            merged_array = array_one + public_key
            hash_str = hashlib.sha3_256(merged_array).hexdigest()
            return IResult.ok(truncate_string(hash_str, len(hash_str) - 16))
        elif version == TEMP_ADDRESS_VERSION:
            # Match JS SDK: sha3_256 of base64 bytes
            b64_str = base64.b64encode(public_key).decode()
            hex_bytes = bytes.fromhex(b64_str.encode().hex())
            hash_str = hashlib.sha3_256(hex_bytes).hexdigest()
            return IResult.ok(hash_str)
        elif version == ADDRESS_VERSION:
            # Match JS SDK: Return raw hex string
            return IResult.ok(hashlib.sha3_256(public_key).hexdigest())
        else:
            return IResult.err(IErrorInternal.InvalidAddressVersion)
    except Exception as e:
        return IResult.err(f"Failed to construct address: {str(e)}")

def truncate_string(string: str = "", max_length: int = 50) -> str:
    """Truncates a string to the specified length.

    Args:
        string (str): The string to truncate
        max_length (int, optional): The maximum length. Defaults to 50.

    Returns:
        str: The truncated string
    """
    if not string:
        return ""
    return string[:max_length]

def create_signature(secret_key: bytes, message: bytes) -> bytes:
    """Create a detached signature for a message using a secret key.
    
    Args:
        secret_key: The secret key bytes (64-byte full secret key)
        message: The message to sign
        
    Returns:
        bytes: The detached signature
    """
    # Match JS SDK exactly - use full secret key
    return nacl.signing.SigningKey(secret_key).sign(message).signature

def generate_new_keypair_and_address(
    master_key: IMasterKey,
    address_version: int = ADDRESS_VERSION,
    addresses: list[str] = []
) -> IResult[IKeypair]:
    """Generate a new unique keypair and address.
    
    Args:
        master_key: The master key to derive from
        address_version: Address version to use
        addresses: List of existing addresses to avoid duplicates
        
    Returns:
        IResult[IKeypair]: The new unique keypair or an error
    """
    try:
        # Validate version
        version_result = get_address_version(version=address_version)
        if version_result.is_err:
            return IResult.err(version_result.error())
            
        counter = len(addresses)
        while True:
            # Get next derived keypair
            current_key = get_next_derived_keypair(master_key, counter, address_version)
            if current_key.is_err:
                return current_key
                
            # Generate address
            current_addr = construct_address(current_key.get_ok().public_key, address_version)
            if current_addr.is_err:
                return current_addr
                
            # Check if address is unique
            if current_addr.get_ok() not in addresses:
                return current_key
                
            counter += 1
            
    except Exception:
        return IResult.err(IErrorInternal.UnableToGenerateKeypair)

def encrypt_master_key(master_key: IMasterKey, passphrase: Optional[bytes] = None) -> IResult[IMasterKeyEncrypted]:
    """Encrypt a master key using a passphrase.
    
    Args:
        master_key: The master key to encrypt
        passphrase: Optional passphrase for encryption
        
    Returns:
        IResult[IMasterKeyEncrypted]: The encrypted master key or an error
    """
    try:
        if not master_key or not master_key.secret:
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        # Generate nonce and get secret key
        nonce = truncate_by_bytes_utf8(uuid.uuid4().hex, 24)
        secret_key = get_string_bytes(master_key.secret.xprivkey)
        
        # Create secret box and encrypt
        box = nacl.secret.SecretBox(passphrase)
        encrypted = box.encrypt(secret_key, get_string_bytes(nonce))
        
        return IResult.ok(IMasterKeyEncrypted(
            nonce=nonce,
            save=base64.b64encode(encrypted.ciphertext).decode('utf-8')
        ))
    except Exception:
        return IResult.err(IErrorInternal.UnableToEncryptMasterKey)

def validate_address(address: str) -> IResult[str]:
    """Validate a Bitcoin address.
    
    Args:
        address: The address to validate
        
    Returns:
        IResult containing the validated address or an error
    """
    try:
        # Decode the base58 address
        decoded = base58.b58decode(address)
        
        # Check minimum length (version + hash + checksum)
        if len(decoded) < 25:
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        # Extract version, hash, and checksum
        version = decoded[0]
        hash_bytes = decoded[1:-4]
        checksum = decoded[-4:]
        
        # Verify version
        if version != ADDRESS_VERSION:
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        # Verify checksum
        double_sha256 = hashlib.sha256(hashlib.sha256(decoded[:-4]).digest()).digest()
        if double_sha256[:4] != checksum:
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        return IResult.ok(address)
        
    except Exception:
        return IResult.err(IErrorInternal.InvalidParametersProvided)

def decrypt_master_key(encrypted_key: IMasterKeyEncrypted, passphrase: bytes) -> IResult[IMasterKey]:
    """Decrypt an encrypted master key using the passphrase.
    
    Args:
        encrypted_key: The encrypted master key
        passphrase: The passphrase to decrypt with
        
    Returns:
        IResult[IMasterKey]: The decrypted master key or an error
    """
    try:
        if not encrypted_key or not encrypted_key.save or not encrypted_key.nonce:
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        # Decode the encrypted data
        ciphertext = base64.b64decode(encrypted_key.save)
        nonce = get_string_bytes(encrypted_key.nonce)
        
        # Create secret box and decrypt
        box = nacl.secret.SecretBox(passphrase)
        decrypted = box.decrypt(ciphertext, nonce)
        
        return IResult.ok(IMasterKey(
            secret=decrypted,
            seed=""  # Original seed is not stored
        ))
    except Exception:
        return IResult.err(IErrorInternal.UnableToDecryptMasterKey)

def decrypt_keypair(encrypted_keypair: IKeypairEncrypted, passphrase: bytes) -> IResult[IKeypair]:
    """Decrypt an encrypted keypair using a passphrase.

    Args:
        encrypted_keypair: The encrypted keypair
        passphrase: The passphrase bytes used for encryption

    Returns:
        IResult[IKeypair]: The decrypted keypair or error
    """
    logger.debug("Attempting to decrypt keypair. Version: %s", encrypted_keypair.version)
    logger.debug("Received passphrase (bytes): %s", passphrase.hex() if passphrase else 'None')
    logger.debug("Encrypted Master Key Nonce (b64): %s", encrypted_keypair.master_key.nonce)
    logger.debug("Encrypted Master Key Save (b64): %s", encrypted_keypair.master_key.save)
    try:
        if not encrypted_keypair or not encrypted_keypair.master_key:
            logger.error("Invalid encrypted_keypair object provided to decrypt_keypair")
            return IResult.err(IErrorInternal.InvalidParametersProvided)

        # Hash the passphrase to create the 32-byte key (MUST match encryption)
        key = hashlib.sha256(passphrase).digest()
        logger.debug("Derived decryption key (sha256(passphrase)): %s", key.hex())

        # Decode nonce and ciphertext from base64
        try:
            nonce = base64.b64decode(encrypted_keypair.master_key.nonce)
            ciphertext = base64.b64decode(encrypted_keypair.master_key.save)
            logger.debug("Decoded nonce (bytes): %s", nonce.hex())
            logger.debug("Decoded ciphertext (bytes): %s", ciphertext.hex())
        except Exception as decode_err:
            logger.error("Failed to decode base64 nonce or ciphertext: %s", decode_err)
            return IResult.err(IErrorInternal.InvalidParametersProvided, "Invalid base64 encoding")

        # Decrypt using SecretBox
        box = nacl.secret.SecretBox(key)
        secret_key_bytes = box.decrypt(ciphertext, nonce) # This is the original 64-byte SigningKey seed
        logger.debug("Successfully decrypted secret key (bytes): %s", secret_key_bytes.hex())

        # Reconstruct the SigningKey and VerifyKey
        signing_key = nacl.signing.SigningKey(seed=secret_key_bytes) # Correctly using the full 64-byte seed
        verify_key = signing_key.verify_key
        public_key_bytes = verify_key.encode()
        logger.debug("Reconstructed public key (bytes): %s", public_key_bytes.hex())

        # Reconstruct the address using the stored version
        address_result = construct_address(public_key_bytes, encrypted_keypair.version)
        if address_result.is_err:
            logger.error("Failed to reconstruct address from decrypted key: %s - %s", address_result.error, address_result.error_message)
            return address_result # Propagate error
        
        reconstructed_address = address_result.get_ok()
        logger.debug("Reconstructed address: %s", reconstructed_address)

        return IResult.ok(IKeypair(
            address=reconstructed_address,
            secret_key=secret_key_bytes, # Store the full 64-byte seed
            public_key=public_key_bytes,
            version=encrypted_keypair.version
        ))
    except CryptoError: # Specific error for decryption failure
        logger.error("Decryption failed - likely incorrect passphrase or corrupted data")
        return IResult.err(IErrorInternal.UnableToDecryptKeypair, "Decryption failed - likely incorrect passphrase or corrupted data")
    except Exception as e:
        logger.error(f"Unexpected error during keypair decryption: {str(e)}")
        return IResult.err(IErrorInternal.UnableToDecryptKeypair)

def encrypt_keypair(keypair: IKeypair, passphrase: bytes) -> IResult[IKeypairEncrypted]:
    """Encrypt a keypair using a passphrase.
    
    Args:
        keypair: The keypair to encrypt
        passphrase: The passphrase to use for encryption
        
    Returns:
        IResult[IKeypairEncrypted]: The encrypted keypair or an error
    """
    try:
        if not keypair or not keypair.secret_key:
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        # Hash the passphrase to create a 32-byte key
        key = hashlib.sha256(passphrase).digest()
        
        # Create secret box and encrypt
        box = nacl.secret.SecretBox(key)
        secret_key = bytes.fromhex(keypair.secret_key) if isinstance(keypair.secret_key, str) else keypair.secret_key
        encrypted = box.encrypt(secret_key)
        
        # Create encrypted master key
        master_key = IMasterKeyEncrypted(
            nonce=base64.b64encode(encrypted[:24]).decode('utf-8'),
            save=base64.b64encode(encrypted).decode('utf-8')
        )
        
        return IResult.ok(IKeypairEncrypted(
            master_key=master_key,
            version=keypair.version
        ))
    except Exception:
        return IResult.err(IErrorInternal.UnableToEncryptKeypair)

def generate_keypair_from_seed(seed_phrase: str, version: int = ADDRESS_VERSION) -> IResult[IKeypair]:
    """Generate a keypair from a seed phrase.
    
    Args:
        seed_phrase: The seed phrase to generate the keypair from
        version: Address version to use
        
    Returns:
        IResult[IKeypair]: The generated keypair or an error
    """
    try:
        # Validate inputs
        if not seed_phrase:
            return IResult.err(IErrorInternal.InvalidParametersProvided)
            
        version_result = get_address_version(version=version)
        if version_result.is_err:
            return version_result
            
        # Validate seed phrase
        if not validate_seed_phrase(seed_phrase):
            return IResult.err(IErrorInternal.InvalidSeedPhrase)
            
        # Generate master key
        master_key_result = generate_master_key(seed_phrase)
        if master_key_result.is_err:
            return master_key_result
            
        # Generate keypair from first 32 bytes of master key secret
        master_key = master_key_result.get_ok()
        return generate_keypair(version, master_key.secret[:32])
        
    except Exception as e:
        logger.error(f"Failed to generate keypair from seed: {e}")
        return IResult.err(IErrorInternal.UnableToGenerateKeypair)