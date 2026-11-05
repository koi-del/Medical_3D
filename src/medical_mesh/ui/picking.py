"""Nearest-boundary picking with a finite geometric tolerance."""
import numpy as np


def nearest_boundary(asset,diagnosis,point,relative_tolerance=.025):
    point=np.asarray(point,dtype=float)
    if point.shape!=(3,) or not np.isfinite(point).all():return None
    scale=float(np.linalg.norm(np.ptp(asset.vertices,axis=0)))
    best=None;distance=float('inf')
    for boundary in diagnosis['boundaries']:
        for ia,ib in boundary['edges']:
            a,b=asset.vertices[[ia,ib]]
            ab=b-a;denom=float(ab@ab)
            t=np.clip(float((point-a)@ab)/denom,0,1) if denom else 0
            value=float(np.linalg.norm(point-(a+t*ab)))
            if value<distance:best=boundary['id'];distance=value
    return best if distance<=scale*relative_tolerance else None
