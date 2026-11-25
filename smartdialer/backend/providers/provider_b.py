import random
import uuid
from datetime import datetime, timedelta

from .base import BaseProvider, RawEvent


class ProviderB(BaseProvider):
    """
    Slow, occasional timeouts, and -- deliberately, to exercise failure
    handling -- duplicate events and events that ARRIVE out of the order
    they logically occurred in (e.g. a retried RINGING notification that
    lands after CONNECTED already has).
    """

    name = "provider_b"

    FAILURE_RATE = 0.15
    TIMEOUT_RATE = 0.10
    DUPLICATE_PROB = 0.35
    REORDER_PROB = 0.25

    def plan_call_events(self, call_id: str, answer_rate: float):
        now = datetime.utcnow()
        events = [RawEvent(f"evt-{uuid.uuid4().hex[:8]}", "RINGING", now, delay_seconds=1.5)]

        if self._rng_answered(self.TIMEOUT_RATE):
            # Provider never confirms -- call will be timed out by the allocator.
            return events

        if self._rng_answered(self.FAILURE_RATE):
            events.append(RawEvent(f"evt-{uuid.uuid4().hex[:8]}", "FAILED", now + timedelta(seconds=2), 2.5))
        elif self._rng_answered(answer_rate):
            events.append(RawEvent(f"evt-{uuid.uuid4().hex[:8]}", "CONNECTED", now + timedelta(seconds=2), 2.2))
            events.append(RawEvent(f"evt-{uuid.uuid4().hex[:8]}", "COMPLETED", now + timedelta(seconds=6), 3.5))
        else:
            events.append(RawEvent(f"evt-{uuid.uuid4().hex[:8]}", "FAILED", now + timedelta(seconds=2), 2.5))

        # Inject a duplicate of a random already-planned event (same event_id
        # so the idempotency ledger must catch it).
        if events and random.random() < self.DUPLICATE_PROB:
            original = random.choice(events)
            dup_delay = original.delay_seconds + random.uniform(0.1, 0.8)
            events.append(RawEvent(original.event_id, original.event_type, original.emitted_at, dup_delay))

        # Simulate out-of-order ARRIVAL: shuffle delay_seconds slightly so a
        # logically-earlier event can physically arrive after a later one,
        # even though emitted_at still reflects the true logical order.
        if len(events) > 1 and random.random() < self.REORDER_PROB:
            i, j = random.sample(range(len(events)), 2)
            events[i].delay_seconds, events[j].delay_seconds = events[j].delay_seconds, events[i].delay_seconds

        return events
