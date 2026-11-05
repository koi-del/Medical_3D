"""Reproducible public MRI-derived patella experiment. Run from work/.

Outputs keep optimization error, conversion-only error, and end-to-end error separate.
No full diagnostic service is injected, no candidate is promoted to a formal model.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import html
import json
import shutil
import sys
import time
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
from medical_mesh.core.model import MeshAsset, save_asset, load_asset, write_json, file_hash
from medical_mesh.evaluation import EvaluationConfig, evaluate_mesh
from medical_mesh.evaluation.metrics import quality
from medical_mesh.optimization.filters import process_mesh
from medical_mesh.optimization.search import Limits, geometry_reasons
from medical_mesh.cad.runner import effective_config, convert_file, run_worker
from medical_mesh.jobs.worker import environment_report
from medical_mesh.reporting import render_report

SOURCE_URL = 'https://www.openanatomy.org/atlases/nac/knee-2016-09.zip'
PAGE_URL = 'https://www.openanatomy.org/atlas-pages/atlas-spl-knee.html'
LICENSE_URL = 'https://raw.githubusercontent.com/Slicer/Slicer/main/License.txt'
COORD_URL = 'https://www.slicer.org/wiki/Slicer3:Coordinates'
MODEL_NAME = 'Data/Model_98_patella.vtk'
SEED = 20261022
ARCHIVE_SHA256 = '2f61002f42843910eada3877adf4229ef845bf87cc1e422b719c930dfadc5f6a'
MODEL_SHA256 = '592fdfbb7dda4b1a9fe89a5c2d3cc1b5eacfed12490eceda92c3d1d0958ede76'
ATTRIBUTION = ('SPL Knee Atlas, Jen Richolt, Marianna Jakab, Ron Kikinis, Surgical Planning Laboratory, '
               'Brigham and Women’s Hospital, Harvard Medical School. '
               'All or portions of this licensed product (such portions are the "Software") have been '
               'obtained under license from The Brigham and Women\'s Hospital, Inc. and are subject to '
               'the terms and conditions of the 3D Slicer License. Modified: extracted patella surface, '
               'triangulated, optimized, and converted to STL/STEP/IGS for a course experiment.')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def download(url, path):
    path = Path(path)
    if not path.is_file():
        with urllib.request.urlopen(url, timeout=120) as src, path.with_suffix(path.suffix+'.partial').open('wb') as dst:
            shutil.copyfileobj(src, dst)
        path.with_suffix(path.suffix+'.partial').rename(path)


def topology(asset):
    """Measured basic topology only; not a full diagnosis or self-intersection check."""
    import trimesh
    faces = asset.faces
    edges = np.sort(np.vstack((faces[:,[0,1]], faces[:,[1,2]], faces[:,[2,0]])), axis=1)
    unique, inverse, count = np.unique(edges, axis=0, return_inverse=True, return_counts=True)
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    incidence=coo_matrix((np.ones(len(inverse)), (np.tile(np.arange(len(faces)),3), inverse)),
                         shape=(len(faces),len(unique))).tocsr()
    component_count=connected_components(incidence@incidence.T,directed=False,return_labels=False)
    canonical = np.sort(faces, axis=1)
    mesh = trimesh.Trimesh(asset.vertices, faces, process=False)
    return {'vertices':len(asset.vertices), 'used_vertices':int(len(np.unique(faces))), 'faces':len(faces),
            'edges':len(unique), 'boundary_edges':int(np.sum(count==1)), 'nonmanifold_edges':int(np.sum(count>2)),
            'duplicate_faces':int(len(faces)-len(np.unique(canonical, axis=0))),
            'watertight_edge_test':bool(mesh.is_watertight), 'consistent_winding_test':bool(mesh.is_winding_consistent),
            'connected_surface_components':int(component_count),
            'euler_characteristic_used_vertices':int(len(np.unique(faces))-len(unique)+len(faces)),
            'bbox_mm':[asset.vertices.min(axis=0).tolist(),asset.vertices.max(axis=0).tolist()],
            'extent_mm':np.ptp(asset.vertices,axis=0).tolist(), 'self_intersection':'not_checked',
            'roi_protection':'not_checked', 'solid_qualification':'not_checked', 'quality':quality(asset)}


def prepare(out, source):
    source.mkdir(parents=True,exist_ok=True)
    archive=source/'knee-2016-09.zip'
    download(SOURCE_URL,archive)
    if file_hash(archive) != ARCHIVE_SHA256:
        raise ValueError('公开图谱ZIP校验失败，请保留异常缓存并重新获取官方数据')
    names=['LICENSE.md','atlasStructure.json','KneeAtlas-2015Sept-Slicer4-4Version.mrml',MODEL_NAME]
    with zipfile.ZipFile(archive) as z:
        for name in names:
            dest=source/name; dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(z.read('knee-2016-09/'+name))
        (source/'MRI_header.txt').write_bytes(z.read('knee-2016-09/Data/I.nrrd').split(b'\n\n',1)[0])
    if file_hash(source/MODEL_NAME) != MODEL_SHA256:
        raise ValueError('髌骨原始VTK与已核实公开模型不匹配')
    download(PAGE_URL,source/'source_page.html')
    download(LICENSE_URL,source/'3D-Slicer-License.txt')
    scene=ET.parse(source/'KneeAtlas-2015Sept-Slicer4-4Version.mrml').getroot()
    node=next(n for n in scene if n.tag=='Model' and n.get('name')=='Model_98_patella')
    storage=next(n for n in scene if n.get('id')==node.get('storageNodeRef'))
    if node.get('transformNodeRef'):
        raise ValueError('Unresolved model transform; do not discard scene placement')
    from vtkmodules.vtkIOLegacy import vtkPolyDataReader
    from vtkmodules.vtkFiltersCore import vtkTriangleFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    reader=vtkPolyDataReader();reader.SetFileName(str(source/MODEL_NAME));reader.Update()
    raw=reader.GetOutput()
    triangles=vtkTriangleFilter();triangles.SetInputData(raw);triangles.PassLinesOff();triangles.PassVertsOff();triangles.Update()
    mesh=triangles.GetOutput()
    offsets=vtk_to_numpy(mesh.GetPolys().GetOffsetsArray())
    if not np.all(np.diff(offsets)==3):
        raise ValueError('Non-triangular cells remain')
    faces=vtk_to_numpy(mesh.GetPolys().GetConnectivityArray()).reshape(-1,3).astype(np.int64)
    vertices=vtk_to_numpy(mesh.GetPoints().GetData()).astype(np.float64)
    raw_asset=MeshAsset(vertices, faces, unit_status='confirmed', unit_name='mm', unit_to_mm=1.)
    save_asset(raw_asset,out/'raw_triangulated_reference.npz')
    unique,inverse=np.unique(vertices,axis=0,return_inverse=True)
    normalized_faces=inverse[faces]
    exact_equivalence=bool(np.array_equal(vertices[faces],unique[normalized_faces]))
    if not exact_equivalence:
        raise ValueError('Index canonicalization changed triangle coordinates')
    asset=MeshAsset(unique, normalized_faces, unit_status='confirmed', unit_name='mm', unit_to_mm=1.,
                    source_path=str((source/MODEL_NAME).resolve()), source_sha256=file_hash(source/MODEL_NAME),
                    metadata={'source':'SPL Knee Atlas','structure':'patella','source_kind':'real_MRI_derived_atlas_surface',
                              'coordinate_system':'legacy_Slicer_scene_RAS_convention',
                              'coordinate_evidence':COORD_URL,'unit_evidence':'Slicer legacy model physical-coordinate convention; no independent calibration',
                              'quality_status':'unverified','member1_diagnosis_pending':True})
    save_asset(asset,out/'reference.npz')
    import trimesh
    trimesh.Trimesh(asset.vertices,asset.faces,process=False).export(str(out/'reference.stl'))
    provenance={'retrieved_date':'2026-10-22','source_url':SOURCE_URL,'description_url':PAGE_URL,
                'authors':['Jen Richolt','Marianna Jakab','Ron Kikinis'],'institution':'SPL / Brigham and Women’s Hospital / Harvard Medical School',
                'source_release_page':'September 2015; downloaded archive named knee-2016-09.zip; archive internal timestamps are not acquisition dates',
                'license':'3D Slicer License section B (archive LICENSE links to full Slicer license)',
                'attribution':ATTRIBUTION, 'original_subject_age':None,'anatomical_side':'not_asserted',
                'acquisition_date':None, 'model_entry':MODEL_NAME,'archive_sha256':file_hash(archive),
                'source_vtk_sha256':file_hash(source/MODEL_NAME),'license_sha256':file_hash(source/'3D-Slicer-License.txt'),
                'scene_sha256':file_hash(source/'KneeAtlas-2015Sept-Slicer4-4Version.mrml'),
                'raw_vtk_points':raw.GetNumberOfPoints(),'raw_vtk_cells':raw.GetNumberOfCells(),
                'raw_triangle_strips':raw.GetNumberOfStrips(),'triangle_faces':len(asset.faces),
                'preprocessing':['VTK triangle strips expanded to explicit triangles','exact-equal coordinate vertex index canonicalization'],
                'exact_duplicate_vertices_reindexed':len(vertices)-len(unique),
                'triangle_coordinates_bitwise_equal_after_reindex':exact_equivalence,
                'nearby_vertex_welding_smoothing_centering_scaling_or_registration':False,
                'scene_model':dict(node.attrib),'scene_storage':dict(storage.attrib),
                'coordinate_note':'Numeric positions preserved from source; legacy RAS inferred from 2015 scene and official convention, not DICOM orientation verification.',
                'reference_version':asset.version_id,'reference_geometry_sha256':asset.geometry_hash,
                'raw_index_topology':topology(raw_asset), 'source_topology':topology(asset)}
    write_json(out/'provenance.json',provenance)
    (out/'ATTRIBUTION.txt').write_text(ATTRIBUTION+'\n',encoding='utf-8')
    shutil.copy2(source/'3D-Slicer-License.txt',out/'3D-Slicer-License.txt')
    shutil.copy2(source/'LICENSE.md',out/'atlas_LICENSE.md')
    return asset


def run_optimization(out, progress=lambda *_:None, keep_all_samples=True):
    reference=load_asset(out/'reference.npz')
    n=len(reference.faces)
    configs=[{'label':'identity','operation':'qem','keep_ratio':1.}]
    configs += [{'label':f'qem_{target}','operation':'qem','keep_ratio':target/n} for target in (6000,3000,2400,1800,1200,800)]
    configs += [{'label':'laplacian_5','operation':'laplacian','iterations':5},
                {'label':'taubin_5','operation':'taubin','iterations':5},
                {'label':'qem_2400_taubin_3','operation':'qem','keep_ratio':2400/n,'smooth_iterations':3}]
    limits=Limits()
    plan={'screening_samples':10000,'screening_seed':SEED,'final_samples':50000,'final_seed':SEED+10000,
          'limits':{'d95_normalized':limits.d95_normalized,'sampled_max_normalized':limits.sampled_max_normalized,'area_change':limits.area_change},
          'cad_face_budget':3000,'configs':configs,
          'stability_audit_seeds':[SEED+40000,SEED+50000,SEED+60000],
          'stability_audit_samples_each_direction':50000,
          'selection_rule':'among independent-final-pass candidates with <=3000 faces and basic topology preserved, ascending face count then D95; require all three additional independent seed checks at unchanged geometry limits; no full diagnosis acceptance'}
    write_json(out/'optimization_plan.json',plan)
    rows=[];preview_details={}
    for index,config in enumerate(configs):
        name=config['label']; directory=out/'optimization'/name;directory.mkdir(parents=True,exist_ok=False)
        print('OPTIMIZE',name,flush=True); begin=time.perf_counter()
        progress('optimization',f'优化对照 {index+1}/{len(configs)}：{name}',{'label':name,'index':index,'total':len(configs)})
        try:
            # Identity baseline uses unchanged coordinates, not an optimizer round-trip.
            candidate=reference.derive(reference.vertices,reference.faces,'identity',{}) if name=='identity' else process_mesh(reference,{k:v for k,v in config.items() if k!='label'})
            seconds=time.perf_counter()-begin
            save_asset(candidate,directory/'candidate.npz')
            screening,_=evaluate_mesh(reference,candidate,EvaluationConfig(10000,SEED))
            final,details=evaluate_mesh(reference,candidate,EvaluationConfig(50000,SEED+10000))
            if keep_all_samples:
                np.savez_compressed(directory/'final_samples.npz',**details)
            basic=topology(candidate); source=read(out/'provenance.json')['source_topology']
            basic_preserved=(basic['boundary_edges']==source['boundary_edges'] and basic['nonmanifold_edges']==source['nonmanifold_edges']==0
                             and basic['duplicate_faces']==source['duplicate_faces']==0 and basic['connected_surface_components']==source['connected_surface_components']
                             and basic['euler_characteristic_used_vertices']==source['euler_characteristic_used_vertices']
                             and basic['consistent_winding_test'] and basic['quality']['zero_area_faces']==0)
            reasons=geometry_reasons(final,limits)
            if not keep_all_samples and not reasons and basic_preserved and len(candidate.faces)<=3000:
                preview_details[name]=details
            row={'label':name,'parameters':config,'processing_seconds':seconds,'actual_faces':len(candidate.faces),
                 'reduction_ratio':1-len(candidate.faces)/n,'screening':screening,'final_metrics':final,
                 'basic_topology':basic,'basic_topology_preserved':basic_preserved,
                 'geometry_screen_pass':not geometry_reasons(screening,limits), 'geometry_final_pass':not reasons,
                 'reason_codes':reasons,'within_cad_budget':len(candidate.faces)<=3000,
                 'candidate_path':str((directory/'candidate.npz').resolve()),'status':'completed',
                 'decision':'needs_review' if not reasons and basic_preserved else 'rejected','quality_status':'unverified','full_member1_diagnosis':'unavailable'}
            write_json(directory/'result.json',row); rows.append(row)
            print(' ',len(candidate.faces),'D95',final['d95'],'MAX',final['sampled_max'],'PASS',not reasons,flush=True)
        except Exception as error:
            row={'label':name,'status':'failed','errors':[str(error)]};rows.append(row);write_json(directory/'result.json',row)
            print(' FAILED',error,flush=True)
        progress('optimization_candidate',f'{name}计算完成',{'label':name,'index':index,'row':row})
    eligible=[r for r in rows if r.get('geometry_final_pass') and r.get('within_cad_budget') and r.get('basic_topology_preserved')]
    if not eligible:
        write_json(out/'optimization_summary.json',{'rows':rows,'selected':None,'status':'no_eligible_candidate'})
        raise RuntimeError('No candidate passed frozen geometry and CAD budget; preserve failed results, do not weaken thresholds')
    best=None
    for item in sorted(eligible,key=lambda r:(r['actual_faces'],r['final_metrics']['d95'])):
        print('STABILITY',item['label'],flush=True)
        candidate=load_asset(item['candidate_path']);audits=[]
        for seed in plan['stability_audit_seeds']:
            progress('stability',f"{item['label']}独立种子复核：{seed}",{'label':item['label'],'seed':seed})
            metrics,details=evaluate_mesh(reference,candidate,EvaluationConfig(50000,seed))
            if keep_all_samples:
                np.savez_compressed(out/'optimization'/item['label']/f'stability_{seed}.npz',**details)
            audits.append({'seed':seed,'metrics':metrics,'reason_codes':geometry_reasons(metrics,limits)})
        item['stability_checks']=audits
        item['stability_passed']=all(not a['reason_codes'] for a in audits)
        if not item['stability_passed']:
            item['decision']='rejected'
        write_json(out/'optimization'/item['label']/'result.json',item)
        print(' ',item['stability_passed'],[a['metrics']['sampled_max'] for a in audits],flush=True)
        progress('optimization_candidate',f"{item['label']}追加复核{'通过' if item['stability_passed'] else '未通过'}",{'label':item['label'],'row':item})
        if item['stability_passed']:
            best=item;break
    if best is None:
        write_json(out/'optimization_summary.json',{'rows':rows,'selected':None,'status':'no_stable_candidate'})
        raise RuntimeError('No candidate passed additional seed audit at unchanged limits')
    chosen=load_asset(best['candidate_path']);save_asset(chosen,out/'selected_candidate.npz')
    if not keep_all_samples:
        np.savez_compressed(out/'optimization'/best['label']/'final_samples.npz',**preview_details[best['label']])
    import trimesh
    trimesh.Trimesh(chosen.vertices,chosen.faces,process=False).export(str(out/'selected_candidate.stl'))
    summary={'rows':rows,'selected':best['label'],'selected_path':str((out/'selected_candidate.npz').resolve()),
             'selection_status':'research_preview_only','reference_version_unchanged':load_asset(out/'reference.npz').version_id==reference.version_id,
             'reference_hash_unchanged':load_asset(out/'reference.npz').geometry_hash==reference.geometry_hash}
    write_json(out/'optimization_summary.json',summary)
    write_csv(out/'optimization_matrix.csv',[{'label':r['label'],'status':r['status'],'faces':r.get('actual_faces'),
        'reduction_ratio':r.get('reduction_ratio'),'asd_mm':r.get('final_metrics',{}).get('asd'),'d95_mm':r.get('final_metrics',{}).get('d95'),
        'sampled_max_mm':r.get('final_metrics',{}).get('sampled_max'),'area_change':r.get('final_metrics',{}).get('area_change'),
        'geometry_final_pass':r.get('geometry_final_pass'),'within_cad_budget':r.get('within_cad_budget'),
        'stability_passed':r.get('stability_passed'),
        'seconds':r.get('processing_seconds')} for r in rows])
    print('SELECTED',best['label'],flush=True)
    return summary


def write_csv(path,rows):
    with Path(path).open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def robustness(out):
    reference=load_asset(out/'reference.npz');selected=load_asset(out/'selected_candidate.npz')
    optimization=read(out/'optimization_summary.json')
    item=next(r for r in optimization['rows'] if r['label']==optimization['selected'])
    values=[{'seed':a['seed'],'asd_mm':a['metrics']['asd'],'d95_mm':a['metrics']['d95'],
             'sampled_max_mm':a['metrics']['sampled_max'],'geometry_pass':not a['reason_codes']}
            for a in item['stability_checks']]
    config=read(out/'frozen_cad_config.json');negatives=[]
    for name,vertices in [('translate_x_1mm',selected.vertices+np.array([1.,0.,0.])),('wrong_scale_10x',selected.vertices*10)]:
        distorted=selected.derive(vertices,selected.faces,name,{})
        metrics,_=evaluate_mesh(selected,distorted,EvaluationConfig(10000,SEED+70000))
        bbox=float(np.max(np.abs(np.array(topology(selected)['bbox_mm'])-np.array(topology(distorted)['bbox_mm']))))
        negatives.append({'case':name,'d95_mm':metrics['d95'],'sampled_max_mm':metrics['sampled_max'],'bbox_delta_mm':bbox,
                          'correctly_rejected':bbox>config['coordinate_tolerance_mm'] and metrics['d95']>config['d95_mm']})
    negative_dir=out/'negative/unknown_stl_unit'
    result=convert_file(out/'selected_candidate.stl','step',config,negative_dir,unit=None)
    render_report(result,negative_dir)
    negatives.append({'case':'unknown_stl_unit','status':result['status'],'correctly_rejected':result['status']=='failed','errors':result.get('errors')})
    result={'sampling_repeats':values,'negative_controls':negatives,
            'sampling_note':'3 seed repeats are empirical repeatability checks, not a statistical confidence interval or exact maximum bound'}
    write_json(out/'robustness.json',result)
    return result


def run_conversions(out, progress=lambda *_:None, run_controls=True, keep_all_samples=True):
    config=read(out/'frozen_cad_config.json')
    runtime=run_worker(config,{'mode':'probe'},out,'runtime')
    write_json(out/'runtime.json',runtime)
    original=load_asset(out/'reference.npz'); selected=load_asset(out/'selected_candidate.npz')
    paths={'stl':out/'selected_candidate.stl'}
    results=[]
    for src,target in [('stl','step'),('stl','igs'),('step','stl'),('step','igs'),('igs','stl'),('igs','step')]:
        name=f'{src}_to_{target}';directory=out/'conversion'/name
        progress('conversion',f'{src.upper()} → {target.upper()} 开始',{'direction':name,'index':len(results),'status':'running'})
        print('CONVERT',name,flush=True)
        if (directory/'result.json').exists():
            result=read(directory/'result.json')
            if result.get('config')!=config:
                raise ValueError('Refusing reuse with changed configuration')
        else:
            result=convert_file(paths[src],target,config,directory,'mm' if src=='stl' else None,
                                lambda stage,message: progress('conversion',message,{'direction':name,'stage':stage,'status':'running'}))
            result['run_id']=directory.name
            result['source_chain']=['selected_candidate.stl'] if src=='stl' else ['selected_candidate.stl',f'stl_to_{src}/converted.{src}']
            result['note']='CAD inputs are faceted derivatives of this selected medical mesh, not native parametric CAD.'
            previews=result.get('preview_assets')
            if previews:
                readback=load_asset(previews['candidate'])
                for label,ref in [('end_to_end_original',original),('chain_vs_selected',selected)]:
                    progress('conversion',f'{name}：端到端误差评价',{'direction':name,'stage':label,'status':'running'})
                    metrics,details=evaluate_mesh(ref,readback,EvaluationConfig(50000,SEED+20000))
                    if keep_all_samples:
                        np.savez_compressed(directory/(label+'_samples.npz'),**details)
                    result[label]=metrics
            render_report(result,directory)
        if src=='stl' and result.get('output_path'):
            paths[target]=Path(result['output_path'])
        results.append({'direction':name,'status':result['status'],'geometry_status':result.get('geometry_status'),
                        'actual_representation':result.get('actual_representation'),
                        'asd_mm':result.get('metrics',{}).get('asd'),'d95_mm':result.get('metrics',{}).get('d95'),
                        'sampled_max_mm':result.get('metrics',{}).get('sampled_max'),
                        'bbox_delta_mm':result.get('bbox_max_delta_mm'),'convergence_delta_mm':result.get('convergence_delta_mm'),
                        'end_to_end_d95_mm':result.get('end_to_end_original',{}).get('d95'),
                        'end_to_end_max_mm':result.get('end_to_end_original',{}).get('sampled_max'),
                        'chain_vs_selected_d95_mm':result.get('chain_vs_selected',{}).get('d95'),
                        'elapsed_seconds':result['elapsed_seconds'],
                        'output_bytes':Path(result['output_path']).stat().st_size if result.get('output_path') else None,
                        'report':str(directory/'report.html'),'errors':result.get('errors',result.get('reason_codes',[]))})
        print(' ',result['status'],result.get('geometry_status'),results[-1]['errors'],flush=True)
        progress('conversion_done',f'{name}：{result.get("geometry_status",result["status"])}',{'direction':name,'row':results[-1]})
    summary={'cases':results,'passed':sum(r['status']=='completed' and r['geometry_status']=='passed' for r in results),
             'total':len(results),'samples_each_direction':config['samples'], 'all_inputs_are_mesh_derived':True}
    write_json(out/'conversion_summary.json',summary);write_csv(out/'conversion_matrix.csv',results)
    if run_controls and not (out/'robustness.json').exists():robustness(out)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',default='runs/medical_patella_20261022')
    parser.add_argument('--source',default='data/public/spl_knee/source')
    parser.add_argument('--phase',choices=['prepare','optimize','convert','report','all'],default='all')
    args=parser.parse_args();out=Path(args.out).resolve();source=Path(args.source).resolve()
    if args.phase in ('prepare','all'):
        if out.exists() and (args.phase=='all' or (out/'provenance.json').exists()):
            parser.error('New experiment needs a fresh output directory. Use a specific phase to resume.')
        out.mkdir(parents=True,exist_ok=True)
        config=effective_config({'samples':50000,'seed':SEED+30000,'write_error_figure':True})
        write_json(out/'frozen_cad_config.json',config)
        write_json(out/'environment.json',environment_report())
        write_json(out/'experiment.json',{'date':'2026-10-22','structure':'patella','source_url':SOURCE_URL,
            'requested_phases':['source_provenance','optimization','six_conversions','roundtrip_and_end_to_end_errors','report'],
            'started_local':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),'script_sha256':file_hash(__file__)})
        prepare(out,source)
    if args.phase in ('optimize','all'):run_optimization(out)
    if args.phase in ('convert','all'):run_conversions(out)
    if args.phase in ('report','all'):
        from .patella_report import generate_report
        generate_report(out,ROOT)
    print('OUTPUT',out,flush=True)


if __name__=='__main__':
    main()
