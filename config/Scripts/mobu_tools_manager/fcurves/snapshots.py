"""Immutable selected-key capture for interactive FCurve operations."""

from __future__ import absolute_import


def _key_selected(curve, index):
    try:
        return bool(curve.KeyGetSelected(index))
    except Exception:
        pass
    try:
        return bool(curve.Keys[index].Selected)
    except Exception:
        return False


def _key_value(curve, index):
    try:
        return float(curve.Keys[index].Value)
    except Exception:
        return float(curve.KeyGetValue(index))


class KeySnapshot(object):
    def __init__(self, record, index, key, selected=True):
        self.record = record
        self.property = record.property
        self.curve = record.curve
        self.original_index = int(index)
        self.key = key
        self.original_time = int(key.Time.Get())
        self.original_value = _key_value(record.curve, index)
        self.original_selected = bool(selected)
        self.current_time = self.original_time
        self.current_value = self.original_value


def capture_selected_keys(records):
    snapshots = []
    for record in records:
        curve = record.curve
        try:
            key_count = len(curve.Keys)
        except Exception:
            continue
        for index in range(key_count):
            if not _key_selected(curve, index):
                continue
            try:
                snapshots.append(
                    KeySnapshot(
                        record,
                        index,
                        curve.Keys[index],
                        _key_selected(curve, index),
                    )
                )
            except Exception:
                pass
    return tuple(snapshots)
