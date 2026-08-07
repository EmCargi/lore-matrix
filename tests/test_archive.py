import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

extract_web = importlib.import_module("extract-web")
extract_from_local_archive = extract_web.extract_from_local_archive

def test_extract_from_local_archive_not_found():
    """
    Test that extract_from_local_archive handles non-existent snapshot gracefully.
    """
    with patch.object(extract_web, "ARCHIVEBOX_VAULT_DIR", Path("/mock/archive/vault")), \
         patch.object(extract_web.Path, "exists", return_value=False):
        
        # Run function and verify it returns False
        success = extract_from_local_archive("999999")
        assert success is False


def test_extract_from_local_archive_success():
    """
    Test that extract_from_local_archive reads file, parses HTML, chunks, and processes it.
    """
    # Mock AI response
    mock_active_ai = MagicMock()
    mock_generate = MagicMock(return_value='{"entries": [{"id": 1, "name": "Test Entry", "keys": ["test"], "content": "Test Description", "insertion_order": 50, "priority": 50}]}')
    
    with patch.object(extract_web, "ARCHIVEBOX_VAULT_DIR", Path("/mock/archive/vault")), \
         patch.object(extract_web.Path, "exists", return_value=True), \
         patch("builtins.open", mock_open(read_data="<html><body><div class='wsite-not-footer'><p>Test Content Block 1</p></div></body></html>")) as mock_file, \
         patch.object(extract_web, "generate_with_retry", mock_generate), \
         patch.object(extract_web, "ACTIVE_AI", mock_active_ai), \
         patch.object(extract_web, "OUTPUT_CHUNKS_DIR", "/mock/output"), \
         patch("os.makedirs"), \
         patch("json.dump"):
        
        success = extract_from_local_archive("123456", active_ai=mock_active_ai)
        
        assert success is True
        mock_generate.assert_called()
        
        # Verify first call opens the singlefile.html for reading
        first_call = mock_file.call_args_list[0]
        assert first_call[0][0] == Path("/mock/archive/vault/123456/singlefile.html")
        assert first_call.kwargs.get("encoding") == "utf-8"
