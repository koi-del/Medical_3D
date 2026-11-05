"""Signed enclosed volume only for independently verified single closed shells."""
import numpy as np


def enrich_volume(metrics,reference,candidate,diagnosis):
    if diagnosis.get('status')!='passed':return metrics
    details=diagnosis.get('details',{})
    for key in ('diagnosis_before','diagnosis_after'):
        d=details.get(key,{})
        m=d.get('metrics',{})
        if (m.get('component_count')!=1 or m.get('boundary_edge_count')!=0 or not m.get('topology_passed') or
            d.get('self_intersection',{}).get('status')!='verified' or d['self_intersection']['face_ids']):return metrics
    def volume(asset):
        p=asset.vertices[asset.faces]-asset.vertices.mean(axis=0)
        return abs(float(np.einsum('ij,ij->i',p[:,0],np.cross(p[:,1],p[:,2])).sum()/6))
    a,b=volume(reference),volume(candidate)
    if a<=np.finfo(float).eps*reference.scale**3:return metrics
    metrics.update(volume_status='verified_single_closed_shell',volume_reason=None,
        reference_volume=a,candidate_volume=b,volume_change=abs(b-a)/a,
        volume_scope='oriented enclosed geometric volume; no multi-shell solid ownership or clinical claim')
    if reference.unit_status=='confirmed':
        metrics['volumes_mm3']={'reference':a*reference.unit_to_mm**3,'candidate':b*reference.unit_to_mm**3}
    return metrics
