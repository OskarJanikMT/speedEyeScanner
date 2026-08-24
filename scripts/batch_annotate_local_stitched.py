from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(r"C:\Users\preze\Desktop\SpeedEyeScanner")
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from ultralytics import YOLO

from helpers.onnx_knot_detector import annotate_image, resolve_inference_device, resolve_model_image_size


DEFAULT_MODEL = WORKSPACE_ROOT / "best.onnx"
DEFAULT_INPUT_DIR = Path(r"D:\SpeedEyeWoodTraining\local_stitched_labeling\images")
DEFAULT_OUTPUT_DIR = Path(r"D:\SpeedEyeWoodTraining\local_stitched_labeling\zaznaczone")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--min-confidence", type=float, default=0.25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_path = Path(args.model)
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not model_path.exists():
        raise RuntimeError(f"Brak modelu: {model_path}")
    if not input_dir.exists():
        raise RuntimeError(f"Brak katalogu obrazow: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    model_image_size = resolve_model_image_size(model_path)
    inference_device = resolve_inference_device(model_path)

    with contextlib.redirect_stdout(None):
        model = YOLO(str(model_path))

    image_paths = sorted(
        path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in {".bmp", ".jpg", ".jpeg", ".png"}
    )
    total = len(image_paths)
    if total == 0:
        print("Brak obrazow do przetworzenia.")
        return

    for index, image_path in enumerate(image_paths, start=1):
        output_path = output_dir / image_path.name
        result = annotate_image(
            model=model,
            image_path=str(image_path),
            output_path=str(output_path),
            conf=args.conf,
            min_confidence=args.min_confidence,
            model_image_size=model_image_size,
            inference_device=inference_device,
        )
        print(
            f"[{index}/{total}] {image_path.name} -> {output_path.name} | "
            f"defects={result['defect_count']} | {result['inference_ms']:.1f} ms"
        )

    print(f"Gotowe. Wyniki zapisane w: {output_dir}")


if __name__ == "__main__":
    main()
