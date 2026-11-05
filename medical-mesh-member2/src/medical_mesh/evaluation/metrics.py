from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from vtkmodules.vtkCommonCore import reference
from vtkmodules.vtkCommonDataModel import vtkPolyData, vtkCellArray, vtkStaticCellLocator
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray


@dataclass(frozen=True)
class EvaluationConfig:
    samples: int = 10000
    seed: int = 20261018

    def __post_init__(self):
        if isinstance(self.samples, bool) or not isinstance(self.samples, int) or self.samples < 1:
            raise ValueError("samples must be a positive integer")
        if not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be nonnegative integer")


def triangle_measures(asset):
    tri = asset.vertices[asset.faces]
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    lengths2 = ((a-b)**2).sum(axis=1) + ((b-c)**2).sum(axis=1) + ((c-a)**2).sum(axis=1)
    q = np.divide(4*np.sqrt(3)*area, lengths2, out=np.zeros_like(area), where=lengths2 > 0)
    return area, np.clip(q, 0, 1)


def sample_surface(asset, count, seed):
    EvaluationConfig(count, seed)
    area, _ = triangle_measures(asset)
    if not np.isfinite(area).all() or area.sum() <= 0:
        raise ValueError("no valid surface area")
    rng = np.random.default_rng(seed)
    ids = rng.choice(len(area), size=count, p=area / area.sum())
    uv = rng.random((count, 2))
    s = np.sqrt(uv[:, 0])
    weights = np.column_stack((1-s, s*(1-uv[:, 1]), s*uv[:, 1]))
    points = np.einsum("ni,nij->nj", weights, asset.vertices[asset.faces[ids]])
    return points, ids, weights


def vtk_mesh(asset, origin=None):
    origin = np.zeros(3) if origin is None else np.asarray(origin)
    points = vtkPoints()
    points.SetData(numpy_to_vtk(np.ascontiguousarray(asset.vertices - origin), deep=True))
    cells = vtkCellArray()
    raw = np.column_stack((np.full(len(asset.faces), 3), asset.faces)).ravel()
    cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(raw, deep=True))
    data = vtkPolyData()
    data.SetPoints(points)
    data.SetPolys(cells)
    return data


def surface_distances(points, target, origin=None):
    origin = np.zeros(3) if origin is None else np.asarray(origin)
    data = vtk_mesh(target, origin)
    locator = vtkStaticCellLocator()
    locator.SetDataSet(data)
    locator.BuildLocator()
    distances = np.empty(len(points))
    closest_points = np.empty_like(points)
    cell_ids = np.empty(len(points), dtype=np.int64)
    cell_id, sub_id, distance2 = reference(0), reference(0), reference(0.0)
    closest = [0.0, 0.0, 0.0]
    for index, point in enumerate(points - origin):
        locator.FindClosestPoint(point, closest, cell_id, sub_id, distance2)
        if int(cell_id) < 0 or not np.isfinite(float(distance2)):
            raise RuntimeError("closest surface query failed")
        distances[index] = np.sqrt(max(0.0, float(distance2)))
        closest_points[index] = np.asarray(closest) + origin
        cell_ids[index] = int(cell_id)
    return distances, closest_points, cell_ids


def quality(asset):
    area, q = triangle_measures(asset)
    return {"faces": len(asset.faces), "vertices": len(asset.vertices), "area": float(area.sum()),
            "q_min": float(q.min()), "q_p5": float(np.quantile(q, .05)),
            "q_median": float(np.median(q)), "low_quality_fraction": float(np.mean(q < .1)),
            "zero_area_faces": int(np.count_nonzero(area == 0))}


def evaluate_mesh(reference_asset, candidate, config=None):
    config = config or EvaluationConfig()
    if (reference_asset.unit_status, reference_asset.unit_to_mm) != (candidate.unit_status, candidate.unit_to_mm):
        raise ValueError("incompatible coordinate units; convert explicitly before evaluation")
    if reference_asset.scale <= 0:
        raise ValueError("zero reference scale")
    pa, fa, wa = sample_surface(reference_asset, config.samples, config.seed)
    pb, fb, wb = sample_surface(candidate, config.samples, config.seed + 1)
    origin = reference_asset.vertices.mean(axis=0)
    da, ca, ia = surface_distances(pa, candidate, origin)
    db, cb, ib = surface_distances(pb, reference_asset, origin)
    qa, qb = quality(reference_asset), quality(candidate)
    asd = float((da.mean() + db.mean()) / 2)
    d95 = float(max(np.quantile(da, .95), np.quantile(db, .95)))
    maximum = float(max(da.max(), db.max()))
    scale = reference_asset.scale
    metrics = {
        "status": "completed", "reference_version": reference_asset.version_id,
        "candidate_version": candidate.version_id, "reference_hash": reference_asset.geometry_hash,
        "candidate_hash": candidate.geometry_hash, "backend": "VTK.StaticCellLocator.point_to_triangle",
        "distance_definition": "unsigned; D95=max(directional Q95); sampled maximum is not exact Hausdorff",
        "asd": asd, "d95": d95, "sampled_max": maximum,
        "reference_scale": scale, "asd_normalized": asd / scale,
        "d95_normalized": d95 / scale, "sampled_max_normalized": maximum / scale,
        "unit_status": reference_asset.unit_status,
        "coordinate_unit": reference_asset.unit_name or "original_coordinate_unit",
        "unit_to_mm": reference_asset.unit_to_mm,
        "samples_each_direction": config.samples, "seed_ab": config.seed, "seed_ba": config.seed + 1,
        "reference_quality": qa, "candidate_quality": qb,
        "reduction_ratio": 1 - len(candidate.faces) / len(reference_asset.faces),
        "area_change": abs(qb["area"]-qa["area"]) / qa["area"],
        "volume_change": None, "volume_status": "unavailable",
        "volume_reason": "member1 closure/orientation/self-intersection/entity checks not supplied",
    }
    if reference_asset.unit_status == "confirmed":
        metrics["distances_mm"] = {"asd": asd*reference_asset.unit_to_mm,
            "d95": d95*reference_asset.unit_to_mm, "sampled_max": maximum*reference_asset.unit_to_mm}
    details = dict(points_ab=pa, points_ba=pb, distances_ab=da, distances_ba=db,
                   face_ids_a=fa, face_ids_b=fb, weights_a=wa, weights_b=wb,
                   closest_ab=ca, closest_ba=cb, target_cell_ids_ab=ia, target_cell_ids_ba=ib)
    return metrics, details
