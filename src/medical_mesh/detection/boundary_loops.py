import numpy as np


def extract_boundaries(vertices, edge_faces):
    edges = [e for e, faces in edge_faces.items() if len(faces) == 1]
    neighbors = {}
    for a, b in edges:
        neighbors.setdefault(a, set()).add(b)
        neighbors.setdefault(b, set()).add(a)
    remaining = set(neighbors)
    boundaries = []
    while remaining:
        seed = min(remaining)
        stack, component = [seed], set()
        while stack:
            v = stack.pop()
            if v in component:
                continue
            component.add(v)
            stack.extend(neighbors[v] - component)
        remaining -= component
        simple = all(len(neighbors[v]) == 2 for v in component)
        ordered = sorted(component)
        if simple:
            ordered, prev, cur = [seed], None, seed
            while True:
                nxt = min(neighbors[cur] - ({prev} if prev is not None else set()))
                if nxt == seed:
                    break
                ordered.append(nxt)
                prev, cur = cur, nxt
        local_edges = [e for e in edges if e[0] in component]
        points = vertices[ordered]
        boundaries.append({"id": len(boundaries), "kind": "simple_loop" if simple else "chain_or_branch",
                           "role": "unknown", "vertex_ids": ordered, "edges": local_edges,
                           "adjacent_face_ids": sorted({edge_faces[e][0][0] for e in local_edges}),
                           "edge_count": len(local_edges),
                           "perimeter": float(sum(np.linalg.norm(vertices[a]-vertices[b]) for a, b in local_edges)),
                           "bbox": [points.min(axis=0).tolist(), points.max(axis=0).tolist()],
                           "span": float(np.linalg.norm(np.ptp(points, axis=0)))})
    return boundaries
