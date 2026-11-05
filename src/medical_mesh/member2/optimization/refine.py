"""Bounded tangential relaxation, reprojected onto the original surface."""
import numpy as np
from scipy.sparse import coo_matrix
from ..evaluation import evaluate_mesh,EvaluationConfig
from ..evaluation.metrics import quality,surface_distances


def refine_quality(reference,candidate,steps=3):
    if isinstance(steps,bool) or not isinstance(steps,int) or not 0<=steps<=3:raise ValueError('Quality passes must be 0..3')
    from .filters import boundary_vertices
    boundary,edges=boundary_vertices(candidate);n=len(candidate.vertices)
    rows=np.r_[edges[:,0],edges[:,1]];cols=np.r_[edges[:,1],edges[:,0]]
    graph=coo_matrix((np.ones(len(rows)),(rows,cols)),shape=(n,n)).tocsr();degree=np.asarray(graph.sum(axis=1)).ravel()
    initial=quality(candidate);baseline,_=evaluate_mesh(reference,candidate,EvaluationConfig(2000,20261104))
    best=candidate;accepted=0
    for _ in range(steps):
        points=best.vertices;tri=points[best.faces];normals=np.zeros_like(points)
        face_normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
        for corner in range(3):np.add.at(normals,best.faces[:,corner],face_normals)
        normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],np.finfo(float).tiny)
        delta=graph@points/np.maximum(degree[:,None],1)-points
        delta-=normals*np.einsum('ij,ij->i',delta,normals)[:,None]
        proposed=points+.5*delta
        _,projected,_=surface_distances(proposed,reference,reference.vertices.mean(axis=0));projected[boundary]=candidate.vertices[boundary]
        trial=reference.derive(projected,candidate.faces,'remesh_quality',{})
        if quality(trial)['q_p5']<=quality(best)['q_p5']+1e-8:break
        measured,_=evaluate_mesh(reference,trial,EvaluationConfig(2000,20261104))
        tolerance=reference.scale*1e-7
        if any(measured[key]>baseline[key]*1.05+tolerance for key in ('d95','sampled_max')):break
        best=trial;accepted+=1
    final=quality(best)
    return best.vertices,best.faces,dict(method='tangential_relaxation_projected_to_reference',requested_passes=steps,
        accepted_passes=accepted,quality_p5_before=initial['q_p5'],quality_p5_after=final['q_p5'],
        guard='2000 deterministic samples: D95 and sampled max <= 1.05*base + 1e-7*bbox; full independent final verification remains required')
