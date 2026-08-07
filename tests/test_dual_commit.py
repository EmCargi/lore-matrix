import importlib
import json
import os
import sys
from unittest.mock import MagicMock, mock_open, patch

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import module dynamically due to folder structure path mapping
dual_commit = importlib.import_module("src.storage.dual_commit")

def test_dual_commit_json_file():
    mock_json_data = {
        "177-003-00-004": {
            "file_id": 177,
            "map_id": 3,
            "event_id": 0,
            "line_id": 4,
            "name": "Poison",
            "body": "Poison decreases your hit points.",
            "icon_index": 18,
            "keywords": ["Poison"]
        }
    }
    
    mock_collection = MagicMock()
    
    with patch("builtins.open", mock_open(read_data=json.dumps(mock_json_data))), \
         patch("src.storage.dual_commit.Path.exists", return_value=True), \
         patch("src.storage.dual_commit.get_collection", return_value=mock_collection), \
         patch("sqlite3.connect") as mock_sql_connect:
         
        # Mock SQLite connection context manager
        mock_conn = MagicMock()
        mock_sql_connect.return_value.__enter__.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        
        success = dual_commit.dual_commit_json_file("dummy.json", "dummy.db")
        
        assert success is True
        
        # Verify SQLite execution
        mock_cursor.execute.assert_called()
        mock_cursor.executemany.assert_called()
        
        # Verify ChromaDB execution
        mock_collection.upsert.assert_called_once_with(
            documents=["Poison decreases your hit points."],
            metadatas=[{
                "composite_key": "177-003-00-004",
                "file_id": 177,
                "map_id": 3,
                "event_id": 0,
                "line_id": 4,
                "name": "Poison",
                "icon_index": 18,
                "keywords": "Poison"
            }],
            ids=["177-003-00-004"]
        )
