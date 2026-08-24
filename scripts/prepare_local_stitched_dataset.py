from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SCANS_DIR = Path.cwd() / "scany"
DEFAULT_OUTPUT_DIR = Path(r"D:\SpeedEyeWoodTraining\local_stitched_labeling")


@dataclass
class BoardSample:
    board_id: str
    board_dir: Path
    stitched_path: Path
    annotated_path: Path | None
    detections_path: Path | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scans-dir", default=str(DEFAULT_SCANS_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def discover_samples(scans_dir: Path, limit: int) -> list[BoardSample]:
    candidates: list[BoardSample] = []
    for board_dir in scans_dir.iterdir():
        if not board_dir.is_dir():
            continue
        stitched_path = board_dir / "stitched.bmp"
        if not stitched_path.exists():
            continue
        annotated_path = board_dir / "stitched_annotated.bmp"
        detections_path = board_dir / "stitched_knots.json"
        candidates.append(
            BoardSample(
                board_id=board_dir.name,
                board_dir=board_dir,
                stitched_path=stitched_path,
                annotated_path=annotated_path if annotated_path.exists() else None,
                detections_path=detections_path if detections_path.exists() else None,
            )
        )

    candidates.sort(key=lambda sample: sample.board_dir.stat().st_mtime_ns, reverse=True)
    return candidates[: max(1, limit)]


def copy_sample(sample: BoardSample, output_dir: Path) -> dict:
    image_dir = output_dir / "images"
    preview_dir = output_dir / "previews"
    ai_dir = output_dir / "ai_logs"
    labels_dir = output_dir / "labels"

    image_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    ai_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    image_target = image_dir / f"{sample.board_id}.bmp"
    shutil.copy2(sample.stitched_path, image_target)

    preview_target = None
    if sample.annotated_path is not None:
        preview_target = preview_dir / f"{sample.board_id}_annotated.bmp"
        shutil.copy2(sample.annotated_path, preview_target)

    ai_log_target = None
    ai_detections = None
    if sample.detections_path is not None:
        ai_log_target = ai_dir / f"{sample.board_id}_stitched_knots.json"
        shutil.copy2(sample.detections_path, ai_log_target)
        try:
            ai_detections = json.loads(sample.detections_path.read_text(encoding="utf-8"))
        except Exception:
            ai_detections = None

    label_stub = labels_dir / f"{sample.board_id}.txt"
    if not label_stub.exists():
        label_stub.write_text("", encoding="utf-8")

    return {
        "board_id": sample.board_id,
        "source_board_dir": str(sample.board_dir),
        "stitched_image": str(image_target),
        "annotated_preview": str(preview_target) if preview_target is not None else "",
        "ai_log": str(ai_log_target) if ai_log_target is not None else "",
        "existing_ai_defect_count": int(ai_detections.get("defect_count", 0)) if ai_detections else 0,
        "label_file": str(label_stub),
        "label_status": "todo",
    }


def write_manifest(output_dir: Path, rows: list[dict]) -> None:
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "dataset_type": "local_stitched_labeling",
                "total_samples": len(rows),
                "samples": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    readme_path = output_dir / "README.txt"
    readme_path.write_text(
        "\n".join(
            [
                "Lokalny zestaw do oznaczania sęków z aplikacji SpeedEyeScanner.",
                "",
                "Foldery:",
                "images/   - stitched.bmp do ręcznego oznaczania",
                "previews/ - stitched_annotated.bmp z bieżących testów AI",
                "ai_logs/  - stitched_knots.json z bieżących testów AI",
                "labels/   - puste pliki .txt do wypełnienia po oznaczeniu",
                "",
                "Manifest:",
                "manifest.json zawiera listę próbek i ścieżki źródłowe.",
                "",
                "Docelowo:",
                "1. oznacz prawdziwe sęki na obrazach z images/",
                "2. zapisz etykiety do labels/",
                "3. potem zrobimy konwersję do treningu YOLO.",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    scans_dir = Path(args.scans_dir)
    output_dir = Path(args.output_dir)

    if not scans_dir.exists():
        raise RuntimeError(f"Brak katalogu skanow: {scans_dir}")

    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)

    samples = discover_samples(scans_dir, args.limit)
    rows = [copy_sample(sample, output_dir) for sample in samples]
    write_manifest(output_dir, rows)

    print(f"Prepared local labeling dataset: {output_dir}")
    print(f"Collected stitched boards: {len(rows)}")
    print(f"Manifest: {output_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
