from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import cv2

from face_engine import CavaFaceRecognizer, FaceDatabase


DEFAULT_DATABASE = Path(__file__).resolve().parent / "known_faces" / "embeddings.npz"
DEFAULT_CAPTURE_DIR = Path(__file__).resolve().parent / "captures"


def clean_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip())
    if not cleaned:
        raise ValueError("Name must contain at least one letter or number")
    return cleaned[:48]


def capture_samples(camera_index: int, samples: int, output_dir: Path, name: str) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera index {camera_index}")

    paths: list[Path] = []
    try:
        for _ in range(10):
            cap.read()
            time.sleep(0.05)

        print("Look at the camera. Capturing samples...")
        for index in range(samples):
            time.sleep(0.45)
            ok, frame = cap.read()
            if not ok or frame is None:
                print(f"Skipping sample {index + 1}: camera frame failed")
                continue

            path = output_dir / f"enroll_{name}_{int(time.time())}_{index + 1:02d}.jpg"
            cv2.imwrite(str(path), frame)
            paths.append(path)
            print(f"Captured {path}")
    finally:
        cap.release()

    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enroll known users for Arduino Q Face Guard.")
    parser.add_argument("--name", required=True, help="Known user's display name.")
    parser.add_argument("--image", action="append", default=[], help="Image path. Can be repeated.")
    parser.add_argument("--camera", action="store_true", help="Capture enrollment images from webcam.")
    parser.add_argument("--camera-index", type=int, default=0, help="OpenCV camera index.")
    parser.add_argument("--samples", type=int, default=8, help="Number of webcam samples to capture.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="Embedding database path.")
    parser.add_argument("--captures-dir", type=Path, default=DEFAULT_CAPTURE_DIR, help="Where webcam samples are saved.")
    parser.add_argument("--flip", action="store_true", help="Use CavaFace flip ensemble for embeddings.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    name = clean_name(args.name)

    image_paths = [Path(path) for path in args.image]
    if args.camera:
        image_paths.extend(capture_samples(args.camera_index, args.samples, args.captures_dir, name))

    if not image_paths:
        raise SystemExit("Provide at least one --image or use --camera.")

    recognizer = CavaFaceRecognizer(use_flip=args.flip)
    embeddings = []
    for path in image_paths:
        try:
            embeddings.append(recognizer.embedding_from_image_path(path))
            print(f"Enrolled embedding from {path}")
        except Exception as exc:
            print(f"Skipping {path}: {exc}")

    if not embeddings:
        raise SystemExit("No usable face embeddings were created.")

    database = FaceDatabase.load(args.database)
    added = database.add_many(name, embeddings)
    database.save(args.database)
    print(f"Saved {added} embedding(s) for {name} to {args.database}")


if __name__ == "__main__":
    main()
