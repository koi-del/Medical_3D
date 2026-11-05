"""Staged same-input E-3D tests. Does not confirm charges."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/e3d_complex'
parser=argparse.ArgumentParser()
parser.add_argument('stage',choices=['open','open-manual','run','run-curve','confirm','cancel','export','add','request-export','manual','isolate-manual','close-export','add-visible'])
parser.add_argument('case');parser.add_argument('--row',type=int);parser.add_argument('--rows',nargs='+',type=int)
args=parser.parse_args()
cases={x['case']:x for x in json.loads((BASE/'cases.json').read_text(encoding='utf-8'))}
if args.case not in cases:raise ValueError('Unknown test case')
case=args.case


def step(*options):
    result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/inspect_e3d.py'),
        '--output-root','e3d_complex',*map(str,options)],cwd=ROOT,capture_output=True,encoding='utf-8')
    if result.returncode:raise RuntimeError(result.stderr)
    print('Completed:',' '.join(map(str,options)),flush=True)


if args.stage in ('open','open-manual'):
    if args.row is None:raise ValueError('Model row required')
    step('--click',.047,.042,'--label',case+'_data')
    step('--click',.214,.072,'--label',case+'_dialog')
    step('--file',BASE/'inputs'/(case+'.stl'),'--label',case+'_import')
    step('--click',.88,(366+27*args.row)/1527,'--label',case+'_selected')
    step('--click',.236,.042,'--label',case+'_mesh')
    step('--click',.084 if args.stage=='open-manual' else .049,.072,'--controls','--label',case+'_panel')
elif args.stage=='run':
    step('--verify-name',case,'--label',case+'_identity_check')
    if cases[case]['category']=='hole':step('--edit',4038,1,'--label',case+'_preserve_outer')
    step('--press-id',4323,'--label',case+'_run')
elif args.stage=='run-curve':
    step('--verify-name',case,'--label',case+'_identity_check')
    mode=json.loads((BASE/(case+'_mode_combo.json')).read_text(encoding='utf-8'))
    index=mode['values'].index('曲率填充')
    step('--combo-index',4338,index,'--edit',4038,1,'--label',case+'_curve_parameters')
    step('--press-id',4491,'--label',case+'_run')
elif args.stage=='confirm':step('--press-id',11,'--label',case+'_confirmed')
elif args.stage=='cancel':step('--press-id',12,'--label',case+'_cancelled')
elif args.stage=='manual':step('--click',.084,.072,'--controls','--label',case+'_manual_panel')
elif args.stage=='isolate-manual':
    for row in range(1,16,2):step('--click',.838,(366+27*row)/1527,'--label',f'hide_test_{row}')
elif args.stage=='export':
    step('--click',.047,.042,'--label','export_data')
    step('--click',.276,.072,'--label','complex_export_dialog')
    step('--dialog-title','导出STL模型','--edit',7252,BASE/'vendor_raw','--controls','--label','complex_export_destination')
elif args.stage=='add':
    for row in args.rows or []:
        if not 0<=row<25:raise ValueError('Unreviewed tree row')
        step('--click',.30,(456+36.2*row)/1527,'--label',f'export_pick_{row}')
        step('--dialog-title','导出STL模型','--press-id',7086,'--label',f'export_add_{row}')
elif args.stage=='request-export':
    step('--dialog-title','导出STL模型','--press-id',7090,'--label','complex_fee_gate')
elif args.stage=='close-export':step('--dialog-title','导出STL模型','--press-id',11,'--label','complex_export_paused')
elif args.stage=='add-visible':step('--dialog-title','导出STL模型','--press-id',7091,'--label','complex_export_all_visible')
