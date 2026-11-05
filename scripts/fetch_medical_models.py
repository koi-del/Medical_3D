"""Fetch redistributable BodyParts3D 3.0 anatomy; retain original bytes/licenses."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import urllib.request
import csv
import hashlib
import json
from datetime import date
from medical_mesh import load_mesh, detect_defects

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://raw.githubusercontent.com/Kevin-Mattheus-Moerman/BodyParts3D/main/assets/BodyParts3D_data/"


def main():
    destination = ROOT / "data" / "medical"
    destination.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for filename in ("parts_list_e.txt", "LICENSE_content", "README_e.html", "coordinate_system.png"):
        path = destination / filename
        if not path.exists():
            path.write_bytes(opener.open(BASE+filename, timeout=60).read())
    rows = []
    listing = (destination / "parts_list_e.txt").read_text(encoding="utf-8-sig")
    selected = []
    for line in listing.splitlines():
        fields = line.split("\t")
        if len(fields) >= 2 and fields[1].strip().lower() in ("liver", "right kidney", "right femur"):
            selected.append((fields[0].strip(), fields[1].strip()))
    if len(selected) != 3:
        raise RuntimeError("Could not resolve all 3 organs: " + repr(selected))
    for identifier, name in selected:
        filename = identifier + ".stl"
        path = destination / filename
        url = BASE+"stl/"+filename
        if not path.exists():
            path.write_bytes(opener.open(url, timeout=90).read())
        mesh = load_mesh(path)
        diagnosis = detect_defects(mesh)
        (destination / (identifier + ".diagnosis.json")).write_text(json.dumps(diagnosis.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        rows.append({"asset_id": identifier, "group_id": "BodyParts3D_3.0_single_male", "path": str(path.relative_to(ROOT)),
                     "source_url": url, "source_dataset": "BodyParts3D 3.0 (20110915), DBCLS; STL mirror Kevin Moerman",
                     "anatomy": name, "license_note": "CC BY-SA 2.1 Japan; see data/medical/LICENSE_content",
                     "download_date": "2026-10-16", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "source_format": "STL", "unit_status": "unknown", "vertex_count": len(mesh.vertices),
                     "face_count": len(mesh.faces), "expected_components": "unannotated",
                     "observed_components": diagnosis.metrics["component_count"],
                     "open_boundary_note": "Observed loops: " + str(diagnosis.metrics["boundary_loop_count"]),
                     "reference_qualification": "complex_unverified", "subset": "external_validation"})
        print(name, len(mesh.faces), "faces")
    manifest = ROOT / "data" / "manifest.csv"
    with manifest.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
