from datetime import datetime
from typing import Any, Dict


class RuntimeContext:
    """Collect deterministic runtime information for context assembly."""

    @staticmethod
    def collect() -> Dict[str, Any]:
        """Return a minimal runtime context snapshot."""
        now = datetime.now()
        return {
            "current_datetime": now.isoformat(timespec="seconds"),
            "current_date": now.date().isoformat(),
            "current_time": now.time().strftime("%H:%M:%S"),
        }
