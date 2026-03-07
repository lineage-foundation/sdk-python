"""Configuration module for the AIBlock SDK."""

from __future__ import annotations

from typing import TypedDict, Optional, Literal, Dict, Any
from dataclasses import dataclass
from enum import Enum
import os
import logging
from dotenv import load_dotenv
from aiblock.interfaces import IResult, IErrorInternal

# Set up logging
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

class AIBlockConfig(TypedDict):
    """Type definition for AIBlock configuration."""
    passphrase: str
    mempoolHost: str
    storageHost: str
    valenceHost: str

def get_config() -> IResult[Dict[str, str]]:
    """Get configuration from environment variables.
    
    Returns:
        IResult[Dict[str, str]]: Configuration dictionary or error
    """
    config = {}
    
    # Required environment variables
    required_vars = {
        'AIBLOCK_MEMPOOL_HOST': 'mempoolHost',
        'AIBLOCK_STORAGE_HOST': 'storageHost',
        'AIBLOCK_PASSPHRASE': 'passphrase'
    }
    
    # Check for required environment variables
    missing_vars = []
    for env_var, config_key in required_vars.items():
        value = os.getenv(env_var)
        if not value:
            missing_vars.append(env_var)
        else:
            config[config_key] = value
    
    if missing_vars:
        return IResult.err(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    # Validate URLs
    for host_key in ['mempoolHost', 'storageHost']:
        url = config[host_key]
        if not url.startswith(('http://', 'https://')):
            return IResult.err(f"Invalid URL for {host_key}: {url}")
    
    return IResult.ok(config)

def validate_config(config: Dict[str, Any], init_offline: bool = False) -> IResult[Dict[str, Any]]:
    """Validate configuration dictionary.
    
    Args:
        config: Configuration dictionary to validate
        init_offline: Whether to validate for offline mode
        
    Returns:
        IResult[Dict[str, Any]]: Validated configuration or error
    """
    try:
        logger.debug("Validating config: %s, init_offline: %s", config, init_offline)
        if not config:
            logger.error("No configuration provided")
            return IResult.err(IErrorInternal.InvalidParametersProvided, "No configuration provided")

        # In offline mode, no validation needed
        if init_offline:
            logger.debug("Validating offline mode")
            return IResult.ok(config)

        # Check required fields for online mode
        logger.debug("Validating online mode")
        if not isinstance(config.get('mempoolHost'), str):
            logger.error("Missing or invalid mempoolHost")
            return IResult.err(IErrorInternal.InvalidParametersProvided, "Missing or invalid mempoolHost")
            
        if not isinstance(config.get('storageHost'), str):
            logger.error("Missing or invalid storageHost")
            return IResult.err(IErrorInternal.InvalidParametersProvided, "Missing or invalid storageHost")
            
        # Validate URLs
        logger.debug("Validating URLs")
        for host_key in ['mempoolHost', 'storageHost', 'valenceHost']:
            if host := config.get(host_key):
                logger.debug("Validating %s: %s", host_key, host)
                if not isinstance(host, str):
                    logger.error("Invalid %s: not a string", host_key)
                    return IResult.err(IErrorInternal.InvalidParametersProvided, f"Invalid {host_key}")
                if not host.startswith(('http://', 'https://')):
                    logger.error("Invalid URL for %s: %s", host_key, host)
                    return IResult.err(IErrorInternal.InvalidParametersProvided, f"Invalid URL for {host_key}")
                    
        logger.debug("Config validation successful")
        return IResult.ok(config)
        
    except Exception as e:
        logger.error("Exception during validation: %s", e)
        return IResult.err(IErrorInternal.InvalidParametersProvided, str(e))

def validate_env_config(config: dict) -> IResult[dict]:
    """Validate configuration loaded from environment variables.
    
    Args:
        config: Configuration dictionary loaded from environment variables
        
    Returns:
        IResult[dict]: Success with validated config or error with message
    """
    if not config:
        return IResult.err(IErrorInternal.InvalidParametersProvided, "No configuration provided")

    # Required configuration keys
    required_keys = ['passphrase', 'mempoolHost', 'storageHost']
    missing_keys = [key for key in required_keys if key not in config]
    
    if missing_keys:
        return IResult.err(
            IErrorInternal.InvalidParametersProvided,
            f"Missing required configuration keys: {', '.join(missing_keys)}"
        )

    # Validate URLs
    for host_key in ['mempoolHost', 'storageHost', 'valenceHost']:
        url = config.get(host_key)
        if url and not isinstance(url, str):
            return IResult.err(
                IErrorInternal.InvalidParametersProvided,
                f"Invalid type for {host_key}: expected string"
            )
        if url and not url.startswith(('http://', 'https://')):
            return IResult.err(
                IErrorInternal.InvalidParametersProvided,
                f"Invalid URL for {host_key}: {url}"
            )

    return IResult.ok(config)

def get_default_config() -> AIBlockConfig:
    """Get the default configuration dictionary.
    
    Returns:
        AIBlockConfig: Default configuration with mainnet endpoints
    """
    return {
        'passphrase': '',  # Must be provided by user
        'storageHost': 'https://storage.aiblock.dev',
        'mempoolHost': 'https://mempool.aiblock.dev',
        'valenceHost': 'https://valence.aiblock.dev'
    } 