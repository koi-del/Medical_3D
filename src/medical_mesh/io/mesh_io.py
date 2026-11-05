from __future__ import annotations
from pathlib import Path
import hashlib
import json
import re
import struct
import numpy as np
from ..core.model import MeshAsset


def canonicalize_vertices(vertices, faces):
    """Exact coordinate welding only; returns raw->canonical mapping."""
    unique, inverse = np.unique(vertices, axis=0, return_inverse=True)
    return unique, inverse[faces], inverse


def _read_stl(data):
    # Binary headers can start with 'solid'; file length is authoritative.
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if 84 + n * 50 == len(data):
            if n == 0:
                raise ValueError("Empty STL")
            dtype = np.dtype([("normal", "<f4", 3), ("tri", "<f4", (3, 3)), ("attr", "<u2")])
            triangles = np.frombuffer(data, dtype=dtype, count=n, offset=84)["tri"].astype(float)
            return triangles.reshape(-1, 3), np.arange(n * 3).reshape(-1, 3)
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as e:
        raise ValueError("Truncated or invalid binary STL") from e
    # Parse facet grammar strictly instead of silently discarding malformed facets.
    tokens = re.findall(r"\S+", text)
    pos = 0
    if not tokens or tokens[0].lower() != "solid":
        raise ValueError("Invalid ASCII STL header")
    first = re.search(r"(?im)^\s*facet\s+normal\s+", text)
    if first is None:
        raise ValueError("Empty or invalid ASCII STL")
    body = text[first.start():]
    facet = re.compile(r"facet\s+normal\s+(\S+)\s+(\S+)\s+(\S+)\s+outer\s+loop\s+"
                       r"vertex\s+(\S+)\s+(\S+)\s+(\S+)\s+"
                       r"vertex\s+(\S+)\s+(\S+)\s+(\S+)\s+"
                       r"vertex\s+(\S+)\s+(\S+)\s+(\S+)\s+endloop\s+endfacet", re.I)
    triangles = []
    while True:
        body = body.lstrip()
        if body.lower().startswith("endsolid"):
            break
        match = facet.match(body)
        if not match:
            raise ValueError("Malformed ASCII STL facet or missing endsolid")
        try:
            values = np.asarray([float(x) for x in match.groups()])
        except ValueError as e:
            raise ValueError("Invalid ASCII STL number") from e
        triangles.append(values[3:].reshape(3, 3))
        body = body[match.end():]
    v = np.asarray(triangles).reshape(-1, 3)
    return v, np.arange(len(v)).reshape(-1, 3)


def load_mesh(path, *, source_unit=None, unit_to_mm=None, raw_archive=None):
    path = Path(path)
    data = path.read_bytes()
    if path.suffix.lower() == ".npz":
        with np.load(path, allow_pickle=False) as z:
            if 'metadata' not in z and path.with_suffix('.json').is_file():
                sidecar=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
                if sidecar.get('schema_version')=='1.0':
                    from ..member2.core.model import load_asset
                    from ..integration.member2 import from_optimization
                    return from_optimization(load_asset(path))
            meta = json.loads(str(z["metadata"])) if "metadata" in z else {}
            asset = MeshAsset(z["vertices"], z["faces"], **meta)
        return asset
    if path.suffix.lower() == ".stl":
        v, f = _read_stl(data)
    elif path.suffix.lower() in (".ply", ".obj"):
        import trimesh
        mesh = trimesh.load(path, process=False, maintain_order=True)
        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError("Expected one triangle mesh, not a scene")
        v, f = mesh.vertices, mesh.faces
    else:
        raise ValueError("Supported formats: STL, PLY, OBJ, NPZ; CAD belongs to member 2")
    # Validate before any welding. Duplicate/degenerate faces are retained.
    raw = MeshAsset(v, f, source_file=str(path.resolve()), source_sha256=hashlib.sha256(data).hexdigest())
    if raw_archive is not None:
        save_mesh(raw, raw_archive)
    v, f, mapping = canonicalize_vertices(raw.vertices, raw.faces)
    if (source_unit is None) != (unit_to_mm is None):
        raise ValueError("Provide both source_unit and unit_to_mm")
    if unit_to_mm is not None and (not np.isfinite(unit_to_mm) or unit_to_mm <= 0):
        raise ValueError("unit_to_mm must be positive and finite")
    return MeshAsset(v, f, asset_id=raw.asset_id, source_file=raw.source_file,
                     source_sha256=raw.source_sha256, source_unit=source_unit,
                     unit_to_mm=unit_to_mm, unit_status="confirmed" if source_unit else "unknown",
                     preprocessing_record=({"operation": "exact_coordinate_weld", "raw_vertices": len(raw.vertices),
                                            "merged_vertices": len(raw.vertices)-len(v), "raw_to_canonical": mapping.tolist()},))


def _stl_export_validation(asset,path):
    """Inspect the actual serialized file; topology only, not self-intersection."""
    from ..detection.topology import detect_defects
    before=detect_defects(asset).metrics
    reread=load_mesh(path)
    after=detect_defects(reread).metrics
    keys=('component_count','boundary_loop_count','boundary_edge_count','duplicate_face_count',
          'degenerate_face_count','non_manifold_edge_count','non_manifold_vertex_count','orientation_conflict_count')
    changed={k:dict(before=before[k],after=after[k]) for k in keys if before[k]!=after[k]}
    warnings=[]
    if changed:warnings.append('STL实际回读后拓扑指标发生变化；请查看导出检查，保留NPZ/项目包作为原生版本。')
    if not after['topology_passed']:warnings.append('导出STL仍有拓扑缺陷，请勿将导出成功视为修复通过。')
    return dict(status='checked',topology_passed=after['topology_passed'],changed_metrics=changed,
                roundtrip_metrics={k:after[k] for k in keys},warnings=warnings,
                self_intersection_status='unverified',file_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def save_mesh(asset, path, *, ascii=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".npz":
        with path.open("wb") as stream:
            np.savez_compressed(stream, vertices=asset.vertices, faces=asset.faces,
                                metadata=json.dumps(asset.metadata(), ensure_ascii=False))
    elif path.suffix.lower() == ".stl":
        tri = asset.vertices[asset.faces]
        normals = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        normals /= np.where(lengths == 0, 1, lengths)[:, None]
        if ascii:
            with path.open("w", encoding="ascii") as out:
                out.write("solid medical_mesh\n")
                for n, t in zip(normals, tri):
                    out.write(" facet normal " + " ".join(format(x, ".17g") for x in n) + "\n outer loop\n")
                    for p in t:
                        out.write(" vertex " + " ".join(format(x, ".17g") for x in p) + "\n")
                    out.write(" endloop\n endfacet\n")
                out.write("endsolid medical_mesh\n")
        else:
            if np.max(np.abs(tri)) > np.finfo(np.float32).max:
                raise ValueError("Coordinates exceed binary STL float32 range")
            with path.open("wb") as out:
                out.write(b"medical_mesh: original coordinates; units in metadata".ljust(80, b" "))
                out.write(struct.pack("<I", len(tri)))
                for n, t in zip(normals, tri):
                    out.write(struct.pack("<12fH", *n, *t.ravel(), 0))
        metadata=asset.metadata()
        try:metadata['export_validation']=_stl_export_validation(asset,path)
        except Exception as error:
            metadata['export_validation']=dict(status='failed',topology_passed=False,
                warnings=['STL已写入，但实际回读检查失败：'+str(error)],self_intersection_status='unverified')
        path.with_suffix(path.suffix + ".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        raise ValueError("Export supports NPZ and STL")
    return str(path)
