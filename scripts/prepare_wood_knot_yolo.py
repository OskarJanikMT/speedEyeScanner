from __future__ import annotations

import random
import shutil
from pathlib import Path

from datasets import load_from_disk


DATASET_PATH = Path(r"D:\SpeedEyeWoodTraining\dataset")
OUTPUT_ROOT = Path(r"D:\SpeedEyeWoodTraining\yolo_knot_test")
SEED = 42
TRAIN_RATIO = 0.9
MAX_SAMPLES = 2500
KNOT_LABELS = {
    "Dead_Knot",
    "Live_Knot",
    "knot_with_crack",
    "Knot_missing",
}


def ensure_clean_output(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    (path / "images" / "train").mkdir(parents=True, exist_ok=True)
    (path / "images" / "val").mkdir(parents=True, exist_ok=True)
    (path / "labels" / "train").mkdir(parents=True, exist_ok=True)
    (path / "labels" / "val").mkdir(parents=True, exist_ok=True)


def normalized_box_to_yolo(bb: list[float]) -> tuple[float, float, float, float]:
    x_center, y_center, width, height = bb
    return x_center, y_center, width, height


def write_label_file(label_path: Path, boxes: list[tuple[float, float, float, float]]) -> None:
    if not boxes:
        label_path.write_text("", encoding="utf-8")
        return
    lines = [f"0 {x:.6f} {y:.6f} {w:.6f} {h:.6f}" for x, y, w, h in boxes]
    label_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    dataset = load_from_disk(str(DATASET_PATH))["train"]
    eligible_indices: list[int] = []
    for index in range(len(dataset)):
        objects = dataset[index]["objects"]
        if any(obj.get("label") in KNOT_LABELS for obj in objects):
            eligible_indices.append(index)

    random.seed(SEED)
    random.shuffle(eligible_indices)
    selected_indices = eligible_indices[: min(MAX_SAMPLES, len(eligible_indices))]
    train_cutoff = int(len(selected_indices) * TRAIN_RATIO)
    train_indices = set(selected_indices[:train_cutoff])

    ensure_clean_output(OUTPUT_ROOT)

    train_count = 0
    val_count = 0
    skipped_count = 0

    for index in selected_indices:
        row = dataset[index]
        knot_boxes = [
            normalized_box_to_yolo(obj["bb"])
            for obj in row["objects"]
            if obj.get("label") in KNOT_LABELS
        ]
        if not knot_boxes:
            skipped_count += 1
            continue

        split = "train" if index in train_indices else "val"
        image_path = OUTPUT_ROOT / "images" / split / f"{row['id']}.jpg"
        label_path = OUTPUT_ROOT / "labels" / split / f"{row['id']}.txt"

        row["image"].convert("RGB").save(image_path, format="JPEG", quality=95)
        write_label_file(label_path, knot_boxes)

        if split == "train":
            train_count += 1
        else:
            val_count += 1

    yaml_path = OUTPUT_ROOT / "dataset.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                f"path: {OUTPUT_ROOT.as_posix()}",
                "train: images/train",
                "val: images/val",
                "names:",
                "  0: knot",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Prepared dataset at: {OUTPUT_ROOT}")
    print(f"Selected samples: {len(selected_indices)}")
    print(f"Train images: {train_count}")
    print(f"Val images: {val_count}")
    print(f"Skipped rows without knot boxes: {skipped_count}")
    print(f"Dataset YAML: {yaml_path}")


if __name__ == "__main__":
    main()
