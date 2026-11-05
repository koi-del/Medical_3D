"""Record observed UI counts separately from independent file measurements."""
import json
from pathlib import Path
from PIL import Image

BASE = Path(__file__).resolve().parents[1] / 'results/e3d_benchmark'
evidence = BASE / 'evidence'
evidence.mkdir(exist_ok=True)
for case, filename in [('open_tube', 'open_tube_default_result_2.png'),
                       ('two_components', 'two_components_default_result_2.png'),
                       ('duplicate', 'duplicate_default_result_2.png'),
                       ('degenerate', 'degenerate_default_result_2.png'),
                       ('flip', 'flip_default_result_2.png'),
                       ('non_manifold_edge', 'non_manifold_edge_default_result_2.png')]:
    with Image.open(BASE / filename) as screenshot:
        # Only relevant E-3D controls and preview counters; omit account header.
        screenshot.crop((0, 200, 325, 675)).save(evidence / (case + '_settings.png'))
        screenshot.crop((350, 1430, 1100, 1480)).save(evidence / (case + '_preview_counts.png'))
        screenshot.crop((1880, 220, 2110, 285)).save(evidence / (case + '_identity.png'))
with Image.open(BASE / 'liver_selected_2.png') as screenshot:
    screenshot.crop((2115, 1130, 2530, 1405)).save(evidence / 'liver_import_properties.png')
with Image.open(BASE / 'batch_add_14_3.png') as screenshot:
    screenshot.crop((1320, 400, 1940, 680)).save(evidence / 'remaining_export_list.png')
status_path = BASE / 'research_status.json'
status = json.loads(status_path.read_text(encoding='utf-8-sig'))
import csv
with (BASE / 'comparison.csv').open(encoding='utf-8-sig', newline='') as stream:
    measured = sum(row['status'] == 'measured' for row in csv.DictReader(stream))
status.update(vendor_sample_runs_completed=measured, vendor_sample_runs_pending=8-measured,
              export_state='all_files_measured' if measured == 8 else 'remaining_batch_awaiting_manual_export',
              vendor_models_imported=[name + '.stl' for name in (
                  'hole', 'open_tube', 'two_components', 'duplicate', 'degenerate', 'flip',
                  'non_manifold_edge', 'liver')],
              vendor_ui_cases_exercised=8,
              vendor_ui_observations={
                  'open_tube': {'before_faces': 48, 'preview_faces': 92,
                                'independent_output_measurement': (BASE / 'open_tube_default_independent_audit.json').exists()},
                  'two_components': {'before_faces': 8, 'preview_faces': 8,
                                     'independent_output_measurement': (BASE / 'two_components_default_independent_audit.json').exists()},
                  'duplicate': {'import_faces': 961, 'preview_faces': 960},
                  'degenerate': {'stl_faces': 961, 'import_faces': 960, 'preview_faces': 960},
                  'flip': {'import_faces': 960, 'preview_faces': 960},
                  'non_manifold_edge': {'import_faces': 961, 'preview_faces': 960},
                  'liver': {'import_vertices': 9710, 'import_faces': 19416,
                            'operation': 'unchanged_export'}},
              comparison_claim=('Exact oriented STL triangle equality for eight planned cases; '
                                'five repair outputs and three unchanged-export outputs. '
                                'No general or clinical equivalence established') if measured == 8 else
                               'Exact oriented STL triangle equality established only for one synthetic triangular hole')
status.pop('vendor_ui_only_observations', None)
status['last_updated'] = '2026-10-23'
status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
print('Recorded eight UI cases;', measured, 'independently measured main-case exports.')
