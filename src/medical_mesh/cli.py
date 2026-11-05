"""Unified explicit CLI; no automatic demonstration entry points."""
import argparse
import json
from pathlib import Path
from datetime import datetime
from uuid import uuid4


def main(argv=None):
    parser=argparse.ArgumentParser(description='医学三维模型工作台：诊断修复、优化评价、CAD转换')
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('gui',help='打开统一工作台，不自动加载或运行样例')
    commands.add_parser('probe',help='检查本机依赖与FreeCAD配置').add_argument('--out')
    for name in ('evaluate','optimize','convert'):
        command=commands.add_parser(name);command.add_argument('--input',required=True);command.add_argument('--out')
        if name=='evaluate':command.add_argument('--candidate',required=True)
        if name!='convert':command.add_argument('--samples',type=int,default=10000)
        if name=='optimize':
            command.add_argument('--operation',choices=['qem','laplacian','taubin','remesh'],default='qem')
            command.add_argument('--ratio',type=float,default=.8);command.add_argument('--iterations',type=int,default=5)
            command.add_argument('--target-faces',type=int)
            command.add_argument('--edge',type=float,default=1.);command.add_argument('--search',action='store_true')
            command.add_argument('--final-samples',type=int,default=50000);command.add_argument('--limits')
        if name=='convert':
            command.add_argument('--target',choices=['stl','step','igs'],required=True)
            command.add_argument('--unit',choices=['mm','cm','m']);command.add_argument('--config')
    args=parser.parse_args(argv)
    if args.command=='gui':
        from .ui.workbench import main as gui
        return gui()
    from .member2.jobs.worker import dispatch
    from .member2.core.model import save_asset
    from .integration.member2 import to_optimization
    from .io.mesh_io import load_mesh
    directory=Path(args.out) if args.out else Path('runs')/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+args.command+'_'+uuid4().hex[:6])
    directory=directory.resolve();directory.mkdir(parents=True,exist_ok=False)
    request={'operation':args.command,'output_dir':str(directory)}
    if args.command in ('evaluate','optimize'):
        reference=to_optimization(load_mesh(args.input));request['input_path']=str(save_asset(reference,directory/'input_reference.npz'))
        request['samples']=args.samples
    if args.command=='evaluate':
        request['candidate_path']=str(save_asset(to_optimization(load_mesh(args.candidate)),directory/'input_candidate.npz'))
    if args.command=='optimize':
        request.update(configs=[dict(operation=args.operation,keep_ratio=args.ratio,iterations=args.iterations,target_edge_length=args.edge)],
                       final_samples=args.final_samples,provider='medical_mesh.integration.member2:diagnose_pair')
        if args.search:request['configs']=[dict(operation='qem',keep_ratio=r,smooth_iterations=n) for r in (.8,.5,.3) for n in (0,5,10)]
        if args.target_faces is not None and not args.search:request['configs'][0]['target_faces']=args.target_faces
        if args.limits:request['limits']=json.loads(Path(args.limits).read_text(encoding='utf-8'))
    if args.command=='convert':
        request.update(input_path=str(Path(args.input).resolve()),target_format=args.target,unit=args.unit,
            cad_config=json.loads(Path(args.config).read_text(encoding='utf-8')) if args.config else {})
        if Path(args.input).suffix.lower()=='.npz':
            request['asset_input_path']=str(save_asset(to_optimization(load_mesh(args.input)),directory/'input_asset.npz'))
    result=dispatch(request)
    print(json.dumps({'status':result['status'],'output_dir':str(directory),'decision':result.get('decision')},ensure_ascii=False))
    return 0 if result['status']=='completed' else 2
