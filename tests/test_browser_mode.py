import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BrowserStorageModeTests(unittest.TestCase):
    def _run_isolated(self, code: str, extra_env=None):
        env = os.environ.copy()
        env.update(extra_env or {})
        vendor = str(ROOT / 'vendor')
        env['PYTHONPATH'] = os.pathsep.join([vendor, str(ROOT), env.get('PYTHONPATH', '')])
        proc = subprocess.run(
            [sys.executable, '-c', textwrap.dedent(code)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            self.fail(f'Processo isolado falhou.\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}')
        return proc.stdout

    def test_vercel_ativa_modo_browser_automaticamente(self):
        out = self._run_isolated(
            """
            import app
            assert app.STORAGE_MODE == 'browser', app.STORAGE_MODE
            print('ok')
            """,
            {'VERCEL': '1', 'COMBINIX_STORAGE_MODE': ''},
        )
        self.assertIn('ok', out)

    def test_fluxo_browser_nao_grava_disco_e_preserva_estado(self):
        out = self._run_isolated(
            r"""
            import json, os, re, shutil
            from pathlib import Path
            import app

            assert app.STORAGE_MODE == 'browser'
            browser_dir = Path('database/workspaces/browser')
            if browser_dir.exists():
                shutil.rmtree(browser_dir)

            client = app.app.test_client()
            first = client.get('/')
            assert first.status_code == 200
            assert b'Carregando seus dados' in first.data
            csrf = json.loads(re.search(r'window\.COMBINIX_CSRF = (.*?);', first.data.decode('utf-8')).group(1))

            rendered = client.post('/', data={'browser_state': '{}', 'csrf_token': csrf})
            assert rendered.status_code == 200
            assert b'Web \xc2\xb7 navegador' in rendered.data

            discs = [{'nome':'Teste Web','codigo':'TW1','curso':'Teste','semestre':1,'carga_horaria':60}]
            profs = [{'nome':'Ada Web'}]
            saved = client.post('/salvar_selecoes', json={
                'disciplinas': discs,
                'professores': profs,
                '_browser_state': {},
            }, headers={'X-CSRF-Token': csrf})
            assert saved.status_code == 200, saved.data
            assert saved.json['status'] == 'ok'
            state = saved.json['browser_state']
            assert len(state['disciplinas_selecionadas']) == 1
            assert len(state['professores_selecionados']) == 1

            config = client.post('/config?return=/generate', data={
                'browser_state': json.dumps(state),
                'csrf_token': csrf,
            })
            assert config.status_code == 200
            assert b'Teste Web' in config.data
            assert b'Ada Web' in config.data
            assert b'Salvar altera' in config.data

            cfg = client.post('/salvar_config_disciplina', json={
                'idx': 0,
                'tipo': 'externa',
                'aulas_semanais': 1,
                'semestre_oferta': 1,
                'fixacoes': [],
                'restricoes': [],
                'permitir_multiplos_professores': False,
                'professores_fixos': [],
                '_browser_state': state,
            }, headers={'X-CSRF-Token': csrf})
            assert cfg.status_code == 200, cfg.data
            state = cfg.json['browser_state']

            generated = client.post('/iniciar_geracao', json={
                'regenerar': False,
                '_browser_state': state,
            }, headers={'X-CSRF-Token': csrf})
            assert generated.status_code == 200, generated.data
            assert generated.json['status'] == 'sucesso'
            state = generated.json['browser_state']
            assert state['browser_resultados']['grade_disciplinas']

            results = client.post('/resultados', data={
                'browser_state': json.dumps(state),
                'csrf_token': csrf,
            })
            assert results.status_code == 200
            assert b'Teste Web' in results.data

            export_loader = client.get('/export')
            assert b'Carregando seus dados' in export_loader.data
            exported = client.post('/export', data={
                'browser_state': json.dumps(state),
                'csrf_token': csrf,
            })
            assert exported.status_code == 200
            assert exported.content_type.startswith('application/json')

            excel = client.post('/download_excel', data={
                'browser_state': json.dumps(state),
                'csrf_token': csrf,
            })
            assert excel.status_code == 200
            assert 'spreadsheetml' in excel.content_type

            reset = client.post('/reset', json={'_browser_state': state}, headers={'X-CSRF-Token': csrf})
            assert reset.status_code == 200
            assert not reset.json['browser_state']['disciplinas_selecionadas']
            assert not reset.json['browser_state']['browser_resultados']
            assert not (browser_dir / 'state.json').exists()
            print('browser-flow-ok')
            """,
            {'COMBINIX_STORAGE_MODE': 'browser', 'VERCEL': ''},
        )
        self.assertIn('browser-flow-ok', out)

    def test_loader_preserva_query_de_recomendacao(self):
        out = self._run_isolated(
            r"""
            import app
            client = app.app.test_client()
            response = client.get('/config?return=/generate&tab=avancadas')
            html = response.data.decode('utf-8')
            assert '/config?return=/generate\\u0026tab=avancadas' in html
            print('query-ok')
            """,
            {'COMBINIX_STORAGE_MODE': 'browser', 'VERCEL': ''},
        )
        self.assertIn('query-ok', out)


if __name__ == '__main__':
    unittest.main()
