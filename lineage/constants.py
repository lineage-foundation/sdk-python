"""Constants used throughout the AIBlock SDK."""

# Address versions
ADDRESS_VERSION = 1
ADDRESS_VERSION_OLD = 0
TEMP_ADDRESS_VERSION = 2

# Default item configuration
ITEM_DEFAULT = 1  # Default to creating 1 item

# Default item metadata
DEFAULT_ITEM_METADATA = {
    'type': 'default',
    'name': 'Default Item',
    'description': 'Default item description',
    'meta': {}
}

# Seed regeneration threshold
SEED_REGEN_THRES = 100

# Metadata size limit (1MB)
MAX_METADATA_SIZE = 1024 * 1024 