"""One-time namespace migration; refuse overwriting an already integrated module."""
import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'medical-mesh-member2/src/medical_mesh'
TARGET=ROOT/'src/medical_mesh/member2'
ALLOWED={'core','evaluation','optimization','cad','jobs','reporting','ui'}
SKIP={'ui/patella_demo.py'}
DEMO_METHODS={'load_demo','run_patella_demo','on_demo_event','load_demo_optimization',
    'show_demo_comparison','show_demo_conversion','open_demo_report','apply_demo_result','replay_patella_demo'}


class StripDemo(ast.NodeTransformer):
    def visit_FunctionDef(self,node):
        if node.name in DEMO_METHODS:return None
        return self.generic_visit(node)

    def visit_If(self,node):
        test=ast.unparse(node.test)
        if 'patella_demo' in test or 'demo_result.json' in test:
            return [self.visit(statement) for statement in node.orelse] or None
        return self.generic_visit(node)

    def visit_ImportFrom(self,node):
        if node.module and node.module.endswith('patella_demo'):return None
        return node

    def visit_Expr(self,node):
        value=ast.unparse(node)
        if any(x in value for x in ('self.demo','self.on_demo_event','self.run_patella_demo',"'integration'",'pending_layout.')):return None
        return self.generic_visit(node)

    def visit_Assign(self,node):
        targets=' '.join(ast.unparse(t) for t in node.targets)
        if any(x in targets for x in ('self.demo','pending','pending_layout')):return None
        return self.generic_visit(node)


def main():
    if TARGET.exists():raise RuntimeError('集成目录已存在，拒绝覆盖后续适配修改')
    records=[]
    for path in sorted(SOURCE.rglob('*.py')):
        relative=path.relative_to(SOURCE)
        if '__pycache__' in relative.parts:continue
        if len(relative.parts)>1 and relative.parts[0] not in ALLOWED:continue
        if len(relative.parts)==1 and path.name not in ('__init__.py','fixtures.py'):continue
        if relative.as_posix() in SKIP:continue
        source=path.read_text(encoding='utf-8')
        migrated=source.replace('medical_mesh.','medical_mesh.member2.')
        if relative.as_posix() in ('ui/main_window.py','jobs/worker.py','jobs/qt_manager.py'):
            tree=StripDemo().visit(ast.parse(migrated));ast.fix_missing_locations(tree)
            migrated=ast.unparse(tree)+'\n'
        destination=TARGET/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(migrated,encoding='utf-8')
        records.append(dict(source=str(path.relative_to(ROOT)),target=str(destination.relative_to(ROOT)),
            source_sha256=hashlib.sha256(source.encode()).hexdigest()))
    out=ROOT/'results/member2_merge';out.mkdir(exist_ok=True)
    (out/'import_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Imported modules:',len(records),'Automatic demonstration excluded')


if __name__=='__main__':main()
