"""Independently audit the manually exported vendor hole result."""
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from medical_mesh import load_mesh, detect_defects


def triangles(mesh, oriented=False):
    counts = Counter()
    for face in mesh.faces:
        points = [tuple(float(x) for x in p) for p in mesh.vertices[face]]
        key = min(tuple(points[i:] + points[:i]) for i in range(3)) if oriented else tuple(sorted(points))
        counts[key] += 1
    return counts


def main():
    base = ROOT / 'results/e3d_benchmark'
    files = list((base / 'vendor_raw/hole_default').glob('*.stl'))
    if len(files) != 1:
        raise RuntimeError('Expected exactly one manually exported STL')
    raw = files[0]
    target = base / 'e3d_outputs/hole.stl'
    target.parent.mkdir(exist_ok=True)
    shutil.copy2(raw, target)
    vendor = load_mesh(target)
    project = load_mesh(base / 'project_outputs/hole.stl')
    original = load_mesh(base / 'inputs/hole.stl')
    diagnosis = detect_defects(vendor, check_self_intersection=True)
    v, p, o = triangles(vendor), triangles(project), triangles(original)
    record = dict(
        raw_file=str(raw.relative_to(ROOT)),
        raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
        standardized_copy_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        input_sha256=hashlib.sha256((base / 'inputs/hole.stl').read_bytes()).hexdigest(),
        diagnosis=diagnosis.to_dict(),
        comparison=dict(
            coordinate_precision='Exact equality of reimported STL floating point coordinates; face order ignored',
            vendor_triangles_absent_from_project=sum((v-p).values()),
            project_triangles_absent_from_vendor=sum((p-v).values()),
            same_oriented_triangle_multiset=triangles(vendor, True) == triangles(project, True),
            removed_input_triangles=sum((o-v).values()),
            added_triangles=sum((v-o).values()),
            bbox_max_difference_from_project=float(np.max(np.abs(
                np.array(diagnosis.metrics['bbox']) - np.array([
                    project.vertices.min(axis=0), project.vertices.max(axis=0)])))),
        ),
        scope='One synthetic triangular hole, default vendor repair versus explicitly selected project hole repair. No broader equivalence established.',
    )
    (base / 'hole_independent_audit.json').write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(metrics=diagnosis.metrics, self_intersection=diagnosis.self_intersection,
                          comparison=record['comparison']), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
