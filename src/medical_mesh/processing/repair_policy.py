from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict, deque
import time
import numpy as np
from ..core.model import TaskResult
from ..detection.topology import detect_defects, adjacency


@dataclass
class RepairOptions:
    remove_duplicates: bool = False
    remove_degenerate: bool = False
    orient_faces: bool = False
    fill_boundary_ids: tuple[int, ...] = ()
    delete_face_ids: tuple[int, ...] = ()
    split_vertex_ids: tuple[int, ...] = ()
    max_hole_edges: int = 64
    max_hole_span: float = 10.0
    max_planarity_ratio: float = 0.02
    preserve_components: bool = True
    check_self_intersection: bool = False
    boundary_roles: dict[str, str] = field(default_factory=dict)
    hole_method: str = 'planar'


@dataclass
class RepairResult(TaskResult):
    diagnosis_before: dict = field(default_factory=dict)
    diagnosis_after: dict = field(default_factory=dict)
    operations: list = field(default_factory=list)
    accepted: bool = False


def _orient(faces):
    edges = adjacency(faces)
    graph = defaultdict(list)
    for inc in edges.values():
        if len(inc) == 2:
            (a, da), (b, db) = inc
            graph[a].append((b, int(da == db)))
            graph[b].append((a, int(da == db)))
    flips = {}
    for seed in range(len(faces)):
        if seed in flips:
            continue
        flips[seed] = 0
        queue = deque([seed])
        component=[]
        while queue:
            a = queue.popleft()
            component.append(a)
            for b, parity in graph[a]:
                wanted = flips[a] ^ parity
                if b in flips and flips[b] != wanted:
                    raise ValueError("Non-orientable or contradictory face neighborhood")
                if b not in flips:
                    flips[b] = wanted
                    queue.append(b)
        # Both coherent orientations are valid locally. Change the smaller
        # subset instead of letting a flipped BFS seed invert the whole shell.
        if sum(flips[i] for i in component)>len(component)/2:
            for i in component:flips[i]^=1
    out = faces.copy()
    changed = [i for i, flip in flips.items() if flip]
    out[changed] = out[changed][:, [0, 2, 1]]
    return out, changed


def _cross(a, b):
    return float(a[0]*b[1]-a[1]*b[0])


def _triangulate_loop(vertices, ordered, faces, options):
    """Projected ear clipping for simple, near-planar, explicitly selected loops."""
    if len(ordered) < 3 or len(ordered) > options.max_hole_edges:
        raise ValueError("Selected hole exceeds edge limit or has fewer than 3 vertices")
    points = vertices[ordered]
    span = np.linalg.norm(np.ptp(points, axis=0))
    if span > options.max_hole_span:
        raise ValueError("Selected hole exceeds span limit (original coordinate units)")
    _, _, axes = np.linalg.svd(points-points.mean(axis=0), full_matrices=False)
    residual = np.max(np.abs((points-points.mean(axis=0)) @ axes[-1]))
    if residual > options.max_planarity_ratio * span:
        raise ValueError("Nonplanar hole requires another repair method")
    # Choose cap orientation opposite the existing boundary face traversal.
    edges = adjacency(faces)
    a, b = ordered[:2]
    inc = edges.get((min(a,b), max(a,b)), [])
    if len(inc) != 1:
        raise ValueError("Selected boundary changed; rerun diagnosis")
    direction = 1 if a < b else -1
    if inc[0][1] == direction:
        ordered = list(reversed(ordered))
        points = vertices[ordered]
    xy = (points-points.mean(axis=0)) @ axes[:2].T
    eps = max(span**2 * 1e-12, np.finfo(float).tiny)
    area = sum(_cross(xy[i], xy[(i+1) % len(xy)]) for i in range(len(xy)))
    if abs(area) <= eps:
        raise ValueError("Projected hole has zero area")
    sign = 1 if area > 0 else -1
    # Reject projected self-crossing boundaries, including collinear overlaps.
    def intersects(a, b, c, d):
        ab_c, ab_d = _cross(b-a, c-a), _cross(b-a, d-a)
        cd_a, cd_b = _cross(d-c, a-c), _cross(d-c, b-c)
        if ab_c*ab_d < -eps**2 and cd_a*cd_b < -eps**2:
            return True
        for p, q, r, cr in ((a,b,c,ab_c), (a,b,d,ab_d), (c,d,a,cd_a), (c,d,b,cd_b)):
            if abs(cr) <= eps and np.all(r >= np.minimum(p,q)-np.sqrt(eps)) and np.all(r <= np.maximum(p,q)+np.sqrt(eps)):
                return True
        return False
    n = len(xy)
    for i in range(n):
        for j in range(i+1,n):
            if j == (i+1)%n or i == (j+1)%n:
                continue
            if intersects(xy[i],xy[(i+1)%n],xy[j],xy[(j+1)%n]):
                raise ValueError("Projected boundary is self-intersecting")
    remaining, triangles = list(range(n)), []
    while len(remaining) > 3:
        found = False
        for k, b in enumerate(remaining):
            a, c = remaining[k-1], remaining[(k+1)%len(remaining)]
            if sign*_cross(xy[b]-xy[a], xy[c]-xy[b]) <= eps:
                continue
            contains = False
            for p in remaining:
                if p in (a,b,c):
                    continue
                if all(sign*_cross(xy[y]-xy[x], xy[p]-xy[x]) >= -eps for x,y in ((a,b),(b,c),(c,a))):
                    contains = True
                    break
            if contains:
                continue
            triangles.append([ordered[a],ordered[b],ordered[c]])
            remaining.pop(k)
            found = True
            break
        if not found:
            raise ValueError("Ear clipping failed; boundary may be degenerate")
    triangles.append([ordered[i] for i in remaining])
    return triangles


def _boundary_geometry(asset, diagnosis, excluded=()):
    return {tuple(sorted(tuple(asset.vertices[i]) for i in edge))
            for b in diagnosis.boundaries if b["id"] not in excluded for edge in b["edges"]}


def repair_mesh(asset, options=None, progress=None):
    """Return (accepted mesh or unchanged input, RepairResult). No implicit repair."""
    options = options or RepairOptions()
    start = time.perf_counter()
    if progress:progress('检测输入缺陷')
    before = detect_defects(asset, check_self_intersection=options.check_self_intersection)
    result = RepairResult(status="rejected", input_version=asset.version, output_version=asset.version,
                          diagnosis_before=before.to_dict(), quality_status=before.quality_status)
    try:
        if options.max_hole_span <= 0 or options.max_hole_edges < 3 or options.max_planarity_ratio < 0:
            raise ValueError("Invalid hole repair limits")
        ids = set(options.fill_boundary_ids)
        if options.hole_method not in ('planar','quadric','surface'):
            raise ValueError('Unknown hole filling method')
        if ids and options.hole_method in ('quadric','surface') and not options.check_self_intersection:
            raise ValueError('曲面补洞必须启用自交检测')
        if any(i < 0 or i >= len(before.boundaries) for i in ids):
            raise ValueError("Unknown boundary ID")
        roles = options.boundary_roles
        valid_roles = {'uncertain', 'natural', 'repair_target'}
        if any(str(b['id']) not in roles for b in before.boundaries) and roles:
            raise ValueError('Boundary roles must cover every current boundary')
        if any(k not in {str(b['id']) for b in before.boundaries} or v not in valid_roles
               for k, v in roles.items()):
            raise ValueError('Invalid boundary role or stale boundary ID')
        if roles and any(roles[str(i)] != 'repair_target' for i in ids):
            raise ValueError('Natural or uncertain boundaries cannot be filled')
        deleted = set(options.delete_face_ids)
        if any(i < 0 or i >= len(asset.faces) for i in deleted):
            raise ValueError("Unknown face ID")
        if options.remove_duplicates:
            deleted.update(before.defects["duplicate_face_ids"])
        if options.remove_degenerate:
            deleted.update(before.defects["degenerate_face_ids"])
        if deleted:
            result.operations.append({"operation": "delete_selected_faces", "input_face_ids": sorted(deleted)})
        faces = asset.faces[[i for i in range(len(asset.faces)) if i not in deleted]].copy()
        vertices = asset.vertices
        if progress:progress('生成受控修复候选')
        if options.split_vertex_ids:
            from .vertex_split import split_vertex_fans
            vertices,faces,records=split_vertex_fans(vertices,faces,options.split_vertex_ids)
            result.operations.append(dict(operation='split_vertex_fans',splits=records))
        if not len(faces):
            raise ValueError("Repair would remove all faces")
        if options.orient_faces:
            faces, changed = _orient(faces)
            result.operations.append({"operation": "coherent_orientation", "candidate_face_ids": changed})
        for i in sorted(ids):
            boundary = before.boundaries[i]
            if boundary["kind"] != "simple_loop":
                raise ValueError("Only simple boundary loops can be filled")
            details={"method":"projected_ear_clipping"}
            if options.hole_method == 'surface':
                from .surface_cap import surface_cap
                vertices,triangles,details=surface_cap(vertices,faces,boundary['vertex_ids'],options)
            elif options.hole_method == 'quadric':
                from .curved_cap import quadric_cap
                vertices,triangles,details=quadric_cap(vertices,faces,boundary['vertex_ids'],options)
            else:
                triangles = _triangulate_loop(vertices, boundary["vertex_ids"], faces, options)
            faces = np.vstack((faces, triangles))
            result.operations.append({"operation": "fill_selected_loop", "input_boundary_id": i,
                                      "role": "repair_target", "added_faces": triangles, **details})
        if not result.operations:
            raise ValueError("No repair target or strategy selected")
        candidate = asset.derive(vertices=vertices,faces=faces, parameters=vars(options))
        if progress:progress('复检候选拓扑与自交')
        after = detect_defects(candidate, check_self_intersection=options.check_self_intersection)
        result.diagnosis_after = after.to_dict()
        if ids and options.hole_method in ('quadric','surface') and not after.metrics['topology_passed']:
            raise ValueError('曲面补洞后仍有拓扑缺陷，候选已拒绝')
        protected = _boundary_geometry(asset, before, ids)
        # Explicit face deletion authorizes changes only to that face's edges.
        # Duplicate/degenerate cleanup does not waive boundary protection.
        selected_delete_edges = {tuple(sorted((tuple(asset.vertices[a]), tuple(asset.vertices[b]))))
                                 for fid in options.delete_face_ids
                                 for a,b in zip(asset.faces[fid], np.roll(asset.faces[fid],-1))}
        protected -= selected_delete_edges
        # Explicit deletion never waives a user's protected-opening decision.
        if roles:
            protected |= _boundary_geometry(asset, before,
                {b['id'] for b in before.boundaries
                 if roles[str(b['id'])] == 'repair_target'
                 or (roles[str(b['id'])] == 'uncertain' and b['kind'] != 'simple_loop')})
        if not protected.issubset(_boundary_geometry(candidate, after)):
            raise ValueError("Repair changes an unselected boundary")
        if options.preserve_components and before.metrics["component_count"] != after.metrics["component_count"]:
            raise ValueError("Repair changes connected component count")
        for metric in ("duplicate_face_count", "degenerate_face_count", "non_manifold_edge_count",
                       "non_manifold_vertex_count", "orientation_conflict_count"):
            if after.metrics[metric] > before.metrics[metric]:
                raise ValueError("Repair introduces or increases " + metric)
        if ids and after.metrics["boundary_loop_count"] != before.metrics["boundary_loop_count"] - len(ids):
            raise ValueError("Selected loop closure failed post-check")
        if options.orient_faces and after.metrics["orientation_conflict_count"]:
            raise ValueError("Orientation conflicts remain")
        if options.check_self_intersection:
            if after.self_intersection["status"] != "verified":
                raise ValueError("Requested self-intersection verification unavailable")
            if after.self_intersection["face_ids"]:
                raise ValueError("Self-intersections remain; candidate rejected")
        result.status, result.accepted = "completed", True
        result.output_version = candidate.version
        result.quality_status = after.quality_status
        result.metrics = {"face_count_before": len(asset.faces), "face_count_after": len(faces),
                          "face_count_change": len(faces)-len(asset.faces),
                          "boundary_edges_before": before.metrics["boundary_edge_count"],
                          "boundary_edges_after": after.metrics["boundary_edge_count"],
                          "new_boundary_edges": sorted(_boundary_geometry(candidate, after)-_boundary_geometry(asset, before)),
                          "residual_defects": {k: after.metrics[k] for k in after.metrics if k.endswith("_count")}}
        result.warnings = after.warnings + (["Self-intersection remains unverified"] if after.self_intersection["status"] != "verified" else [])
        from ..core.changes import mesh_changes
        from .patch_quality import patch_quality
        result.metrics['changes']=mesh_changes(asset,candidate)
        result.metrics['patch_quality']=patch_quality(candidate,result.metrics['changes']['added_face_ids'])
        result.warnings.extend('补片质量提示：'+message for message in result.metrics['patch_quality']['warnings'])
        if options.split_vertex_ids:
            result.warnings.append('顶点拆分保留重合坐标；NPZ/项目包保留拓扑，但STL精确焊接回读可能重新合并这些顶点。')
        return candidate, result
    except ValueError as e:
        result.errors.append(str(e))
        return asset, result
    except Exception as e:
        result.status = "failed"
        result.errors.append(f"{type(e).__name__}: {e}")
        return asset, result
    finally:
        result.elapsed_seconds = time.perf_counter()-start
