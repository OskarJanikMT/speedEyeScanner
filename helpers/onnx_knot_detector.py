import argparse
import base64
import contextlib
import json
import os
import sys
from time import perf_counter
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from ultralytics import YOLO


DEFAULT_MODEL_IMAGE_HEIGHT = 768
DEFAULT_MODEL_IMAGE_WIDTH = 1536
# Stitched board scans are very tall and narrow. Rotating them before tiling
# collapses the whole board into a single oversized tile, which then gets
# downscaled to the model input and loses knot detail.
ROTATE_FOR_INFERENCE_CLOCKWISE = False
MIN_DEFECT_BOX_WIDTH_PX = 12
MIN_DEFECT_BOX_HEIGHT_PX = 12
MIN_DEFECT_BOX_AREA_PX = 400
DEFAULT_MAX_DEFECT_BOX_AREA_PX = 0
MAX_DEFECT_ASPECT_RATIO = 48.0
EDGE_MARGIN_PX = 6
EDGE_STRIP_MAX_HEIGHT_PX = 60
LARGE_DEFECT_BOX_AREA_PX = 12000
LARGE_DEFECT_MIN_CONFIDENCE = 0.10

# Force plain CPU image buffers in OpenCV. The previous UMat/OpenCL path was
# causing CL_MEM_OBJECT_ALLOCATION_FAILURE during buffer downloads.
cv2.ocl.setUseOpenCL(False)


def preload_nvidia_dll_directories():
    if not hasattr(os, "add_dll_directory"):
        return

    site_packages_dir = Path(ort.__file__).resolve().parent.parent
    candidate_dirs = [
        site_packages_dir / "nvidia" / "cu13" / "bin" / "x86_64",
        site_packages_dir / "nvidia" / "cudnn" / "bin",
        site_packages_dir / "torch" / "lib",
    ]
    for directory in candidate_dirs:
        if directory.exists():
            os.add_dll_directory(str(directory))


preload_nvidia_dll_directories()
ort.preload_dlls(directory="")


def is_onnx_model(model_path):
    return Path(model_path).suffix.lower() == ".onnx"


def get_available_onnx_execution_providers():
    try:
        return list(ort.get_available_providers())
    except Exception:
        return []


def resolve_onnx_execution_provider(model_path):
    available_providers = get_available_onnx_execution_providers()
    if "CUDAExecutionProvider" in available_providers:
        try:
            session = ort.InferenceSession(
                str(model_path),
                providers=[("CUDAExecutionProvider", {"device_id": 0}), "CPUExecutionProvider"],
            )
            active_providers = list(session.get_providers())
            if active_providers and active_providers[0] == "CUDAExecutionProvider":
                return 0, "onnx:CUDAExecutionProvider"
        except Exception:
            pass
    return "cpu", "onnx:CPUExecutionProvider"


def format_confidence(confidence):
    if confidence >= 0.1:
        return f"{confidence:.2f}"
    if confidence >= 0.01:
        return f"{confidence:.3f}"
    return f"{confidence:.4f}"


def resolve_inference_device(model_path):
    if is_onnx_model(model_path):
        inference_device, _ = resolve_onnx_execution_provider(model_path)
        return inference_device

    try:
        import torch

        if torch.cuda.is_available():
            return 0
    except Exception:
        pass
    return "cpu"


def normalize_model_image_size(model_image_size):
    if isinstance(model_image_size, (tuple, list)) and len(model_image_size) >= 2:
        height = int(model_image_size[0])
        width = int(model_image_size[1])
        return max(1, height), max(1, width)
    size = int(model_image_size)
    size = max(1, size)
    return size, size


def build_inference_tiles(image, model_image_size):
    image_height, image_width = image.shape[:2]
    model_height, model_width = normalize_model_image_size(model_image_size)
    tile_height = max(1, model_height)
    tile_width = max(1, min(image_width, model_width))
    tiles = []
    tile_index = 0

    for y_offset in range(0, image_height, tile_height):
        tile = image[y_offset : min(y_offset + tile_height, image_height), 0:tile_width]
        current_tile_height, current_tile_width = tile.shape[:2]
        if current_tile_height <= 0 or current_tile_width <= 0:
            continue

        padded_tile = np.zeros((model_height, model_width, 3), dtype=np.uint8)
        padded_tile[0:current_tile_height, 0:current_tile_width] = tile
        tiles.append(
            {
                "tile_index": tile_index,
                "y_offset": y_offset,
                "tile_width": current_tile_width,
                "tile_height": current_tile_height,
                "image": padded_tile,
            }
        )
        tile_index += 1

    return tiles


def rotate_image_for_inference(image):
    if not ROTATE_FOR_INFERENCE_CLOCKWISE:
        return image
    return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)


def map_rotated_box_to_original(box, original_height):
    xr1, yr1, xr2, yr2 = box
    rotated_points = [
        (xr1, yr1),
        (xr2, yr1),
        (xr1, yr2),
        (xr2, yr2),
    ]
    original_points = [(yr, original_height - 1 - xr) for xr, yr in rotated_points]
    xs = [point[0] for point in original_points]
    ys = [point[1] for point in original_points]
    return min(xs), min(ys), max(xs), max(ys)


def resolve_model_image_size(model_path):
    if not is_onnx_model(model_path):
        return DEFAULT_MODEL_IMAGE_HEIGHT, DEFAULT_MODEL_IMAGE_WIDTH

    try:
        session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        input_shape = session.get_inputs()[0].shape
        if len(input_shape) >= 4:
            image_height = input_shape[2]
            image_width = input_shape[3]
            if (
                isinstance(image_height, int)
                and image_height > 0
                and isinstance(image_width, int)
                and image_width > 0
            ):
                return image_height, image_width
    except Exception:
        pass
    return DEFAULT_MODEL_IMAGE_HEIGHT, DEFAULT_MODEL_IMAGE_WIDTH


def describe_inference_backend(model_path, inference_device):
    if not is_onnx_model(model_path):
        return f"torch:{inference_device}"
    _, backend_description = resolve_onnx_execution_provider(model_path)
    return backend_description


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--image")
    parser.add_argument("--output")
    parser.add_argument("--conf", type=float, default=0.45)
    parser.add_argument("--min-confidence", type=float, default=0.35)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--warmup", action="store_true")
    return parser.parse_args()


def annotate_image(model, image_path, output_path, conf, min_confidence, model_image_size, inference_device=None):
    image = cv2.imread(image_path)
    if image is None:
        raise RuntimeError(f"Cannot read image: {image_path}")

    boxes_payload, inference_ms = detect_boxes(
        model=model,
        image=image,
        conf=conf,
        min_confidence=min_confidence,
        model_image_size=model_image_size,
        inference_device=inference_device,
        annotate_target=image,
        min_box_area_px=MIN_DEFECT_BOX_AREA_PX,
        max_box_area_px=DEFAULT_MAX_DEFECT_BOX_AREA_PX,
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), image):
        raise RuntimeError(f"Cannot write annotated image: {output_path}")

    detections_path = output_path.with_name("stitched_knots.json")
    detections_payload = {
        "image_path": str(image_path),
        "annotated_path": str(output_path),
        "inference_ms": inference_ms,
        "model_image_size": model_image_size,
        "model_confidence_threshold": max(0.0, min(1.0, conf)),
        "min_knot_confidence_threshold": min_confidence,
        "defect_count": len(boxes_payload),
        "boxes": boxes_payload,
    }
    detections_path.write_text(
        json.dumps(detections_payload, indent=2),
        encoding="utf-8",
    )

    return {
        "annotated_path": str(output_path),
        "detections_path": "",
        "defect_count": len(boxes_payload),
        "boxes": boxes_payload,
        "inference_ms": inference_ms,
    }


def decode_image_from_request(request):
    image_base64 = str(request.get("image_base64", "")).strip()
    if image_base64:
        image_bytes = base64.b64decode(image_base64)
        image_buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(image_buffer, cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("Cannot decode image from image_base64")
        return image

    image_path = request.get("image")
    if not image_path:
        raise RuntimeError("Missing image or image_base64 in request")
    image = cv2.imread(str(image_path))
    if image is None:
        raise RuntimeError(f"Cannot read image: {image_path}")
    return image


def detect_boxes(
    model,
    image,
    conf,
    min_confidence,
    model_image_size,
    inference_device=None,
    annotate_target=None,
    min_box_area_px=MIN_DEFECT_BOX_AREA_PX,
    max_box_area_px=DEFAULT_MAX_DEFECT_BOX_AREA_PX,
):
    if image is None:
        raise RuntimeError("Cannot run detection on empty image")

    model_height, model_width = normalize_model_image_size(model_image_size)
    inference_image = rotate_image_for_inference(image)
    boxes_payload = []
    min_confidence = max(0.0, min(1.0, min_confidence))
    min_box_area_px = max(0, int(min_box_area_px or 0))
    max_box_area_px = max(0, int(max_box_area_px or 0))
    started_at = perf_counter()
    tiles = build_inference_tiles(inference_image, (model_height, model_width))
    for tile in tiles:
        with contextlib.redirect_stdout(sys.stderr):
            result = model.predict(
                source=tile["image"],
                conf=max(0.0, min(1.0, conf)),
                verbose=False,
                imgsz=[model_height, model_width],
                device=inference_device,
            )[0]

        if result.boxes is None:
            continue

        y_offset = int(tile["y_offset"])

        for box in result.boxes:
            confidence = float(box.conf[0].item()) if box.conf is not None else 0.0

            raw_x1, raw_y1, raw_x2, raw_y2 = box.xyxy[0].tolist()
            # Tiles are padded into the model canvas without resizing, so
            # prediction coordinates are already in the original tile space.
            rotated_x1 = int(round(raw_x1))
            rotated_y1 = int(round(raw_y1 + y_offset))
            rotated_x2 = int(round(raw_x2))
            rotated_y2 = int(round(raw_y2 + y_offset))

            if ROTATE_FOR_INFERENCE_CLOCKWISE:
                x1, y1, x2, y2 = map_rotated_box_to_original(
                    (rotated_x1, rotated_y1, rotated_x2, rotated_y2),
                    image.shape[0],
                )
            else:
                x1, y1, x2, y2 = rotated_x1, rotated_y1, rotated_x2, rotated_y2

            x1 = max(0, min(image.shape[1] - 1, x1))
            y1 = max(0, min(image.shape[0] - 1, y1))
            x2 = max(0, min(image.shape[1] - 1, x2))
            y2 = max(0, min(image.shape[0] - 1, y2))

            if x2 <= x1 or y2 <= y1:
                continue
            box_width = x2 - x1
            box_height = y2 - y1
            box_area = box_width * box_height
            effective_min_confidence = min_confidence
            if box_area >= LARGE_DEFECT_BOX_AREA_PX:
                effective_min_confidence = min(effective_min_confidence, LARGE_DEFECT_MIN_CONFIDENCE)
            if confidence < effective_min_confidence:
                continue
            if (
                box_width < MIN_DEFECT_BOX_WIDTH_PX
                or box_height < MIN_DEFECT_BOX_HEIGHT_PX
                or box_area < max(MIN_DEFECT_BOX_AREA_PX, min_box_area_px)
            ):
                continue
            if max_box_area_px > 0 and box_area > max_box_area_px:
                continue
            aspect_ratio = max(box_width / max(1, box_height), box_height / max(1, box_width))
            if aspect_ratio > MAX_DEFECT_ASPECT_RATIO:
                continue
            touches_top_or_bottom = y1 <= EDGE_MARGIN_PX or y2 >= image.shape[0] - EDGE_MARGIN_PX
            if touches_top_or_bottom and box_height <= EDGE_STRIP_MAX_HEIGHT_PX:
                continue

            if annotate_target is not None:
                cv2.rectangle(annotate_target, (x1, y1), (x2, y2), (0, 0, 255), 3)
                label = format_confidence(confidence)
                text_origin = (x1, max(24, y1 - 8))
                cv2.putText(
                    annotate_target,
                    label,
                    text_origin,
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )
            boxes_payload.append(
                {
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "confidence": confidence,
                    "tile_index": int(tile["tile_index"]),
                }
            )

    inference_ms = (perf_counter() - started_at) * 1000.0
    return boxes_payload, inference_ms


def serve(model, model_image_size, inference_device):
    print("READY", flush=True)
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            request = json.loads(raw_line)
            mode = request.get("mode", "annotate")
            if mode == "detect_boxes":
                image = decode_image_from_request(request)
                boxes_payload, inference_ms = detect_boxes(
                    model=model,
                    image=image,
                    conf=float(request.get("conf", 0.45)),
                    min_confidence=float(request.get("min_confidence", 0.35)),
                    model_image_size=model_image_size,
                    inference_device=inference_device,
                    annotate_target=None,
                    min_box_area_px=int(request.get("min_box_area_px", MIN_DEFECT_BOX_AREA_PX)),
                    max_box_area_px=int(request.get("max_box_area_px", DEFAULT_MAX_DEFECT_BOX_AREA_PX)),
                )
                result = {
                    "defect_count": len(boxes_payload),
                    "boxes": boxes_payload,
                    "inference_ms": inference_ms,
                    "image_height": int(image.shape[0]),
                    "image_width": int(image.shape[1]),
                }
            else:
                result = annotate_image(
                    model=model,
                    image_path=request["image"],
                    output_path=request["output"],
                    conf=float(request.get("conf", 0.45)),
                    min_confidence=float(request.get("min_confidence", 0.35)),
                    model_image_size=model_image_size,
                    inference_device=inference_device,
                )
            print(json.dumps({"ok": True, "result": result}), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc)}), flush=True)


def warmup(model, inference_device):
    warmup_image = Path.cwd() / "tmp" / "ai_warmup.bmp"
    warmup_image.parent.mkdir(parents=True, exist_ok=True)
    image = np.zeros((DEFAULT_MODEL_IMAGE_HEIGHT, DEFAULT_MODEL_IMAGE_WIDTH, 3), dtype=np.uint8)
    cv2.imwrite(str(warmup_image), image)
    annotate_image(
        model=model,
        image_path=str(warmup_image),
        output_path=str(warmup_image.with_name("ai_warmup_out.bmp")),
        conf=0.45,
        min_confidence=0.35,
        model_image_size=(DEFAULT_MODEL_IMAGE_HEIGHT, DEFAULT_MODEL_IMAGE_WIDTH),
        inference_device=inference_device,
    )


def main():
    args = parse_args()
    inference_device = resolve_inference_device(args.model)
    model_image_size = resolve_model_image_size(args.model)
    with contextlib.redirect_stdout(sys.stderr):
        model = YOLO(args.model)
    print(
        f"Using {describe_inference_backend(args.model, inference_device)}",
        file=sys.stderr,
        flush=True,
    )

    if args.warmup:
        warmup(model, inference_device)
        print("WARMED", flush=True)
        return

    if args.serve:
        serve(model, model_image_size, inference_device)
        return

    if not args.image or not args.output:
        raise RuntimeError("--image i --output sa wymagane bez --serve")

    result = annotate_image(
        model=model,
        image_path=args.image,
        output_path=args.output,
        conf=args.conf,
        min_confidence=args.min_confidence,
        model_image_size=model_image_size,
        inference_device=inference_device,
    )
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
