"""Render the five reported samples and validate overlay geometry and panel labels."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtWidgets import QApplication,QMainWindow
from medical_mesh import load_mesh,detect_defects
from medical_mesh.ui.member1_panel import Member1Panel
from medical_mesh.ui.preview_host import ViewerAdapter
errors=[]
sys.excepthook=lambda kind,value,tb:errors.append(repr(value))

app=QApplication([])
window=QMainWindow();viewer=ViewerAdapter(window)
out=ROOT/'results'/'display_fix';out.mkdir(parents=True,exist_ok=True)
panel=Member1Panel(viewer,out/'session');window.setCentralWidget(panel)
window.resize(1400,1000);window.show();app.processEvents()
checks=[]
for name,folder,row in [('hole','damaged',5),('open_tube','reference',6),('non_manifold_edge','damaged',3),
                        ('flip','damaged',2),('degenerate','damaged',1)]:
    panel.asset=load_mesh(ROOT/'data'/folder/(name+'.npz'))
    panel.bind_diagnosis(detect_defects(panel.asset).to_dict());panel.render()
    panel.defects.item(row).setSelected(True);panel.highlight()
    app.processEvents()
    if name in ('hole','open_tube','non_manifold_edge','flip'):
        mesh=viewer.plotter.actors['selected_edges'].mapper.dataset
        assert mesh.n_verts==0, 'Unexpected scattered vertex cells'
    if name in ('hole','open_tube'):assert 'selected_faces' not in viewer.plotter.actors
    if name=='degenerate':
        assert 'collapsed_edges' in viewer.plotter.actors and 'selected_points' in viewer.plotter.actors
    if name=='flip':assert 'normal_0' in viewer.plotter.actors and 'traversal_0' in viewer.plotter.actors
    panel.wire.setChecked(True);app.processEvents()
    assert viewer.highlight_actors
    panel.wire.setChecked(False);app.processEvents()
    if name!='open_tube':panel.focus_selected()
    panel._busy(False)
    app.processEvents()
    window.grab().save(str(out/(name+'.png')))
    checks.append({'sample':name,'status':'passed','label':panel.defects.item(row).text()})
assert not errors, errors
(out/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=False))
viewer.plotter.close();window.close()
