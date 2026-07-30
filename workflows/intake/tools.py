"""Tier 2 deterministic prefix table and the Tier 3 bound tool. See
openspec/changes/build-intake-workflow/design.md.
"""
from typing import Optional

from langchain_core.tools import tool

from gateway.schemas import Intent

# Exact, case-sensitive prefix match, checked before any model call.
# Prefixes mirror Intent's own values -- no separate vocabulary, no
# prefix reserved for an intent that doesn't exist yet.
TIER2_PREFIXES: dict[str, Intent] = {f"{intent.value}: ": intent for intent in Intent}


def match_tier2_prefix(raw_text: str) -> Intent | None:
    for prefix, intent in TIER2_PREFIXES.items():
        if raw_text.startswith(prefix):
            return intent
    return None


@tool
def select_intent(
    intent: Optional[Intent] = None, clarifying_question: Optional[str] = None
) -> str:
    """Resolve the user's request to exactly one intent from the
    candidates given in the prompt, or set clarifying_question instead
    if none fit clearly. Never invent an intent outside the given
    list.
    """
    return f"intent={intent} clarifying_question={clarifying_question}"
