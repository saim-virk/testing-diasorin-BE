from rest_framework.exceptions import APIException


class TransitionError(APIException):
    """An action the request's current state does not allow (HTTP 409)."""

    status_code = 409
    default_code = "transition_not_allowed"

    def __init__(self, message: str, code: str = "transition_not_allowed"):
        super().__init__({"message": message, "code": code})


class StaleVersion(TransitionError):
    def __init__(self):
        super().__init__(
            "This request was changed in another tab or window. Reload the latest version.", "stale_version"
        )


class StepValidationError(Exception):
    """Field errors for one step. `errors` follows the backend convention:
    {"field": ["msg"], "lines": {0: {"lot_number": ["msg"]}, "non_field_errors": ["msg"]}}."""

    def __init__(self, step: int, errors: dict, failed_steps: list[int] | None = None):
        self.step, self.errors = step, errors
        self.failed_steps = failed_steps or [step]
        super().__init__(f"step {step}: {errors}")
