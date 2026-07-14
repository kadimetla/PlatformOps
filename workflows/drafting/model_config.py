"""Loads per-role model identifiers from config/models.yaml, same
convention as agents/model_config.py's get_model(), but returns a
litellm-ready ChatLiteLLM instance instead of a bare model string --
see openspec/changes/migrate-to-langgraph/design.md's "Model-agnosticism
via langchain_litellm.ChatLiteLLM" decision.
"""
import os

import yaml
from langchain_litellm import ChatLiteLLM

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "models.yaml")

# config/models.yaml stores bare model names (e.g. "gemini-2.5-flash").
# litellm needs an explicit provider prefix to avoid ambiguity -- unlike
# init_chat_model, which silently infers "gemini-..." as Vertex AI by
# default (a real gotcha this project's own Google AI Studio setup,
# README.md's GOOGLE_API_KEY, would have hit). Extend this map if a
# non-Gemini model is ever added to models.yaml.
_MODEL_PREFIX_BY_FAMILY = {
    "gemini": "gemini",
}


def _to_litellm_model_string(bare_model: str) -> str:
    for family, prefix in _MODEL_PREFIX_BY_FAMILY.items():
        if bare_model.startswith(family):
            return f"{prefix}/{bare_model}"
    raise ValueError(
        f"No litellm provider prefix known for model '{bare_model}' -- "
        f"add it to _MODEL_PREFIX_BY_FAMILY in {__file__}"
    )


def get_model(role: str) -> ChatLiteLLM:
    """Return a ChatLiteLLM instance configured for an agent role
    (routing, execution, review, orchestration), reading the same
    config/models.yaml agents/model_config.py already reads."""
    with open(_CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    if role not in config:
        raise KeyError(f"No model configured for role '{role}' in {_CONFIG_PATH}")
    bare_model = config[role]["model"]
    return ChatLiteLLM(model=_to_litellm_model_string(bare_model))
