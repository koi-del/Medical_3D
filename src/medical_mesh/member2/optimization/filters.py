import numpy as np
from scipy.sparse import coo_matrix


def boundary_vertices(asset):
    faces = asset.faces
    edges = np.sort(np.vstack((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])), axis=1)
    unique, degree = np.unique(edges, axis=0, return_counts=True)
    if np.any(degree > 2):
        raise ValueError("nonmanifold edges: request member1 repair before smoothing")
    return np.unique(unique[degree == 1]), unique


def smooth_fixed(asset, method, iterations):
    boundary, edges = boundary_vertices(asset)
    n = len(asset.vertices)
    rows, cols = np.concatenate((edges[:, 0], edges[:, 1])), np.concatenate((edges[:, 1], edges[:, 0]))
    graph = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n)).tocsr()
    degree = np.asarray(graph.sum(axis=1)).ravel()
    movable = degree > 0
    movable[boundary] = False
    vertices = asset.vertices.copy()
    for _ in range(iterations):
        for coefficient in ([.5] if method == "laplacian" else [.5, -.53]):
            average = graph @ vertices / np.maximum(degree[:, None], 1)
            vertices[movable] += coefficient * (average[movable] - vertices[movable])
    return vertices


def process_mesh(asset, config):
    """Generate a candidate only. This does not certify or accept its quality."""
    operation = config.get("operation", "qem")
    if operation in {"laplacian", "taubin"}:
        iterations = config.get("iterations", 5)
        if isinstance(iterations, bool) or not isinstance(iterations, int) or not 0 <= iterations <= 100:
            raise ValueError("iterations must be integer between 0 and 100")
        vertices = smooth_fixed(asset, operation, iterations)
        params = {**config, "backend": "numpy_scipy_uniform_fixed_boundary", "iterations": iterations}
        return asset.derive(vertices, asset.faces, operation, params)
    import pymeshlab
    required = ("meshing_decimation_quadric_edge_collapse" if operation == "qem"
                else "meshing_isotropic_explicit_remeshing")
    if required not in pymeshlab.filter_list():
        # macOS hidden-file flags can hide installed plug-ins from Qt's directory
        # enumeration. Load the known bundled meshing plug-in explicitly.
        from pathlib import Path
        plugin_dir = Path(pymeshlab.__file__).parent / "PlugIns"
        plugin = next((p for p in plugin_dir.glob("*filter_meshing.*") if p.suffix in {".so", ".dll", ".dylib"}), None)
        if plugin is not None:
            pymeshlab.load_plugin(str(plugin))
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertex_matrix=asset.vertices.copy(), face_matrix=asset.faces.astype(np.int32)), "reference")
    if operation == "qem":
        ratio = float(config.get("keep_ratio", .5))
        if not np.isfinite(ratio) or not 0 < ratio <= 1:
            raise ValueError("keep_ratio must be in (0,1]")
        target = config.get('target_faces',max(4,int(len(asset.faces)*ratio)))
        if isinstance(target,bool) or not isinstance(target,int) or not 4<=target<=len(asset.faces):
            raise ValueError('target_faces must be an integer from 4 to the original face count')
        if target==len(asset.faces):return asset.derive(asset.vertices,asset.faces,operation,{**config,'target_faces':target,'backend':'identity_target'})
        ms.apply_filter("meshing_decimation_quadric_edge_collapse", targetfacenum=target,
                        preserveboundary=True, preservenormal=True, preservetopology=True,
                        qualitythr=.5,optimalplacement=True,autoclean=True)
    elif operation == "remesh":
        target = float(config.get("target_edge_length", asset.scale / 30))
        iterations = config.get("iterations", 3)
        if not np.isfinite(target) or target <= 0 or not isinstance(iterations, int) or not 1 <= iterations <= 20:
            raise ValueError("positive edge length and 1..20 iterations required")
        ms.apply_filter("meshing_isotropic_explicit_remeshing", iterations=iterations,
                        targetlen=pymeshlab.PureValue(target))
    else:
        raise ValueError(f"unsupported operation: {operation}")
    mesh = ms.current_mesh()
    result = asset.derive(mesh.vertex_matrix(), mesh.face_matrix(), operation, {**config, "backend": "pymeshlab"})
    if operation=='remesh' and config.get('quality_refinement',True):
        from .refine import refine_quality
        vertices,faces,record=refine_quality(asset,result,3)
        result=asset.derive(vertices,faces,operation,{**result.parameters,'quality_refinement':record})
    smooth_steps = config.get("smooth_iterations", 0)
    if smooth_steps:
        result = process_mesh(result, {"operation": "taubin", "iterations": smooth_steps})
        # Preserve the full chain, and the original reference relationship.
        result = asset.derive(result.vertices, result.faces, operation, {**config, "backend": "pymeshlab+uniform_taubin"})
    return result
