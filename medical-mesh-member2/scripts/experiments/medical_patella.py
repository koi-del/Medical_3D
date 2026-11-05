"""CLI entry point for the shared real MRI patella workflow."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from medical_mesh.experiments.patella import *

if __name__ == "__main__":
    main()
