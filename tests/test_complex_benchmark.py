import importlib.util
from pathlib import Path
import numpy as np
import pytest
from medical_mesh import MeshAsset


def audit_module():
    path=Path(__file__).resolve().parents[1]/'scripts/audit_complex_benchmark.py'
    spec=importlib.util.spec_from_file_location('complex_audit',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_point_triangle_distance_uses_surface_not_nearest_vertex():
    module=audit_module()
    mesh=MeshAsset(np.array([[0.,0,0],[1,0,0],[0,1,0]]),np.array([[0,1,2]]))
    values=module.distances(np.array([[.2,.2,.1],[.2,.2,0]]),module.dataset(mesh))
    assert values[0]==pytest.approx(.1) and values[1]==pytest.approx(0)


def test_empty_patch_sampling_is_not_zero_error():
    module=audit_module()
    mesh=MeshAsset(np.array([[0.,0,0],[1,0,0],[0,1,0]]),np.array([[0,1,2]]))
    result=module.distance_summary(np.empty((0,3)),mesh)
    assert result['status']=='no_interior_samples' and result['rms'] is None
