import json
import re
from typing import Any, Dict, Optional, Protocol

from ai.gemini import GeminiProvider


class AIProvider(Protocol):
    def generate_text(self, prompt: str) -> str:
        ...


class AIBrain:
    """Convert natural-language commands into validated structured action plans."""

    VALID_ACTIONS = {
        "open",
        "search",
        "list",
        "help",
        "exit",
        "create",
        "delete",
        "rename",
        "copy",
        "move",
    }

    def __init__(self, provider: Optional[AIProvider] = None):
        self.provider = provider or GeminiProvider()

    def _format_context(self, context: Optional[Any]) -> str:
        if context is None:
            return "No additional context provided."

        if hasattr(context, "to_dict"):
            context = context.to_dict()

        if not isinstance(context, dict):
            return str(context)

        runtime = context.get("runtime", {})
        user_context = context.get("user_context", {})
        system_context = context.get("system_context", {})
        summary = context.get("summary", "")
        memories = context.get("relevant_memories", [])

        memory_text = "; ".join(
            f"{memory.get('category', 'memory')}: {memory.get('content', '')}"
            for memory in memories[:5]
        )

        parts = [
            f"summary: {summary}" if summary else "summary: none",
            f"runtime: {runtime}",
            f"user_context: {user_context}",
            f"system_context: {system_context}",
            f"relevant_memories: {memory_text or 'none'}",
        ]

        return " | ".join(parts)

    def build_prompt(self, command: str, context: Optional[Any] = None) -> str:
        return (
            "You are a desktop command planner. "
            "Return only valid JSON. "
            "Do not execute commands. "
            "Do not generate Python, shell, filesystem, or code execution instructions. "
            "The JSON must match this schema: "
            '{"actions":[{"action":"open","target":"chrome","params":{}}]}. '
            f"Allowed actions are: {sorted(self.VALID_ACTIONS)}. "
            "Every action must include a string 'action', a non-empty string 'target', and an object 'params'. "
            "The user command is: "
            f"{command}. "
            f"Context: {self._format_context(context)} "
            "Return only the JSON object, without markdown fences or extra text."
        )

    def _strip_code_fence(self, response: str) -> str:
        cleaned = response.strip()
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return cleaned

    def validate_action_plan(self, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Action plan must be a JSON object.")

        actions = payload.get("actions")
        if not isinstance(actions, list):
            raise ValueError("Action plan must contain an 'actions' list.")
        if not actions:
            raise ValueError("Action plan cannot be empty.")

        normalized_actions = []
        for item in actions:
            if not isinstance(item, dict):
                raise ValueError("Each action must be an object.")

            action_name = item.get("action")
            if action_name not in self.VALID_ACTIONS:
                raise ValueError(f"Unsupported action: {action_name}")

            target = item.get("target")
            if not isinstance(target, str) or not target.strip():
                raise ValueError(f"Missing target for action: {action_name}")

            params = item.get("params", {})
            if not isinstance(params, dict):
                raise ValueError(f"Params for action {action_name} must be a dictionary.")

            normalized_actions.append(
                {
                    "action": action_name,
                    "target": target.strip(),
                    "params": params,
                }
            )

        return {"actions": normalized_actions}

    def plan(self, command: str, context: Optional[Any] = None) -> Dict[str, Any]:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("Command must be a non-empty string.")

        prompt = self.build_prompt(command, context)
        raw_response = self.provider.generate_text(prompt)
        cleaned_response = self._strip_code_fence(raw_response)

        try:
            parsed = json.loads(cleaned_response)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Gemini JSON response: {exc.msg}") from exc

        return self.validate_action_plan(parsed)
