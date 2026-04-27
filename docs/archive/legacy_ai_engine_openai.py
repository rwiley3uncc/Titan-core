"""Archived legacy OpenAI engine.

This was the old unused OpenAI engine.
The active Titan brain now uses titan_core/brain.py with
titan_brain/local_llm.py and Ollama.
This file is archived for reference only.
"""

import os
from openai import OpenAI


class AIEngine:
    """
    Handles communication between Titan and the AI model.
    """

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        self.client = OpenAI(api_key=api_key)

    def ask(self, prompt: str) -> str:
        """
        Send a prompt to the AI model and return the response text.
        """
        response = self.client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )

        return response.output_text
