"""Member 1 mesh subsystem; GUI dependencies are optional."""
from .core.model import MeshAsset
from .io.mesh_io import load_mesh, save_mesh
from .io.shell_set import save_shell_set
from .detection.topology import detect_defects
from .processing.repair_policy import repair_mesh, RepairOptions

__all__ = ["MeshAsset", "load_mesh", "save_mesh", "save_shell_set", "detect_defects", "repair_mesh", "RepairOptions"]
