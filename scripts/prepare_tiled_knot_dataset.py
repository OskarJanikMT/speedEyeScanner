from __future__ import annotations

import argparse
import random
import shutil
import sys
from pathlib import Path

import cv2

WORKSPACE_ROOT = Path(r"C:\Users\preze\Desktop\SpeedEyeScanner")
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from helpers.onnx_knot_detector import build_square_tiles, rotate_image_for_inference


DEFAULT_SOURCE_DIR = Path(r"D:\SpeedEyeWoodTraining\data")
DEFAULT_OUTPUT_DIR = Path(r"D:\SpeedEyeWoodTraining\tiled_knot_data")
TRAIN_RATIO = 0.9
SEED = 42

# Training/inference should ignore pixel-sized specks that are not meaningful knots.
MIN_BOX_WIDTH_PX = 12.0
MIN_BOX_HEIGHT_PX = 12.0
MIN_BOX_AREA_PX = 400.0
MIN_TILE_BOX_AREA_PX = 36.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--train-ratio", type=float, default=TRAIN_RATIO)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def parse_yolo_boxes(label_path: Path, image_width: int, image_height: int) -> list[tuple[float, float, float, float]]:
    boxes: list[tuple[float, float, float, float]] = []
    if not label_path.exists():
        return boxes

    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.strip().split()
        if len(parts) != 5:
            continue

        _, x_center, y_center, width, height = parts
        width_px = float(width) * image_width
        height_px = float(height) * image_height
        if (
            width_px < MIN_BOX_WIDTH_PX
            or height_px < MIN_BOX_HEIGHT_PX
            or width_px * height_px < MIN_BOX_AREA_PX
        ):
            continue

        x_center_px = float(x_center) * image_width
        y_center_px = float(y_center) * image_height
        x1 = x_center_px - width_px / 2.0
        y1 = y_center_px - height_px / 2.0
        x2 = x_center_px + width_px / 2.0
        y2 = y_center_px + height_px / 2.0
        boxes.append((x1, y1, x2, y2))

    return boxes


def map_original_box_to_rotated(box: tuple[float, float, float, float], original_height: int) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = box
    original_points = [
        (x1, y1),
        (x2, y1),
        (x1, y2),
        (x2, y2),
    ]
    rotated_points = [(original_height - 1 - y, x) for x, y in original_points]
    xs = [point[0] for point in rotated_points]
    ys = [point[1] for point in rotated_points]
    return min(xs), min(ys), max(xs), max(ys)


def intersect_box_with_tile(
    box: tuple[float, float, float, float],
    tile_width: int,
    tile_height: int,
    y_offset: int,
) -> tuple[float, float, float, float] | None:
    x1, y1, x2, y2 = box
    ix1 = max(0.0, x1)
    iy1 = max(float(y_offset), y1)
    ix2 = min(float(tile_width), x2)
    iy2 = min(float(y_offset + tile_height), y2)
    if ix2 <= ix1 or iy2 <= iy1:
        return None

    local_x1 = ix1
    local_y1 = iy1 - y_offset
    local_x2 = ix2
    local_y2 = iy2 - y_offset
    if (local_x2 - local_x1) * (local_y2 - local_y1) < MIN_TILE_BOX_AREA_PX:
        return None
    return local_x1, local_y1, local_x2, local_y2


def to_yolo_line(box: tuple[float, float, float, float], tile_size: int) -> str:
    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    x_center = x1 + width / 2.0
    y_center = y1 + height / 2.0
    return f"0 {x_center / tile_size:.6f} {y_center / tile_size:.6f} {width / tile_size:.6f} {height / tile_size:.6f}"


def ensure_clean_output(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    (path / "images" / "train").mkdir(parents=True, exist_ok=True)
    (path / "images" / "val").mkdir(parents=True, exist_ok=True)
    (path / "labels" / "train").mkdir(parents=True, exist_ok=True)
    (path / "labels" / "val").mkdir(parents=True, exist_ok=True)


def write_dataset_yaml(output_dir: Path) -> None:
    (output_dir / "dataset.yaml").write_text(
        "\n".join(
            [
                f"path: {output_dir.as_posix()}",
                "train: images/train",
                "val: images/val",
                "names:",
                "  0: knot",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)
    image_dir = source_dir / "images"
    label_dir = source_dir / "labels"

    if not image_dir.exists() or not label_dir.exists():
        raise RuntimeError(f"Brak images/labels w: {source_dir}")

    if args.clean or not output_dir.exists():
        ensure_clean_output(output_dir)
    else:
        ensure_clean_output(output_dir)

    image_paths = sorted(path for path in image_dir.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"})
    random.Random(args.seed).shuffle(image_paths)
    train_cutoff = int(len(image_paths) * max(0.1, min(0.99, args.train_ratio)))
    train_ids = {path.stem for path in image_paths[:train_cutoff]}

    total_tiles = 0
    positive_tiles = 0
    skipped_small_boxes = 0

    for image_path in sorted(image_paths):
        image = cv2.imread(str(image_path))
        if image is None:
            continue

        split = "train" if image_path.stem in train_ids else "val"
        original_height, original_width = image.shape[:2]
        original_boxes = parse_yolo_boxes(label_dir / f"{image_path.stem}.txt", original_width, original_height)
        all_label_lines = (label_dir / f"{image_path.stem}.txt").read_text(encoding="utf-8").splitlines()
        skipped_small_boxes += max(0, len([line for line in all_label_lines if line.strip()]) - len(original_boxes))
        rotated_boxes = [map_original_box_to_rotated(box, original_height) for box in original_boxes]

        rotated_image = rotate_image_for_inference(image)
        tiles = build_square_tiles(rotated_image)
        tile_size = rotated_image.shape[1]

        for tile in tiles:
            tile_boxes: list[str] = []
            for rotated_box in rotated_boxes:
                clipped = intersect_box_with_tile(
                    rotated_box,
                    tile_width=int(tile["tile_width"]),
                    tile_height=int(tile["tile_height"]),
                    y_offset=int(tile["y_offset"]),
                )
                if clipped is None:
                    continue
                tile_boxes.append(to_yolo_line(clipped, tile_size))

            tile_name = f"{image_path.stem}_tile{int(tile['tile_index']):02d}.jpg"
            tile_image_path = output_dir / "images" / split / tile_name
            tile_label_path = output_dir / "labels" / split / f"{Path(tile_name).stem}.txt"

            cv2.imwrite(str(tile_image_path), tile["image"])
            tile_label_path.write_text("\n".join(tile_boxes), encoding="utf-8")
            total_tiles += 1
            if tile_boxes:
                positive_tiles += 1

    write_dataset_yaml(output_dir)

    print(f"Prepared tiled dataset at: {output_dir}")
    print(f"Source images: {len(image_paths)}")
    print(f"Tiles: {total_tiles}")
    print(f"Positive tiles: {positive_tiles}")
    print(f"Filtered tiny boxes: {skipped_small_boxes}")
    print(f"Dataset YAML: {output_dir / 'dataset.yaml'}")


if __name__ == "__main__":
    main()
