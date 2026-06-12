# Combinix Lovelace 2.2.0 Híbrido

O **Combinix Lovelace** monta grades acadêmicas automaticamente a partir das disciplinas, professores e restrições definidas pela coordenação. A versão 2.2.0 possui persistência **híbrida**: continua funcionando localmente com arquivos JSON e também pode ser publicada na Vercel como demonstração web, salvando os dados somente no navegador de cada visitante.



## Novidades 2.2.0 — modo web demonstrativo com IndexedDB

A aplicação detecta automaticamente quando está sendo executada na **Vercel**. Nesse ambiente, ela deixa de tentar alterar arquivos na hospedagem e utiliza o navegador como armazenamento.

- **IndexedDB** é o armazenamento principal, pois oferece capacidade maior do que `localStorage`.
- `localStorage` permanece somente como fallback para navegadores que não disponibilizem IndexedDB.
- A interface mostra o backend utilizado, o tamanho do estado atual, o uso total daquela origem e a cota informada pelo navegador.
- O botão **Proteger armazenamento** solicita ao navegador uma proteção adicional contra remoções automáticas em situações de pouco espaço. O navegador pode aceitar ou recusar.
- O botão **Exportar backup** continua disponível e é recomendado para preservar uma cópia externa.
- O botão **Limpar dados** remove seleções, configurações e grades somente daquele navegador.

O modo web mantém apenas o estado atual. As alterações sobrescrevem o snapshot anterior, portanto não existe crescimento ilimitado a cada clique. O armazenamento é separado por domínio, navegador e dispositivo: ainda não existe sincronização entre computadores nem login.

Em outros serviços de hospedagem, o modo navegador pode ser ativado manualmente com:

```text
COMBINIX_STORAGE_MODE=browser
```

## Correção 2.1.4 — avanço confiável para a configuração

Ao clicar em **Próximo: Configurar**, a seleção atual é gravada novamente e o servidor confirma a releitura do arquivo antes de abrir a etapa seguinte. O navegador também mantém uma cópia defensiva das listas. Caso a configuração chegue vazia após uma interrupção inesperada, o sistema tenta restaurar essa cópia automaticamente uma única vez e informa a recuperação.

## Correção 2.1.3 — recuperação automática do salvamento

Quando o servidor local é reiniciado enquanto uma aba antiga permanece aberta no navegador, o token de segurança anterior deixa de ser válido. A interface agora renova esse token automaticamente e repete o salvamento uma única vez, sem exigir que o usuário recarregue a página.

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

Essa pergunta normalmente aparece depois de uma interrupção manual com `Ctrl+C`. Responda `S`, feche a janela e execute novamente o `run_local.bat`. A versão `2.2.0-hybrid` não executa `pip install`.

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

### Modo local

Ao executar `run_local.bat`, os dados ficam no computador em:

```text
database/workspaces/local/
```

A escrita é atômica e mantém somente o estado atual e um backup anterior. Os resultados gerados ficam em `database/resultados.json`.

### Modo web demonstrativo

Na Vercel, o sistema ativa automaticamente o armazenamento no navegador. O estado completo — seleções, configurações e última grade — é mantido no **IndexedDB** daquela origem. Caso IndexedDB não esteja disponível, o frontend utiliza `localStorage` como fallback.

A capacidade efetiva do IndexedDB varia conforme navegador, sistema operacional e espaço disponível. A interface consulta `navigator.storage.estimate()` e mostra a cota informada pelo navegador. Como segurança adicional, exporte backups JSON periodicamente.

Embora o IndexedDB possa oferecer uma cota maior, o snapshot precisa atravessar uma função da Vercel para que o motor Python processe a grade. Para preservar uma margem segura no transporte, o Combinix limita o estado web sincronizado a **3 MiB** e os backups importados no modo web a **4 MiB**. A interface avisa quando o estado atual passa de 2,5 MiB. As exportações baixadas não são acumuladas dentro do IndexedDB.

Os dados podem deixar de estar disponíveis se o usuário limpar os dados do site, utilizar navegação anônima, trocar de navegador, trocar de computador ou acessar outro domínio. Esse modo é apropriado para demonstração e testes individuais, não para colaboração entre coordenadores.

### Evolução futura

O botão de exportação gera um backup JSON completo. A área de importação restaura backups válidos e rejeita estruturas corrompidas ou horários desconhecidos.

Quando houver autenticação, o modo web deverá migrar para um banco de dados associado ao coordenador autenticado. O IndexedDB poderá continuar sendo utilizado como cache local e mecanismo de recuperação.

## Segurança e publicação futura

A versão local continua adequada para uso individual em `127.0.0.1`. Na Vercel, a versão 2.2.0 funciona como **modo web demonstrativo**: cada navegador possui seu próprio estado e o servidor não grava arquivos durante a execução.

Esse modo ainda não substitui uma versão multiusuário. Antes de disponibilizar contas para coordenadores, implemente autenticação, banco de dados transacional, autorização por usuário, políticas de backup, testes de concorrência e gerenciamento de segredos.

A proteção CSRF do modo navegador utiliza um cookie próprio do domínio, evitando depender da persistência do sistema de arquivos da Vercel.

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
templates/                  páginas HTML e loader do IndexedDB
static/                     CSS, JavaScript, IndexedDB, Bootstrap local e imagens
disciplinas/                catálogos base de disciplinas
professores/                catálogos base de professores
tests/                      testes automatizados
docs/                       documentação técnica
```

## Versão

`2.2.0-hybrid`
