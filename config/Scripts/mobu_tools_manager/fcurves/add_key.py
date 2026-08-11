"""Insert a key on selected curves without native-action key injection."""

from __future__ import absolute_import

from .discovery import selected_curve_records


TOOL_NAME = "Add FCurve Key"


def _has_key_at_time(curve, ticks):
    try:
        key_count = len(curve.Keys)
    except Exception:
        key_count = 0
    for index in range(key_count):
        try:
            if int(curve.Keys[index].Time.Get()) == ticks:
                return True
        except Exception:
            continue
    return False


def add_key(context, sdk=None):
    """Insert one current-time key per selected current-layer FCurve."""
    if sdk is None:
        import pyfbsdk as sdk

    current_ticks = int(context.system.LocalTime.Get())
    records = selected_curve_records(context)
    targets = tuple(
        record
        for record in records
        if not _has_key_at_time(record.curve, current_ticks)
    )
    report = {
        "selected_curve_count": len(records),
        "inserted": 0,
        "time_ticks": current_ticks,
    }
    if not targets:
        return report

    transaction = context.undo.begin(TOOL_NAME)
    try:
        for record in targets:
            transaction.add_property(record.property)
        for record in targets:
            record.curve.KeyInsert(sdk.FBTime(current_ticks))
            report["inserted"] += 1
    except Exception:
        transaction.cancel()
        if report["inserted"]:
            context.evaluation.request_fcurve()
        raise
    else:
        transaction.commit()

    if report["inserted"]:
        context.evaluation.request_fcurve()
    return report
