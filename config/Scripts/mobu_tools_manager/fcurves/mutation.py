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

    @staticmethod
    def _curve_key_time(curve, index, candidate=None):
        try:
            return int(curve.KeyGetTime(index).Get())
        except Exception:
            pass
        try:
            key = candidate if candidate is not None else curve.Keys[index]
            return int(key.Time.Get())
        except Exception:
            return None

    @staticmethod
    def _curve_key_value(curve, index, candidate=None):
        try:
            return float(curve.KeyGetValue(index))
        except Exception:
            pass
        try:
            key = candidate if candidate is not None else curve.Keys[index]
            return float(key.Value)
        except Exception:
            return None

    def _resolve_key(self, snapshot):
        candidates = ()
        try:
            candidates = tuple(snapshot.curve.Keys)
        except Exception:
            pass
        for index, candidate in enumerate(candidates):
            try:
                if candidate is snapshot.key or candidate == snapshot.key:
                    snapshot.key = candidate
                    snapshot.current_index = index
                    return candidate
            except Exception:
                pass
        for target_time, target_value in (
            (snapshot.current_time, snapshot.current_value),
            (snapshot.original_time, snapshot.original_value),
        ):
            for index, candidate in enumerate(candidates):
                time_ticks = self._curve_key_time(
                    snapshot.curve,
                    index,
                    candidate,
                )
                value = self._curve_key_value(
                    snapshot.curve,
                    index,
                    candidate,
                )
                if (
                    time_ticks == int(target_time)
                    and value is not None
                    and abs(value - float(target_value)) <= 0.000001
                ):
                    snapshot.key = candidate
                    snapshot.current_index = index
                    return candidate
        if self._key_accessible(snapshot.key):
            return snapshot.key
        raise RuntimeError("selected FCurve key is no longer available")

    def resolve_index(self, snapshot):
        try:
            candidates = tuple(snapshot.curve.Keys)
        except Exception:
            candidates = ()
        current_index = getattr(
            snapshot,
            "current_index",
            snapshot.original_index,
        )
        if 0 <= current_index < len(candidates):
            candidate = candidates[current_index]
            if (
                self._curve_key_time(
                    snapshot.curve,
                    current_index,
                    candidate,
                ) == int(snapshot.current_time)
                and self._curve_key_value(
                    snapshot.curve,
                    current_index,
                    candidate,
                ) is not None
                and abs(
                    self._curve_key_value(
                        snapshot.curve,
                        current_index,
                        candidate,
                    ) - float(snapshot.current_value)
                ) <= 0.000001
            ):
                snapshot.key = candidate
                return current_index
        key = self._resolve_key(snapshot)
        for index, candidate in enumerate(candidates):
            try:
                if candidate is key or candidate == key:
                    snapshot.current_index = index
                    return index
            except Exception:
                pass
        for index, candidate in enumerate(candidates):
            time_ticks = self._curve_key_time(
                snapshot.curve,
                index,
                candidate,
            )
            value = self._curve_key_value(
                snapshot.curve,
                index,
                candidate,
            )
            if (
                time_ticks == int(snapshot.current_time)
                and value is not None
                and abs(value - float(snapshot.current_value)) <= 0.000001
            ):
                snapshot.key = candidate
                snapshot.current_index = index
                return index
        raise RuntimeError("selected FCurve key index is no longer available")

    def _resolve_indices(self, curve, states):
        """Resolve all selected keys with one curve scan.

        FCurve keys have unique times.  G and positive-factor S preserve the
        selected keys' time order, so their current time is a stable lookup
        token between previews even when MotionBuilder replaces wrappers.
        """
        try:
            candidates = tuple(curve.Keys)
        except Exception:
            candidates = ()
        by_time = {}
        for index, candidate in enumerate(candidates):
            time_ticks = self._curve_key_time(curve, index, candidate)
            if time_ticks is not None:
                by_time[int(time_ticks)] = index
        resolved = {}
        used = set()
        for snapshot in states:
            index = by_time.get(int(snapshot.current_time))
            if index is None or index in used:
                index = self.resolve_index(snapshot)
            resolved[snapshot] = index
            used.add(index)
            snapshot.current_index = index
            try:
                snapshot.key = candidates[index]
            except Exception:
                pass
        return resolved

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

    def _restore_selection(self, curve, states):
        """Restore selection without forcing a curve-wide selection update."""
        try:
            resolved = self._resolve_indices(curve, states)
        except Exception:
            resolved = {}
        for snapshot in states:
            index = resolved.get(snapshot)
            if index is not None:
                try:
                    if bool(curve.Keys[index].Selected) == bool(
                        snapshot.original_selected
                    ):
                        continue
                except Exception:
                    pass
                try:
                    curve.Keys[index].Selected = snapshot.original_selected
                    continue
                except Exception:
                    pass
            try:
                if index is None:
                    index = self.resolve_index(snapshot)
                curve.KeySetSelected(index, snapshot.original_selected)
            except Exception:
                pass

    def restore_selection(self):
        """Reapply the captured key selection after a secondary edit pass."""
        for curve, states in self.by_curve.items():
            self._restore_selection(curve, states)

    def _set_time(self, snapshot, time_value):
        """Prefer the captured key wrapper; indexed edits re-sort the curve."""
        try:
            snapshot.key.Time = time_value
            return
        except Exception:
            pass
        index = self.resolve_index(snapshot)
        snapshot.curve.KeySetTime(index, time_value)

    def _set_value(self, snapshot, value):
        """Prefer the captured key wrapper; it remains stable during EditBegin."""
        try:
            snapshot.key.Value = value
            return
        except Exception:
            pass
        index = self.resolve_index(snapshot)
        snapshot.curve.KeySetValue(index, value)

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
        # The transform session previews once at its pivot when it starts.
        # Opening an FCurve edit transaction for that identity preview is
        # expensive on dense curves and can delay G/S by about a second.
        if all(
            int(targets[snapshot][0]) == int(snapshot.current_time)
            and abs(
                float(targets[snapshot][1])
                - float(snapshot.current_value)
            ) <= 0.0000001
            for snapshot in self.snapshots
        ):
            return False
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
            indices = self._resolve_indices(curve, states)
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
                # Set the value before retiming while the batched index is
                # known.  Directional ordering keeps every not-yet-edited
                # selected index stable when KeySetTime re-sorts the curve.
                for snapshot in ordered:
                    index = indices[snapshot]
                    try:
                        curve.KeySetValue(index, targets[snapshot][1])
                    except Exception:
                        curve.Keys[index].Value = targets[snapshot][1]
                    try:
                        curve.KeySetTime(
                            index,
                            FBTime(targets[snapshot][0]),
                        )
                    except Exception:
                        curve.Keys[index].Time = FBTime(
                            targets[snapshot][0]
                        )
                    snapshot.current_time = targets[snapshot][0]
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
                # MotionBuilder may invalidate key wrappers and clear their
                # selected state while finalizing a retime operation.
                self._restore_selection(curve, states)
        return True

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
