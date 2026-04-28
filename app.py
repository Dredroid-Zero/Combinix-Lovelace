# app.py — Combinix Lovelace · CSP Solver: blocos 2/3 + cascata níveis + sábado 3 estados
import os, json, random, copy, io, logging, uuid
from collections import defaultdict
from flask import Flask, render_template, request, session, jsonify, send_file
from persistence import save_state, load_state, reset_state

app = Flask(__name__)
app.secret_key = 'chave_super_secreta_combinix_lovelace'

# ═══════════════════════════════════════════════════════════════════════════
# ARMAZENAMENTO DE RESULTADOS — fora da session (evita cookie >4KB)
# ═══════════════════════════════════════════════════════════════════════════
# A session armazena APENAS um token UUID (poucos bytes). Os resultados grandes
# (grades, relatórios) ficam em memória do servidor e persistidos em disco.
# Isso evita o erro "session cookie too large" que causava tela em branco.
RESULTADOS_STORE = {}
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTADOS_FILE = os.path.join(_APP_DIR, 'database', 'resultados.json')

def _load_resultados_from_disk():
    """
    Carrega store de resultados do disco (sobrevive reinício do servidor).
    Resiliente a JSON corrompido — em caso de erro, ignora o arquivo (não crasha).
    """
    if not os.path.exists(RESULTADOS_FILE):
        return
    try:
        with open(RESULTADOS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        if not content.strip():
            return
        data = json.loads(content)
        if isinstance(data, dict):
            RESULTADOS_STORE.update(data)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        logging.warning('[Combinix] resultados.json corrompido, ignorando: %s', e)
        # Renomear o arquivo corrompido para investigação posterior
        try:
            os.replace(RESULTADOS_FILE, RESULTADOS_FILE + '.corrupted')
        except OSError:
            pass

def _save_resultados_to_disk():
    """
    Persiste store em disco de forma ATÔMICA:
    escreve em arquivo temporário e usa os.replace (rename atômico).
    Isso evita 'Extra data' por escritas interrompidas.
    """
    import tempfile
    try:
        target_dir = os.path.dirname(RESULTADOS_FILE)
        os.makedirs(target_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix='.tmp_res_', suffix='.json')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(RESULTADOS_STORE, f, ensure_ascii=False)
                f.flush()
                try: os.fsync(f.fileno())
                except OSError: pass
            os.replace(tmp_path, RESULTADOS_FILE)
        except Exception:
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except OSError: pass
            raise
    except Exception as e:
        logging.warning('[Combinix] Falha salvar resultados: %s', e)

def _novo_token():
    return uuid.uuid4().hex[:16]  # 16 chars (8 bytes) é suficiente

def _store_resultados(dados):
    """Cria novo token, armazena resultados e retorna o token."""
    # Limpar resultados anteriores do mesmo usuário
    token_antigo = session.get('resultado_token')
    if token_antigo and token_antigo in RESULTADOS_STORE:
        del RESULTADOS_STORE[token_antigo]
    token = _novo_token()
    RESULTADOS_STORE[token] = dados
    _save_resultados_to_disk()
    return token

def _get_resultados():
    """Retorna os resultados do usuário atual, ou {} se não existir/inválido."""
    token = session.get('resultado_token')
    if not token or token not in RESULTADOS_STORE:
        return {}
    return RESULTADOS_STORE[token]

def _limpar_resultados_usuario():
    """Remove os resultados do usuário atual do store (mantém o token na sessão em branco)."""
    token = session.get('resultado_token')
    if token and token in RESULTADOS_STORE:
        del RESULTADOS_STORE[token]
        _save_resultados_to_disk()
    session.pop('resultado_token', None)

_load_resultados_from_disk()

# ─── Caminhos ABSOLUTOS — funciona independente do diretório de execução ────
# Sempre relativo ao diretório onde app.py está, não ao diretório de trabalho
BASE_DIR           = os.path.dirname(os.path.abspath(__file__))
DISCIPLINAS_FOLDER = os.path.join(BASE_DIR, 'disciplinas')
PROFESSORES_FOLDER = os.path.join(BASE_DIR, 'professores')

os.makedirs(DISCIPLINAS_FOLDER, exist_ok=True)
os.makedirs(PROFESSORES_FOLDER, exist_ok=True)

# ─── Verificação da camada de dados na inicialização ────────────────────────
def _verificar_dados():
    """
    Verifica se as pastas de dados têm arquivos JSON.
    Retorna dict com status da data layer.
    NOTA: reset() NÃO apaga esses arquivos — apenas limpa o estado do usuário.
    """
    disc_files = [f for f in os.listdir(DISCIPLINAS_FOLDER) if f.endswith('.json')]
    prof_files = [f for f in os.listdir(PROFESSORES_FOLDER) if f.endswith('.json')]
    status = {
        'disciplinas': {'pasta': DISCIPLINAS_FOLDER, 'arquivos': disc_files, 'ok': len(disc_files) > 0},
        'professores':  {'pasta': PROFESSORES_FOLDER, 'arquivos': prof_files, 'ok': len(prof_files) > 0},
    }
    if not status['disciplinas']['ok']:
        logging.warning('[Combinix] ATENÇÃO: pasta disciplinas está vazia: %s', DISCIPLINAS_FOLDER)
    if not status['professores']['ok']:
        logging.warning('[Combinix] ATENÇÃO: pasta professores está vazia: %s', PROFESSORES_FOLDER)
    return status

# Executar verificação ao iniciar o módulo
_STATUS_DADOS = _verificar_dados()

DIAS_BASE = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta']
DIAS_SABADO = DIAS_BASE + ['Sábado']
DIAS = DIAS_SABADO  # Constante completa; solver filtra conforme estado_sabado
HORARIOS = ['08:00-09:00','09:00-10:00','10:00-11:00','11:00-12:00',
            '14:00-15:00','15:00-16:00','16:00-17:00','17:00-18:00']
HORARIO_ULTIMO = '17:00-18:00'

DICT_KEYS = {'config_avancadas'}

# ─── Identidade única ──────────────────────────────────────────────────────
def disc_uid(d): return '{}|{}|{}'.format(d.get('curso','Geral'),d.get('nome',''),d.get('semestre',''))
def grupo_key(c,s): return '{}|{}'.format(c or 'Geral',s)

# ─── Config padrão ─────────────────────────────────────────────────────────
def _cfg_padrao(d):
    return {'tipo':'interna','aulas_semanais':max(1,round(d.get('carga_horaria',60)/15)),
            'semestre_oferta':d.get('semestre',1),'fixacoes':[],'restricoes':[]}
def _cfg_padrao_prof():
    return {'disciplinas_internas':[],'carga_maxima':20,'disponibilidade':[]}
def _normalizar_avancadas(cfg):
    """Normaliza config_avancadas: bool→estado_sabado, quebrar_blocos legado→nivel_restricao."""
    if 'usar_sabado' in cfg and 'estado_sabado' not in cfg:
        cfg['estado_sabado'] = 'normal' if cfg.pop('usar_sabado') else 'desativado'
    cfg.setdefault('estado_sabado', 'desativado')
    cfg.pop('quebrar_blocos', None)
    nv = cfg.get('nivel_restricao', 3)
    try: nv = int(nv)
    except (TypeError, ValueError): nv = 3
    if nv not in (1, 2, 3): nv = 3
    cfg['nivel_restricao'] = nv

# ─── Persistência ──────────────────────────────────────────────────────────
# A session agora contém APENAS:
#   - disciplinas_selecionadas, professores_selecionados
#   - config_disciplinas, config_professores, grupos_choque, config_avancadas
#   - resultado_token (UUID curto apontando para RESULTADOS_STORE)
#   - tema
# Os resultados GRANDES ficam em RESULTADOS_STORE (em memória + disco).
_SESSION_KEYS = ['disciplinas_selecionadas', 'professores_selecionados',
                 'config_disciplinas', 'config_professores',
                 'grupos_choque', 'config_avancadas']

def auto_save():
    data = {k: session.get(k, {} if k in DICT_KEYS else []) for k in _SESSION_KEYS}
    data['tema'] = session.get('tema', 'claro')
    data['resultado_token'] = session.get('resultado_token', '')
    save_state(data)

def carregar_estado_inicial():
    estado = load_state()
    if estado:
        for k in _SESSION_KEYS:
            session[k] = estado.get(k, {} if k in DICT_KEYS else [])
        session['tema'] = estado.get('tema', 'claro')
        if estado.get('resultado_token'):
            session['resultado_token'] = estado['resultado_token']
        session.modified = True
        return True
    return False

def _preservar_configs_disc(novas, antigas, cfgs_antigas):
    """CRÍTICO: Preserva configs ao navegar — não apaga dados."""
    mapa = {disc_uid(antigas[i]): cfgs_antigas[i] for i in range(min(len(antigas),len(cfgs_antigas)))}
    return [mapa.get(disc_uid(d), _cfg_padrao(d)) for d in novas]

def _preservar_configs_prof(novos, antigos, cfgs_antigas):
    mapa = {antigos[i].get('nome',''): cfgs_antigas[i] for i in range(min(len(antigos),len(cfgs_antigas)))}
    return [mapa.get(p.get('nome',''), _cfg_padrao_prof()) for p in novos]

# ─── Páginas ───────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if 'disciplinas_selecionadas' not in session: carregar_estado_inicial()
    return render_template('index.html')

@app.route('/config')
def config():
    if 'disciplinas_selecionadas' not in session: carregar_estado_inicial()
    disciplinas = session.get('disciplinas_selecionadas',[])
    professores = session.get('professores_selecionados',[])
    config_disc = session.get('config_disciplinas',[])
    config_prof = session.get('config_professores',[])
    while len(config_disc) < len(disciplinas): config_disc.append(_cfg_padrao(disciplinas[len(config_disc)]))
    while len(config_prof) < len(professores): config_prof.append(_cfg_padrao_prof())
    grupos_choque = session.get('grupos_choque',[])
    config_avancadas = session.get('config_avancadas',{'estado_sabado':'desativado','nivel_restricao':3})
    _normalizar_avancadas(config_avancadas)
    # Persistir migração (remove quebrar_blocos legado, adiciona nivel_restricao)
    session['config_avancadas'] = config_avancadas
    session.modified = True
    return render_template('config.html', disciplinas=disciplinas, professores=professores,
                           config_disciplinas=config_disc, config_professores=config_prof,
                           grupos_choque=grupos_choque, config_avancadas=config_avancadas,
                           dias=DIAS, horarios=HORARIOS)

@app.route('/generate')
def generate():
    if 'disciplinas_selecionadas' not in session: carregar_estado_inicial()
    res = _get_resultados()
    return render_template('generate.html',
        show_results=bool(res.get('grade_disciplinas')),
        grade_disciplinas=res.get('grade_disciplinas',{}),
        grade_professores=res.get('grade_professores',{}),
        horarios_professores=res.get('horarios_professores',{}),
        grade_por_semestre=res.get('grade_por_semestre',{}),
        grade_por_professor=res.get('grade_por_professor',{}),
        grades_com_prof=res.get('grades_com_prof',{}),
        relatorio=res.get('relatorio',{}), dias=DIAS, horarios=HORARIOS)

@app.route('/resultados')
def resultados():
    res = _get_resultados()
    return render_template('generate.html', show_results=True,
        grade_disciplinas=res.get('grade_disciplinas',{}),
        grade_professores=res.get('grade_professores',{}),
        horarios_professores=res.get('horarios_professores',{}),
        grade_por_semestre=res.get('grade_por_semestre',{}),
        grade_por_professor=res.get('grade_por_professor',{}),
        grades_com_prof=res.get('grades_com_prof',{}),
        relatorio=res.get('relatorio',{}), dias=DIAS, horarios=HORARIOS)

# ─── APIs ──────────────────────────────────────────────────────────────────
@app.route('/api/status')
def api_status():
    """
    Endpoint de saúde: retorna status da data layer.
    O frontend usa isso para mostrar erros claros quando dados faltam.
    """
    status = _verificar_dados()  # Sempre relê do disco, não usa cache
    return jsonify({
        'ok': status['disciplinas']['ok'] and status['professores']['ok'],
        'disciplinas': {
            'total': len(status['disciplinas']['arquivos']),
            'cursos': sorted(f.replace('.json','') for f in status['disciplinas']['arquivos']),
            'pasta': DISCIPLINAS_FOLDER,
            'ok': status['disciplinas']['ok'],
        },
        'professores': {
            'total': len(status['professores']['arquivos']),
            'institutos': sorted(f.replace('.json','') for f in status['professores']['arquivos']),
            'pasta': PROFESSORES_FOLDER,
            'ok': status['professores']['ok'],
        },
    })

@app.route('/api/cursos/disciplinas')
def api_cursos_disciplinas():
    try:
        cursos = sorted(f.replace('.json','') for f in os.listdir(DISCIPLINAS_FOLDER) if f.endswith('.json'))
    except OSError:
        cursos = []
    return jsonify(cursos)

@app.route('/api/cursos/professores')
def api_cursos_professores():
    try:
        cursos = sorted(f.replace('.json','') for f in os.listdir(PROFESSORES_FOLDER) if f.endswith('.json'))
    except OSError:
        cursos = []
    return jsonify(cursos)

@app.route('/api/disciplinas/<path:curso>')
def api_disciplinas(curso):
    """Aceita <path:curso> para lidar com nomes com caracteres especiais/acentos na URL."""
    f = os.path.join(DISCIPLINAS_FOLDER, '{}.json'.format(curso))
    if os.path.exists(f):
        try:
            data = json.load(open(f,'r',encoding='utf-8'))
            for d in data: d['curso'] = curso
            return jsonify(data)
        except Exception as e:
            return jsonify({'erro': str(e)}), 500
    return jsonify([])

@app.route('/api/professores/<path:curso>')
def api_professores(curso):
    """Aceita <path:curso> para lidar com nomes com espaços/acentos."""
    f = os.path.join(PROFESSORES_FOLDER, '{}.json'.format(curso))
    if os.path.exists(f):
        try:
            return jsonify(json.load(open(f,'r',encoding='utf-8')))
        except Exception as e:
            return jsonify({'erro': str(e)}), 500
    return jsonify([])

# ─── Seleção ───────────────────────────────────────────────────────────────
@app.route('/selecionar_disciplinas', methods=['POST'])
def selecionar_disciplinas():
    disc = (request.get_json() or {}).get('disciplinas',[]) if request.is_json else \
           json.loads(request.form.get('disciplinas','[]'))
    vistos,unicas = set(),[]
    for d in disc:
        uid=disc_uid(d)
        if uid not in vistos: vistos.add(uid); unicas.append(d)
    session['config_disciplinas'] = _preservar_configs_disc(
        unicas, session.get('disciplinas_selecionadas',[]), session.get('config_disciplinas',[]))
    session['disciplinas_selecionadas'] = unicas
    session.modified=True; auto_save()
    return jsonify({'status':'ok'})

@app.route('/selecionar_professores', methods=['POST'])
def selecionar_professores():
    profs = (request.get_json() or {}).get('professores',[]) if request.is_json else \
            json.loads(request.form.get('professores','[]'))
    session['config_professores'] = _preservar_configs_prof(
        profs, session.get('professores_selecionados',[]), session.get('config_professores',[]))
    session['professores_selecionados'] = profs
    session.modified=True; auto_save()
    return jsonify({'status':'ok'})

@app.route('/adicionar_disciplina_manual', methods=['POST'])
def adicionar_disciplina_manual():
    d = {'nome':request.form.get('nome',''),'codigo':request.form.get('codigo','MAN'),
         'curso':request.form.get('curso','Manual'),'semestre':int(request.form.get('semestre',1)),
         'carga_horaria':int(request.form.get('carga',60))}
    discs = session.get('disciplinas_selecionadas',[])
    if any(disc_uid(x)==disc_uid(d) for x in discs): return jsonify({'status':'erro','mensagem':'Já existe'})
    discs.append(d); session['disciplinas_selecionadas']=discs
    cfgs=session.get('config_disciplinas',[]); cfgs.append(_cfg_padrao(d))
    session['config_disciplinas']=cfgs; session.modified=True; auto_save()
    return jsonify({'status':'ok'})

@app.route('/adicionar_professor_manual', methods=['POST'])
def adicionar_professor_manual():
    profs=session.get('professores_selecionados',[]); profs.append({'nome':request.form.get('nome','')})
    cfgs=session.get('config_professores',[]); cfgs.append(_cfg_padrao_prof())
    session['professores_selecionados']=profs; session['config_professores']=cfgs
    session.modified=True; auto_save(); return jsonify({'status':'ok'})

@app.route('/remover_disciplina', methods=['POST'])
def remover_disciplina():
    idx=int(request.form.get('index',-1))
    d=session.get('disciplinas_selecionadas',[]); c=session.get('config_disciplinas',[])
    if 0<=idx<len(d): d.pop(idx);(c.pop(idx) if idx<len(c) else None)
    session['disciplinas_selecionadas']=d; session['config_disciplinas']=c
    session.modified=True; auto_save(); return jsonify({'status':'ok'})

@app.route('/remover_disciplina_config', methods=['POST'])
def remover_disciplina_config():
    """Remove disciplina diretamente na tela de configuração."""
    data=request.get_json(force=True,silent=True) or {}; idx=data.get('idx')
    if isinstance(idx,str) and idx.isdigit(): idx=int(idx)
    d=session.get('disciplinas_selecionadas',[]); c=session.get('config_disciplinas',[])
    if isinstance(idx,int) and 0<=idx<len(d):
        d.pop(idx); (c.pop(idx) if idx<len(c) else None)
        session['disciplinas_selecionadas']=d; session['config_disciplinas']=c
        session.modified=True; auto_save(); return jsonify({'status':'ok'})
    return jsonify({'status':'erro','mensagem':'Índice inválido'})

@app.route('/remover_professor_config', methods=['POST'])
def remover_professor_config():
    """Remove professor diretamente na tela de configuração (mesma lógica simétrica)."""
    data = request.get_json(force=True, silent=True) or {}
    idx = data.get('idx')
    if isinstance(idx, str) and idx.isdigit(): idx = int(idx)
    p = session.get('professores_selecionados', [])
    c = session.get('config_professores', [])
    if isinstance(idx, int) and 0 <= idx < len(p):
        p.pop(idx)
        if idx < len(c): c.pop(idx)
        session['professores_selecionados'] = p
        session['config_professores'] = c
        session.modified = True
        auto_save()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'erro', 'mensagem': 'Índice inválido'})

@app.route('/remover_professor', methods=['POST'])
def remover_professor():
    idx=int(request.form.get('index',-1))
    p=session.get('professores_selecionados',[]); c=session.get('config_professores',[])
    if 0<=idx<len(p): p.pop(idx);(c.pop(idx) if idx<len(c) else None)
    session['professores_selecionados']=p; session['config_professores']=c
    session.modified=True; auto_save(); return jsonify({'status':'ok'})

# ─── Configuração ──────────────────────────────────────────────────────────
def _upd_cfg_disc(idx, data):
    cfgs=session.get('config_disciplinas',[])
    if isinstance(idx,int) and 0<=idx<len(cfgs):
        cfgs[idx].update({'tipo':data.get('tipo','interna'),
                          'aulas_semanais':int(data.get('aulas_semanais',2)),
                          'semestre_oferta':int(data.get('semestre_oferta',1))})
    session['config_disciplinas']=cfgs; session.modified=True

@app.route('/salvar_config_disciplina', methods=['POST'])
def salvar_config_disciplina():
    data=request.get_json(force=True,silent=True) or {}; _upd_cfg_disc(data.get('idx'),data); auto_save(); return jsonify({'status':'ok'})

@app.route('/salvar_todas_disciplinas', methods=['POST'])
def salvar_todas_disciplinas():
    data=request.get_json(force=True,silent=True) or {}
    for c in data.get('configs',[]): _upd_cfg_disc(c.get('idx'),c)
    auto_save(); return jsonify({'status':'ok','total':len(data.get('configs',[]))})

@app.route('/salvar_fixacao', methods=['POST'])
def salvar_fixacao():
    data=request.get_json(force=True,silent=True) or {}
    idx=data.get('idx'); dia=data.get('dia'); hora=data.get('hora'); tipo=data.get('tipo')
    if isinstance(idx,str) and idx.isdigit(): idx=int(idx)
    cfgs=session.get('config_disciplinas',[])
    if not(isinstance(idx,int) and 0<=idx<len(cfgs)): return jsonify({'status':'erro','mensagem':'Índice inválido'})
    cfg=cfgs[idx]; slot=[dia,hora]; N=int(cfg.get('aulas_semanais',2))
    nf=[s for s in cfg.get('fixacoes',[]) if s!=slot]; nr=[s for s in cfg.get('restricoes',[]) if s!=slot]
    if tipo=='fixar': nf.append(slot)
    elif tipo=='restringir': nr.append(slot)
    if len(nf)>N: return jsonify({'status':'erro','codigo':'fixacoes_excedem_carga','mensagem':'Max {} fixações.'.format(N)})
    av=session.get('config_avancadas',{}); _normalizar_avancadas(av)
    dias_v=_get_dias_para_nivel(3, av.get('estado_sabado','desativado'))
    if len(dias_v)*len(HORARIOS)-len(nr)<N: return jsonify({'status':'erro','codigo':'poucos_disponiveis','mensagem':'Slots insuficientes.'})
    cfg['fixacoes']=nf; cfg['restricoes']=nr; session['config_disciplinas']=cfgs; session.modified=True; auto_save()
    return jsonify({'status':'ok'})

@app.route('/resetar_disciplina', methods=['POST'])
def resetar_disciplina():
    data=request.get_json(force=True,silent=True) or {}; idx=data.get('idx')
    if isinstance(idx,str) and idx.isdigit(): idx=int(idx)
    d=session.get('disciplinas_selecionadas',[]); c=session.get('config_disciplinas',[])
    if not(isinstance(idx,int) and 0<=idx<len(c)): return jsonify({'status':'erro','mensagem':'Índice inválido'})
    c[idx]=_cfg_padrao(d[idx] if idx<len(d) else {}); session['config_disciplinas']=c; session.modified=True; auto_save()
    return jsonify({'status':'ok'})

@app.route('/resetar_professor', methods=['POST'])
def resetar_professor():
    data=request.get_json(force=True,silent=True) or {}; idx=data.get('idx')
    if isinstance(idx,str) and idx.isdigit(): idx=int(idx)
    c=session.get('config_professores',[])
    if not(isinstance(idx,int) and 0<=idx<len(c)): return jsonify({'status':'erro','mensagem':'Índice inválido'})
    c[idx]=_cfg_padrao_prof(); session['config_professores']=c; session.modified=True; auto_save()
    return jsonify({'status':'ok'})

@app.route('/adicionar_grupo_choque', methods=['POST'])
def adicionar_grupo_choque():
    data=request.get_json(force=True,silent=True) or {}
    nome=(data.get('nome','') or '').strip(); discs=data.get('disciplinas',[])
    if not nome or len(discs)<2: return jsonify({'status':'erro','mensagem':'Nome e 2+ disciplinas obrigatórios'})
    grupos=session.get('grupos_choque',[])
    if any(g.get('nome','').strip().lower()==nome.lower() for g in grupos):
        return jsonify({'status':'erro','codigo':'nome_duplicado','mensagem':'Já existe um grupo com esse nome'})
    grupos.append({'nome':nome,'disciplinas':discs}); session['grupos_choque']=grupos; session.modified=True; auto_save()
    return jsonify({'status':'ok'})

@app.route('/remover_grupo_choque', methods=['POST'])
def remover_grupo_choque():
    data=request.get_json(force=True,silent=True) or {}; idx=data.get('idx',-1)
    grupos=session.get('grupos_choque',[]); (grupos.pop(idx) if 0<=idx<len(grupos) else None)
    session['grupos_choque']=grupos; session.modified=True; auto_save(); return jsonify({'status':'ok'})

@app.route('/limpar_todos_conflitos', methods=['POST'])
def limpar_todos_conflitos():
    session['grupos_choque']=[]; session.modified=True; auto_save(); return jsonify({'status':'ok'})

@app.route('/salvar_config_professor', methods=['POST'])
def salvar_config_professor():
    data=request.get_json(force=True,silent=True) or {}; idx=data.get('idx')
    if isinstance(idx,str) and idx.isdigit(): idx=int(idx)
    c=session.get('config_professores',[])
    if isinstance(idx,int) and 0<=idx<len(c):
        c[idx].update({'disciplinas_internas':data.get('disciplinas_internas',[]),
                       'carga_maxima':int(data.get('carga_maxima',20)),'disponibilidade':data.get('disponibilidade',[])})
    session['config_professores']=c; session.modified=True; auto_save(); return jsonify({'status':'ok'})

@app.route('/salvar_todas_professores', methods=['POST'])
def salvar_todas_professores():
    data=request.get_json(force=True,silent=True) or {}; c=session.get('config_professores',[])
    for x in data.get('configs',[]):
        idx=x.get('idx')
        if isinstance(idx,int) and 0<=idx<len(c):
            c[idx].update({'disciplinas_internas':x.get('disciplinas_internas',[]),
                           'carga_maxima':int(x.get('carga_maxima',20)),'disponibilidade':x.get('disponibilidade',[])})
    session['config_professores']=c; session.modified=True; auto_save()
    return jsonify({'status':'ok','total':len(data.get('configs',[]))})

@app.route('/salvar_config_avancadas', methods=['POST'])
def salvar_config_avancadas():
    data = request.get_json(force=True, silent=True) or {}
    nv = data.get('nivel_restricao', 3)
    try: nv = int(nv)
    except (TypeError, ValueError): nv = 3
    if nv not in (1, 2, 3): nv = 3
    cfg = {
        'estado_sabado':   data.get('estado_sabado', 'desativado'),
        'nivel_restricao': nv,
    }
    _normalizar_avancadas(cfg)
    session['config_avancadas'] = cfg
    session.modified = True; auto_save()
    return jsonify({'status': 'ok'})

# =============================================================================
# CSP SOLVER — Blocos 2/3 + Cascata de Níveis + Sábado 3 estados
# =============================================================================

def decompor_blocos(N):
    """Decompõe N aulas em blocos de 2 e 3. Bloco de 1 só aparece em N=1."""
    if N<=0: return []
    if N==1: return [1]
    if N==2: return [2]
    if N==3: return [3]
    if N==4: return [2,2]
    if N==5: return [3,2]
    if N==6: return [3,3]
    if N==7: return [3,2,2]
    if N==8: return [3,3,2]
    b,r=[],N
    while r>=3: b.append(3); r-=3
    if r>0: b.append(r)
    return b

def _get_dias_para_nivel(nivel, estado_sabado):
    if estado_sabado=='desativado': return DIAS_BASE
    if estado_sabado=='normal': return DIAS_SABADO
    return DIAS_SABADO if nivel>=3 else DIAS_BASE  # 'restrito'

def _pode_usar_ultimo(nivel, bsz):
    if nivel==1: return False
    if nivel==2: return bsz>=3
    return True

def _pode_repetir_dia(nivel, blocos_dia, bsz):
    if nivel==1: return False
    if nivel==2: return blocos_dia<2 and bsz==2
    return blocos_dia<2

def _conflito_grupo(dia, hora, uid, occ_global, grupos_choque, uid_to_nome):
    nome=uid_to_nome.get(uid,'')
    for g in grupos_choque:
        dg=g.get('disciplinas',[])
        if nome not in dg: continue
        for ou in occ_global.get((dia,hora),[]):
            if ou!=uid and uid_to_nome.get(ou,'') in dg and uid_to_nome.get(ou,'')!=nome: return True
    return False

def _tentar_bloco_nivel(dias_v, res, uid, bsz, nivel, occ_sem, occ_global,
                         grupos_choque, u2n, dias_disc, bpd, estado_sabado):
    periodos=[(0,4),(4,8)]; cands=[]
    for dia in dias_v:
        if dia=='Sábado' and estado_sabado=='restrito' and nivel<3: continue
        blocos_dia=bpd.get(dia,0)
        if blocos_dia>0 and not _pode_repetir_dia(nivel,blocos_dia,bsz): continue
        for ini,fim in periodos:
            for start in range(ini,fim-bsz+1):
                slots=[(dia,HORARIOS[start+k]) for k in range(bsz)]
                lh=slots[-1][1]
                if lh==HORARIO_ULTIMO and not _pode_usar_ultimo(nivel,bsz): continue
                ok=True
                for(d,h) in slots:
                    if[d,h] in res or occ_sem[(d,h)] or _conflito_grupo(d,h,uid,occ_global,grupos_choque,u2n):
                        ok=False; break
                if not ok: continue
                pen=0
                if lh==HORARIO_ULTIMO: pen+=20
                if dia=='Sábado': pen+=50
                if blocos_dia>0: pen+=10
                pen+=dias_disc.get(dia,0)*3
                cands.append((pen,random.random(),slots))
    if not cands: return []
    cands.sort(); top=cands[:min(3,len(cands))]; return random.choice(top)[2]

def _undo(uid,placements,grade,occ_sem,occ_global):
    for(d,h) in placements:
        for lst in [grade[d][h],occ_sem[(d,h)],occ_global[(d,h)]]:
            try: lst.remove(uid)
            except ValueError: pass

def _colocar_nivel(uid,cfg,nivel,estado_sabado,dias_v,grade,occ_sem,occ_global,grupos_choque,u2n):
    N=int(cfg.get('aulas_semanais',2)); fix=cfg.get('fixacoes',[]); res=cfg.get('restricoes',[])
    pls=[]; dias_disc={}; bpd={}
    for sl in fix:
        d,h=sl[0],sl[1]
        if h not in HORARIOS: continue
        if occ_sem[(d,h)] or _conflito_grupo(d,h,uid,occ_global,grupos_choque,u2n):
            _undo(uid,pls,grade,occ_sem,occ_global); return False,[]
        if d in dias_v:
            grade[d][h].append(uid); occ_sem[(d,h)].append(uid); occ_global[(d,h)].append(uid)
            pls.append((d,h)); dias_disc[d]=dias_disc.get(d,0)+1
    nr=N-len(pls)
    if nr<=0: return True,pls
    for bsz in decompor_blocos(nr):
        if bsz==1 and nivel<3: _undo(uid,pls,grade,occ_sem,occ_global); return False,[]
        slots=_tentar_bloco_nivel(dias_v,res,uid,bsz,nivel,occ_sem,occ_global,grupos_choque,u2n,dias_disc,bpd,estado_sabado)
        if not slots: _undo(uid,pls,grade,occ_sem,occ_global); return False,[]
        for(d,h) in slots:
            grade[d][h].append(uid); occ_sem[(d,h)].append(uid); occ_global[(d,h)].append(uid)
            pls.append((d,h)); dias_disc[d]=dias_disc.get(d,0)+1
        bpd[slots[0][0]]=bpd.get(slots[0][0],0)+1
    return True,pls

def _colocar_cascata(uid, cfg, estado_sabado, grade, occ_sem, occ_global, grupos_choque, u2n, nivel_max=3):
    """Tenta colocar a disciplina do nível 1 até nivel_max. Se nivel_max=1, só tenta rígido."""
    if nivel_max not in (1, 2, 3): nivel_max = 3
    niveis_a_tentar = list(range(1, nivel_max + 1))
    for nivel in niveis_a_tentar:
        dias_v = _get_dias_para_nivel(nivel, estado_sabado)
        ok, pls = _colocar_nivel(uid, cfg, nivel, estado_sabado, dias_v, grade, occ_sem, occ_global, grupos_choque, u2n)
        if ok:
            av = None if nivel == 1 else "Nível {}: '{}'.".format(nivel, u2n.get(uid, '?'))
            return nivel, pls, av
    # Falha: se nivel_max<3, explicar que ficou limitado
    if nivel_max < 3:
        return 0, [], "❌ Impossível no Nível ≤{}: '{}'.".format(nivel_max, u2n.get(uid, '?'))
    return 0, [], "❌ Impossível: '{}'.".format(u2n.get(uid, '?'))

def _score(grades_por_grupo, dias_base):
    sc=0
    for gkey,grade in grades_por_grupo.items():
        for dia in dias_base:
            if dia not in grade: continue
            prev=None; run=0
            for h in HORARIOS:
                curr=tuple(sorted(grade[dia][h])) if grade[dia][h] else None
                if curr and curr==prev: run+=1
                else:
                    if run>=2: sc+=(run-1)*4
                    run=1 if curr else 0; prev=curr
            if run>=2: sc+=(run-1)*4
            if grade[dia].get(HORARIO_ULTIMO): sc-=8
            idx=[i for i,h in enumerate(HORARIOS) if grade[dia].get(h)]
            if len(idx)>=2: sc-=(idx[-1]-idx[0]+1-len(idx))*2
        cnt=[sum(1 for h in HORARIOS if grade.get(d,{}).get(h)) for d in dias_base if d in grade]
        if cnt:
            m=sum(cnt)/len(cnt); sc-=sum((c-m)**2 for c in cnt)/len(cnt)*1.5
    return sc

def gerar_grade():
    disciplinas=session.get('disciplinas_selecionadas',[])
    professores=session.get('professores_selecionados',[])
    config_disc=session.get('config_disciplinas',[])
    config_prof=session.get('config_professores',[])
    grupos_choque=session.get('grupos_choque',[])
    config_avancadas=session.get('config_avancadas',{})
    _normalizar_avancadas(config_avancadas); estado_sabado=config_avancadas.get('estado_sabado','desativado')
    nivel_max = config_avancadas.get('nivel_restricao', 3)
    relatorio={'erros':[],'avisos':[],'niveis':{},'fase1_ok':False,'fase2_ok':False,
               'professores_sobrecarga':[],'disciplinas_sem_professor':[],'score':0,
               'nivel_max_usuario': nivel_max}
    u2n={disc_uid(d):d.get('nome','') for d in disciplinas}

    # Verificação básica
    for i,disc in enumerate(disciplinas):
        cfg=config_disc[i] if i<len(config_disc) else {}
        N=int(cfg.get('aulas_semanais',2))
        if len(cfg.get('fixacoes',[]))>N:
            relatorio['erros'].append("'{}': fixações > aulas/sem.".format(disc.get('nome','?')))
    if relatorio['erros']: return {},{},{},{},{},relatorio

    # Agrupamento (curso, semestre)
    grupos=defaultdict(list)
    for i,disc in enumerate(disciplinas):
        cfg=config_disc[i] if i<len(config_disc) else {}
        grupos[(disc.get('curso','Geral'), cfg.get('semestre_oferta',disc.get('semestre',1)))].append(i)

    # Multi-restart Las Vegas
    melhor=None; melhor_sc=-float('inf')
    for attempt in range(6):
        random.seed(attempt*31+7)
        gpg={}; occ_global=defaultdict(list); avs=[]; nvs={}
        for gkey in sorted(grupos.keys()):
            curso,sem=gkey
            dias_v=_get_dias_para_nivel(nivel_max, estado_sabado)
            grade_g={d:{h:[] for h in HORARIOS} for d in dias_v}
            occ_g=defaultdict(list)
            ordered=sorted(grupos[gkey],key=lambda i:(-1 if config_disc[i].get('fixacoes') else 0,
                -int(config_disc[i].get('aulas_semanais',2)),-len(config_disc[i].get('restricoes',[])),random.random()))
            for i in ordered:
                uid=disc_uid(disciplinas[i]); cfg=config_disc[i] if i<len(config_disc) else {}
                nv,_,av=_colocar_cascata(uid,cfg,estado_sabado,grade_g,occ_g,occ_global,grupos_choque,u2n, nivel_max=nivel_max)
                nvs[uid]=nv
                if av: avs.append(av)
            gpg[gkey]=grade_g
        sc=_score(gpg,DIAS_BASE)-sum(1 for a in avs if '❌' in a)*200
        if sc>melhor_sc: melhor_sc=sc; melhor=(gpg,avs,nvs)

    grades_por_grupo,avisos,niveis=melhor
    relatorio['avisos'].extend(avisos); relatorio['niveis']={u2n.get(k,k):v for k,v in niveis.items()}
    relatorio['fase1_ok']=True; relatorio['score']=round(melhor_sc,2)

    # Converter display — TODAS as tabelas usam o conjunto COMPLETO de dias
    # (não filtra dias vazios → tabela sempre tem N colunas iguais)
    dias_completos = _get_dias_para_nivel(nivel_max, estado_sabado)
    grades_display={}
    for gkey,grade in grades_por_grupo.items():
        curso,sem=gkey; ks=grupo_key(curso,sem)
        grades_display[ks]={
            dia: {h: (', '.join(u2n.get(u,u) for u in grade.get(dia,{}).get(h,[])) if grade.get(dia,{}).get(h) else '—')
                  for h in HORARIOS}
            for dia in dias_completos
        }

    # Grade combinada
    dias_max = dias_completos
    gc={d:{h:[] for h in HORARIOS} for d in dias_max}
    for gkey,grade in grades_por_grupo.items():
        curso,sem=gkey; lbl='[{}º-{}]'.format(sem,curso)
        for dia in grade:
            if dia not in gc: gc[dia]={h:[] for h in HORARIOS}
            for h in HORARIOS:
                if grade[dia][h]: gc[dia][h].append('{} {}'.format(lbl,', '.join(u2n.get(u,u) for u in grade[dia][h])))
    # Grade combinada: TAMBÉM com todas colunas
    dias_comb = dias_completos
    grade_display={d:{h:(' | '.join(gc[d][h]) if gc.get(d,{}).get(h) else '—') for h in HORARIOS} for d in dias_comb}

    # FASE 2 — Professores
    grade_prof=copy.deepcopy(grade_display)
    prof_carga={p.get('nome',''):0 for p in professores}
    prof_carga_max={p.get('nome',''):20 for p in professores}
    h_por_prof={p.get('nome',''):[] for p in professores}

    # Grade por professor — TODAS as colunas de dias (não filtra dias vazios)
    grade_por_professor = {
        p.get('nome',''): {d: {h:'—' for h in HORARIOS} for d in dias_completos}
        for p in professores
    }

    # Grades por semestre COM PROFESSORES (mesma estrutura de grades_display, mas
    # mostrando "Disciplina (Professor)" em cada célula)
    grades_com_prof = {ks: {dia: {h:'—' for h in HORARIOS} for dia in dias_completos}
                       for ks in grades_display.keys()}

    uid_para_prof=defaultdict(list)
    for pi,prof in enumerate(professores):
        cp=config_prof[pi] if pi<len(config_prof) else {}
        prof_carga_max[prof.get('nome','')] = int(cp.get('carga_maxima',20))
        for di in cp.get('disciplinas_internas',[]):
            try: di=int(di)
            except: continue
            if di<len(disciplinas):
                uid=disc_uid(disciplinas[di])
                uid_para_prof[uid].append({'nome':prof.get('nome',''),'carga_max':int(cp.get('carga_maxima',20)),
                                           'indisp':cp.get('disponibilidade',[]),'n_disc':len(cp.get('disciplinas_internas',[]))})
    discs_semprof=set(); occ_prof_slot=defaultdict(set)
    for gkey,grade in grades_por_grupo.items():
        curso,sem=gkey; lbl='[{}º-{}]'.format(sem,curso); ks=grupo_key(curso,sem)
        for dia in dias_completos:
            if dia not in grade: continue
            for hora in HORARIOS:
                if not grade[dia][hora]: continue
                partes=[]; partes_sem_lbl=[]
                for uid in grade[dia][hora]:
                    nd=u2n.get(uid,uid); prof_ok=None
                    cands=sorted(uid_para_prof.get(uid,[]),key=lambda c:(c['n_disc'],prof_carga.get(c['nome'],0)))
                    for cand in cands:
                        pn=cand['nome']
                        if pn in occ_prof_slot[(dia,hora)]: continue
                        if [dia,hora] in cand.get('indisp',[]): continue
                        if prof_carga.get(pn,0)<cand['carga_max']:
                            prof_ok=pn; prof_carga[pn]=prof_carga.get(pn,0)+1
                            occ_prof_slot[(dia,hora)].add(pn); h_por_prof[pn].append('{} {} {}: {}'.format(lbl,dia,hora,nd))
                            if pn in grade_por_professor and dia in grade_por_professor[pn]:
                                grade_por_professor[pn][dia][hora]='{} {}'.format(lbl,nd)
                            break
                    if prof_ok:
                        partes.append('{} ({})'.format(nd,prof_ok))
                        partes_sem_lbl.append('{} ({})'.format(nd,prof_ok))
                    else:
                        partes.append(nd)
                        partes_sem_lbl.append(nd)
                        if uid_para_prof.get(uid): discs_semprof.add(nd)
                grade_prof[dia][hora]='{} {}'.format(lbl,' | '.join(partes))
                # Per-group "Com Professores" — sem o prefixo de grupo, fica idêntico ao por-semestre + (Prof)
                grades_com_prof[ks][dia][hora] = ', '.join(partes_sem_lbl)

    if discs_semprof: relatorio['disciplinas_sem_professor']=sorted(discs_semprof)
    for pi,prof in enumerate(professores):
        pn=prof.get('nome',''); cp=config_prof[pi] if pi<len(config_prof) else {}
        if prof_carga.get(pn,0)>=int(cp.get('carga_maxima',20)): relatorio['professores_sobrecarga'].append(pn)

    # Relatório de carga horária por professor (definida vs alocada)
    relatorio['carga_por_professor'] = {
        p.get('nome',''): {
            'definida': prof_carga_max.get(p.get('nome',''), 20),
            'alocada':  prof_carga.get(p.get('nome',''), 0),
        }
        for p in professores
    }

    relatorio['fase2_ok']=True
    return grade_display, grade_prof, h_por_prof, grades_display, grade_por_professor, relatorio, grades_com_prof

@app.route('/iniciar_geracao', methods=['POST'])
def iniciar_geracao():
    try:
        discs = session.get('disciplinas_selecionadas', [])
        if not discs:
            return jsonify({'status':'erro',
                            'mensagem':'Nenhuma disciplina selecionada',
                            'erros':['Volte à tela de Seleção e escolha pelo menos uma disciplina.']})

        # Validação: configs existem para cada disciplina
        config_disc = session.get('config_disciplinas', [])
        if len(config_disc) < len(discs):
            session['config_disciplinas'] = [_cfg_padrao(d) for d in discs]
            session.modified = True

        gd, gp, hp, gs, gpp, rel, gcp = gerar_grade()

        if rel.get('erros'):
            return jsonify({'status':'erro',
                            'mensagem':'Falha na validação dos dados',
                            'erros':rel['erros']})

        # Anti-vazio
        total_alocado = sum(1 for d in gd for h, c in gd[d].items() if c != '—')
        if total_alocado == 0 and discs:
            return jsonify({'status':'erro',
                            'mensagem':'Não foi possível gerar uma grade com as configurações atuais',
                            'erros':['Verifique se há slots suficientes considerando suas restrições.',
                                     'Tente aumentar o nível de flexibilidade nas Configurações Avançadas.']})

        # Armazenar no STORE (não na session) e guardar apenas o token
        token = _store_resultados({
            'grade_disciplinas':     gd,
            'grade_professores':     gp,
            'horarios_professores':  hp,
            'grade_por_semestre':    gs,
            'grade_por_professor':   gpp,
            'grades_com_prof':       gcp,
            'relatorio':             rel,
        })
        session['resultado_token'] = token
        session.modified = True
        auto_save()
        return jsonify({'status':'sucesso','relatorio':rel, 'token':token})
    except Exception as e:
        import traceback
        return jsonify({'status':'erro','mensagem':str(e),'trace':traceback.format_exc()})

# ─── Download / Export / Import / Reset / Tema ────────────────────────────
@app.route('/download/<tipo>')
def download(tipo):
    mapa = {'disciplinas':   ('grade_disciplinas',    'grade_disciplinas.json'),
            'professores':   ('grade_professores',    'grade_professores.json'),
            'horarios':      ('horarios_professores', 'horarios_professores.json'),
            'semestre':      ('grade_por_semestre',   'grade_por_semestre.json'),
            'por_professor': ('grade_por_professor',  'grade_por_professor.json')}
    if tipo not in mapa: return jsonify({'erro':'tipo inválido'})
    chave, fn = mapa[tipo]
    res = _get_resultados()
    buf = io.BytesIO(json.dumps(res.get(chave, {}), ensure_ascii=False, indent=2).encode('utf-8'))
    buf.seek(0)
    return send_file(buf, mimetype='application/json', as_attachment=True, download_name=fn)


@app.route('/download_excel')
def download_excel():
    """
    Gera arquivo .xlsx com 4 abas, cada uma com uma versão da grade.
    Mantém o mesmo formato visual da interface (linhas=horários, colunas=dias).
    """
    res = _get_resultados()
    if not res.get('grade_disciplinas'):
        return jsonify({'erro': 'Nenhuma grade gerada'}), 404

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        return jsonify({'erro':'Módulo openpyxl não instalado. Execute: pip install openpyxl'}), 500

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove sheet padrão

    # Estilos
    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill('solid', fgColor='6C9EBF')
    title_font  = Font(bold=True, size=14, color='2D2D5F')
    subtitle_font = Font(italic=True, size=10, color='666666')
    cell_align  = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin = Side(border_style='thin', color='CCCCCC')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    almoco_fill = PatternFill('solid', fgColor='F0F0F0')
    empty_fill  = PatternFill('solid', fgColor='FAFAFA')

    HORARIOS_TODOS = HORARIOS  # mesmos horários do solver

    def _draw_grid_sheet(ws, titulo, subtitulo, dias_grid, get_cell_value):
        """Desenha um cabeçalho + tabela linhas=horários, colunas=dias."""
        ws.cell(row=1, column=1, value=titulo).font = title_font
        if subtitulo:
            ws.cell(row=2, column=1, value=subtitulo).font = subtitle_font
        # Header (linha 4)
        ws.cell(row=4, column=1, value='Horário').font = header_font
        ws.cell(row=4, column=1).fill = header_fill
        ws.cell(row=4, column=1).alignment = cell_align
        ws.cell(row=4, column=1).border = border
        for j, dia in enumerate(dias_grid, start=2):
            c = ws.cell(row=4, column=j, value=dia)
            c.font = header_font; c.fill = header_fill; c.alignment = cell_align; c.border = border
        # Linhas de dados — TODOS os horários + linha de almoço
        row_idx = 5
        for i, hora in enumerate(HORARIOS_TODOS):
            # Inserir linha de almoço entre 11-12 e 14-15
            if i == 4:
                ws.cell(row=row_idx, column=1, value='12:00-14:00').font = Font(italic=True, color='888888')
                ws.cell(row=row_idx, column=1).alignment = cell_align
                ws.cell(row=row_idx, column=1).border = border
                for j in range(2, len(dias_grid)+2):
                    c = ws.cell(row=row_idx, column=j, value='almoço')
                    c.alignment = cell_align; c.fill = almoco_fill; c.border = border
                    c.font = Font(italic=True, color='888888', size=9)
                row_idx += 1
            ws.cell(row=row_idx, column=1, value=hora).font = Font(bold=True, color='555555')
            ws.cell(row=row_idx, column=1).alignment = cell_align
            ws.cell(row=row_idx, column=1).border = border
            for j, dia in enumerate(dias_grid, start=2):
                val = get_cell_value(dia, hora)
                c = ws.cell(row=row_idx, column=j, value=val if val and val != '—' else '')
                c.alignment = cell_align; c.border = border
                if not val or val == '—':
                    c.fill = empty_fill
            row_idx += 1
        # Larguras
        ws.column_dimensions['A'].width = 14
        for j in range(2, len(dias_grid)+2):
            ws.column_dimensions[openpyxl.utils.get_column_letter(j)].width = 22
        ws.row_dimensions[1].height = 24
        for r in range(4, row_idx):
            ws.row_dimensions[r].height = 28

    # ── Aba 1: Por Semestre (uma sub-tabela por grupo) ─────────────────────
    gs = res.get('grade_por_semestre', {})
    ws1 = wb.create_sheet('Por Semestre')
    if gs:
        # Para cada grupo, criamos um bloco vertical
        row_offset = 0
        for gk in sorted(gs.keys()):
            grade_g = gs[gk]
            curso, sem = (gk.split('|') + ['Geral','1'])[:2]
            titulo = f'{sem}º SEMESTRE — {curso}'
            subt = ''
            dias_grid = list(grade_g.keys())
            # Reescreve esta seção começando em row_offset+1
            base_row = row_offset + 1
            ws1.cell(row=base_row, column=1, value=titulo).font = title_font
            ws1.cell(row=base_row+2, column=1, value='Horário').font = header_font
            ws1.cell(row=base_row+2, column=1).fill = header_fill
            ws1.cell(row=base_row+2, column=1).alignment = cell_align
            ws1.cell(row=base_row+2, column=1).border = border
            for j, dia in enumerate(dias_grid, start=2):
                c = ws1.cell(row=base_row+2, column=j, value=dia)
                c.font = header_font; c.fill = header_fill; c.alignment = cell_align; c.border = border
            row = base_row + 3
            for i, hora in enumerate(HORARIOS_TODOS):
                if i == 4:
                    ws1.cell(row=row, column=1, value='12:00-14:00').alignment = cell_align
                    ws1.cell(row=row, column=1).border = border
                    for j in range(2, len(dias_grid)+2):
                        c = ws1.cell(row=row, column=j, value='almoço')
                        c.alignment = cell_align; c.fill = almoco_fill; c.border = border
                    row += 1
                ws1.cell(row=row, column=1, value=hora).alignment = cell_align
                ws1.cell(row=row, column=1).border = border
                for j, dia in enumerate(dias_grid, start=2):
                    val = grade_g.get(dia, {}).get(hora, '—')
                    c = ws1.cell(row=row, column=j, value=val if val != '—' else '')
                    c.alignment = cell_align; c.border = border
                    if val == '—': c.fill = empty_fill
                row += 1
            row_offset = row + 2  # espaço entre tabelas
        ws1.column_dimensions['A'].width = 14
        for col_letter in 'BCDEFG':
            ws1.column_dimensions[col_letter].width = 22

    # ── Aba 2: Combinada ────────────────────────────────────────────────────
    gd = res.get('grade_disciplinas', {})
    ws2 = wb.create_sheet('Grade Combinada')
    if gd:
        dias_g = list(gd.keys())
        _draw_grid_sheet(ws2, 'Grade Combinada', 'Todos os semestres em uma única tabela',
                         dias_g, lambda d, h: gd.get(d, {}).get(h, '—'))

    # ── Aba 3: Com Professores (por grupo, igual à aba 1 mas com prof) ─────
    gcp = res.get('grades_com_prof', {})
    ws3 = wb.create_sheet('Com Professores')
    if gcp:
        row_offset = 0
        for gk in sorted(gcp.keys()):
            grade_g = gcp[gk]
            curso, sem = (gk.split('|') + ['Geral','1'])[:2]
            titulo = f'{sem}º SEMESTRE — {curso} (com professores)'
            dias_grid = list(grade_g.keys())
            base_row = row_offset + 1
            ws3.cell(row=base_row, column=1, value=titulo).font = title_font
            ws3.cell(row=base_row+2, column=1, value='Horário').font = header_font
            ws3.cell(row=base_row+2, column=1).fill = header_fill
            ws3.cell(row=base_row+2, column=1).alignment = cell_align
            ws3.cell(row=base_row+2, column=1).border = border
            for j, dia in enumerate(dias_grid, start=2):
                c = ws3.cell(row=base_row+2, column=j, value=dia)
                c.font = header_font; c.fill = header_fill; c.alignment = cell_align; c.border = border
            row = base_row + 3
            for i, hora in enumerate(HORARIOS_TODOS):
                if i == 4:
                    ws3.cell(row=row, column=1, value='12:00-14:00').alignment = cell_align
                    ws3.cell(row=row, column=1).border = border
                    for j in range(2, len(dias_grid)+2):
                        c = ws3.cell(row=row, column=j, value='almoço')
                        c.alignment = cell_align; c.fill = almoco_fill; c.border = border
                    row += 1
                ws3.cell(row=row, column=1, value=hora).alignment = cell_align
                ws3.cell(row=row, column=1).border = border
                for j, dia in enumerate(dias_grid, start=2):
                    val = grade_g.get(dia, {}).get(hora, '—')
                    c = ws3.cell(row=row, column=j, value=val if val and val != '—' else '')
                    c.alignment = cell_align; c.border = border
                    if not val or val == '—': c.fill = empty_fill
                row += 1
            row_offset = row + 2
        ws3.column_dimensions['A'].width = 14
        for col_letter in 'BCDEFG':
            ws3.column_dimensions[col_letter].width = 22

    # ── Aba 4: Por Professor ────────────────────────────────────────────────
    gpp = res.get('grade_por_professor', {})
    cargas = res.get('relatorio', {}).get('carga_por_professor', {})
    ws4 = wb.create_sheet('Por Professor')
    if gpp:
        row_offset = 0
        for prof in gpp.keys():
            grade_p = gpp[prof]
            carga = cargas.get(prof, {})
            definida = carga.get('definida', '?')
            alocada  = carga.get('alocada', 0)
            dias_grid = list(grade_p.keys())
            base_row = row_offset + 1
            ws4.cell(row=base_row, column=1, value=prof).font = title_font
            ws4.cell(row=base_row+1, column=1, value=f'Carga Horária Definida: {definida}h/sem · Carga Alocada: {alocada}h/sem').font = subtitle_font
            ws4.cell(row=base_row+3, column=1, value='Horário').font = header_font
            ws4.cell(row=base_row+3, column=1).fill = header_fill
            ws4.cell(row=base_row+3, column=1).alignment = cell_align
            ws4.cell(row=base_row+3, column=1).border = border
            for j, dia in enumerate(dias_grid, start=2):
                c = ws4.cell(row=base_row+3, column=j, value=dia)
                c.font = header_font; c.fill = header_fill; c.alignment = cell_align; c.border = border
            row = base_row + 4
            for i, hora in enumerate(HORARIOS_TODOS):
                if i == 4:
                    ws4.cell(row=row, column=1, value='12:00-14:00').alignment = cell_align
                    ws4.cell(row=row, column=1).border = border
                    for j in range(2, len(dias_grid)+2):
                        c = ws4.cell(row=row, column=j, value='almoço')
                        c.alignment = cell_align; c.fill = almoco_fill; c.border = border
                    row += 1
                ws4.cell(row=row, column=1, value=hora).alignment = cell_align
                ws4.cell(row=row, column=1).border = border
                for j, dia in enumerate(dias_grid, start=2):
                    val = grade_p.get(dia, {}).get(hora, '—')
                    c = ws4.cell(row=row, column=j, value=val if val and val != '—' else '')
                    c.alignment = cell_align; c.border = border
                    if not val or val == '—': c.fill = empty_fill
                row += 1
            row_offset = row + 2
        ws4.column_dimensions['A'].width = 14
        for col_letter in 'BCDEFG':
            ws4.column_dimensions[col_letter].width = 22

    # Salvar em buffer
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True, download_name='combinix_grade.xlsx')

@app.route('/export')
def export():
    # Dados leves vêm da sessão
    data = {k: session.get(k, {} if k in DICT_KEYS else []) for k in _SESSION_KEYS}
    # Resultados vêm do store
    res = _get_resultados()
    data.update({
        'resultado_grade_disciplinas':    res.get('grade_disciplinas', {}),
        'resultado_grade_professores':    res.get('grade_professores', {}),
        'resultado_horarios_professores': res.get('horarios_professores', {}),
        'resultado_grade_por_semestre':   res.get('grade_por_semestre', {}),
        'resultado_grade_por_professor':  res.get('grade_por_professor', {}),
        'resultado_relatorio':            res.get('relatorio', {}),
    })
    buf = io.BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))
    buf.seek(0)
    return send_file(buf, mimetype='application/json', as_attachment=True, download_name='combinix_export.json')

@app.route('/import', methods=['POST'])
def import_state():
    try:
        f = request.files.get('file')
        if not f: return jsonify({'status':'erro','mensagem':'Nenhum arquivo enviado'})
        data = json.loads(f.read().decode('utf-8'))
        # Dados leves → sessão
        for k in _SESSION_KEYS:
            if k in data: session[k] = data[k]
        # Resultados → store (se houver)
        res_keys = ['resultado_grade_disciplinas','resultado_grade_professores',
                    'resultado_horarios_professores','resultado_grade_por_semestre',
                    'resultado_grade_por_professor','resultado_relatorio']
        if any(k in data and data[k] for k in res_keys):
            dados = {
                'grade_disciplinas':     data.get('resultado_grade_disciplinas', {}),
                'grade_professores':     data.get('resultado_grade_professores', {}),
                'horarios_professores':  data.get('resultado_horarios_professores', {}),
                'grade_por_semestre':    data.get('resultado_grade_por_semestre', {}),
                'grade_por_professor':   data.get('resultado_grade_por_professor', {}),
                'relatorio':             data.get('resultado_relatorio', {}),
            }
            token = _store_resultados(dados)
            session['resultado_token'] = token
        session.modified = True
        auto_save()
        return jsonify({'status':'sucesso'})
    except Exception as e:
        return jsonify({'status':'erro','mensagem':str(e)})

@app.route('/reset', methods=['POST'])
def reset():
    """Reset COMPLETO: limpa sessão + state.json + resultados do usuário."""
    _limpar_resultados_usuario()
    session.clear()
    reset_state()
    return jsonify({'status':'ok'})

@app.route('/reset_configuracoes', methods=['POST'])
def reset_configuracoes():
    """
    Reset SUAVE: mantém seleções (disciplinas + professores escolhidos),
    mas zera todas as configurações (fixações, tipos, conflitos, indisponibilidades).
    """
    discs = session.get('disciplinas_selecionadas', [])
    profs = session.get('professores_selecionados', [])
    session['config_disciplinas']  = [_cfg_padrao(d) for d in discs]
    session['config_professores']  = [_cfg_padrao_prof() for _ in profs]
    session['grupos_choque']       = []
    session['config_avancadas']    = {'estado_sabado':'desativado','nivel_restricao':3}
    # Limpa resultados do usuário (store + token)
    _limpar_resultados_usuario()
    session.modified = True
    auto_save()
    return jsonify({'status':'ok'})

@app.route('/reset_resultados', methods=['POST'])
def reset_resultados():
    """Reset apenas dos resultados gerados — mantém TUDO (seleções + configs)."""
    _limpar_resultados_usuario()
    session.modified = True
    auto_save()
    return jsonify({'status':'ok'})

@app.route('/salvar_tema', methods=['POST'])
def salvar_tema():
    data=request.get_json(force=True,silent=True) or {}
    if not data: data=request.form.to_dict()
    session['tema']=data.get('tema','claro'); session.modified=True; auto_save()
    return jsonify({'status':'ok'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)