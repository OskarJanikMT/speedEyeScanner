from pathlib import Path
from time import perf_counter

import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QTransform


DERIVED_OUTPUT_NAMES = {
    "stitched.bmp",
    "stitched_annotated.bmp",
    "stitched_knots.json",
    "ai_warmup.bmp",
    "ai_warmup_out.bmp",
}
DEFAULT_LEFT_EDGE_ANCHOR_PX = 100
LEFT_EDGE_SEARCH_RADIUS_PX = 80


def rotate_qimage_180(image):
    if image is None or image.isNull():
        return image
    return image.transformed(QTransform().rotate(180), Qt.FastTransformation)


def load_ai_ready_image(
    image_path,
    crop_x_margin_percent=4,
    active_threshold_percent=28,
    left_edge_anchor_px=DEFAULT_LEFT_EDGE_ANCHOR_PX,
):
    image = QImage(str(image_path)).convertToFormat(QImage.Format.Format_RGB32)
    if image.isNull():
        return None, None
    image = rotate_qimage_180(image)

    return crop_ai_ready_qimage(
        image,
        crop_x_margin_percent=crop_x_margin_percent,
        active_threshold_percent=active_threshold_percent,
        left_edge_anchor_px=left_edge_anchor_px,
    )


def crop_ai_ready_qimage(
    image,
    crop_x_margin_percent=4,
    active_threshold_percent=28,
    left_edge_anchor_px=DEFAULT_LEFT_EDGE_ANCHOR_PX,
):
    if image is None or image.isNull():
        return None, None

    left, right = _estimate_final_horizontal_bounds(
        image,
        crop_x_margin_percent=crop_x_margin_percent,
        final_crop_x_margin_percent=0,
        active_threshold_percent=active_threshold_percent,
        left_edge_anchor_px=left_edge_anchor_px,
    )
    cropped = image.copy(left, 0, max(1, right - left), image.height())
    return cropped, (left, right)


def stitch_board_folder(
    folder_path,
    ordered_filenames=None,
    overlap_extra_pixels=48,
    max_horizontal_shift_px=36,
    crop_x_margin_percent=4,
    crop_y_margin_percent=2,
    final_crop_x_margin_percent=3,
    active_threshold_percent=28,
    left_edge_anchor_px=DEFAULT_LEFT_EDGE_ANCHOR_PX,
    stitch_mode="ai_ready",
    preserve_vertical_span=False,
    on_log=None,
    return_metadata=False,
):
    folder = Path(folder_path)
    if ordered_filenames:
        image_paths = []
        for filename in ordered_filenames:
            candidate_path = folder / str(filename)
            if candidate_path.exists() and candidate_path.name.lower() not in DERIVED_OUTPUT_NAMES:
                image_paths.append(candidate_path)
    else:
        image_paths = sorted(
            (
                path
                for path in folder.glob("*.bmp")
                if path.name.lower() not in DERIVED_OUTPUT_NAMES
            ),
        )
    if not image_paths:
        return None

    load_started_at = perf_counter()
    images = [
        rotate_qimage_180(QImage(str(path)).convertToFormat(QImage.Format.Format_RGB32))
        for path in image_paths
    ]
    load_rotate_ms = (perf_counter() - load_started_at) * 1000.0
    if any(image.isNull() for image in images):
        return None

    crop_window = None

    offsets = [0]
    for image in images[:-1]:
        offsets.append(offsets[-1] + image.height())

    canvas_width = max(image.width() for image in images)
    canvas_height = max(offset + image.height() for offset, image in zip(offsets, images))
    compose_started_at = perf_counter()
    canvas = QImage(canvas_width, canvas_height, QImage.Format.Format_RGB32)
    canvas.fill(QColor(0, 0, 0))

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
    for y_offset, image in zip(offsets, images):
        painter.drawImage(0, y_offset, image)
    painter.end()
    compose_ms = (perf_counter() - compose_started_at) * 1000.0

    crop_started_at = perf_counter()
    final_crop_rect = _estimate_final_board_crop_rect(
        canvas,
        crop_x_margin_percent=crop_x_margin_percent,
        crop_y_margin_percent=crop_y_margin_percent,
        final_crop_x_margin_percent=final_crop_x_margin_percent,
        active_threshold_percent=active_threshold_percent,
        left_edge_anchor_px=left_edge_anchor_px,
        preserve_vertical_span=preserve_vertical_span,
    )
    original_canvas_width = canvas.width()
    original_canvas_height = canvas.height()
    if final_crop_rect is not None:
        canvas = canvas.copy(*final_crop_rect)
    canvas = rotate_qimage_180(canvas)
    crop_rotate_ms = (perf_counter() - crop_started_at) * 1000.0

    output_path = folder / "stitched.bmp"
    temp_output_path = folder / "stitched.tmp.bmp"
    save_started_at = perf_counter()
    if not canvas.save(str(temp_output_path), "BMP"):
        return None
    temp_output_path.replace(output_path)
    save_ms = (perf_counter() - save_started_at) * 1000.0

    if on_log is not None:
        mode_text = "ai-ready crop + finalny crop" if stitch_mode == "ai_ready" else "pelne doklejanie + finalny crop"
        crop_suffix = ""
        if crop_window is not None:
            crop_suffix = f", x={crop_window[0]}..{crop_window[1]}"
        on_log(
            f"Scalono {len(image_paths)} zdjec do {output_path.name} "
            f"(tryb: {mode_text}, xmax={int(max_horizontal_shift_px)}px{crop_suffix})"
        )
        on_log(
            "Czas stitchingu [ms]: "
            f"wczytanie+obrot={load_rotate_ms:.0f}, "
            f"skladanie={compose_ms:.0f}, "
            f"crop+obrot={crop_rotate_ms:.0f}, zapis={save_ms:.0f}"
        )

    if not return_metadata:
        return output_path

    return output_path, {
        "source_image_count": len(image_paths),
        "pre_crop_window": crop_window,
        "final_crop_rect": final_crop_rect,
        "canvas_width_before_final_crop": original_canvas_width,
        "canvas_height_before_final_crop": original_canvas_height,
        "stitched_width": canvas.width(),
        "stitched_height": canvas.height(),
    }


def _crop_images_for_ai_ready_stitch(
    images,
    crop_x_margin_percent=4,
    active_threshold_percent=28,
    left_edge_anchor_px=DEFAULT_LEFT_EDGE_ANCHOR_PX,
):
    if not images:
        return images, None

    bounds = []
    min_width = min(image.width() for image in images)
    for image in images:
        left, right = _estimate_final_horizontal_bounds(
            image,
            crop_x_margin_percent=crop_x_margin_percent,
            final_crop_x_margin_percent=0,
            active_threshold_percent=active_threshold_percent,
            left_edge_anchor_px=left_edge_anchor_px,
        )
        bounds.append((left, right))

    # Keep the pre-stitch crop conservative: remove only background that is
    # outside every source frame's detected board span.
    left = min(bound[0] for bound in bounds)
    right = max(bound[1] for bound in bounds)
    left = max(0, min(min_width - 1, left))
    right = max(left + 1, min(min_width, right))

    cropped_images = [image.copy(left, 0, right - left, image.height()) for image in images]
    return cropped_images, (left, right)


def _compute_column_means(image):
    x_step = 8
    pixels = _qimage_pixels(image)
    samples = pixels[:, ::x_step, :3].astype(np.float32)
    gray = samples[:, :, 2] * 0.299 + samples[:, :, 1] * 0.587 + samples[:, :, 0] * 0.114
    return gray.mean(axis=0).tolist()


def _gray_at(data, index):
    blue = data[index]
    green = data[index + 1]
    red = data[index + 2]
    return (red * 299 + green * 587 + blue * 114) // 1000


def _compute_row_means(image, left_edge, right_edge):
    x_step = 8
    width = image.width()

    left = max(0, min(width - 1, left_edge))
    right = max(left + 1, min(width, right_edge))
    sample_positions = list(range(left, right, x_step))
    if not sample_positions:
        sample_positions = list(range(0, width, x_step))

    pixels = _qimage_pixels(image)
    samples = pixels[:, sample_positions, :3].astype(np.float32)
    gray = samples[:, :, 2] * 0.299 + samples[:, :, 1] * 0.587 + samples[:, :, 0] * 0.114
    return gray.mean(axis=1).tolist()


def _qimage_pixels(image):
    """Returns a BGR view of an RGB32 QImage without copying every pixel to Python."""
    width = image.width()
    height = image.height()
    raw = np.frombuffer(image.constBits(), dtype=np.uint8, count=image.sizeInBytes())
    rows = raw.reshape(height, image.bytesPerLine())
    return rows[:, : width * 4].reshape(height, width, 4)


def _compute_row_means_center(image, left_edge, right_edge, keep_ratio=0.6):
    width = max(1, right_edge - left_edge)
    keep_width = max(16, int(width * keep_ratio))
    start = left_edge + max(0, (width - keep_width) // 2)
    end = min(right_edge, start + keep_width)
    return _compute_row_means(image, start, end)


def _estimate_board_right_edge_from_means(column_means):
    x_step = 8
    best_index = None
    best_drop = 0
    for index in range(20, len(column_means) - 1):
        drop = column_means[index] - column_means[index + 1]
        if drop > best_drop:
            best_drop = drop
            best_index = index

    if best_index is None:
        return len(column_means) * x_step

    return best_index * x_step


def _estimate_board_left_edge_from_means(column_means, right_edge):
    x_step = 8
    right_index = max(4, min(len(column_means) - 2, right_edge // x_step))
    search_end = max(8, min(right_index - 4, right_index // 2 + 12))

    best_index = 0
    best_rise = 0
    for index in range(1, search_end):
        rise = column_means[index + 1] - column_means[index]
        if rise > best_rise:
            best_rise = rise
            best_index = index + 1

    return max(0, best_index * x_step)


def _estimate_active_horizontal_bounds(column_means, image_width, active_threshold_percent=28):
    x_step = 8
    if not column_means:
        return 0, image_width

    border_bounds = _estimate_border_contrast_bounds(
        column_means,
        image_width,
        active_threshold_percent=active_threshold_percent,
    )
    if border_bounds is not None:
        return border_bounds

    min_mean = min(column_means)
    max_mean = max(column_means)
    dynamic_range = max_mean - min_mean
    threshold_ratio = max(0.05, min(0.95, active_threshold_percent / 100.0))
    threshold = min_mean + max(10.0, dynamic_range * threshold_ratio)
    active_indices = [index for index, value in enumerate(column_means) if value >= threshold]

    if not active_indices:
        right_edge = _estimate_board_right_edge_from_means(column_means)
        left_edge = _estimate_board_left_edge_from_means(column_means, right_edge)
        return left_edge, right_edge

    left_edge = max(0, active_indices[0] * x_step)
    right_edge = min(image_width, (active_indices[-1] + 1) * x_step)

    if right_edge <= left_edge:
        return 0, image_width

    return left_edge, right_edge


def _estimate_border_contrast_bounds(column_means, image_width, active_threshold_percent=28):
    x_step = 8
    sample_count = len(column_means)
    if sample_count < 12:
        return None

    edge_sample_size = max(4, min(12, sample_count // 8))
    left_background = sum(column_means[:edge_sample_size]) / edge_sample_size
    right_background = sum(column_means[-edge_sample_size:]) / edge_sample_size
    dynamic_range = max(column_means) - min(column_means)
    threshold_ratio = max(0.04, min(0.6, active_threshold_percent / 100.0))
    delta_threshold = max(6.0, dynamic_range * threshold_ratio * 0.55)
    run_length = 3

    left_index = _find_edge_run(
        column_means,
        start=0,
        stop=sample_count - run_length + 1,
        step=1,
        baseline=left_background,
        threshold=delta_threshold,
        run_length=run_length,
    )
    right_index = _find_edge_run(
        column_means,
        start=sample_count - 1,
        stop=run_length - 2,
        step=-1,
        baseline=right_background,
        threshold=delta_threshold,
        run_length=run_length,
    )

    if left_index is None or right_index is None:
        return None

    left_edge = max(0, left_index * x_step)
    right_edge = min(image_width, (right_index + 1) * x_step)
    if right_edge <= left_edge:
        return None

    min_detected_width = int(image_width * 0.15)
    if right_edge - left_edge < min_detected_width:
        return None

    return left_edge, right_edge


def _find_edge_run(column_means, start, stop, step, baseline, threshold, run_length):
    if step > 0:
        indices = range(start, stop, step)
    else:
        indices = range(start, stop, step)

    for index in indices:
        if step > 0:
            window = column_means[index:index + run_length]
            if len(window) < run_length:
                continue
            if all(abs(value - baseline) >= threshold for value in window):
                return index
        else:
            window = column_means[index - run_length + 1:index + 1]
            if len(window) < run_length:
                continue
            if all(abs(value - baseline) >= threshold for value in window):
                return index - run_length + 1

    return None


def _estimate_board_vertical_bounds(row_means, image_height):
    min_mean = min(row_means)
    max_mean = max(row_means)
    threshold = min_mean + max(8.0, (max_mean - min_mean) * 0.18)
    active_rows = [index for index, value in enumerate(row_means) if value >= threshold]
    if not active_rows:
        return 0, image_height
    return active_rows[0], active_rows[-1] + 1


def _estimate_final_board_crop_rect(
    image,
    crop_x_margin_percent=4,
    crop_y_margin_percent=2,
    final_crop_x_margin_percent=3,
    active_threshold_percent=28,
    left_edge_anchor_px=DEFAULT_LEFT_EDGE_ANCHOR_PX,
    preserve_vertical_span=False,
):
    left, right = _estimate_final_horizontal_bounds(
        image,
        crop_x_margin_percent=crop_x_margin_percent,
        final_crop_x_margin_percent=final_crop_x_margin_percent,
        active_threshold_percent=active_threshold_percent,
        left_edge_anchor_px=left_edge_anchor_px,
    )
    if preserve_vertical_span:
        top = 0
        bottom = image.height()
    else:
        row_means = _compute_row_means_center(image, left, right, keep_ratio=0.55)
        first_active_row, last_active_row = _estimate_board_vertical_bounds(row_means, image.height())
        detected_height = max(1, last_active_row - first_active_row)
        margin_y = max(4, int(detected_height * max(0.0, crop_y_margin_percent) / 100.0))
        top = max(0, first_active_row - margin_y)
        bottom = min(image.height(), last_active_row + margin_y)
    left = max(0, left)
    right = min(image.width(), right)
    crop_width = max(1, right - left)
    crop_height = max(1, bottom - top)

    if crop_height >= image.height() and crop_width >= image.width():
        return None

    return (left, top, crop_width, crop_height)


def _estimate_final_horizontal_bounds(
    image,
    crop_x_margin_percent=4,
    final_crop_x_margin_percent=3,
    active_threshold_percent=28,
    left_edge_anchor_px=DEFAULT_LEFT_EDGE_ANCHOR_PX,
):
    image = image.convertToFormat(QImage.Format.Format_RGB32)
    width = image.width()
    column_means = _compute_column_means(image)
    detected_left_edge, right_edge = _estimate_active_horizontal_bounds(
        column_means,
        width,
        active_threshold_percent=active_threshold_percent,
    )
    left = max(0, min(width - 1, int(detected_left_edge)))
    detected_width = max(1, right_edge - left)
    total_margin_percent = max(0.0, crop_x_margin_percent) + max(
        0.0, final_crop_x_margin_percent
    )
    margin_left = max(2, int(detected_width * max(0.0, crop_x_margin_percent) / 100.0))
    margin_x = max(2, int(detected_width * total_margin_percent / 100.0))
    left = max(0, left - margin_left)
    right = min(width, right_edge + margin_x)
    right = max(left + 1, right)

    return left, right


def _estimate_left_edge_near_anchor(
    column_means,
    image_width,
    fallback_left_edge,
    left_edge_anchor_px=DEFAULT_LEFT_EDGE_ANCHOR_PX,
):
    x_step = 8
    sample_count = len(column_means)
    if sample_count < 3:
        return max(0, min(image_width - 1, fallback_left_edge))

    anchor_index = max(1, min(sample_count - 2, int(left_edge_anchor_px // x_step)))
    radius_indices = max(2, int(LEFT_EDGE_SEARCH_RADIUS_PX // x_step))
    start = max(1, anchor_index - radius_indices)
    stop = min(sample_count - 2, anchor_index + radius_indices)

    best_index = None
    best_rise = float("-inf")
    for index in range(start, stop + 1):
        rise = column_means[index + 1] - column_means[index]
        distance_penalty = abs(index - anchor_index) * 0.35
        score = rise - distance_penalty
        if score > best_rise:
            best_rise = score
            best_index = index + 1

    if best_index is None:
        left_edge = fallback_left_edge
    else:
        left_edge = best_index * x_step

    max_allowed_shift = LEFT_EDGE_SEARCH_RADIUS_PX
    anchor_px = max(0, min(image_width - 1, int(left_edge_anchor_px)))
    left_edge = max(anchor_px - max_allowed_shift, min(anchor_px + max_allowed_shift, left_edge))
    return max(0, min(image_width - 1, left_edge))
