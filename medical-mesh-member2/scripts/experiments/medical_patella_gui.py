"""Open saved real-model artifacts in the desktop UI; verify unchanged reference."""
from pathlib import Path
import sys
import json
import argparse
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from medical_mesh.ui.bootstrap import configure_qt
configure_qt()
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from medical_mesh.ui.main_window import MainWindow
from medical_mesh.core.model import load_asset, write_json
import numpy as np


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',default='runs/medical_patella_verified_20261022')
    args=parser.parse_args();out=Path(args.out).resolve()
    configure_qt();app=QApplication([]);app.setStyle('Fusion')
    window=MainWindow(ROOT);reference=load_asset(out/'reference.npz');candidate=load_asset(out/'selected_candidate.npz')
    version,geometry=reference.version_id,reference.geometry_hash
    window.set_asset(reference);window.current_candidate=candidate;window.cad.set_assets(reference,candidate)
    summary=json.loads((out/'optimization_summary.json').read_text())
    with np.load(out/'optimization'/summary['selected']/'final_samples.npz',allow_pickle=False) as arrays:
        window.viewer.show_comparison(reference,candidate,{k:arrays[k] for k in arrays.files})
    window.tabs.setCurrentWidget(window.cad);window.show()
    directory=out/'gui';directory.mkdir(exist_ok=True)
    errors=[]
    def verify():
        try:
            assert 'reference_mesh' in window.viewer.plotter.renderers[0].actors
            window.grab().save(str(directory/'original_vs_optimized.png'))
            window.load_saved_task(out/'conversion/stl_to_step/result.json')
            assert window.conversion_results.result['geometry_status']=='passed'
            assert window.viewer.assets[1].unit_name=='mm'
            window.workspace.setCurrentWidget(window.conversion_results)
            window.grab().save(str(directory/'real_conversion_result.png'))
            window.load_saved_task(out/'report.html')
            text=window.report_viewer.browser.toPlainText()
            assert '2,400' in text and 'MRI' in text
            assert window.workspace.currentWidget() is window.report_viewer
            assert window.current_asset.version_id==version and window.current_asset.geometry_hash==geometry
            assert window.current_candidate.metadata['quality_status']=='unverified'
            window.grab().save(str(directory/'real_experiment_report.png'))
            write_json(directory/'verification.json',{'status':'passed','original_vs_optimized_preview':True,
                'conversion_result_and_readback_preview':True,'full_report_in_same_window':True,
                'reference_unchanged':True,'candidate_unverified':True})
        except Exception as error:
            errors.append(str(error));write_json(directory/'verification.json',{'status':'failed','errors':errors})
        finally:
            window.close();app.quit()
    QTimer.singleShot(1200,verify)
    QTimer.singleShot(30000,lambda:app.exit(3))
    result=app.exec()
    return result if not errors else 2


if __name__=='__main__':
    raise SystemExit(main())
