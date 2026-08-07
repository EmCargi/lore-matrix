import importlib
import os
import sys
from unittest.mock import MagicMock, patch

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

md_slicer = importlib.import_module("src.utils.md_slicer")

def test_sanitize_filename():
    assert md_slicer.sanitize_filename("Poison") == "Poison"
    assert md_slicer.sanitize_filename("Blind / Silence?") == "Blind  Silence"
    assert md_slicer.sanitize_filename("Invalid:*?\"<>|Name") == "InvalidName"


def test_slice_markdown_without_frontmatter():
    raw_data = """# Poison
Poison decreases hit points.
# Blind
Reduces physical accuracy.
"""
    mock_files = {}
    
    # Custom file writer mock to inspect output file contents
    def open_mock(path, mode, encoding=None):
        path_str = str(path)
        mock_file = MagicMock()
        mock_file.write = lambda text: mock_files.setdefault(path_str, []).append(text)
        return mock_file

    with patch("src.utils.md_slicer.Path.exists", return_value=True), \
         patch("src.utils.md_slicer.extract_global_frontmatter") as mock_extract, \
         patch("os.makedirs"), \
         patch("builtins.open", side_effect=open_mock):
         
        # Setup mock frontmatter extraction
        def gen():
            for line in raw_data.strip().splitlines():
                yield line + "\n"
        mock_extract.return_value = ("", gen())
        
        success = md_slicer.slice_markdown_file("monolith.md", "/mock/vault")
        
        assert success is True
        # Verify both files created
        assert "/mock/vault/Poison.md" in mock_files
        assert "/mock/vault/Blind.md" in mock_files
        
        # Verify contents
        poison_content = "".join(mock_files["/mock/vault/Poison.md"])
        assert poison_content == "# Poison\nPoison decreases hit points.\n"
        
        blind_content = "".join(mock_files["/mock/vault/Blind.md"])
        assert blind_content == "# Blind\nReduces physical accuracy.\n"


def test_slice_markdown_with_frontmatter():
    mock_files = {}
    
    def open_mock(path, mode, encoding=None):
        path_str = str(path)
        mock_file = MagicMock()
        mock_file.write = lambda text: mock_files.setdefault(path_str, []).append(text)
        return mock_file

    with patch("src.utils.md_slicer.Path.exists", return_value=True), \
         patch("src.utils.md_slicer.extract_global_frontmatter") as mock_extract, \
         patch("os.makedirs"), \
         patch("builtins.open", side_effect=open_mock):
         
        frontmatter = "---\ntype: game-text-export\nsource: game_vault.db\n---\n"
        def gen():
            body = "# Silence\nPrevents using magic.\n# Stun\nSkips event turns.\n"
            for line in body.splitlines():
                yield line + "\n"
        mock_extract.return_value = (frontmatter, gen())
        
        success = md_slicer.slice_markdown_file("monolith.md", "/mock/vault")
        
        assert success is True
        # Verify both files created
        assert "/mock/vault/Silence.md" in mock_files
        assert "/mock/vault/Stun.md" in mock_files
        
        # Verify frontmatter is prepended to each file
        silence_content = "".join(mock_files["/mock/vault/Silence.md"])
        assert silence_content.startswith(frontmatter)
        assert "# Silence" in silence_content
        
        stun_content = "".join(mock_files["/mock/vault/Stun.md"])
        assert stun_content.startswith(frontmatter)
        assert "# Stun" in stun_content
