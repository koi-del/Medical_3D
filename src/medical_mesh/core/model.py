from __future__ import annotations
from dataclasses import dataclass, field, replace, asdict
from typing import Any
import hashlib
import json
import uuid
import numpy as np


def jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "__dataclass_fields__"):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(x) for x in value]
    return value


@dataclass(frozen=True)
class MeshAsset:
    vertices: np.ndarray
    faces: np.ndarray
    asset_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    version: str = field(default_factory=lambda: uuid.uuid4().hex)
    source_file: str = ""
    source_sha256: str = ""
    unit_status: str = "unknown"
    source_unit: str | None = None
    unit_to_mm: float | None = None
    coordinate_note: str = "Original position and scale preserved"
    preprocessing_record: tuple = ()
    expected_component_count: int | None = None
    expected_open_boundaries: int | None = None
    parent_version: str | None = None
    processing_parameters: dict = field(default_factory=dict)

    def __post_init__(self):
        v = np.array(self.vertices, dtype=np.float64, copy=True)
        raw = np.asarray(self.faces)
        if raw.dtype.kind not in "iu":
            raise ValueError("Face indices must be integers")
        f = np.array(raw, dtype=np.int64, copy=True)
        if v.ndim != 2 or v.shape[1:] != (3,) or f.ndim != 2 or f.shape[1:] != (3,):
            raise ValueError("vertices/faces must have shape (N,3)/(M,3)")
        if not len(v) or not len(f):
            raise ValueError("Empty mesh")
        if not np.isfinite(v).all():
            raise ValueError("Non-finite vertex coordinates")
        if f.min() < 0 or f.max() >= len(v):
            raise ValueError("Face index outside vertex array")
        if not np.isfinite(np.ptp(v, axis=0)).all() or np.linalg.norm(np.ptp(v, axis=0)) == 0:
            raise ValueError("Zero or unrepresentable mesh scale")
        # Immutable byte-backed arrays cannot be made writeable again.
        object.__setattr__(self, "vertices", np.frombuffer(v.tobytes(), dtype=np.float64).reshape(v.shape))
        object.__setattr__(self, "faces", np.frombuffer(f.tobytes(), dtype=np.int64).reshape(f.shape))

    def derive(self, vertices=None, faces=None, parameters=None):
        return replace(self, vertices=self.vertices if vertices is None else vertices,
                       faces=self.faces if faces is None else faces,
                       version=uuid.uuid4().hex, parent_version=self.version,
                       processing_parameters=parameters or {})

    def metadata(self):
        return {k: jsonable(getattr(self, k)) for k in self.__dataclass_fields__ if k not in ("vertices", "faces")}

    def geometry_hash(self):
        return hashlib.sha256(self.vertices.tobytes() + self.faces.tobytes()).hexdigest()


@dataclass
class TaskResult:
    status: str
    input_version: str
    output_version: str | None = None
    metrics: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    output_paths: dict = field(default_factory=dict)
    quality_status: str = "unverified"

    def to_dict(self):
        return jsonable(self)
