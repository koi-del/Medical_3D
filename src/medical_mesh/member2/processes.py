"""Cancel only the task-owned process tree on Windows."""
import os
import subprocess


def stop_windows_tree(pid):
    if os.name!='nt' or int(pid)<=0 or int(pid)==os.getpid():raise ValueError('Invalid task PID')
    return subprocess.run(['taskkill','/PID',str(int(pid)),'/T','/F'],stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
