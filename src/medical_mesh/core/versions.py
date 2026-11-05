from pathlib import Path
import json
from datetime import datetime, timezone
from ..io.mesh_io import save_mesh, load_mesh
from .model import jsonable


class VersionStore:
    """Persistent immutable snapshots and current-version pointer with callbacks."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.listeners = []
        self.current_version = None
        if (self.root / "current.json").exists():
            self.current_version = json.loads((self.root / "current.json").read_text(encoding="utf-8"))["version"]

    def subscribe(self, callback):
        self.listeners.append(callback)

    def commit(self, asset, result=None):
        path = self.root / (asset.version + ".npz")
        if path.exists():
            previous = load_mesh(path)
            if previous.geometry_hash() != asset.geometry_hash() or previous.metadata() != asset.metadata():
                raise ValueError("Version ID already exists with different data")
        else:
            save_mesh(asset, path)
        if result is not None:
            data = result.to_dict() if hasattr(result, "to_dict") else result
            (self.root / (asset.version + ".result.json")).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._select(asset.version, "commit")
        return path

    def _select(self, version, operation):
        self.current_version = version
        temporary = self.root / "current.tmp"
        temporary.write_text(json.dumps({"version": version}), encoding="utf-8")
        temporary.replace(self.root / "current.json")
        with (self.root / "events.jsonl").open("a", encoding="utf-8") as out:
            out.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "operation": operation,
                                  "version": version}, ensure_ascii=False) + "\n")
        for callback in self.listeners:
            callback(version)  # Consumer must drop stale face highlights.

    def get(self, version=None):
        version = version or self.current_version
        if not version or not all(c in "0123456789abcdef" for c in version):
            raise ValueError("Invalid version ID")
        return load_mesh(self.root / (version + ".npz"))

    def rollback(self, version=None):
        target = version or self.get().parent_version
        if target is None:
            raise ValueError("Original version has no parent")
        asset = self.get(target)
        self._select(asset.version, "rollback")
        return asset

    def redo(self,version):
        asset=self.get(version)
        if asset.parent_version!=self.current_version:raise ValueError('Redo target is not a child of the current version')
        self._select(asset.version,'redo')
        return asset
