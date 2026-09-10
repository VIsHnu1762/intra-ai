"""Select due projection events without changing explicit/manual retry behavior."""
from datetime import datetime, timezone


class DueProjectionEvents:
    """Narrow repository adapter for the worker, not a new evidence store."""
    def __init__(self, repository):
        self.repository = repository
        self.sb = repository.sb

    def __getattr__(self, name):
        return getattr(self.repository, name)

    async def events(self, key):
        now = datetime.now(timezone.utc)
        result = []
        for event in await self.repository.events(key):
            due = event.get("projection_next_attempt_at")
            if due is None:
                result.append(event)
                continue
            try:
                parsed = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
                if parsed.tzinfo is not None and parsed <= now:
                    result.append(event)
            except (TypeError, ValueError):
                # Invalid scheduling metadata cannot create an unbounded retry loop.
                continue
        return result
