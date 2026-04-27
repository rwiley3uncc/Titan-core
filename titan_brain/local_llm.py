"""Local LLM integration for Titan.

This module routes Titan's reply generation through a local Ollama server,
so normal local use does not require an OPENAI_API_KEY.
"""

import os

import requests

OLLAMA_URL = os.getenv("TITAN_OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("TITAN_OLLAMA_MODEL", "llama3")


def generate_local_reply(prompt: str, system_prompt: str = "") -> str:
    """Generate a non-streaming reply from the configured local Ollama model."""
    full_prompt = prompt

    if system_prompt:
        full_prompt = (
            f"System instructions:\n{system_prompt}\n\n"
            f"User/task prompt:\n{prompt}"
        )

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": full_prompt,
        "stream": False,
    }

    print("Using local Ollama model")
    response = requests.post(OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()

    data = response.json()
    return data.get("response", "").strip()
