"""Captures every LLM call's input/output/tokens/latency/outcome for
observability and evals, via litellm's own callback hooks -- see
openspec/changes/migrate-to-langgraph/specs/langgraph-agent-runtime/spec.md's
"Every LLM call is captured for observability" requirement.

Uses litellm.integrations.custom_logger.CustomLogger (verified real,
log_success_event/log_failure_event(self, kwargs, response_obj,
start_time, end_time) signature, confirmed by direct introspection of
the installed package) rather than the older bare-function callback
style -- this fires for every call made through ChatLiteLLM regardless
of which node or provider made it, since ChatLiteLLM calls straight
through to litellm.completion()/acompletion() underneath.
"""
import json
import sqlite3

import litellm
from litellm.integrations.custom_logger import CustomLogger


class LLMObservabilityLogger(CustomLogger):
    """Writes one row per LLM call to llm_call_logs in the same SQLite
    file gateway/tool_dispatcher.py already opens. Never raises --
    a logging failure must not break the LLM call it's observing."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_call_logs (
                    call_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    model TEXT,
                    role TEXT,
                    prompt_messages TEXT,
                    response_text TEXT,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    total_tokens INTEGER,
                    latency_ms REAL,
                    success INTEGER,
                    error TEXT
                )
                """
            )

    def _write(self, kwargs, response_obj, start_time, end_time, success: bool, error: str = None):
        try:
            latency_ms = (end_time - start_time).total_seconds() * 1000
            usage = getattr(response_obj, "usage", None)
            model = kwargs.get("model")
            messages = kwargs.get("messages", [])
            response_text = None
            if success and response_obj is not None:
                choices = getattr(response_obj, "choices", None)
                if choices:
                    response_text = getattr(choices[0].message, "content", None)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """INSERT INTO llm_call_logs
                       (model, role, prompt_messages, response_text,
                        prompt_tokens, completion_tokens, total_tokens,
                        latency_ms, success, error)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        model,
                        kwargs.get("litellm_params", {}).get("metadata", {}).get("role"),
                        json.dumps(messages),
                        response_text,
                        getattr(usage, "prompt_tokens", None),
                        getattr(usage, "completion_tokens", None),
                        getattr(usage, "total_tokens", None),
                        latency_ms,
                        int(success),
                        error,
                    ),
                )
        except Exception:  # noqa: BLE001 -- observability must never break the real call
            pass

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._write(kwargs, response_obj, start_time, end_time, success=True)

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        error = str(kwargs.get("exception", "unknown error"))
        self._write(kwargs, response_obj, start_time, end_time, success=False, error=error)


def register_llm_observability(db_path: str) -> LLMObservabilityLogger:
    """Registers one LLMObservabilityLogger instance as a litellm
    global callback. Idempotent-ish: called once at graph-build time
    (workflows/drafting/graph.py), not per-node."""
    logger = LLMObservabilityLogger(db_path)
    litellm.callbacks = [logger]
    return logger
