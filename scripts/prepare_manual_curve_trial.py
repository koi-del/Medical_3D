"""Additional paired trial of E-3D's explicit manual hole tool."""
import json
import shutil
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]/'results/e3d_complex'
path=BASE/'cases.json';cases=json.loads(path.read_text(encoding='utf-8'))
if not any(c['case']=='c_hcur' for c in cases):
    original=next(c for c in cases if c['case']=='c_high')
    trial={**original,'case':'c_hcur','variant_of':'c_high','vendor_method':'manual_curvature_trial'}
    cases.append(trial)
    for directory,suffixes in [('inputs',['.stl','.npz']),('references',['.npz']),('project',['.stl','.npz','.json'])]:
        for suffix in suffixes:shutil.copy2(BASE/directory/('c_high'+suffix),BASE/directory/('c_hcur'+suffix))
    path.write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared separate manual trial c_hcur; does not overwrite c_high.')
