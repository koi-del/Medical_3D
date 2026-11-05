"""Bounded local and multi-region proposals; every proposal needs full verification."""
from itertools import combinations,islice
import numpy as np
import time
from ..core.model import TaskResult
from ..detection.topology import detect_defects
from .repair_policy import RepairOptions,repair_mesh


def _region_plans(asset, diagnosis, budget):
    """Beam over edge neighborhoods, without known damaged-face identifiers."""
    edges=diagnosis.defects['non_manifold_edges']
    groups=[]
    for edge in edges:
        faces=set(edge['face_ids'])
        touched=[g for g in groups if g & faces]
        for group in touched:
            faces |= group;groups.remove(group)
        groups.append(faces)
    if not 2<=len(groups)<=8:return []
    from ..detection.topology import adjacency
    edge_map=adjacency(asset.faces)
    face_edges={}
    for key,inc in edge_map.items():
        for fid,_ in inc:face_edges.setdefault(fid,[]).append(key)
    initial_bad=sum(len(inc)>2 for inc in edge_map.values())
    initial_open=sum(len(inc)==1 for inc in edge_map.values())
    def rank(deleted):
        affected={key for fid in deleted for key in face_edges[fid]}
        bad,opened=initial_bad,initial_open
        for key in affected:
            inc=edge_map[key];remaining=sum(fid not in deleted for fid,_ in inc)
            bad+=int(remaining>2)-int(len(inc)>2)
            opened+=int(remaining==1)-int(len(inc)==1)
        return (bad,opened,len(deleted),tuple(sorted(deleted)))
    beam=[frozenset()]
    for group in groups:
        # Local alternatives remove the excess incidences, up to four faces.
        alternatives=(frozenset(pair) for edge in edges if set(edge['face_ids']) <= group and 3<=len(edge['face_ids'])<=6
                      for pair in combinations(sorted(edge['face_ids']),len(edge['face_ids'])-2))
        local=set(islice(alternatives,budget))
        if not local:return []
        beam=sorted({prefix|choice for prefix in beam for choice in local},key=rank)[:budget]
    return [dict(delete_face_ids=sorted(p),split_vertex_ids=[]) for p in beam]


def suggest_non_manifold_repairs(asset,boundary_roles=None,max_candidates=12,progress=None):
    started=time.perf_counter()
    if not 1<=max_candidates<=48:raise ValueError('候选预算必须在1到48之间')
    if progress:progress('定位非流形邻域')
    diagnosis=detect_defects(asset)
    ids=sorted({i for edge in diagnosis.defects['non_manifold_edges'] for i in edge['face_ids']})
    result=TaskResult(status='completed',input_version=asset.version,output_version=asset.version)
    result.metrics=dict(suggestions=[],rejected_candidates=[],examined=0,total_incident_faces=len(ids),truncated=False)
    if len(asset.faces)>50000:
        result.warnings.append('模型超过50000面，暂不执行整模逐候选复检；可继续定位与检测。')
        result.elapsed_seconds=time.perf_counter()-started;return result
    plans=[dict(delete_face_ids=[i],split_vertex_ids=[]) for i in ids[:max_candidates]]
    pair_iter=(pair for edge in diagnosis.defects['non_manifold_edges'] for pair in combinations(sorted(edge['face_ids']),2))
    pairs=list(dict.fromkeys(islice(pair_iter,max_candidates)))
    plans += [dict(delete_face_ids=list(pair),split_vertex_ids=[]) for pair in pairs]
    bad_edge_vertices={v for edge in diagnosis.defects['non_manifold_edges'] for v in edge['edge']}
    plans += [dict(delete_face_ids=[],split_vertex_ids=[v['vertex_id']])
              for v in diagnosis.defects['non_manifold_vertices'] if v['vertex_id'] not in bad_edge_vertices]
    combined=_region_plans(asset,diagnosis,max_candidates)
    split_all=sorted(v['vertex_id'] for v in diagnosis.defects['non_manifold_vertices'] if v['vertex_id'] not in bad_edge_vertices)
    if combined and split_all:
        combined=[{**p,'split_vertex_ids':split_all} for p in combined]
    if not ids and len(split_all)>1:combined=[dict(delete_face_ids=[],split_vertex_ids=split_all)]
    plans=combined+plans
    plans=list({(tuple(p['delete_face_ids']),tuple(p['split_vertex_ids'])):p for p in plans}.values())
    estimated=len(ids)+sum(len(e['face_ids'])*(len(e['face_ids'])-1)//2 for e in diagnosis.defects['non_manifold_edges'])+len(diagnosis.defects['non_manifold_vertices'])
    result.metrics['truncated']=estimated+len(combined)>max_candidates
    result.metrics['multi_region_candidates']=len(combined)
    before_bad=diagnosis.metrics['non_manifold_edge_count']+diagnosis.metrics['non_manifold_vertex_count']
    for index,plan in enumerate(plans[:max_candidates]):
        if progress:progress(f'复检建议 {index+1}/{min(len(plans),max_candidates)}')
        _,check=repair_mesh(asset,RepairOptions(**plan,boundary_roles=boundary_roles or {},check_self_intersection=True))
        result.metrics['examined']+=1;after=check.diagnosis_after.get('metrics',{})
        if (check.accepted and after.get('topology_passed') and
            after['non_manifold_edge_count']+after['non_manifold_vertex_count']<before_bad):
            points=asset.vertices[asset.faces[plan['delete_face_ids']]]
            area=float(np.linalg.norm(np.cross(points[:,1]-points[:,0],points[:,2]-points[:,0]),axis=1).sum()/2) if len(points) else 0.
            affected=sorted({fid for v in diagnosis.defects['non_manifold_vertices']
                             if v['vertex_id'] in plan['split_vertex_ids'] for fid in v['face_ids']})
            result.metrics['suggestions'].append(dict(**plan,input_version=asset.version,
                kind='split_vertex' if plan['split_vertex_ids'] else 'delete_faces',affected_face_ids=affected,removed_area=area,
                boundary_loops_before=diagnosis.metrics['boundary_loop_count'],boundary_loops_after=after['boundary_loop_count'],
                components_before=diagnosis.metrics['component_count'],components_after=after['component_count'],
                self_intersection_status=check.diagnosis_after['self_intersection']['status'],
                explanation=('拆分断开的面扇区，保留原坐标；STL回读可能重新合并重合顶点，建议使用NPZ/项目包。' if plan['split_vertex_ids'] else
                             '删面后拓扑与自交复检通过；需要检查是否符合模型用途。')))
        else:result.metrics['rejected_candidates'].append(dict(**plan,reasons=check.errors or ['处理后仍有拓扑缺陷']))
    result.metrics['suggestions'].sort(key=lambda p:(max(0,p['boundary_loops_after']-p['boundary_loops_before']),len(p['delete_face_ids']),p['removed_area']))
    if not result.metrics['suggestions']:result.warnings.append('受限搜索中未找到通过复检的方案，原模型保留；不是完整搜索。')
    result.elapsed_seconds=time.perf_counter()-started
    return result
