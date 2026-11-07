"""Camera capture + evidence artifact store.

Evidence binary stays on the rover/Pi filesystem; SpacetimeDB only ever sees
references + SHA-256 (ADR-008). Every artifact gets a JSON sidecar linking
mission, zone, waypoint, UTC timestamp, pose and hash.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


@dataclass
class Frame:
    data: bytes
    width: int = 0
    height: int = 0
    format: str = "jpeg"


class Camera(Protocol):
    def capture(self) -> Frame: ...


class SyntheticCamera:
    """Deterministic test/sim frame — a labeled pattern, NOT a real photo.

    Used only in simulation; real deployments use Cv2Camera. Frames carry
    `synthetic=True` in metadata so evidence is never misrepresented.
    """

    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height
        self._n = 0

    def capture(self) -> Frame:
        self._n += 1
        # Deterministic pseudo-image: header + counter + timestamp bytes.
        stamp = int(time.time() * 1000).to_bytes(8, "big")
        body = (b"SYNTHETIC-FRAME\n" + stamp + self._n.to_bytes(4, "big")
                + bytes((self._n * 37) % 256 for _ in range(256)))
        return Frame(data=body, width=self.width, height=self.height,
                     format="bin")


class Cv2Camera:
    """Real camera via OpenCV (CSI or USB). Lazy import — cv2 optional."""

    def __init__(self, device: int = 0, width: int = 1280, height: int = 720):
        try:
            import cv2  # noqa: F401
        except ImportError:
            raise RuntimeError("opencv-python not installed")
        import cv2

        self._cv2 = cv2
        self._cap = cv2.VideoCapture(device)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self._cap.isOpened():
            raise RuntimeError(f"camera device {device} failed to open")

    def capture(self) -> Frame:
        ok, img = self._cap.read()
        if not ok or img is None:
            raise RuntimeError("camera capture failed")
        h, w = img.shape[:2]
        ok, buf = self._cv2.imencode(".jpg", img)
        if not ok:
            raise RuntimeError("jpeg encode failed")
        return Frame(data=buf.tobytes(), width=w, height=h, format="jpeg")

    def close(self) -> None:
        if getattr(self, "_cap", None):
            self._cap.release()


@dataclass
class EvidenceRef:
    artifact_id: str
    path: str
    sha256: str
    bytes: int
    observed_at: str
    zone_id: str
    mission_id: str
    waypoint_id: Optional[str]
    pose: dict
    synthetic: bool = False


class ArtifactStore:
    """Writes evidence images + sidecar metadata under a root dir."""

    def __init__(self, root: str | Path, retention_per_zone: int = 50):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.retention = retention_per_zone

    def store(self, frame: Frame, *, zone_id: str, mission_id: str,
              waypoint_id: Optional[str], pose: dict,
              observed_at: Optional[str] = None,
              camera_id: str = "cam-mast",
              synthetic: bool = False) -> EvidenceRef:
        observed_at = observed_at or time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        )
        digest = hashlib.sha256(frame.data).hexdigest()
        ext = frame.format if frame.format != "jpeg" else "jpg"
        artifact_id = f"ev-{mission_id}-{int(time.time() * 1000)}"
        zone_dir = self.root / zone_id
        zone_dir.mkdir(parents=True, exist_ok=True)
        img_path = zone_dir / f"{artifact_id}.{ext}"
        meta_path = zone_dir / f"{artifact_id}.json"

        img_path.write_bytes(frame.data)
        meta = {
            "artifact_id": artifact_id,
            "mission_id": mission_id,
            "command_id": None,
            "device_id": "rover-01",
            "zone_id": zone_id,
            "waypoint_id": waypoint_id,
            "camera_id": camera_id,
            "observed_at": observed_at,
            "received_at": observed_at,
            "pose": pose,
            "sha256": digest,
            "bytes": len(frame.data),
            "width": frame.width,
            "height": frame.height,
            "format": frame.format,
            "synthetic": synthetic,
            "storage_ref": str(img_path),
        }
        meta_path.write_text(json.dumps(meta, indent=2))
        self._enforce_retention(zone_dir)
        return EvidenceRef(
            artifact_id=artifact_id, path=str(img_path), sha256=digest,
            bytes=len(frame.data), observed_at=observed_at, zone_id=zone_id,
            mission_id=mission_id, waypoint_id=waypoint_id, pose=pose,
            synthetic=synthetic,
        )

    def _enforce_retention(self, zone_dir: Path) -> None:
        images = sorted(zone_dir.glob("ev-*.?*"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
        # keep newest `retention` image+sidecar pairs; delete older
        pairs = {}
        for p in images:
            if p.suffix == ".json":
                continue
            stem = p.with_suffix("")
            pairs.setdefault(stem.name, {"img": p})
            meta = zone_dir / f"{stem.name}.json"
            if meta.exists():
                pairs[stem.name]["meta"] = meta
        for name, files in list(pairs.items())[self.retention:]:
            files["img"].unlink(missing_ok=True)
            files.get("meta", zone_dir / f"{name}.json").unlink(missing_ok=True)
