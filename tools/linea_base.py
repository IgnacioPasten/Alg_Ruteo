"""Línea base: hashes de A1-A4 para verificar que el refactor no cambia resultados."""
import hashlib, json
from core.contracts import ROOT, canonical
from core.aerial_data import build

config = json.loads((ROOT/'config/proyecto.json').read_text(encoding='utf-8'))
doc, context = build(config)
out = {k: dict(registros=len(context['records'][k]),
               sha256=hashlib.sha256(canonical(context['records'][k])).hexdigest())
       for k in ['A1', 'A2', 'A3', 'A4']}
out['context_sha256'] = doc['lineage']['context_sha256']
print(json.dumps(out, indent=2))
