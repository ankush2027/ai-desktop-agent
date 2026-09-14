from typing import Any, Callable, Dict, List, Optional

from ai.brain import AIBrain
from context import ContextEngine
from memory import MemoryManager
from ai.errors import AIPlanningError, AIServiceError
from ai.action_policy import ActionPolicy, ActionPolicyError
from ai.task_execution import execute_task
from ai.plan_schema import validate_plan
from memory.errors import MemoryStorageError
from logger import safe_target
from actions.email import validate_email_provenance


class AIOrchestrator:
    """Minimal orchestration layer that converts natural-language input into executor actions."""

    def __init__(
        self,
        brain: Optional[AIBrain] = None,
        context_engine: Optional[ContextEngine] = None,
        action_policy: Optional[ActionPolicy] = None,
    ):
        self.context_engine = context_engine
        self.brain = brain
        self.action_policy = action_policy or ActionPolicy()

    def build_context(self, command: str) -> Any:
        print("[AI] Building context")
        if self.context_engine is not None:
            return self.context_engine.build_context(
                user_context={"raw_command": command}, system_context={"mode": "ai"}, query=command,
            )
        with MemoryManager() as manager:
            return ContextEngine(manager).build_context(
                user_context={"raw_command": command}, system_context={"mode": "ai"}, query=command,
            )

    def validate_plan(self, plan):
        return validate_plan(plan)["actions"]

    def handle_command(self, command: str) -> List[Dict[str, Any]]:
        print("[AI] Received natural-language command: [content omitted]")
        try:
            context = self.build_context(command)
            print("[AI] Calling AIBrain")
            if self.brain is None:
                self.brain = AIBrain()
            plan = self.brain.plan(command, context)
            validated_actions = self.validate_plan(plan)
            context_data = context.to_dict() if hasattr(context, "to_dict") else context
            preferred = (context_data or {}).get("system_context", {}).get("browsers", {}).get("preferred")
            validated_actions = self.action_policy.validate(validated_actions, preferred_browser=preferred)
            for action in validated_actions:
                if action["action"] == "draft_email":
                    try:
                        validate_email_provenance(command, action["params"])
                    except ValueError as exc:
                        raise ActionPolicyError(str(exc)) from None
        except MemoryStorageError:
            raise AIPlanningError("Memory context is unavailable.") from None
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
                f"target={safe_target(action['action'], action['target'])}, params=[redacted]"
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
