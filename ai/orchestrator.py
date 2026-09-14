import re
from typing import Any, Callable, Dict, List, Optional

from ai.brain import AIBrain
from context import ContextEngine
from memory import MemoryManager
from ai.errors import AIPlanningError, AIServiceError
from ai.action_policy import ActionPolicy, ActionPolicyError
from ai.task_execution import execute_task
from ai.plan_schema import validate_plan


class AIOrchestrator:
    """Minimal orchestration layer that converts natural-language input into executor actions."""

    def __init__(
        self,
        brain: Optional[AIBrain] = None,
        context_engine: Optional[ContextEngine] = None,
        action_policy: Optional[ActionPolicy] = None,
    ):
        self.memory_manager = MemoryManager()
        self.context_engine = context_engine or ContextEngine(self.memory_manager)
        self.brain = brain
        self.action_policy = action_policy or ActionPolicy()

    def build_context(self, command: str) -> Any:
        print("[AI] Building context")
        return self.context_engine.build_context(
            user_context={"raw_command": command},
            system_context={"mode": "ai"},
            query=command,
        )

    def validate_plan(self, plan):
        return validate_plan(plan)["actions"]

    def handle_command(self, command: str) -> List[Dict[str, Any]]:
        print("[AI] Received natural-language command: [content omitted]")
        context = self.build_context(command)
        print("[AI] Calling AIBrain")
        if self.brain is None:
            self.brain = AIBrain()
        try:
            plan = self.brain.plan(command, context)
            validated_actions = self.validate_plan(plan)
            context_data = context.to_dict() if hasattr(context, "to_dict") else context
            preferred = (context_data or {}).get("system_context", {}).get("browsers", {}).get("preferred")
            validated_actions = self.action_policy.validate(validated_actions, preferred_browser=preferred)
            for action in validated_actions:
                if action["action"] == "draft_email":
                    if not re.search(r"\b(?:draft|compose|prepare)\b", command, re.IGNORECASE):
                        raise ActionPolicyError("Email preparation requires an explicit draft, compose, or prepare request.")
                    if re.search(r"(?:^|\bthen\s+|\band\s+)(?:please\s+)?send\b", command.strip(), re.IGNORECASE):
                        raise ActionPolicyError("Sending email is not supported.")
                    # Extractive first version: do not execute invented content.
                    normalized = " ".join(command.split()).casefold()
                    for value in action["params"].values():
                        if value and " ".join(value.split()).casefold() not in normalized:
                            raise ActionPolicyError("Email fields must come from the user's command.")
                    recipient = action["params"]["to"]
                    address_chars = r"[\w.!#$%&'*+/=?^_`{|}~@-]"
                    if recipient and not re.search(
                        rf"(?<!{address_chars}){re.escape(recipient)}(?!{address_chars})",
                        command, re.IGNORECASE,
                    ):
                        raise ActionPolicyError("Email recipient must match an address supplied by the user.")
        except ActionPolicyError:
            print("[AI] Command failed: action rejected by safety policy")
            raise
        except AIServiceError:
            print("[AI] Command failed: AI service unavailable or returned an unusable plan")
            raise
        except ValueError as exc:
            print("[AI] Command failed: AI service unavailable or returned an unusable plan")
            raise AIPlanningError("AI returned an unusable response.") from exc
        print(f"[AI] Received validated action plan with {len(validated_actions)} action(s)")
        for index, action in enumerate(validated_actions, start=1):
            if action["action"] == "draft_email":
                print(f"[AI] Action {index}: action=draft_email, target=gmail, params=[redacted]")
                continue
            print(
                f"[AI] Action {index}: action={action['action']}, "
                f"target={action['target']}, params={action['params']}"
            )
        return validated_actions


def process_natural_language_command(
    command: str,
    executor_func: Optional[Callable[[Dict[str, Any]], None]] = None,
    brain: Optional[AIBrain] = None,
    context_engine: Optional[ContextEngine] = None,
) -> List[Dict[str, Any]]:
    orchestrator = AIOrchestrator(brain=brain, context_engine=context_engine)
    actions = orchestrator.handle_command(command)

    dispatcher = executor_func
    if dispatcher is None:
        from executor import execute as default_execute
        dispatcher = default_execute

    execute_task(actions, dispatcher)

    return actions
