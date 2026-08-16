"""Shared cached screen/time/value transform for FCurve interactions."""

from __future__ import absolute_import

import itertools
import math


AXIS_LABEL_WIDTH = 41
AXIS_LABEL_HEIGHT = 8
OCR_MAX_SCORE = 0.75
MARKER_DENSITY_RADIUS = 3
MARKER_MIN_DENSITY = 24
MARKER_MIN_SEPARATION = 8.0
MARKER_MAX_FIT_COMBINATIONS = 6000
MARKER_MAX_RESIDUAL = 2.5
GRID_INCREMENT_RELATIVE_TOLERANCE = 0.08

class FCurveViewTransformCache(object):
    """Runtime-owned visual calibration cache and instrumentation."""

    def __init__(self):
        self.transforms = {}
        self.font_resources = {}
        self.label_masks = {}
        self.expensive_capture_count = 0

    def get(self, widget, signature):
        cached = self.transforms.get(id(widget))
        if cached is not None and cached.signature == signature:
            return cached
        return None

    def put(self, widget, transform):
        self.transforms[id(widget)] = transform

    def note_expensive_capture(self):
        self.expensive_capture_count += 1

    def invalidate_surface(self, widget):
        if widget is not None:
            self.transforms.pop(id(widget), None)

    def clear(self):
        self.transforms = {}
        self.font_resources = {}
        self.label_masks = {}


def _qt_gui():
    try:
        from PySide6 import QtGui
    except ImportError:
        from PySide2 import QtGui
    return QtGui


def _snapshot(widget):
    QtGui = _qt_gui()
    pixmap = widget.grab()
    image = pixmap.toImage()
    if pixmap.isNull() or image.isNull():
        return None
    image_format = (
        QtGui.QImage.Format.Format_RGBA8888
        if hasattr(QtGui.QImage, "Format")
        else QtGui.QImage.Format_RGBA8888
    )
    image = image.convertToFormat(image_format)
    size = (
        int(image.sizeInBytes())
        if hasattr(image, "sizeInBytes")
        else int(image.byteCount())
    )
    bits = image.bits()
    try:
        bits.setsize(size)
    except Exception:
        pass
    raw = bytes(bits)
    if len(raw) < size:
        return None
    return image, raw, int(image.bytesPerLine())


def _median_spacing(rows):
    if len(rows) < 2:
        return None
    differences = sorted(
        float(rows[index + 1] - rows[index])
        for index in range(len(rows) - 1)
    )
    middle = len(differences) // 2
    if len(differences) % 2:
        return differences[middle]
    return (differences[middle - 1] + differences[middle]) * 0.5


def _grid_layout(snapshot):
    image, raw, bytes_per_line = snapshot
    width = int(image.width())
    height = int(image.height())
    sample_xs = list(range(60, max(61, width - 30), 12))
    if not sample_xs:
        return (), None
    major_rows = []
    all_rows = []
    minimum_score = max(3, int(len(sample_xs) * 0.8))
    for image_y in range(4, max(5, height - 34)):
        row_offset = image_y * bytes_per_line
        major_score = 0
        grid_score = 0
        for image_x in sample_xs:
            offset = row_offset + (image_x * 4)
            red = raw[offset]
            green = raw[offset + 1]
            blue = raw[offset + 2]
            if red != green or green != blue:
                continue
            if 45 <= red <= 88:
                grid_score += 1
            if 72 <= red <= 88:
                major_score += 1
        if grid_score >= minimum_score:
            if not all_rows or image_y - all_rows[-1] > 2:
                all_rows.append(image_y)
        if major_score >= minimum_score:
            if not major_rows or image_y - major_rows[-1] > 2:
                major_rows.append(image_y)
    return tuple(major_rows), _median_spacing(all_rows)


def _font_resources(font, cache):
    try:
        key = font.toString()
    except Exception:
        key = str(font)
    cached = cache.font_resources.get(key)
    if cached is not None:
        return cached
    QtGui = _qt_gui()
    image_format = (
        QtGui.QImage.Format.Format_RGB32
        if hasattr(QtGui.QImage, "Format")
        else QtGui.QImage.Format_RGB32
    )
    metrics = QtGui.QFontMetrics(font)
    glyph_masks = {}
    for character in "-0123456789.":
        image = QtGui.QImage(12, AXIS_LABEL_HEIGHT, image_format)
        image.fill(QtGui.QColor(41, 41, 41))
        painter = QtGui.QPainter(image)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(199, 199, 199))
        painter.drawText(0, AXIS_LABEL_HEIGHT, character)
        painter.end()
        glyph_masks[character] = {
            (image_x, image_y)
            for image_y in range(AXIS_LABEL_HEIGHT)
            for image_x in range(image.width())
            if image.pixelColor(image_x, image_y).red() > 90
        }
    cached = metrics, glyph_masks
    cache.font_resources[key] = cached
    return cached


def _label_mask(text, font, metrics, cache):
    try:
        font_key = font.toString()
    except Exception:
        font_key = str(font)
    key = (font_key, text)
    cached = cache.label_masks.get(key)
    if cached is not None:
        return cached
    QtGui = _qt_gui()
    image_format = (
        QtGui.QImage.Format.Format_RGB32
        if hasattr(QtGui.QImage, "Format")
        else QtGui.QImage.Format_RGB32
    )
    image = QtGui.QImage(
        AXIS_LABEL_WIDTH,
        AXIS_LABEL_HEIGHT,
        image_format,
    )
    image.fill(QtGui.QColor(41, 41, 41))
    painter = QtGui.QPainter(image)
    painter.setFont(font)
    painter.setPen(QtGui.QColor(199, 199, 199))
    painter.drawText(
        AXIS_LABEL_WIDTH - metrics.horizontalAdvance(text),
        AXIS_LABEL_HEIGHT,
        text,
    )
    painter.end()
    mask = {
        (image_x, image_y)
        for image_y in range(AXIS_LABEL_HEIGHT)
        for image_x in range(AXIS_LABEL_WIDTH)
        if image.pixelColor(image_x, image_y).red() > 90
    }
    cache.label_masks[key] = mask
    return mask


def _nearby_label_candidates(font, anchor_values, cache):
    metrics, _glyph_masks = _font_resources(font, cache)
    labels = set()
    for anchor in anchor_values:
        try:
            anchor = float(anchor)
        except Exception:
            continue
        if not math.isfinite(anchor):
            continue
        for exponent in range(-10, 13):
            for mantissa in (1.0, 2.0, 5.0):
                increment = mantissa * (10.0 ** exponent)
                decimals = max(0, -int(math.floor(math.log10(increment))))
                center = int(round(anchor / increment))
                for offset in range(-8, 9):
                    value = (center + offset) * increment
                    fixed = "%.*f" % (decimals, value)
                    labels.add(fixed)
                    if decimals > 0:
                        labels.add(fixed.rstrip("0").rstrip("."))
                        labels.add("%.*f" % (decimals + 1, value))
    candidates = []
    for text in labels:
        if not text or text == "-":
            continue
        if metrics.horizontalAdvance(text) > AXIS_LABEL_WIDTH:
            continue
        try:
            value = float(text)
        except Exception:
            continue
        candidates.append(
            (text, value, _label_mask(text, font, metrics, cache))
        )
    return candidates


def _axis_row_mask(snapshot, image_y):
    image, raw, bytes_per_line = snapshot
    mask = set()
    first_y = int(image_y) - 3
    for local_y in range(AXIS_LABEL_HEIGHT):
        sample_y = first_y + local_y
        if sample_y < 0 or sample_y >= int(image.height()):
            continue
        row_offset = sample_y * bytes_per_line
        for image_x in range(AXIS_LABEL_WIDTH):
            offset = row_offset + (image_x * 4)
            red = raw[offset]
            green = raw[offset + 1]
            blue = raw[offset + 2]
            if (
                red > 90
                and abs(red - green) <= 3
                and abs(green - blue) <= 3
            ):
                mask.add((image_x, local_y))
    return mask


def _row_candidates(snapshot, rows, widget, anchors, cache):
    labels = _nearby_label_candidates(widget.font(), anchors, cache)
    result = []
    for image_y in rows:
        actual = _axis_row_mask(snapshot, image_y)
        scored = []
        for text, value, candidate in labels:
            union = actual | candidate
            score = float(len(actual ^ candidate)) / max(
                1.0,
                float(len(union)),
            )
            if score <= OCR_MAX_SCORE:
                scored.append((score, value, text))
        result.append(sorted(scored)[:24])
    return result


def _guide_alignment_error(
    anchors,
    guide_y,
    value_per_image_pixel,
    value_at_image_origin,
):
    if guide_y is None or value_per_image_pixel <= 0.0:
        return None
    errors = []
    for anchor in anchors:
        try:
            anchor = float(anchor)
        except Exception:
            continue
        if not math.isfinite(anchor):
            continue
        predicted_y = (
            float(value_at_image_origin) - anchor
        ) / float(value_per_image_pixel)
        if math.isfinite(predicted_y):
            errors.append(abs(predicted_y - float(guide_y)))
    return min(errors) if errors else None


def _guide_rows_alignment_error(
    anchors,
    guide_rows,
    value_per_image_pixel,
    value_at_image_origin,
):
    if not guide_rows or value_per_image_pixel <= 0.0:
        return None
    predicted = []
    for anchor in anchors:
        try:
            anchor = float(anchor)
        except Exception:
            continue
        if not math.isfinite(anchor):
            continue
        image_y = (
            float(value_at_image_origin) - anchor
        ) / float(value_per_image_pixel)
        if math.isfinite(image_y):
            predicted.append(image_y)
    predicted.sort()
    unique_predicted = []
    for image_y in predicted:
        if not unique_predicted or abs(image_y - unique_predicted[-1]) > 2.0:
            unique_predicted.append(image_y)
    guides = sorted(float(image_y) for image_y in guide_rows)
    if not unique_predicted or not guides:
        return None
    smaller, larger = (
        (unique_predicted, guides)
        if len(unique_predicted) <= len(guides)
        else (guides, unique_predicted)
    )
    best = None
    for subset in itertools.combinations(larger, len(smaller)):
        error = sum(
            abs(first - second)
            for first, second in zip(smaller, subset)
        ) / float(len(smaller))
        if best is None or error < best:
            best = error
    return best


def _axis_label_texts(value, increment):
    decimals = max(
        0,
        -int(math.floor(math.log10(float(increment)))),
    )
    fixed = "%.*f" % (decimals, float(value))
    texts = {fixed}
    if decimals > 0:
        texts.add(fixed.rstrip("0").rstrip("."))
        texts.add("%.*f" % (decimals + 1, float(value)))
    return tuple(text for text in texts if text and text != "-")


def _guided_axis_scale(snapshot, rows, widget, anchors, cache, guide_y):
    spacing = _median_spacing(rows)
    if (
        guide_y is None
        or spacing is None
        or spacing <= 0.0
        or not anchors
    ):
        return None
    metrics, _glyph_masks = _font_resources(widget.font(), cache)
    actual_masks = [
        _axis_row_mask(snapshot, image_y)
        for image_y in rows
    ]
    best = None
    for anchor in anchors:
        try:
            anchor = float(anchor)
        except Exception:
            continue
        if not math.isfinite(anchor):
            continue
        for exponent in range(-10, 13):
            for mantissa in (1.0, 2.0, 5.0):
                increment = mantissa * (10.0 ** exponent)
                value_per_image_pixel = increment / float(spacing)
                value_at_image_origin = (
                    anchor
                    + (float(guide_y) * value_per_image_pixel)
                )
                scores = []
                for image_y, actual in zip(rows, actual_masks):
                    predicted = value_at_image_origin - (
                        float(image_y) * value_per_image_pixel
                    )
                    label_scores = []
                    for text in _axis_label_texts(predicted, increment):
                        if metrics.horizontalAdvance(text) > AXIS_LABEL_WIDTH:
                            continue
                        candidate = _label_mask(
                            text,
                            widget.font(),
                            metrics,
                            cache,
                        )
                        union = actual | candidate
                        label_scores.append(
                            float(len(actual ^ candidate))
                            / max(1.0, float(len(union)))
                        )
                    if label_scores:
                        scores.append(min(label_scores))
                if len(scores) < 2:
                    continue
                scores.sort()
                retained = scores[:max(2, len(scores) - 1)]
                average_score = sum(retained) / float(len(retained))
                candidate = (
                    average_score,
                    value_per_image_pixel,
                    value_at_image_origin,
                )
                if best is None or candidate < best:
                    best = candidate
    if best is None or best[0] > OCR_MAX_SCORE:
        return None
    return best[1], best[2]


def _grid_increment_error(value_per_image_pixel, rows):
    """Measure distance from MotionBuilder's 1/2/5 major-grid cadence."""
    spacing = _median_spacing(rows)
    increment = abs(float(value_per_image_pixel) * float(spacing or 0.0))
    if increment <= 0.0 or not math.isfinite(increment):
        return None
    exponent = math.floor(math.log10(increment))
    normalized = increment / (10.0 ** exponent)
    return min(
        abs(normalized - mantissa) / mantissa
        for mantissa in (1.0, 2.0, 5.0, 10.0)
    )


def _multi_key_guide_scale(anchors, guide_rows, rows):
    """Derive graph scale/origin from selected-value bounding guides."""
    values = sorted(
        set(
            float(anchor)
            for anchor in anchors
            if math.isfinite(float(anchor))
        )
    )
    guides = sorted(set(float(image_y) for image_y in guide_rows))
    if len(values) < 2 or len(guides) < 2:
        return None
    top = guides[0]
    bottom = guides[-1]
    pixel_span = bottom - top
    value_span = values[-1] - values[0]
    if pixel_span < 4.0 or value_span <= 0.000000000001:
        return None
    value_per_image_pixel = value_span / pixel_span
    cadence_error = _grid_increment_error(value_per_image_pixel, rows)
    if (
        cadence_error is None
        or cadence_error > GRID_INCREMENT_RELATIVE_TOLERANCE
    ):
        return None
    value_at_image_origin = values[-1] + (
        top * value_per_image_pixel
    )
    return value_per_image_pixel, value_at_image_origin


def _select_axis_hypothesis(
    hypotheses,
    anchors,
    guide_y,
    rows,
    guide_rows=None,
):
    hypotheses = tuple(hypotheses)
    maximum_matches = max(item[0] for item in hypotheses)
    supported = tuple(
        hypothesis
        for hypothesis in hypotheses
        if hypothesis[0] >= max(2, maximum_matches - 1)
    )
    cadence_aligned = []
    for hypothesis in supported:
        cadence_error = _grid_increment_error(hypothesis[2], rows)
        if (
            cadence_error is not None
            and cadence_error <= GRID_INCREMENT_RELATIVE_TOLERANCE
        ):
            cadence_aligned.append(hypothesis)
    cadence_aligned = tuple(cadence_aligned)
    if cadence_aligned:
        hypotheses = cadence_aligned

    def cadence_rank(hypothesis):
        error = _grid_increment_error(hypothesis[2], rows)
        return float("inf") if error is None else float(error)

    if guide_rows and anchors:
        tolerance = max(
            3.0,
            float(_median_spacing(rows) or 0.0) * 0.15,
        )
        row_aligned = []
        maximum_matches = max(item[0] for item in hypotheses)
        for hypothesis in hypotheses:
            if hypothesis[0] < max(2, maximum_matches - 1):
                continue
            alignment_error = _guide_rows_alignment_error(
                anchors,
                guide_rows,
                hypothesis[2],
                hypothesis[3],
            )
            if (
                alignment_error is not None
                and alignment_error <= tolerance
            ):
                row_aligned.append((alignment_error, hypothesis))
        if row_aligned:
            return min(
                row_aligned,
                key=lambda item: (
                    -item[1][0],
                    item[0],
                    cadence_rank(item[1]),
                    item[1][1],
                    item[1][2],
                    item[1][3],
                ),
            )[1]

    best = min(
        hypotheses,
        key=lambda item: (
            -item[0],
            cadence_rank(item),
            item[1],
            item[2],
            item[3],
        ),
    )
    if guide_y is None or not anchors:
        return best
    maximum_matches = max(item[0] for item in hypotheses)
    tolerance = max(
        3.0,
        float(_median_spacing(rows) or 0.0) * 0.15,
    )
    aligned = []
    for hypothesis in hypotheses:
        if hypothesis[0] < max(2, maximum_matches - 1):
            continue
        alignment_error = _guide_alignment_error(
            anchors,
            guide_y,
            hypothesis[2],
            hypothesis[3],
        )
        if alignment_error is not None and alignment_error <= tolerance:
            aligned.append((alignment_error, hypothesis))
    if not aligned:
        return best
    return min(
        aligned,
        key=lambda item: (
            -item[1][0],
            item[0],
            cadence_rank(item[1]),
            item[1][1],
            item[1][2],
            item[1][3],
        ),
    )[1]


def _axis_hypotheses(rows, candidates):
    """Build value-axis fits from logical major-grid steps.

    Qt rasterization makes evenly spaced graph rows alternate between nearby
    integer pixel gaps (for example 42/43 pixels).  Treating one pair's raw
    pixel distance as exact makes the predicted labels drift at later rows and
    can give a coherent OCR misread more matches than the real scale.  Match
    labels by rounded major-grid steps first, then fit the matched values back
    to their physical image rows.
    """
    spacing = _median_spacing(rows)
    if spacing is None or spacing <= 0.0:
        return []
    hypotheses = []
    for first_index in range(len(rows) - 1):
        for second_index in range(first_index + 1, len(rows)):
            step_count = max(
                1,
                int(
                    round(
                        float(rows[second_index] - rows[first_index])
                        / float(spacing)
                    )
                ),
            )
            for first in candidates[first_index]:
                for second in candidates[second_index]:
                    grid_increment = (
                        first[1] - second[1]
                    ) / float(step_count)
                    if grid_increment <= 0.0:
                        continue
                    matches = []
                    for row_index, image_y in enumerate(rows):
                        row_steps = int(
                            round(
                                float(image_y - rows[first_index])
                                / float(spacing)
                            )
                        )
                        predicted = first[1] - (
                            row_steps * grid_increment
                        )
                        tolerance = max(
                            abs(grid_increment) * 0.05,
                            abs(predicted) * 0.000001,
                            0.000000000001,
                        )
                        available = [
                            item
                            for item in candidates[row_index]
                            if abs(item[1] - predicted) <= tolerance
                        ]
                        if available:
                            matches.append((image_y, min(available)))
                    if len(matches) < 2:
                        continue
                    fit = _linear_fit(
                        [float(item[0]) for item in matches],
                        [float(item[1][1]) for item in matches],
                    )
                    if fit is None or fit[0] >= -0.000000000001:
                        continue
                    score = sum(
                        item[1][0] for item in matches
                    ) / float(len(matches))
                    hypotheses.append(
                        (
                            len(matches),
                            score,
                            -fit[0],
                            fit[1],
                        )
                    )
    return hypotheses


def _axis_scale(snapshot, rows, widget, anchors, cache):
    if len(rows) < 2:
        return None
    horizontal_guides = _selected_horizontal_guides(snapshot, widget)
    bounded = _multi_key_guide_scale(
        anchors,
        horizontal_guides,
        rows,
    )
    if bounded is not None:
        return bounded
    guide = _selected_guides(snapshot, widget)
    guided = _guided_axis_scale(
        snapshot,
        rows,
        widget,
        anchors,
        cache,
        None if guide is None else guide[1],
    )
    if guided is not None:
        return guided
    candidates = _row_candidates(snapshot, rows, widget, anchors, cache)
    hypotheses = _axis_hypotheses(rows, candidates)
    if not hypotheses:
        return None

    best = _select_axis_hypothesis(
        hypotheses,
        anchors,
        None if guide is None else guide[1],
        rows,
        horizontal_guides,
    )
    return best[2], best[3]


def _evenly_spaced(start, stop, maximum):
    count = max(0, int(stop) - int(start))
    if count <= maximum:
        return list(range(int(start), int(stop)))
    return [
        int(start) + min(
            count - 1,
            int(((index + 0.5) * count) / maximum),
        )
        for index in range(maximum)
    ]


def _selected_guides(snapshot, widget):
    image, raw, bytes_per_line = snapshot
    width = int(image.width())
    height = int(image.height())
    scale_x = float(width) / max(1.0, float(widget.width()))
    scale_y = float(height) / max(1.0, float(widget.height()))
    left = max(8, int(round(50.0 * scale_x)))
    right = max(left + 1, width - max(8, int(round(20.0 * scale_x))))
    top = max(4, int(round(4.0 * scale_y)))
    bottom = max(
        top + 1,
        height
        - max(int(round(34.0 * scale_y)), int(round(height * 0.15))),
    )
    sampled_xs = _evenly_spaced(left, right, 96)
    sampled_ys = _evenly_spaced(top, bottom, 64)
    row_scores = []
    for image_y in range(top, bottom):
        row_offset = image_y * bytes_per_line
        score = sum(
            1
            for image_x in sampled_xs
            if min(
                raw[row_offset + image_x * 4],
                raw[row_offset + image_x * 4 + 1],
                raw[row_offset + image_x * 4 + 2],
            )
            >= 200
        )
        row_scores.append((score, image_y))
    column_scores = []
    for image_x in range(left, right):
        score = sum(
            1
            for image_y in sampled_ys
            if min(
                raw[image_y * bytes_per_line + image_x * 4],
                raw[image_y * bytes_per_line + image_x * 4 + 1],
                raw[image_y * bytes_per_line + image_x * 4 + 2],
            )
            >= 200
        )
        column_scores.append((score, image_x))
    row_score, image_y = max(row_scores) if row_scores else (0, 0)
    column_score, image_x = max(column_scores) if column_scores else (0, 0)
    if row_score < max(8, int(round(len(sampled_xs) * 0.22))):
        return None
    if column_score < max(8, int(round(len(sampled_ys) * 0.35))):
        return None
    return float(image_x), float(image_y)


def _selected_horizontal_guides(snapshot, widget):
    """Return strong selected-key horizontal guide rows in image pixels."""
    image, raw, bytes_per_line = snapshot
    width = int(image.width())
    height = int(image.height())
    scale_x = float(width) / max(1.0, float(widget.width()))
    scale_y = float(height) / max(1.0, float(widget.height()))
    left = max(8, int(round(50.0 * scale_x)))
    right = max(left + 1, width - max(8, int(round(20.0 * scale_x))))
    top = max(4, int(round(4.0 * scale_y)))
    bottom = max(
        top + 1,
        height
        - max(int(round(34.0 * scale_y)), int(round(height * 0.15))),
    )
    sampled_xs = _evenly_spaced(left, right, 96)
    scores = []
    for image_y in range(top, bottom):
        row_offset = image_y * bytes_per_line
        score = 0
        for image_x in sampled_xs:
            offset = row_offset + image_x * 4
            red = raw[offset]
            green = raw[offset + 1]
            blue = raw[offset + 2]
            if (
                min(red, green, blue) >= 145
                and max(red, green, blue) - min(red, green, blue) <= 8
            ):
                score += 1
        scores.append((score, image_y))
    maximum_score = max((item[0] for item in scores), default=0)
    minimum_score = max(
        8,
        int(round(len(sampled_xs) * 0.22)),
        int(round(maximum_score * 0.5)),
    )
    peaks = []
    for score, image_y in sorted(scores, reverse=True):
        if score < minimum_score:
            break
        if any(abs(image_y - existing_y) <= 2 for existing_y in peaks):
            continue
        peaks.append(image_y)
    return tuple(sorted(peaks))


def _single_key_axis_scale(snapshot, rows, widget, snapshots, cache):
    if len(rows) != 1 or len(snapshots) != 1:
        return None
    guide = _selected_guides(snapshot, widget)
    if guide is None:
        return None
    pixel_delta = float(guide[1]) - float(rows[0])
    if abs(pixel_delta) < 4.0:
        return None
    selected_value = float(snapshots[0].original_value)
    candidates = _row_candidates(
        snapshot,
        rows,
        widget,
        [selected_value],
        cache,
    )[0]
    if not candidates:
        return None
    _score, axis_value, _text = min(candidates)
    value_per_image_pixel = (
        float(axis_value) - selected_value
    ) / pixel_delta
    if value_per_image_pixel <= 0.0000001:
        return None
    return (
        value_per_image_pixel,
        selected_value + (float(guide[1]) * value_per_image_pixel),
    )


def _linear_fit(inputs, outputs):
    average_input = sum(inputs) / float(len(inputs))
    average_output = sum(outputs) / float(len(outputs))
    denominator = sum(
        (value - average_input) ** 2
        for value in inputs
    )
    if denominator <= 0.000001:
        return None
    slope = sum(
        (input_value - average_input) * (output_value - average_output)
        for input_value, output_value in zip(inputs, outputs)
    ) / denominator
    intercept = average_output - slope * average_input
    residual = math.sqrt(
        sum(
            (
                output_value
                - (intercept + slope * input_value)
            ) ** 2
            for input_value, output_value in zip(inputs, outputs)
        )
        / float(len(inputs))
    )
    return slope, intercept, residual


def _dense_markers(snapshot):
    image, raw, bytes_per_line = snapshot
    width = int(image.width())
    height = int(image.height())
    pixels = set()
    for image_y in range(max(0, height - 34)):
        offset = image_y * bytes_per_line
        for image_x in range(width):
            red = raw[offset]
            green = raw[offset + 1]
            blue = raw[offset + 2]
            maximum = max(red, green, blue)
            minimum = min(red, green, blue)
            if maximum >= 145 and maximum - minimum >= 40:
                pixels.add((image_x, image_y))
            offset += 4
    radius = MARKER_DENSITY_RADIUS
    dense = []
    for image_x, image_y in pixels:
        density = sum(
            1
            for neighbor_y in range(image_y - radius, image_y + radius + 1)
            for neighbor_x in range(image_x - radius, image_x + radius + 1)
            if (neighbor_x, neighbor_y) in pixels
        )
        if density >= MARKER_MIN_DENSITY:
            dense.append((density, image_x, image_y))
    markers = []
    minimum_distance = MARKER_MIN_SEPARATION ** 2
    for density, image_x, image_y in sorted(dense, reverse=True):
        if any(
            (image_x - marker_x) ** 2 + (image_y - marker_y) ** 2
            <= minimum_distance
            for _density, marker_x, marker_y in markers
        ):
            continue
        markers.append((density, image_x, image_y))
    return sorted(markers, key=lambda marker: marker[1])


def _marker_value_scale(snapshot, widget, records, time_span):
    markers = _dense_markers(snapshot)
    if len(markers) < 2:
        return None
    span_start, span_stop = sorted(time_span)
    best = None
    tested = 0
    for record in records:
        entries = []
        try:
            keys = tuple(record.curve.Keys)
        except Exception:
            continue
        for key in keys:
            try:
                ticks = int(key.Time.Get())
                if span_start <= ticks <= span_stop:
                    entries.append(
                        (
                            float(key.Time.GetSecondDouble()),
                            float(key.Value),
                        )
                    )
            except Exception:
                pass
        entries.sort()
        maximum = min(len(entries), len(markers))
        minimum = 2 if maximum == 2 else max(3, maximum - 2)
        for size in range(maximum, minimum - 1, -1):
            combinations = (
                math.comb(len(entries), size)
                * math.comb(len(markers), size)
            )
            if tested + combinations > MARKER_MAX_FIT_COMBINATIONS:
                continue
            for key_subset in itertools.combinations(entries, size):
                times = [entry[0] for entry in key_subset]
                values = [entry[1] for entry in key_subset]
                for marker_subset in itertools.combinations(markers, size):
                    tested += 1
                    xs = [float(marker[1]) for marker in marker_subset]
                    ys = [float(marker[2]) for marker in marker_subset]
                    horizontal = _linear_fit(times, xs)
                    vertical = _linear_fit(values, ys)
                    if horizontal is None or vertical is None:
                        continue
                    if horizontal[0] <= 0.000001 or vertical[0] >= -0.000001:
                        continue
                    if (
                        horizontal[2] > MARKER_MAX_RESIDUAL
                        or vertical[2] > MARKER_MAX_RESIDUAL
                    ):
                        continue
                    candidate = (
                        -size,
                        horizontal[2] + vertical[2],
                        vertical[0],
                        vertical[1],
                    )
                    if best is None or candidate[:2] < best[:2]:
                        best = candidate
    if best is None:
        return None
    image = snapshot[0]
    image_scale_y = float(image.height()) / max(1.0, float(widget.height()))
    image_pixels_per_value = best[2]
    value_per_image_pixel = -1.0 / image_pixels_per_value
    value_at_image_origin = -best[3] / image_pixels_per_value
    return (
        value_per_image_pixel * image_scale_y,
        value_at_image_origin,
    )


def _fallback_value_scale(records, widget):
    values = []
    for record in records:
        try:
            values.extend(float(key.Value) for key in record.curve.Keys)
        except Exception:
            pass
    graph_height = max(1.0, float(widget.height()) - 38.0)
    if not values:
        return 2.0 / graph_height
    value_range = max(values) - min(values)
    if value_range < 2.0:
        center = max(abs(sum(values) / len(values)) * 0.1, 1.0)
        value_range = max(2.0, center * 2.0)
    return value_range * 1.2 / graph_height


def _frame_ticks(context):
    try:
        mode = context.player_control.GetTransportFps()
        from pyfbsdk import FBTime

        return max(1, abs(int(FBTime(0, 0, 0, 1, 0, mode).Get())))
    except Exception:
        return 1


def _ticks_per_second(context):
    try:
        mode = context.player_control.GetTransportFps()
        from pyfbsdk import FBTime

        frame = FBTime(0, 0, 0, 1, 0, mode)
        seconds = abs(float(frame.GetSecondDouble()))
        if seconds > 0.000000001:
            return abs(float(frame.Get())) / seconds
    except Exception:
        pass
    return float(_frame_ticks(context))


class FCurveViewTransform(object):
    def __init__(
        self,
        ticks_per_pixel,
        value_per_pixel,
        frame_ticks,
        plot_rect,
        signature,
        time_span=None,
        value_at_y_zero=0.0,
        derivative_scale=None,
    ):
        self.ticks_per_pixel = float(ticks_per_pixel)
        self.value_per_pixel = float(value_per_pixel)
        self.frame_ticks = int(frame_ticks)
        self.plot_rect = tuple(plot_rect)
        self.signature = signature
        self.time_span = tuple(time_span or (0, 0))
        self.value_at_y_zero = float(value_at_y_zero)
        self.derivative_scale = max(
            0.000001,
            float(derivative_scale or self.value_per_pixel),
        )

    def time_to_local_x(self, time_ticks):
        start, stop = self.time_span
        left, _top, right, _bottom = self.plot_rect
        span = float(stop - start)
        if abs(span) <= 0.000001:
            return float(left)
        return float(left) + (
            (float(time_ticks) - float(start))
            * (float(right) - float(left))
            / span
        )

    def value_to_local_y(self, value):
        if abs(self.value_per_pixel) <= 0.000000001:
            return float(self.plot_rect[1])
        return (
            self.value_at_y_zero - float(value)
        ) / self.value_per_pixel

    def key_local_point(self, time_ticks, value):
        return (
            self.time_to_local_x(time_ticks),
            self.value_to_local_y(value),
        )

    @classmethod
    def capture(cls, context, widget, records, key_snapshots):
        try:
            time_span_object = context.fcurves.displayed_time_span(widget)
            time_span = (
                int(time_span_object.GetStart().Get()),
                int(time_span_object.GetStop().Get()),
            )
        except Exception:
            time_span = (0, _frame_ticks(context))
        property_signature = tuple(
            sorted(id(record.property) for record in records)
        )
        try:
            dpr = round(float(widget.devicePixelRatioF()), 4)
        except Exception:
            dpr = 1.0
        signature = (
            int(widget.width()),
            int(widget.height()),
            dpr,
            time_span,
            property_signature,
            id(context.animation_layer),
            context.surface_generation(widget),
        )
        cache = context.graph_transforms
        cached = cache.get(widget, signature)
        if cached is not None:
            return cached

        cache.note_expensive_capture()
        snapshot = _snapshot(widget)
        if snapshot is None:
            cache.invalidate_surface(widget)
            raise RuntimeError("could not capture the FCurve graph")
        image = snapshot[0]
        rows, minor_spacing = _grid_layout(snapshot)
        width = max(1.0, float(widget.width()))
        height = max(1.0, float(widget.height()))
        plot_left = min(width - 1.0, 50.0)
        plot_right = max(plot_left + 1.0, width - 20.0)
        plot_top = 4.0
        plot_bottom = max(plot_top + 1.0, height - max(34.0, height * 0.15))
        visible_ticks = abs(float(time_span[1] - time_span[0]))
        ticks_per_pixel = visible_ticks / max(1.0, plot_right - plot_left)

        anchors = [
            snapshot_state.original_value
            for snapshot_state in key_snapshots
        ]
        value_calibration = _axis_scale(
            snapshot,
            rows,
            widget,
            anchors,
            cache,
        )
        if value_calibration is None:
            value_calibration = _single_key_axis_scale(
                snapshot,
                rows,
                widget,
                key_snapshots,
                cache,
            )
        image_scale_y = float(image.height()) / height
        value_at_y_zero = None
        if value_calibration is not None:
            image_value_per_pixel, value_at_y_zero = value_calibration
            value_per_pixel = image_value_per_pixel * image_scale_y
        else:
            value_per_pixel = None
        if value_per_pixel is None:
            value_calibration = _marker_value_scale(
                snapshot,
                widget,
                records,
                time_span,
            )
            if isinstance(value_calibration, (tuple, list)):
                value_per_pixel, value_at_y_zero = value_calibration
            else:
                value_per_pixel = value_calibration
        if value_per_pixel is None:
            value_per_pixel = _fallback_value_scale(records, widget)
        if value_at_y_zero is None:
            selected_values = sorted(
                float(snapshot_state.original_value)
                for snapshot_state in key_snapshots
            )
            if selected_values:
                middle = len(selected_values) // 2
                if len(selected_values) % 2:
                    center_value = selected_values[middle]
                else:
                    center_value = (
                        selected_values[middle - 1]
                        + selected_values[middle]
                    ) * 0.5
            else:
                center_value = 0.0
            plot_center_y = (plot_top + plot_bottom) * 0.5
            value_at_y_zero = center_value + (
                plot_center_y * value_per_pixel
            )

        derivative_scale = value_per_pixel * (
            _ticks_per_second(context)
            / max(0.000001, ticks_per_pixel)
        )
        transform = cls(
            ticks_per_pixel,
            value_per_pixel,
            _frame_ticks(context),
            (plot_left, plot_top, plot_right, plot_bottom),
            signature,
            time_span,
            value_at_y_zero,
            derivative_scale,
        )
        cache.put(widget, transform)
        return transform
