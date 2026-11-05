"""Compatibility import for the shared experiment report generator."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"src"))
from medical_mesh.experiments.patella_report import *
