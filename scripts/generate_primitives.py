import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import json
from medical_mesh.data.synthetic import sphere,open_tube,tetrahedron,two_components,bowtie_vertex,intersecting_triangles,inject_defects
from medical_mesh import save_mesh,detect_defects


def main():
    root=Path(__file__).resolve().parents[1]/"data"
    references={"sphere":sphere(),"open_tube":open_tube(),"tetrahedron":tetrahedron(),
                "two_components":two_components(),"bowtie_vertex":bowtie_vertex(),"self_intersection":intersecting_triangles(),
                "translated_asymmetric":tetrahedron((10,20,30))}
    for name,mesh in references.items():
        save_mesh(mesh,root/"reference"/(name+".npz"))
        save_mesh(mesh,root/"reference"/(name+".stl"))
    for kind in ("hole","duplicate","reverse_duplicate","degenerate","flip","non_manifold_edge","noise"):
        damaged,record=inject_defects(references["sphere"],kind)
        record["observed_diagnosis"]=detect_defects(damaged).to_dict()
        save_mesh(damaged,root/"damaged"/(kind+".npz"))
        save_mesh(damaged,root/"damaged"/(kind+".stl"))
        (root/"damaged"/(kind+".json")).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Generated 7 reference and 7 reproducible damaged meshes")


if __name__=="__main__": main()
