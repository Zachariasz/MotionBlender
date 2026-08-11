"""Small in-memory diagnostics buffer; disk output is explicit only."""

from __future__ import absolute_import

import json
import threading
import time
from collections import deque


class Diagnostics(object):
    def __init__(self, capacity=500):
        self._records = deque(maxlen=capacity)
        self._lock = threading.RLock()

    def record(self, event, feature_id=None, **data):
        record = {
            "time": time.time(),
            "event": event,
            "feature_id": feature_id,
            "data": data,
        }
        with self._lock:
            self._records.append(record)
        return record

    def snapshot(self):
        with self._lock:
            return list(self._records)

    def export(self, path, extra=None):
        payload = {
            "generated_at": time.time(),
            "records": self.snapshot(),
        }
        if extra:
            payload.update(extra)
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, default=str)
        return path
