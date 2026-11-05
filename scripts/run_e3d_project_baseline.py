"""Run our policies on exactly the STL inputs offered to E-3D."""
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from medical_mesh import load_mesh, save_mesh, detect_defects, repair_mesh, RepairOptions
from prepare_e3d_benchmark import CASES


def main():
    base = ROOT / 'results/e3d_benchmark'
    output = base / 'project_outputs'
    output.mkdir(exist_ok=True)
    strategies = {
        'hole': dict(fill_boundary_ids=(0,)),
        'duplicate': dict(remove_duplicates=True),
        'degenerate': dict(remove_degenerate=True),
        'flip': dict(orient_faces=True),
        # This synthetic fixture explicitly appends the unwanted face at 960.
        'non_manifold_edge': dict(delete_face_ids=(960,)),
    }
    rows = []
    for name, source, reference, task, loops, components in CASES:
        path = base / 'inputs' / (name + '.stl')
        asset = load_mesh(path)
        result = None
        if name in strategies:
            candidate, result = repair_mesh(asset, RepairOptions(
                **strategies[name], check_self_intersection=True))
            if not result.accepted:
                raise RuntimeError(f'{name}: {result.errors}')
        else:
            candidate = asset
        exported = output / (name + '.stl')
        save_mesh(candidate, exported)
        diagnosis = detect_defects(load_mesh(exported), check_self_intersection=True)
        metrics = diagnosis.metrics
        record = dict(input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      task=task, strategy=strategies.get(name, {}),
                      operation='repair' if result else 'unchanged_export',
                      repair_result=result.to_dict() if result else None,
                      exported_diagnosis=diagnosis.to_dict())
        (output / (name + '.json')).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        rows.append(dict(case=name, operation=record['operation'],
                         input_faces=len(asset.faces), output_faces=len(candidate.faces),
                         boundary_loops=metrics['boundary_loop_count'],
                         components=metrics['component_count'],
                         topology_matches_target=bool(metrics['topology_passed']
                             and metrics['boundary_loop_count'] == loops
                             and metrics['component_count'] == components),
                         self_intersection_status=diagnosis.self_intersection['status']))
    with (output / 'baseline.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
