# Troubleshooting Guide

This guide covers common issues you might encounter when using the AIBlock SDK and their solutions.

## Common Issues

### 1. Connection Issues

#### Problem: Unable to connect to blockchain nodes
```python
{
    "status": "error",
    "reason": "Failed to connect to storage node",
    "error_code": "NETWORK_ERROR"
}
```

**Solutions:**
1. Check if your environment variables are set correctly:
   ```env
   # .env file in your project directory
   AIBLOCK_STORAGE_HOST=https://storage.aiblock.dev
   AIBLOCK_MEMPOOL_HOST=https://mempool.aiblock.dev
   AIBLOCK_VALENCE_HOST=https://valence.aiblock.dev
   ```

2. Verify network connectivity:
   ```python
   import requests
   
   def check_node_status(url: str) -> bool:
       try:
           response = requests.get(f"{url}/debug_data")
           return response.status_code == 200
       except Exception:
           return False
   ```

3. If you need to override the environment variables, provide explicit hosts:
   ```python
   client = BlockchainClient(
       storage_host="https://custom-storage.example.com",
       mempool_host="https://custom-mempool.example.com"
   )
   ```

### 2. Insufficient Balance

#### Problem: Unable to create assets due to insufficient balance
```python
{
    "status": "error",
    "reason": "Insufficient balance for operation",
    "error_code": "INSUFFICIENT_BALANCE"
}
```

**Solutions:**
1. Check current balance:
   ```python
   result = wallet.get_balance()
   if result.is_ok:
       print(f"Current balance: {result.get_ok()['total']['tokens']}")
   else:
       print(result.error, result.error_message)
   ```

2. Ensure you're using the correct wallet:
   ```python
   # Verify wallet address
   print(f"Using wallet address: {wallet.address}")
   ```

### 3. Invalid Metadata

#### Problem: Asset creation fails due to invalid metadata
```python
{
    "status": "error",
    "reason": "Invalid metadata format",
    "error_code": "INVALID_METADATA"
}
```

**Solutions:**
1. Validate metadata format:
   ```python
   import json
   
   def validate_metadata(metadata: dict) -> bool:
       try:
           # Check if serializable
           json.dumps(metadata)
           
           # Check required fields
           required_fields = ["type", "name", "version"]
           for field in required_fields:
               if field not in metadata:
                   return False
           
           return True
       except Exception:
           return False
   ```

2. Use metadata templates:
   ```python
   def get_model_metadata_template():
       return {
           "type": "ai_model",
           "name": "",
           "version": "1.0",
           "description": "",
           "parameters": {},
           "timestamp": ""
       }
   ```

### 4. Version Mismatch

#### Problem: SDK version compatibility issues
```python
ImportError: Cannot import name 'X' from 'aiblock'
```

**Solutions:**
1. Check installed version:
   ```python
   import aiblock
   print(f"Installed version: {aiblock.__version__}")
   ```

2. Install specific version:
   ```bash
   pip install aiblock==0.2.0
   ```

### 5. Large File Handling

#### Problem: Timeout when handling large model files
```python
TimeoutError: Request timed out
```

**Solutions:**
1. Use chunked processing:
   ```python
   def process_large_file(file_path: str, chunk_size: int = 1024*1024):
       with open(file_path, 'rb') as f:
           while True:
               chunk = f.read(chunk_size)
               if not chunk:
                   break
               # Process chunk
               yield chunk
   ```

2. Implement progress tracking:
   ```python
   import os
   from tqdm import tqdm
   
   def upload_large_model(file_path: str, client: BlockchainClient):
       file_size = os.path.getsize(file_path)
       with tqdm(total=file_size, unit='B', unit_scale=True) as pbar:
           for chunk in process_large_file(file_path):
               # Process chunk
               pbar.update(len(chunk))
   ```

## Best Practices for Error Prevention

1. **Always validate inputs:**
   ```python
   def validate_input(value: str, max_length: int = 1000) -> bool:
       return bool(value and len(value) <= max_length)
   ```

2. **Use try-except blocks:**
   ```python
   try:
       response = client.create_item_asset(...)
   except Exception as e:
       logging.error(f"Failed to create asset: {str(e)}")
       raise
   ```

3. **Implement retries for network operations:**
   ```python
   from tenacity import retry, stop_after_attempt, wait_exponential
   
   @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
   def create_asset_with_retry(*args, **kwargs):
       return client.create_item_asset(*args, **kwargs)
   ```

4. **Log operations for debugging:**
   ```python
   import logging
   
   logging.basicConfig(level=logging.INFO)
   logger = logging.getLogger(__name__)
   
   def log_operation(func):
       def wrapper(*args, **kwargs):
           logger.info(f"Starting {func.__name__}")
           result = func(*args, **kwargs)
           logger.info(f"Completed {func.__name__}")
           return result
       return wrapper
   ```

## Getting Help

If you encounter issues not covered in this guide:

1. Check the [GitHub Issues](https://github.com/AIBlockOfficial/2Way.py/issues)
2. Join our [Discord Community](https://discord.gg/aiblock)
3. Contact support at support@aiblock.dev

## Contributing

Found a bug or want to improve the documentation?

1. Open an issue on GitHub
2. Submit a pull request
3. Follow our [Contributing Guidelines](CONTRIBUTING.md) 