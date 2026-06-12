"""Smoke test opcional dos catálogos reais incluídos no projeto.

Execute separadamente porque analisa catálogos maiores e pode levar alguns segundos.
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.solver import cfg_padrao, solve_schedule
COURSES = ['Matematica', 'Fisica', 'Biologia', 'Quimica']

for course in COURSES:
    items = json.loads((ROOT / 'disciplinas' / f'{course}.json').read_text(encoding='utf-8'))
    # Catálogos são sanitizados pelo app em uso normal. Aqui basta adicionar curso ausente.
    discs = []
    for raw in items:
        d = dict(raw)
        d.setdefault('curso', course)
        d.setdefault('semestre', 1)
        d.setdefault('carga_horaria', 60)
        discs.append(d)
    # Um docente exclusivo por disciplina evita pendências docentes neste smoke test
    # e permite verificar o status final completo de cada catálogo.
    profs = [{'nome': f'Professor teste {i+1}'} for i in range(len(discs))]
    cfg_profs = [{'disciplinas_internas': [i], 'carga_maxima': 20, 'disponibilidade': []} for i in range(len(discs))]
    start = time.perf_counter()
    *_grades, report, _gcp = solve_schedule(
        discs, profs, [cfg_padrao(d) for d in discs], cfg_profs, [],
        {'estado_sabado': 'desativado', 'nivel_restricao': 3},
    )
    elapsed = time.perf_counter() - start
    print(f'{course:12} status={report["status_geracao"]:10} disciplinas={report["disciplinas_alocadas"]}/{report["total_disciplinas"]} tempo={elapsed:.2f}s')
    if report['status_geracao'] != 'sucesso':
        raise SystemExit(f'Falha no catálogo {course}: {report["disciplinas_nao_alocadas"]}')
