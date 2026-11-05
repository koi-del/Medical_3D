"""Explicit staged vendor trials; charge confirmation remains manual."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/e3d_optimization'
parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['open','run','confirm','inspect','export','add-results','request-export'])
parser.add_argument('case');parser.add_argument('--row',type=int);args=parser.parse_args()
cases={c['case']:c for c in json.loads((BASE/'cases.json').read_text(encoding='utf-8'))}
if args.case not in cases:raise ValueError('Unknown case')
case=cases[args.case]


def step(*options):
    result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/inspect_e3d.py'),
        '--output-root','e3d_optimization',*map(str,options)],cwd=ROOT,capture_output=True,encoding='utf-8')
    if result.returncode:raise RuntimeError(result.stderr or result.stdout)
    print('Step:',*options,flush=True)


if args.stage=='open':
    if args.row is None:raise ValueError('Exact selected row required')
    step('--click',.047,.042,'--label',args.case+'_data')
    step('--click',.214,.072,'--label',args.case+'_dialog')
    step('--file',BASE/'inputs'/(args.case+'.stl'),'--label',args.case+'_import')
    step('--click',.88,(366+27*args.row)/1527,'--label',args.case+'_selected')
    step('--click',.236,.042,'--label',args.case+'_mesh')
    position={'qem':.17,'taubin':.246,'remesh':.219}[case['operation']]
    step('--click',position,.072,'--controls','--label',args.case+'_panel')
elif args.stage=='inspect':step('--controls','--label',args.case+'_inspect')
elif args.stage=='confirm':step('--press-id',11,'--label',args.case+'_confirmed')
elif args.stage=='export':
    step('--click',.047,.042,'--label','export_data')
    step('--click',.276,.072,'--controls','--label','optimization_export_dialog')
    step('--dialog-title','导出STL模型','--edit',7252,BASE/'vendor_raw','--label','optimization_export_destination')
elif args.stage=='request-export':step('--dialog-title','导出STL模型','--press-id',7090,'--label','optimization_fee_gate')
elif args.stage=='add-results':
    for row in (1,3,5,7,9,11):
        step('--click',.30,(456+36.2*row)/1527,'--label','optimization_pick_'+str(row))
        step('--dialog-title','导出STL模型','--press-id',7086,'--label','optimization_add_'+str(row))
elif args.stage=='run' and case['operation']=='qem':
    step('--verify-name',args.case,'--edit',4482,case['parameters']['keep_ratio'],'--check',4463,1,
         '--press-id',4153,'--label',args.case+'_run')
elif args.stage=='run' and case['operation']=='taubin':
    step('--verify-name',args.case,'--edit',4093,5,'--edit',4042,70,'--edit',4381,.1,
         '--check',4098,1,'--press-id',4031,'--label',args.case+'_run')
elif args.stage=='run' and case['operation']=='remesh':
    step('--verify-name',args.case,'--edit',4032,3,'--edit',4042,30,'--edit',4093,3,
         '--check',4098,1,'--press-id',4031,'--label',args.case+'_run')
else:raise ValueError('Run parameters must be inspected explicitly before invoking a new vendor tool')
