"""Conservative local quadric fit for small convex holes; never a general hole solver."""
import numpy as np
from ..detection.topology import adjacency


def quadric_cap(vertices, faces, ordered, options):
    if not 6 <= len(ordered) <= options.max_hole_edges:
        raise ValueError('曲面补洞仅支持至少6条边的简单凸孔')
    points = vertices[ordered]
    center = points.mean(axis=0)
    span = float(np.linalg.norm(np.ptp(points, axis=0)))
    if span <= 0 or span > options.max_hole_span:
        raise ValueError('曲面补洞超过跨度限制')
    _, _, axes = np.linalg.svd(points-center, full_matrices=False)
    local = (points-center) @ axes.T / span
    xy = local[:, :2]
    cross = lambda a,b: float(a[0]*b[1]-a[1]*b[0])
    turns = [cross(xy[(i+1)%len(xy)]-xy[i],xy[(i+2)%len(xy)]-xy[(i+1)%len(xy)])
             for i in range(len(xy))]
    if not (all(x > 1e-10 for x in turns) or all(x < -1e-10 for x in turns)):
        raise ValueError('曲面补洞暂仅支持严格凸的投影边界')
    # The projected centroid must lie strictly inside every oriented edge.
    # This also excludes self-crossing star polygons with uniform turn signs.
    sides = [cross(xy[(i+1)%len(xy)]-xy[i],-xy[i]) for i in range(len(xy))]
    if not (all(x > 1e-10 for x in sides) or all(x < -1e-10 for x in sides)):
        raise ValueError('曲面补洞投影边界无有效内部中心')
    n = len(xy)
    for i in range(n):
        for j in range(i+1,n):
            if j in (i,(i+1)%n) or i == (j+1)%n:continue
            a,b,c,d=xy[i],xy[(i+1)%n],xy[j],xy[(j+1)%n]
            if cross(b-a,c-a)*cross(b-a,d-a) < 0 and cross(d-c,a-c)*cross(d-c,b-c) < 0:
                raise ValueError('曲面补洞投影边界自交')
    # One-ring surface context supplies curvature; boundary points alone cannot
    # determine a circular hole's center height.
    incident = faces[np.any(np.isin(faces, ordered), axis=1)]
    context_ids = np.unique(incident)
    context = (vertices[context_ids]-center) @ axes.T / span
    context = context[np.linalg.norm(context[:, :2],axis=1) <= 1.5]
    if len(context) < 9:
        raise ValueError('曲面补洞缺少足够的邻域采样点')
    x,y,z=context.T
    design=np.column_stack((x*x,x*y,y*y,x,y,np.ones(len(x))))
    coefficients,_,rank,singular=np.linalg.lstsq(design,z,rcond=None)
    if rank < 6 or singular[0]/singular[-1] > 1e6:
        raise ValueError('局部曲面拟合不稳定，保留原模型')
    residual=design@coefficients-z
    if np.max(np.abs(residual)) > .03:
        raise ValueError('局部曲面拟合偏差超过孔洞跨度的3%')
    height=float(coefficients[-1])
    if abs(height) > .5:
        raise ValueError('拟合中心偏离过大，保留原模型')
    new_point=center+axes[2]*height*span
    edge_map=adjacency(faces)
    a,b=ordered[:2];inc=edge_map.get((min(a,b),max(a,b)),[])
    if len(inc)!=1:raise ValueError('边界已变化，请重新检测')
    ordered=list(ordered)
    if inc[0][1] == (1 if a < b else -1):ordered.reverse()
    new_id=len(vertices)
    triangles=[[a,b,new_id] for a,b in zip(ordered,ordered[1:]+ordered[:1])]
    expanded=np.vstack((vertices,new_point))
    minimum_angle=180.
    for triangle in triangles:
        p=expanded[triangle]
        lengths=[np.linalg.norm(p[(i+1)%3]-p[i]) for i in range(3)]
        if min(lengths) <= span*1e-10:raise ValueError('曲面补片含过短边')
        angles=[np.degrees(np.arccos(np.clip(np.dot(p[(i+1)%3]-p[i],p[(i+2)%3]-p[i])/
                    (np.linalg.norm(p[(i+1)%3]-p[i])*np.linalg.norm(p[(i+2)%3]-p[i])),-1,1))) for i in range(3)]
        if min(angles) < 5:raise ValueError('曲面补片出现小于5度的瘦三角形')
        minimum_angle=min(minimum_angle,min(angles))
    return expanded,triangles,dict(method='local_quadric_fan',added_vertex_id=new_id,
        fitted_center=new_point.tolist(),fit_max_residual=float(np.max(np.abs(residual))*span),
        neighborhood_sample_count=len(context),minimum_triangle_angle_degrees=minimum_angle,
        minimum_triangle_angle_limit_degrees=5)
