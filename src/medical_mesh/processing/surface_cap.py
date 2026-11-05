"""Bounded height-field patches with fixed rim and conforming interior refinement."""
from dataclasses import replace
import numpy as np


def _design(xy):
    x,y=xy.T
    return np.column_stack((np.ones(len(x)),x,y,x*x,x*y,y*y))


def _kernel(a,b):
    r2=np.sum((a[:,None,:]-b[None,:,:])**2,axis=2)
    return .5*r2*np.log(np.maximum(r2,1e-30))


def _minimum_angle(points,triangles):
    p=points[np.asarray(triangles)]
    angles=[]
    for i in range(3):
        u=p[:,(i+1)%3]-p[:,i];v=p[:,(i+2)%3]-p[:,i]
        angles.append(np.degrees(np.arctan2(np.linalg.norm(np.cross(u,v),axis=1),np.einsum('ij,ij->i',u,v))))
    return float(np.min(angles))


def _relax_patch(output,projected,triangles,first_new,lift):
    """Move only new interior vertices, accepting local angle improvements."""
    points=np.asarray(output).copy();xy=np.asarray(projected).copy();faces=np.asarray(triangles)
    before=_minimum_angle(points,faces);moves=0
    incident={int(v):np.flatnonzero(np.any(faces==v,axis=1)) for v in np.unique(faces) if v>=first_new}
    for _ in range(6):
        changed=False
        for vertex,ids in incident.items():
            star=faces[ids];neighbors=np.unique(star);neighbors=neighbors[neighbors!=vertex]
            target=xy[neighbors].mean(axis=0)
            old_xy=xy[vertex].copy();old_point=points[vertex].copy();old_quality=_minimum_angle(points,star)
            p=xy[star];u=p[:,1]-p[:,0];v=p[:,2]-p[:,0];sign=u[:,0]*v[:,1]-u[:,1]*v[:,0]
            for step in (.5,.25):
                candidate=old_xy+step*(target-old_xy);xy[vertex]=candidate
                p=xy[star];u=p[:,1]-p[:,0];v=p[:,2]-p[:,0];area=u[:,0]*v[:,1]-u[:,1]*v[:,0]
                if np.any(area*sign<=1e-20):xy[vertex]=old_xy;continue
                try:points[vertex]=lift(candidate)
                except ValueError:xy[vertex]=old_xy;continue
                if _minimum_angle(points,star)>old_quality+1e-5:
                    moves+=1;changed=True;break
                xy[vertex]=old_xy;points[vertex]=old_point
            else:
                xy[vertex]=old_xy;points[vertex]=old_point
        if not changed:break
    return points,dict(interior_relaxation_moves=moves,minimum_angle_before_degrees=before,
                       minimum_angle_after_degrees=_minimum_angle(points,faces))


def _improve(triangles,xy,rim):
    """Quality-improving interior flips, with fixed polygon constraints."""
    def quality(t):
        p=xy[t];u,v=p[1]-p[0],p[2]-p[0]
        return abs(u[0]*v[1]-u[1]*v[0])/sum(np.sum((p[i]-p[(i+1)%3])**2) for i in range(3))
    def turn(a,b,c):
        u,v=xy[b]-xy[a],xy[c]-xy[a]
        return u[0]*v[1]-u[1]*v[0]
    for _ in range(12):
        edges={}
        for index,t in enumerate(triangles):
            for i in range(3):edges.setdefault(tuple(sorted((t[i],t[(i+1)%3]))),[]).append(index)
        used=set();changed=False
        for (a,b),indices in edges.items():
            if (a,b) in rim or len(indices)!=2 or used.intersection(indices):continue
            i,j=indices;c=next(v for v in triangles[i] if v not in (a,b));d=next(v for v in triangles[j] if v not in (a,b))
            if c==d or turn(c,d,a)*turn(c,d,b)>=-1e-18:continue
            if tuple(sorted((c,d))) in edges:continue
            if np.linalg.norm(xy[c]-xy[d])>np.linalg.norm(xy[a]-xy[b])+1e-12:continue
            replacement=[[c,d,a],[d,c,b]]
            if min(map(quality,replacement))<=min(quality(triangles[i]),quality(triangles[j]))+1e-8:continue
            sign=turn(*triangles[i])
            for t in replacement:
                if turn(*t)*sign<0:t[1],t[2]=t[2],t[1]
            triangles[i],triangles[j]=replacement;used.update(indices);changed=True
        if not changed:break
    return triangles


def surface_cap(vertices,faces,ordered,options):
    from .repair_policy import _triangulate_loop
    if not 6<=len(ordered)<=min(64,options.max_hole_edges):
        raise ValueError('邻域曲面补洞仅支持6至64边简单孔')
    points=vertices[ordered];center=points.mean(axis=0)
    span=float(np.linalg.norm(np.ptp(points,axis=0)))
    if span<=0 or span>options.max_hole_span:raise ValueError('曲面补洞超过跨度限制')
    context_ids=np.asarray(ordered)
    for _ in range(2):
        context_ids=np.unique(faces[np.any(np.isin(faces,context_ids),axis=1)])
    if len(context_ids)>256:raise ValueError('局部邻域超过256点预算，请使用更小孔洞')
    if len(context_ids)<12:raise ValueError('曲面补洞邻域采样不足')
    context=(vertices[context_ids]-center)/span
    _,_,pca=np.linalg.svd((points-center)/span,full_matrices=False)
    frames=[pca,np.eye(3),np.eye(3)[[1,2,0]],np.eye(3)[[2,0,1]]]
    choices=[]
    for frame in frames:
        local=context@frame.T;xy=local[:,:2];z=local[:,2]
        design=_design(xy)
        coefficient,_,rank,singular=np.linalg.lstsq(design,z,rcond=None)
        if rank<6 or singular[0]/singular[-1]>1e6:continue
        delta=xy[:,None,:]-xy[None,:,:]
        distance=np.sum(delta*delta,axis=2);np.fill_diagonal(distance,np.inf)
        if distance.min()<1e-14:continue
        # Leave-one-out quadratic residual penalizes near-vertical projections.
        cubic=np.column_stack((design,xy[:,0]**3,xy[:,0]**2*xy[:,1],xy[:,0]*xy[:,1]**2,xy[:,1]**3))
        scores=[]
        for model in (design,cubic):
            coef,_,model_rank,_=np.linalg.lstsq(model,z,rcond=None)
            if model_rank<model.shape[1]:continue
            leverage=np.einsum('ij,ji->i',model,np.linalg.pinv(model))
            residual=(model@coef-z)/np.maximum(1-leverage,.05)
            scores.append(float(np.sqrt(np.mean(residual**2))))
        projected=(vertices-center)@frame.T/span
        flattened=np.column_stack((projected[:,:2],np.zeros(len(vertices))))
        try:
            triangles=_triangulate_loop(flattened,ordered,faces,replace(options,max_hole_span=10.,max_planarity_ratio=1.))
        except ValueError:continue
        choices.append((min(scores),frame,local,triangles))
    if not choices:raise ValueError('孔边界没有稳定的无自交高度场投影')
    score,frame,local,triangles=min(choices,key=lambda c:c[0])
    if score>.15:raise ValueError('邻域高度场拟合不稳定，保留原模型')
    xy=local[:,:2];z=local[:,2];p=_design(xy);n=len(xy)
    system=np.block([[_kernel(xy,xy)+np.eye(n)*1e-8,p],[p.T,np.zeros((6,6))]])
    if np.linalg.cond(system)>1e12:raise ValueError('曲面插值条件数过大')
    weights=np.linalg.solve(system,np.r_[z,np.zeros(6)])
    def lift(q):
        height=float((_kernel(q[None,:],xy)@weights[:n]+_design(q[None,:])@weights[n:])[0])
        if not np.isfinite(height) or height<z.min()-.5 or height>z.max()+.5:
            raise ValueError('曲面插值偏离邻域过大')
        return center+np.r_[q,height]@frame*span
    output=vertices.tolist()
    projected=((vertices-center)@frame.T/span)[:,:2].tolist()
    rim={tuple(sorted((a,b))) for a,b in zip(ordered,list(ordered[1:])+[ordered[0]])}
    # Fixed long rim segments make arbitrarily short interior edges impossible.
    edge_limit=max(.10,1.05*max(np.linalg.norm(np.asarray(projected[a])-projected[b]) for a,b in rim))
    triangles=_improve(triangles,np.asarray(projected),rim)
    # Split an interior edge in both incident triangles; rim edges never change.
    for iteration in range(768):
        edges={tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3)}-rim
        if not edges:break
        edge=max(sorted(edges),key=lambda e:np.linalg.norm(np.asarray(projected[e[0]])-projected[e[1]]))
        a,b=edge;q=(np.asarray(projected[a])+projected[b])/2
        if np.linalg.norm(np.asarray(projected[a])-projected[b])<=edge_limit:break
        midpoint=len(output);output.append(lift(q).tolist());projected.append(q.tolist())
        refined=[]
        for triangle in triangles:
            if a in triangle and b in triangle:
                for i in range(3):
                    u,v,w=triangle[i],triangle[(i+1)%3],triangle[(i+2)%3]
                    if {u,v}=={a,b}:
                        refined.extend(([u,midpoint,w],[midpoint,v,w]));break
            else:refined.append(triangle)
        triangles=refined
        if iteration%8==7:triangles=_improve(triangles,np.asarray(projected),rim)
    else:raise ValueError('曲面补片超过768点预算')
    expanded,relaxation=_relax_patch(output,projected,triangles,len(vertices),lift)
    t=expanded[np.asarray(triangles)]
    area=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)
    if area.min()<span*span*1e-10:raise ValueError('曲面补片产生退化三角形')
    return expanded,triangles,dict(method='fixed_rim_thin_plate_patch',
        added_vertex_count=len(expanded)-len(vertices),neighborhood_sample_count=n,
        projection_frame=frame.tolist(),polynomial_loo_rms=score*span,
        **relaxation,
        boundary_fixed=True,interior_edge_limit=edge_limit*span,
        limitation='局部高度场插值，不能保证恢复未知原曲面；必须检查预览和自交')
