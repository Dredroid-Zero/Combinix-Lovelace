import unittest

from services.solver import cfg_padrao, cfg_padrao_prof, solve_schedule


def disc(nome, codigo='D1', curso='Teste', semestre=1, carga=60):
    return {'nome': nome, 'codigo': codigo, 'curso': curso, 'semestre': semestre, 'carga_horaria': carga}


def solve(discs, cfg_discs=None, profs=None, cfg_profs=None, choques=None, avancadas=None):
    cfg_discs = cfg_discs if cfg_discs is not None else [cfg_padrao(d) for d in discs]
    profs = profs or []
    cfg_profs = cfg_profs if cfg_profs is not None else [cfg_padrao_prof() for _ in profs]
    return solve_schedule(discs, profs, cfg_discs, cfg_profs, choques or [], avancadas or {'estado_sabado': 'desativado', 'nivel_restricao': 3})


class SolverV2Tests(unittest.TestCase):
    def test_disciplina_usa_um_unico_professor_por_padrao(self):
        discs = [disc('Cálculo I')]
        cfgd = [cfg_padrao(discs[0])]
        cfgd[0]['aulas_semanais'] = 4
        profs = [{'nome': 'Ada'}, {'nome': 'Grace'}]
        cfgp = [
            {'disciplinas_internas': [0], 'carga_maxima': 8, 'disponibilidade': []},
            {'disciplinas_internas': [0], 'carga_maxima': 8, 'disponibilidade': []},
        ]
        *_grades, rel, _gcp = solve(discs, cfgd, profs, cfgp)
        self.assertEqual(rel['status_geracao'], 'sucesso')
        self.assertEqual(len(rel['professores_por_disciplina']['Cálculo I']), 1)
        self.assertEqual(rel['docencia_compartilhada_usada'], [])

    def test_divisao_entre_professores_exige_autorizacao_explicita(self):
        discs = [disc('Laboratório')]
        cfgd = [cfg_padrao(discs[0])]
        cfgd[0]['aulas_semanais'] = 4
        profs = [{'nome': 'Ada'}, {'nome': 'Grace'}]
        cfgp = [
            {'disciplinas_internas': [0], 'carga_maxima': 2, 'disponibilidade': []},
            {'disciplinas_internas': [0], 'carga_maxima': 2, 'disponibilidade': []},
        ]
        *_grades, rel, _gcp = solve(discs, cfgd, profs, cfgp)
        self.assertEqual(rel['status_geracao'], 'impossivel')
        codes = {d['codigo'] for d in rel['diagnosticos']}
        self.assertIn('professor_sem_carga_suficiente', codes)

        cfgd[0]['permitir_multiplos_professores'] = True
        *_grades, rel, _gcp = solve(discs, cfgd, profs, cfgp)
        self.assertEqual(rel['status_geracao'], 'sucesso')
        self.assertEqual(set(rel['professores_por_disciplina']['Laboratório']), {'Ada', 'Grace'})
        self.assertEqual(rel['docencia_compartilhada_usada'], ['Laboratório'])

    def test_fixacao_no_sabado_desativado_e_explicada(self):
        discs = [disc('Álgebra')]
        cfgd = [cfg_padrao(discs[0])]
        cfgd[0]['fixacoes'] = [['Sábado', '08:00-09:00']]
        *_grades, rel, _gcp = solve(discs, cfgd)
        self.assertEqual(rel['status_geracao'], 'impossivel')
        diagnostics = {d['codigo']: d for d in rel['diagnosticos']}
        self.assertIn('fixacao_sabado_desativado', diagnostics)
        self.assertTrue(any('Ative o sábado' in a for a in diagnostics['fixacao_sabado_desativado']['acoes']))

    def test_conflito_de_fixacoes_na_mesma_turma_e_explicado(self):
        discs = [disc('A', 'A'), disc('B', 'B')]
        cfgd = [cfg_padrao(d) for d in discs]
        for cfg in cfgd:
            cfg['fixacoes'] = [['Segunda', '08:00-09:00']]
        *_grades, rel, _gcp = solve(discs, cfgd)
        self.assertEqual(rel['status_geracao'], 'impossivel')
        self.assertIn('fixacoes_mesma_turma', {d['codigo'] for d in rel['diagnosticos']})

    def test_resultado_parcial_informa_disciplina_pendente(self):
        discs = [disc('A', 'A', 'Curso A', 1), disc('B', 'B', 'Curso B', 1)]
        cfgd = [cfg_padrao(d) for d in discs]
        for cfg in cfgd:
            cfg['aulas_semanais'] = 1
            cfg['fixacoes'] = [['Segunda', '08:00-09:00']]
        profs = [{'nome': 'Ada'}]
        cfgp = [{'disciplinas_internas': [0, 1], 'carga_maxima': 10, 'disponibilidade': []}]
        *_grades, rel, _gcp = solve(discs, cfgd, profs, cfgp)
        self.assertEqual(rel['status_geracao'], 'parcial')
        self.assertEqual(rel['disciplinas_alocadas'], 1)
        self.assertEqual(len(rel['disciplinas_nao_alocadas']), 1)
        self.assertIn('bloqueio_professor', {d['codigo'] for d in rel['diagnosticos']})

    def test_horario_sem_professor_e_previa_parcial(self):
        discs = [disc('Sem Docente')]
        *_grades, rel, _gcp = solve(discs)
        self.assertEqual(rel['status_geracao'], 'parcial')
        self.assertEqual(rel['disciplinas_sem_professor'], ['Sem Docente'])
        self.assertIn('disciplina_sem_professor_vinculado', {d['codigo'] for d in rel['diagnosticos']})

    def test_grade_combinada_acumula_turmas_simultaneas(self):
        discs = [disc('A', 'A', 'Curso A', 1), disc('B', 'B', 'Curso B', 1)]
        cfgd = [cfg_padrao(d) for d in discs]
        for cfg in cfgd:
            cfg['aulas_semanais'] = 1
            cfg['fixacoes'] = [['Segunda', '08:00-09:00']]
        gd, *_rest = solve(discs, cfgd)
        cell = gd['Segunda']['08:00-09:00']
        self.assertIn('Curso A', cell)
        self.assertIn('Curso B', cell)
        self.assertIn(' | ', cell)

    def test_professor_fixo_unico_sobrepoe_lista_automatica(self):
        discs = [disc('Cálculo Fixo')]
        cfgd = [cfg_padrao(discs[0])]
        cfgd[0]['aulas_semanais'] = 4
        cfgd[0]['professores_fixos'] = ['Grace']
        profs = [{'nome': 'Ada'}, {'nome': 'Grace'}]
        cfgp = [
            {'disciplinas_internas': [0], 'carga_alvo': 4, 'carga_maxima': 8, 'disponibilidade': []},
            {'disciplinas_internas': [], 'carga_alvo': 4, 'carga_maxima': 8, 'disponibilidade': []},
        ]
        *_grades, rel, _gcp = solve(discs, cfgd, profs, cfgp)
        self.assertEqual(rel['status_geracao'], 'sucesso')
        self.assertEqual(rel['professores_por_disciplina']['Cálculo Fixo'], ['Grace'])

    def test_dois_professores_fixos_devem_participar_da_disciplina(self):
        discs = [disc('Projeto Integrador')]
        cfgd = [cfg_padrao(discs[0])]
        cfgd[0]['aulas_semanais'] = 4
        cfgd[0]['professores_fixos'] = ['Ada', 'Grace']
        profs = [{'nome': 'Ada'}, {'nome': 'Grace'}]
        cfgp = [
            {'disciplinas_internas': [], 'carga_alvo': 2, 'carga_maxima': 4, 'disponibilidade': []},
            {'disciplinas_internas': [], 'carga_alvo': 2, 'carga_maxima': 4, 'disponibilidade': []},
        ]
        *_grades, rel, _gcp = solve(discs, cfgd, profs, cfgp)
        self.assertEqual(rel['status_geracao'], 'sucesso')
        self.assertEqual(set(rel['professores_por_disciplina']['Projeto Integrador']), {'Ada', 'Grace'})
        self.assertIn('Projeto Integrador', rel['docencia_compartilhada_usada'])

    def test_professores_fixos_acima_das_aulas_gera_diagnostico(self):
        discs = [disc('Seminário')]
        cfgd = [cfg_padrao(discs[0])]
        cfgd[0]['aulas_semanais'] = 1
        cfgd[0]['professores_fixos'] = ['Ada', 'Grace']
        profs = [{'nome': 'Ada'}, {'nome': 'Grace'}]
        cfgp = [cfg_padrao_prof(), cfg_padrao_prof()]
        *_grades, rel, _gcp = solve(discs, cfgd, profs, cfgp)
        self.assertEqual(rel['status_geracao'], 'impossivel')
        self.assertIn('professores_fixos_excedem_aulas', {d['codigo'] for d in rel['diagnosticos']})

    def test_cobertura_insuficiente_do_professor_e_explicada(self):
        discs = [disc('Única Disciplina')]
        cfgd = [cfg_padrao(discs[0])]
        cfgd[0]['aulas_semanais'] = 4
        profs = [{'nome': 'Ada'}]
        cfgp = [{'disciplinas_internas': [0], 'carga_alvo': 20, 'carga_maxima': 20, 'disponibilidade': []}]
        *_grades, rel, _gcp = solve(discs, cfgd, profs, cfgp)
        self.assertIn('professor_cobertura_insuficiente', {d['codigo'] for d in rel['diagnosticos']})
        cobertura = rel['cobertura_professores']['Ada']
        self.assertEqual(cobertura['horas_disponiveis'], 4)
        self.assertEqual(cobertura['faltam_horas'], 16)
        self.assertFalse(cobertura['cobertura_suficiente'])

    def test_disciplina_externa_usa_professor_externo_sem_vinculo_interno(self):
        discs = [disc('Educação Ambiental')]
        cfgd = [cfg_padrao(discs[0])]
        cfgd[0]['tipo'] = 'externa'
        cfgd[0]['aulas_semanais'] = 2
        *_grades, rel, grades_com_prof = solve(discs, cfgd, profs=[], cfg_profs=[])
        self.assertEqual(rel['status_geracao'], 'sucesso')
        self.assertEqual(rel['disciplinas_sem_professor'], [])
        self.assertEqual(rel['disciplinas_externas'], ['Educação Ambiental'])
        self.assertEqual(rel['professores_por_disciplina']['Educação Ambiental'], ['Professor externo'])
        self.assertIn('Professor externo', str(grades_com_prof))
        self.assertTrue(rel['carga_por_professor']['Professor externo']['externo'])

    def test_disciplina_externa_nao_consumira_carga_do_professor_interno(self):
        discs = [disc('Externa'), disc('Interna', codigo='D2', curso='Outro')]
        cfgd = [cfg_padrao(d) for d in discs]
        cfgd[0]['tipo'] = 'externa'
        cfgd[0]['aulas_semanais'] = 4
        cfgd[1]['aulas_semanais'] = 4
        profs = [{'nome': 'Ada'}]
        cfgp = [{'disciplinas_internas': [0, 1], 'carga_alvo': 4, 'carga_maxima': 4, 'disponibilidade': []}]
        *_grades, rel, _gcp = solve(discs, cfgd, profs, cfgp)
        self.assertEqual(rel['status_geracao'], 'sucesso')
        self.assertEqual(rel['carga_por_professor']['Ada']['alocada'], 4)
        self.assertEqual(rel['carga_por_professor']['Professor externo']['alocada'], 4)

    def test_sementes_de_variacao_podem_gerar_assinaturas_distintas(self):
        discs = [disc('Flexível')]
        cfgd = [cfg_padrao(discs[0])]
        cfgd[0]['tipo'] = 'externa'
        cfgd[0]['aulas_semanais'] = 1
        assinaturas = set()
        for seed in range(5):
            *_grades, rel, _gcp = solve_schedule(discs, [], cfgd, [], [], {'estado_sabado':'desativado','nivel_restricao':3}, variant_seed=seed)
            assinaturas.add(rel['assinatura_grade'])
        self.assertGreater(len(assinaturas), 1)


if __name__ == '__main__':
    unittest.main()
