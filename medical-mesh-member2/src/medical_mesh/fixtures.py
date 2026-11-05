from pathlib import Path
import numpy as np
import trimesh
from medical_mesh.core.model import MeshAsset, save_asset, write_json


def plane(z=0.0, subdivide=False):
    if not subdivide:
        v = np.array([[0, 0, z], [1, 0, z], [1, 1, z], [0, 1, z]], dtype=float)
        f = np.array([[0, 1, 2], [0, 2, 3]])
    else:
        v = np.array([[0, 0, z], [1, 0, z], [1, 1, z], [0, 1, z], [.5, .5, z]], dtype=float)
        f = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])
    return MeshAsset(v, f, unit_status="confirmed", unit_name="mm", unit_to_mm=1.)


def open_tube(segments=32, levels=8):
    angle = np.arange(segments)*2*np.pi/segments
    vertices = np.array([[np.cos(t), np.sin(t), z] for z in np.linspace(0, 4, levels) for t in angle])
    faces = []
    for row in range(levels-1):
        for col in range(segments):
            a, b = row*segments+col, row*segments+(col+1)%segments
            c, d = a+segments, b+segments
            faces.extend([[a, b, d], [a, d, c]])
    return MeshAsset(vertices, np.array(faces), unit_status="confirmed", unit_name="mm", unit_to_mm=1.)


def generate_fixtures(directory):
    directory = Path(directory)
    sphere_mesh = trimesh.creation.icosphere(subdivisions=3, radius=20)
    sphere = MeshAsset(sphere_mesh.vertices, sphere_mesh.faces, unit_status="confirmed", unit_name="mm", unit_to_mm=1.)
    shifted = sphere.derive(sphere.vertices * [1, .7, 1.4] + [83, -27, 15], sphere.faces, "fixture", {})
    small = sphere.vertices*.15 + [70, 0, 0]
    two = MeshAsset(np.vstack((sphere.vertices, small)), np.vstack((sphere.faces, sphere.faces+len(sphere.vertices))),
                    unit_status="confirmed", unit_name="mm", unit_to_mm=1.)
    assets = {"plane": plane(), "plane_shifted": plane(2.5), "plane_subdivided": plane(subdivide=True),
              "sphere": sphere, "open_tube": open_tube(), "two_components": two, "offcenter_asymmetric": shifted}
    manifest = []
    for name, asset in assets.items():
        path = save_asset(asset, directory / (name+".npz"))
        trimesh.Trimesh(asset.vertices, asset.faces, process=False).export(str(path.with_suffix(".stl")))
        manifest.append({"name": name, "path": str(path.resolve()), "kind": "synthetic_not_medical",
                         "unit": "mm", "geometry_sha256": asset.geometry_hash,
                         "group_id": "plane" if name.startswith("plane") else "sphere" if name in {"sphere", "offcenter_asymmetric"} else name})
    write_json(directory / "manifest.json", manifest)
    return manifest
