"""Pick which AI runs SSC, based on the key saved with ./add_key.sh."""

import os


def make_agent(effort: str = "high", on_tool_call=None):
    """Return (agent, name). A Google key wins if both are saved."""
    if os.environ.get("GEMINI_API_KEY"):
        from gemini_agent import GeminiAgent
        return GeminiAgent(on_tool_call=on_tool_call), "Google Gemini"
    from agent import Agent
    return Agent(effort=effort, on_tool_call=on_tool_call), "Claude"


def provider_name() -> str:
    return "Google Gemini" if os.environ.get("GEMINI_API_KEY") else "Claude"
