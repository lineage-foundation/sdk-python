#!/usr/bin/env python3
"""Test script to find working API endpoints."""

import requests
import json
import os

def test_endpoints():
    """Test various API endpoints to find working ones."""
    
    # Default hosts
    storage_host = os.getenv('AIBLOCK_STORAGE_HOST', 'https://storage.aiblock.dev')
    mempool_host = os.getenv('AIBLOCK_MEMPOOL_HOST', 'https://mempool.aiblock.dev')
    
    print(f"Testing endpoints...")
    print(f"Storage Host: {storage_host}")
    print(f"Mempool Host: {mempool_host}")
    print("=" * 60)
    
    # Test block number 866894 and transaction hash g33a9a99d44c445c9ca694f0f5e1391b
    test_block_num = 866894
    test_tx_hash = "g33a9a99d44c445c9ca694f0f5e1391b"
    
    # Endpoints to test
    endpoints = [
        # Storage endpoints - various patterns for blocks
        (storage_host, 'latest_block', 'Storage'),
        (storage_host, f'block/{test_block_num}', 'Storage'),
        (storage_host, f'blocks/{test_block_num}', 'Storage'),
        (storage_host, f'get_block/{test_block_num}', 'Storage'),
        (storage_host, f'blockchain/{test_block_num}', 'Storage'),
        (storage_host, f'chain/{test_block_num}', 'Storage'),
        
        # Various patterns for transactions
        (storage_host, f'blockchain/{test_tx_hash}', 'Storage'),
        (storage_host, f'transaction/{test_tx_hash}', 'Storage'),
        (storage_host, f'transactions/{test_tx_hash}', 'Storage'),
        (storage_host, f'tx/{test_tx_hash}', 'Storage'),
        (storage_host, f'get_transaction/{test_tx_hash}', 'Storage'),
        (storage_host, f'get_tx/{test_tx_hash}', 'Storage'),
        
        # Mempool endpoints
        (mempool_host, 'total_supply', 'Mempool'),
        (mempool_host, 'issued_supply', 'Mempool'),
        (mempool_host, 'get_total_supply', 'Mempool'),
        (mempool_host, 'get_issued_supply', 'Mempool'),
        
        # Debug endpoints
        (storage_host, 'debug_data', 'Storage'),
        (mempool_host, 'debug_data', 'Mempool'),
        (storage_host, 'status', 'Storage'),
        (mempool_host, 'status', 'Mempool'),
        
        # Alternative block patterns
        (storage_host, f'block_by_number/{test_block_num}', 'Storage'),
        (storage_host, f'block_by_num/{test_block_num}', 'Storage'),
        (storage_host, f'get_block_by_number/{test_block_num}', 'Storage'),
    ]
    
    working_endpoints = []
    
    for host, endpoint, host_type in endpoints:
        url = f"{host}/{endpoint}"
        print(f"\nTesting: {url}")
        
        try:
            response = requests.get(url, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"✓ SUCCESS - Response: {json.dumps(data, indent=2)[:200]}...")
                    working_endpoints.append((endpoint, host_type, response.status_code))
                except:
                    print(f"✓ SUCCESS - Non-JSON response: {response.text[:100]}...")
                    working_endpoints.append((endpoint, host_type, response.status_code))
            else:
                try:
                    error_data = response.json()
                    print(f"✗ FAILED - {response.status_code}: {json.dumps(error_data, indent=2)[:200]}...")
                except:
                    print(f"✗ FAILED - {response.status_code}: {response.text[:100]}...")
                    
        except requests.exceptions.RequestException as e:
            print(f"✗ ERROR - {str(e)}")
    
    print("\n" + "=" * 60)
    print("WORKING ENDPOINTS SUMMARY:")
    print("=" * 60)
    
    if working_endpoints:
        for endpoint, host_type, status in working_endpoints:
            print(f"✓ {host_type}: {endpoint} (Status: {status})")
    else:
        print("No working endpoints found!")
    
    print(f"\nTotal working endpoints: {len(working_endpoints)}")

if __name__ == "__main__":
    test_endpoints() 