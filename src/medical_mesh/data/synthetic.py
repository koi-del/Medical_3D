from collections import deque
import numpy as np
from ..core.model import MeshAsset
from ..detection.topology import adjacency


def tetrahedron(offset=(0,0,0)):
    v = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]], float) + offset
    f = np.array([[0,2,1],[0,1,3],[1,2,3],[2,0,3]])
    return MeshAsset(v, f, source_unit="mm", unit_to_mm=1, unit_status="confirmed", expected_component_count=1, expected_open_boundaries=0)


def sphere(segments=32, rings=16):
    v = [[0,0,1]]
    for j in range(1,rings):
        phi = np.pi*j/rings
        for i in range(segments):
            theta = 2*np.pi*i/segments
            v.append([np.sin(phi)*np.cos(theta),np.sin(phi)*np.sin(theta),np.cos(phi)])
    bottom = len(v)
    v.append([0,0,-1])
    f = []
    for i in range(segments):
        ni = (i+1)%segments
        f.append([0,1+i,1+ni])
        for j in range(rings-2):
            a,b = 1+j*segments+i,1+j*segments+ni
            c,d = a+segments,b+segments
            f.extend([[a,c,b],[b,c,d]])
        a,b = 1+(rings-2)*segments+i,1+(rings-2)*segments+ni
        f.append([a,bottom,b])
    return MeshAsset(np.array(v),np.array(f), source_unit="mm", unit_to_mm=1,unit_status="confirmed",
                     expected_component_count=1,expected_open_boundaries=0)


def open_tube(segments=24):
    theta = np.arange(segments)*2*np.pi/segments
    v = np.array([[np.cos(t),np.sin(t),z] for z in (0,3) for t in theta])
    f = []
    for i in range(segments):
        n = (i+1)%segments
        f.extend([[i,n,i+segments],[n,n+segments,i+segments]])
    return MeshAsset(v,np.array(f),source_unit="mm",unit_to_mm=1,unit_status="confirmed",
                     expected_component_count=1,expected_open_boundaries=2)


def two_components():
    a,b = tetrahedron(),tetrahedron((4,0,0))
    return MeshAsset(np.vstack((a.vertices,b.vertices)),np.vstack((a.faces,b.faces+4)),
                     expected_component_count=2,expected_open_boundaries=0)


def bowtie_vertex():
    a,b = tetrahedron(),tetrahedron((-1,-1,-1))
    # Share a single vertex but no edges: both closed vertex fans must be detected.
    v = np.vstack((a.vertices,b.vertices[:3]))
    mapping = np.array([4,5,6,0])
    return MeshAsset(v,np.vstack((a.faces,mapping[b.faces])))


def intersecting_triangles():
    return MeshAsset(np.array([[-1,-1,0],[1,-1,0],[0,1,0],[0,-.5,-1],[0,-.5,1],[0,.5,0]]),
                     np.array([[0,1,2],[3,4,5]]))


def inject_defects(asset, kind, *, seed=20261016, count=1):
    if seed <= 0 or count < 1:
        raise ValueError("seed/count must be positive")
    rng = np.random.default_rng(seed)
    v,f = asset.vertices.copy(),asset.faces.copy()
    start = int(rng.integers(len(f)))
    chosen = []
    if kind == "hole":
        table = adjacency(f)
        neighbors = {i:set() for i in range(len(f))}
        for inc in table.values():
            for a,_ in inc:
                neighbors[a].update(b for b,_ in inc if a != b)
        queue, visited = deque([start]),set()
        while queue and len(chosen) < count:
            i = queue.popleft()
            if i in visited:
                continue
            visited.add(i)
            chosen.append(i)
            queue.extend(sorted(neighbors[i]-visited))
        f = np.delete(f,chosen,axis=0)
    elif kind in ("duplicate", "reverse_duplicate", "flip"):
        chosen = rng.choice(len(f),size=min(count,len(f)),replace=False).tolist()
        if kind == "flip":
            f[chosen] = f[chosen][:,[0,2,1]]
        else:
            added = f[chosen] if kind == "duplicate" else f[chosen][:,[0,2,1]]
            f = np.vstack((f,added))
    elif kind == "degenerate":
        chosen = [start]
        f = np.vstack((f,[[f[start,0],f[start,0],f[start,1]]] * count))
    elif kind == "non_manifold_edge":
        chosen = [start]
        a,b = map(int,f[start,:2])
        midpoint = (v[a]+v[b])/2
        normal = np.cross(v[f[start,1]]-v[f[start,0]],v[f[start,2]]-v[f[start,0]])
        normal /= np.linalg.norm(normal)
        v = np.vstack((v,midpoint + normal * np.linalg.norm(np.ptp(v,axis=0))*.1))
        f = np.vstack((f,[a,b,len(v)-1]))
    elif kind == "noise":
        chosen = rng.choice(len(v),size=min(count,len(v)),replace=False).tolist()
        v[chosen] += rng.normal(size=(len(chosen),3))*np.linalg.norm(np.ptp(v,axis=0))*.005
    else:
        raise ValueError("Unknown defect type")
    metadata = {"kind":kind,"seed":seed,"count":count,"parent_id":asset.asset_id,
                "parent_version":asset.version,"reference_geometry_sha256":asset.geometry_hash(),
                "original_face_ids" if kind != "noise" else "original_vertex_ids":chosen,
                "original_faces":asset.faces[chosen].tolist() if kind != "noise" else [],
                "added_face_ids":list(range(len(asset.faces),len(f))) if len(f)>len(asset.faces) else []}
    return asset.derive(vertices=v,faces=f,parameters=metadata),metadata
