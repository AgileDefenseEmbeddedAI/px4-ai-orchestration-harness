"""
Dispatch authorization gate.

Ensures no vehicle commands are issued without a recorded authorization event.
Any code path that calls dispatch must pass through require_authorization first.
"""


class UnauthorizedDispatchError(Exception):
    """Raised when dispatch is attempted without a recorded authorization event."""


def require_authorization(mission_id: str) -> None:
    """Raise UnauthorizedDispatchError if no authorization_granted event exists for mission_id."""
    from harness.audit.logger import has_authorization_event

    if not has_authorization_event(mission_id):
        raise UnauthorizedDispatchError(
            f"Mission {mission_id} has no recorded authorization event; dispatch blocked"
        )
