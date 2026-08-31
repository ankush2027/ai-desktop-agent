from typing import Any, Callable, Dict, List, Optional

from ai.brain import AIBrain
from context import ContextEngine
from memory import MemoryManager


class AIOrchestrator:
    """Minimal orchestration layer that converts natural-language input into executor actions."""

    def __init__(self, brain: Optional[AIBrain] = None, context_engine: Optional[ContextEngine] = None):
        self.memory_manager = MemoryManager()
        self.context_engine = context_engine or ContextEngine(self.memory_manager)
        self.brain = brain or AIBrain()

    def build_context(self, command: str) -> Any:
        return self.context_engine.build_context(
            user_context={"raw_command": command},
            system_context={"mode": "ai"},
            query=command,
        )

    def validate_plan(self, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(plan, dict):
            raise ValueError("AI plan must be a dictionary.")

        actions = plan.get("actions")
        if not isinstance(actions, list):
            raise ValueError("AI plan must contain an 'actions' list.")

        if not actions:
            raise ValueError("AI plan cannot be empty.")

        validated = []
        for item in actions:
            if not isinstance(item, dict):
                raise ValueError("Each action in the AI plan must be an object.")
            if not isinstance(item.get("action"), str) or not item["action"].strip():
                raise ValueError("Each AI action must contain a valid 'action' string.")
            if not isinstance(item.get("target"), str) or not item["target"].strip():
                raise ValueError(f"Action '{item.get('action')}' is missing a valid 'target'.")
            params = item.get("params", {})
            if not isinstance(params, dict):
                raise ValueError(f"Action '{item.get('action')}' has invalid params.")
            validated.append({"action": item["action"].strip(), "target": item["target"].strip(), "params": params})

        return validated

    def handle_command(self, command: str) -> List[Dict[str, Any]]:
        context = self.build_context(command)
        plan = self.brain.plan(command, context)
        return self.validate_plan(plan)


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

    for action in actions:
        dispatcher(action)

    return actions
