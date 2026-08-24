from __future__ import annotations

import os
from pathlib import Path

from ultralytics import YOLO


def main() -> None:
    base = Path(r"D:\SpeedEyeWoodTraining")
    os.environ.setdefault("YOLO_CONFIG_DIR", str(base / "Ultralytics"))
    os.environ.setdefault("HF_HOME", str(base / "hf_home"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(base / "hf_home" / "hub"))
    os.environ.setdefault("HF_DATASETS_CACHE", str(base / "hf_home" / "datasets"))

    model = YOLO("yolov8n.pt")
    model.train(
        data=str(base / "yolo_knot_test" / "dataset.yaml"),
        imgsz=512,
        epochs=12,
        batch=16,
        device=0,
        workers=4,
        project=str(base / "runs"),
        name="knot_test_10min",
        exist_ok=True,
        patience=12,
        cache=False,
        pretrained=True,
        verbose=True,
    )


if __name__ == "__main__":
    main()
