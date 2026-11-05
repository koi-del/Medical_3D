from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict
import time
import numpy as np
from ..core.model import TaskResult
from .boundary_loops import extract_boundaries


@dataclass
class DiagnosisResult(TaskResult):
    defects: dict = field(default_factory=dict)
    boundaries: list = field(default_factory=list)
    components: list = field(default_factory=list)
    self_intersection: dict = field(default_factory=lambda: {"status": "unverified", "face_ids": None})


def adjacency(faces, face_ids=None):
    table = defaultdict(list)
    if face_ids is None:
        face_ids = range(len(faces))
    for fid in face_ids:
        face = faces[fid]
        for a, b in zip(face, np.roll(face, -1)):
            a, b = int(a), int(b)
            table[min(a, b), max(a, b)].append((int(fid), 1 if a < b else -1))
    return dict(table)


def connected_groups(nodes, neighbors):
    unseen = set(nodes)
    groups = []
    while unseen:
        stack, group = [min(unseen)], []
        while stack:
            x = stack.pop()
            if x not in unseen:
                continue
            unseen.remove(x)
            group.append(x)
            stack.extend(neighbors.get(x, ()))
        groups.append(sorted(group))
    return groups


def detect_defects(asset, *, relative_area_tolerance=1e-12, absolute_area_tolerance=0.0,
                   check_self_intersection=False):
    start = time.perf_counter()
    if relative_area_tolerance < 0 or absolute_area_tolerance < 0:
        raise ValueError("Area tolerances must be nonnegative")
    v, f = asset.vertices, asset.faces
    tri = v[f]
    area = np.linalg.norm(np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0]), axis=1) / 2
    scale = float(np.linalg.norm(np.ptp(v, axis=0)))
    degenerate = np.flatnonzero(area <= max(absolute_area_tolerance, relative_area_tolerance * scale**2)).tolist()
    seen, duplicate, duplicate_groups = {}, [], defaultdict(list)
    for i, face in enumerate(f):
        key = tuple(sorted(map(int, face)))
        if key in seen:
            duplicate.append(i)
            duplicate_groups[seen[key]].append(i)
        else:
            seen[key] = i
    degenerate_set = set(degenerate)
    valid = [i for i in range(len(f)) if i not in degenerate_set]
    raw_edges = adjacency(f, valid)
    clean_ids = sorted(set(valid)-set(duplicate))
    edges = adjacency(f, clean_ids)
    nonmanifold = [e for e, inc in edges.items() if len(inc) > 2]
    conflicts = [{"edge": e, "face_ids": [x[0] for x in inc]} for e, inc in edges.items()
                 if len(inc) == 2 and inc[0][1] == inc[1][1]]
    face_neighbors = defaultdict(set)
    incident = defaultdict(set)
    vertex_links = defaultdict(list)
    vertex_face_neighbors = defaultdict(lambda: defaultdict(set))
    for fid in clean_ids:
        a, b, c = map(int, f[fid])
        for x, y, z in ((a, b, c), (b, c, a), (c, a, b)):
            incident[x].add(fid)
            vertex_links[x].append((y, z))
    for (a, b), inc in edges.items():
        ids = [x[0] for x in inc]
        if ids:
            # Star graph suffices for connectivity; avoid quadratic all-pairs.
            for fid in ids[1:]:
                face_neighbors[ids[0]].add(fid)
                face_neighbors[fid].add(ids[0])
                for x in (a, b):
                    vertex_face_neighbors[x][ids[0]].add(fid)
                    vertex_face_neighbors[x][fid].add(ids[0])
    bad_vertices = []
    for x, ids in incident.items():
        sectors = connected_groups(ids, vertex_face_neighbors[x])
        link_degree = defaultdict(int)
        for a, b in vertex_links[x]:
            link_degree[a] += 1
            link_degree[b] += 1
        degrees = list(link_degree.values())
        valid_link = all(d == 2 for d in degrees) or (degrees.count(1) == 2 and all(d in (1, 2) for d in degrees))
        if len(sectors) != 1 or not valid_link:
            bad_vertices.append({"vertex_id": x, "sector_count": len(sectors), "face_ids": sorted(ids),
                                 "position": v[x].tolist()})
    components = connected_groups(clean_ids, face_neighbors)
    boundaries = extract_boundaries(v, edges)
    self_check = {"status": "unverified", "face_ids": None, "reason": "Not requested"}
    warnings = []
    if asset.unit_status == "unknown":
        warnings.append("Unit unknown: lengths are in original coordinate units")
    if check_self_intersection:
        try:
            import pymeshlab
            ms = pymeshlab.MeshSet()
            ms.add_mesh(pymeshlab.Mesh(vertex_matrix=v.copy(), face_matrix=f.copy()))
            ms.apply_filter("compute_selection_by_self_intersections_per_face")
            ids = np.flatnonzero(ms.current_mesh().face_selection_array()).tolist()
            self_check = {"status": "verified", "face_ids": ids, "marked_face_count": len(ids), "backend": "pymeshlab"}
        except Exception as e:
            self_check = {"status": "unverified", "face_ids": None, "reason": f"{type(e).__name__}: {e}"}
            warnings.append("Self-intersection check unavailable or failed")
    defects = {"duplicate_face_ids": duplicate, "duplicate_groups": dict(duplicate_groups),
               "degenerate_face_ids": degenerate,
               "non_manifold_edges": [{"edge": e, "face_ids": [x[0] for x in edges[e]],
                                       "position": v[list(e)].mean(axis=0).tolist()} for e in nonmanifold],
               "non_manifold_vertices": bad_vertices, "orientation_conflicts": conflicts}
    for name in ("duplicate", "degenerate"):
        defects[name + "_positions"] = tri[defects[name + "_face_ids"]].mean(axis=1).tolist()
    topology_ok = not (duplicate or degenerate or nonmanifold or bad_vertices or conflicts)
    quality = "diagnosed"
    if topology_ok and self_check["status"] == "verified" and not self_check["face_ids"]:
        quality = "verified_open_surface" if boundaries else "verified_closed_surface"
    metrics = {"vertex_count": len(v), "face_count": len(f), "component_count": len(components),
               "duplicate_face_count": len(duplicate), "degenerate_face_count": len(degenerate),
               "boundary_edge_count": sum(len(x) == 1 for x in edges.values()),
               "boundary_loop_count": sum(x["kind"] == "simple_loop" for x in boundaries),
               "non_manifold_edge_count": len(nonmanifold), "non_manifold_vertex_count": len(bad_vertices),
               "orientation_conflict_count": len(conflicts), "area": float(area.sum()),
               "bbox": [v.min(axis=0).tolist(), v.max(axis=0).tolist()], "bbox_diagonal": scale,
               "topology_passed": topology_ok, "self_intersection_status": self_check["status"],
               "raw_topology": {"boundary_edge_count": sum(len(x) == 1 for x in raw_edges.values()),
                                "non_manifold_edge_count": sum(len(x) > 2 for x in raw_edges.values())},
               "topology_basis": "duplicate and degenerate faces excluded; original face IDs retained"}
    return DiagnosisResult(status="completed", input_version=asset.version, output_version=asset.version,
                           metrics=metrics, warnings=warnings, defects=defects, boundaries=boundaries,
                           components=components, self_intersection=self_check, quality_status=quality,
                           elapsed_seconds=time.perf_counter()-start)
