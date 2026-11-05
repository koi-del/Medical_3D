import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import argparse,json
from medical_mesh import load_mesh,save_mesh
from medical_mesh.data.synthetic import inject_defects

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("input");p.add_argument("output")
    p.add_argument("--kind",required=True,choices=["hole","duplicate","reverse_duplicate","degenerate","flip","non_manifold_edge","noise"])
    p.add_argument("--seed",type=int,default=20261016);p.add_argument("--count",type=int,default=1)
    args=p.parse_args()
    result,record=inject_defects(load_mesh(args.input),args.kind,seed=args.seed,count=args.count)
    save_mesh(result,args.output)
    Path(args.output+".defects.json").write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
