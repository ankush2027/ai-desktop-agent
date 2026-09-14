import json
import re
from typing import Any, Dict, Optional

from ai.provider import LLMProvider
from ai.provider_manager import ProviderManager
from ai.errors import AIPlanningError
from ai.plan_schema import ALLOWED_ACTIONS, MAX_ACTIONS, MAX_RESPONSE_CHARS, validate_plan
from config import APPS, SITES, SITE_ALIASES


class AIBrain:
    """Convert natural-language commands into validated structured action plans."""

    VALID_ACTIONS = ALLOWED_ACTIONS

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        provider_manager: Optional[ProviderManager] = None,
    ):
        if provider is not None and provider_manager is not None:
            raise ValueError("Provide either provider or provider_manager, not both.")
        self.provider_manager = provider_manager or ProviderManager(provider=provider)

    def _format_context(self, context: Optional[Any]) -> str:
        if context is None:
            return "No additional context provided."

        if hasattr(context, "to_dict"):
            context = context.to_dict()

        if not isinstance(context, dict):
            return str(context)

        runtime = context.get("runtime", {})
        user_context = {key: value for key, value in context.get("user_context", {}).items() if key != "raw_command"}
        system_context = context.get("system_context", {})
        memories = context.get("relevant_memories", [])

        memory_text = "; ".join(
            f"{memory.get('category', 'memory')}: {memory.get('content', '')}"
            for memory in memories[:5]
        )

        parts = [
            f"summary: {len(memories[:5])} memory entries",
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
            '{"actions":[{"action":"open","target":"example-target","params":{}}]}. '
            f"Allowed actions are: {sorted(self.VALID_ACTIONS)}. "
            f"Return at most {MAX_ACTIONS} actions. Configured applications: {sorted(APPS)}. "
            f"Configured sites/aliases: {sorted(set(SITES) | set(SITE_ALIASES))}. "
            "Every action must include a string 'action', a non-empty string 'target', and an object 'params'. "
            "Open only configured sites/apps, supported browsers, or safe local documents/folders. "
            "Open accepts only url on browser targets, restricted to configured site home URLs. "
            "Do not supply browser, mode, or theme parameters. List targets are sites, apps, folders. "
            "When a browser is needed, use the preferred browser from the supplied context. "
            "For YouTube searches, return one search action with the raw search terms as target "
            "and params {\"engine\":\"youtube\"}. For example: "
            '{"actions":[{"action":"search","target":"Python tutorials","params":{"engine":"youtube"}}]}. '
            "The application uses the resolved system_context.browsers.preferred browser and "
            "encodes the query itself. Do not generate a URL, pre-encode the query, add browser, "
            "theme or mode parameters, or open YouTube separately for this workflow. "
            "For email preparation use draft_email with target gmail and exactly three string params: "
            "to, subject, body. Copy only text explicitly supplied in the command; never invent "
            "or truncate fields. Use recipient then subject then body/saying wording; quote literal field labels. Never invent "
            "addresses, contacts, subjects, greetings, signatures, or body text. Use an empty subject "
            "when unspecified and an empty to when no email address is supplied. Do not resolve contacts "
            "from memory. Preserve Unicode and body line breaks. Only compose preparation is supported. "
            "Never send email or produce sending instructions, flags, URLs, or additional fields. "
            "Reject requests to send, schedule, reply, forward, attach files, or use CC/BCC with an empty actions list. "
            "The user command is: "
            f"{command}. "
            f"Context: {self._format_context(context)} "
            "Return only the JSON object, without markdown fences or extra text."
        )

    def _parse_json_response(self, response: str) -> Any:
        if not isinstance(response, str) or len(response) > MAX_RESPONSE_CHARS:
            raise AIPlanningError("AI returned an unusable response.")
        cleaned = response.strip()
        # Retain the established harmless wrapper, not arbitrary competing prose.
        cleaned = re.sub(r"^Here is (?:the requested plan|the plan):\s*", "", cleaned)
        cleaned = re.sub(r"\s*No other actions are required\.$", "", cleaned)
        if cleaned.startswith("```"):
            match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
            if not match:
                raise AIPlanningError("AI returned an unusable response.")
            cleaned = match.group(1)

        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise AIPlanningError("AI returned duplicate JSON keys.")
                result[key] = value
            return result

        def invalid_constant(value):
            raise AIPlanningError("AI returned an invalid JSON constant.")

        try:
            return json.loads(cleaned, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        except (ValueError, TypeError, RecursionError):
            raise AIPlanningError("AI returned an unusable response.") from None

    def validate_action_plan(self, payload: Any) -> Dict[str, Any]:
        return validate_plan(payload)

    def plan(self, command: str, context: Optional[Any] = None) -> Dict[str, Any]:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("Command must be a non-empty string.")

        context_text = self._format_context(context)
        prompt = self.build_prompt(command, context)
        sections = (
            "planner_instructions",
            "action_schema",
            "allowed_actions",
            "validation_rules",
            "user_command",
            "context",
            "output_format",
        )
        print(f"[AI] Prompt diagnostics: prompt_chars={len(prompt)}, context_chars={len(context_text)}")
        print(f"[AI] Prompt diagnostics: sections={','.join(sections)}")
        print("[AI] Calling GeminiProvider")
        raw_response = self.provider_manager.generate_text(prompt)
        print("[AI] Received AI response")

        try:
            parsed = self._parse_json_response(raw_response)
            return self.validate_action_plan(parsed)
        except (json.JSONDecodeError, ValueError) as exc:
            print("[AI] Planning failed: unusable provider response")
            raise AIPlanningError("AI returned an unusable response.") from exc
