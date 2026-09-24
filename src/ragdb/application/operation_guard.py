"""Hold the runtime's mutation lease for an entire application operation."""

from contextlib import nullcontext
from functools import wraps


def guarded_mutation(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        gate = self.operation_gate.ingestion() if self.operation_gate is not None else nullcontext()
        with gate:
            return method(self, *args, **kwargs)

    return wrapped
