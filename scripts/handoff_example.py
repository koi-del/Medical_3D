import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from medical_mesh import load_mesh,detect_defects,repair_mesh,RepairOptions,save_mesh
from medical_mesh.core.versions import VersionStore

root=ROOT/"results"/"handoff_demo"
mesh=load_mesh(ROOT/"data"/"damaged"/"duplicate.npz")
candidate,result=repair_mesh(mesh,RepairOptions(remove_duplicates=True))
assert result.accepted,result.errors
store=VersionStore(root/"versions");store.commit(mesh);store.commit(candidate,result)
save_mesh(candidate,root/"accepted_mesh.npz")
assert store.rollback().version==mesh.version
bad,failed=repair_mesh(mesh,RepairOptions(fill_boundary_ids=(999,)))
assert bad is mesh and failed.status=="rejected"
(root/"success.json").write_text(json.dumps(result.to_dict(),indent=2),encoding="utf-8")
(root/"rejected.json").write_text(json.dumps(failed.to_dict(),indent=2),encoding="utf-8")
print("Handoff success, rejection and persistent rollback verified")
