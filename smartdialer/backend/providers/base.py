"""
Common interface for mock telecom providers.

A provider's job in this prototype is purely to decide, for one call
attempt, what sequence of events will be emitted and when -- including,
for the "bad" provider, injecting duplicates and reordering events to
exercise the idempotency / out-of-order handling in call_allocator.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List


@dataclass
class RawEvent:
    event_id: str
    event_type: str       # RINGING | CONNECTED | FAILED | COMPLETED
    emitted_at: datetime   # provider's own clock -- used to detect out-of-order delivery
    delay_seconds: float   # simulated network/processing delay before WE receive it


class BaseProvider:
    name: str = "base"

    def plan_call_events(self, call_id: str, answer_rate: float) -> List[RawEvent]:
        """
        Returns the full event sequence a real provider would eventually
        deliver for this call attempt (in the order they'll actually
        ARRIVE at our system, which for provider_b may not be the order
        they logically occurred in -- that's the point).
        """
        raise NotImplementedError

    def _rng_answered(self, answer_rate: float) -> bool:
        return random.random() < answer_rate
