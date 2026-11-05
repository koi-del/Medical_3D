from dataclasses import asdict
from pathlib import Path
from time import perf_counter
import importlib.metadata
import json
import os
import platform
import sys
import traceback
import numpy as np
from medical_mesh.member2.core.model import load_asset, save_asset, write_json
from medical_mesh.member2.evaluation import evaluate_mesh, EvaluationConfig
from medical_mesh.member2.optimization import optimize_mesh
from medical_mesh.member2.optimization.search import Limits, load_provider
from medical_mesh.member2.reporting import render_report
from medical_mesh.member2.reporting.report import error_figure

def environment_report():
    packages = {}
    for name in ('numpy', 'scipy', 'trimesh', 'pymeshlab', 'vtk', 'pyvista', 'pyvistaqt', 'PySide6-Essentials', 'pytest'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    from medical_mesh.member2.cad import probe_freecad
    return {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(), 'packages': packages, 'freecad': probe_freecad()}

def dispatch(request, progress=lambda *_: None):
    directory = Path(request['output_dir']).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / 'request.json', request)
    started = perf_counter()
    operation = request['operation']
    result = {'operation': operation, 'run_id': directory.name}
    try:
        if operation in {'evaluate', 'optimize'}:
            reference = load_asset(request['input_path'])
            save_asset(reference, directory / 'reference.npz')
            result['input_version'] = reference.version_id
            config = EvaluationConfig(int(request.get('samples', 10000)), int(request.get('seed', 20261018)))
        if operation == 'evaluate':
            progress('evaluating', '双向点到三角表面距离')
            candidate = load_asset(request['candidate_path'])
            metrics, details = evaluate_mesh(reference, candidate, config)
            np.savez_compressed(directory / 'evaluation_samples.npz', **details)
            error_figure(details, directory / 'error.png')
            result.update(status='completed', quality_status='unverified', decision='not_applicable', metrics=metrics)
        elif operation == 'optimize':
            configs = request.get('configs')
            if not configs:
                raise ValueError('non-empty candidate configuration required')
            final = EvaluationConfig(int(request.get('final_samples', max(config.samples, 50000))), config.seed + 10000)
            result.update(optimize_mesh(reference, configs, directory, config, final, Limits(**request.get('limits', {})), load_provider(request.get('provider')), progress))
            best = result['selected_candidate'] or result['preview_candidate']
            if best:
                with np.load(directory / (best + '_final.npz'), allow_pickle=False) as arrays:
                    error_figure({k: arrays[k] for k in arrays.files}, directory / 'error.png')
        elif operation == 'convert':
            from medical_mesh.member2.cad import convert_file
            input_path, unit = (request.get('input_path'), request.get('unit'))
            if request.get('asset_input_path'):
                progress('preparing', '将所选网格快照导出为毫米STL，不更改已接受版本')
                asset = load_asset(request['asset_input_path'])
                if asset.unit_status != 'confirmed':
                    raise ValueError('所选网格单位尚未确认，不能进行CAD转换')
                import trimesh
                input_path = str(directory / 'source_asset_mm.stl')
                trimesh.Trimesh(asset.vertices * asset.unit_to_mm, asset.faces, process=False).export(input_path)
                unit = 'mm'
                result['source_asset'] = {'asset_id': asset.asset_id, 'version_id': asset.version_id, 'unit_name': asset.unit_name, 'factor_to_mm': asset.unit_to_mm, 'geometry_sha256': asset.geometry_hash, 'lifecycle': asset.metadata.get('lifecycle', 'input'), 'quality_status': asset.metadata.get('quality_status', 'unverified'), 'formal_version_unchanged': True}
            result.update(convert_file(input_path, request['target_format'], request.get('cad_config', {}), directory, unit, progress))
        elif operation=='verify_candidate':
            from ..optimization.search import verify_selected
            reference=load_asset(request['input_path']);save_asset(reference,directory/'reference.npz')
            verified,details=verify_selected(reference,request['verification'],request['candidate_id'],directory,
                load_provider(request.get('provider')),progress)
            for key in ('operation','run_id','output_dir','environment','elapsed_seconds'):verified.pop(key,None)
            result.update(verified);error_figure(details,directory/'error.png')
        elif operation == 'probe':
            result.update(status='completed', decision='not_applicable', quality_status='not_applicable', environment=environment_report())
        else:
            raise ValueError('Unsupported task operation')
    except Exception as error:
        result.update(status='failed', quality_status='unverified', decision='rejected', errors=[str(error)], traceback=traceback.format_exc())
    result['elapsed_seconds'] = perf_counter() - started
    result['environment'] = environment_report()
    progress('reporting', '保存JSON/CSV/HTML')
    render_report(result,directory)
    return result

def main():
    if os.name == 'posix':
        try:
            os.setsid()
        except OSError:
            pass
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))

    def progress(stage, message, data=None):
        print(json.dumps({'event': 'progress', 'stage': stage, 'message': message, 'data': data or {}}, ensure_ascii=False), flush=True)
    result = dispatch(request, progress)
    print(json.dumps({'event': 'finished', 'status': result['status']}), flush=True)
    return 0 if result['status'] == 'completed' else 2
if __name__ == '__main__':
    raise SystemExit(main())
