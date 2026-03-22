"""
Pytest configuration and fixtures
"""
import sys
import os
import pytest
import tempfile
from pathlib import Path

# Add the parent directory to Python path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

# Base URL for API testing
BASE_URL = "http://localhost:8080"
INTERNAL_KEY = os.getenv("SANDBOX_INTERNAL_API_KEY", "test-key")

@pytest.fixture
def client():
    """Create requests session"""
    session = requests.Session()
    session.headers.update(
        {
            "Content-Type": "application/json",
            "X-Internal-Key": INTERNAL_KEY,
        }
    )
    return session


@pytest.fixture
def temp_test_file():
    """Create temporary test file path for container"""
    # Use container-accessible path
    temp_file = "/tmp/test_file.txt"
    # Create content via API
    import requests
    session = requests.Session()
    session.headers.update(
        {
            "Content-Type": "application/json",
            "X-Internal-Key": INTERNAL_KEY,
        }
    )
    
    content = "Line 1: Hello World\nLine 2: This is a test\nLine 3: Python testing"
    session.post(f"{BASE_URL}/api/v1/file/write", json={
        "file": temp_file,
        "content": content
    })
    
    yield temp_file
    
    # Cleanup via API
    try:
        session.post(f"{BASE_URL}/api/v1/file/write", json={
            "file": temp_file,
            "content": ""
        })
    except:
        pass 
