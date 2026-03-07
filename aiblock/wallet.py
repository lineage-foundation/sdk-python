import requests
import json
import base64
import nacl.signing
import time
import hashlib
import os
from typing import Dict, Any, List, Optional, Union, TypeVar, cast, TypedDict, NotRequired
from urllib.parse import urlparse
import nacl.bindings
from mnemonic import Mnemonic
import uuid
import random
import logging
from dataclasses import dataclass, field

from aiblock.interfaces import (
    IErrorInternal, IResult, IMasterKey,
    IKeypair, IKeypairEncrypted, INetworkConfig,
    IClientConfig, INetworkRoute, ITransactionData,
    ITransaction, IBalanceResponse, INewWalletResponse, IMasterKeyEncrypted
)
from aiblock.key_handler import (
    get_passphrase_buffer,
    generate_master_key,
    generate_seed_phrase,
    validate_address,
    generate_keypair,
    construct_address,
    decrypt_keypair,
    generate_keypair_from_seed,
)
from aiblock.validators import validate_metadata
from aiblock.utils import (
    cast_api_status,
)
from aiblock.utils.general_utils import (
    get_random_bytes,
    get_random_string
)
from aiblock.constants import ADDRESS_VERSION, ITEM_DEFAULT, SEED_REGEN_THRES, TEMP_ADDRESS_VERSION
from aiblock.config import get_config, validate_env_config, validate_config
from aiblock.blockchain import BlockchainClient, get_headers as client_get_headers, handle_response as client_handle_response

# Set up logging
logger = logging.getLogger(__name__)

T = TypeVar('T')

class WalletConfig(TypedDict):
    """Wallet configuration type."""
    mempoolHost: NotRequired[str]
    storageHost: NotRequired[str]
    valenceHost: NotRequired[str]
    passphrase: NotRequired[str]

class RouteConfig(TypedDict):
    """Type definition for route configuration.
    
    All fields represent the required proof-of-work difficulty (number of leading zeros)
    for each route. A value of 0 means no proof-of-work is required.
    """
    fetch_balance: int
    create_item_asset: int
    create_transactions: int
    total_supply: int
    issued_supply: int
    transaction_status: int
    debug_data: int

@dataclass
class Wallet:
    """AIBlock wallet implementation.
    
    Attributes:
        debug: Whether to enable debug output
        config: Wallet configuration
        master_key: Master key for the wallet
        current_keypair: Current active keypair
        network_config: Network configuration
        passphrase_key: Passphrase key
        seed_phrase: Seed phrase
        routes_initialized: Whether routes are initialized
    """
    debug: bool = False
    config: Optional[IClientConfig] = None
    master_key: Optional[IMasterKey] = None
    current_keypair: Optional[IKeypair] = None
    network_config: Optional[INetworkConfig] = None
    passphrase_key: Optional[bytes] = None
    seed_phrase: Optional[str] = None
    routes_initialized: bool = False

    def init_new(self, config: Dict[str, str]) -> IResult[None]:
        """Initialize a new wallet instance.
        
        Args:
            config: Configuration dictionary with required keys
            
        Returns:
            IResult[None]: Success or error
        """
        try:
            if not config:
                return IResult.err(IErrorInternal.InvalidParametersProvided, "No configuration provided")

            # Validate config
            config_result = validate_wallet_config(config)
            if config_result.is_err:
                return config_result
        
            validated_config = config_result.get_ok()
            
            # Initialize network routes
            init_result = self.init_network(validated_config)
            if init_result.is_err:
                return init_result
                
            # Generate new keypair if none exists
            if not self.current_keypair:
                self.current_keypair = self.generate_keypair()
                
            return IResult.ok(None)
            
        except Exception as e:
            logger.error(f"Error initializing wallet: {str(e)}")
            return IResult.err(IErrorInternal.UnableToInitializeWallet, str(e))

    def from_master_key(self, master_key: IMasterKey, config: WalletConfig, init_offline: bool = False) -> IResult[bool]:
        """Initialize wallet from an existing master key.
        
        Args:
            master_key: The master key to initialize from
            config: Wallet configuration
            init_offline: Whether to initialize in offline mode
            
        Returns:
            IResult[bool]: Success or failure with error details
        """
        try:
            passphrase_result = get_passphrase_buffer(config.get('passphrase'))
            if passphrase_result.is_err:
                return passphrase_result

            self.passphrase_key = passphrase_result.get_ok()
            self.master_key = master_key
            self.config = config

            if not init_offline:
                init_network_result = self.init_network(config)
                if init_network_result.is_err:
                    return init_network_result

            return IResult.ok(True)
            
        except Exception as e:
            logger.error(f"Error initializing from master key: {str(e)}")
            return IResult.err(IErrorInternal.UnableToInitializeWallet)

    def from_seed(self, seed_phrase: str, config: WalletConfig, init_offline: bool = False) -> IResult[bool]:
        """Initialize wallet from a seed phrase.
        
        Args:
            seed_phrase: The seed phrase to initialize from
            config: Wallet configuration
            init_offline: Whether to initialize in offline mode
            
        Returns:
            IResult[bool]: Success or failure with error details
        """
        try:
            # Validate config first
            print(f"Validating config in from_seed: {config}, init_offline: {init_offline}")  # Debug log
            config_result = validate_wallet_config(config, init_offline)
            if config_result.is_err:
                print(f"Config validation failed: {config_result.error}, {config_result.error_message}")  # Debug log
                return config_result

            # Store the validated config
            self.config = config_result.get_ok()
            print(f"Validated config: {self.config}")  # Debug log

            # Get passphrase buffer (now optional)
            passphrase_result = get_passphrase_buffer(self.config.get('passphrase'))
            if passphrase_result.is_err:
                print(f"Passphrase buffer failed: {passphrase_result.error}, {passphrase_result.error_message}")  # Debug log
                return passphrase_result

            self.passphrase_key = passphrase_result.get_ok()

            # Generate master key with optional passphrase
            master_key_result = generate_master_key(seed_phrase, self.config.get('passphrase'))
            if master_key_result.is_err:
                print(f"Master key generation failed: {master_key_result.error}, {master_key_result.error_message}")  # Debug log
                return master_key_result

            self.master_key = master_key_result.get_ok()
            self.seed_phrase = seed_phrase

            # Initialize the keypair
            keypair_result = generate_keypair_from_seed(seed_phrase, ADDRESS_VERSION)
            if keypair_result.is_err:
                print(f"Keypair generation failed: {keypair_result.error}, {keypair_result.error_message}")  # Debug log
                return keypair_result

            self.current_keypair = keypair_result.get_ok()

            if not init_offline:
                init_result = self.init_network(self.config)
                if init_result.is_err:
                    print(f"Network initialization failed: {init_result.error}, {init_result.error_message}")  # Debug log
                    return init_result

            return IResult.ok(True)

        except Exception as e:
            logger.error(f"Error initializing from seed: {str(e)}")
            return IResult.err(IErrorInternal.UnableToInitializeWallet)

    def init_network(self, config: WalletConfig) -> IResult[bool]:
        """Initialize network connections.
        
        Args:
            config: Configuration dictionary containing host URLs
            
        Returns:
            IResult[bool]: Success or failure with error details
        """
        try:
            logger.debug("Initializing network with config: %s", config)
            self.network_config = config
            
            logger.debug("Hosts - Mempool: %s, Storage: %s, Valence: %s",
                      self.network_config.get('mempoolHost'), self.network_config.get('storageHost'), self.network_config.get('valenceHost'))

            if not self.network_config.get('mempoolHost'):
                return IResult.err(IErrorInternal.UnableToInitializeNetwork)

            # Validate URLs
            for host in [self.network_config.get('mempoolHost'), self.network_config.get('storageHost'), self.network_config.get('valenceHost')]:
                if host and not host.startswith(('http://', 'https://')):
                    return IResult.err(IErrorInternal.UnableToInitializeNetwork)

            # Initialize mempool routes
            logger.debug("Initializing mempool routes...")
            self.routes_initialized = True
            return IResult.ok(True)
            
        except Exception as e:
            logger.error(f"Error initializing network: {str(e)}")
            return IResult.err(IErrorInternal.UnableToInitializeNetwork)

    def _get_default_routes(self) -> RouteConfig:
        """Get default route configuration.
        
        Returns:
            RouteConfig: Default route configuration
        """
        return {
                        'fetch_balance': 0,
                        'create_item_asset': 0,
                        'create_transactions': 0,
                        'total_supply': 0,
                        'issued_supply': 0,
                        'transaction_status': 0,
                        'debug_data': 0
                    }

    def fetch_balance(self, address_list: List[str]) -> IResult[Dict[str, Any]]:
        """Fetch balance for a list of addresses.
        
        Args:
            address_list: List of addresses to fetch balances for
            
        Returns:
            IResult[Dict[str, Any]]: Balance information or error details
        """
        try:
            logger.debug("Fetching balance for addresses: %s", address_list)
            
            # Initialize network if not already initialized
            if not self.routes_initialized:
                logger.debug("Routes not initialized, initializing network...")
                init_result = self.init_network(self.config)
                if init_result.is_err:
                    return init_result
            
            if not address_list:
                return IResult.err(IErrorInternal.InvalidParametersProvided, "No addresses provided")

            # Build headers using shared helper
            headers = client_get_headers()

            # Make request
            url = f"{self.network_config.get('mempoolHost')}/fetch_balance"
            response = requests.post(url, json=address_list, headers=headers, timeout=30)

            # Unified response handling
            result = client_handle_response(response)
            if result.is_err:
                return IResult.err(result.error, result.error_message)
            api_response = result.get_ok()
            return IResult.ok(api_response.get('content'))
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching balance: {str(e)}")
            return IResult.err("Network error while fetching balance")
        except Exception as e:
            logger.error(f"Error fetching balance: {str(e)}")
            return IResult.err("Failed to fetch balance")

    def get_debug_data(self, host: str) -> IResult[Dict[str, Any]]:
        """Get debug data from a host.
        
        Args:
            host: Host URL to get debug data from
            
        Returns:
            IResult[Dict[str, Any]]: Debug data or error
        """
        try:
            # Validate URL
            parsed = urlparse(host)
            if not all([parsed.scheme, parsed.netloc]):
                return IResult.err(IErrorInternal.InvalidParametersProvided)

            headers = client_get_headers()
            response = requests.get(f"{host}/debug_data", headers=headers, timeout=30)
            handled = client_handle_response(response)
            if handled.is_err:
                return IResult.err(handled.error, handled.error_message)
            content = handled.get_ok().get('content')
            return IResult.ok({
                'status': 'success',
                'reason': 'Debug data retrieved successfully',
                'content': {'debugDataResponse': content}
            })
        except Exception as e:
            logger.error(f"Error getting debug data: {str(e)}")
            return IResult.err(IErrorInternal.UnableToGetDebugData)

    def calculate_pow(self, data: Dict[str, Any], difficulty: int = 0) -> IResult[str]:
        """Calculate proof of work for request data.
        
        Args:
            data: Data to calculate proof of work for
            difficulty: Required difficulty (number of leading zeros)
            
        Returns:
            IResult[str]: Proof of work string or error
        """
        try:
            # Convert data to canonical JSON string
            data_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
            
            # Initialize counter
            counter = 0
            max_attempts = 1000000  # Prevent infinite loops
            
            while counter < max_attempts:
                # Create test string with counter
                test_str = f"{data_str}{counter}"
                
                # Calculate hash
                hash_result = hashlib.sha256(test_str.encode()).hexdigest()
                
                # Check if hash meets difficulty requirement
                if hash_result.startswith('0' * difficulty):
                    return IResult.ok(str(counter))
                
                counter += 1
                
            return IResult.err(IErrorInternal.UnableToCalculateProofOfWork)
                
        except Exception as e:
            logger.error(f"Error calculating proof of work: {str(e)}")
            return IResult.err(IErrorInternal.UnableToCalculateProofOfWork)

    def calculate_transaction_hash(self, transaction: Dict[str, Any]) -> IResult[str]:
        """Calculate hash for a transaction.
        
        Args:
            transaction: Transaction data to hash
            
        Returns:
            IResult[str]: Transaction hash or error
        """
        try:
            # Convert transaction to canonical JSON string
            tx_str = json.dumps(transaction, sort_keys=True, separators=(',', ':'))
            
            # Calculate hash
            return IResult.ok(hashlib.sha256(tx_str.encode()).hexdigest())
            
        except Exception as e:
            logger.error(f"Error calculating transaction hash: {str(e)}")
            return IResult.err(IErrorInternal.UnableToCalculateTransactionHash)

    def sign_request(self, data: Any) -> IResult[str]:
        """Sign request data using the master key.
        
        Args:
            data: Data to sign
            
        Returns:
            IResult[str]: Hex encoded signature or error
        """
        try:
            if not self.master_key:
                return IResult.err(IErrorInternal.WalletNotInitialized)
                
            # Convert data to canonical JSON string, handling bytes
            def bytes_handler(obj):
                if isinstance(obj, bytes):
                    return obj.hex()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
                
            data_str = json.dumps(data, sort_keys=True, separators=(',', ':'), default=bytes_handler)
            data_bytes = data_str.encode('utf-8')
            
            # Create signing key from the full master key secret (64 bytes)
            # nacl.signing.SigningKey accepts a 64-byte seed directly
            signing_key = nacl.signing.SigningKey(self.master_key.secret)
            
            # Sign the data
            signature = signing_key.sign(data_bytes).signature
            
            # Return hex encoded signature
            return IResult.ok(signature.hex())
            
        except Exception as e:
            logger.error(f"Error signing request: {str(e)}")
            return IResult.err(IErrorInternal.UnableToSignRequest)

    def get_keypair_for_address(self, address: IKeypair) -> IResult[IKeypair]:
        """Get the keypair for a given address.
        
        Args:
            address: The keypair object
            
        Returns:
            IResult[IKeypair]: The keypair if found or error
        """
        try:
            if not address:
                return IResult.err(IErrorInternal.InvalidParametersProvided)
            return IResult.ok(address)
        except Exception as e:
            logger.error(f"Error getting keypair for address: {str(e)}")
            return IResult.err(IErrorInternal.UnableToGetKeypair)

    def sign_message(self, message: Union[str, bytes]) -> str:
        """Sign a message with the current keypair.
        
        Args:
            message: Message to sign (string or bytes)
            
        Returns:
            str: Signature as a hex string
            
        Raises:
            RuntimeError: If wallet is not initialized
        """
        try:
            if not self.current_keypair:
                raise RuntimeError("Wallet not initialized")

            # Convert message to bytes if needed
            if isinstance(message, str):
                message = message.encode('utf-8')

            # Sign the message
            signing_key = nacl.signing.SigningKey(self.current_keypair.secret_key)
            signature = signing_key.sign(message)
            return signature.signature.hex()

        except Exception as e:
            logger.error(f"Error signing message: {str(e)}")
            raise

    def get_signable_asset_hash(self, data: dict) -> IResult:
        """
        Generate a signable hash for asset creation requests.
        
        Args:
            data (dict): The data to generate a hash from, containing item_amount and metadata.
            
        Returns:
            IResult: The signable hash or an error.
        """
        try:
            if not isinstance(data, dict):
                return IResult.err(
                    IErrorInternal.UnableToGenerateSignableHash,
                    "Data must be a dictionary"
                )
            
            if 'item_amount' not in data or 'metadata' not in data:
                return IResult.err(
                    IErrorInternal.UnableToGenerateSignableHash,
                    "Data must contain item_amount and metadata"
                )
            
            # Ensure item_amount is a number
            try:
                amount = int(data['item_amount'])
            except (TypeError, ValueError):
                return IResult.err(
                    IErrorInternal.UnableToGenerateSignableHash,
                    "item_amount must be convertible to an integer"
                )
            
            # Create signable data
            signable_data = {
                "item_amount": amount,
                "metadata": data['metadata']
            }
            
            # Generate SHA3-256 hash
            hash_object = hashlib.sha3_256()
            hash_object.update(json.dumps(signable_data, sort_keys=True).encode())
            return IResult.ok(hash_object.digest())
        except Exception as e:
            return IResult.err(
                IErrorInternal.UnableToGenerateSignableHash,
                f"Failed to generate signable hash: {str(e)}"
            )

    def get_headers(self) -> Dict[str, str]:
        """Get headers for API requests.
        
        Returns:
            Dict[str, str]: Headers including Content-Type, Accept, Request-ID, and Nonce
        """
        return {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Request-ID': str(uuid.uuid4()),
            'Nonce': get_random_string(32)
        }

    def get_balance(self) -> IResult[Dict[str, Any]]:
        """Get balance for the current address as an IResult for consistency."""
        try:
            if not self.current_keypair:
                return IResult.err(IErrorInternal.WalletNotInitialized, "Wallet not initialized")

            # Initialize network if needed
            if not self.routes_initialized:
                init_result = self.init_network(self.config)
                if init_result.is_err:
                    return IResult.err(IErrorInternal.UnableToInitializeNetwork, init_result.error_message)

            balance_result = self.fetch_balance([self.current_keypair.address])
            if balance_result.is_err:
                return IResult.err(IErrorInternal.UnableToFetchBalance, balance_result.error_message)

            return IResult.ok(balance_result.get_ok())
        except Exception as e:
            logger.error(f"Error getting balance: {str(e)}")
            return IResult.err(IErrorInternal.InternalError, str(e))

    def get_balance_result(self) -> IResult[Dict[str, Any]]:
        """Get balance for the current address as an IResult for consistency.

        Returns:
            IResult[Dict[str, Any]]: Success with balance dict, or error with reason.
        """
        try:
            if not self.current_keypair:
                return IResult.err(IErrorInternal.WalletNotInitialized, "Wallet not initialized")

            # Initialize network if needed
            if not self.routes_initialized:
                init_result = self.init_network(self.config)
                if init_result.is_err:
                    return IResult.err(IErrorInternal.UnableToInitializeNetwork, init_result.error_message)

            balance_result = self.fetch_balance([self.current_keypair.address])
            if balance_result.is_err:
                return IResult.err(IErrorInternal.UnableToFetchBalance, balance_result.error_message)

            return IResult.ok(balance_result.get_ok())
        except Exception as e:
            logger.error(f"Error getting balance: {str(e)}")
            return IResult.err(IErrorInternal.InternalError, str(e))

    def create_item_asset(
        self,
        secret_key: bytes,
        public_key: bytes,
        version: Optional[int],
        amount: int = ITEM_DEFAULT,
        default_genesis_hash: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> IResult:
        """Create item assets payload and send to mempool. Matches JS SDK's createItemPayload logic.

        Args:
            secret_key (bytes): The 64-byte secret key (signing key seed).
            public_key (bytes): The public key bytes.
            version (Optional[int]): The address version associated with the keys.
            amount (int, optional): Amount of items to create. Defaults to ITEM_DEFAULT.
            default_genesis_hash (bool, optional): Whether to use default genesis hash spec. Defaults to True.
            metadata (Optional[Dict[str, Any]], optional): Optional metadata dictionary. Defaults to None.

        Returns:
            IResult: Result of the operation, containing API response content on success.
        """
        try:
            # 1. Validate Inputs & Derive Address
            logger.debug(f"create_item_asset received secret_key length: {len(secret_key) if secret_key else 'None'}") # Log length
            if not secret_key:
                 logger.error("Invalid secret_key provided (must not be empty)")
                 return IResult.err(IErrorInternal.InvalidKeypairProvided, "Invalid secret_key")

            logger.debug(f"create_item_asset received public_key length: {len(public_key) if public_key else 'None'}") # Log length
            if not public_key or len(public_key) != 32:
                 logger.error("Invalid public_key provided (must be 32 bytes)")
                 return IResult.err(IErrorInternal.InvalidKeypairProvided, "Invalid public_key")

            if version is None: # Explicitly require version now, matching JS createItemPayload needs
                 logger.error("Address version must be provided")
                 return IResult.err(IErrorInternal.InvalidParametersProvided, "Address version is required")

            # Derive address from public key and version
            address_result = construct_address(public_key, version)
            if address_result.is_err:
                logger.error("Failed to construct address from public key and version: %s", address_result.error_message)
                return IResult.err(IErrorInternal.UnableToConstructDefaultAddress, address_result.error_message)
            address = address_result.get_ok()
            logger.debug(f"Using derived address: {address} for version: {version}")

            # 2. Validate Metadata
            if metadata:
                if not isinstance(metadata, dict):
                    logger.error("Invalid metadata format provided (not a dict)")
                    return IResult.err(IErrorInternal.InvalidMetadataFormat, "Metadata must be a dictionary")

                metadata_result = validate_metadata(metadata)
                if metadata_result.is_err:
                     logger.error("Metadata validation failed: %s", metadata_result.error_message)
                     return IResult.err(IErrorInternal.InvalidMetadataFormat, metadata_result.error_message)
            else:
                metadata = {} # Ensure metadata is always a dict for hashing

            # 3. Check Network Initialization
            if not self.network_config.get('mempoolHost'):
                logger.error("Network not initialized (mempoolHost missing)")
                return IResult.err(IErrorInternal.NetworkNotInitialized)

            # 4. Prepare Data for Hashing (Match JS SDK 'asset' structure for hash)
            asset_data_for_hash = {
            "item_amount": amount,
                "metadata": metadata # Use the validated or default metadata dict
            }

            # 5. Generate Signable Hash (of amount and metadata)
            signable_hash_result = self.get_signable_asset_hash(asset_data_for_hash)
            if signable_hash_result.is_err:
                logger.error("Failed to generate signable asset hash: %s", signable_hash_result.error_message)
                return IResult.err(IErrorInternal.UnableToGenerateSignableHash, signable_hash_result.error_message)
            signable_hash_bytes = signable_hash_result.get_ok() # Should be bytes

            # 6. Sign the Hash using the provided 32-byte secret key (seed)
            try:
                # Initialize SigningKey from the 32-byte seed stored in IKeypair.secret_key
                signing_key = nacl.signing.SigningKey(seed=secret_key) # Ensure seed= is used
                signature_bytes = signing_key.sign(signable_hash_bytes).signature
                signature_hex = signature_bytes.hex()
                logger.debug("Successfully signed asset hash. Signature: %s", signature_hex)
            except Exception as sign_err:
                logger.error("Failed to sign asset hash: %s", str(sign_err))
                return IResult.err(IErrorInternal.UnableToSignMessage, f"Failed to sign asset hash: {str(sign_err)}")

            # 7. Construct Final API Payload (Match JS SDK's createItemPayload return structure)
            public_key_hex = public_key.hex() # Already have bytes
            genesis_hash_spec_value = "Default" if default_genesis_hash else "Create"

            request_data = {
                "item_amount": amount,
                "script_public_key": address, # Use derived address
                "public_key": public_key_hex,
                "signature": signature_hex,
                "version": version, # Use provided version
                "genesis_hash_spec": genesis_hash_spec_value,
                "metadata": metadata if metadata else None # Send original metadata (or null if it was None)
            }
            logger.debug("Constructed API request payload: %s", json.dumps(request_data, indent=2))

            # 8. Get Headers & Make Request
            headers = client_get_headers()
            logger.debug("Request Headers: %s", headers)
            api_endpoint = f"{self.network_config.get('mempoolHost')}/create_item_asset"
            logger.info("Sending POST request to %s", api_endpoint)

            try:
                response = requests.post(api_endpoint, json=request_data, headers=headers, timeout=10)
                logger.debug("Received response status code: %s", response.status_code)
                logger.debug("Received response body: %s", response.text)
            except requests.exceptions.RequestException as e:
                logger.error("Network request failed: %s", str(e))
                return IResult.err(IErrorInternal.NetworkError, str(e))

            # 9. Handle response using shared handler
            handled = client_handle_response(response)
            if handled.is_err:
                return IResult.err(handled.error, handled.error_message)
            logger.info("create_item_asset successful.")
            return IResult.ok(handled.get_ok().get('content'))

        except Exception as e:
            logger.error(f"Unexpected error in create_item_asset: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return IResult.err(IErrorInternal.InternalError, str(e))

    def create_transactions(self, destination_address: str, amount: int) -> IResult[ITransaction]:
        """Create a new transaction.
        
        Args:
            destination_address: Destination address
            amount: Amount to transfer
            
        Returns:
            IResult[ITransaction]: Transaction or error
        """
        try:
            if not self.current_keypair:
                return IResult.err(IErrorInternal.WalletNotInitialized)

            # Get current balance
            balance_result = self.fetch_balance([self.current_keypair.address])
            if balance_result.is_err:
                return IResult.err(IErrorInternal.UnableToFetchBalance)

            balance = balance_result.get_ok()
            if balance['total']['tokens'] < amount:
                return IResult.err(IErrorInternal.InsufficientFunds)

            # Create transaction data
            tx_data = ITransactionData(
                timestamp=int(time.time() * 1000),
                sender=self.current_keypair.address,
                receiver=destination_address,
                amount=amount,
                fee=0,  # Fee calculation should be implemented
                metadata={
                    "action": "transfer",
                    "app": "wallet",
                    "data": {}
                }
            )

            # Sign transaction
            signature_result = self.sign_request(tx_data)
            if signature_result.is_err:
                return signature_result

            transaction = ITransaction(
                data=tx_data,
                signature=signature_result.get_ok()
            )

            return IResult.ok(transaction)

        except Exception as e:
            logger.error("Error creating transaction: %s", str(e))
            return IResult.err(IErrorInternal.InternalError)

    def generate_seed_phrase(self) -> str:
        """Generate a new seed phrase.
        
        Returns:
            str: Generated seed phrase
        """
        try:
            mnemo = Mnemonic("english")
            return mnemo.generate(strength=128)
        except Exception as e:
            logger.error("Error generating seed phrase: %s", str(e))
            raise ValueError("Failed to generate seed phrase") from e

    def init_from_seed(self, seed_phrase: str, config: IClientConfig) -> IResult[None]:
        """Initialize wallet from a seed phrase.
        
        Args:
            seed_phrase: The seed phrase
            config: Wallet configuration
            
        Returns:
            IResult[None]: Success or error
        """
        try:
            mnemo = Mnemonic("english")
            if not mnemo.check(seed_phrase):
                return IResult.err(IErrorInternal.InvalidSeedPhrase)
            
            master_key_result = generate_master_key(seed_phrase)
            if master_key_result.is_err:
                return master_key_result
                
            self.master_key = master_key_result.get_ok()
            self.config = config
            self.seed_phrase = seed_phrase
            
            init_result = self.init_network(config)
            if init_result.is_err:
                return init_result
                
            return IResult.ok(None)
            
        except Exception as e:
            logger.error("Error initializing from seed: %s", str(e))
            return IResult.err(IErrorInternal.UnableToInitializeWallet)

    def generate_keypair(self) -> IResult[IKeypair]:
        """Generate a new keypair.
        
        Returns:
            IResult[IKeypair]: Generated keypair or error
        """
        try:
            # Generate a new keypair
            signing_key = nacl.signing.SigningKey.generate()
            verify_key = signing_key.verify_key

            # Get the keys as bytes
            secret_key = signing_key.encode()
            public_key = verify_key.encode()

            # Generate address from public key
            address = hashlib.sha3_256(public_key).hexdigest()

            # Create keypair
            keypair = IKeypair(
                address=address,
                public_key=public_key,
                secret_key=secret_key,
                version=ADDRESS_VERSION
            )
            
            self.current_keypair = keypair
            return IResult.ok(keypair)
            
        except Exception as e:
            logger.error("Error generating keypair: %s", str(e))
            return IResult.err(IErrorInternal.UnableToGenerateKeypair)

    def decrypt_keypair(self, keypair: IKeypairEncrypted) -> IResult[IKeypair]:
        """Decrypt an encrypted keypair.
        
        Args:
            keypair: Encrypted keypair
            
        Returns:
            IResult[IKeypair]: Decrypted keypair or error
        """
        try:
            if not self.config:
                return IResult.err(IErrorInternal.WalletNotInitialized)
                
            if not self.passphrase_key:
                return IResult.err(IErrorInternal.NoPassPhraseProvided)
            
            decrypted_result = decrypt_keypair(keypair, self.passphrase_key)
            if decrypted_result.is_err:
                return decrypted_result
                
            return IResult.ok(decrypted_result.get_ok())
            
        except Exception as e:
            logger.error("Error decrypting keypair: %s", str(e))
            return IResult.err(IErrorInternal.UnableToDecryptKeypair)

    def generate_nonce(self) -> IResult[str]:
        """Generate a random nonce for requests.
        
        Returns:
            IResult[str]: Hex encoded nonce or error
        """
        try:
            # Generate 24 random bytes
            nonce_bytes = nacl.utils.random(24)
            # Return hex encoded nonce
            return IResult.ok(nonce_bytes.hex())
        except Exception as e:
            logger.error("Error generating nonce: %s", str(e))
            return IResult.err(IErrorInternal.InternalError)

    def encrypt_keypair(self, keypair: IKeypair, passphrase: bytes) -> IResult[IKeypairEncrypted]:
        """Encrypt a keypair using a passphrase.
        
        Args:
            keypair: The keypair to encrypt
            passphrase: The passphrase to use for encryption
            
        Returns:
            IResult[IKeypairEncrypted]: The encrypted keypair or error
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
                nonce=base64.b64encode(encrypted.nonce).decode('utf-8'),
                save=base64.b64encode(encrypted.ciphertext).decode('utf-8')
            )
            
            return IResult.ok(IKeypairEncrypted(
                master_key=master_key,
                version=keypair.version
            ))
        except Exception as e:
            logger.error("Error encrypting keypair: %s", str(e))
            return IResult.err(IErrorInternal.UnableToEncryptKeypair)

    def _serialize_keypair(self, keypair):
        """Convert keypair dict or IKeypair to a JSON-serializable dict with hex-encoded keys."""
        if hasattr(keypair, '__dict__'):
            keypair = keypair.__dict__
        return {
            'address': keypair['address'],
            'public_key': keypair['public_key'].hex() if isinstance(keypair['public_key'], bytes) else keypair['public_key'],
            'secret_key': keypair['secret_key'].hex() if isinstance(keypair['secret_key'], bytes) else keypair['secret_key'],
            'version': keypair['version']
        }

    def make_2way_payment(
        self,
        payment_address: str,
        sending_asset: dict,
        receiving_asset: dict,
        all_keypairs: list,
        receive_address: dict,
    ) -> IResult:
        try:
            # 1. Decrypt the receiving keypair
            receiver_keypair_result = self.decrypt_keypair(receive_address)
            if receiver_keypair_result.is_err:
                return receiver_keypair_result
            receiver_keypair = receiver_keypair_result.get_ok()

            # 2. Get all addresses and keypair map
            all_addresses, keypair_map = self.get_all_addresses_and_keypair_map(all_keypairs)

            # 3. Fetch balance
            balance_result = self.fetch_balance(all_addresses)
            if balance_result.is_err:
                return balance_result
            balance = balance_result.get_ok()

            # 4. Generate DRUID
            druid = self.generate_druid()

            # 5. Construct sender/receiver expectations
            sender_expectation = {
                "from": "",
                "to": receiver_keypair.address,
                "asset": receiving_asset,
            }
            receiver_expectation = {
                "from": "",
                "to": payment_address,
                "asset": sending_asset,
            }

            # 6. Create the half-transaction
            send_2w_tx_half = self.create_2w_tx_half(
                balance, druid, sender_expectation, receiver_expectation, receiver_keypair.address, keypair_map
            )

            # 7. Encrypt the transaction (JS SDK: sender = wallet user, receiver = counterparty)
            # sender_keypair: the wallet user's keypair (self.current_keypair)
            # receiver_public_key: the counterparty's public key (receiver_keypair.public_key)
            encrypted_tx = self.encrypt_transaction(
                send_2w_tx_half["createTx"],
                sender_keypair=self.current_keypair,
                receiver_public_key=receiver_keypair.public_key
            )

            # 8. Prepare payload for valence node
            receiver_expectation["from"] = self.construct_tx_ins_address(send_2w_tx_half["createTx"]["inputs"])
            value_payload = {
                "druid": druid,
                "senderExpectation": sender_expectation,
                "receiverExpectation": receiver_expectation,
                "status": "pending",
                "mempoolHost": self.network_config.get("mempoolHost"),
            }
            send_body = self.generate_valence_set_body(payment_address, value_payload, druid)
            send_headers = self.generate_verification_headers(payment_address, receiver_keypair, value_payload)

            # 9. POST to valence node
            valence_host = self.network_config.get("valenceHost")
            response = requests.post(f"{valence_host}/valence_set", json=send_body, headers=send_headers, timeout=30)
            handled = client_handle_response(response)
            if handled.is_err:
                return IResult.err(handled.error, handled.error_message)

            # 10. Return DRUID and encrypted transaction
            return IResult.ok({"druid": druid, "encryptedTx": encrypted_tx})

        except Exception as e:
            logger.error(f"Error in make_2way_payment: {str(e)}")
            return IResult.err(IErrorInternal.InternalError, str(e))

    def select_utxos_for_2way(self, balance, asset, address):
        """
        Port of JS selectUtxosFor2Way.
        Returns (utxos, change).
        """
        asset_type = next(iter(asset.keys()))
        asset_amount = next(iter(asset.values()))
        utxos = []
        total = 0
        for utxo in balance.get("utxos", []):
            if (
                utxo.get("assetType") == asset_type
                and utxo.get("address") == address
            ):
                utxos.append(utxo)
                total += utxo.get("amount", 0)
                if total >= asset_amount:
                    break
        if total < asset_amount:
            raise ValueError("Insufficient UTXOs for 2WayPayment.")
        change = total - asset_amount
        return utxos, change

    def sign_transaction(self, tx, keypair):
        """
        1:1 port of JS signTransaction for 2WayPayment.
        Signs each input with the sender's keypair using Ed25519 (nacl).
        Returns a list of hex signatures (one per input).
        """
        import nacl.signing
        import json
        signatures = []
        # Prepare the message to sign for each input (can be the tx minus signatures field)
        tx_copy = dict(tx)
        tx_copy.pop('signatures', None)
        # Canonical JSON encoding
        tx_bytes = json.dumps(tx_copy, sort_keys=True, separators=(",", ":")).encode()
        signing_key = nacl.signing.SigningKey(keypair['secret_key'] if isinstance(keypair, dict) else keypair.secret_key)
        for _ in tx['inputs']:
            sig = signing_key.sign(tx_bytes).signature.hex()
            signatures.append(sig)
        return signatures

    def create_2w_tx_half(
        self,
        balance: dict,
        druid: str,
        sender_expectation: dict,
        receiver_expectation: dict,
        address: str,
        keypair_map: dict,
    ) -> dict:
        """
        1:1 port of JS SDK's create2WTxHalf for 2WayPayment.
        """
        # 1. Select UTXOs to cover the asset being sent
        utxos, change = self.select_utxos_for_2way(
            balance, receiver_expectation['asset'], address
        )
        # 2. Build transaction inputs
        inputs = [
            {
                "txid": utxo["txid"],
                "vout": utxo["vout"],
                "address": utxo["address"],
                "assetType": utxo["assetType"],
                "amount": utxo["amount"],
            }
            for utxo in utxos
        ]
        # 3. Build transaction outputs
        asset_type = next(iter(receiver_expectation['asset'].keys()))
        asset_amount = next(iter(receiver_expectation['asset'].values()))
        outputs = [
            {
                "address": receiver_expectation["to"],
                "assetType": asset_type,
                "amount": asset_amount,
            }
        ]
        if change > 0:
            outputs.append({
                "address": address,
                "assetType": asset_type,
                "amount": change,
            })
        # 4. Attach DRUID and expectations
        druid_info = {
            "druid": druid,
            "senderExpectation": sender_expectation,
            "receiverExpectation": receiver_expectation,
        }
        # 5. Build the transaction object
        tx = {
            "inputs": inputs,
            "outputs": outputs,
            "druidInfo": druid_info,
            "timestamp": int(time.time() * 1000),
            "version": 1,
        }
        # 6. Sign the transaction
        sender_keypair = keypair_map[address]
        tx["signatures"] = self.sign_transaction(tx, sender_keypair)
        return {"createTx": tx}

    def encrypt_transaction(self, tx, sender_keypair=None, receiver_public_key=None):
        """
        Port of JS SDK's encryptTransaction.
        Encrypts the transaction object using NaCl Box (asymmetric, shared secret between sender and receiver).
        Returns base64-encoded ciphertext and nonce.
        """
        import nacl.public
        import nacl.utils
        import base64
        import json

        if sender_keypair is None or receiver_public_key is None:
            raise ValueError("Both sender_keypair and receiver_public_key are required for encryption.")

        # Serialize tx to canonical JSON
        tx_bytes = json.dumps(tx, sort_keys=True, separators=(",", ":")).encode()

        # Prepare keys
        sender_private = nacl.public.PrivateKey(sender_keypair['secret_key'] if isinstance(sender_keypair, dict) else sender_keypair.secret_key)
        receiver_pub = nacl.public.PublicKey(receiver_public_key)
        box = nacl.public.Box(sender_private, receiver_pub)
        nonce = nacl.utils.random(nacl.public.Box.NONCE_SIZE)
        encrypted = box.encrypt(tx_bytes, nonce)
        return {
            "ciphertext": base64.b64encode(encrypted.ciphertext).decode(),
            "nonce": base64.b64encode(nonce).decode(),
        }

    def generate_druid(self):
        """Generate a unique DRUID (transaction identifier), matching JS SDK's getNewDRUID."""
        import uuid
        return f"DRUID{uuid.uuid4().hex}"

    def generate_valence_set_body(self, payment_address, value_payload, druid):
        """Build the payload for the valence node's /valence_set endpoint, matching JS SDK's generateValenceSetBody."""
        return {
            "address": payment_address,
            "value": value_payload,
            "druid": druid
        }

    def generate_verification_headers(self, payment_address, sender_keypair, payload=None):
        """
        Port of JS SDK's generateVerificationHeaders.
        Signs the canonical JSON of the payload/body.
        Returns headers: x-signature, x-public-key.
        """
        import json
        import base64
        import nacl.signing

        if payload is None:
            payload = {}

        # Canonical JSON
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        signing_key = nacl.signing.SigningKey(sender_keypair['secret_key'] if isinstance(sender_keypair, dict) else sender_keypair.secret_key)
        signature = signing_key.sign(payload_bytes).signature

        return {
            "x-signature": base64.b64encode(signature).decode(),
            "x-public-key": base64.b64encode(signing_key.verify_key.encode()).decode(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def construct_tx_ins_address(self, inputs):
        """
        Port of JS SDK's constructTxInsAddress.
        Concatenates all input addresses, comma-separated.
        """
        return ",".join(str(inp["address"]) for inp in inputs)

    def get_all_addresses_and_keypair_map(self, all_keypairs):
        """Get all addresses and a mapping from address to keypair, matching JS SDK's getAllAddressesAndKeypairMap."""
        addresses = []
        keypair_map = {}
        for kp in all_keypairs:
            addr = kp['address'] if isinstance(kp, dict) else kp.address
            addresses.append(addr)
            keypair_map[addr] = kp
        return addresses, keypair_map

    def fetch_pending_2way_payments(self, all_keypairs, encrypted_tx_list):
        """
        Fetch and decrypt pending 2WayPayments from the valence node.
        Mirrors JS SDK's fetchPending2WayPayments.
        """
        import requests
        import base64
        import nacl.public
        import json

        valence_host = self.network_config.get("valenceHost")
        headers = client_get_headers()
        response = requests.post(f"{valence_host}/fetch_pending_2way_payments", json={"encryptedTxList": encrypted_tx_list}, headers=headers, timeout=30)
        handled = client_handle_response(response)
        if handled.is_err:
            return IResult.err(handled.error, handled.error_message)
        result = handled.get_ok()
        pending = result.get("content", {}).get("pending", {})
        # Decrypt each pending tx
        decrypted = {}
        for druid, tx_info in pending.items():
            enc = tx_info.get("encryptedTx")
            nonce = base64.b64decode(enc["nonce"])
            ciphertext = base64.b64decode(enc["ciphertext"])
            # Find matching keypair
            for kp in all_keypairs:
                try:
                    private_key = nacl.public.PrivateKey(kp['secret_key'] if isinstance(kp, dict) else kp.secret_key)
                    # Assume sender's public key is provided in tx_info
                    sender_pub = nacl.public.PublicKey(base64.b64decode(tx_info["senderPublicKey"]))
                    box = nacl.public.Box(private_key, sender_pub)
                    tx_bytes = box.decrypt(ciphertext, nonce)
                    tx = json.loads(tx_bytes.decode())
                    decrypted[druid] = tx
                    break
                except Exception:
                    continue
        return IResult.ok({"pending": decrypted})

    def accept_2way_payment(self, druid, pending_dict, all_keypairs):
        """
        Accept a pending 2WayPayment: decrypt, merge, sign, and submit the merged transaction.
        Mirrors JS SDK's accept2WayPayment.
        """
        import requests
        import json
        # 1. Get the pending half-tx
        half_tx = pending_dict[druid]
        # 2. Find our keypair
        my_address = half_tx['outputs'][0]['address']
        my_keypair = None
        for kp in all_keypairs:
            if (kp['address'] if isinstance(kp, dict) else kp.address) == my_address:
                my_keypair = kp
                break
        if my_keypair is None:
            return IResult.err(IErrorInternal.InvalidParametersProvided, "No matching keypair for acceptance.")
        # 3. Construct our own half-tx
        # (Assume we have the same expectations as the counterparty, swap sender/receiver)
        sender_expectation = half_tx['druidInfo']['receiverExpectation']
        receiver_expectation = half_tx['druidInfo']['senderExpectation']
        balance = self.fetch_balance([my_address]).get_ok()
        keypair_map = {kp['address'] if isinstance(kp, dict) else kp.address: kp for kp in all_keypairs}
        my_half = self.create_2w_tx_half(balance, druid, sender_expectation, receiver_expectation, my_address, keypair_map)["createTx"]
        # 4. Merge both halves (inputs + outputs + druidInfo)
        merged_tx = {
            "inputs": half_tx["inputs"] + my_half["inputs"],
            "outputs": half_tx["outputs"] + my_half["outputs"],
            "druidInfo": half_tx["druidInfo"],
            "timestamp": int(time.time() * 1000),
            "version": 1,
        }
        # 5. Sign merged tx with both keypairs
        merged_tx["signatures"] = self.sign_transaction(merged_tx, my_keypair)
        # 6. Submit to valence node
        valence_host = self.network_config.get("valenceHost")
        headers = client_get_headers()
        response = requests.post(f"{valence_host}/accept_2way_payment", json={"druid": druid, "mergedTx": merged_tx}, headers=headers, timeout=30)
        handled = client_handle_response(response)
        if handled.is_err:
            return IResult.err(handled.error, handled.error_message)
        return IResult.ok(handled.get_ok().get("content"))

    def reject_2way_payment(self, druid, pending_dict, all_keypairs):
        """
        Reject a pending 2WayPayment by updating its status to 'rejected' on the valence node.
        Mirrors JS SDK's reject2WayPayment.
        """
        import requests
        valence_host = self.network_config.get("valenceHost")
        headers = client_get_headers()
        response = requests.post(f"{valence_host}/reject_2way_payment", json={"druid": druid}, headers=headers, timeout=30)
        handled = client_handle_response(response)
        if handled.is_err:
            return IResult.err(handled.error, handled.error_message)
        return IResult.ok(handled.get_ok().get("content"))

def validate_wallet_config(config: Dict[str, Any], init_offline: bool = False) -> IResult[WalletConfig]:
    """Validate wallet configuration.
    
    Args:
        config: Configuration dictionary to validate
        init_offline: Whether to initialize in offline mode
        
    Returns:
        IResult[WalletConfig]: Validated configuration or error
    """
    try:
        if not config:
            return IResult.err(IErrorInternal.InvalidParametersProvided, "No configuration provided")

        # In offline mode, passphrase is optional
        if init_offline:
            wallet_config: WalletConfig = {'passphrase': config.get('passphrase', '')}
            return IResult.ok(wallet_config)

        # Check required fields for online mode
        if not isinstance(config.get('mempoolHost'), str):
            return IResult.err(IErrorInternal.InvalidParametersProvided, "Missing or invalid mempoolHost")
            
        # Validate URLs
        for host_key in ['mempoolHost', 'storageHost', 'valenceHost']:
            if host := config.get(host_key):
                if not isinstance(host, str):
                    return IResult.err(IErrorInternal.InvalidParametersProvided, f"Invalid {host_key}")
                parsed = urlparse(host)
                if not all([parsed.scheme, parsed.netloc]):
                    return IResult.err(IErrorInternal.InvalidParametersProvided, f"Invalid URL for {host_key}")
                    
        # Cast to WalletConfig type with optional passphrase
        wallet_config: WalletConfig = {
            'passphrase': config.get('passphrase', ''),  # Default to empty string if not provided
            'mempoolHost': config['mempoolHost']
        }
        
        # Add optional hosts if provided
        if storage_host := config.get('storageHost'):
            wallet_config['storageHost'] = storage_host
        if valence_host := config.get('valenceHost'):
            wallet_config['valenceHost'] = valence_host
            
        return IResult.ok(wallet_config)
    except Exception as e:
        return IResult.err(IErrorInternal.InvalidParametersProvided, str(e))

# You can add additional methods following the same pattern, adjusting them according to your needs
