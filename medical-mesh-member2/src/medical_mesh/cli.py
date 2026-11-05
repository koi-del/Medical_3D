import argparse
import json
from pathlib import Path
from uuid import uuid4

from medical_mesh.core.model import load_preview, save_asset
from medical_mesh.jobs.worker import dispatch


def main(argv=None):
    parser = argparse.ArgumentParser(description="成员2医学网格处理原型")
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fixtures", help="生成可解析的合成开发样本")
    f.add_argument("--output", default="data/generated")
    p = sub.add_parser("probe")
    p.add_argument("--out")
    p = sub.add_parser("evaluate")
    p.add_argument("--reference", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--samples", type=int, default=10000)
    p.add_argument("--out")
    p = sub.add_parser("optimize")
    p.add_argument("--input", required=True)
    p.add_argument("--operation", choices=["qem", "laplacian", "taubin", "remesh"], default="qem")
    p.add_argument("--ratio", type=float, default=.5)
    p.add_argument("--iterations", type=int, default=5)
    p.add_argument("--edge", type=float, default=1.)
    p.add_argument("--samples", type=int, default=10000)
    p.add_argument("--final-samples", type=int, default=50000)
    p.add_argument("--search", action="store_true")
    p.add_argument("--provider", help="成员1适配函数 module:function")
    p.add_argument("--limits", help="JSON limit file")
    p.add_argument("--out")
    p = sub.add_parser("convert")
    p.add_argument("--input", required=True)
    p.add_argument("--target", required=True, choices=["stl", "step", "igs"])
    p.add_argument("--unit", choices=["mm", "cm", "m"])
    p.add_argument("--config")
    p.add_argument("--out")
    p = sub.add_parser("import-preview")
    p.add_argument("--input", required=True)
    p.add_argument("--unit", choices=["mm", "cm", "m"])
    p.add_argument("--output", required=True)
    p = sub.add_parser("report")
    p.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    if args.command == "fixtures":
        from medical_mesh.fixtures import generate_fixtures
        print(json.dumps(generate_fixtures(args.output), ensure_ascii=False, indent=2))
        return 0
    if args.command == "import-preview":
        path = save_asset(load_preview(args.input, args.unit), args.output)
        print(path)
        return 0
    if args.command == "report":
        from medical_mesh.reporting import render_report
        root = Path(args.run_dir)
        print(render_report(json.loads((root/"result.json").read_text()), root))
        return 0
    directory = Path(args.out or f"runs/{args.command}_{uuid4().hex[:10]}").resolve()
    if (directory / "result.json").exists():
        parser.error("output already contains a result; choose a fresh run directory")
    request = {"operation": args.command, "output_dir": str(directory), "run_id": directory.name}
    if args.command == "evaluate":
        request.update(input_path=str(Path(args.reference).resolve()), candidate_path=str(Path(args.candidate).resolve()), samples=args.samples)
    elif args.command == "optimize":
        configs = [{"operation": args.operation, "keep_ratio": args.ratio, "iterations": args.iterations, "target_edge_length": args.edge}]
        if args.search:
            configs = [{"operation": "qem", "keep_ratio": ratio, "smooth_iterations": n} for ratio in (.8, .5, .3) for n in (0, 5, 10)]
        request.update(input_path=str(Path(args.input).resolve()), configs=configs, samples=args.samples,
                       final_samples=args.final_samples, provider=args.provider)
        if args.limits:
            request["limits"] = json.loads(Path(args.limits).read_text())
    elif args.command == "convert":
        request.update(input_path=str(Path(args.input).resolve()), target_format=args.target, unit=args.unit,
                       cad_config=json.loads(Path(args.config).read_text()) if args.config else {})
    result = dispatch(request, lambda stage, message: print(f"[{stage}] {message}", flush=True))
    print(json.dumps({"status": result["status"], "decision": result.get("decision"),
                      "quality_status": result.get("quality_status"), "report": str(directory/"report.html")}, ensure_ascii=False))
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
