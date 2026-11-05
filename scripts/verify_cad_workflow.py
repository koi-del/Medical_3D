"""Exercise all six real CAD directions through the unified desktop workflow."""
import os,sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));os.environ.setdefault('QT_API','pyside6')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from medical_mesh.ui.workbench import Workbench
out=ROOT/'results/cad_six_directions/gui';out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);window=Workbench(ROOT,out/'session');window.show()
window.root=out;window.numerical.root=out
n=window.numerical;cad=n.cad;window.set_step('export')
pairs=[('stl','step'),('stl','igs'),('step','stl'),('igs','stl'),('step','igs'),('igs','step')]
fixture=ROOT/'results/cad_six_directions/windows_114_relative/fixtures/sphere'
checks=[];active=None;start=time.monotonic();beats=0
def pulse():
    global beats
    beats+=1
heartbeat=QTimer();heartbeat.timeout.connect(pulse);heartbeat.start(40)
def finish(error=None):
    timer.stop()
    (out/'verification.json').write_text(json.dumps(dict(status='completed' if error is None else 'failed',checks=checks,error=error,heartbeats=beats),ensure_ascii=False,indent=2),encoding='utf-8')
    print(checks,error,flush=True);window.close();app.exit(0 if error is None else 1)
def tick():
    global active
    try:
        if time.monotonic()-start>240:raise RuntimeError('CAD GUI timeout')
        if n.jobs.busy:return
        if active:
            result=n.last_result
            assert result and result.get('status')=='completed',str(result)
            assert result.get('geometry_status')=='passed',str(result.get('errors'))
            assert window.repair.asset is None,'conversion replaced accepted mesh'
            checks.append(dict(direction='->'.join(active),geometry_status=result['geometry_status']))
            window.grab().save(str(out/('to_'+active[1]+'_'+active[0]+'.png')))
            active=None
        if not pairs:finish();return
        active=pairs.pop(0);source,target=active
        # A completed task routes the property dock to its result page.
        # Re-enter the export step as a user would before the next conversion.
        window.set_step('export')
        cad.mode.setCurrentIndex(0);cad.input_path.setText(str(fixture/('source.'+source)))
        cad.output_root.setText(str(out/'jobs'));cad.samples.setValue(50000)
        if source=='stl':
            cad.units.setCurrentIndex(0);assert not cad.run_button.isEnabled()
            cad.units.setCurrentIndex(1)
        cad.target.setCurrentIndex(cad.target.findData(target))
        assert cad.run_button.isVisible() and cad.run_button.isEnabled(),cad.validation.text()
        QTest.mouseClick(cad.run_button,Qt.LeftButton)
        assert n.jobs.busy,'job not submitted'
    except Exception as exc:finish(repr(exc))
timer=QTimer();timer.timeout.connect(tick);timer.start(150)
sys.exit(app.exec())
