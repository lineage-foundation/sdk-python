import requests
import json
import base64
import nacl.signing
import time
import hashlib
import os
from typing import Dict, Any, List, Optional, Union, TypeVar, cast, TypedDict
from typing_extensions import NotRequired
from urllib.parse import urlparse
import nacl.bindings
from mnemonic import Mnemonic
import uuid
import random
import logging
from dataclasses import dataclass, field

from lineage.interfaces import (
    IErrorInternal, IResult, IMasterKey,
    IKeypair, IKeypairEncrypted, INetworkConfig,
    IClientConfig, INetworkRoute,
    IBalanceResponse, INewWalletResponse, IMasterKeyEncrypted
)
from lineage.transaction import (
    construct_tx_in_signable_asset_hash,
    construct_signature as tx_construct_signature,
    create_payment_tx,
    create_2w_tx_half as tx_create_2w_tx_half,
    construct_tx_ins_address as tx_construct_tx_ins_address,
)
from lineage.key_handler import (
    get_passphrase_buffer,
    generate_master_key,
    generate_seed_phrase,
    validate_address,
    generate_keypair,
    construct_address,
    decrypt_keypair,
    generate_keypair_from_seed,
    generate_druid,
)
from lineage.validators import validate_metadata
from lineage.utils import (
    cast_api_status,
)
from lineage.utils.general_utils import (
    get_random_bytes,
)
from lineage.constants import ADDRESS_VERSION, ITEM_DEFAULT, SEED_REGEN_THRES, TEMP_ADDRESS_VERSION
from lineage.config import get_config, validate_env_config, validate_config
from lineage.blockchain import BlockchainClient, get_headers as client_get_headers, handle_response as client_handle_response
from lineage.valence import ValenceClient
import nacl.secret

# Set up logging
logger = logging.getLogger(__name__)

T = TypeVar('T')

class WalletConfig(TypedDict):
    """Wallet configuration type."""
    mempoolHost: NotRequired[str]
    storageHost: NotRequired[str]
    valenceHost: NotRequired[str]
    passphrase: NotRequired[str]
    apiKey: NotRequired[str]

@dataclass
class Wallet:
    """Lineage wallet implementation.
    
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
            headers = client_get_headers(self.network_config.get('apiKey'))

            # Make request
            url = f"{self.network_config.get('mempoolHost')}/v1/balances/query"
            response = requests.post(url, json={'addresses': address_list}, headers=headers, timeout=30)

            # Unified response handling
            result = client_handle_response(response)
            if result.is_err:
                return IResult.err(result.error, result.error_message)
            api_response = result.get_ok()
            return IResult.ok(api_response.get('balance'))
            
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
        version: Optional[int] = ADDRESS_VERSION,
        amount: int = ITEM_DEFAULT,
        default_genesis_hash: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> IResult:
        """Create an item asset via `POST /v1/items`. Matches sdk-js's `createItemPayload`.

        The signature is produced exactly as `lineage/transaction.py`'s
        `construct_tx_in_signable_asset_hash` + `construct_signature` do
        (golden-vector-verified against sdk-js) - the preimage is the plain
        string `Item:<amount>`, deliberately excluding `genesis_hash` and
        `metadata`. The legacy `version` field is not sent on the wire.

        Args:
            secret_key (bytes): The 32-byte ed25519 seed (signing key).
            public_key (bytes): The public key bytes.
            version (Optional[int]): The address version to derive `script_public_key`
                with. Defaults to this SDK's `ADDRESS_VERSION` (the default/latest
                address, matching sdk-js's `null`).
            amount (int, optional): Amount of items to create. Defaults to ITEM_DEFAULT.
            default_genesis_hash (bool, optional): Whether to use default genesis hash spec. Defaults to True.
            metadata (Optional[Dict[str, Any]], optional): Optional metadata dictionary. Defaults to None.

        Returns:
            IResult: `{asset, to_address, tx_hash}` on success, or an error result.
        """
        try:
            # 1. Validate Inputs & Derive Address
            if not secret_key:
                 logger.error("Invalid secret_key provided (must not be empty)")
                 return IResult.err(IErrorInternal.InvalidKeypairProvided, "Invalid secret_key")

            if not public_key or len(public_key) != 32:
                 logger.error("Invalid public_key provided (must be 32 bytes)")
                 return IResult.err(IErrorInternal.InvalidKeypairProvided, "Invalid public_key")

            if version is None:
                 logger.error("Address version must be provided")
                 return IResult.err(IErrorInternal.InvalidParametersProvided, "Address version is required")

            # Derive address from public key and version
            address_result = construct_address(public_key, version)
            if address_result.is_err:
                logger.error("Failed to construct address from public key and version: %s", address_result.error_message)
                return IResult.err(IErrorInternal.UnableToConstructDefaultAddress, address_result.error_message)
            address = address_result.get_ok()

            # 2. Validate Metadata
            if metadata:
                if not isinstance(metadata, dict):
                    logger.error("Invalid metadata format provided (not a dict)")
                    return IResult.err(IErrorInternal.InvalidMetadataFormat, "Metadata must be a dictionary")

                metadata_result = validate_metadata(metadata)
                if metadata_result.is_err:
                     logger.error("Metadata validation failed: %s", metadata_result.error_message)
                     return IResult.err(IErrorInternal.InvalidMetadataFormat, metadata_result.error_message)

            # 3. Check Network Initialization
            if not self.network_config or not self.network_config.get('mempoolHost'):
                logger.error("Network not initialized (mempoolHost missing)")
                return IResult.err(IErrorInternal.NetworkNotInitialized)

            # 4. Sign the asset hash (Item:<amount>, matching transaction.py/sdk-js exactly)
            asset_hash = construct_tx_in_signable_asset_hash({'Item': {'amount': amount}})
            try:
                signature_hex = tx_construct_signature(asset_hash, secret_key)
            except Exception as sign_err:
                logger.error("Failed to sign asset hash: %s", str(sign_err))
                return IResult.err(IErrorInternal.UnableToSignMessage, f"Failed to sign asset hash: {str(sign_err)}")

            # 5. Construct Final API Payload - no `version` field on the wire.
            request_data = {
                "item_amount": amount,
                "genesis_hash_spec": "Default" if default_genesis_hash else "Create",
                "metadata": json.dumps(metadata) if metadata else None,
                "script_public_key": address,
                "public_key": public_key.hex(),
                "signature": signature_hex,
            }

            # 6. Get Headers & Make Request
            headers = client_get_headers(self.network_config.get('apiKey'))
            api_endpoint = f"{self.network_config.get('mempoolHost')}/v1/items"
            logger.info("Sending POST request to %s", api_endpoint)

            try:
                response = requests.post(api_endpoint, json=request_data, headers=headers, timeout=10)
            except requests.exceptions.RequestException as e:
                logger.error("Network request failed: %s", str(e))
                return IResult.err(IErrorInternal.NetworkError, str(e))

            # 7. Handle response using shared handler
            handled = client_handle_response(response)
            if handled.is_err:
                return IResult.err(handled.error, handled.error_message)
            logger.info("create_item_asset successful.")
            return IResult.ok(handled.get_ok())

        except Exception as e:
            logger.error(f"Unexpected error in create_item_asset: {str(e)}")
            return IResult.err(IErrorInternal.InternalError, str(e))

    def create_transactions(
        self,
        destination_address: str,
        amount: int,
        all_keypairs: Optional[List[IKeypair]] = None,
        excess_keypair: Optional[IKeypair] = None,
        locktime: int = 0,
    ) -> IResult[Dict[str, Any]]:
        """Make a client-signed token payment via `POST /v1/transactions`.

        Matches sdk-js's `makeTokenPayment`/`makePayment`: fetches the
        latest balance for `all_keypairs`' addresses, builds and signs the
        UTXO `CreateTransaction` with `lineage/transaction.py`'s
        `create_payment_tx` (golden-vector-verified against sdk-js), then
        submits it. `fees: null` is added to the wire body only - it is
        never part of the signed structure.

        Args:
            destination_address: Address to pay.
            amount: Token amount to pay (int).
            all_keypairs: Keypairs whose UTXOs may be spent as inputs.
                Defaults to `[self.current_keypair]` for a plain
                single-address wallet.
            excess_keypair: Keypair to receive any change/excess output.
                Defaults to `self.current_keypair`.
            locktime: Locktime for the payment output. Defaults to 0.

        Returns:
            IResult[Dict[str, Any]]: `{transaction_hash, payment_address,
            asset, used_addresses}` on success, or an error result.
        """
        try:
            if not self.current_keypair:
                return IResult.err(IErrorInternal.WalletNotInitialized)

            if all_keypairs is None:
                all_keypairs = [self.current_keypair]
            if not all_keypairs:
                return IResult.err(IErrorInternal.InvalidParametersProvided, "No keypairs provided")

            if excess_keypair is None:
                excess_keypair = self.current_keypair

            all_addresses = [keypair.address for keypair in all_keypairs]
            keypair_map = {keypair.address: keypair for keypair in all_keypairs}

            # Get current balance for the spending addresses
            balance_result = self.fetch_balance(all_addresses)
            if balance_result.is_err:
                return IResult.err(balance_result.error, balance_result.error_message)
            balance = balance_result.get_ok()

            payment_asset = {'Token': amount}

            try:
                payment_body = create_payment_tx(
                    destination_address,
                    payment_asset,
                    excess_keypair.address,
                    balance,
                    keypair_map,
                    locktime,
                )
            except ValueError as e:
                if str(e) == 'InsufficientFunds':
                    return IResult.err(IErrorInternal.InsufficientFunds, str(e))
                return IResult.err(IErrorInternal.InvalidParametersProvided, str(e))

            create_tx = payment_body['create_tx']
            used_addresses = payment_body['used_addresses']

            # `fees` isn't part of the signed transaction - it's an explicit
            # (nullable) field required by the `/v1/transactions` DTO.
            request_body = {'transactions': [{**create_tx, 'fees': None}]}

            headers = client_get_headers(self.network_config.get('apiKey'))
            url = f"{self.network_config.get('mempoolHost')}/v1/transactions"

            try:
                response = requests.post(url, json=request_body, headers=headers, timeout=30)
            except requests.exceptions.RequestException as e:
                logger.error("Network request failed: %s", str(e))
                return IResult.err(IErrorInternal.NetworkError, str(e))

            handled = client_handle_response(response)
            if handled.is_err:
                return IResult.err(handled.error, handled.error_message)

            transactions = handled.get_ok().get('transactions') or {}
            transaction_hash = next(iter(transactions), None)
            if transaction_hash is None:
                return IResult.err(IErrorInternal.InvalidNetworkResponse, "No transaction returned")
            tx_result = transactions[transaction_hash]

            return IResult.ok({
                'transaction_hash': transaction_hash,
                'payment_address': tx_result.get('address'),
                'asset': tx_result.get('asset'),
                'used_addresses': used_addresses,
            })

        except Exception as e:
            logger.error("Error creating transaction: %s", str(e))
            return IResult.err(IErrorInternal.InternalError, str(e))

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

    def _valence_client(self) -> ValenceClient:
        """Build a `ValenceClient` against this wallet's configured valence host."""
        return ValenceClient(self.network_config.get("valenceHost"))

    def _to_ikeypair(self, keypair: Any) -> IKeypair:
        """Normalize a plain keypair (`IKeypair` or an equivalent dict) into
        an `IKeypair`, hex-decoding `secret_key`/`public_key` if needed.

        The 2-way flow methods take already-decrypted (plain) keypairs -
        matching this SDK's existing `create_transactions`' `all_keypairs`
        convention - not `IKeypairEncrypted`.
        """
        if isinstance(keypair, IKeypair):
            return keypair
        if isinstance(keypair, dict):
            secret_key = keypair['secret_key']
            public_key = keypair['public_key']
            if isinstance(secret_key, str):
                secret_key = bytes.fromhex(secret_key)
            if isinstance(public_key, str):
                public_key = bytes.fromhex(public_key)
            return IKeypair(
                address=keypair['address'],
                secret_key=secret_key,
                public_key=public_key,
                version=keypair.get('version', ADDRESS_VERSION),
            )
        return keypair

    def _build_keypair_map(self, all_keypairs: list) -> tuple:
        """Normalize `all_keypairs` into `(addresses, {address: IKeypair})`,
        matching sdk-go's `decryptKeypairsMap` / sdk-php's
        `decryptKeypairsMap` shape (this SDK's keypairs are already plain,
        so there is nothing to decrypt here beyond normalization).
        """
        addresses: List[str] = []
        keypair_map: Dict[str, IKeypair] = {}
        for kp in all_keypairs:
            ikp = self._to_ikeypair(kp)
            addresses.append(ikp.address)
            keypair_map[ikp.address] = ikp
        return addresses, keypair_map

    def _encrypt_2w_half(self, create_tx: dict) -> dict:
        """Seal a 2-way payment half (`create_tx`) under the wallet's own
        passphrase key for local persistence.

        This is entirely local - unrelated to valence, which only ever sees
        plaintext - and reuses the same secretbox construction as this
        module's `encrypt_keypair`/`key_handler.decrypt_keypair` (sha256 of
        the passphrase as the 32-byte key).
        """
        key = hashlib.sha256(self.passphrase_key or b'').digest()
        box = nacl.secret.SecretBox(key)
        plaintext = json.dumps(create_tx, separators=(',', ':')).encode('utf-8')
        encrypted = box.encrypt(plaintext)
        druid_info = create_tx.get('druid_info') or {}
        return {
            'druid': druid_info.get('druid'),
            'nonce': base64.b64encode(encrypted.nonce).decode('utf-8'),
            'save': base64.b64encode(encrypted.ciphertext).decode('utf-8'),
        }

    def _decrypt_2w_half(self, encrypted_half: dict) -> dict:
        """Open a 2-way payment half sealed by `_encrypt_2w_half`."""
        key = hashlib.sha256(self.passphrase_key or b'').digest()
        box = nacl.secret.SecretBox(key)
        nonce = base64.b64decode(encrypted_half['nonce'])
        ciphertext = base64.b64decode(encrypted_half['save'])
        plaintext = box.decrypt(ciphertext, nonce)
        return json.loads(plaintext.decode('utf-8'))

    def _submit_2w_half(self, host: str, tx: dict) -> IResult:
        """POST `tx` to `host`'s `/v1/transactions`, with `fees` and
        `druid_info.genesis_hash` explicitly null.

        Matches sdk-go's `submitTwoWayHalf` / sdk-php's `submitTwoWayHalf`:
        a 2-way half's constructed `druid_info` never carries `genesis_hash`
        - it is added here, last, only for the wire submission - and `fees`
        isn't part of the signed transaction, it's a separate, always-null
        field the `/v1` DTO requires.
        """
        druid_info = dict(tx.get('druid_info') or {})
        druid_info['genesis_hash'] = None
        body = {
            'transactions': [{
                'inputs': tx['inputs'],
                'outputs': tx['outputs'],
                'version': tx['version'],
                'druid_info': druid_info,
                'fees': None,
            }]
        }
        headers = client_get_headers(self.network_config.get('apiKey'))
        try:
            response = requests.post(f"{host}/v1/transactions", json=body, headers=headers, timeout=30)
        except requests.exceptions.RequestException as e:
            logger.error("Network request failed submitting 2-way half: %s", str(e))
            return IResult.err(IErrorInternal.NetworkError, str(e))
        return client_handle_response(response)

    def make_2way_payment(
        self,
        payment_address: str,
        sending_asset: dict,
        receiving_asset: dict,
        all_keypairs: list,
        receive_keypair: Any,
    ) -> IResult:
        """Offer a two-way (DRUID) trade to `payment_address`: this wallet
        will pay `sending_asset` to `payment_address` in exchange for
        `receiving_asset` delivered to `receive_keypair`'s address.

        Builds this party's transaction half (sourcing inputs from
        `all_keypairs`' addresses, change back to `receive_keypair`'s
        address), posts the plaintext offer to valence (addressed to
        `payment_address`'s mailbox, signed by `receive_keypair`), and
        returns a pending half - this party's half, sealed at rest under the
        wallet's passphrase key - for the caller to persist until
        `fetch_pending_2way_payment` reports it settled. Mirrors sdk-go's
        `Wallet.Make2WayPayment` / sdk-php's `Client::make2WayPayment`.
        """
        try:
            if not all_keypairs:
                return IResult.err(IErrorInternal.InvalidParametersProvided, "No keypairs provided")

            receive_kp = self._to_ikeypair(receive_keypair)
            addresses, keypair_map = self._build_keypair_map(all_keypairs)

            balance_result = self.fetch_balance(addresses)
            if balance_result.is_err:
                return balance_result
            balance = balance_result.get_ok()

            druid = generate_druid()

            # sender_expectation: what this (sending) party expects to receive.
            # receiver_expectation: what the counterparty (payee) is owed by this half.
            sender_expectation = {"from": "", "to": receive_kp.address, "asset": receiving_asset}
            receiver_expectation = {"from": "", "to": payment_address, "asset": sending_asset}

            my_half = tx_create_2w_tx_half(
                druid, sender_expectation, receiver_expectation, balance,
                keypair_map, receive_kp.address, 0,
            )
            create_tx = my_half["create_tx"]

            # Now that this half's inputs are known, fill in the "from" the
            # counterparty will use to correlate their acceptance transaction.
            receiver_expectation["from"] = tx_construct_tx_ins_address(create_tx["inputs"])

            encrypted_half = self._encrypt_2w_half(create_tx)

            details = {
                "druid": druid,
                "senderExpectation": sender_expectation,
                "receiverExpectation": receiver_expectation,
                "status": "pending",
                "mempoolHost": self.network_config.get("mempoolHost"),
            }

            post_result = self._valence_client().post(payment_address, receive_kp, details)
            if post_result.is_err:
                return post_result

            return IResult.ok({
                "druid": druid,
                "encryptedHalf": encrypted_half,
                "senderExpectation": sender_expectation,
                "receiverExpectation": receiver_expectation,
            })
        except ValueError as e:
            if str(e) == 'InsufficientFunds':
                return IResult.err(IErrorInternal.InsufficientFunds, str(e))
            return IResult.err(IErrorInternal.InvalidParametersProvided, str(e))
        except Exception as e:
            logger.error(f"Error in make_2way_payment: {str(e)}")
            return IResult.err(IErrorInternal.InternalError, str(e))

    def fetch_pending_2way_payment(self, stored: list, all_keypairs: list) -> IResult:
        """Poll this wallet's own mailboxes - one per address in
        `all_keypairs`, deduplicated - and do both of this wallet's possible
        roles in a two-way (DRUID) trade against whatever it finds there:

        1. Acceptor discovery: an offer `make_2way_payment` posts is
           addressed to whichever of the counterparty's own addresses it was
           handed as `payment_address`, so it lands in one of *our* mailboxes
           here. Any mailbox entry whose druid isn't in `stored` - this
           wallet never initiated it - is surfaced as-is in the returned
           `pending` map for the caller to inspect and
           `accept_2way_payment`/`reject_2way_payment`.
        2. Initiator settlement: an offer this wallet made shows up back in
           its own mailbox once the counterparty accepts. For any such entry
           - druid present in `stored`, status `"accepted"` - the stored
           half is decrypted, its `druid_info` expectation is replaced with
           the counterparty-filled `senderExpectation` now on the mailbox
           entry, the resulting transaction is submitted to this wallet's
           own mempool, and the settled mailbox entry is deleted.

        A failure against one mailbox, or one mailbox entry, never discards
        progress already made against the others: `pending` and `settled`
        are accumulated across every mailbox regardless of errors elsewhere.
        Errors are collected (not swallowed) under `errors` in the returned
        payload. Mirrors sdk-go's `Wallet.FetchPending2WayPayment` / sdk-php's
        `Client::fetchPending2WayPayment`.
        """
        try:
            addresses, keypair_map = self._build_keypair_map(all_keypairs)

            stored_by_druid: Dict[str, Any] = {}
            for half in stored or []:
                druid_key = half['druid'] if isinstance(half, dict) else half.druid
                stored_by_druid[druid_key] = half

            pending: Dict[str, Any] = {}
            settled: List[str] = []
            errors: List[str] = []

            vc = self._valence_client()
            seen_mailbox = set()

            for mailbox_address in addresses:
                if mailbox_address in seen_mailbox:
                    continue
                seen_mailbox.add(mailbox_address)

                kp = keypair_map[mailbox_address]

                entries_result = vc.get(mailbox_address, kp)
                if entries_result.is_err:
                    errors.append(f"fetch valence mailbox {mailbox_address}: {entries_result.error_message}")
                    continue
                entries = entries_result.get_ok() or {}

                for druid, details in entries.items():
                    half = stored_by_druid.get(druid)
                    if half is None or (details or {}).get('status') != 'accepted':
                        # Either an incoming offer (or status update) this
                        # wallet never initiated, or one of our own offers
                        # that isn't settled yet - surface both as pending.
                        pending[druid] = details
                        continue

                    try:
                        encrypted_half = half['encryptedHalf'] if isinstance(half, dict) else half.encrypted_half
                        tx = self._decrypt_2w_half(encrypted_half)
                    except Exception as e:
                        errors.append(f"decrypt stored half for druid {druid}: {e}")
                        continue

                    druid_info = tx.get('druid_info') or {}
                    expectations = druid_info.get('expectations') or []
                    if not expectations:
                        errors.append(f"stored half for druid {druid} has no DRUID expectations")
                        continue

                    # The counterparty has now filled in senderExpectation.from;
                    # replace our stored (incomplete) expectation with theirs.
                    expectations[0] = details.get('senderExpectation')

                    submit_result = self._submit_2w_half(self.network_config.get('mempoolHost'), tx)
                    if submit_result.is_err:
                        errors.append(f"submit settled half for druid {druid}: {submit_result.error_message}")
                        continue

                    delete_result = vc.delete(druid, mailbox_address, kp)
                    if delete_result.is_err:
                        # The half is already submitted on-chain even though
                        # the valence entry couldn't be cleaned up - this is
                        # committed progress and must still be reported settled.
                        errors.append(f"delete settled valence entry for druid {druid}: {delete_result.error_message}")

                    settled.append(druid)

            result: Dict[str, Any] = {"pending": pending, "settled": settled}
            if errors:
                result["errors"] = errors
            return IResult.ok(result)
        except Exception as e:
            logger.error(f"Error in fetch_pending_2way_payment: {str(e)}")
            return IResult.err(IErrorInternal.InternalError, str(e))

    def _handle_2w_tx_response(self, details: dict, status: str, all_keypairs: list) -> IResult:
        """Shared implementation behind `accept_2way_payment` and
        `reject_2way_payment`: stamps `details` with `status`, and - only
        when accepting - builds this party's matching transaction half
        (paying `details["senderExpectation"]`'s asset to its address,
        embedding `details["receiverExpectation"]` as this party's own
        `druid_info` expectation - the role-swap relative to
        `make_2way_payment`) and submits it to `details["mempoolHost"]`,
        before posting the updated status back to valence (addressed to
        `details["senderExpectation"]["to"]`'s mailbox, signed by this
        party's own - `details["receiverExpectation"]["to"]` - keypair).
        Mirrors sdk-go's `Wallet.handle2WTxResponse` / sdk-php's
        `Client::handle2WTxResponse`.
        """
        try:
            addresses, keypair_map = self._build_keypair_map(all_keypairs)

            receiver_address = details['receiverExpectation']['to']
            receiver_kp = keypair_map.get(receiver_address)
            if receiver_kp is None:
                return IResult.err(
                    IErrorInternal.InvalidParametersProvided,
                    f"No keypair for receiver address {receiver_address}",
                )

            details = dict(details)
            details['senderExpectation'] = dict(details['senderExpectation'])
            details['receiverExpectation'] = dict(details['receiverExpectation'])
            details['status'] = status

            if status == 'accepted':
                balance_result = self.fetch_balance(addresses)
                if balance_result.is_err:
                    return balance_result
                balance = balance_result.get_ok()

                my_half = tx_create_2w_tx_half(
                    details['druid'], details['receiverExpectation'], details['senderExpectation'],
                    balance, keypair_map, receiver_address, 0,
                )
                create_tx = my_half['create_tx']

                details['senderExpectation']['from'] = tx_construct_tx_ins_address(create_tx['inputs'])

                submit_result = self._submit_2w_half(details['mempoolHost'], create_tx)
                if submit_result.is_err:
                    return submit_result

            post_result = self._valence_client().post(details['senderExpectation']['to'], receiver_kp, details)
            if post_result.is_err:
                return post_result

            return IResult.ok(details)
        except ValueError as e:
            if str(e) == 'InsufficientFunds':
                return IResult.err(IErrorInternal.InsufficientFunds, str(e))
            return IResult.err(IErrorInternal.InvalidParametersProvided, str(e))
        except Exception as e:
            logger.error(f"Error in _handle_2w_tx_response: {str(e)}")
            return IResult.err(IErrorInternal.InternalError, str(e))

    def accept_2way_payment(self, details: dict, all_keypairs: list) -> IResult:
        """Accept a pending two-way trade offer described by `details`: pays
        `details["senderExpectation"]`'s asset to the offering party, embeds
        this party's own `details["receiverExpectation"]` as its half of the
        DRUID trade, submits the resulting transaction to
        `details["mempoolHost"]`, and posts the accepted status (with
        `senderExpectation.from` now filled in) back to valence.
        `all_keypairs` must include the keypair for
        `details["receiverExpectation"]["to"]` (this party's own address in
        the offer). Mirrors sdk-go's `Wallet.Accept2WayPayment` / sdk-php's
        `Client::accept2WayPayment`.
        """
        return self._handle_2w_tx_response(details, 'accepted', all_keypairs)

    def reject_2way_payment(self, details: dict, all_keypairs: list) -> IResult:
        """Decline a pending two-way trade offer described by `details`: no
        transaction is built or submitted, but the rejected status is posted
        back to valence so the offering party's `fetch_pending_2way_payment`
        can observe it. `all_keypairs` must include the keypair for
        `details["receiverExpectation"]["to"]` (this party's own address in
        the offer). Mirrors sdk-go's `Wallet.Reject2WayPayment` / sdk-php's
        `Client::reject2WayPayment`.
        """
        return self._handle_2w_tx_response(details, 'rejected', all_keypairs)

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
        if api_key := config.get('apiKey'):
            wallet_config['apiKey'] = api_key

        return IResult.ok(wallet_config)
    except Exception as e:
        return IResult.err(IErrorInternal.InvalidParametersProvided, str(e))

# You can add additional methods following the same pattern, adjusting them according to your needs
