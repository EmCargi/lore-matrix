import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.utils import clean_reasoning_response


def test_strips_reasoning_tags():
    raw = (
        '1 This is the hidden reasoning trace from deepseek-r1. 2 The scene is a cafe.\n'
        ' response'
        '{"entries": [{"Speaker": "A", "Dialogue": "Hi", "Scene Description": "Cafe"}]}'
    )
    cleaned = clean_reasoning_response(raw)
    assert cleaned == '{"entries": [{"Speaker": "A", "Dialogue": "Hi", "Scene Description": "Cafe"}]}'


def test_isolates_json_from_surrounding_text():
    raw = 'Some preamble text{"entries": []}some trailing prose'
    cleaned = clean_reasoning_response(raw)
    assert cleaned == '{"entries": []}'


def test_strips_code_fences():
    raw = '```json\n{"entries": []}\n```'
    cleaned = clean_reasoning_response(raw)
    assert cleaned == '{"entries": []}'


def test_plain_json_passthrough():
    raw = '{"entries": []}'
    assert clean_reasoning_response(raw) == raw