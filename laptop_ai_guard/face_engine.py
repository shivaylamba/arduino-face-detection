from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class FaceCrop:
    image_bgr: np.ndarray
    box: tuple[int, int, int, int]


@dataclass(frozen=True)
class MatchResult:
    known: bool
    name: str
    score: float


def _normalize_embedding(embedding: np.ndarray) -> np.ndarray:
    emb = np.asarray(embedding, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(emb))
    if norm <= 1e-9:
        raise ValueError("CavaFace returned an empty embedding")
    return emb / norm


class FaceDatabase:
    def __init__(self, names: list[str] | None = None, embeddings: np.ndarray | None = None):
        self.names = names or []
        if embeddings is None:
            self.embeddings = np.empty((0, 512), dtype=np.float32)
        else:
            self.embeddings = np.asarray(embeddings, dtype=np.float32)

    @classmethod
    def load(cls, path: str | Path) -> "FaceDatabase":
        db_path = Path(path)
        if not db_path.exists():
            return cls()

        data = np.load(db_path, allow_pickle=False)
        names = [str(name) for name in data["names"].tolist()]
        embeddings = np.asarray(data["embeddings"], dtype=np.float32)
        return cls(names, embeddings)

    def save(self, path: str | Path) -> None:
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            db_path,
            names=np.asarray(self.names, dtype=str),
            embeddings=np.asarray(self.embeddings, dtype=np.float32),
        )

    def add_many(self, name: str, embeddings: Iterable[np.ndarray]) -> int:
        rows = [_normalize_embedding(embedding) for embedding in embeddings]
        if not rows:
            return 0

        new_embeddings = np.vstack(rows).astype(np.float32)
        if self.embeddings.size == 0:
            self.embeddings = new_embeddings
        else:
            self.embeddings = np.vstack([self.embeddings, new_embeddings]).astype(np.float32)
        self.names.extend([name] * len(rows))
        return len(rows)

    def match(self, embedding: np.ndarray, threshold: float = 0.50) -> MatchResult:
        if self.embeddings.size == 0:
            return MatchResult(False, "unknown", 0.0)

        query = _normalize_embedding(embedding)
        scores = self.embeddings @ query
        best_index = int(np.argmax(scores))
        best_score = float(scores[best_index])
        best_name = self.names[best_index]
        return MatchResult(best_score >= threshold, best_name, best_score)


class CavaFaceRecognizer:
    def __init__(self, use_flip: bool = False, face_margin: float = 0.25):
        from qai_hub_models.models.cavaface.app import CavaFaceApp
        from qai_hub_models.models.cavaface.model import CavaFace

        self.model = CavaFace.from_pretrained()
        self.app = CavaFaceApp(self.model, input_height=112, input_width=112)
        self.use_flip = use_flip
        self.face_margin = face_margin

        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        self.detector = cv2.CascadeClassifier(str(cascade_path))
        if self.detector.empty():
            raise RuntimeError(f"Could not load OpenCV Haar cascade at {cascade_path}")

    def detect_largest_face(self, frame_bgr: np.ndarray) -> FaceCrop | None:
        if frame_bgr is None or frame_bgr.size == 0:
            return None

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        faces = self.detector.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(80, 80),
        )
        if len(faces) == 0:
            return None

        x, y, w, h = max(faces, key=lambda rect: rect[2] * rect[3])
        height, width = frame_bgr.shape[:2]
        margin_x = int(w * self.face_margin)
        margin_y = int(h * self.face_margin)
        x0 = max(0, x - margin_x)
        y0 = max(0, y - margin_y)
        x1 = min(width, x + w + margin_x)
        y1 = min(height, y + h + margin_y)
        crop = frame_bgr[y0:y1, x0:x1].copy()
        return FaceCrop(crop, (x0, y0, x1 - x0, y1 - y0))

    def embedding_from_bgr(self, frame_bgr: np.ndarray) -> np.ndarray:
        face = self.detect_largest_face(frame_bgr)
        if face is None:
            raise ValueError("No face detected")

        rgb = cv2.cvtColor(face.image_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        return _normalize_embedding(self.app.predict_features(pil_image, use_flip=self.use_flip))

    def embedding_from_image_path(self, image_path: str | Path) -> np.ndarray:
        path = Path(image_path)
        frame = cv2.imread(str(path))
        if frame is None:
            raise ValueError(f"Could not read image: {path}")
        return self.embedding_from_bgr(frame)
