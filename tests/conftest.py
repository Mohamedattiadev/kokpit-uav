"""pytest ortak kurulum: onboard/ ve simulation/ modüllerini path'e ekle, SIMULATION aç."""
import os
import sys

os.environ.setdefault("KOKPIT_SIM", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "onboard"))
sys.path.insert(0, os.path.join(ROOT, "simulation"))
