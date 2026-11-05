"""Fast spatial clustering for display only; exact data remains untouched."""
import pyvista as pv
from vtkmodules.vtkFiltersCore import vtkQuadricClustering


def display_mesh(mesh,enabled=True,threshold=100000):
    if not enabled or mesh.n_cells<=threshold:return mesh
    clustering=vtkQuadricClustering();clustering.SetInputData(mesh)
    clustering.SetNumberOfXDivisions(48);clustering.SetNumberOfYDivisions(48);clustering.SetNumberOfZDivisions(48)
    clustering.AutoAdjustNumberOfDivisionsOff();clustering.Update()
    result=pv.wrap(clustering.GetOutput()).copy()
    return result if 0<result.n_cells<mesh.n_cells else mesh
