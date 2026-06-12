# Modo web demonstrativo na Vercel

## Objetivo

A Vercel não deve ser utilizada para gravar os JSONs locais durante a execução. A versão 2.2.2 ativa automaticamente o modo `browser` quando a variável `VERCEL` está presente.

## Onde os dados ficam

O navegador mantém um snapshot com:

- disciplinas e professores selecionados;
- configurações das disciplinas;
- professores fixos e docência compartilhada;
- configurações dos professores;
- indisponibilidades;
- conflitos;
- parâmetros avançados;
- última grade gerada e relatório.

O snapshot fica no IndexedDB da origem. `localStorage` é somente fallback. O frontend sobrescreve o estado atual, sem criar histórico ilimitado.

## Fluxo técnico

1. A página-loader lê o IndexedDB.
2. O snapshot é enviado temporariamente para o endpoint Flask.
3. O Flask processa a página ou alteração em memória.
4. Respostas JSON devolvem o snapshot atualizado.
5. O frontend grava novamente o IndexedDB.

Downloads e exportações utilizam POST com o snapshot para gerar o arquivo em memória.

## Capacidade e margem operacional

O IndexedDB utiliza a cota disponibilizada pelo navegador, que pode ser maior do que a capacidade do `localStorage`. Entretanto, o snapshot precisa atravessar a função da Vercel para que o motor Python processe a grade. Por isso, o Combinix aplica um limite operacional de **3 MiB** ao estado web e de **4 MiB** aos backups importados nesse modo. Ao ultrapassar 2,5 MiB, a interface recomenda exportar backup e limpar resultados antigos.

O estado atual é sobrescrito. Downloads Excel e JSON ficam na pasta de downloads do usuário e não aumentam o snapshot salvo no navegador.

## Limitações

- Os dados não sincronizam entre navegadores ou computadores.
- Limpar dados do site pode remover o estado salvo.
- Navegação anônima não deve ser utilizada como armazenamento permanente.
- Esse modo não possui login e não é uma solução multiusuário.

## Evolução recomendada

Quando forem criadas contas para coordenadores, migrar o estado para Postgres. O IndexedDB pode permanecer como cache local, recuperação offline e rascunho antes da sincronização.
