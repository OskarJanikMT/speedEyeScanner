from __future__ import annotations

import os
from pathlib import Path

from ultralytics import YOLO


BASE_DIR = Path(r"D:\SpeedEyeWoodTraining")
DATA_DIR = BASE_DIR / "data"
RUNS_DIR = BASE_DIR / "runs"
YAML_PATH = DATA_DIR / "dataset_auto.yaml"
MODEL_PATH = Path.cwd() / "yolov8n.pt"


def write_dataset_yaml() -> None:
    YAML_PATH.write_text(
        "\n".join(
            [
                f"path: {DATA_DIR.as_posix()}",
                "train: images",
                "val: images",
                "names:",
                "  0: knot",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    os.environ.setdefault("YOLO_CONFIG_DIR", str(BASE_DIR / "Ultralytics"))
    os.environ.setdefault("HF_HOME", str(BASE_DIR / "hf_home"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(BASE_DIR / "hf_home" / "hub"))
    os.environ.setdefault("HF_DATASETS_CACHE", str(BASE_DIR / "hf_home" / "datasets"))

    write_dataset_yaml()

    model = YOLO(str(MODEL_PATH))
    model.train(
        data=str(YAML_PATH),
        imgsz=640,
        epochs=1,
        batch=16,
        device=0,
        workers=8,
        project=str(RUNS_DIR),
        name="knot_data_one_epoch",
        exist_ok=True,
        pretrained=True,
        verbose=True,
        rect=True,
        cache=False,
        val=False,
        save=True,
        plots=False,
    )


if __name__ == "__main__":
    main()
