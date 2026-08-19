from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

def stitch_board_folder(
    folder_path,
    overlap_extra_pixels=48,
    max_horizontal_shift_px=36,
    crop_x_margin_percent=4,
    crop_y_margin_percent=2,
    final_crop_x_margin_percent=3,
    active_threshold_percent=28,
    on_log=None,
):
    folder = Path(folder_path)
    image_paths = sorted(folder.glob("*.bmp"), reverse=True)
    if not image_paths:
        return None

    images = [QImage(str(path)).convertToFormat(QImage.Format.Format_RGB32) for path in image_paths]
    if any(image.isNull() for image in images):
        return None

    offsets = [0]
    for image in images[:-1]:
        offsets.append(offsets[-1] + image.height())

    canvas_width = max(image.width() for image in images)
    canvas_height = max(offset + image.height() for offset, image in zip(offsets, images))
    canvas = QImage(canvas_width, canvas_height, QImage.Format.Format_RGB32)
    canvas.fill(QColor(0, 0, 0))

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
    for y_offset, image in zip(offsets, images):
        painter.drawImage(0, y_offset, image)
    painter.end()

    final_crop_rect = _estimate_final_board_crop_rect(
        canvas,
        crop_x_margin_percent=crop_x_margin_percent,
        crop_y_margin_percent=crop_y_margin_percent,
        final_crop_x_margin_percent=final_crop_x_margin_percent,
        active_threshold_percent=active_threshold_percent,
    )
    if final_crop_rect is not None:
        canvas = canvas.copy(*final_crop_rect)

    output_path = folder / "stitched.bmp"
    canvas.save(str(output_path), "BMP")

    if on_log is not None:
        on_log(
            f"Scalono {len(image_paths)} zdjec do {output_path.name} "
            f"(tryb: pelne doklejanie + finalny crop, xmax={int(max_horizontal_shift_px)}px)"
        )

    return output_path


def _compute_column_means(image):
    x_step = 8
    width = image.width()
    height = image.height()
    bytes_per_line = image.bytesPerLine()
    data = bytes(image.bits())

    column_means = []
    for x in range(0, width, x_step):
        total = 0
        for y in range(height):
            index = y * bytes_per_line + x * 4
            total += _gray_at(data, index)
        column_means.append(total / height)
    return column_means


def _gray_at(data, index):
    blue = data[index]
    green = data[index + 1]
    red = data[index + 2]
    return (red * 299 + green * 587 + blue * 114) // 1000


def _compute_row_means(image, left_edge, right_edge):
    x_step = 8
    width = image.width()
    height = image.height()
    bytes_per_line = image.bytesPerLine()
    data = bytes(image.bits())

    left = max(0, min(width - 1, left_edge))
    right = max(left + 1, min(width, right_edge))
    sample_positions = list(range(left, right, x_step))
    if not sample_positions:
        sample_positions = list(range(0, width, x_step))

    row_means = []
    for y in range(height):
        total = 0
        for x in sample_positions:
            index = y * bytes_per_line + x * 4
            total += _gray_at(data, index)
        row_means.append(total / len(sample_positions))
    return row_means


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
):
    left, right = _estimate_final_horizontal_bounds(
        image,
        crop_x_margin_percent=crop_x_margin_percent,
        final_crop_x_margin_percent=final_crop_x_margin_percent,
        active_threshold_percent=active_threshold_percent,
    )
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
):
    image = image.convertToFormat(QImage.Format.Format_RGB32)
    width = image.width()
    column_means = _compute_column_means(image)
    left_edge, right_edge = _estimate_active_horizontal_bounds(
        column_means,
        width,
        active_threshold_percent=active_threshold_percent,
    )

    detected_width = max(1, right_edge - left_edge)
    total_margin_percent = max(0.0, crop_x_margin_percent) + max(0.0, final_crop_x_margin_percent)
    margin_x = max(2, int(detected_width * total_margin_percent / 100.0))
    left = max(0, left_edge - margin_x)
    right = min(width, right_edge + margin_x)

    return left, right
