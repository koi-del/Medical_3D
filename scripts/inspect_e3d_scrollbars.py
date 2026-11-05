import json
from pathlib import Path
import win32gui
import win32process
BASE=Path(__file__).resolve().parents[1]/'results/e3d_complex'
windows=json.loads((BASE/'windows.json').read_text(encoding='utf-8'))
main=next(w['hwnd'] for w in windows if w['title'].startswith('E-3D '))
rows=[]
def visit(hwnd,_):
    name=win32gui.GetClassName(hwnd)
    if 'scroll' in name.lower() and win32gui.IsWindowVisible(hwnd):
        rows.append(dict(hwnd=hwnd,cls=name,parent=win32gui.GetParent(hwnd),rect=win32gui.GetWindowRect(hwnd),id=win32gui.GetDlgCtrlID(hwnd)))
pid=win32process.GetWindowThreadProcessId(main)[1]
roots=[]
win32gui.EnumWindows(lambda hwnd,_:roots.append(hwnd) if win32process.GetWindowThreadProcessId(hwnd)[1]==pid and win32gui.IsWindowVisible(hwnd) else None,None)
for root in roots:win32gui.EnumChildWindows(root,visit,None)
print(json.dumps(rows,ensure_ascii=False,indent=2))
