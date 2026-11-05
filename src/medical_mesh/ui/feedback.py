"""Human-readable explanations without changing backend gate decisions."""
REASONS={
    'Self-intersection remains unverified':'自交尚未完成验证，不能视为无自交',
    'Self-intersection check unavailable or failed':'自交检查不可用或失败，请查看报告',
    'Unit unknown: lengths are in original coordinate units':'单位未确认；尺寸与距离按原坐标单位显示',
    'D95_LIMIT_EXCEEDED':'D95超过阈值；可增加保留面数或减弱处理强度',
    'SAMPLED_MAX_LIMIT_EXCEEDED':'采样最大偏差超过阈值；请检查局部变形',
    'AREA_LIMIT_EXCEEDED':'表面积变化超过阈值；请检查收缩或形状损失',
    'ZERO_AREA_FACE':'产生零面积面，需要修复后重新检查',
    'STRUCTURAL_CHECK_FAILED':'结构复检未通过；请查看边界、分量、方向及自交检查',
    'REQUIRED_CHECK_UNAVAILABLE':'必需的检查尚未验证，不能视为通过',
    'MEMBER1_DIAGNOSTIC_SERVICE_MISSING':'缺少结构诊断服务，无法完成复检',
    'DIAGNOSTIC_SERVICE_MISSING':'缺少结构诊断服务，无法完成复检',
    'DIAGNOSTIC_ERROR':'结构诊断出错；请查看任务报告',
    'FINAL_CHECK_FAILED':'最终独立复核未通过',
    'NO_CANDIDATE_ACCEPTED':'没有候选同时满足结构和误差阈值',
    'CANDIDATE_FAILED':'候选计算失败；请查看任务日志',
    'FIXTURE_OR_UNDECLARED_SCOPE':'诊断来源未声明为生产检查',
    'UNVERIFIED':'尚未验证，不能视为通过',
}

def explain_reasons(reasons):
    return '；'.join(REASONS.get(reason,str(reason)) for reason in reasons)
