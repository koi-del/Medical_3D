"""Small staged UI runner; never performs a paid export confirmation."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('stage', choices=['open', 'select', 'run', 'confirm', 'cancel', 'export', 'export-add'])
parser.add_argument('case', choices=['duplicate', 'degenerate', 'flip', 'non_manifold_edge',
                                    'open_tube', 'two_components', 'liver'])
parser.add_argument('--row', type=int)
parser.add_argument('--export-rows', type=int, nargs='+')
args = parser.parse_args()


def step(*options):
    result = subprocess.run([sys.executable, '-X', 'utf8',
        str(ROOT / 'scripts/inspect_e3d.py'), *map(str, options)],
        cwd=ROOT, capture_output=True, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(result.stderr)
    print('Completed:', ' '.join(map(str, options)), flush=True)


case = args.case
if args.stage in ('open', 'select'):
    if args.row is None:
        raise ValueError('Provide the intended new model row (zero based)')
    if args.stage == 'open':
        step('--click', .047, .042, '--label', case + '_data')
        step('--click', .214, .072, '--label', case + '_open')
        step('--file', ROOT / 'results/e3d_benchmark/inputs' / (case + '.stl'),
             '--label', case + '_import')
    # The model list row height is 27 physical pixels in this verified layout.
    step('--click', .88, (366 + 27 * args.row) / 1527,
         '--label', case + '_selected')
    if case != 'liver':
        step('--click', .236, .042, '--label', case + '_mesh')
        step('--click', .049, .072, '--label', case + '_panel')
elif args.stage == 'run':
    step('--press-id', 4323, '--label', case + '_default_result')
elif args.stage == 'confirm':
    step('--press-id', 11, '--label', case + '_confirmed')
elif args.stage == 'cancel':
    step('--press-id', 12, '--label', case + '_cancelled')
elif args.stage == 'export':
    step('--click', .047, .042, '--label', 'batch_data')
    step('--click', .276, .072, '--label', 'batch_export_dialog')
    # Stop after setting destination. Selecting objects and requesting export
    # require separate review; this runner never confirms any charge.
    step('--dialog-title', '导出STL模型', '--edit', 7252,
         ROOT / 'results/e3d_benchmark/vendor_raw/remaining_batch',
         '--controls', '--label', 'batch_export_destination')
elif args.stage == 'export-add':
    for index in args.export_rows or []:
        if not 0 <= index <= 14:
            raise ValueError('Unexpected model list index')
        step('--click', .30, (456 + 36.2 * index) / 1527,
             '--label', f'batch_pick_{index}')
        step('--dialog-title', '导出STL模型', '--press-id', 7086,
             '--label', f'batch_add_{index}')
