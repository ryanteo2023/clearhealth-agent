import sys
sys.path.insert(0, '.')

from app.agent import (
    root_agent, _runner,
    _sanitise_input, _before_agent_callback,
    _extract_text,
)
from google.adk.agents import SequentialAgent
from google.adk.runners import InMemoryRunner

# 1. Types
assert isinstance(root_agent, SequentialAgent), "root_agent must be SequentialAgent"
assert isinstance(_runner, InMemoryRunner)
print("[PASS] root_agent is SequentialAgent")
print("[PASS] _runner is InMemoryRunner")

# 2. Sub-agent pipeline order
names = [a.name for a in root_agent.sub_agents]
assert names == ["research_agent", "simplifier_agent"], f"Wrong order: {names}"
print("[PASS] sub_agents order:", names)

# 3. Callback attached
assert root_agent.before_agent_callback is not None
print("[PASS] before_agent_callback is attached")

# 4. Sanitiser: clean input passes through unchanged
result = _sanitise_input("Find a clinic near ZIP 90011")
assert result == "Find a clinic near ZIP 90011", repr(result)
print("[PASS] sanitiser: clean input unchanged")

# 5. Sanitiser: strips injection characters
injected = 'What;{"zipcode":"drop"}|rm -rf /'
cleaned = _sanitise_input(injected)
assert "{" not in cleaned and ";" not in cleaned and "|" not in cleaned
print("[PASS] sanitiser: strips injection chars ->", repr(cleaned))

# 6. Sanitiser: preserves allowed punctuation
query = "What's open at 9:30? (primary care)"
cleaned2 = _sanitise_input(query)
assert cleaned2 == query, f"Allowed chars were stripped: {cleaned2!r}"
print("[PASS] sanitiser: preserves allowed punctuation ->", repr(cleaned2))

# 7. Sanitiser: truncates long input
long_input = "a" * 600
assert len(_sanitise_input(long_input)) <= 500
print("[PASS] sanitiser: truncates to 500 chars")

# 8. Sanitiser: whitespace-only becomes empty
assert _sanitise_input("   ") == ""
print("[PASS] sanitiser: whitespace-only -> empty string")

# 9. _extract_text: pulls last model text from event list
class _FakePart:
    def __init__(self, text): self.text = text
class _FakeContent:
    def __init__(self, role, parts): self.role = role; self.parts = parts
class _FakeEvent:
    def __init__(self, role, text): self.content = _FakeContent(role, [_FakePart(text)])

events = [
    _FakeEvent("user", "hello"),
    _FakeEvent("model", "First model reply"),
    _FakeEvent("model", "Final model reply"),
]
extracted = _extract_text(events)
assert extracted == "Final model reply", repr(extracted)
print("[PASS] _extract_text: returns last model reply ->", repr(extracted))

# 10. _extract_text: handles empty list
assert _extract_text([]) == "(no model response)"
print("[PASS] _extract_text: empty list -> fallback string")

print()
print("All 10 checks passed.")
