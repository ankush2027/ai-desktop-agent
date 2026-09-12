class AIServiceError(ValueError):
    """Base class for controlled AI failures safe to surface to the CLI."""


class AIProviderError(AIServiceError):
    """The active provider could not complete a request."""


class AIPlanningError(AIServiceError):
    """The provider response could not be converted into a valid action plan."""
