"""Prepare identical STL inputs and honest comparison rows for manual E-3D runs."""
import sys,csv,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from medical_mesh import load_mesh,detect_defects

CASES=[('hole','damaged/hole.stl','reference/sphere.npz','只补人工缺面，保留其他结构',0,1),
       ('duplicate','damaged/duplicate.stl','reference/sphere.npz','清理重复面',0,1),
       ('degenerate','damaged/degenerate.stl','reference/sphere.npz','清理零面积面',0,1),
       ('flip','damaged/flip.stl','reference/sphere.npz','局部方向一致化',0,1),
       ('non_manifold_edge','damaged/non_manifold_edge.stl','reference/sphere.npz','去除附加面，保留球面',0,1),
       ('open_tube','reference/open_tube.stl','reference/open_tube.npz','保留两个天然开口，不执行全自动封口',2,1),
       ('two_components','reference/two_components.stl','reference/two_components.npz','保留两个分量，不仅保留最大块',0,2),
       ('liver','medical/FMA7197.stl','medical/FMA7197.stl','原样导入导出，核对位置与尺寸；单位未知',0,1)]


def main():
    out=ROOT/'results/e3d_benchmark';(out/'inputs').mkdir(parents=True,exist_ok=True);(out/'e3d_outputs').mkdir(exist_ok=True)
    rows=[]
    for name,source,reference,task,loops,components in CASES:
        target=out/'inputs'/(name+'.stl');shutil.copyfile(ROOT/'data'/source,target)
        d=detect_defects(load_mesh(target))
        rows.append(dict(case=name,input=str(target.relative_to(ROOT)),task=task,
                         expected_loops=loops,expected_components=components,
                         expected_export=f'e3d_outputs/{name}.stl',
                         input_face_count=d.metrics['face_count'],e3d_execution_status='not_executed'))
    with (out/'cases.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('Prepared',len(rows),'same-input cases; no E-3D result is fabricated')


if __name__=='__main__':main()
