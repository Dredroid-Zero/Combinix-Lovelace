import io
import json
import os
import unittest

import app as combinix
from persistence import load_state, reset_state, save_state


class AppRoutesTests(unittest.TestCase):
    def setUp(self):
        combinix.app.config.update(TESTING=True)
        reset_state('local')
        combinix.RESULTADOS_STORE.clear()
        try:
            os.remove(combinix.RESULTADOS_FILE)
        except FileNotFoundError:
            pass
        self.client = combinix.app.test_client()
        self.client.get('/')
        with self.client.session_transaction() as sess:
            self.csrf = sess['_csrf_token']
        self.headers = {'X-CSRF-Token': self.csrf}

    def tearDown(self):
        # Não depende da validade do cookie para limpar o disco de teste.
        reset_state('local')
        combinix.RESULTADOS_STORE.clear()
        try:
            os.remove(combinix.RESULTADOS_FILE)
        except FileNotFoundError:
            pass

    def test_paginas_principais_abrem(self):
        for route in ['/', '/config', '/generate', '/api/status', '/api/cursos/disciplinas', '/api/cursos/professores']:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

    def test_post_sem_csrf_e_bloqueado(self):
        response = self.client.post('/reset')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json['status'], 'erro')

    def test_path_traversal_de_catalogo_e_bloqueado(self):
        response = self.client.get('/api/disciplinas/..%2Fapp')
        self.assertEqual(response.status_code, 404)

    def test_formulario_manual_invalido_retorna_400(self):
        response = self.client.post('/adicionar_professor_manual', data={'nome': ''}, headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn('nome', response.json['mensagem'].lower())

    def test_backup_invalido_e_rejeitado(self):
        data = {'file': (io.BytesIO(b'{nao-json'), 'backup.json')}
        response = self.client.post('/import', data=data, headers=self.headers, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json['status'], 'erro')

    def test_backup_com_slot_invalido_e_rejeitado(self):
        backup = {
            'disciplinas_selecionadas': [{'nome': 'Teste', 'codigo': 'T', 'curso': 'C', 'semestre': 1, 'carga_horaria': 60}],
            'professores_selecionados': [],
            'config_disciplinas': [{'aulas_semanais': 2, 'fixacoes': [['Domingo', '08:00-09:00']]}],
            'config_professores': [],
        }
        data = {'file': (io.BytesIO(json.dumps(backup).encode()), 'backup.json')}
        response = self.client.post('/import', data=data, headers=self.headers, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 400)
        self.assertIn('inválido', response.json['mensagem'])

    def test_salvar_selecoes_atomico_persiste_as_duas_listas(self):
        discs = [
            {'nome': 'Cálculo I', 'codigo': 'MAT01', 'curso': 'Matemática', 'semestre': 1, 'carga_horaria': 60},
            {'nome': 'Álgebra', 'codigo': 'MAT02', 'curso': 'Matemática', 'semestre': 1, 'carga_horaria': 60},
        ]
        profs = [{'nome': 'Ada'}, {'nome': 'Grace'}]
        response = self.client.post('/salvar_selecoes', json={
            'disciplinas': discs,
            'professores': profs,
        }, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['disciplinas_salvas'], 2)
        self.assertEqual(response.json['professores_salvos'], 2)
        state = load_state('local')
        self.assertEqual([d['nome'] for d in state['disciplinas_selecionadas']], ['Cálculo I', 'Álgebra'])
        self.assertEqual([p['nome'] for p in state['professores_selecionados']], ['Ada', 'Grace'])

    def test_cookie_permanece_pequeno_com_catalogo_grande(self):
        discs = [
            {'nome': f'Disciplina {i}', 'codigo': f'D{i}', 'curso': 'Teste', 'semestre': (i % 10) + 1, 'carga_horaria': 60}
            for i in range(120)
        ]
        profs = [{'nome': f'Professor {i}'} for i in range(120)]
        response = self.client.post('/salvar_selecoes', json={
            'disciplinas': discs,
            'professores': profs,
        }, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        set_cookie_headers = response.headers.getlist('Set-Cookie')
        self.assertTrue(set_cookie_headers)
        self.assertLess(max(len(value) for value in set_cookie_headers), 1000)
        state = load_state('local')
        self.assertEqual(len(state['disciplinas_selecionadas']), 120)
        self.assertEqual(len(state['professores_selecionados']), 120)

    def test_nova_sessao_recupera_selecoes_do_disco(self):
        self.client.post('/salvar_selecoes', json={
            'disciplinas': [{'nome': 'Persistente', 'codigo': 'P1', 'curso': 'C', 'semestre': 1, 'carga_horaria': 60}],
            'professores': [{'nome': 'Docente Persistente'}],
        }, headers=self.headers)
        outro_cliente = combinix.app.test_client()
        response = outro_cliente.get('/config')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Persistente', response.data)
        self.assertIn(b'Docente Persistente', response.data)
        with outro_cliente.session_transaction() as sess:
            self.assertNotIn('disciplinas_selecionadas', sess)
            self.assertNotIn('professores_selecionados', sess)

    def test_geracao_parcial_e_export_completo(self):
        discs = [
            {'nome':'A','codigo':'A','curso':'Curso A','semestre':1,'carga_horaria':60},
            {'nome':'B','codigo':'B','curso':'Curso B','semestre':1,'carga_horaria':60},
        ]
        cfgd = []
        for d in discs:
            cfg = combinix._cfg_padrao(d)
            cfg.update({'aulas_semanais':1,'fixacoes':[['Segunda','08:00-09:00']]})
            cfgd.append(cfg)
        save_state({
            'disciplinas_selecionadas': discs,
            'config_disciplinas': cfgd,
            'professores_selecionados': [{'nome':'Ada'}],
            'config_professores': [{'disciplinas_internas':[0,1],'carga_maxima':10,'disponibilidade':[]}],
            'grupos_choque': [],
            'config_avancadas': {'estado_sabado':'desativado','nivel_restricao':3},
            'tema': 'claro',
            'resultado_token': '',
        }, 'local')
        response = self.client.post('/iniciar_geracao', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['status'], 'parcial')
        exported = self.client.get('/export')
        self.assertEqual(exported.status_code, 200)
        payload = json.loads(exported.data)
        self.assertIn('resultado_grades_com_prof', payload)
        self.assertIn('resultado_relatorio', payload)
        excel = self.client.get('/download_excel')
        self.assertEqual(excel.status_code, 200)
        self.assertIn('spreadsheetml', excel.content_type)

    def test_reserva_docente_remove_disciplina_dos_demais_professores(self):
        discs = [{'nome':'Cálculo','codigo':'C1','curso':'Teste','semestre':1,'carga_horaria':60}]
        profs = [{'nome':'Ada'}, {'nome':'Grace'}]
        self.client.post('/salvar_selecoes', json={'disciplinas':discs,'professores':profs}, headers=self.headers)
        response = self.client.post('/salvar_todas_disciplinas', json={'configs':[{
            'idx':0,'tipo':'interna','aulas_semanais':4,'semestre_oferta':1,
            'professores_fixos':['Ada'],'permitir_multiplos_professores':False,
        }]}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        state = load_state('local')
        self.assertEqual(state['config_disciplinas'][0]['professores_fixos'], ['Ada'])
        self.assertEqual(state['config_professores'][0]['disciplinas_internas'], [0])
        self.assertEqual(state['config_professores'][1]['disciplinas_internas'], [])

    def test_backup_com_professor_fixo_desconhecido_remove_reserva_obsoleta(self):
        backup = {
            'disciplinas_selecionadas': [{'nome':'Teste','codigo':'T','curso':'C','semestre':1,'carga_horaria':60}],
            'professores_selecionados': [{'nome':'Ada'}],
            'config_disciplinas': [{'aulas_semanais':2,'professores_fixos':['Professor removido']}],
            'config_professores': [{'disciplinas_internas':[],'carga_alvo':20,'carga_maxima':20,'disponibilidade':[]}],
        }
        data = {'file': (io.BytesIO(json.dumps(backup).encode()), 'backup.json')}
        response = self.client.post('/import', data=data, headers=self.headers, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        state = load_state('local')
        self.assertEqual(state['config_disciplinas'][0]['professores_fixos'], [])

    def test_remover_disciplina_preserva_indices_dos_vinculos_restantes(self):
        discs = [
            {'nome':'A','codigo':'A','curso':'C','semestre':1,'carga_horaria':60},
            {'nome':'B','codigo':'B','curso':'C','semestre':1,'carga_horaria':60},
        ]
        save_state({
            'disciplinas_selecionadas': discs,
            'config_disciplinas': [combinix._cfg_padrao(d) for d in discs],
            'professores_selecionados': [{'nome':'Ada'}],
            'config_professores': [{'disciplinas_internas':[1],'carga_alvo':4,'carga_maxima':20,'disponibilidade':[]}],
            'grupos_choque': [], 'config_avancadas': {'estado_sabado':'desativado','nivel_restricao':3},
        }, 'local')
        response = self.client.post('/remover_disciplina_config', json={'idx':0}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        state=load_state('local')
        self.assertEqual([d['nome'] for d in state['disciplinas_selecionadas']], ['B'])
        self.assertEqual(state['config_professores'][0]['disciplinas_internas'], [0])

    def test_disciplina_externa_remove_vinculo_interno_e_gera_professor_externo(self):
        discs = [{'nome':'Educação Ambiental','codigo':'EA','curso':'Teste','semestre':1,'carga_horaria':30}]
        profs = [{'nome':'Ada'}]
        self.client.post('/salvar_selecoes', json={'disciplinas':discs,'professores':profs}, headers=self.headers)
        self.client.post('/salvar_todas_professores', json={'configs':[{'idx':0,'disciplinas_internas':[0],'carga_alvo':0,'carga_maxima':20,'disponibilidade':[]}]}, headers=self.headers)
        response = self.client.post('/salvar_todas_disciplinas', json={'configs':[{'idx':0,'tipo':'externa','aulas_semanais':2,'semestre_oferta':1,'professores_fixos':['Ada'],'permitir_multiplos_professores':True}]}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        state = load_state('local')
        self.assertEqual(state['config_disciplinas'][0]['professores_fixos'], [])
        self.assertFalse(state['config_disciplinas'][0]['permitir_multiplos_professores'])
        self.assertEqual(state['config_professores'][0]['disciplinas_internas'], [])
        generated = self.client.post('/iniciar_geracao', json={}, headers=self.headers)
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(generated.json['status'], 'sucesso')
        rel = generated.json['relatorio']
        self.assertEqual(rel['disciplinas_sem_professor'], [])
        self.assertEqual(rel['disciplinas_externas'], ['Educação Ambiental'])
        self.assertEqual(rel['professores_por_disciplina']['Educação Ambiental'], ['Professor externo'])
        page = self.client.get('/resultados')
        self.assertIn('Professor externo'.encode(), page.data)

    def test_recomendacao_possui_atalho_e_contexto_salvo_volta_para_geracao(self):
        discs = [{'nome':'Sem Docente','codigo':'SD','curso':'Teste','semestre':1,'carga_horaria':30}]
        self.client.post('/salvar_selecoes', json={'disciplinas':discs,'professores':[{'nome':'Ada'}]}, headers=self.headers)
        response = self.client.post('/iniciar_geracao', json={}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        diagnosticos = response.json['relatorio']['diagnosticos']
        sem_docente = next(d for d in diagnosticos if d['codigo'] == 'disciplina_sem_professor_vinculado')
        self.assertTrue(sem_docente['atalhos'])
        self.assertIn('/config?', sem_docente['atalhos'][0]['href'])
        config_page = self.client.get(sem_docente['atalhos'][0]['href'])
        self.assertEqual(config_page.status_code, 200)
        self.assertIn(b'salvarVoltarGeracaoBtn', config_page.data)
        save_response = self.client.post('/salvar_contexto_recomendacao', json={
            'config_disciplinas':[{'idx':0,'tipo':'interna','aulas_semanais':2,'semestre_oferta':1,'professores_fixos':['Ada'],'permitir_multiplos_professores':False}],
            'config_professores':[{'idx':0,'disciplinas_internas':[0],'carga_alvo':2,'carga_maxima':20,'disponibilidade':[]}],
            'config_avancadas':{'estado_sabado':'desativado','nivel_restricao':3},
        }, headers=self.headers)
        self.assertEqual(save_response.status_code, 200)
        confirmation = self.client.get('/generate?alteracoes=1')
        self.assertEqual(confirmation.status_code, 200)
        self.assertIn('Alterações salvas.'.encode(), confirmation.data)
        generated = self.client.post('/iniciar_geracao', json={}, headers=self.headers)
        self.assertEqual(generated.status_code, 200)
        self.assertEqual(generated.json['status'], 'sucesso')

    def test_regerar_informa_quando_encontra_alternativa(self):
        discs = [{'nome':'Flexível','codigo':'F','curso':'Teste','semestre':1,'carga_horaria':15}]
        self.client.post('/salvar_selecoes', json={'disciplinas':discs,'professores':[]}, headers=self.headers)
        self.client.post('/salvar_todas_disciplinas', json={'configs':[{'idx':0,'tipo':'externa','aulas_semanais':1,'semestre_oferta':1,'professores_fixos':[],'permitir_multiplos_professores':False}]}, headers=self.headers)
        first = self.client.post('/iniciar_geracao', json={}, headers=self.headers)
        self.assertEqual(first.status_code, 200)
        old_sig = first.json['relatorio']['assinatura_grade']
        second = self.client.post('/iniciar_geracao', json={'regenerar':True}, headers=self.headers)
        self.assertEqual(second.status_code, 200)
        regen = second.json['relatorio']['regeneracao']
        self.assertEqual(regen['resultado'], 'alternativa_encontrada')
        self.assertNotEqual(second.json['relatorio']['assinatura_grade'], old_sig)

    def test_regerar_mantem_grade_quando_nao_encontra_alternativa_equivalente(self):
        discs = [{'nome':'Horário Único','codigo':'U','curso':'Teste','semestre':1,'carga_horaria':15}]
        self.client.post('/salvar_selecoes', json={'disciplinas':discs,'professores':[]}, headers=self.headers)
        self.client.post('/salvar_todas_disciplinas', json={'configs':[{'idx':0,'tipo':'externa','aulas_semanais':1,'semestre_oferta':1,'professores_fixos':[],'permitir_multiplos_professores':False}]}, headers=self.headers)
        fixed = self.client.post('/salvar_fixacao', json={'idx':0,'dia':'Segunda','hora':'08:00-09:00','tipo':'fixar'}, headers=self.headers)
        self.assertEqual(fixed.status_code, 200)
        first = self.client.post('/iniciar_geracao', json={}, headers=self.headers)
        self.assertEqual(first.status_code, 200)
        old_sig = first.json['relatorio']['assinatura_grade']
        second = self.client.post('/iniciar_geracao', json={'regenerar':True}, headers=self.headers)
        self.assertEqual(second.status_code, 200)
        rel2 = second.json['relatorio']
        self.assertEqual(rel2['regeneracao']['resultado'], 'mesma_combinacao')
        self.assertEqual(rel2['assinatura_grade'], old_sig)
        cursor2 = rel2['cursor_regeneracao']
        third = self.client.post('/iniciar_geracao', json={'regenerar':True}, headers=self.headers)
        self.assertEqual(third.status_code, 200)
        rel3 = third.json['relatorio']
        self.assertEqual(rel3['regeneracao']['resultado'], 'mesma_combinacao')
        self.assertGreater(rel3['cursor_regeneracao'], cursor2)
        self.assertEqual(rel3['assinatura_grade'], old_sig)


if __name__ == '__main__':
    unittest.main()
