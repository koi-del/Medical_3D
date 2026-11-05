"""Independent same-input audits; preserve missing vendor data as missing."""
import csv,hashlib,importlib.util,json
from pathlib import Path
import numpy as np
from medical_mesh import load_mesh,save_mesh,detect_defects
from medical_mesh.integration.member2 import diagnose_pair
from medical_mesh.member2.core.model import MeshAsset as Asset
from medical_mesh.member2.optimization.filters import process_mesh
from medical_mesh.member2.optimization.search import check_diagnosis
from medical_mesh.member2.evaluation import evaluate_mesh,EvaluationConfig
from medical_mesh.member2.evaluation.verified_volume import enrich_volume
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'results/e3d_optimization'


def numerical(mesh):return Asset(mesh.vertices,mesh.faces)


def main():
    source=BASE/'baseline_filters.py'
    if not source.exists():
        source.write_bytes((ROOT/'medical-mesh-member2/src/medical_mesh/optimization/filters.py').read_bytes())
    spec=importlib.util.spec_from_file_location('member2_original_filters',source);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    rows=[]
    for case in json.loads((BASE/'cases.json').read_text(encoding='utf-8')):
        name=case['case'];path=BASE/'inputs'/(name+'.stl')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=case['input_sha256']:raise RuntimeError('Input hash changed')
        native=load_mesh(path);asset=numerical(native);clean=numerical(load_mesh(BASE/'references'/(name+'.npz')))
        input_clean,_=evaluate_mesh(clean,asset,EvaluationConfig(50000,20261104))
        for engine,processor in [('project_before',old.process_mesh),('project_after',process_mesh),('vendor',None)]:
            record={'case':name,'engine':engine,'status':'missing_vendor_export','input_sha256':case['input_sha256']}
            record['input_clean_reference_d95']=input_clean['d95']
            if processor:
                output=processor(asset,{'operation':case['operation'],**case['parameters']})
                record['algorithm_parameters']=json.dumps(output.parameters,ensure_ascii=False)
                derived=native.derive(vertices=output.vertices,faces=output.faces);target=BASE/engine/(name+'.stl');save_mesh(derived,target)
                output=numerical(load_mesh(target))
            else:
                files=[p for p in (BASE/'vendor_raw').glob('*.stl') if p.stem.replace(' ','').endswith('-'+name)]
                if len(files)>1:raise RuntimeError('Multiple vendor results for '+name)
                if not files:rows.append(record);continue
                target=files[0];output=numerical(load_mesh(target))
            diagnosis=check_diagnosis(diagnose_pair,asset,output)
            metrics,details=evaluate_mesh(asset,output,EvaluationConfig(50000,20261104))
            enrich_volume(metrics,asset,output,diagnosis)
            clean_metrics,_=evaluate_mesh(clean,output,EvaluationConfig(50000,20261104))
            quality=metrics['candidate_quality']
            record.update(status='measured',file=str(target.relative_to(ROOT)),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                faces=len(output.faces),actual_retention=len(output.faces)/len(asset.faces),asd=metrics['asd'],d95=metrics['d95'],
                sampled_max=metrics['sampled_max'],area_change=metrics['area_change'],volume_change=metrics['volume_change'],
                clean_reference_d95=clean_metrics['d95'],structure=diagnosis['status'],quality=json.dumps(quality,ensure_ascii=False))
            payload=dict(summary=record,metrics=metrics,clean_reference_metrics=clean_metrics,diagnosis=diagnosis)
            (BASE/(name+'_'+engine+'_audit.json')).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            if engine=='vendor':np.savez_compressed(BASE/(name+'_vendor_distances.npz'),**details)
            rows.append(record);print(name,engine,record['faces'],record['d95'],record['structure'],flush=True)
    keys=list(dict.fromkeys(key for row in rows for key in row))
    with (BASE/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader();writer.writerows(rows)
    status=dict(measured_vendor=sum(r['engine']=='vendor' and r['status']=='measured' for r in rows),expected_vendor=6,
                scope='same fixed inputs; 50k samples per direction; synthetic clean references for noise only; original coordinate units')
    (BASE/'audit_status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')


if __name__=='__main__':main()
