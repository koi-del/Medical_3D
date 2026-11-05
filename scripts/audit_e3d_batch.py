"""Audit actual vendor exports, preserving raw files and provenance."""
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from medical_mesh import load_mesh, detect_defects
from audit_e3d_hole import triangles
from prepare_e3d_benchmark import CASES
from compare_e3d_outputs import main as compare

BASE = ROOT / 'results/e3d_benchmark'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    raw_files = list((BASE / 'vendor_raw/remaining_batch').glob('*.stl'))
    rows = []
    # E-3D shortens generated object names. Match exact known suffixes only;
    # never guess from geometric similarity or substitute our own output.
    aliases = {'non_manifold_edge': ['non_manifold', 'non_manifold_edge'],
               'two_components': ['two_componen', 'two_components']}
    targets = [(case[0], case[0], case[0] not in ('open_tube', 'two_components', 'liver'))
               for case in CASES if case[0] != 'hole']
    targets += [('open_tube_default', 'open_tube', True),
                ('two_components_default', 'two_components', True)]
    for output_name, case, repaired in targets:
        row = dict(case=output_name, status='awaiting_manual_export', raw_file='',
                   face_count='', boundary_loops='', components='',
                   quality_status='', same_oriented_triangles_as_project='',
                   bbox_max_difference_from_project='', error='')
        candidates = []
        for path in raw_files:
            name = path.stem.replace(' ', '')
            is_repaired = name.startswith('自动修复-')
            suffix = name.removeprefix('自动修复-') if is_repaired else name
            if is_repaired == repaired and suffix in aliases.get(case, [case]):
                candidates.append(path)
        if len(candidates) > 1:
            row.update(status='ambiguous_export', error='Multiple matching raw files')
        elif candidates:
            raw = candidates[0]
            try:
                mesh = load_mesh(raw)
                diagnosis = detect_defects(mesh, check_self_intersection=True)
                project_path = BASE / 'project_outputs' / (case + '.stl')
                project = load_mesh(project_path)
                input_path = BASE / 'inputs' / (case + '.stl')
                unoriented, project_unoriented = triangles(mesh), triangles(project)
                comparison = dict(
                    same_oriented_triangle_multiset=triangles(mesh, True) == triangles(project, True),
                    vendor_triangles_absent_from_project=sum((unoriented-project_unoriented).values()),
                    project_triangles_absent_from_vendor=sum((project_unoriented-unoriented).values()),
                    bbox_max_difference_from_project=float(np.max(np.abs(
                        np.asarray(diagnosis.metrics['bbox']) - np.asarray([
                            project.vertices.min(axis=0), project.vertices.max(axis=0)])))),
                    equality_basis='Exact reimported STL coordinates; face order ignored')
                record = dict(case=output_name, operation='default_auto_repair' if repaired else 'unchanged_export',
                              raw_file=str(raw.relative_to(ROOT)), raw_sha256=digest(raw),
                              input_file=str(input_path.relative_to(ROOT)), input_sha256=digest(input_path),
                              project_output_sha256=digest(project_path),
                              diagnosis=diagnosis.to_dict(), comparison=comparison)
                (BASE / (output_name + '_independent_audit.json')).write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
                if output_name == case:
                    destination = BASE / 'e3d_outputs' / (case + '.stl')
                    shutil.copy2(raw, destination)
                    if digest(destination) != digest(raw):
                        raise RuntimeError('Standardized copy hash mismatch')
                row.update(status='measured', raw_file=str(raw.relative_to(ROOT)),
                           face_count=len(mesh.faces), boundary_loops=diagnosis.metrics['boundary_loop_count'],
                           components=diagnosis.metrics['component_count'], quality_status=diagnosis.quality_status,
                           same_oriented_triangles_as_project=comparison['same_oriented_triangle_multiset'],
                           bbox_max_difference_from_project=comparison['bbox_max_difference_from_project'])
            except Exception as error:
                row.update(status='audit_failed', error=str(error))
        rows.append(row)
    with (BASE / 'remaining_batch_audit.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    compare()
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
