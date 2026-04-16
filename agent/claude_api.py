"""
agent/claude_api.py

Handles communication with the Claude API.
- call_claude: sends a prompt to Claude and returns a parsed JSON response
"""

import anthropic
import json
import os
from dotenv import load_dotenv

load_dotenv()


def call_claude(prompt: str) -> dict:
    """
    Send a prompt to Claude and return a parsed JSON response.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment.")

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8096,
        messages=[{"role": "user", "content": prompt}],
    )

    text_parts = []
    for block in message.content:
        if hasattr(block, "text"):
            text_parts.append(block.text)

    raw = "\n".join(text_parts).strip()

    # Handle accidental markdown fences
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude did not return valid JSON.\nRaw response:\n{raw}") from e