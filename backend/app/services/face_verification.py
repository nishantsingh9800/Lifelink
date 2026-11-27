import base64
import io
import math
from typing import Dict, List, Tuple

try:
    import cv2
    import numpy as np

    _HAS_CV2 = True
except ImportError:  # pragma: no cover - lightweight serverless runtimes (e.g. Vercel)
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    _HAS_CV2 = False

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]


class FaceDetectionError(ValueError):
    """Raised when image decoding or single-face detection fails."""


if _HAS_CV2:
    _FRONTAL_CASCADE = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    _ALT_CASCADE = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"
    )
else:
    _FRONTAL_CASCADE = None
    _ALT_CASCADE = None


def decode_base64_image(data_url_or_b64: str) -> bytes:
    """Decode a raw base64 string or data URL ('data:image/jpeg;base64,...') into bytes."""
    cleaned = (data_url_or_b64 or "").strip()
    if "," in cleaned and cleaned.lower().startswith("data:"):
        cleaned = cleaned.split(",", 1)[1]
    try:
        raw = base64.b64decode(cleaned, validate=True)
    except Exception as exc:
        raise FaceDetectionError("Invalid base64 image payload.") from exc
    if not raw:
        raise FaceDetectionError("Image payload is empty.")
    return raw


def _detect_single_face(gray: np.ndarray) -> Tuple[int, int, int, int]:
    faces = _FRONTAL_CASCADE.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48)
    )
    if len(faces) == 0:
        faces = _ALT_CASCADE.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48)
        )
    if len(faces) == 0:
        raise FaceDetectionError(
            "No clear human face detected. Face the camera directly in good lighting."
        )
    if len(faces) > 1:
        raise FaceDetectionError(
            "Multiple faces detected. Only the registered donor should appear in the frame."
        )
    x, y, w, h = faces[0]
    return int(x), int(y), int(w), int(h)


def _compute_lbp_grid(face_96: np.ndarray, grid_n: int = 6) -> np.ndarray:
    """Compute a 6x6 spatial grid of 16-bin 8-neighbor LBP histograms."""
    padded = np.pad(face_96, 1, mode="edge")
    center = padded[1:-1, 1:-1]
    offsets = [
        (-1, -1), (-1, 0), (-1, 1), (0, 1),
        (1, 1), (1, 0), (1, -1), (0, -1),
    ]
    lbp = np.zeros_like(center, dtype=np.uint8)
    h, w = center.shape
    for bit, (dy, dx) in enumerate(offsets):
        neighbor = padded[1 + dy : 1 + dy + h, 1 + dx : 1 + dx + w]
        lbp |= ((neighbor >= center).astype(np.uint8) << bit)

    # Quantize 256 LBP codes into 16 bins for illumination & pose robustness
    quantized = (lbp >> 4).astype(np.uint8)
    cell_h = h // grid_n
    cell_w = w // grid_n
    features: List[np.ndarray] = []
    for gy in range(grid_n):
        for gx in range(grid_n):
            cell = quantized[gy * cell_h : (gy + 1) * cell_h, gx * cell_w : (gx + 1) * cell_w]
            hist = np.bincount(cell.ravel(), minlength=16).astype(np.float32)
            norm = np.linalg.norm(hist)
            if norm > 0:
                hist /= norm
            features.append(hist)
    return np.concatenate(features)


def _compute_hog_grid(face_96: np.ndarray, grid_n: int = 4) -> np.ndarray:
    """Compute a 4x4 spatial grid of 8-bin Sobel gradient orientation histograms."""
    gx = cv2.Sobel(face_96, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(face_96, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx * gx + gy * gy)
    ang = (np.degrees(np.arctan2(gy, gx)) + 180.0) % 180.0
    bins = np.clip((ang / 22.5).astype(np.int32), 0, 7)

    h, w = face_96.shape
    cell_h = h // grid_n
    cell_w = w // grid_n
    features: List[np.ndarray] = []
    for r in range(grid_n):
        for c in range(grid_n):
            b_cell = bins[r * cell_h : (r + 1) * cell_h, c * cell_w : (c + 1) * cell_w]
            m_cell = mag[r * cell_h : (r + 1) * cell_h, c * cell_w : (c + 1) * cell_w]
            hist = np.bincount(b_cell.ravel(), weights=m_cell.ravel(), minlength=8).astype(np.float32)
            norm = np.linalg.norm(hist)
            if norm > 0:
                hist /= norm
            features.append(hist)
    return np.concatenate(features)


def _extract_pillow_descriptor(image_bytes: bytes) -> Tuple[List[float], Dict[str, int]]:
    """Lightweight image descriptor fallback when OpenCV is excluded from serverless bundles."""
    if Image is None:
        raise FaceDetectionError("Image processing library unavailable in this runtime.")
    try:
        with Image.open(io.BytesIO(image_bytes)) as im:
            gray = ImageOps.grayscale(im)
            w, h = gray.size
            if w < 48 or h < 48:
                raise FaceDetectionError("Image resolution is too small for face verification.")
            box_w, box_h = int(w * 0.6), int(h * 0.6)
            x0, y0 = (w - box_w) // 2, (h - box_h) // 2
            crop = gray.crop((x0, y0, x0 + box_w, y0 + box_h)).resize((24, 24))
            pixels = list(crop.getdata())
    except FaceDetectionError:
        raise
    except Exception as exc:
        raise FaceDetectionError("Unable to decode image. Upload a valid JPEG, PNG, or WEBP photo.") from exc

    mean = sum(pixels) / len(pixels)
    var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
    if var < 25.0:
        raise FaceDetectionError(
            "No clear human face detected. Face the camera directly in good lighting."
        )

    # 6x6 spatial grid (36 dims) of centered pixel intensity + horizontal/vertical edge strength
    vec: List[float] = []
    for gy in range(6):
        for gx in range(6):
            block = [
                pixels[(gy * 4 + dy) * 24 + (gx * 4 + dx)] - mean
                for dy in range(4)
                for dx in range(4)
            ]
            vec.append(sum(block) / len(block))
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return [round(v, 6) for v in vec], {"x": x0, "y": y0, "width": box_w, "height": box_h}


def extract_face_descriptor(image_bytes: bytes) -> Tuple[List[float], Dict[str, int]]:
    """
    Detect a single frontal human face and extract an L2-normalized spatial LBP+HOG descriptor.
    """
    if not _HAS_CV2:
        return _extract_pillow_descriptor(image_bytes)

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        raise FaceDetectionError("Unable to decode image. Upload a valid JPEG, PNG, or WEBP photo.")

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    x, y, w, h = _detect_single_face(gray)

    roi = gray[y : y + h, x : x + w]
    resized = cv2.resize(roi, (96, 96), interpolation=cv2.INTER_AREA)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    norm_face = clahe.apply(resized)

    lbp_feat = _compute_lbp_grid(norm_face, grid_n=6)
    hog_feat = _compute_hog_grid(norm_face, grid_n=4)
    combined = np.concatenate([lbp_feat * 0.65, hog_feat * 0.35]).astype(np.float32)
    norm = float(np.linalg.norm(combined))
    if norm > 0:
        combined /= norm

    return [round(float(v), 6) for v in combined], {"x": x, "y": y, "width": w, "height": h}


def compare_descriptors(
    enrolled: List[float], candidate: List[float], threshold: float = 0.80
) -> Tuple[bool, float]:
    """Compare two normalized face descriptors using cosine similarity."""
    if not _HAS_CV2:
        if not enrolled or not candidate or len(enrolled) != len(candidate):
            return False, 0.0
        dot = sum(a * b for a, b in zip(enrolled, candidate))
        na = math.sqrt(sum(a * a for a in enrolled))
        nb = math.sqrt(sum(b * b for b in candidate))
        if na == 0.0 or nb == 0.0:
            return False, 0.0
        score = max(0.0, min(1.0, dot / (na * nb)))
        return score >= threshold, round(score, 4)

    a = np.asarray(enrolled, dtype=np.float32)
    b = np.asarray(candidate, dtype=np.float32)
    if a.shape != b.shape or a.size == 0:
        return False, 0.0
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return False, 0.0
    score = float(np.dot(a, b) / denom)
    score = max(0.0, min(1.0, score))
    return score >= threshold, round(score, 4)
