"""Motor de geração de horários do Combinix Lovelace.

A versão 2 separa o solver das rotas Flask e trata três objetivos:
1. nunca declarar sucesso quando parte da grade ficou sem alocação;
2. usar um único professor por disciplina por padrão;
3. explicar conflitos com diagnósticos objetivos e sugestões acionáveis.

O solver continua leve e adequado ao uso local: usa busca com retrocesso limitada,
heurística MRV (primeiro a disciplina com menos opções) e níveis graduais de
flexibilidade. Ele não depende de serviços externos.
"""
from __future__ import annotations

import copy
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import quote

DIAS_BASE = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]
DIAS_SABADO = DIAS_BASE + ["Sábado"]
DIAS = DIAS_SABADO
HORARIOS = [
    "08:00-09:00", "09:00-10:00", "10:00-11:00", "11:00-12:00",
    "14:00-15:00", "15:00-16:00", "16:00-17:00", "17:00-18:00",
]
HORARIO_ULTIMO = "17:00-18:00"
PROFESSOR_EXTERNO = "Professor externo"
Slot = Tuple[str, str]


def disc_uid(disciplina: dict) -> str:
    """Identificador estável suficiente para o catálogo local atual."""
    return "{}|{}|{}|{}".format(
        disciplina.get("curso", "Geral"),
        disciplina.get("codigo", ""),
        disciplina.get("nome", ""),
        disciplina.get("semestre", ""),
    )


def grupo_key(curso: str, semestre: object) -> str:
    return "{}|{}".format(curso or "Geral", semestre)


def cfg_padrao(disciplina: dict) -> dict:
    try:
        carga = int(disciplina.get("carga_horaria", 60))
    except (TypeError, ValueError):
        carga = 60
    return {
        "tipo": "interna",
        "aulas_semanais": max(1, round(carga / 15)),
        "semestre_oferta": disciplina.get("semestre", 1),
        "fixacoes": [],
        "restricoes": [],
        # Regra nova: só divide uma disciplina entre docentes quando o usuário autorizar.
        "permitir_multiplos_professores": False,
        # Atribuição opcional definida diretamente na disciplina. Sem nomes, o
        # solver escolhe entre docentes compatíveis marcados na aba Professores.
        "professores_fixos": [],
    }


def cfg_padrao_prof() -> dict:
    return {
        "disciplinas_internas": [],
        # Carga que a coordenação deseja cumprir. O motor usa este valor para
        # diagnosticar cobertura insuficiente, sem confundi-lo com o teto rígido.
        "carga_alvo": 20,
        "carga_maxima": 20,
        "disponibilidade": [],
    }


def normalizar_avancadas(cfg: dict) -> dict:
    cfg = dict(cfg or {})
    if "usar_sabado" in cfg and "estado_sabado" not in cfg:
        cfg["estado_sabado"] = "normal" if cfg.pop("usar_sabado") else "desativado"
    estado = cfg.get("estado_sabado", "desativado")
    if estado not in {"desativado", "normal", "restrito"}:
        estado = "desativado"
    cfg["estado_sabado"] = estado
    cfg.pop("quebrar_blocos", None)
    try:
        nivel = int(cfg.get("nivel_restricao", 3))
    except (TypeError, ValueError):
        nivel = 3
    cfg["nivel_restricao"] = nivel if nivel in (1, 2, 3) else 3
    return cfg


def decompor_blocos(n_aulas: int) -> List[int]:
    """Decompõe aulas em blocos preferenciais de 2 e 3 horas."""
    if n_aulas <= 0:
        return []
    tabela = {
        1: [1], 2: [2], 3: [3], 4: [2, 2], 5: [3, 2], 6: [3, 3],
        7: [3, 2, 2], 8: [3, 3, 2],
    }
    if n_aulas in tabela:
        return tabela[n_aulas][:]
    blocos, restante = [], n_aulas
    while restante >= 3:
        blocos.append(3)
        restante -= 3
    if restante:
        blocos.append(restante)
    return blocos


def get_dias_para_nivel(nivel: int, estado_sabado: str) -> List[str]:
    if estado_sabado == "desativado":
        return DIAS_BASE[:]
    if estado_sabado == "normal":
        return DIAS_SABADO[:]
    return DIAS_SABADO[:] if nivel >= 3 else DIAS_BASE[:]


def _normalizar_slots(slots: Iterable[Sequence[str]]) -> List[List[str]]:
    vistos: Set[Slot] = set()
    saida: List[List[str]] = []
    for slot in slots or []:
        if not isinstance(slot, (list, tuple)) or len(slot) != 2:
            continue
        dia, hora = str(slot[0]), str(slot[1])
        chave = (dia, hora)
        if chave not in vistos:
            vistos.add(chave)
            saida.append([dia, hora])
    return saida


def _int_seguro(valor: object, padrao: int, minimo: int = 0, maximo: Optional[int] = None) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return padrao
    n = max(minimo, n)
    if maximo is not None:
        n = min(maximo, n)
    return n


def _nome_disc(item: "DiscItem") -> str:
    return item.disc.get("nome", "Disciplina sem nome")


def _atalho(rotulo: str, href: str, icone: str = "fa-arrow-up-right-from-square") -> dict:
    return {"rotulo": rotulo, "href": href, "icone": icone}


def _href_disciplina(idx: int) -> str:
    return f"/config?tab=disciplinas&disc={idx}&return=/generate"


def _href_professor(nome: str) -> str:
    return f"/config?tab=professores&prof={quote(nome)}&return=/generate"


def _href_avancadas(focus: str = "nivelRestricao") -> str:
    return f"/config?tab=avancadas&focus={quote(focus)}&return=/generate"


def _href_conflitos() -> str:
    return "/config?tab=choque&return=/generate"


def _diag(codigo: str, titulo: str, detalhes: str, acoes: Sequence[str],
          severidade: str = "erro", disciplinas: Optional[Sequence[str]] = None,
          atalhos: Optional[Sequence[dict]] = None) -> dict:
    return {
        "codigo": codigo,
        "titulo": titulo,
        "detalhes": detalhes,
        "acoes": list(acoes),
        "severidade": severidade,
        "disciplinas": list(disciplinas or []),
        "atalhos": list(atalhos or []),
    }


@dataclass
class DiscItem:
    idx: int
    uid: str
    disc: dict
    cfg: dict
    grupo: Tuple[str, int]
    aulas: int
    fixacoes: Tuple[Slot, ...]
    restricoes: Set[Slot]
    tipo: str
    permitir_multiplos: bool
    professores_fixos: Tuple[str, ...] = ()
    professores_elegiveis: Tuple[str, ...] = ()


@dataclass
class SolverState:
    assignments: Dict[str, dict] = field(default_factory=dict)
    group_occ: Dict[Tuple[Tuple[str, int], str, str], str] = field(default_factory=dict)
    uid_slots: Dict[str, Set[Slot]] = field(default_factory=lambda: defaultdict(set))
    teacher_occ: Dict[Slot, Set[str]] = field(default_factory=lambda: defaultdict(set))
    teacher_load: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def clone_assignments(self) -> Dict[str, dict]:
        return copy.deepcopy(self.assignments)


@dataclass
class SearchContext:
    items: List[DiscItem]
    choque_por_uid: Dict[str, Set[str]]
    teacher_max: Dict[str, int]
    teacher_unavailable: Dict[str, Set[Slot]]
    estado_sabado: str
    nivel: int
    deadline: float
    max_nodes: int
    rng: random.Random
    nodes: int = 0
    best_assignments: Dict[str, dict] = field(default_factory=dict)
    blockers: Dict[str, dict] = field(default_factory=dict)
    timed_out: bool = False


def _prepare_items(disciplinas: Sequence[dict], config_disc: Sequence[dict],
                   professores: Sequence[dict], config_prof: Sequence[dict]) -> Tuple[List[DiscItem], Dict[str, int], Dict[str, int], Dict[str, Set[Slot]]]:
    nomes_professores = {str(p.get("nome", "")).strip() for p in professores if str(p.get("nome", "")).strip()}
    itens: List[DiscItem] = []
    for i, disc in enumerate(disciplinas):
        cfg = dict(config_disc[i]) if i < len(config_disc) and isinstance(config_disc[i], dict) else cfg_padrao(disc)
        cfg.setdefault("tipo", "interna")
        if cfg.get("tipo") not in {"interna", "externa", "cedida"}:
            cfg["tipo"] = "interna"
        cfg.setdefault("semestre_oferta", disc.get("semestre", 1))
        cfg.setdefault("permitir_multiplos_professores", False)
        cfg.setdefault("professores_fixos", [])
        cfg["fixacoes"] = _normalizar_slots(cfg.get("fixacoes", []))
        cfg["restricoes"] = _normalizar_slots(cfg.get("restricoes", []))
        fixos: List[str] = []
        for nome in cfg.get("professores_fixos", []) or []:
            nome = str(nome).strip()
            if nome and nome in nomes_professores and nome not in fixos:
                fixos.append(nome)
        # Disciplinas externas pertencem a outros cursos. Elas ocupam horário da
        # turma, mas não usam os docentes selecionados neste workspace.
        if cfg.get("tipo") == "externa":
            fixos = []
            cfg["professores_fixos"] = []
            cfg["permitir_multiplos_professores"] = False
        # Dois ou mais professores fixos representam uma escolha intencional de
        # docência compartilhada. O solver deverá usar todos eles.
        elif len(fixos) > 1:
            cfg["permitir_multiplos_professores"] = True
        aulas = _int_seguro(cfg.get("aulas_semanais", 2), 2, 1, 40)
        semestre = _int_seguro(cfg.get("semestre_oferta", disc.get("semestre", 1)), 1, 1, 30)
        itens.append(DiscItem(
            idx=i,
            uid=disc_uid(disc),
            disc=dict(disc),
            cfg=cfg,
            grupo=(str(disc.get("curso", "Geral") or "Geral"), semestre),
            aulas=aulas,
            fixacoes=tuple((x[0], x[1]) for x in cfg["fixacoes"]),
            restricoes={(x[0], x[1]) for x in cfg["restricoes"]},
            tipo=str(cfg.get("tipo", "interna")),
            permitir_multiplos=bool(cfg.get("permitir_multiplos_professores", False)),
            professores_fixos=tuple(fixos),
        ))

    teacher_max: Dict[str, int] = {}
    teacher_target: Dict[str, int] = {}
    teacher_unavailable: Dict[str, Set[Slot]] = {}
    uid_to_teachers: Dict[str, Set[str]] = defaultdict(set)
    for pi, prof in enumerate(professores):
        nome = str(prof.get("nome", "")).strip()
        if not nome:
            continue
        cp = config_prof[pi] if pi < len(config_prof) and isinstance(config_prof[pi], dict) else cfg_padrao_prof()
        maxima = _int_seguro(cp.get("carga_maxima", 20), 20, 0, 100)
        alvo = _int_seguro(cp.get("carga_alvo", maxima), maxima, 0, 100)
        teacher_max[nome] = maxima
        teacher_target[nome] = min(alvo, maxima)
        teacher_unavailable[nome] = {(x[0], x[1]) for x in _normalizar_slots(cp.get("disponibilidade", []))}
        for di in cp.get("disciplinas_internas", []) or []:
            try:
                indice = int(di)
            except (TypeError, ValueError):
                continue
            if 0 <= indice < len(itens):
                uid_to_teachers[itens[indice].uid].add(nome)
    for item in itens:
        # Quando a disciplina possui professores fixos, ela fica reservada a
        # eles. A aba Professores não pode ampliar essa lista silenciosamente.
        item.professores_elegiveis = (() if item.tipo == "externa"
                                      else (item.professores_fixos or tuple(sorted(uid_to_teachers.get(item.uid, set())))))
    return itens, teacher_max, teacher_target, teacher_unavailable


def _minimo_disciplinas_para_horas(cargas: Iterable[int], alvo: int) -> Optional[int]:
    if alvo <= 0:
        return 0
    acumulado = 0
    for quantidade, carga in enumerate(sorted((max(0, int(x)) for x in cargas), reverse=True), start=1):
        acumulado += carga
        if acumulado >= alvo:
            return quantidade
    return None


def analisar_cobertura_professores(disciplinas: Sequence[dict], professores: Sequence[dict],
                                    config_disc: Sequence[dict], config_prof: Sequence[dict]) -> Dict[str, dict]:
    """Resume se cada professor possui disciplinas suficientes para atingir sua carga alvo.

    A contagem é uma estimativa mínima baseada nas maiores cargas semanais
    disponíveis. Ela serve como orientação antecipada; a grade final ainda pode
    reduzir a alocação por choques de horários e indisponibilidades.
    """
    itens, teacher_max, teacher_target, _teacher_unavailable = _prepare_items(
        disciplinas, config_disc, professores, config_prof
    )
    resultado: Dict[str, dict] = {}
    for prof in sorted(teacher_max):
        vinculadas = [item for item in itens if item.tipo != "externa" and prof in item.professores_elegiveis]
        possiveis = [item for item in itens if item.tipo != "externa" and (not item.professores_fixos or prof in item.professores_fixos)]
        vinculadas_uids = {item.uid for item in vinculadas}
        extras = [item for item in possiveis if item.uid not in vinculadas_uids]
        alvo = teacher_target.get(prof, 0)
        horas = sum(item.aulas for item in vinculadas)
        faltam = max(0, alvo - horas)
        minimo_geral = _minimo_disciplinas_para_horas((item.aulas for item in possiveis), alvo)
        extras_estimados = _minimo_disciplinas_para_horas((item.aulas for item in extras), faltam) if faltam else 0
        resultado[prof] = {
            "carga_alvo": alvo,
            "carga_maxima": teacher_max.get(prof, 0),
            "disciplinas_disponiveis": len(vinculadas),
            "horas_disponiveis": horas,
            "cobertura_suficiente": horas >= alvo,
            "faltam_horas": faltam,
            "minimo_disciplinas_necessarias": minimo_geral,
            "disciplinas_adicionais_estimadas": extras_estimados,
            "disciplinas_fixadas": sorted(_nome_disc(item) for item in itens if prof in item.professores_fixos),
        }
    return resultado


def _prepare_choques(itens: Sequence[DiscItem], grupos_choque: Sequence[dict]) -> Dict[str, Set[str]]:
    """Converte grupos por nomes em relações por UID; nomes ambíguos são ligados a todos os UIDs correspondentes."""
    nome_para_uids: Dict[str, Set[str]] = defaultdict(set)
    for item in itens:
        nome_para_uids[_nome_disc(item)].add(item.uid)
    mapa: Dict[str, Set[str]] = defaultdict(set)
    for grupo in grupos_choque or []:
        nomes = [str(x) for x in (grupo.get("disciplinas", []) or [])]
        uids: Set[str] = set()
        for nome in nomes:
            uids.update(nome_para_uids.get(nome, set()))
        for uid in uids:
            mapa[uid].update(uids - {uid})
    return mapa


def _preflight(itens: Sequence[DiscItem], professores: Sequence[dict], teacher_max: Dict[str, int],
               teacher_target: Dict[str, int], cobertura_professores: Dict[str, dict],
               choque_por_uid: Dict[str, Set[str]], estado_sabado: str) -> List[dict]:
    diags: List[dict] = []
    uids_vistos: Set[str] = set()
    for item in itens:
        nome = _nome_disc(item)
        if item.uid in uids_vistos:
            diags.append(_diag(
                "disciplina_duplicada", "Disciplina duplicada",
                f"A disciplina “{nome}” aparece mais de uma vez com o mesmo curso, código e semestre.",
                ["Remova uma das duplicatas na etapa Seleção."], disciplinas=[nome],
                atalhos=[_atalho("Revisar seleção", "/", "fa-list-check")]))
        uids_vistos.add(item.uid)
        if len(item.fixacoes) > item.aulas:
            diags.append(_diag(
                "fixacoes_excedem_carga", "Fixações acima da carga semanal",
                f"“{nome}” possui {len(item.fixacoes)} horários fixados, mas foi configurada com {item.aulas} aula(s) por semana.",
                [f"Remova pelo menos {len(item.fixacoes)-item.aulas} fixação(ões).", "Ou aumente a quantidade de aulas semanais."],
                disciplinas=[nome], atalhos=[_atalho("Abrir disciplina", _href_disciplina(item.idx), "fa-book-open")]))
        repetidos = set(item.fixacoes) & item.restricoes
        if repetidos:
            slots = ", ".join(f"{d} {h}" for d, h in sorted(repetidos))
            diags.append(_diag(
                "fixacao_restrita", "Horário simultaneamente fixado e bloqueado",
                f"“{nome}” possui horário(s) incompatível(is): {slots}.",
                ["Na configuração da disciplina, deixe cada célula como livre, fixa ou restrita — nunca em dois estados."],
                disciplinas=[nome], atalhos=[_atalho("Corrigir horários da disciplina", _href_disciplina(item.idx), "fa-calendar-days")]))
        invalidos = [(d, h) for d, h in item.fixacoes if d not in DIAS or h not in HORARIOS]
        invalidos += [(d, h) for d, h in item.restricoes if d not in DIAS or h not in HORARIOS]
        if invalidos:
            slots = ", ".join(f"{d} {h}" for d, h in invalidos[:5])
            diags.append(_diag(
                "slot_invalido", "Horário inválido na disciplina",
                f"“{nome}” contém horário(s) não reconhecido(s): {slots}.",
                ["Restaure a disciplina e refaça as marcações de horário."], disciplinas=[nome],
                atalhos=[_atalho("Abrir disciplina", _href_disciplina(item.idx), "fa-rotate-left")]))
        if estado_sabado == "desativado" and any(d == "Sábado" for d, _ in item.fixacoes):
            diags.append(_diag(
                "fixacao_sabado_desativado", "Há fixação no sábado, mas o sábado está desativado",
                f"“{nome}” possui aula fixada no sábado. O motor não ignora mais essa regra silenciosamente.",
                ["Ative o sábado nas Configurações Avançadas.", "Ou remova a fixação no sábado."], disciplinas=[nome],
                atalhos=[_atalho("Configurar sábado", _href_avancadas("estadoSabado"), "fa-calendar-day"),
                         _atalho("Abrir disciplina", _href_disciplina(item.idx), "fa-book-open")]))
        dias_disponiveis = DIAS_BASE if estado_sabado == "desativado" else DIAS_SABADO
        livres = {(d, h) for d in dias_disponiveis for h in HORARIOS} - item.restricoes
        if len(livres) < item.aulas:
            diags.append(_diag(
                "restricoes_excessivas", "Poucos horários livres para a disciplina",
                f"“{nome}” precisa de {item.aulas} aula(s), mas restaram apenas {len(livres)} horário(s) permitido(s).",
                [f"Libere pelo menos {item.aulas-len(livres)} horário(s).", "Ative o sábado caso seja pedagogicamente aceitável."],
                disciplinas=[nome], atalhos=[_atalho("Abrir horários da disciplina", _href_disciplina(item.idx), "fa-calendar-days"),
                                            _atalho("Configurar sábado", _href_avancadas("estadoSabado"), "fa-calendar-day")]))
        if item.tipo != "externa" and item.professores_fixos and len(item.professores_fixos) > item.aulas:
            diags.append(_diag(
                "professores_fixos_excedem_aulas", "Professores fixos acima da quantidade de aulas",
                f"“{nome}” possui {len(item.professores_fixos)} professores fixos, mas somente {item.aulas} aula(s) semanal(is). Não é possível garantir participação de todos.",
                ["Remova professor(es) fixo(s).", "Ou aumente a quantidade de aulas semanais da disciplina."],
                disciplinas=[nome], atalhos=[_atalho("Revisar professores fixos", _href_disciplina(item.idx), "fa-people-group")]))
        if item.tipo != "externa" and item.professores_fixos and len(item.professores_fixos) > 1:
            soma_capacidade = sum(teacher_max.get(prof, 0) for prof in item.professores_fixos)
            sem_capacidade = [prof for prof in item.professores_fixos if teacher_max.get(prof, 0) <= 0]
            if soma_capacidade < item.aulas or sem_capacidade:
                diags.append(_diag(
                    "professores_fixos_sem_carga", "Professores fixos sem carga suficiente",
                    f"“{nome}” foi reservada para {', '.join(item.professores_fixos)}, mas a capacidade conjunta não atende às {item.aulas}h semanais.",
                    ["Aumente o limite máximo dos professores fixos.", "Ou remova um professor fixo da disciplina."],
                    disciplinas=[nome], atalhos=[_atalho("Revisar disciplina", _href_disciplina(item.idx), "fa-book-open"),
                                                _atalho("Revisar professores", "/config?tab=professores&return=/generate", "fa-user-gear")]))
        if item.tipo != "externa" and not item.professores_elegiveis:
            diags.append(_diag(
                "disciplina_sem_professor_vinculado", "Disciplina sem professor compatível",
                f"“{nome}” ainda não possui professor vinculado. Defina um professor fixo na própria disciplina ou marque um docente compatível na aba Professores.",
                ["Na disciplina, selecione um professor fixo se a atribuição já estiver decidida.", "Ou, na aba Professores, abra um docente e marque esta disciplina como compatível."],
                severidade="aviso", disciplinas=[nome],
                atalhos=[_atalho("Abrir esta disciplina", _href_disciplina(item.idx), "fa-book-open"),
                         _atalho("Abrir professores", "/config?tab=professores&return=/generate", "fa-user-tie")]))
        if item.tipo != "externa" and item.professores_elegiveis and not item.permitir_multiplos:
            capazes = [p for p in item.professores_elegiveis if teacher_max.get(p, 0) >= item.aulas]
            if not capazes:
                diags.append(_diag(
                    "professor_sem_carga_suficiente", "Nenhum professor consegue assumir sozinho a disciplina",
                    f"“{nome}” exige {item.aulas}h semanais, mas nenhum professor vinculado possui essa carga livre máxima individual.",
                    ["Aumente a carga máxima de um professor vinculado.", "Ou ative a opção de docência compartilhada apenas para esta disciplina."],
                    disciplinas=[nome], atalhos=[_atalho("Abrir disciplina", _href_disciplina(item.idx), "fa-people-arrows"),
                                                _atalho("Abrir professores", "/config?tab=professores&return=/generate", "fa-user-tie")]))

    # Cobertura mínima por professor: avisa antes da geração quando o docente
    # sequer possui disciplinas suficientes para alcançar a carga alvo.
    for prof, cobertura in cobertura_professores.items():
        alvo = cobertura.get("carga_alvo", 0)
        if alvo > teacher_max.get(prof, 0):
            diags.append(_diag(
                "carga_alvo_acima_do_limite", "Carga alvo acima do limite máximo",
                f"{prof} possui meta de {alvo}h, mas limite máximo de {teacher_max.get(prof, 0)}h.",
                ["Aumente o limite máximo ou reduza a carga alvo."], disciplinas=[],
                atalhos=[_atalho("Configurar este professor", _href_professor(prof), "fa-user-gear")]))
        if alvo > 0 and not cobertura.get("cobertura_suficiente"):
            extras = cobertura.get("disciplinas_adicionais_estimadas")
            sugestao = (f"Vincule ao menos mais {extras} disciplina(s) compatível(is)." if isinstance(extras, int)
                        else "Não existem disciplinas livres suficientes; revise reservas fixas ou reduza a carga alvo.")
            diags.append(_diag(
                "professor_cobertura_insuficiente", "Professor com cobertura insuficiente",
                f"{prof} precisa cumprir {alvo}h semanais, mas as disciplinas atualmente disponíveis somam {cobertura.get('horas_disponiveis', 0)}h em {cobertura.get('disciplinas_disponiveis', 0)} disciplina(s). Faltam {cobertura.get('faltam_horas', 0)}h potenciais.",
                [sugestao, "Ou reduza a carga alvo deste professor."],
                severidade="aviso", disciplinas=[], atalhos=[_atalho("Configurar este professor", _href_professor(prof), "fa-user-gear")]))

    # Capacidade bruta por curso × semestre.
    por_grupo: Dict[Tuple[str, int], List[DiscItem]] = defaultdict(list)
    for item in itens:
        por_grupo[item.grupo].append(item)
    total_slots = (len(DIAS_BASE) if estado_sabado == "desativado" else len(DIAS_SABADO)) * len(HORARIOS)
    for (curso, semestre), grupo in por_grupo.items():
        demanda = sum(x.aulas for x in grupo)
        if demanda > total_slots:
            nomes = [_nome_disc(x) for x in grupo]
            diags.append(_diag(
                "grupo_sem_capacidade", "Carga horária maior que a capacidade da semana",
                f"{curso} · {semestre}º semestre exige {demanda}h, mas a semana configurada oferece somente {total_slots}h.",
                [f"Reduza ao menos {demanda-total_slots}h da oferta.", "Ative o sábado se isso fizer sentido para o curso.", "Revise o semestre de oferta das disciplinas."],
                disciplinas=nomes, atalhos=[_atalho("Configurar sábado", _href_avancadas("estadoSabado"), "fa-calendar-day"),
                                           _atalho("Revisar disciplinas", "/config?tab=disciplinas&return=/generate", "fa-book-open")]))

    # Fixações que colidem dentro da mesma turma ou de grupos de choque.
    ocupacao_fixa: Dict[Tuple[Tuple[str, int], Slot], DiscItem] = {}
    fixas_por_uid = {x.uid: set(x.fixacoes) for x in itens}
    item_por_uid = {x.uid: x for x in itens}
    for item in itens:
        for slot in item.fixacoes:
            chave = (item.grupo, slot)
            outro = ocupacao_fixa.get(chave)
            if outro and outro.uid != item.uid:
                diags.append(_diag(
                    "fixacoes_mesma_turma", "Duas disciplinas da mesma turma foram fixadas juntas",
                    f"“{_nome_disc(outro)}” e “{_nome_disc(item)}” estão fixadas em {slot[0]} {slot[1]} para {item.grupo[0]} · {item.grupo[1]}º semestre.",
                    ["Mova ou remova uma das duas fixações."], disciplinas=[_nome_disc(outro), _nome_disc(item)],
                    atalhos=[_atalho("Abrir primeira disciplina", _href_disciplina(outro.idx), "fa-book-open"),
                             _atalho("Abrir segunda disciplina", _href_disciplina(item.idx), "fa-book-open")]))
            ocupacao_fixa[chave] = item
        for outro_uid in choque_por_uid.get(item.uid, set()):
            if item.uid >= outro_uid:
                continue
            conflito = set(item.fixacoes) & fixas_por_uid.get(outro_uid, set())
            if conflito:
                outro = item_por_uid.get(outro_uid)
                slot = sorted(conflito)[0]
                diags.append(_diag(
                    "fixacoes_grupo_choque", "Conflito entre horários fixados",
                    f"“{_nome_disc(item)}” e “{_nome_disc(outro)}” pertencem a um grupo de conflito e foram fixadas em {slot[0]} {slot[1]}.",
                    ["Mova uma das fixações ou revise o grupo de conflitos."], disciplinas=[_nome_disc(item), _nome_disc(outro)],
                    atalhos=[_atalho("Abrir primeira disciplina", _href_disciplina(item.idx), "fa-book-open"),
                             _atalho("Abrir segunda disciplina", _href_disciplina(outro.idx), "fa-book-open"),
                             _atalho("Revisar conflitos", _href_conflitos(), "fa-object-group")]))

    # Nomes vazios e duplicados de professores geram ambiguidades no relatório.
    nomes = [str(p.get("nome", "")).strip() for p in professores]
    vazios = sum(1 for nome in nomes if not nome)
    if vazios:
        diags.append(_diag(
            "professor_sem_nome", "Professor sem nome",
            f"Há {vazios} professor(es) sem nome na seleção.",
            ["Remova os registros vazios e adicione os nomes novamente."], severidade="erro",
            atalhos=[_atalho("Revisar seleção", "/", "fa-list-check")]))
    duplicados = sorted({nome for nome in nomes if nome and nomes.count(nome) > 1})
    if duplicados:
        diags.append(_diag(
            "professor_duplicado", "Professor selecionado mais de uma vez",
            "Os seguintes nomes aparecem duplicados: {}.".format(", ".join(duplicados)),
            ["Remova as duplicatas na etapa Seleção."], severidade="erro",
            atalhos=[_atalho("Revisar seleção", "/", "fa-list-check")]))
    return diags


def _pode_usar_ultimo(nivel: int, tamanho: int) -> bool:
    if nivel == 1:
        return False
    if nivel == 2:
        return tamanho >= 3
    return True


def _pode_repetir_dia(nivel: int, blocos_no_dia: int, tamanho: int) -> bool:
    if blocos_no_dia == 0:
        return True
    if nivel == 1:
        return False
    if nivel == 2:
        return blocos_no_dia < 2 and tamanho == 2
    return blocos_no_dia < 2


def _slot_choca(uid: str, slot: Slot, state: SolverState, choque_por_uid: Dict[str, Set[str]]) -> bool:
    bloqueados = choque_por_uid.get(uid, set())
    if not bloqueados:
        return False
    return any(outro in bloqueados and slot in state.uid_slots.get(outro, set()) for outro in bloqueados)


def _slot_livre_para_disc(item: DiscItem, slot: Slot, state: SolverState, choque_por_uid: Dict[str, Set[str]]) -> bool:
    if slot in item.restricoes:
        return False
    if (item.grupo, slot[0], slot[1]) in state.group_occ:
        return False
    if _slot_choca(item.uid, slot, state, choque_por_uid):
        return False
    return True


def _penalidade_slots(slots: Iterable[Slot], nivel: int) -> int:
    slots = list(slots)
    dias = defaultdict(int)
    penalidade = 0
    for dia, hora in slots:
        dias[dia] += 1
        if dia == "Sábado":
            penalidade += 50
        if hora == HORARIO_ULTIMO:
            penalidade += 20
    penalidade += sum(max(0, qtd - 3) * 5 for qtd in dias.values())
    penalidade += (nivel - 1) * 15
    return penalidade


def _gerar_blocos_disponiveis(item: DiscItem, state: SolverState, ctx: SearchContext,
                              tamanho: int, usados: Set[Slot], blocos_por_dia: Dict[str, int]) -> List[Tuple[Slot, ...]]:
    dias = get_dias_para_nivel(ctx.nivel, ctx.estado_sabado)
    blocos: List[Tuple[Slot, ...]] = []
    for dia in dias:
        qtd = blocos_por_dia.get(dia, 0)
        if not _pode_repetir_dia(ctx.nivel, qtd, tamanho):
            continue
        for ini, fim in ((0, 4), (4, 8)):
            for start in range(ini, fim - tamanho + 1):
                bloco = tuple((dia, HORARIOS[start + k]) for k in range(tamanho))
                if bloco[-1][1] == HORARIO_ULTIMO and not _pode_usar_ultimo(ctx.nivel, tamanho):
                    continue
                if any(slot in usados for slot in bloco):
                    continue
                if all(_slot_livre_para_disc(item, slot, state, ctx.choque_por_uid) for slot in bloco):
                    blocos.append(bloco)
    blocos.sort(key=lambda b: (_penalidade_slots(b, ctx.nivel), b))
    return blocos


def _gerar_candidatos_slots(item: DiscItem, state: SolverState, ctx: SearchContext,
                            limite: int = 20) -> List[Tuple[int, Tuple[Slot, ...]]]:
    dias_validos = set(get_dias_para_nivel(ctx.nivel, ctx.estado_sabado))
    fixacoes = tuple(item.fixacoes)
    if any(d not in dias_validos or h not in HORARIOS for d, h in fixacoes):
        return []
    if any(not _slot_livre_para_disc(item, slot, state, ctx.choque_por_uid) for slot in fixacoes):
        return []
    if len(fixacoes) > item.aulas:
        return []
    restantes = item.aulas - len(fixacoes)
    if restantes == 0:
        return [(_penalidade_slots(fixacoes, ctx.nivel), tuple(sorted(fixacoes)))]
    blocos = decompor_blocos(restantes)
    if 1 in blocos and ctx.nivel < 3:
        return []
    resultados: List[Tuple[int, Tuple[Slot, ...]]] = []
    vistos: Set[Tuple[Slot, ...]] = set()

    def rec(pos: int, usados: Set[Slot], blocos_por_dia: Dict[str, int]) -> None:
        if time.monotonic() > ctx.deadline or len(resultados) >= limite:
            return
        if pos >= len(blocos):
            slots = tuple(sorted(set(fixacoes) | usados))
            if len(slots) != item.aulas or slots in vistos:
                return
            vistos.add(slots)
            resultados.append((_penalidade_slots(slots, ctx.nivel), slots))
            return
        tamanho = blocos[pos]
        possibilidades = _gerar_blocos_disponiveis(item, state, ctx, tamanho, usados | set(fixacoes), blocos_por_dia)
        # Pequena variação entre reinícios preserva qualidade sem tornar a execução imprevisível.
        cabeca = possibilidades[: min(len(possibilidades), 8)]
        ctx.rng.shuffle(cabeca)
        cabeca.sort(key=lambda b: (_penalidade_slots(b, ctx.nivel), ctx.rng.random()))
        for bloco in cabeca:
            novos = usados | set(bloco)
            novos_bpd = dict(blocos_por_dia)
            novos_bpd[bloco[0][0]] = novos_bpd.get(bloco[0][0], 0) + 1
            rec(pos + 1, novos, novos_bpd)
            if time.monotonic() > ctx.deadline or len(resultados) >= limite:
                break

    rec(0, set(), {})
    resultados.sort(key=lambda x: (x[0], x[1]))
    return resultados[:limite]


def _teacher_single_options(item: DiscItem, slots: Sequence[Slot], state: SolverState,
                            ctx: SearchContext, limite: int = 12) -> List[dict]:
    if not item.professores_elegiveis:
        return [{"slot_professores": {}, "professores": [], "penalidade": 80}]
    saida = []
    for prof in item.professores_elegiveis:
        if state.teacher_load.get(prof, 0) + len(slots) > ctx.teacher_max.get(prof, 0):
            continue
        if any(slot in ctx.teacher_unavailable.get(prof, set()) for slot in slots):
            continue
        if any(prof in state.teacher_occ.get(slot, set()) for slot in slots):
            continue
        saida.append({
            "slot_professores": {slot: prof for slot in slots},
            "professores": [prof],
            "penalidade": state.teacher_load.get(prof, 0),
        })
    saida.sort(key=lambda x: (x["penalidade"], x["professores"]))
    return saida[:limite]


def _teacher_shared_options(item: DiscItem, slots: Sequence[Slot], state: SolverState,
                            ctx: SearchContext, limite: int = 12) -> List[dict]:
    if not item.professores_elegiveis:
        return [{"slot_professores": {}, "professores": [], "penalidade": 80}]
    slots_ordenados = list(slots)
    # Começa pelos slots mais difíceis (menos professores disponíveis).
    def disponiveis(slot: Slot, carga_local: Dict[str, int]) -> List[str]:
        profs = []
        for prof in item.professores_elegiveis:
            if slot in ctx.teacher_unavailable.get(prof, set()):
                continue
            if prof in state.teacher_occ.get(slot, set()):
                continue
            if state.teacher_load.get(prof, 0) + carga_local.get(prof, 0) >= ctx.teacher_max.get(prof, 0):
                continue
            profs.append(prof)
        return sorted(profs, key=lambda p: (state.teacher_load.get(p, 0) + carga_local.get(p, 0), p))
    slots_ordenados.sort(key=lambda s: len(disponiveis(s, {})))
    saida: List[dict] = []

    def rec(pos: int, mapa: Dict[Slot, str], carga_local: Dict[str, int]) -> None:
        if len(saida) >= limite * 3:
            return
        if pos >= len(slots_ordenados):
            profs = sorted(set(mapa.values()))
            obrigatorios = set(item.professores_fixos) if len(item.professores_fixos) > 1 else set()
            if obrigatorios and not obrigatorios.issubset(profs):
                return
            penalidade = (len(profs) - 1) * 35 + sum(state.teacher_load.get(p, 0) for p in profs)
            saida.append({"slot_professores": dict(mapa), "professores": profs, "penalidade": penalidade})
            return
        slot = slots_ordenados[pos]
        for prof in disponiveis(slot, carga_local)[:8]:
            mapa[slot] = prof
            carga_local[prof] = carga_local.get(prof, 0) + 1
            rec(pos + 1, mapa, carga_local)
            carga_local[prof] -= 1
            if carga_local[prof] <= 0:
                del carga_local[prof]
            mapa.pop(slot, None)

    rec(0, {}, {})
    # Preferir um único docente mesmo quando a divisão foi autorizada; dividir só quando necessário ou vantajoso.
    saida.sort(key=lambda x: (len(x["professores"]), x["penalidade"], x["professores"]))
    unicos = []
    vistos = set()
    for opt in saida:
        chave = tuple(sorted(opt["slot_professores"].items()))
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(opt)
        if len(unicos) >= limite:
            break
    return unicos


def _teacher_options(item: DiscItem, slots: Sequence[Slot], state: SolverState,
                     ctx: SearchContext, limite: int = 12) -> List[dict]:
    if item.tipo == "externa":
        return [{"slot_professores": {slot: PROFESSOR_EXTERNO for slot in slots},
                 "professores": [PROFESSOR_EXTERNO], "penalidade": 0,
                 "ignorar_recurso_docente": True}]
    if item.permitir_multiplos or len(item.professores_fixos) > 1:
        return _teacher_shared_options(item, slots, state, ctx, limite)
    return _teacher_single_options(item, slots, state, ctx, limite)


def _opcoes_disciplina(item: DiscItem, state: SolverState, ctx: SearchContext,
                       limite_slots: int = 16, limite_total: int = 32) -> List[dict]:
    opcoes = []
    for penalidade_slots, slots in _gerar_candidatos_slots(item, state, ctx, limite_slots):
        for prof_opt in _teacher_options(item, slots, state, ctx):
            opcoes.append({
                "slots": slots,
                "slot_professores": prof_opt["slot_professores"],
                "professores": prof_opt["professores"],
                "ignorar_recurso_docente": bool(prof_opt.get("ignorar_recurso_docente", False)),
                "nivel": ctx.nivel,
                "penalidade": penalidade_slots + prof_opt["penalidade"],
            })
            if len(opcoes) >= limite_total:
                break
        if len(opcoes) >= limite_total:
            break
    # Em empates de qualidade, a semente da tentativa permite explorar outra
    # combinação ao clicar em “Regerar”, sem sacrificar regras pedagógicas.
    opcoes.sort(key=lambda x: (x["penalidade"], ctx.rng.random(), len(x["professores"]), x["slots"]))
    return opcoes[:limite_total]


def _aplicar(item: DiscItem, opcao: dict, state: SolverState) -> None:
    state.assignments[item.uid] = copy.deepcopy(opcao)
    for slot in opcao["slots"]:
        state.group_occ[(item.grupo, slot[0], slot[1])] = item.uid
        state.uid_slots[item.uid].add(slot)
    if not opcao.get("ignorar_recurso_docente"):
        for slot, prof in opcao.get("slot_professores", {}).items():
            state.teacher_occ[slot].add(prof)
            state.teacher_load[prof] += 1


def _desfazer(item: DiscItem, opcao: dict, state: SolverState) -> None:
    state.assignments.pop(item.uid, None)
    for slot in opcao["slots"]:
        state.group_occ.pop((item.grupo, slot[0], slot[1]), None)
        state.uid_slots[item.uid].discard(slot)
    if not opcao.get("ignorar_recurso_docente"):
        for slot, prof in opcao.get("slot_professores", {}).items():
            state.teacher_occ[slot].discard(prof)
            state.teacher_load[prof] -= 1


def _diagnosticar_sem_opcao(item: DiscItem, state: SolverState, ctx: SearchContext) -> dict:
    nome = _nome_disc(item)
    dias = get_dias_para_nivel(ctx.nivel, ctx.estado_sabado)
    todos = {(d, h) for d in dias for h in HORARIOS}
    apos_restricoes = todos - item.restricoes
    livres_turma = {s for s in apos_restricoes if (item.grupo, s[0], s[1]) not in state.group_occ}
    livres_choque = {s for s in livres_turma if not _slot_choca(item.uid, s, state, ctx.choque_por_uid)}
    candid_slots = _gerar_candidatos_slots(item, state, ctx, limite=25)
    if any(d == "Sábado" for d, _ in item.fixacoes) and ctx.estado_sabado == "desativado":
        return _diag(
            "bloqueio_sabado", "Fixação no sábado bloqueada",
            f"“{nome}” exige sábado, mas esse dia está desativado.",
            ["Ative o sábado nas Configurações Avançadas.", "Ou remova a fixação no sábado."], disciplinas=[nome],
            atalhos=[_atalho("Configurar sábado", _href_avancadas("estadoSabado"), "fa-calendar-day"),
                     _atalho("Abrir disciplina", _href_disciplina(item.idx), "fa-book-open")])
    if len(apos_restricoes) < item.aulas:
        return _diag(
            "bloqueio_restricoes", "Restrições excessivas",
            f"“{nome}” precisa de {item.aulas}h, mas possui apenas {len(apos_restricoes)} slot(s) liberado(s).",
            [f"Libere pelo menos {item.aulas-len(apos_restricoes)} slot(s).", "Revise as células marcadas com 🚫."], disciplinas=[nome],
            atalhos=[_atalho("Abrir horários da disciplina", _href_disciplina(item.idx), "fa-calendar-days")])
    if len(livres_turma) < item.aulas:
        ocupados = len(apos_restricoes) - len(livres_turma)
        return _diag(
            "bloqueio_turma", "A turma já está ocupada nos horários necessários",
            f"“{nome}” precisa de {item.aulas}h. Restaram {len(livres_turma)} slot(s) livres para {item.grupo[0]} · {item.grupo[1]}º semestre; {ocupados} foram ocupados por outras disciplinas da mesma turma.",
            ["Mova fixações de disciplinas da mesma turma.", "Aumente o nível de flexibilidade.", "Revise o semestre de oferta."], disciplinas=[nome],
            atalhos=[_atalho("Abrir disciplina", _href_disciplina(item.idx), "fa-book-open"),
                     _atalho("Aumentar flexibilidade", _href_avancadas("nivelRestricao"), "fa-sliders")])
    if len(livres_choque) < item.aulas:
        return _diag(
            "bloqueio_grupo_conflito", "Grupo de conflito bloqueou os encaixes",
            f"“{nome}” possui horários livres na turma, mas os grupos de conflito reduziram as opções para {len(livres_choque)} slot(s).",
            ["Revise os grupos de conflitos.", "Mova fixações das disciplinas relacionadas.", "Aumente o nível de flexibilidade."], disciplinas=[nome],
            atalhos=[_atalho("Revisar conflitos", _href_conflitos(), "fa-object-group"),
                     _atalho("Aumentar flexibilidade", _href_avancadas("nivelRestricao"), "fa-sliders")])
    if not candid_slots:
        return _diag(
            "bloqueio_blocos", "Não foi possível formar blocos contínuos",
            f"“{nome}” possui horários isolados, mas não há combinação compatível com blocos de 2h/3h no nível {ctx.nivel}.",
            ["Libere horários consecutivos na manhã ou na tarde.", "Aumente o nível de flexibilidade.", "Use menos fixações isoladas."], disciplinas=[nome],
            atalhos=[_atalho("Liberar horários desta disciplina", _href_disciplina(item.idx), "fa-calendar-days"),
                     _atalho("Aumentar flexibilidade", _href_avancadas("nivelRestricao"), "fa-sliders")])
    if item.professores_elegiveis:
        if not any(_teacher_options(item, slots, state, ctx, limite=1) for _, slots in candid_slots):
            detalhes_prof = []
            for prof in item.professores_elegiveis:
                carga = state.teacher_load.get(prof, 0)
                maxima = ctx.teacher_max.get(prof, 0)
                indis = len(ctx.teacher_unavailable.get(prof, set()))
                detalhes_prof.append(f"{prof}: {carga}/{maxima}h alocadas; {indis} indisponibilidade(s)")
            return _diag(
                "bloqueio_professor", "Nenhum professor vinculado consegue assumir os horários restantes",
                f"“{nome}” possui combinações de horário possíveis para a turma, mas nenhuma é compatível com os docentes vinculados. " + " | ".join(detalhes_prof[:4]),
                ["Revise as indisponibilidades dos professores.", "Aumente a carga máxima de um docente.", "Mova fixações que causam choque docente.", "Ative docência compartilhada somente se a divisão for desejada."], disciplinas=[nome],
                atalhos=[_atalho("Abrir professores", "/config?tab=professores&return=/generate", "fa-user-gear"),
                         _atalho("Abrir disciplina", _href_disciplina(item.idx), "fa-book-open")])
    return _diag(
        "bloqueio_combinatorio", "Combinação de regras sem encaixe",
        f"“{nome}” não encontrou encaixe no nível {ctx.nivel} após considerar turma, conflitos, blocos e docentes.",
        ["Aumente o nível de flexibilidade.", "Reduza restrições ou fixações.", "Revise os grupos de conflito."], disciplinas=[nome],
        atalhos=[_atalho("Aumentar flexibilidade", _href_avancadas("nivelRestricao"), "fa-sliders"),
                 _atalho("Abrir disciplina", _href_disciplina(item.idx), "fa-book-open"),
                 _atalho("Revisar conflitos", _href_conflitos(), "fa-object-group")])


def _buscar(ctx: SearchContext, state: SolverState, restantes: List[DiscItem]) -> bool:
    if time.monotonic() > ctx.deadline or ctx.nodes >= ctx.max_nodes:
        ctx.timed_out = True
        return False
    ctx.nodes += 1
    if len(state.assignments) > len(ctx.best_assignments):
        ctx.best_assignments = state.clone_assignments()
    if not restantes:
        ctx.best_assignments = state.clone_assignments()
        return True

    # MRV: tenta primeiro a disciplina atualmente mais difícil.
    analise = []
    # Avaliar uma janela das disciplinas mais difíceis evita recalcular centenas
    # de combinações em catálogos grandes, sem perder a heurística MRV.
    janela = restantes[: min(10, len(restantes))]
    for item in janela:
        if time.monotonic() > ctx.deadline:
            ctx.timed_out = True
            return False
        opcoes = _opcoes_disciplina(item, state, ctx)
        analise.append((len(opcoes), -len(item.fixacoes), -item.aulas, item.uid, item, opcoes))
        if not opcoes:
            break
    analise.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    quantidade, _, _, _, item, opcoes = analise[0]
    proximos = [x for x in restantes if x.uid != item.uid]
    if quantidade == 0:
        ctx.blockers[item.uid] = _diagnosticar_sem_opcao(item, state, ctx)
        # Continua sem esta disciplina para produzir a melhor prévia parcial possível.
        _buscar(ctx, state, proximos)
        return False

    for opcao in opcoes:
        _aplicar(item, opcao, state)
        if _buscar(ctx, state, proximos):
            return True
        _desfazer(item, opcao, state)
        if time.monotonic() > ctx.deadline or ctx.nodes >= ctx.max_nodes:
            ctx.timed_out = True
            break

    return False


def _score_assignments(assignments: Dict[str, dict]) -> float:
    score = len(assignments) * 1000.0
    for opcao in assignments.values():
        score -= float(opcao.get("penalidade", 0))
        if len(opcao.get("professores", [])) > 1:
            score -= 25.0
    return round(score, 2)


def _executar_nivel(itens: List[DiscItem], teacher_max: Dict[str, int], teacher_unavailable: Dict[str, Set[Slot]],
                   choque_por_uid: Dict[str, Set[str]], estado_sabado: str, nivel: int,
                   segundos: float = 1.5, max_nodes: int = 2500, seed: int = 7) -> Tuple[Dict[str, dict], SearchContext]:
    ctx = SearchContext(
        items=itens,
        choque_por_uid=choque_por_uid,
        teacher_max=teacher_max,
        teacher_unavailable=teacher_unavailable,
        estado_sabado=estado_sabado,
        nivel=nivel,
        deadline=time.monotonic() + segundos,
        max_nodes=max_nodes,
        rng=random.Random(seed),
    )
    itens_ordenados = sorted(itens, key=lambda x: (-len(x.fixacoes), -x.aulas, -len(x.restricoes), _nome_disc(x)))
    state = SolverState()
    _buscar(ctx, state, itens_ordenados)
    return ctx.best_assignments, ctx


def _renderizar(itens: Sequence[DiscItem], assignments: Dict[str, dict], professores: Sequence[dict],
                teacher_max: Dict[str, int], teacher_target: Dict[str, int], cobertura_professores: Dict[str, dict],
                estado_sabado: str, nivel_usado: int) -> Tuple[dict, dict, dict, dict, dict, dict]:
    item_por_uid = {x.uid: x for x in itens}
    dias = get_dias_para_nivel(nivel_usado, estado_sabado)
    grupos = sorted({x.grupo for x in itens})
    grades_raw: Dict[Tuple[str, int], Dict[str, Dict[str, List[str]]]] = {
        grupo: {d: {h: [] for h in HORARIOS} for d in dias} for grupo in grupos
    }
    grades_com_prof_raw: Dict[Tuple[str, int], Dict[str, Dict[str, List[str]]]] = {
        grupo: {d: {h: [] for h in HORARIOS} for d in dias} for grupo in grupos
    }
    grade_comb_raw = {d: {h: [] for h in HORARIOS} for d in dias}
    grade_prof_raw = {d: {h: [] for h in HORARIOS} for d in dias}
    nomes_prof = sorted({str(p.get("nome", "")).strip() for p in professores if str(p.get("nome", "")).strip()})
    tem_externas = any(item.tipo == "externa" for item in itens)
    nomes_grade_prof = nomes_prof + ([PROFESSOR_EXTERNO] if tem_externas else [])
    grade_por_prof_raw = {p: {d: {h: [] for h in HORARIOS} for d in dias} for p in nomes_grade_prof}
    horarios_prof = {p: [] for p in nomes_grade_prof}
    carga_prof = {p: 0 for p in nomes_grade_prof}
    professores_por_disc: Dict[str, List[str]] = {}
    docencia_compartilhada_usada: List[str] = []
    disciplinas_externas: List[str] = []

    for uid, opcao in assignments.items():
        item = item_por_uid[uid]
        nome = _nome_disc(item)
        curso, semestre = item.grupo
        lbl = f"[{semestre}º-{curso}]"
        profs = sorted(opcao.get("professores", []))
        professores_por_disc[nome] = profs
        if item.tipo == "externa":
            disciplinas_externas.append(nome)
        if len(profs) > 1:
            docencia_compartilhada_usada.append(nome)
        for slot in opcao.get("slots", []):
            dia, hora = slot
            prof = opcao.get("slot_professores", {}).get(slot)
            grades_raw[item.grupo][dia][hora].append(nome)
            grade_comb_raw[dia][hora].append(f"{lbl} {nome}")
            texto_prof = f"{nome} ({prof})" if prof else f"{nome} (sem professor)"
            grades_com_prof_raw[item.grupo][dia][hora].append(texto_prof)
            grade_prof_raw[dia][hora].append(f"{lbl} {texto_prof}")
            if prof:
                if prof != PROFESSOR_EXTERNO:
                    carga_prof[prof] = carga_prof.get(prof, 0) + 1
                grade_por_prof_raw.setdefault(prof, {d: {h: [] for h in HORARIOS} for d in dias})
                grade_por_prof_raw[prof][dia][hora].append(f"{lbl} {nome}")
                horarios_prof.setdefault(prof, []).append(f"{lbl} {dia} {hora}: {nome}")

    def simplificar_grade(grade: Dict[str, Dict[str, List[str]]]) -> dict:
        return {d: {h: (" | ".join(vals) if vals else "—") for h, vals in hs.items()} for d, hs in grade.items()}

    grade_por_semestre = {grupo_key(c, s): simplificar_grade(grades_raw[(c, s)]) for c, s in grupos}
    grades_com_prof = {grupo_key(c, s): simplificar_grade(grades_com_prof_raw[(c, s)]) for c, s in grupos}
    grade_disciplinas = simplificar_grade(grade_comb_raw)
    grade_professores = simplificar_grade(grade_prof_raw)
    grade_por_professor = {p: simplificar_grade(g) for p, g in grade_por_prof_raw.items()}
    carga_por_professor = {
        p: ({
            "alvo": 0, "definida": "—", "maxima": "—",
            "alocada": sum(len(vals) for dia in grade_por_prof_raw.get(p, {}).values() for vals in dia.values()),
            "externo": True,
        } if p == PROFESSOR_EXTERNO else {
            "alvo": teacher_target.get(p, teacher_max.get(p, 20)),
            "definida": teacher_max.get(p, 20),
            "maxima": teacher_max.get(p, 20),
            "alocada": carga_prof.get(p, 0),
            "externo": False,
        }) for p in grade_por_professor
    }
    abaixo_alvo = [
        p for p, carga in carga_por_professor.items()
        if not carga.get("externo") and carga.get("alocada", 0) < carga.get("alvo", 0)
    ]
    extras = {
        "carga_por_professor": carga_por_professor,
        "cobertura_professores": cobertura_professores,
        "professores_abaixo_carga_alvo": sorted(abaixo_alvo),
        "professores_por_disciplina": professores_por_disc,
        "docencia_compartilhada_usada": sorted(docencia_compartilhada_usada),
        "disciplinas_externas": sorted(set(disciplinas_externas)),
    }
    return grade_disciplinas, grade_professores, horarios_prof, grade_por_semestre, grade_por_professor, grades_com_prof, extras


def _assinatura_assignments(assignments: Dict[str, dict]) -> str:
    partes = []
    for uid, opcao in sorted(assignments.items()):
        slots = ",".join(f"{d}@{h}" for d, h in sorted(opcao.get("slots", [])))
        profs = ",".join(f"{d}@{h}={p}" for (d, h), p in sorted(opcao.get("slot_professores", {}).items()))
        partes.append(f"{uid}::{slots}::{profs}")
    return "||".join(partes)


def solve_schedule(disciplinas: Sequence[dict], professores: Sequence[dict], config_disc: Sequence[dict],
                   config_prof: Sequence[dict], grupos_choque: Sequence[dict], config_avancadas: dict,
                   variant_seed: int = 0) -> Tuple[dict, dict, dict, dict, dict, dict, dict]:
    """Executa a geração e retorna as mesmas estruturas esperadas pela interface.

    A função sempre devolve um relatório rico. Se a solução não for completa, o
    relatório usa status_geracao='parcial' ou 'impossivel' e lista exatamente as
    disciplinas não alocadas.
    """
    avancadas = normalizar_avancadas(config_avancadas)
    estado_sabado = avancadas["estado_sabado"]
    nivel_max = avancadas["nivel_restricao"]
    itens, teacher_max, teacher_target, teacher_unavailable = _prepare_items(disciplinas, config_disc, professores, config_prof)
    cobertura_professores = analisar_cobertura_professores(disciplinas, professores, config_disc, config_prof)
    choque_por_uid = _prepare_choques(itens, grupos_choque)
    preflight = _preflight(itens, professores, teacher_max, teacher_target, cobertura_professores, choque_por_uid, estado_sabado)
    erros_fatais = [d for d in preflight if d.get("severidade") == "erro"]
    avisos_pre = [d for d in preflight if d.get("severidade") != "erro"]
    relatorio = {
        "erros": [d["detalhes"] for d in erros_fatais],
        "avisos": [d["detalhes"] for d in avisos_pre],
        "diagnosticos": preflight[:],
        "niveis": {},
        "fase1_ok": False,
        "fase2_ok": False,
        "professores_sobrecarga": [],
        "disciplinas_sem_professor": sorted({_nome_disc(x) for x in itens if x.tipo != "externa" and not x.professores_elegiveis}),
        "score": 0,
        "nivel_max_usuario": nivel_max,
        "nivel_usado": None,
        "status_geracao": "impossivel",
        "total_disciplinas": len(itens),
        "disciplinas_alocadas": 0,
        "disciplinas_nao_alocadas": [],
        "aulas_previstas": sum(x.aulas for x in itens),
        "aulas_alocadas": 0,
        "busca_interrompida_por_limite": False,
    }
    if erros_fatais:
        relatorio["disciplinas_nao_alocadas"] = [_nome_disc(x) for x in itens]
        return {}, {}, {}, {}, {}, relatorio, {}
    if not itens:
        relatorio["erros"].append("Nenhuma disciplina selecionada.")
        relatorio["diagnosticos"].append(_diag(
            "sem_disciplinas", "Nenhuma disciplina selecionada",
            "Selecione ao menos uma disciplina antes de gerar a grade.",
            ["Volte à etapa Seleção e escolha disciplinas."], disciplinas=[],
            atalhos=[_atalho("Abrir seleção", "/", "fa-list-check")]))
        return {}, {}, {}, {}, {}, relatorio, {}

    melhor_assignments: Dict[str, dict] = {}
    melhor_ctx: Optional[SearchContext] = None
    melhor_score = -float("inf")
    nivel_solucao = nivel_max
    # Testa níveis progressivamente. Em cada nível, usa dois reinícios curtos.
    for nivel in range(1, nivel_max + 1):
        for restart in range(2):
            assignments, ctx = _executar_nivel(
                itens, teacher_max, teacher_unavailable, choque_por_uid,
                estado_sabado, nivel, segundos=1.6, max_nodes=2500,
                seed=17 + nivel * 101 + restart * 1009 + int(variant_seed) * 100003,
            )
            score = _score_assignments(assignments)
            if len(assignments) > len(melhor_assignments) or (
                len(assignments) == len(melhor_assignments) and score > melhor_score
            ):
                melhor_assignments, melhor_ctx, melhor_score, nivel_solucao = assignments, ctx, score, nivel
            if len(assignments) == len(itens):
                melhor_assignments, melhor_ctx, melhor_score, nivel_solucao = assignments, ctx, score, nivel
                break
        if len(melhor_assignments) == len(itens):
            break

    alocados = set(melhor_assignments)
    nao_alocados = [x for x in itens if x.uid not in alocados]
    if melhor_ctx:
        relatorio["busca_interrompida_por_limite"] = melhor_ctx.timed_out
        for item in nao_alocados:
            # Explica a ausência considerando a melhor solução parcial efetivamente exibida.
            # Isso evita mensagens genéricas obtidas em ramos intermediários da busca.
            state = SolverState(assignments=copy.deepcopy(melhor_assignments))
            for assigned_uid, opcao in melhor_assignments.items():
                assigned_item = next(x for x in itens if x.uid == assigned_uid)
                for slot in opcao.get("slots", []):
                    state.group_occ[(assigned_item.grupo, slot[0], slot[1])] = assigned_uid
                    state.uid_slots[assigned_uid].add(slot)
                if not opcao.get("ignorar_recurso_docente"):
                    for slot, prof in opcao.get("slot_professores", {}).items():
                        state.teacher_occ[slot].add(prof)
                        state.teacher_load[prof] += 1
            diag = _diagnosticar_sem_opcao(item, state, melhor_ctx)
            relatorio["diagnosticos"].append(diag)

    gd, gp, hp, gs, gpp, gcp, extras = _renderizar(
        itens, melhor_assignments, professores, teacher_max, teacher_target, cobertura_professores, estado_sabado, nivel_solucao
    )
    relatorio.update(extras)
    relatorio["score"] = melhor_score if melhor_score != -float("inf") else 0
    relatorio["assinatura_grade"] = _assinatura_assignments(melhor_assignments)
    relatorio["semente_variacao"] = int(variant_seed)
    relatorio["nivel_usado"] = nivel_solucao
    relatorio["disciplinas_alocadas"] = len(melhor_assignments)
    relatorio["disciplinas_nao_alocadas"] = [_nome_disc(x) for x in nao_alocados]
    relatorio["aulas_alocadas"] = sum(len(x.get("slots", [])) for x in melhor_assignments.values())
    relatorio["niveis"] = {_nome_disc(x): (nivel_solucao if x.uid in melhor_assignments else 0) for x in itens}
    relatorio["fase1_ok"] = not nao_alocados
    relatorio["fase2_ok"] = not nao_alocados and not relatorio["disciplinas_sem_professor"]
    if not nao_alocados and not relatorio["disciplinas_sem_professor"]:
        relatorio["status_geracao"] = "sucesso"
    elif melhor_assignments:
        relatorio["status_geracao"] = "parcial"
        if nao_alocados:
            relatorio["avisos"].append(
                f"Grade parcial: {len(melhor_assignments)} de {len(itens)} disciplinas foram alocadas. Revise os diagnósticos antes de usar a grade."
            )
        if relatorio["disciplinas_sem_professor"]:
            relatorio["avisos"].append(
                "Grade parcial: há disciplina(s) sem professor compatível vinculado. Configure a atribuição docente antes de usar a grade como versão final."
            )
    else:
        relatorio["status_geracao"] = "impossivel"
    if relatorio.get("docencia_compartilhada_usada"):
        relatorio["avisos"].append(
            "Docência compartilhada aplicada somente nas disciplinas autorizadas: " +
            ", ".join(relatorio["docencia_compartilhada_usada"])
        )
    if relatorio.get("professores_abaixo_carga_alvo"):
        relatorio["avisos"].append(
            "Há professor(es) abaixo da carga alvo: " + ", ".join(relatorio["professores_abaixo_carga_alvo"]) +
            ". A grade de disciplinas pode estar completa, mas a distribuição docente ainda merece revisão."
        )
    if relatorio["busca_interrompida_por_limite"]:
        relatorio["avisos"].append(
            "A busca atingiu o limite de segurança. O resultado parcial continua válido como diagnóstico, mas pode existir outra combinação possível."
        )
    return gd, gp, hp, gs, gpp, relatorio, gcp
