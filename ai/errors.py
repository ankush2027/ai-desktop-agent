class AIServiceError(ValueError):
    """Base class for controlled AI failures safe to surface to the CLI."""


class AIProviderError(AIServiceError):
    """The active provider could not complete a request."""

    def __init__(self, message, *, transient=False):
        super().__init__(message)
        self.transient = transient


class AIPlanningError(AIServiceError):
    """The provider response could not be converted into a valid action plan."""


class TaskExecutionError(AIServiceError):
    """A task step failed during application-owned execution."""
