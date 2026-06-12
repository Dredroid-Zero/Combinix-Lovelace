# Motor de Horários V2.1.3

## Objetivo

O motor recebe disciplinas, professores, restrições, fixações e grupos de conflito. Ele tenta produzir uma grade completa respeitando regras pedagógicas e disponibilidade docente. Quando isso não é possível, devolve a melhor prévia parcial encontrada e explica os bloqueios.

## Regra de professor único

Cada disciplina usa um único professor por padrão. Esse vínculo é escolhido junto com os horários da disciplina, e não depois da criação da grade. Isso elimina o comportamento antigo em que aulas da mesma disciplina podiam ser distribuídas silenciosamente entre docentes diferentes.

A divisão entre professores somente é aceita quando a configuração da disciplina contém:

```json
{
  "permitir_multiplos_professores": true
}
```

Mesmo autorizada, a divisão é usada apenas quando necessária ou vantajosa para viabilizar a grade. O relatório lista toda disciplina em que ela foi aplicada.

## Professores fixos por disciplina

A coordenação pode reservar uma disciplina diretamente para um ou mais docentes, sem fixar horários:

```json
{
  "professores_fixos": ["Ada Lovelace"]
}
```

Quando existe um professor fixo, a disciplina fica reservada a ele e deixa de ser ampliada silenciosamente pela aba de professores. Quando existem dois ou mais professores fixos, a configuração representa uma escolha intencional de docência compartilhada:

```json
{
  "professores_fixos": ["Ada Lovelace", "Grace Hopper"],
  "permitir_multiplos_professores": true
}
```

Nesse caso, o motor exige que todos os professores fixos participem. Se houver mais professores fixos do que aulas semanais, ou se a capacidade conjunta não for suficiente, a geração é bloqueada com diagnóstico específico.


## Disciplinas externas

Uma disciplina com `tipo: "externa"` pertence a outro curso. Ela participa normalmente da ocupação da turma, mas não utiliza recursos docentes internos:

```json
{
  "tipo": "externa"
}
```

O solver ignora professores fixos internos eventualmente presentes em dados antigos, não exige vínculo na aba de professores e renderiza o responsável como `Professor externo`. Disciplinas externas também ficam fora do cálculo de cobertura mínima dos docentes internos.

## Cobertura mínima da carga docente

Cada professor possui dois valores distintos:

```json
{
  "carga_alvo": 20,
  "carga_maxima": 20
}
```

- `carga_alvo`: quantidade que a coordenação pretende cumprir;
- `carga_maxima`: teto rígido que o motor nunca pode ultrapassar.

Antes da busca, o sistema soma as horas potenciais das disciplinas disponíveis para cada professor. Também estima a quantidade mínima de disciplinas necessária para atingir a meta, usando primeiro as disciplinas com maior carga semanal. A estimativa serve como alerta antecipado: a distribuição final ainda depende dos horários e das indisponibilidades.

## Estratégia de busca

O motor utiliza busca retroativa limitada com estas etapas:

1. validação prévia de contradições evidentes;
2. decomposição das aulas em blocos pedagógicos;
3. ordenação dinâmica das disciplinas mais difíceis;
4. teste conjunto de horários e professor responsável;
5. retrocesso quando uma escolha bloqueia o restante da grade;
6. progressão do nível 1 ao nível máximo autorizado;
7. preservação da melhor solução parcial para diagnóstico;
8. uso opcional de sementes de variação para explorar combinações alternativas ao regenerar.

A busca possui limite de tempo e de nós para evitar travamentos. Quando esse limite é atingido, o relatório informa que pode existir outra combinação possível.

## Níveis

- **Nível 1 — rígido:** prioriza blocos distribuídos em dias diferentes e evita o último horário.
- **Nível 2 — moderado:** aceita repetição controlada e último horário somente em condições específicas.
- **Nível 3 — flexível:** amplia as alternativas, inclusive sábado conforme a configuração escolhida.

## Estados de retorno

- `sucesso`: todas as disciplinas foram alocadas.
- `parcial`: a prévia contém parte das disciplinas ou ainda possui disciplinas sem professor compatível vinculado; deve ser revisada.
- `impossivel`: contradições prévias ou ausência total de alocação impedem uma grade utilizável.

## Diagnósticos

Cada diagnóstico contém:

```json
{
  "codigo": "professor_sem_carga_suficiente",
  "titulo": "Nenhum professor consegue assumir sozinho a disciplina",
  "detalhes": "...",
  "acoes": ["..."],
  "severidade": "erro",
  "disciplinas": ["..."],
  "atalhos": [{"rotulo": "Abrir disciplina", "href": "/config?..."}]
}
```

O campo `atalhos` alimenta o painel de correção assistida: cada botão conduz ao ponto relevante da configuração. Ao retornar à geração, as alterações visíveis são salvas em conjunto antes de uma nova tentativa.

## Regeneração

O botão **Regerar** executa novas sementes de desempate e compara o novo resultado com a grade anterior. Uma alternativa somente substitui a grade visível quando preserva ao menos o mesmo nível de conclusão. Quando nenhuma alternativa equivalente é encontrada, a grade anterior permanece ativa e o relatório esclarece que as tentativas realizadas não provam unicidade matemática. O cursor avança para que cliques seguintes explorem novas combinações.

Entre os novos diagnósticos estão:

- `professores_fixos_excedem_aulas`;
- `professores_fixos_sem_carga`;
- `professor_cobertura_insuficiente`;
- `carga_alvo_acima_do_limite`.
