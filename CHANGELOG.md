# Changelog

## 2.1.3-local

### Recuperação automática da sessão local
- Corrige o erro de salvamento exibido quando uma aba antiga permanece aberta após reiniciar o servidor local.
- Em caso de token CSRF desatualizado, o servidor devolve um token renovado e a interface repete a alteração automaticamente uma única vez.
- O usuário não precisa mais recarregar manualmente a página para recuperar o salvamento de disciplinas e professores.
- Adiciona teste automatizado para o fluxo: token antigo rejeitado, token renovado recebido e salvamento repetido com sucesso.

## 2.1.2-local

### Disciplinas externas
- Disciplinas marcadas como **Externas** passam a ocupar a grade da turma sem consumir carga nem disponibilidade dos docentes internos.
- A visualização final registra automaticamente **Professor externo**.
- Vínculos internos antigos ou selecionados por engano são removidos automaticamente quando o tipo muda para externo.
- Disciplinas externas deixam de gerar aviso de professor compatível ausente e não entram na cobertura mínima dos professores internos.

### Diagnósticos navegáveis
- O painel de diagnósticos recebeu botões de ação para abrir a disciplina, professor, grupo de conflitos ou configuração avançada relevante.
- Atalhos de flexibilidade, sábado e horários consecutivos apontam diretamente para a opção correta.
- A tela de configuração identifica quando foi aberta por uma recomendação e oferece **Salvar alterações e voltar para gerar**.
- O retorno à geração confirma que as novas regras foram persistidas e serão usadas na próxima tentativa.

### Regeneração de combinações
- O botão **Regerar** passa a explorar sementes diferentes de desempate.
- Quando encontra uma alternativa equivalente, exibe uma nova organização.
- Quando não encontra alternativa equivalente, preserva a grade anterior, informa que não há prova matemática de unicidade e avança o cursor para explorar novas tentativas no próximo clique.
- Uma tentativa nova nunca substitui silenciosamente uma grade anterior por resultado inferior.

### Interface local
- Bootstrap CSS e JavaScript passam a acompanhar o ZIP em `static/vendor/`, mantendo os recursos essenciais da interface disponíveis offline.
- A dependência antiga de jQuery foi removida, pois o frontend atual usa JavaScript nativo.
- Ícones decorativos continuam opcionais e não interferem no uso do sistema quando estiver offline.

### Testes
- 31 testes automatizados, incluindo professor externo, links de recomendação, retorno com alterações salvas e regeneração com ou sem alternativa equivalente.
- Catálogos reais revalidados: Matemática 47/47, Física 53/53, Biologia 55/55 e Química 60/60.

## 2.1.1-local

- Inclui dependências Python portáteis em `vendor/`.
- Remove a criação automática de `.venv` e qualquer chamada a `pip install` no `run_local.bat`.
- Permite abrir a aplicação sem internet após instalar apenas Python 3.10 ou superior.
- Adiciona `diagnostico_local.bat` para verificar Python, dependências locais e importações.
- Atualiza a documentação de instalação e solução de problemas.

## 2.1.0-local

### Atribuição docente por disciplina
- Novo bloco visual **Atribuição docente** em cada disciplina, com seleção organizada e visível de professor(es) fixo(s).
- Reserva opcional de uma disciplina diretamente para um ou mais professores sem fixar horários.
- Uma disciplina reservada deixa de aparecer como opção editável para os demais professores.
- Quando dois ou mais professores fixos são escolhidos, a docência compartilhada é ativada automaticamente e o motor exige a participação de todos.
- O botão de docência compartilhada foi redesenhado com contraste maior e posição mais clara.

### Cobertura mínima de carga docente
- Novo campo **Carga que precisa cumprir** separado do **Limite máximo permitido**.
- Cálculo antecipado de horas potenciais, disciplinas disponíveis e quantidade mínima estimada de disciplinas para alcançar a carga alvo.
- Avisos específicos quando um professor não possui disciplinas suficientes para cumprir sua carga.
- Relatório final destaca professores abaixo da carga alvo mesmo quando a grade das disciplinas está completa.

### Persistência e consistência
- Migração automática de configurações antigas sem professores fixos e sem carga alvo.
- Remoção automática de reservas obsoletas quando um professor deixa a seleção.
- Preservação correta dos vínculos docentes quando disciplinas são removidas ou reordenadas.
- Backups passam a incluir professores fixos e carga alvo.

### Testes
- 24 testes automatizados cobrindo reservas docentes, compartilhamento obrigatório, cobertura insuficiente, importação legada e remapeamento de vínculos.
- Catálogos reais validados: Matemática 47/47, Física 53/53, Biologia 55/55 e Química 60/60.

## 2.0.2-local

### Inicialização local
- Remoção da atualização obrigatória do `pip` em todas as execuções.
- Instalação das dependências somente quando algum pacote necessário estiver ausente.
- Uso direto do Python interno do ambiente virtual, sem depender da ativação do terminal.
- Mensagens específicas para ausência do Python, falha na criação do ambiente virtual, falha de instalação e encerramento inesperado do servidor.
- Ajuste equivalente no inicializador para Linux e macOS.
- Exibição correta do endereço ao usar uma porta personalizada.

## 2.0.1-local

### Salvamento e persistência
- Salvamento atômico conjunto de disciplinas e professores por meio do endpoint `/salvar_selecoes`.
- Fila de salvamento no frontend para preservar a ordem de cliques rápidos.
- Navegação para a configuração aguarda a conclusão da gravação.
- Dados extensos removidos do cookie de sessão do Flask e hidratados do workspace local a cada requisição.
- Indicador visível de sincronização na tela de seleção.

### Testes
- Regressão para salvar simultaneamente disciplinas e professores.
- Regressão com 120 disciplinas e 120 professores garantindo cookie pequeno.
- Regressão para recuperação do estado local em uma nova sessão.

## 2.0.0-local

### Motor
- Busca retroativa limitada com priorização das disciplinas mais difíceis.
- Vinculação de professor integrada à alocação de horários.
- Professor único por disciplina como regra padrão.
- Docência compartilhada somente mediante autorização explícita por disciplina.
- Diagnósticos estruturados e ações recomendadas.
- Resultados `sucesso`, `parcial` e `impossivel`.
- Acúmulo correto de aulas simultâneas em grades combinadas.

### Dados e segurança local
- Persistência atômica por workspace.
- Preparação estrutural para login futuro por coordenador.
- Proteção CSRF, limite de backup, segredo local persistente e modo debug desativado por padrão.
- Bloqueio de leitura externa aos catálogos.
- Validação de formulários, índices, listas, horários e backups.
- Backup completo incluindo grade com professores.

### Interface
- Explicação direta do objetivo na seleção.
- Identificação visual do modo local.
- Resumo da configuração.
- Ferramentas administrativas recolhidas.
- Diagnósticos e métricas mais claros.
- Navegação por teclado nas células interativas.
