from __future__ import annotations

import os
from pathlib import Path

from ultralytics import YOLO


BASE_DIR = Path(r"D:\SpeedEyeWoodTraining")
DATASET_DIR = BASE_DIR / "tiled_knot_data"
DATASET_YAML = DATASET_DIR / "dataset.yaml"
RUNS_DIR = BASE_DIR / "runs"
MODEL_PATH = Path.cwd() / "yolov8n.pt"


def main() -> None:
    os.environ.setdefault("YOLO_CONFIG_DIR", str(BASE_DIR / "Ultralytics"))
    os.environ.setdefault("HF_HOME", str(BASE_DIR / "hf_home"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(BASE_DIR / "hf_home" / "hub"))
    os.environ.setdefault("HF_DATASETS_CACHE", str(BASE_DIR / "hf_home" / "datasets"))

    if not DATASET_YAML.exists():
        raise RuntimeError(f"Brak dataset.yaml: {DATASET_YAML}")

    model = YOLO(str(MODEL_PATH))
    model.train(
        data=str(DATASET_YAML),
        imgsz=640,
        epochs=3,
        batch=32,
        device=0,
        workers=8,
        project=str(RUNS_DIR),
        name="knot_tiled_v1",
        exist_ok=True,
        pretrained=True,
        verbose=True,
        rect=False,
        cache=False,
        save=True,
        plots=False,
        patience=3,
        degrees=0.0,
        scale=0.15,
        mixup=0.0,
        mosaic=0.2,
    )


if __name__ == "__main__":
    main()
