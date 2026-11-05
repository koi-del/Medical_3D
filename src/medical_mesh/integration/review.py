"""Validate an optimization result before entering the shared pending review."""
from ..processing.repair_policy import RepairResult
from ..core.changes import mesh_changes
from ..processing.patch_quality import patch_quality
from ..member2.optimization.search import check_diagnosis,geometry_reasons,Limits
from .member2 import to_optimization,diagnose_pair


def validate_optimization(reference,candidate,verification):
    if candidate.asset_id!=reference.asset_id or candidate.parent_version!=reference.version:
        raise ValueError('优化候选已过期或不属于当前参考版本')
    expected=to_optimization(reference)
    if (candidate.unit_status,candidate.source_unit,candidate.unit_to_mm)!=(reference.unit_status,reference.source_unit,reference.unit_to_mm):
        raise ValueError('优化候选改变单位元数据')
    if verification.get('status')!='completed' or verification.get('input_version')!=reference.version:
        raise ValueError('优化结果未完成或参考版本已失配')
    attempts=[item for item in verification.get('attempts',[]) if item.get('version_id')==candidate.version]
    if len(attempts)!=1:raise ValueError('优化候选与实际生成版本不匹配')
    attempt=attempts[0]
    if attempt.get('diagnosis',{}).get('status')!='passed':
        raise ValueError('该候选尚未通过任务二结构复核，不能提交正式审核')
    metrics=attempt.get('final_metrics',{})
    optimized=to_optimization(candidate)
    if (attempt.get('geometry_sha256')!=optimized.geometry_hash or metrics.get('reference_hash')!=expected.geometry_hash or
        metrics.get('candidate_hash')!=optimized.geometry_hash or metrics.get('reference_version')!=reference.version or
        metrics.get('candidate_version')!=candidate.version):
        raise ValueError('优化复核记录与实际模型几何或版本不匹配')
    if not attempt.get('final_passed') or not attempt.get('final_metrics'):
        raise ValueError('该候选未通过独立种子的最终误差复核')
    if geometry_reasons(attempt['final_metrics'],Limits(**verification.get('limits',{}))):
        raise ValueError('候选几何误差超过本次优化阈值')
    structural=check_diagnosis(diagnose_pair,expected,optimized)
    if structural['status']!='passed':raise ValueError('当前版本结构复检未通过：'+structural['reason'])
    diagnosis=structural['details']
    return RepairResult(status='completed',input_version=reference.version,output_version=candidate.version,
        accepted=True,quality_status=diagnosis['diagnosis_after']['quality_status'],
        diagnosis_before=diagnosis['diagnosis_before'],diagnosis_after=diagnosis['diagnosis_after'],
        operations=[dict(operation='member2_optimization',candidate_id=attempt['candidate_id'],
            parameters=attempt['parameters'],final_metrics=attempt['final_metrics'])],
        metrics=dict(changes=mesh_changes(reference,candidate),patch_quality=patch_quality(candidate,[]),
            optimization_verification=verification))
