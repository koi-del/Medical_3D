"""Patch shape and seam indicators; these do not measure anatomical accuracy."""
import numpy as np
from ..detection.topology import adjacency


def patch_quality(asset,face_ids):
    ids=sorted(set(face_ids))
    if not ids:return dict(status='not_applicable',face_count=0,warnings=[])
    triangles=asset.vertices[asset.faces[ids]]
    areas=[];angles=[];aspects=[];degenerate=[]
    per_face=[]
    for fid,p in zip(ids,triangles):
        lengths=np.array([np.linalg.norm(p[(i+1)%3]-p[i]) for i in range(3)])
        twice_area=float(np.linalg.norm(np.cross(p[1]-p[0],p[2]-p[0])))
        if twice_area==0 or lengths.min()==0:
            degenerate.append(fid);angle=0.;aspect=None
        else:
            values=[float(np.degrees(np.arctan2(twice_area,np.dot(p[(i+1)%3]-p[i],p[(i+2)%3]-p[i])))) for i in range(3)]
            angle=min(values);aspect=float(lengths.max()**2/twice_area)
            aspects.append(aspect)
        areas.append(twice_area/2);angles.append(angle)
        per_face.append(dict(face_id=fid,minimum_angle_degrees=angle,aspect_ratio=aspect,area=twice_area/2))
    patch=set(ids);seams=[]
    for edge,incidents in adjacency(asset.faces).items():
        if len(incidents)!=2:continue
        a,b=incidents[0][0],incidents[1][0]
        if (a in patch)==(b in patch):continue
        p,q=asset.vertices[asset.faces[a]],asset.vertices[asset.faces[b]]
        u,v=np.cross(p[1]-p[0],p[2]-p[0]),np.cross(q[1]-q[0],q[2]-q[0])
        length=np.linalg.norm(u)*np.linalg.norm(v)
        if length:
            angle=float(np.degrees(np.arctan2(np.linalg.norm(np.cross(u,v)),np.dot(u,v))))
            seams.append(dict(edge=list(edge),angle_degrees=angle))
    warnings=[]
    if degenerate:warnings.append('补片存在零面积面')
    if min(angles)<10:warnings.append('补片存在小于10度的尖角，请检查瘦长三角形')
    if aspects and max(aspects)>10:warnings.append('补片长宽比超过10，请检查三角形质量')
    seam_max=max((s['angle_degrees'] for s in seams),default=None)
    if seam_max is not None and seam_max>60:warnings.append('补片与原表面的最大法线夹角超过60度，请检查接缝')
    return dict(status='measured',face_count=len(ids),minimum_angle_degrees=min(angles),
                maximum_aspect_ratio=max(aspects) if aspects else None,total_area=sum(areas),
                degenerate_face_ids=degenerate,seam_edge_count=len(seams),maximum_seam_angle_degrees=seam_max,
                per_face=per_face,seams=seams,warnings=warnings,
                aspect_definition='longest edge / shortest altitude; equilateral triangle = 2/sqrt(3)',
                scope='Geometric inspection thresholds only; not anatomical reconstruction error')
