"""Deprecated compatibility wrapper for Titan's local LLM adapter.

The active Ollama/local-model adapter now lives in Titan-AI. This wrapper stays
in place temporarily so older imports continue to resolve during migration.
"""

from __future__ import annotations

from titan_core.titan_ai_imports import enable_titan_ai_imports

enable_titan_ai_imports()

from titan_ai.local_llm import OLLAMA_MODEL, OLLAMA_URL, generate_local_reply
