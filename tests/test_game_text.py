import importlib
import os
import sys
from unittest.mock import mock_open, patch

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

extract_game_text = importlib.import_module("extract-game-text")

def test_strip_outer_quotes():
    """
    Test utility function strip_outer_quotes.
    """
    assert extract_game_text.strip_outer_quotes('"Hello"') == "Hello"
    assert extract_game_text.strip_outer_quotes("'World'") == "World"
    assert extract_game_text.strip_outer_quotes(' "Hello" ') == "Hello"
    assert extract_game_text.strip_outer_quotes("Hello") == "Hello"
    assert extract_game_text.strip_outer_quotes('"\'Hello\'"') == "Hello"


def test_parse_game_text_file_empty():
    """
    Test parsing an empty file or one with no coordinates.
    """
    with patch("builtins.open", mock_open(read_data="No coordinates here")):
        result = extract_game_text.parse_game_text_file("dummy.txt")
        assert result == {}


def test_parse_game_text_file_success():
    """
    Test parsing a valid game text file with formatting tags, color tags, and icons.
    """
    raw_data = r"""
<|177|003|00|004|>
"Guide \I[12]"
Hello, \C[3]World!\C[0] How are you?
This is a \C[2]multi-line
highlight block\C[0]!

<|10|20|30|40|>
'Hero'
Let's go.
"""
    with patch("builtins.open", mock_open(read_data=raw_data)):
        result = extract_game_text.parse_game_text_file("dummy.txt")
        
        # Verify first entry
        assert "177-003-00-004" in result
        entry1 = result["177-003-00-004"]
        assert entry1["file_id"] == 177
        assert entry1["map_id"] == 3
        assert entry1["event_id"] == 0
        assert entry1["line_id"] == 4
        assert entry1["name"] == "Guide"
        assert entry1["icon_index"] == 12
        assert entry1["body"] == "Hello, World! How are you?\nThis is a multi-line\nhighlight block!"
        
        # Verify keywords (DOTALL multi-line matching verification)
        assert "World!" in entry1["keywords"]
        assert "multi-line\nhighlight block" in entry1["keywords"]

        # Verify second entry
        assert "10-20-30-40" in result
        entry2 = result["10-20-30-40"]
        assert entry2["file_id"] == 10
        assert entry2["map_id"] == 20
        assert entry2["event_id"] == 30
        assert entry2["line_id"] == 40
        assert entry2["name"] == "Hero"
        assert entry2["icon_index"] is None
        assert entry2["body"] == "Let's go."
        assert entry2["keywords"] == []


def test_parse_agnostic_templates():
    """
    Test parsing coordinate templates from both database and dialogue templates.
    """
    raw_data = r"""
<|actors|002|description|>
暗殺拳の達人を祖父にもつ少女。幼少のころからその技の
すべてを叩き込まれている格闘術のエキスパート。

<|COMMON|003|00|020|>
\V[101]が仲間になった！！
名前をつけてあげよう！
"""
    with patch("builtins.open", mock_open(read_data=raw_data)):
        result = extract_game_text.parse_game_text_file("dummy.txt")
        
        # Verify 3-component database entry
        assert "actors-002-description" in result
        entry1 = result["actors-002-description"]
        assert entry1["file_id"] == "actors"
        assert entry1["map_id"] == 2
        assert entry1["event_id"] == "description"
        assert entry1["line_id"] == ""
        assert entry1["name"] == ""
        assert "暗殺拳の達人を祖父にもつ少女。" in entry1["body"]
        assert "すべてを叩き込まれている格闘術のエキスパート。" in entry1["body"]

        # Verify 4-component dialogue entry with alphanumeric identifier
        assert "COMMON-003-00-020" in result
        entry2 = result["COMMON-003-00-020"]
        assert entry2["file_id"] == "COMMON"
        assert entry2["map_id"] == 3
        assert entry2["event_id"] == 0
        assert entry2["line_id"] == 20
        assert entry2["name"] == ""
        assert entry2["body"] == "\\V[101]が仲間になった！！\n名前をつけてあげよう！"

