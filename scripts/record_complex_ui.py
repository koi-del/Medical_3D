"""Keep observed UI counts distinct from file-level audit measurements."""
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/e3d_complex'
observed={'c_e4':(6,4),'c_mnm':(484,960),'c_pin':(7,6),'c_mix':(483,960),
          'c_quad':(92,158),'c_conc':(92,158),'c_high':(77,128),'c_irr':(88,150),
          'c_hcur':(77,128),'c_q2':(104,158),'c_c2':(96,142),'c_h2':(99,148),'c_i2':(96,142)}
measured=set()
if (BASE/'comparison.csv').exists():
    with (BASE/'comparison.csv').open(encoding='utf-8-sig',newline='') as stream:
        measured={r['case'] for r in csv.DictReader(stream) if r['engine']=='vendor' and r['status']=='measured'}
cases=json.loads((BASE/'cases.json').read_text(encoding='utf-8'))
for case in cases:
    name=case['case'];v,f=observed[name]
    case.update(vendor_status='measured' if name in measured else 'ui_tested_awaiting_export',
                vendor_ui_preview_vertices=v,vendor_ui_preview_faces=f,
                vendor_strategy='manual_curvature_preserve_one' if case.get('vendor_method') else
                    ('automatic_preserve_one' if case['category']=='hole' else 'automatic_defaults'))
    subprocess.run([sys.executable,str(ROOT/'scripts/complex_evidence.py'),name],check=True,capture_output=True)
(BASE/'cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
source=BASE/'c_i2_wrong_attempt_1.png'
if source.exists():
    (BASE/'invalid_attempts.json').write_text(json.dumps([dict(case='c_i2',valid=False,
        actual_selected_model='c_h2',reason='Model-list viewport clipped the target row; detected in screenshot, discarded, then repeated after native scrolling and WM_GETTEXT identity verification.',
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        excluded_export_object='自动修复 - c_h2',corrected_identity_record='c_i2_correct_identity_identity.json')],ensure_ascii=False,indent=2),encoding='utf-8')
with Image.open(BASE/'complex_export_all_visible_2.png') as image:
    image.crop((1320,400,1940,790)).save(BASE/'evidence/export_list.png')
status=dict(date='2026-11-03',planned_primary_cases=8,supplementary_trials=5,vendor_ui_trials_completed=len(cases),
            vendor_exports_measured=len(measured),pending_vendor_exports=len(cases)-len(measured),
            state='measured' if len(measured)==len(cases) else 'awaiting_user_manual_fee_confirmation_and_export',
            paid_confirmation='user_only',claims='No final vendor quality claims without actual exported-file audit.')
(BASE/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
print('UI trials:',len(cases),'Measured vendor exports:',len(measured))
