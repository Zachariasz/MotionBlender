"""Balanced, direction-safe FCurve key mutation."""

from __future__ import absolute_import


class FCurveCollision(Exception):
    pass


class FCurveMutationService(object):
    def __init__(self, snapshots):
        self.snapshots = tuple(snapshots)
        self.by_curve = {}
        self.unselected_times = {}
        for snapshot in self.snapshots:
            self.by_curve.setdefault(snapshot.curve, []).append(snapshot)
        for curve, selected in self.by_curve.items():
            selected_indices = set(
                snapshot.original_index for snapshot in selected
            )
            times = set()
            try:
                keys = tuple(curve.Keys)
            except Exception:
                keys = ()
            for index, key in enumerate(keys):
                if index in selected_indices:
                    continue
                try:
                    times.add(int(key.Time.Get()))
                except Exception:
                    pass
            self.unselected_times[curve] = times

    @staticmethod
    def _key_accessible(key):
        try:
            key.Time.Get()
            return True
        except Exception:
            return False

    def _resolve_key(self, snapshot):
        if self._key_accessible(snapshot.key):
            return snapshot.key
        candidates = []
        try:
            candidates = list(snapshot.curve.Keys)
        except Exception:
            pass
        for target_time, target_value in (
            (snapshot.current_time, snapshot.current_value),
            (snapshot.original_time, snapshot.original_value),
        ):
            for key in candidates:
                try:
                    if (
                        int(key.Time.Get()) == int(target_time)
                        and abs(float(key.Value) - float(target_value))
                        <= 0.000001
                    ):
                        snapshot.key = key
                        return key
                except Exception:
                    pass
        raise RuntimeError("selected FCurve key is no longer available")

    def resolve_index(self, snapshot):
        key = self._resolve_key(snapshot)
        try:
            candidates = tuple(snapshot.curve.Keys)
        except Exception:
            candidates = ()
        for index, candidate in enumerate(candidates):
            try:
                if candidate is key or candidate == key:
                    return index
            except Exception:
                pass
        for index, candidate in enumerate(candidates):
            try:
                if (
                    int(candidate.Time.Get()) == int(snapshot.current_time)
                    and abs(float(candidate.Value) - snapshot.current_value)
                    <= 0.000001
                ):
                    snapshot.key = candidate
                    return index
            except Exception:
                pass
        raise RuntimeError("selected FCurve key index is no longer available")

    def _validate_collisions(self, targets):
        for curve, states in self.by_curve.items():
            target_times = [
                int(targets[snapshot][0])
                for snapshot in states
            ]
            if len(target_times) != len(set(target_times)):
                raise FCurveCollision("selected keys would overlap")
            occupied = self.unselected_times.get(curve, set())
            if any(time_ticks in occupied for time_ticks in target_times):
                raise FCurveCollision("target frame already contains a key")

    def apply(self, target_times, target_values):
        from pyfbsdk import FBTime

        targets = dict(
            (
                snapshot,
                (
                    int(target_times[snapshot]),
                    float(target_values[snapshot]),
                ),
            )
            for snapshot in self.snapshots
        )
        self._validate_collisions(targets)
        for curve, states in self.by_curve.items():
            moving_right = sum(
                targets[state][0] - state.current_time
                for state in states
            ) > 0
            ordered = sorted(
                states,
                key=lambda state: state.current_time,
                reverse=moving_right,
            )
            began = False
            try:
                try:
                    curve.EditBegin()
                    began = True
                except Exception:
                    try:
                        curve.KeyModifyBegin()
                        began = True
                    except Exception:
                        pass
                for snapshot in ordered:
                    key = self._resolve_key(snapshot)
                    key.Time = FBTime(targets[snapshot][0])
                    snapshot.current_time = targets[snapshot][0]
                for snapshot in states:
                    key = self._resolve_key(snapshot)
                    key.Value = targets[snapshot][1]
                    try:
                        key.Selected = snapshot.original_selected
                    except Exception:
                        pass
                    snapshot.current_value = targets[snapshot][1]
            finally:
                if began:
                    try:
                        curve.EditEnd()
                    except Exception:
                        try:
                            curve.KeyModifyEnd()
                        except Exception:
                            pass

    def restore(self):
        times = dict(
            (snapshot, snapshot.original_time)
            for snapshot in self.snapshots
        )
        values = dict(
            (snapshot, snapshot.original_value)
            for snapshot in self.snapshots
        )
        self.apply(times, values)
