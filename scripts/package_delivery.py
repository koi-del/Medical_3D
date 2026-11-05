"""Archive reviewable source, samples and evidence, without local dependencies."""
from pathlib import Path
import zipfile
root=Path(__file__).resolve().parents[1]
output=root/"医学三维模型_合并交付包.zip"
excluded={".venv",".git","__pycache__",".pytest_cache","gui_session","medical-mesh-member2","tools"}
with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for path in sorted(root.rglob("*")):
        relative=path.relative_to(root)
        if relative.as_posix()=='configs/freecad.local.json':continue
        if not path.is_file() or any(p in excluded for p in relative.parts):continue
        if (path.suffix==".zip" and not path.name.endswith('.stlset.zip')) or "egg-info" in str(relative):continue
        if (len(relative.parts)>2 and relative.parts[0]=='results' and
            relative.parts[1] in {'guided_repair_verification','visual_review_verification','delivery_verification','specialist_ui_verification','member2_merge','workflow_ui_verification','user_issue_verification'} and
            any(part in {'sessions','jobs','restored','runs'} for part in relative.parts[2:])):continue
        # Public vendor manuals stay local research references, not our deliverables.
        if len(relative.parts)>2 and relative.parts[:2]==('results','e3d_benchmark') and (path.name.startswith('manual_') or path.suffix=='.pdf'):continue
        # Raw desktop captures can contain account headers or other app windows.
        # Deliver only the cropped benchmark evidence images in evidence/.
        if len(relative.parts)>1 and relative.parts[0]=='results' and relative.parts[1] in ('e3d_benchmark','e3d_complex','e3d_optimization','e3d_cad'):
            if len(relative.parts)==3 and path.suffix=='.png':continue
            if path.name in ('controls.json','windows.json'):continue
        archive.write(path,relative)
print(output.name,output.stat().st_size,"bytes")
