class AgentCtxError(Exception):
    """Base exception for agentctx."""


class TamperDetectedError(AgentCtxError):
    """Raised when the observation log hash does not match the last audit entry."""


class ContextDriftWarning(UserWarning):
    """Raised when the current instruction deviates significantly from the task anchor."""
