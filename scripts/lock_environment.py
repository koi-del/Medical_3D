"""Pin the actually imported dependency closure, excluding unrelated user packages."""
import importlib.metadata as md
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
todo=["numpy","trimesh","pymeshlab","PySide6","pyvista","pyvistaqt","pytest"]
versions={}
while todo:
    name=canonicalize_name(todo.pop())
    if name in versions:continue
    dist=md.distribution(name);versions[name]=dist.version
    for requirement in dist.requires or []:
        r=Requirement(requirement)
        if r.marker is None or r.marker.evaluate({"extra":""}):todo.append(r.name)
path=Path(__file__).resolve().parents[1]/"requirements-lock-windows.txt"
path.write_text("# Python 3.11 / Windows AMD64; actual verified dependency closure\n"+
                "\n".join(f"{name}=={version}" for name,version in sorted(versions.items()))+"\n",encoding="utf-8")
print("Pinned",len(versions),"packages")
