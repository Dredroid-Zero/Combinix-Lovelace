# Combinix Lovelace 2.1.2 Local

O **Combinix Lovelace** monta grades acadêmicas automaticamente a partir das disciplinas, professores e restrições definidas pela coordenação. Esta versão foi organizada para uso **local**, em um único computador, mas a persistência já foi separada por `workspace` para facilitar a futura inclusão de login e uma área individual para cada coordenador.



## Novidades 2.1.2 — disciplinas externas, recomendações navegáveis e regeneração

### Disciplinas externas

Uma disciplina marcada como **Externa** pertence a outro curso e não utiliza os docentes selecionados neste workspace. Ela continua ocupando horário na grade da turma, mas aparece automaticamente como **Professor externo**. O sistema remove vínculos internos incompatíveis e não mostra aviso de professor ausente para esse tipo de disciplina.

As disciplinas **Internas** e **Cedidas** continuam seguindo a atribuição docente normal: professor compatível na aba **Professores** ou professor(es) fixo(s) escolhidos diretamente na disciplina.

### Recomendações com atalhos

O painel **Diagnóstico e ações recomendadas** agora inclui botões que abrem diretamente o ponto relevante da configuração. Exemplos: abrir a disciplina que precisa liberar horários consecutivos, ativar sábado, aumentar o nível de flexibilidade, revisar grupos de conflito ou configurar um professor específico.

Ao abrir uma recomendação, a tela exibe o botão **Salvar alterações e voltar para gerar**. Ele salva disciplinas, professores e configurações avançadas em conjunto antes de retornar à geração. Uma confirmação informa que a próxima tentativa já utilizará as regras atualizadas.

### Botão Regerar

O botão **Regerar** passou a explorar combinações diferentes por meio de novas sementes de desempate. Quando encontra uma alternativa com o mesmo nível de conclusão, exibe a nova organização e informa a troca. Quando não encontra alternativa equivalente nas tentativas realizadas, mantém a grade anterior e esclarece que isso pode indicar uma grade muito restrita ou praticamente única, mas não constitui prova matemática de unicidade. Um novo clique explora outro conjunto de tentativas.

## Correção 2.1.1 — execução local sem instalação de pacotes

A edição local agora inclui as bibliotecas Python necessárias na pasta `vendor/`. O arquivo `run_local.bat` não cria ambiente virtual, não executa `pip install` e não precisa acessar a internet. Ele somente verifica se existe Python 3.10 ou superior e inicia o servidor. A partir da versão 2.1.2, os arquivos essenciais do Bootstrap também acompanham o projeto em `static/vendor/`, mantendo abas, modais, botões e avisos funcionais offline. Os ícones decorativos podem ser carregados externamente quando houver conexão, mas não são necessários para operar o sistema.

Também foi incluído `diagnostico_local.bat`. Caso a aplicação não abra, execute esse arquivo e consulte `diagnostico_combinix.txt`.

## Novidades 2.1 — professores fixos e cobertura mínima

Cada disciplina agora possui um bloco visível de **Atribuição docente**. Nele, a coordenação pode:

- deixar a atribuição automática para o motor;
- reservar a disciplina para um professor fixo, sem escolher horário;
- selecionar dois ou mais professores fixos quando desejar docência compartilhada.

Quando uma disciplina é reservada, ela deixa de aparecer como opção editável para os demais professores. Se houver dois ou mais professores fixos, o compartilhamento é ativado automaticamente e todos precisam participar da disciplina.

Na aba **Professores**, a configuração agora separa:

- **Carga que precisa cumprir**: meta semanal do docente;
- **Limite máximo permitido**: teto rígido que o motor não pode ultrapassar.

A tela calcula a cobertura potencial antes da geração e informa quantas horas e quantas disciplinas mínimas são necessárias para alcançar a carga alvo. Esse cálculo é uma estimativa antecipada baseada nas maiores cargas disponíveis; choques de horários e indisponibilidades ainda podem reduzir a alocação final.

## Correção 2.0.1 — salvamento confiável

- Disciplinas e professores agora são gravados juntos em uma única operação atômica.
- Alterações rápidas feitas na tela de seleção entram em uma fila e são salvas na ordem correta.
- O botão **Próximo** aguarda o salvamento terminar antes de abrir a configuração.
- As listas extensas e configurações saíram do cookie do navegador: o cookie mantém apenas identificadores pequenos e os dados completos ficam no workspace local.
- A tela de seleção exibe o estado do salvamento: salvando, salvo ou erro.
- Testes de regressão validam persistência com 120 disciplinas e 120 professores e recuperação por uma nova sessão.

## O que mudou na versão 2.0

- Novo motor de horários isolado em `services/solver.py`.
- Uma disciplina recebe **um único professor por padrão**. A divisão entre docentes somente ocorre quando a opção **Permitir docência compartilhada nesta disciplina** é ativada explicitamente.
- Diagnósticos detalhados para situações impossíveis ou parciais, com ações recomendadas.
- Estados de geração separados: `sucesso`, `parcial` e `impossivel`.
- Grades combinadas acumulam aulas simultâneas de turmas diferentes sem sobrescrever células.
- Fixações no sábado são rejeitadas enquanto o sábado estiver desativado.
- Backups incluem todas as visualizações, inclusive grades com professores.
- Persistência local atômica e separada por workspace.
- Validação de formulários, JSON, catálogos, índices e horários.
- Proteção CSRF para alterações locais, limite de tamanho de backup e bloqueio de caminhos indevidos.
- Modo escuro, resumo de configuração, ferramentas administrativas recolhidas e melhorias de acessibilidade.
- Testes automatizados e teste opcional dos catálogos reais.

## Instalação rápida no Windows

1. Instale Python 3.10 ou superior, caso ele ainda não esteja instalado. Durante a instalação do Python, marque a opção para adicioná-lo ao `PATH`.
2. Extraia o ZIP completo em uma pasta nova.
3. Dê duplo clique em `run_local.bat`.
4. Acesse `http://127.0.0.1:5000` no navegador caso a página não abra automaticamente.

O inicializador não cria ambiente virtual e não instala pacotes. As dependências Python necessárias já acompanham a edição local na pasta `vendor/`, e os arquivos essenciais da interface ficam em `static/vendor/`. Portanto, a operação do sistema não depende de conexão com a internet.

### Caso o sistema não abra

Execute `diagnostico_local.bat`. Ele cria o arquivo `diagnostico_combinix.txt` com a versão do Python, a presença das dependências locais e o resultado do teste de importação.

### Caso apareça uma pergunta sobre finalizar o arquivo em lotes

Essa pergunta normalmente aparece depois de uma interrupção manual com `Ctrl+C`. Responda `S`, feche a janela e execute novamente o `run_local.bat`. A versão `2.1.2-local` não executa `pip install`.

## Execução manual opcional

Requer Python 3.10 ou superior. Na pasta do projeto, execute:

```bash
python app.py
```

No Linux ou macOS, também é possível usar:

```bash
./run_local.sh
```

Acesse `http://127.0.0.1:5000`.

## Fluxo de uso

### 1. Seleção

Selecione disciplinas e professores dos catálogos JSON ou adicione registros manualmente.

### 2. Configuração

Para cada disciplina, defina tipo, aulas semanais, semestre de oferta, horários fixos e horários restritos. No bloco **Atribuição docente**, deixe a escolha automática ou reserve a disciplina diretamente para um ou mais professores. A docência compartilhada fica desativada por padrão; ao escolher dois ou mais professores fixos, ela é ativada automaticamente.

Quando o tipo for **Externa**, a atribuição interna é desativada: a disciplina aparecerá como **Professor externo** e não consumirá carga dos docentes do curso.

Na aba **Professores**, configure carga alvo, limite máximo, disciplinas compatíveis e indisponibilidades. Disciplinas reservadas aparecem bloqueadas para o professor fixo e não ficam disponíveis para os demais. Na aba **Conflitos**, agrupe disciplinas que não podem ocorrer simultaneamente. Na aba **Avançadas**, ajuste sábado e nível de flexibilização.

### 3. Geração

O motor tenta primeiro as regras mais rígidas e flexibiliza progressivamente até o limite escolhido. O resultado apresenta:

- quantidade de disciplinas e aulas alocadas;
- disciplinas pendentes;
- nível de flexibilização usado;
- professor ou professores responsáveis por cada disciplina;
- avisos de docência compartilhada;
- diagnósticos com alterações recomendadas e atalhos para a configuração correspondente;
- resultado da regeneração, informando se outra combinação foi encontrada.

Uma grade **parcial** é exibida como prévia para ajudar a corrigir os conflitos, mas não deve ser usada como versão final. Isso inclui grades cujos horários foram encaixados, mas que ainda possuem disciplinas sem professor compatível vinculado.

## Diagnósticos do motor

O motor identifica, entre outros casos:

- disciplina duplicada;
- fixações acima da carga semanal;
- horário simultaneamente fixado e restrito;
- horário inválido;
- fixação no sábado enquanto o sábado está desativado;
- restrições excessivas;
- carga da turma maior do que a capacidade semanal;
- colisões entre fixações da mesma turma;
- colisões em grupos de conflito;
- disciplina sem professor compatível vinculado;
- ausência de um professor com carga suficiente para assumir sozinho uma disciplina;
- quantidade de professores fixos maior do que a quantidade de aulas da disciplina;
- cobertura insuficiente de disciplinas para um professor cumprir sua carga alvo;
- bloqueios de disponibilidade ou choque de agenda docente;
- busca interrompida pelo limite de segurança.

Cada diagnóstico possui uma explicação, ações sugeridas e, quando aplicável, botões que levam diretamente ao ponto de configuração correspondente. Entre os atalhos estão liberar horários, rever fixações, ativar sábado, aumentar flexibilidade, configurar um docente e revisar grupos de conflito.

Detalhes técnicos adicionais estão em [`docs/MOTOR_DE_HORARIOS.md`](docs/MOTOR_DE_HORARIOS.md).

## Catálogos JSON

Os arquivos base ficam nas pastas:

```text
disciplinas/
professores/
```

Exemplo de disciplina:

```json
{
  "nome": "Cálculo I",
  "codigo": "MAT101",
  "curso": "Matematica",
  "semestre": 1,
  "carga_horaria": 60
}
```

Exemplo de professor:

```json
{
  "nome": "Ada Lovelace"
}
```

Os nomes dos catálogos são carregados somente a partir dos arquivos `.json` existentes nessas pastas. Caminhos externos não são aceitos.

## Persistência, backups e futura autenticação

No modo atual, os dados ficam neste computador. O workspace ativo é `local` e seus arquivos são gravados em:

```text
database/workspaces/local/
```

O botão de exportação gera um backup JSON completo. A área de importação restaura backups válidos e rejeita estruturas corrompidas ou horários desconhecidos.

As seleções completas e configurações ficam nesses arquivos locais, não no cookie do navegador. A separação por workspace foi criada para a evolução futura. Quando houver autenticação, o identificador `local` poderá ser substituído internamente pelo ID do coordenador autenticado, isolando seleções, configurações e resultados.

## Segurança e publicação futura

Esta edição foi preparada para **uso local** em `127.0.0.1`. Ela não deve ser publicada diretamente na internet como servidor multiusuário.

Antes de uma versão online, implemente autenticação, banco de dados transacional, autorização por coordenador, testes de concorrência, HTTPS, gerenciamento de segredos e implantação por um servidor WSGI adequado. O código já deixa explícito o ponto onde o workspace deverá ser associado ao usuário autenticado.

## Testes

Execute a suíte rápida:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Execute também o teste opcional dos catálogos incluídos:

```bash
python tests/smoke_catalogs.py
```

## Estrutura principal

```text
app.py                     rotas, validações e interface Flask
persistence.py             persistência local atômica por workspace
services/solver.py          motor de geração e diagnósticos
templates/                  páginas HTML
static/                     CSS, JavaScript, Bootstrap local e imagens
disciplinas/                catálogos base de disciplinas
professores/                catálogos base de professores
tests/                      testes automatizados
docs/                       documentação técnica
```

## Versão

`2.1.2-local`
