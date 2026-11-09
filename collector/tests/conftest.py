import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Os testes usam a base SINTÉTICA de ofertas (a base real é privada e fica fora do repositório).
# test_ofertas_casos.py usa a base real quando disponível (ver o próprio arquivo).
FIXTURE_OFERTAS = Path(__file__).resolve().parent / "fixtures" / "ofertas_sinteticas.json"
os.environ["RADAR_OFERTAS_FILE"] = str(FIXTURE_OFERTAS)
os.environ.pop("RADAR_OFERTAS_JSON", None)
