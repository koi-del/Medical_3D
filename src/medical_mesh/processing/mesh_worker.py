"""JSON/NPZ process boundary, callable from member 2's job queue."""
import argparse
import json
import traceback
import shutil
import time
from pathlib import Path
from ..io.mesh_io import load_mesh,save_mesh
from ..detection.topology import detect_defects
from .repair_policy import repair_mesh,RepairOptions


def run_job(request):
    output=Path(request["output_dir"])
    output.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    def progress(stage,status='running'):
        temporary=output/'progress.tmp'
        temporary.write_text(json.dumps(dict(stage=stage,status=status,elapsed_seconds=time.monotonic()-started),ensure_ascii=False),encoding='utf-8')
        try:temporary.replace(output/'progress.json')
        except OSError:pass  # A transient progress-reader lock must not fail a mesh task.
    (output/"request.json").write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding="utf-8")
    try:
        progress('读取与校验输入')
        project_roles=None
        if Path(request['input_path']).suffix.lower()=='.m3d':
            from ..core.project_bundle import load_project
            asset,_,project_roles,history=load_project(request['input_path'])
            (output/'imported_history').mkdir(exist_ok=True)
            for name,content in history.items():(output/'imported_history'/name).write_bytes(content)
        else:
            asset=load_mesh(request["input_path"],raw_archive=output/"raw_mesh.npz",**request.get("read_options",{}))
        if not (output/"raw_mesh.npz").exists():save_mesh(asset,output/"raw_mesh.npz")
        source=Path(request["input_path"])
        archived=output/("original_input"+source.suffix.lower())
        if source.resolve()!=archived.resolve():shutil.copyfile(source,archived)
        (output/"input_metadata.json").write_text(json.dumps(asset.metadata(),ensure_ascii=False,indent=2),encoding="utf-8")
        save_mesh(asset,output/"canonical_mesh.npz")
        if request["operation"] in ("load","diagnose"):
            progress('构建邻接、检测缺陷与边界')
            result=detect_defects(asset,**request.get("parameters",{}))
            if project_roles is not None:
                if set(project_roles)!={str(b['id']) for b in result.boundaries}:
                    raise ValueError('项目包边界用途与实际检测不一致')
                if any(project_roles[str(b['id'])]=='repair_target' and b['kind']!='simple_loop' for b in result.boundaries):
                    raise ValueError('项目包包含无效补洞目标')
                result.metrics['imported_boundary_roles']=project_roles
            save_mesh(asset,output/"output.npz")
        elif request["operation"]=="repair":
            asset,result=repair_mesh(asset,RepairOptions(**request.get("parameters",{})),progress=progress)
            save_mesh(asset,output/"output.npz")
            (output/"diagnosis_before.json").write_text(json.dumps(result.diagnosis_before,ensure_ascii=False,indent=2),encoding="utf-8")
            (output/"diagnosis_after.json").write_text(json.dumps(result.diagnosis_after,ensure_ascii=False,indent=2),encoding="utf-8")
        elif request['operation'] == 'suggest':
            from .suggestions import suggest_non_manifold_repairs
            result = suggest_non_manifold_repairs(asset, progress=progress,**request.get('parameters', {}))
            save_mesh(asset, output/'output.npz')
        elif request['operation']=='review_optimization':
            from ..integration.review import validate_optimization
            progress('复核优化候选的参考版本、误差与结构')
            parameters=request['parameters'];candidate=load_mesh(parameters['candidate_path'])
            result=validate_optimization(asset,candidate,parameters['verification'])
            save_mesh(candidate,output/'output.npz')
            (output/'diagnosis_before.json').write_text(json.dumps(result.diagnosis_before,ensure_ascii=False,indent=2),encoding='utf-8')
            (output/'diagnosis_after.json').write_text(json.dumps(result.diagnosis_after,ensure_ascii=False,indent=2),encoding='utf-8')
        else:
            raise ValueError("Unknown operation")
        result.output_paths={"mesh":str((output/"output.npz").resolve())}
        data=result.to_dict()
    except Exception as e:
        data={"status":"failed","input_version":request.get("input_version","unknown"),"output_version":None,
              "metrics":{},"warnings":[],"errors":[f"{type(e).__name__}: {e}"],"elapsed_seconds":0,
              "output_paths":{},"quality_status":"unverified"}
        (output/"worker.log").write_text(traceback.format_exc(),encoding="utf-8")
    if not (output/"worker.log").exists():
        (output/"worker.log").write_text(data["status"]+"\n"+"\n".join(data["errors"]),encoding="utf-8")
    (output/"result.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    progress('任务结束',data['status'])
    return data


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("request")
    args=parser.parse_args()
    result=run_job(json.loads(Path(args.request).read_text(encoding="utf-8")))
    return 0 if result["status"]=="completed" else 2


if __name__=="__main__":
    raise SystemExit(main())
