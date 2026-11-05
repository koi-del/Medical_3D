"""Conservative geometric suggestions; anatomy cannot be inferred from a rim alone."""
import numpy as np

def boundary_advice(asset,boundaries):
    diagonal=float(np.linalg.norm(np.ptp(asset.vertices,axis=0)))
    result=[]
    for b in boundaries:
        ratio=b['span']/max(diagonal,1e-12)
        small=b['kind']=='simple_loop' and b['edge_count']<=64 and ratio<.12
        result.append(dict(id=b['id'],role='repair_target' if small else 'uncertain',
            reason='闭合小孔，跨度小于模型对角线12%；建议人工确认后补洞' if small else '较大开口、复杂边界或可能天然开口；仅凭几何不能确定用途，建议保留并人工判断'))
    return result
