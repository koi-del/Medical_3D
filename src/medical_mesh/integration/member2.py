from dataclasses import replace
import numpy as np
import pyvista as pv
from vtkmodules.vtkCommonCore import reference as vtk_ref
from vtkmodules.vtkCommonDataModel import vtkStaticCellLocator
from ..core.model import MeshAsset
from ..detection.topology import detect_defects
from ..member2.core.model import MeshAsset as OptimizationAsset


def to_optimization(asset,roles=None):
    known=asset.unit_status=='confirmed'
    return OptimizationAsset(asset.vertices,asset.faces,asset_id=asset.asset_id,version_id=asset.version,
        parent_version=asset.parent_version,unit_status=asset.unit_status,
        unit_name=asset.source_unit if known else None,unit_to_mm=asset.unit_to_mm if known else None,
        source_path=asset.source_file,source_sha256=asset.source_sha256,
        metadata={'member1_metadata':asset.metadata(),'boundary_roles':roles or {},'protected_rois':[],
                  'lifecycle':'accepted_reference'})


def from_optimization(candidate,reference=None):
    if reference is not None:
        expected=to_optimization(reference)
        if (candidate.asset_id!=reference.asset_id or candidate.parent_version!=reference.version or
            (candidate.unit_status,candidate.unit_name,candidate.unit_to_mm)!=(expected.unit_status,expected.unit_name,expected.unit_to_mm)):
            raise ValueError('优化候选的来源版本、模型标识或单位与正式参考不一致')
        return replace(reference,vertices=candidate.vertices,faces=candidate.faces,version=candidate.version_id,
            parent_version=reference.version,processing_parameters={**reference.processing_parameters,
                'member2_operation':candidate.operation,'member2_parameters':candidate.parameters})
    metadata=candidate.metadata.get('member1_metadata')
    if metadata:
        metadata={**metadata,'version':candidate.version_id,'parent_version':candidate.parent_version}
        return MeshAsset(candidate.vertices,candidate.faces,**metadata)
    return MeshAsset(candidate.vertices,candidate.faces,asset_id=candidate.asset_id,version=candidate.version_id,
        parent_version=candidate.parent_version,source_unit=candidate.unit_name,unit_status=candidate.unit_status,
        unit_to_mm=candidate.unit_to_mm,source_file=candidate.source_path or '',source_sha256=candidate.source_sha256 or '')


def _polydata(asset):
    return pv.PolyData(asset.vertices.copy(),np.column_stack((np.full(len(asset.faces),3),asset.faces)).ravel())


def _components_correspond(a,b,da,db):
    if len(da.components)!=len(db.components):return False
    if len(da.components)==1:return True
    def mapping(source,target,source_groups,target_groups):
        locator=vtkStaticCellLocator();locator.SetDataSet(_polydata(target));locator.BuildLocator()
        labels=np.empty(len(target.faces),dtype=int)
        for index,ids in enumerate(target_groups):labels[ids]=index
        mapped=[];closest=[0.,0.,0.];cell=vtk_ref(0);sub=vtk_ref(0);distance=vtk_ref(0.)
        for group in source_groups:
            seen=set()
            for point in source.vertices[source.faces[group]].mean(axis=1):
                locator.FindClosestPoint(point,closest,cell,sub,distance);seen.add(int(labels[int(cell)]))
            if len(seen)!=1:return None
            mapped.append(next(iter(seen)))
        return mapped
    forward=mapping(a,b,da.components,db.components);backward=mapping(b,a,db.components,da.components)
    return (forward is not None and backward is not None and len(set(forward))==len(forward)
            and all(backward[j]==i for i,j in enumerate(forward)))


def _boundaries_correspond(a,b,da,db):
    if len(da.boundaries)!=len(db.boundaries):return False
    tolerance=max(np.linalg.norm(np.ptp(a.vertices,axis=0))*1e-9,1e-12)
    def near(source,source_boundary,target,target_boundary):
        edges=np.asarray(target_boundary['edges']);lines=pv.PolyData()
        lines.points=target.vertices.copy();lines.lines=np.column_stack((np.full(len(edges),2),edges)).ravel()
        locator=vtkStaticCellLocator();locator.SetDataSet(lines);locator.BuildLocator()
        samples=source.vertices[np.unique(np.asarray(source_boundary['edges']))]
        mids=source.vertices[np.asarray(source_boundary['edges'])].mean(axis=1)
        closest=[0.,0.,0.];cell=vtk_ref(0);sub=vtk_ref(0);distance=vtk_ref(0.)
        for point in np.vstack((samples,mids)):
            locator.FindClosestPoint(point,closest,cell,sub,distance)
            if float(distance)>tolerance*tolerance:return False
        return True
    remaining=list(db.boundaries)
    for boundary in da.boundaries:
        for index,other in enumerate(remaining):
            if boundary['kind']==other['kind'] and near(a,boundary,b,other) and near(b,other,a,boundary):
                remaining.pop(index);break
        else:return False
    return True


def diagnose_pair(reference,candidate):
    a=from_optimization(reference);b=from_optimization(candidate)
    da=detect_defects(a,check_self_intersection=True);db=detect_defects(b,check_self_intersection=True)
    checks={}
    checks['reference_eligible']='passed' if (da.metrics['topology_passed'] and da.self_intersection['status']=='verified' and not da.self_intersection['face_ids']) else 'failed'
    for name,key in [('duplicate_faces','duplicate_face_count'),('degenerate_faces','degenerate_face_count'),
            ('nonmanifold_edges','non_manifold_edge_count'),('nonmanifold_vertices','non_manifold_vertex_count'),('orientation','orientation_conflict_count')]:
        checks[name]='passed' if db.metrics[key]==0 else 'failed'
    checks['self_intersection']=('unverified' if db.self_intersection['status']!='verified' else
        'failed' if db.self_intersection['face_ids'] else 'passed')
    if da.metrics['topology_passed'] and db.metrics['topology_passed']:
        checks['component_correspondence']='passed' if _components_correspond(a,b,da,db) else 'failed'
        checks['boundary_correspondence']='passed' if _boundaries_correspond(a,b,da,db) else 'failed'
    else:checks.update(component_correspondence='failed',boundary_correspondence='failed')
    checks['protected_rois']='unverified' if reference.metadata.get('protected_rois') else 'not_applicable'
    return dict(scope='production',reference_version=reference.version_id,input_version=candidate.version_id,
        geometry_sha256=candidate.geometry_hash,checks=checks,diagnosis_before=da.to_dict(),diagnosis_after=db.to_dict(),
        limitations=['结构对应使用逐面中心最近表面归属及双向边界顶点/中点距离；不代表语义或医学资格验证'])
