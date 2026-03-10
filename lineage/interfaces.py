"""Type definitions and interfaces for the AIBlock SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TypeVar, Generic, Optional, List, Dict, Any, Union

T = TypeVar('T')

class IErrorInternal(Enum):
    """Internal error types for the SDK."""
    # HTTP status code related errors
    NotFound = auto()
    BadRequest = auto()
    
    # Seed and key generation errors
    InvalidSeedPhrase = auto()
    UnableToGenerateSeed = auto()
    UnableToGenerateKeypair = auto()
    UnableToGetKeypair = auto()
    UnableToGetKeypairFromMap = auto()
    UnableToEncryptKeypair = auto()
    UnableToSaveKeypairLocal = auto()
    UnableToGetLocalKeypair = auto()
    NoPassPhraseProvided = auto()
    UnableToGetPassphraseBuffer = auto()
    UnableToDeriveNextKeypair = auto()
    UnableToGetExistingSeed = auto()
    UnableToGetExistingMasterKey = auto()
    UnableToGenerateMasterKey = auto()

    # Address related errors
    UnableToConstructDefaultAddress = auto()
    UnableToConstructTempAddress = auto()
    UnableToConstructOldAddress = auto()
    UnableToRegenAddresses = auto()
    UnableToFindNonEmptyAddresses = auto()
    InvalidAddressVersion = auto()
    CannotParseAddress = auto()

    # Transaction related errors
    InsufficientFunds = auto()
    NoInputs = auto()
    InvalidInputs = auto()
    UnableToGenerateDruid = auto()
    UnableToConstructTxIns = auto()
    UnableToConstructSignature = auto()
    UnableToEncryptTransaction = auto()
    UnableToDecryptTransaction = auto()
    InvalidDRUIDProvided = auto()
    NoDRUIDValues = auto()
    AssetsIncompatible = auto()
    KeyValuePairNotSingle = auto()

    # Encryption/Decryption errors
    UnableToEncryptMasterKey = auto()
    UnableToDecryptMasterKey = auto()
    UnableToDecryptKeypair = auto()
    MasterKeyCorrupt = auto()

    # Network and client errors
    UnableToInitializeWallet = auto()
    WalletNotInitialized = auto()
    UnableToFetchBalance = auto()
    UnableToInitializeNetwork = auto()
    NetworkNotInitialized = auto()
    UnableToGenerateHeaders = auto()
    UnableToGetDebugData = auto()
    NoHostsProvided = auto()
    ClientNotInitialized = auto()
    StorageNotInitialized = auto()
    ValenceNotInitialized = auto()
    FetchBalanceResponseEmpty = auto()
    InvalidNetworkResponse = auto()
    NoComputeHostProvided = auto()
    NoContentReturned = auto()
    UnableToFilterValenceData = auto()
    Unauthorized = auto()  # New from JS SDK
    Forbidden = auto()  # New from JS SDK
    InternalServerError = auto()  # New from JS SDK
    ServiceUnavailable = auto()  # New from JS SDK
    GatewayTimeout = auto()  # New from JS SDK
    NetworkError = auto()  # New from JS SDK

    # Message signing errors
    UnableToSignMessage = auto()
    UnableToVerifyMessage = auto()

    # Parameter validation errors
    InvalidParametersProvided = auto()
    InvalidKeypairProvided = auto()
    InvalidMetadataFormat = auto()
    InvalidAddressFormat = auto()

    # Generic errors
    InternalError = auto()
    UnknownError = auto()

    # New error type
    UnableToGenerateSignableHash = auto()

@dataclass(frozen=True)
class INetworkRoute:
    """Interface for a network route configuration."""
    host: str
    endpoint: str
    method: str = "GET"

@dataclass(frozen=True)
class INetworkConfig:
    """Interface for network configuration."""
    storage_host: str
    mempool_host: str
    routes: Dict[str, INetworkRoute] = field(default_factory=dict)

@dataclass(frozen=True)
class IClientConfig:
    """Interface for client configuration."""
    network: INetworkConfig
    version: int = 1

@dataclass(frozen=True)
class IKeypair:
    """Interface for a cryptographic key pair."""
    address: str
    secret_key: bytes
    public_key: bytes
    version: int

@dataclass(frozen=True)
class IMasterKey:
    """Interface for a master key."""
    secret: bytes
    seed: str

@dataclass(frozen=True)
class IMasterKeyEncrypted:
    """Interface for an encrypted master key."""
    nonce: str
    save: str

@dataclass(frozen=True)
class IKeypairEncrypted:
    """Interface for an encrypted keypair."""
    master_key: IMasterKeyEncrypted
    version: int

@dataclass(frozen=True)
class ITransactionMetadata:
    """Interface for transaction metadata."""
    action: str
    app: str
    data: Dict[str, Any]

@dataclass(frozen=True)
class ITransactionData:
    """Interface for transaction data."""
    timestamp: int
    sender: str
    receiver: str
    amount: int
    fee: int
    metadata: ITransactionMetadata

@dataclass(frozen=True)
class ITransaction:
    """Interface for a complete transaction."""
    data: ITransactionData
    signature: str

@dataclass(frozen=True)
class IScriptData:
    """Interface for script data."""
    name: str
    description: str
    code: str
    version: int

@dataclass(frozen=True)
class IScript:
    """Interface for a complete script."""
    data: IScriptData
    signature: str

@dataclass(frozen=True)
class IBalanceResponse:
    """Interface for balance response."""
    balance: int
    pending: int
    nonce: int

@dataclass(frozen=True)
class INewWalletResponse:
    """Interface for new wallet response."""
    seed_phrase: str
    address: str
    keypair: IKeypair

@dataclass(frozen=True)
class IResult(Generic[T]):
    """Generic result type for handling success and error cases."""
    _value: Optional[T]
    _is_error: bool
    _error: Optional[IErrorInternal] = None
    _error_message: Optional[str] = None

    @property
    def is_ok(self) -> bool:
        """Check if this is a success result."""
        return not self._is_error

    @property
    def is_err(self) -> bool:
        """Check if this is an error result."""
        return self._is_error

    def get_ok(self) -> T:
        """Get the success value.
        
        Raises:
            RuntimeError: If this is an error result
        """
        if self._is_error:
            raise RuntimeError("Cannot get ok value from error result")
        if self._value is None:
            raise RuntimeError("Success value is None")
        return self._value

    @property
    def error(self) -> IErrorInternal:
        """Get the error value.
        
        Raises:
            RuntimeError: If this is not an error result
        """
        if not self._is_error:
            raise RuntimeError("Cannot get error value from success result")
        if self._error is None:
            raise RuntimeError("Error value is None")
        return self._error

    @property
    def error_message(self) -> Optional[str]:
        """Get the error message if any."""
        return self._error_message if self._is_error else None

    @classmethod
    def ok(cls, value: T) -> IResult[T]:
        """Create a success result."""
        return cls(_value=value, _is_error=False)

    @classmethod
    def err(cls, error: IErrorInternal, message: Optional[str] = None) -> IResult[T]:
        """Create an error result.
        
        Args:
            error: The error type
            message: Optional error message
        """
        return cls(_value=None, _is_error=True, _error=error, _error_message=message)

    # Uppercase aliases for compatibility
    Ok = ok
    Err = err

    def unwrap_or(self, default: T) -> T:
        """Get the success value or return the default if this is an error."""
        return self._value if not self._is_error and self._value is not None else default