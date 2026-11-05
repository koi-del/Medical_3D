"""User decisions follow boundary geometry, never transient boundary indices."""
import hashlib
import json
from pathlib import Path

ROLES = {'uncertain': '待判断（不补洞）', 'natural': '天然开口（保留）',
         'repair_target': '待补孔洞'}


class BoundaryRoles:
    def __init__(self, path):
        self.path = Path(path)
        self.decisions = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}

    @staticmethod
    def key(asset, boundary):
        edges = sorted(tuple(sorted(tuple(float(x) for x in asset.vertices[i]) for i in edge))
                       for edge in boundary['edges'])
        return asset.asset_id + ':' + hashlib.sha256(repr(edges).encode()).hexdigest()

    def mapping(self, asset, diagnosis):
        return {str(b['id']): self.decisions.get(self.key(asset, b), 'uncertain')
                for b in diagnosis['boundaries']}

    def mark(self, asset, boundaries, role):
        if role not in ROLES:
            raise ValueError('Unknown boundary role')
        if role == 'repair_target' and any(b['kind'] != 'simple_loop' for b in boundaries):
            raise ValueError('Only a simple loop can be a repair target')
        for boundary in boundaries:
            self.decisions[self.key(asset, boundary)] = role
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.decisions, ensure_ascii=False, indent=2), encoding='utf-8')
