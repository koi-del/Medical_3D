"""Execute in FreeCAD's runtime. Communication is strict JSON plus file paths."""
import json
import math
import os
from pathlib import Path
import traceback


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def shape_info(shape):
    box = shape.BoundBox
    return {
        "actual_representation": shape.ShapeType, "valid": bool(shape.isValid()),
        "closed": bool(shape.isClosed()), "faces": len(shape.Faces),
        "solids": len(shape.Solids), "shells": len(shape.Shells),
        "area_mm2": float(shape.Area), "bbox_mm": [[box.XMin, box.YMin, box.ZMin], [box.XMax, box.YMax, box.ZMax]],
        "shape_volume_mm3": float(shape.Volume) if shape.Solids else None,
    }


def mesh_info(mesh):
    vertices, faces = mesh.Topology
    if not vertices or not faces:
        raise ValueError("empty triangle mesh")
    xyz = [[float(p.x), float(p.y), float(p.z)] for p in vertices]
    return {"actual_representation": "triangle_mesh", "valid": None,
            "closed": bool(mesh.isSolid()), "faces": len(faces), "solids": None, "shells": None,
            "bbox_mm": [[min(p[i] for p in xyz) for i in range(3)], [max(p[i] for p in xyz) for i in range(3)]]}


def tessellate(shape, request):
    import MeshPart
    linear = float(request.get("linear_deflection_mm", .01))
    angular = float(request.get("angular_deflection_rad", .1))
    if not math.isfinite(linear) or linear <= 0 or not math.isfinite(angular) or not 0 < angular < math.pi:
        raise ValueError("invalid tessellation parameters")
    mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=linear,
                                  AngularDeflection=angular, Relative=False)
    if len(mesh.Topology[1]) == 0:
        raise ValueError("CAD surface produced an empty tessellation")
    return mesh


def prepare_iges(shape):
    """Split a complete spherical face at its periodic seam without approximating it.

    OCC 7.8 IGES can re-import a single full 2*pi spherical face with zero U span.
    Limited to complete spherical faces: do NOT reconstruct arbitrary trimmed faces.
    """
    import Part
    faces, changes = [], []
    for index, face in enumerate(shape.Faces):
        surface = face.Surface
        if isinstance(surface, Part.Sphere) and abs(face.Area - 4*math.pi*surface.Radius**2) <= face.Area*1e-10:
            u0, u1, v0, v1 = face.ParameterRange
            if abs((u1-u0)-2*math.pi) > 1e-8:
                faces.append(face)
                continue
            middle = (u0+u1)/2
            parts = [surface.toShape(a, b, v0, v1) for a, b in ((u0, middle), (middle, u1))]
            if face.Orientation == "Reversed":
                for part in parts:
                    part.reverse()
            area_delta = abs(sum(part.Area for part in parts)-face.Area)
            if area_delta > max(1e-9, face.Area*1e-10):
                raise ValueError("periodic surface split changed area")
            faces.extend(parts)
            changes.append({"face_index": index, "operation": "split_full_sphere_periodic_U_into_two_exact_patches",
                            "area_delta_mm2": area_delta, "surface_approximation": False})
        else:
            faces.append(face)
    return (Part.makeCompound(faces) if changes else shape), changes


def make_fixtures(request):
    import FreeCAD as App
    import Part
    root = Path(request["fixture_dir"])
    root.mkdir(parents=True, exist_ok=True)
    box = Part.makeBox(13, 7, 4, App.Vector(31, -19, 11))
    sphere = Part.makeSphere(5, App.Vector(14, -8, 20))
    patch = Part.makePlane(8, 6, App.Vector(37, -12, 17))
    asymmetric = Part.makeBox(12, 9, 6).cut(Part.makeBox(7, 5, 8, App.Vector(6, 5, -1)))
    asymmetric.translate(App.Vector(47, -21, 13))
    cases = {"offset_box": box, "sphere": sphere, "open_patch": patch, "asymmetric": asymmetric}
    manifest = []
    for name, shape in cases.items():
        directory = root / name
        directory.mkdir(exist_ok=True)
        shape.exportStep(str(directory / "source.step"))
        iges_shape, adaptation = prepare_iges(shape)
        iges_shape.exportIges(str(directory / "source.igs"))
        if name == "sphere":
            shape.exportIges(str(directory / "legacy_periodic.igs"))
        mesh = tessellate(shape, {"linear_deflection_mm": .03, "angular_deflection_rad": .2})
        mesh.write(str(directory / "source.stl"))
        shape.exportBrep(str(directory / "source.brep"))
        manifest.append({"case": name, "source_kind": "synthetic_CAD_not_medical", "unit": "mm",
                         "cad": shape_info(shape), "stl": mesh_info(mesh),
                         "stl_tessellation": {"linear_deflection_mm": .03, "angular_deflection_rad": .2},
                         "iges_export_adaptation": adaptation,
                         "paths": {f: str((directory / ("source." + f)).resolve()) for f in ("stl", "step", "igs")}})
    write_json(root / "manifest.json", manifest)
    return {"status": "completed", "manifest": manifest, "fixture_dir": str(root)}


def execute(request):
    import FreeCAD as App
    import Part
    import Mesh
    import MeshPart
    version = {"freecad_version": list(App.Version()), "python_version": __import__("sys").version,
               "occ_version": getattr(Part, "OCC_VERSION", None), "pid": os.getpid()}
    mode = request["mode"]
    if mode == "probe":
        return {"status": "completed", **version, "meshpart_available": True}
    if mode == "fixtures":
        return {**make_fixtures(request), **version}
    source = request["input_path"]
    is_mesh = request["source_format"] == "stl"
    shape = None
    if is_mesh:
        mesh = Mesh.Mesh(source)
        info = mesh_info(mesh)
    else:
        shape = Part.read(source)
        if shape.isNull():
            raise ValueError("empty CAD shape")
        info = shape_info(shape)
        if not info["valid"] or info["faces"] == 0 or info["area_mm2"] <= 0:
            raise ValueError("invalid/zero-area input CAD surface; periodic domain may be degenerate")
    if mode == "convert":
        target = request["target_format"]
        if is_mesh:
            shape = Part.Shape()
            tolerance = float(request["sewing_tolerance_mm"])
            if not math.isfinite(tolerance) or tolerance <= 0:
                raise ValueError("invalid sewing tolerance")
            shape.makeShapeFromMesh(mesh.Topology, tolerance)
            if not shape.isValid():
                raise ValueError("invalid mesh-derived CAD shape")
            if request.get("representation", "surface") != "surface":
                raise ValueError("solid qualification requires member1 checks; choose surface explicitly")
        adaptations = []
        if target == "stl":
            tessellate(shape, request).write(request["output_path"])
        elif target == "step":
            shape.exportStep(request["output_path"])
        elif target == "igs":
            shape, adaptations = prepare_iges(shape)
            shape.exportIges(request["output_path"])
        else:
            raise ValueError("unsupported target format")
        return {"status": "completed", **version, "input_geometry": info,
                "in_memory_export_shape": shape_info(shape), "output_type_requires_readback": True,
                "iges_export_adaptation": adaptations}
    if mode == "inspect":
        if shape is not None:
            mesh = tessellate(shape, request)
        vertices, faces = mesh.Topology
        if len(faces) > request.get("max_readback_faces", 500000):
            raise ValueError("readback tessellation exceeds budget")
        path = Path(request["result_path"]).with_suffix(".mesh.json")
        write_json(path, {"vertices": [[p.x, p.y, p.z] for p in vertices], "faces": [list(f) for f in faces]})
        return {"status": "completed", **version, **info, "mesh_json": str(path),
                "tessellation": {"linear_deflection_mm": request.get("linear_deflection_mm"),
                                 "angular_deflection_rad": request.get("angular_deflection_rad"), "relative": False},
                "mesh_faces": len(faces)}
    raise ValueError("unsupported worker mode")


if __name__ == "__main__" or os.environ.get("MEDICAL_MESH_CAD_JOB"):
    request = json.loads(Path(os.environ["MEDICAL_MESH_CAD_JOB"]).read_text(encoding="utf-8"))
    try:
        result = execute(request)
    except Exception as error:
        result = {"status": "failed", "error": str(error), "traceback": traceback.format_exc()}
    result.update(request_id=request["request_id"], mode=request["mode"])
    write_json(request["result_path"], result)
