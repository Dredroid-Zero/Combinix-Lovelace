# app.py — Combinix Lovelace · CSP Solver: blocos 2/3 + cascata níveis + sábado 3 estados
import os, json, random, copy, io, logging
from collections import defaultdict
from flask import Flask, render_template, request, session, jsonify, send_file
from persistence import save_state, load_state, reset_state

app = Flask(__name__)
app.secret_key = 'chave_super_secreta_combinix_lovelace'

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

DICT_KEYS = {'config_avancadas','resultado_grade_disciplinas','resultado_grade_professores',
             'resultado_horarios_professores','resultado_grade_por_semestre',
             'resultado_grade_por_professor','resultado_relatorio'}

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
    if 'usar_sabado' in cfg and 'estado_sabado' not in cfg:
        cfg['estado_sabado'] = 'normal' if cfg.pop('usar_sabado') else 'desativado'
    cfg.setdefault('estado_sabado','desativado')

# ─── Persistência ──────────────────────────────────────────────────────────
def auto_save():
    data = {k:session.get(k,{} if k in DICT_KEYS else [])
            for k in ['disciplinas_selecionadas','professores_selecionados','config_disciplinas',
                      'config_professores','grupos_choque','config_avancadas',
                      'resultado_grade_disciplinas','resultado_grade_professores',
                      'resultado_horarios_professores','resultado_grade_por_semestre',
                      'resultado_grade_por_professor','resultado_relatorio']}
    data['tema'] = session.get('tema','claro'); save_state(data)

def carregar_estado_inicial():
    estado = load_state()
    if estado:
        for k in ['disciplinas_selecionadas','professores_selecionados','config_disciplinas',
                  'config_professores','grupos_choque','config_avancadas',
                  'resultado_grade_disciplinas','resultado_grade_professores',
                  'resultado_horarios_professores','resultado_grade_por_semestre',
                  'resultado_grade_por_professor','resultado_relatorio']:
            session[k] = estado.get(k,{} if k in DICT_KEYS else [])
        session['tema'] = estado.get('tema','claro'); session.modified = True; return True
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
    config_avancadas = session.get('config_avancadas',{'estado_sabado':'desativado','quebrar_blocos':'flexivel'})
    _normalizar_avancadas(config_avancadas)
    return render_template('config.html', disciplinas=disciplinas, professores=professores,
                           config_disciplinas=config_disc, config_professores=config_prof,
                           grupos_choque=grupos_choque, config_avancadas=config_avancadas,
                           dias=DIAS, horarios=HORARIOS)

@app.route('/generate')
def generate():
    if 'disciplinas_selecionadas' not in session: carregar_estado_inicial()
    return render_template('generate.html',
        show_results=bool(session.get('resultado_grade_disciplinas')),
        grade_disciplinas=session.get('resultado_grade_disciplinas',{}),
        grade_professores=session.get('resultado_grade_professores',{}),
        horarios_professores=session.get('resultado_horarios_professores',{}),
        grade_por_semestre=session.get('resultado_grade_por_semestre',{}),
        grade_por_professor=session.get('resultado_grade_por_professor',{}),
        relatorio=session.get('resultado_relatorio',{}), dias=DIAS, horarios=HORARIOS)

@app.route('/resultados')
def resultados():
    return render_template('generate.html', show_results=True,
        grade_disciplinas=session.get('resultado_grade_disciplinas',{}),
        grade_professores=session.get('resultado_grade_professores',{}),
        horarios_professores=session.get('resultado_horarios_professores',{}),
        grade_por_semestre=session.get('resultado_grade_por_semestre',{}),
        grade_por_professor=session.get('resultado_grade_por_professor',{}),
        relatorio=session.get('resultado_relatorio',{}), dias=DIAS, horarios=HORARIOS)

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
    data=request.get_json(force=True,silent=True) or {}
    cfg={'estado_sabado':data.get('estado_sabado','desativado'),'quebrar_blocos':data.get('quebrar_blocos','flexivel')}
    _normalizar_avancadas(cfg); session['config_avancadas']=cfg; session.modified=True; auto_save()
    return jsonify({'status':'ok'})

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

def _colocar_cascata(uid,cfg,estado_sabado,grade,occ_sem,occ_global,grupos_choque,u2n):
    for nivel in [1,2,3]:
        dias_v=_get_dias_para_nivel(nivel,estado_sabado)
        ok,pls=_colocar_nivel(uid,cfg,nivel,estado_sabado,dias_v,grade,occ_sem,occ_global,grupos_choque,u2n)
        if ok:
            av=None if nivel==1 else "Nível {}: '{}'.".format(nivel,u2n.get(uid,'?'))
            return nivel,pls,av
    return 0,[],"❌ Impossível: '{}'.".format(u2n.get(uid,'?'))

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
    relatorio={'erros':[],'avisos':[],'niveis':{},'fase1_ok':False,'fase2_ok':False,
               'professores_sobrecarga':[],'disciplinas_sem_professor':[],'score':0}
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
            dias_v=_get_dias_para_nivel(3,estado_sabado)
            grade_g={d:{h:[] for h in HORARIOS} for d in dias_v}
            occ_g=defaultdict(list)
            ordered=sorted(grupos[gkey],key=lambda i:(-1 if config_disc[i].get('fixacoes') else 0,
                -int(config_disc[i].get('aulas_semanais',2)),-len(config_disc[i].get('restricoes',[])),random.random()))
            for i in ordered:
                uid=disc_uid(disciplinas[i]); cfg=config_disc[i] if i<len(config_disc) else {}
                nv,_,av=_colocar_cascata(uid,cfg,estado_sabado,grade_g,occ_g,occ_global,grupos_choque,u2n)
                nvs[uid]=nv
                if av: avs.append(av)
            gpg[gkey]=grade_g
        sc=_score(gpg,DIAS_BASE)-sum(1 for a in avs if '❌' in a)*200
        if sc>melhor_sc: melhor_sc=sc; melhor=(gpg,avs,nvs)

    grades_por_grupo,avisos,niveis=melhor
    relatorio['avisos'].extend(avisos); relatorio['niveis']={u2n.get(k,k):v for k,v in niveis.items()}
    relatorio['fase1_ok']=True; relatorio['score']=round(melhor_sc,2)

    # Converter display
    grades_display={}
    for gkey,grade in grades_por_grupo.items():
        curso,sem=gkey; ks=grupo_key(curso,sem)
        dias_grade=[d for d in grade if any(grade[d][h] for h in HORARIOS)] or DIAS_BASE
        grades_display[ks]={dia:{h:( ', '.join(u2n.get(u,u) for u in grade[dia][h]) if grade[dia][h] else '—') for h in HORARIOS} for dia in dias_grade}

    # Grade combinada
    dias_max=_get_dias_para_nivel(3,estado_sabado)
    gc={d:{h:[] for h in HORARIOS} for d in dias_max}
    for gkey,grade in grades_por_grupo.items():
        curso,sem=gkey; lbl='[{}º-{}]'.format(sem,curso)
        for dia in grade:
            if dia not in gc: gc[dia]={h:[] for h in HORARIOS}
            for h in HORARIOS:
                if grade[dia][h]: gc[dia][h].append('{} {}'.format(lbl,', '.join(u2n.get(u,u) for u in grade[dia][h])))
    dias_comb=[d for d in dias_max if any(gc.get(d,{}).get(h) for h in HORARIOS)] or DIAS_BASE
    grade_display={d:{h:(' | '.join(gc[d][h]) if gc.get(d,{}).get(h) else '—') for h in HORARIOS} for d in dias_comb}

    # FASE 2 — Professores
    grade_prof=copy.deepcopy(grade_display)
    prof_carga={p.get('nome',''):0 for p in professores}
    h_por_prof={p.get('nome',''):[] for p in professores}
    grade_por_professor={p.get('nome',''):{d:{h:'—' for h in HORARIOS} for d in dias_comb} for p in professores}
    uid_para_prof=defaultdict(list)
    for pi,prof in enumerate(professores):
        cp=config_prof[pi] if pi<len(config_prof) else {}
        for di in cp.get('disciplinas_internas',[]):
            try: di=int(di)
            except: continue
            if di<len(disciplinas):
                uid=disc_uid(disciplinas[di])
                uid_para_prof[uid].append({'nome':prof.get('nome',''),'carga_max':int(cp.get('carga_maxima',20)),
                                           'indisp':cp.get('disponibilidade',[]),'n_disc':len(cp.get('disciplinas_internas',[]))})
    discs_semprof=set(); occ_prof_slot=defaultdict(set)
    for gkey,grade in grades_por_grupo.items():
        curso,sem=gkey; lbl='[{}º-{}]'.format(sem,curso)
        for dia in dias_comb:
            if dia not in grade: continue
            for hora in HORARIOS:
                if not grade[dia][hora]: continue
                partes=[]
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
                    if prof_ok: partes.append('{} ({})'.format(nd,prof_ok))
                    else: partes.append(nd); (discs_semprof.add(nd) if uid_para_prof.get(uid) else None)
                grade_prof[dia][hora]='{} {}'.format(lbl,' | '.join(partes))
    if discs_semprof: relatorio['disciplinas_sem_professor']=sorted(discs_semprof)
    for pi,prof in enumerate(professores):
        pn=prof.get('nome',''); cp=config_prof[pi] if pi<len(config_prof) else {}
        if prof_carga.get(pn,0)>=int(cp.get('carga_maxima',20)): relatorio['professores_sobrecarga'].append(pn)
    relatorio['fase2_ok']=True
    return grade_display,grade_prof,h_por_prof,grades_display,grade_por_professor,relatorio

@app.route('/iniciar_geracao', methods=['POST'])
def iniciar_geracao():
    try:
        if not session.get('disciplinas_selecionadas'): return jsonify({'status':'erro','mensagem':'Nenhuma disciplina selecionada'})
        gd,gp,hp,gs,gpp,rel=gerar_grade()
        if rel.get('erros'): return jsonify({'status':'erro','mensagem':'Falha na validação','erros':rel['erros']})
        session['resultado_grade_disciplinas']=gd; session['resultado_grade_professores']=gp
        session['resultado_horarios_professores']=hp; session['resultado_grade_por_semestre']=gs
        session['resultado_grade_por_professor']=gpp; session['resultado_relatorio']=rel
        session.modified=True; auto_save()
        return jsonify({'status':'sucesso','relatorio':rel})
    except Exception as e:
        import traceback; return jsonify({'status':'erro','mensagem':str(e),'trace':traceback.format_exc()})

# ─── Download / Export / Import / Reset / Tema ────────────────────────────
@app.route('/download/<tipo>')
def download(tipo):
    mapa={'disciplinas':('resultado_grade_disciplinas','grade_disciplinas.json'),
          'professores':('resultado_grade_professores','grade_professores.json'),
          'horarios':('resultado_horarios_professores','horarios_professores.json'),
          'semestre':('resultado_grade_por_semestre','grade_por_semestre.json'),
          'por_professor':('resultado_grade_por_professor','grade_por_professor.json')}
    if tipo not in mapa: return jsonify({'erro':'tipo inválido'})
    k,fn=mapa[tipo]; buf=io.BytesIO(json.dumps(session.get(k,{}),ensure_ascii=False,indent=2).encode('utf-8'))
    buf.seek(0); return send_file(buf,mimetype='application/json',as_attachment=True,download_name=fn)

@app.route('/export')
def export():
    keys=['disciplinas_selecionadas','professores_selecionados','config_disciplinas','config_professores',
          'grupos_choque','config_avancadas','resultado_grade_disciplinas','resultado_grade_professores',
          'resultado_horarios_professores','resultado_grade_por_semestre','resultado_grade_por_professor','resultado_relatorio']
    data={k:session.get(k,{} if k in DICT_KEYS else []) for k in keys}
    buf=io.BytesIO(json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8')); buf.seek(0)
    return send_file(buf,mimetype='application/json',as_attachment=True,download_name='combinix_export.json')

@app.route('/import', methods=['POST'])
def import_state():
    try:
        f=request.files.get('file')
        if not f: return jsonify({'status':'erro','mensagem':'Nenhum arquivo enviado'})
        data=json.loads(f.read().decode('utf-8'))
        for k in ['disciplinas_selecionadas','professores_selecionados','config_disciplinas','config_professores',
                  'grupos_choque','config_avancadas','resultado_grade_disciplinas','resultado_grade_professores',
                  'resultado_horarios_professores','resultado_grade_por_semestre','resultado_grade_por_professor','resultado_relatorio']:
            if k in data: session[k]=data[k]
        session.modified=True; auto_save(); return jsonify({'status':'sucesso'})
    except Exception as e: return jsonify({'status':'erro','mensagem':str(e)})

@app.route('/reset', methods=['POST'])
def reset(): session.clear(); reset_state(); return jsonify({'status':'ok'})

@app.route('/salvar_tema', methods=['POST'])
def salvar_tema():
    data=request.get_json(force=True,silent=True) or {}
    if not data: data=request.form.to_dict()
    session['tema']=data.get('tema','claro'); session.modified=True; auto_save()
    return jsonify({'status':'ok'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)