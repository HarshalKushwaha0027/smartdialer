import uuid
from datetime import datetime, timedelta

from .base import BaseProvider, RawEvent


class ProviderA(BaseProvider):
    """Fast, reliable, low failure rate. Events always arrive in order, no duplicates."""

    name = "provider_a"

    FAILURE_RATE = 0.03  # independent of answer rate -- e.g. network reject

    def plan_call_events(self, call_id: str, answer_rate: float):
        now = datetime.utcnow()
        events = [RawEvent(f"evt-{uuid.uuid4().hex[:8]}", "RINGING", now, delay_seconds=0.2)]

        if self._rng_answered(self.FAILURE_RATE):
            events.append(RawEvent(f"evt-{uuid.uuid4().hex[:8]}", "FAILED", now + timedelta(seconds=1), 0.6))
            return events

        if self._rng_answered(answer_rate):
            events.append(RawEvent(f"evt-{uuid.uuid4().hex[:8]}", "CONNECTED", now + timedelta(seconds=1), 0.6))
            events.append(RawEvent(f"evt-{uuid.uuid4().hex[:8]}", "COMPLETED", now + timedelta(seconds=4), 1.0))
        else:
            events.append(RawEvent(f"evt-{uuid.uuid4().hex[:8]}", "FAILED", now + timedelta(seconds=1), 0.6))
        return events
