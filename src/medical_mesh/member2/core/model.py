from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from hashlib import sha256
from uuid import uuid4
import copy
import json
import os
import tempfile
import numpy as np


def write_json(path, value):
    """Write strict JSON atomically; NaN never masquerades as a valid metric."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def file_hash(path):
    digest = sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class MeshAsset:
    vertices: np.ndarray
    faces: np.ndarray
    asset_id: str = field(default_factory=lambda: uuid4().hex)
    version_id: str = field(default_factory=lambda: uuid4().hex)
    parent_version: str | None = None
    unit_status: str = "unknown"
    unit_name: str | None = None
    unit_to_mm: float | None = None
    source_path: str | None = None
    source_sha256: str | None = None
    operation: str = "import"
    parameters: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        raw_faces = np.asarray(self.faces)
        if raw_faces.dtype.kind not in "iu":
            raise ValueError("faces must contain integer indices")
        vertices = np.array(self.vertices, dtype=np.float64, order="C", copy=True)
        faces = np.array(raw_faces, dtype=np.int64, order="C", copy=True)
        if vertices.ndim != 2 or vertices.shape[1:] != (3,) or len(vertices) == 0:
            raise ValueError("vertices must be non-empty [N,3]")
        if faces.ndim != 2 or faces.shape[1:] != (3,) or len(faces) == 0:
            raise ValueError("faces must be non-empty triangular [M,3]")
        if not np.isfinite(vertices).all():
            raise ValueError("non-finite coordinates")
        if faces.min() < 0 or faces.max() >= len(vertices):
            raise ValueError("face index outside vertex range")
        if self.unit_status not in {"unknown", "confirmed"}:
            raise ValueError("invalid unit_status")
        if self.unit_status == "confirmed":
            if (not self.unit_name or self.unit_to_mm is None
                    or not np.isfinite(self.unit_to_mm) or self.unit_to_mm <= 0):
                raise ValueError("confirmed units need a positive unit_to_mm and name")
        elif self.unit_to_mm is not None or self.unit_name is not None:
            raise ValueError("unknown unit cannot carry an assumed scale or name")
        if not np.isfinite(np.linalg.norm(np.ptp(vertices, axis=0))):
            raise ValueError("coordinate extent exceeds numerical range")
        vertices.flags.writeable = False
        faces.flags.writeable = False
        object.__setattr__(self, "vertices", vertices)
        object.__setattr__(self, "faces", faces)
        object.__setattr__(self, "parameters", copy.deepcopy(self.parameters))
        object.__setattr__(self, "metadata", copy.deepcopy(self.metadata))

    @property
    def geometry_hash(self):
        digest = sha256()
        digest.update(self.vertices.astype("<f8").tobytes())
        digest.update(self.faces.astype("<i8").tobytes())
        return digest.hexdigest()

    @property
    def scale(self):
        return float(np.linalg.norm(np.ptp(self.vertices, axis=0)))

    def derive(self, vertices, faces, operation, parameters):
        return MeshAsset(
            vertices, faces, asset_id=self.asset_id, parent_version=self.version_id,
            unit_status=self.unit_status, unit_name=self.unit_name,
            unit_to_mm=self.unit_to_mm, source_path=self.source_path,
            source_sha256=self.source_sha256, operation=operation,
            parameters=parameters, metadata={**copy.deepcopy(self.metadata),
                "lifecycle": "candidate_unaccepted", "quality_status": "unverified"},
        )

    def to_metadata(self):
        result = {key: copy.deepcopy(getattr(self, key)) for key in (
            "asset_id", "version_id", "parent_version", "unit_status", "unit_name",
            "unit_to_mm", "source_path", "source_sha256", "operation", "parameters", "metadata")}
        result.update(schema_version="1.0", geometry_sha256=self.geometry_hash)
        return result


def save_asset(asset, path):
    path = Path(path).with_suffix(".npz")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = stream.name
        np.savez_compressed(stream, vertices=asset.vertices, faces=asset.faces)
    try:
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    write_json(path.with_suffix(".json"), asset.to_metadata())
    return path


def load_asset(path):
    path = Path(path).resolve()
    if path.suffix.lower() != ".npz":
        raise ValueError("public handoff uses NPZ + JSON; STL preview uses load_preview")
    metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    if metadata.pop("schema_version", None) != "1.0":
        raise ValueError("unsupported schema_version")
    expected_hash = metadata.pop("geometry_sha256")
    with np.load(path, allow_pickle=False) as arrays:
        asset = MeshAsset(arrays["vertices"], arrays["faces"], **metadata)
    if asset.geometry_hash != expected_hash:
        raise ValueError("mesh/metadata hash mismatch")
    return asset


def load_preview(path, unit=None):
    """Prototype STL/PLY/OBJ adapter, to be replaced by member 1's import service."""
    path = Path(path).resolve()
    if path.suffix.lower() == ".npz":
        return load_asset(path)
    import trimesh
    mesh = trimesh.load_mesh(path, process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError("expected a single triangle mesh")
    # Exact-coordinate canonicalization only. Never weld nearby anatomical surfaces.
    vertices, inverse = np.unique(mesh.vertices, axis=0, return_inverse=True)
    factors = {"mm": 1.0, "cm": 10.0, "m": 1000.0}
    if unit is not None and unit not in factors:
        raise ValueError("unsupported unit")
    return MeshAsset(
        vertices, inverse[mesh.faces], unit_status="confirmed" if unit else "unknown",
        unit_name=unit, unit_to_mm=factors.get(unit), source_path=str(path),
        source_sha256=file_hash(path), metadata={"import_backend": "member2_preview",
            "canonicalization": "exact_coordinates", "member1_import_pending": True},
    )
