"""Inspect only E-3D Master's own visible window; save local benchmark evidence."""
import json,argparse,time
from pathlib import Path
import win32gui,win32process,win32con,win32api
import ctypes
from ctypes import wintypes
ctypes.windll.user32.SetProcessDPIAware()
from PIL import ImageGrab

out=Path(__file__).resolve().parents[1]/'results'/'e3d_benchmark'
out.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser()
parser.add_argument('--click',nargs=2,type=float)
parser.add_argument('--label',default='inspect')
parser.add_argument('--file')
parser.add_argument('--controls',action='store_true')
parser.add_argument('--press-id',type=int,action='append',default=[])
parser.add_argument('--check',nargs=2,type=int,action='append',default=[])
parser.add_argument('--edit',nargs=2,action='append',default=[])
parser.add_argument('--dialog-title')
parser.add_argument('--tree-index',type=int)
parser.add_argument('--output-root',choices=['e3d_benchmark','e3d_complex','e3d_optimization','e3d_cad'],default='e3d_benchmark')
parser.add_argument('--combo-read',type=int)
parser.add_argument('--combo-index',nargs=2,type=int)
parser.add_argument('--verify-name')
parser.add_argument('--wheel',nargs=3,type=float)
parser.add_argument('--bottom-at',nargs=2,type=float)
parser.add_argument('--key-at',nargs=3,type=float)
parser.add_argument('--scroll-position',type=int)
parser.add_argument('--drag-at',nargs=4,type=float)
args=parser.parse_args()
out=out.parent/args.output_root;out.mkdir(parents=True,exist_ok=True)
windows=[]
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.OpenProcess.restype=wintypes.HANDLE
kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
kernel.CloseHandle.argtypes=[wintypes.HANDLE]
def visit(hwnd,_):
    _,pid=win32process.GetWindowThreadProcessId(hwnd)
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return
    buffer=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(32768)
    ok=kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size))
    kernel.CloseHandle(handle)
    if not ok or Path(buffer.value).name.lower()!='e-3d master x64.exe':return
    title=win32gui.GetWindowText(hwnd)
    if not title:return
    windows.append(dict(hwnd=hwnd,pid=pid,title=title,rect=win32gui.GetWindowRect(hwnd),visible=win32gui.IsWindowVisible(hwnd)))
win32gui.EnumWindows(visit,None)
print(json.dumps(windows,ensure_ascii=False))
main=next((x for x in windows if x['title'].startswith('E-3D ') and x['rect'][2]-x['rect'][0]>200),None)
if main:
    win32gui.ShowWindow(main['hwnd'],win32con.SW_MAXIMIZE)
    try:win32gui.SetForegroundWindow(main['hwnd'])
    except Exception:pass
    time.sleep(.3)
if main and (args.controls or args.press_id or args.check or args.edit or args.tree_index is not None or args.combo_read is not None or args.combo_index or args.verify_name):
    controls=[]
    def read_control(hwnd,_):
        title=win32gui.GetWindowText(hwnd)
        if title or win32gui.GetClassName(hwnd) in ('Button','Edit','ComboBox','SysListView32','SysTreeView32'):
            controls.append(dict(hwnd=hwnd,title=title,cls=win32gui.GetClassName(hwnd),id=win32gui.GetDlgCtrlID(hwnd),visible=win32gui.IsWindowVisible(hwnd),enabled=win32gui.IsWindowEnabled(hwnd),rect=win32gui.GetWindowRect(hwnd)))
    roots=[main['hwnd']]
    def collect_root(hwnd,_):
        if win32process.GetWindowThreadProcessId(hwnd)[1]==main['pid'] and win32gui.IsWindowVisible(hwnd) and hwnd not in roots:roots.append(hwnd)
    win32gui.EnumWindows(collect_root,None)
    if args.dialog_title:
        roots=[x for x in roots if win32gui.GetWindowText(x)==args.dialog_title]
        if len(roots)!=1:raise RuntimeError('Expected one explicitly named dialog')
    for root in roots:win32gui.EnumChildWindows(root,read_control,None)
    (out/'controls.json').write_text(json.dumps(controls,ensure_ascii=False,indent=2),encoding='utf-8')
    print('visible control count',sum(x['visible'] for x in controls))
    if args.verify_name:
        candidates=[x for x in controls if x['visible'] and x['id']==991 and x['cls']=='Edit']
        if len(candidates)!=1:raise RuntimeError('Cannot uniquely identify selected model name')
        buffer=ctypes.create_unicode_buffer(2048)
        send=ctypes.windll.user32.SendMessageW;send.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_void_p]
        send(candidates[0]['hwnd'],13,2048,ctypes.cast(buffer,ctypes.c_void_p))
        actual=buffer.value.strip()
        (out/(args.label+'_identity.json')).write_text(json.dumps(dict(expected=args.verify_name,actual=actual,matched=actual==args.verify_name),ensure_ascii=False),encoding='utf-8')
        if actual!=args.verify_name:raise RuntimeError(f'Selected model is {actual}, expected {args.verify_name}')
    if args.combo_read is not None or args.combo_index:
        cid=args.combo_read if args.combo_read is not None else args.combo_index[0]
        candidates=[x for x in controls if x['visible'] and x['enabled'] and x['id']==cid and x['cls']=='ComboBox']
        if len(candidates)!=1:raise RuntimeError('Expected one specific combo')
        control=candidates[0]['hwnd']
        send=ctypes.windll.user32.SendMessageW;send.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_void_p]
        values=[]
        for index in range(win32gui.SendMessage(control,0x146,0,0)):
            buffer=ctypes.create_unicode_buffer(2048);send(control,0x148,index,ctypes.cast(buffer,ctypes.c_void_p));values.append(buffer.value)
        if args.combo_index:
            index=args.combo_index[1]
            if not 0<=index<len(values):raise RuntimeError('Unknown combo index')
            win32gui.SendMessage(control,0x14E,index,0)
            win32gui.SendMessage(win32gui.GetParent(control),win32con.WM_COMMAND,cid|(1<<16),control)
        record=dict(id=cid,selected=win32gui.SendMessage(control,0x147,0,0),values=values)
        (out/(args.label+'_combo.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(record,ensure_ascii=False))
    for cid,text in args.edit:
        candidates=[x for x in controls if x['visible'] and x['enabled'] and x['id']==int(cid) and x['cls']=='Edit']
        if len(candidates)!=1:raise RuntimeError(f'Ambiguous edit {cid}')
        if int(cid)==7252:
            destination=Path(text).resolve()
            if not destination.is_relative_to(out):raise RuntimeError('Export directory must be inside benchmark workspace')
            destination.mkdir(parents=True,exist_ok=True)
            text=str(destination)
        control=candidates[0]['hwnd']
        win32gui.SendMessage(control,win32con.WM_SETTEXT,0,text)
        win32gui.SendMessage(win32gui.GetParent(control),win32con.WM_COMMAND,int(cid)|(0x300<<16),control)
        print('set edit',cid,win32gui.GetWindowText(control))
    if args.tree_index is not None:
        candidates=[x for x in controls if x['visible'] and x['cls']=='SysTreeView32']
        if len(candidates)!=1:raise RuntimeError('Expected one tree in named dialog')
        tree=candidates[0]['hwnd']
        root_item=win32gui.SendMessage(tree,0x110A,0,0)
        item=win32gui.SendMessage(tree,0x110A,4,root_item)
        for _ in range(args.tree_index):item=win32gui.SendMessage(tree,0x110A,1,item)
        if not item:raise RuntimeError('Missing export model item')
        win32gui.SendMessage(tree,0x110B,9,item)
    for cid,value in args.check:
        candidates=[x for x in controls if x['visible'] and x['enabled'] and x['id']==cid and x['cls']=='Button']
        if len(candidates)!=1:raise RuntimeError(f'Ambiguous checkbox {cid}')
        control=candidates[0]['hwnd']
        if win32gui.SendMessage(control,win32con.BM_GETCHECK,0,0)!=value:
            win32gui.SendMessage(control,win32con.BM_CLICK,0,0)
        print('checkbox',cid,'state',win32gui.SendMessage(control,win32con.BM_GETCHECK,0,0))
    for cid in args.press_id:
        candidates=[x for x in controls if x['visible'] and x['enabled'] and x['id']==cid and x['cls']=='Button']
        if len(candidates)!=1:raise RuntimeError(f'Ambiguous button {cid}')
        control=candidates[0]['hwnd']
        if '确定导出' in win32gui.GetWindowText(control):raise RuntimeError('Paid export confirmation must be handled manually by the user')
        win32gui.PostMessage(win32gui.GetParent(control),win32con.WM_COMMAND,cid,control)
        time.sleep(1)
if main and (args.click or args.wheel or args.bottom_at or args.key_at or args.drag_at):
    hwnd=main['hwnd'];win32gui.ShowWindow(hwnd,win32con.SW_MAXIMIZE)
    try:win32gui.SetForegroundWindow(hwnd)
    except Exception:pass
    time.sleep(.3)
    width,height=win32gui.GetClientRect(hwnd)[2:]
    position_args=args.click or args.wheel or args.bottom_at or args.key_at or args.drag_at
    x,y=int(position_args[0]*width),int(position_args[1]*height)
    point=win32gui.ClientToScreen(hwnd,(x,y))
    if win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())[1]!=main['pid']:
        raise RuntimeError('E-3D is not foreground; refusing to click another application')
    target=win32gui.WindowFromPoint(point)
    if win32process.GetWindowThreadProcessId(target)[1]!=main['pid']:
        raise RuntimeError('Hit target belongs to another process; refusing action')
    for _ in range(8):
        local=win32gui.ScreenToClient(target,point)
        child=win32gui.ChildWindowFromPointEx(target,local,win32con.CWP_SKIPINVISIBLE|win32con.CWP_SKIPDISABLED)
        if not child or child==target:break
        target=child
    x,y=win32gui.ScreenToClient(target,point)
    print('target control',target,win32gui.GetClassName(target),x,y)
    position=(y<<16)|x
    if args.drag_at:
        end=win32gui.ClientToScreen(hwnd,(int(args.drag_at[2]*width),int(args.drag_at[3]*height)))
        if win32process.GetWindowThreadProcessId(win32gui.WindowFromPoint(end))[1]!=main['pid']:raise RuntimeError('Drag endpoint outside E-3D')
        previous=win32api.GetCursorPos()
        try:
            win32api.SetCursorPos(point);win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN,0,0,0,0)
            for i in range(1,6):
                win32api.SetCursorPos((point[0]+(end[0]-point[0])*i//5,point[1]+(end[1]-point[1])*i//5));time.sleep(.08)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,0,0,0,0);time.sleep(.3)
        finally:
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,0,0,0,0);win32api.SetCursorPos(previous)
    elif args.key_at:
        key=int(args.key_at[2])
        if key not in (win32con.VK_END,win32con.VK_UP,win32con.VK_DOWN,win32con.VK_HOME):raise RuntimeError('Only list-navigation keys allowed')
        owner_thread=win32process.GetWindowThreadProcessId(target)[0]
        caller_thread=win32api.GetCurrentThreadId()
        attached=ctypes.windll.user32.AttachThreadInput(caller_thread,owner_thread,True)
        try:
            win32gui.SetFocus(target)
            win32gui.SendMessage(target,win32con.WM_KEYDOWN,key,0)
            win32gui.SendMessage(target,win32con.WM_KEYUP,key,0)
        finally:
            if attached:ctypes.windll.user32.AttachThreadInput(caller_thread,owner_thread,False)
    elif args.bottom_at:
        control=target
        for _ in range(3):
            print('scroll control',control,win32gui.GetClassName(control))
            try:print('before',win32gui.GetScrollInfo(control,win32con.SB_VERT))
            except Exception:pass
            win32gui.SendMessage(control,win32con.WM_VSCROLL,win32con.SB_BOTTOM,0)
            if args.scroll_position is not None:
                try:
                    info=win32gui.GetScrollInfo(control,win32con.SB_VERT)
                    if info[2]>info[1]:
                        pos=max(info[1],min(args.scroll_position,info[2]))
                        win32gui.SendMessage(control,win32con.WM_VSCROLL,(pos<<16)|win32con.SB_THUMBTRACK,0)
                        win32gui.SendMessage(control,win32con.WM_VSCROLL,(pos<<16)|win32con.SB_THUMBPOSITION,0)
                except Exception:pass
            try:print('after',win32gui.GetScrollInfo(control,win32con.SB_VERT))
            except Exception:pass
            parent=win32gui.GetParent(control)
            if not parent or parent==main['hwnd']:break
            control=parent
    elif args.wheel:
        delta=int(args.wheel[2])*120
        previous=win32api.GetCursorPos()
        try:
            win32api.SetCursorPos(point)
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL,0,0,delta,0)
            time.sleep(.3)
        finally:win32api.SetCursorPos(previous)
    else:
        win32gui.PostMessage(target,win32con.WM_LBUTTONDOWN,win32con.MK_LBUTTON,position)
        win32gui.PostMessage(target,win32con.WM_LBUTTONUP,0,position)
    time.sleep(.7)
if args.file:
    dialogs=[]
    def dialog_visit(hwnd,_):
        _,pid=win32process.GetWindowThreadProcessId(hwnd)
        if main and pid==main['pid'] and win32gui.GetClassName(hwnd)=='#32770' and win32gui.IsWindowVisible(hwnd):dialogs.append(hwnd)
    win32gui.EnumWindows(dialog_visit,None)
    print('dialogs',[(x,win32gui.GetWindowText(x)) for x in dialogs])
    for hwnd in dialogs:
        if not any(word in win32gui.GetWindowText(hwnd) for word in ('导入','导出','打开','另存为','保存')):continue
        edits=[]
        win32gui.EnumChildWindows(hwnd,lambda child,_:edits.append(child) if win32gui.GetClassName(child)=='Edit' else None,None)
        if not edits:continue
        print('edit controls',[(x,win32gui.GetDlgCtrlID(x),win32gui.GetClassName(win32gui.GetParent(x))) for x in edits])
        filename=next((x for x in edits if win32gui.GetClassName(win32gui.GetParent(x)) in ('ComboBox','ComboBoxEx32')),None)
        if filename is None:raise RuntimeError('No unambiguous filename edit control')
        win32gui.SendMessage(filename,win32con.WM_SETTEXT,0,str(Path(args.file).resolve()))
        win32gui.PostMessage(hwnd,win32con.WM_COMMAND,1,0)
        time.sleep(1)
        break
for i,window in enumerate(windows):
    hwnd=window['hwnd']
    if not window['visible'] or not window['title'].startswith('E-3D '):continue
    if window['rect'][2]-window['rect'][0]<200:continue
    win32gui.ShowWindow(hwnd,win32con.SW_MAXIMIZE)
    try:win32gui.SetForegroundWindow(hwnd)
    except Exception:pass
    time.sleep(.4)
    ImageGrab.grab(bbox=win32gui.GetWindowRect(hwnd)).save(out/f'{args.label}_{i}.png')
(out/'windows.json').write_text(json.dumps(windows,ensure_ascii=False,indent=2),encoding='utf-8')
