from aiblock.config import get_config, validate_env_config
from aiblock.wallet import Wallet

def test_environment_config():
    """Test loading and validating environment configuration."""
    # Get configuration from environment
    config_result = get_config()
    assert config_result.is_ok, f"Failed to get config: {config_result.reason}"
    
    config = config_result.get_ok()
    validation_result = validate_env_config(config)
    assert validation_result.is_ok, f"Config validation failed: {validation_result.reason}"
    
    # Verify required keys exist
    assert 'mempoolHost' in config, "Missing mempoolHost in config"
    assert 'storageHost' in config, "Missing storageHost in config"
    assert 'passphrase' in config, "Missing passphrase in config"
    
    # Verify URL formats
    assert config['mempoolHost'].startswith(('http://', 'https://')), "Invalid mempoolHost URL format"
    assert config['storageHost'].startswith(('http://', 'https://')), "Invalid storageHost URL format"

def test_wallet_initialization():
    """Test wallet initialization with environment config."""
    config_result = get_config()
    assert config_result.is_ok, f"Failed to get config: {config_result.reason}"
    
    config = config_result.get_ok()
    wallet = Wallet()
    result = wallet.init_new(config)
    
    assert result.is_ok, f"Wallet initialization failed: {result.reason}" 