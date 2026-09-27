"""Typed operational failures with stable public classifications."""
from enum import Enum


class ErrorClass(str, Enum):
    VALIDATION = 'validation'
    AUTHENTICATION = 'authentication'
    AUTHORIZATION = 'authorization'
    RATE_LIMIT = 'rate_limit'
    BUDGET = 'budget'
    PROVIDER_TRANSIENT = 'provider_transient'
    PROVIDER_PERMANENT = 'provider_permanent'
    CIRCUIT_OPEN = 'circuit_open'
    STORAGE = 'storage'
    INTERNAL = 'internal'


class OperationalError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        error_class: ErrorClass,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.error_class = error_class
        self.retryable = retryable


class ProviderBudgetError(OperationalError):
    def __init__(self) -> None:
        super().__init__(
            'Provider budget exhausted.',
            code='PROVIDER_BUDGET_EXHAUSTED',
            error_class=ErrorClass.BUDGET,
        )


class CircuitOpenError(OperationalError):
    def __init__(self, circuit_name: str) -> None:
        super().__init__(
            f'Circuit {circuit_name} is open.',
            code='PROVIDER_CIRCUIT_OPEN',
            error_class=ErrorClass.CIRCUIT_OPEN,
            retryable=True,
        )
