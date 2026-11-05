# 成员1与成员2交接协议提案v1

日期：2026年10月18日。状态：成员2已实现，待成员1共同审核；不代表双方已经确认。

## 模型文件

每份交接包括同名`mesh.npz`和`mesh.json`。NPZ只含vertices float64[N,3]、faces int64[M,3]，读取关闭pickle。JSON记录schema_version=1.0、asset_id、version_id、parent_version、unit_status、unit_name、unit_to_mm、source_path、source_sha256、operation、parameters、metadata、geometry_sha256。

几何哈希为小端float64顶点数组字节加小端int64面数组字节的SHA256，均按C顺序。任意重编号或坐标变化会改变哈希；哈希用于识别几何，不代替源文件哈希。加载时检查配对哈希。

unknown单位时name和scale均为null；confirmed时必须有名称和正的有限unit_to_mm。正式数组保留原坐标单位，CAD适配层显式缩放到毫米。不同单位的两份网格禁止直接比较。

输入不可原地修改，派生结果保留asset_id，生成新version_id，parent_version为输入版本。此版本暂不实现成员1的正式版本存储，候选保存不代表接受。

成员1负责原始读取及共享顶点规范化；成员2预览适配器只对STL完全相同坐标合并，并在metadata记录来源。接入后优先使用成员1导入。复杂边界/ROI的版本内索引不得跨版本复用。

## 诊断适配器

成员2需要用于**参考与候选对比**的函数，而不只是一个“无异常”布尔值：

```python
def diagnose_pair(reference: MeshAsset, candidate: MeshAsset) -> dict:
    # 这里应调用成员1真实检测，再接入双方约定的结构对应评价。
    # 没实现的项明确返回unavailable，不能按下例字段名全填passed。
    return {
        "scope": "production",
        "reference_version": reference.version_id,
        "input_version": candidate.version_id,
        "geometry_sha256": candidate.geometry_hash,
        "checks": {
            "reference_eligible": "unavailable",
            "duplicate_faces": "unavailable",
            "degenerate_faces": "unavailable",
            "nonmanifold_edges": "unavailable",
            "nonmanifold_vertices": "unavailable",
            "orientation": "unavailable",
            "self_intersection": "unavailable",
            "component_correspondence": "unavailable",
            "boundary_correspondence": "unavailable",
            "protected_rois": "unavailable"
        }
    }
```

检查状态为passed/failed/unavailable/not_run。只有boundary_correspondence和protected_rois在明确无对应保护对象时可以not_applicable，其余不能用不适用代替真实检查。fixture_only等测试来源一律不能用于正式合格判定。版本和哈希不匹配返回unverified。

分量/边界/ROI的几何比较仍按原方案由成员2负责，成员1提供本版本的分量、边界环和索引数据；当前接口预留了这些最终门槛，但比较实现尚未完成。该成对适配器是集成出口，不表示把全部结构算法转交给成员1。

## 调用与返回

```python
from medical_mesh.core import load_asset
from medical_mesh.evaluation import evaluate_mesh, EvaluationConfig
from medical_mesh.optimization import optimize_mesh

reference = load_asset("mesh.npz")
metrics, samples = evaluate_mesh(reference, reference, EvaluationConfig(1000, 7))
result = optimize_mesh(reference, [{"operation": "qem", "keep_ratio": .5}],
                       "runs/new_run", diagnostic_service=None)
```

无diagnostic_service时允许生成和评价候选，但结果最多needs_review，output_version为null。所有几何候选超差则rejected且保留参考。只有必需结构和几何检查都通过时才返回selected_candidate；返回accepted表示推荐资格通过，仍需用户显式接受并调用成员1版本服务提交。

任务执行status与decision、quality_status分开。completed不等于passed；failed/cancelled/timeout不产生已接受版本。指标缺失null加原因，不填零。后台通过JSON请求和NPZ交接，不传Qt或FreeCAD对象。

## UI接入

```python
window.register_page("member1_diagnosis", "诊断", your_panel)
window.show_mesh(asset)
window.highlight_faces(asset.version_id, face_ids)
```

当前版实现面高亮，边高亮、版本列表和正式提交恢复仍待后续集成。GUI拥有Qt/VTK对象；后台只计算并写文件。成员1页面的长计算也应经统一任务接口运行，不能直接阻塞按钮回调。
