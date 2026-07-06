import pytest
from unittest.mock import MagicMock
from google.genai import types

from app.agent import (
    root_agent,
    _sanitise_input,
    _before_agent_callback,
    _extract_text,
)
from app.tools.clinic_mcp_server import lookup_clinic, _CLINICS


# ============================================================================
# 1. MCP Clinic Server Tests
# ============================================================================

def test_lookup_clinic_match():
    # Riverside Community Health Center is at 90011
    result = lookup_clinic("90011", "primary care")
    assert result["matched"] is True
    assert result["clinic"]["name"] == "Riverside Community Health Center"
    assert result["need"] == "primary care"
    assert "Riverside Community Health Center" in result["note"]


def test_lookup_clinic_no_match():
    # 00000 should not match any clinic
    result = lookup_clinic("00000", "dental")
    assert result["matched"] is False
    assert result["clinic"] is None
    assert result["need"] == "dental"
    assert "no clinics on file for ZIP code 00000" in result["note"]


def test_lookup_clinic_normalisation():
    # Test spaces and trailing/leading characters padding
    result = lookup_clinic("  90011  ", "primary care")
    assert result["matched"] is True
    assert result["clinic"]["name"] == "Riverside Community Health Center"

    # Test zero-padding (e.g. 77002 is entered as "77002", or "00002" should normalise to 5 digits)
    result_padded = lookup_clinic("7702", "primary care")
    # should zero-pad to "07702", which won't match, but normalises to 5 digits without error
    assert result_padded["matched"] is False
    assert "07702" in result_padded["note"]


# ============================================================================
# 2. Input Sanitisation Tests
# ============================================================================

@pytest.mark.parametrize(
    "input_val, expected",
    [
        ("Find a clinic near ZIP 90011", "Find a clinic near ZIP 90011"),
        ("What's open at 9:30? (primary care)", "What's open at 9:30? (primary care)"),
        ("  spaces  ", "spaces"),
    ]
)
def test_sanitise_input_clean(input_val, expected):
    assert _sanitise_input(input_val) == expected


def test_sanitise_input_dangerous_chars():
    # Test prompt injection and shell character removal
    injected = 'What;{"zipcode":"drop"}|rm -rf /`tag`\\x'
    cleaned = _sanitise_input(injected)
    # Check that dangerous control/JSON punctuation is stripped
    for char in [";", "{", "}", "|", "`", "\\"]:
        assert char not in cleaned


def test_sanitise_input_length_truncation():
    # Input over 500 characters should be truncated
    long_input = "a" * 600
    cleaned = _sanitise_input(long_input)
    assert len(cleaned) <= 500


def test_sanitise_input_whitespace_normalisation():
    assert _sanitise_input("multiple      spaces\n\tnewlines") == "multiple spaces newlines"


# ============================================================================
# 3. Before Agent Callback (Sanitisation & Abort) Tests
# ============================================================================

def test_before_agent_callback_safe_input():
    # If the user input is clean, callback should return None (allowing pipeline to continue)
    mock_part = MagicMock()
    mock_part.text = "Help me find primary care near 90033."
    
    mock_user_content = MagicMock()
    mock_user_content.parts = [mock_part]
    
    mock_ctx = MagicMock()
    mock_ctx.user_content = mock_user_content
    
    result = _before_agent_callback(mock_ctx)
    assert result is None
    assert mock_part.text == "Help me find primary care near 90033."


def test_before_agent_callback_empty_input():
    # Empty input should short-circuit with a user-facing error Content object
    mock_part = MagicMock()
    mock_part.text = "   "
    
    mock_user_content = MagicMock()
    mock_user_content.parts = [mock_part]
    
    mock_ctx = MagicMock()
    mock_ctx.user_content = mock_user_content
    
    result = _before_agent_callback(mock_ctx)
    assert isinstance(result, types.Content)
    assert result.role == "model"
    assert len(result.parts) == 1
    assert "I didn't receive a question" in result.parts[0].text


def test_before_agent_callback_all_stripped():
    # Purely malicious/invalid characters that get completely stripped should abort
    mock_part = MagicMock()
    mock_part.text = ';{|}`\\'
    
    mock_user_content = MagicMock()
    mock_user_content.parts = [mock_part]
    
    mock_ctx = MagicMock()
    mock_ctx.user_content = mock_user_content
    
    result = _before_agent_callback(mock_ctx)
    assert isinstance(result, types.Content)
    assert result.role == "model"
    assert "Your message contained only special characters" in result.parts[0].text


# ============================================================================
# 4. Orchestrator and Pipeline Structure Tests
# ============================================================================

def test_orchestrator_subagents():
    assert len(root_agent.sub_agents) == 2
    assert root_agent.sub_agents[0].name == "research_agent"
    assert root_agent.sub_agents[1].name == "simplifier_agent"
    assert root_agent.before_agent_callback == _before_agent_callback


# ============================================================================
# 5. Extract Text Helper Tests
# ============================================================================

def test_extract_text_helper():
    class FakePart:
        def __init__(self, text):
            self.text = text

    class FakeContent:
        def __init__(self, role, parts):
            self.role = role
            self.parts = parts

    class FakeEvent:
        def __init__(self, role, text):
            self.content = FakeContent(role, [FakePart(text)])

    events = [
        FakeEvent("user", "What is the zipcode?"),
        FakeEvent("model", "We are searching..."),
        FakeEvent("model", "Here is Riverside Free Clinic details."),
    ]
    
    assert _extract_text(events) == "Here is Riverside Free Clinic details."
    assert _extract_text([]) == "(no model response)"
