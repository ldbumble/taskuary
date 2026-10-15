# Como funciona

Referência, não configuração. Esta página descreve como aplicativo trata mensagens, onde colocar instruções e por que cada item chega a determinado lugar.

## Aba Assistente

Duas partes, mesmo objetivo: mostrar o que precisa de você, um item por vez.

**Fluxo**, à esquerda: itens ordenados por necessidade, não por chegada. Novos itens entram e ocupam posição por prioridade. Faixas, em ordem:

- **Agente aguardando você**: pergunta, aprovação ou bloqueio que impede trabalho.
- **Em breve**: reunião nas próximas duas horas ou mensagem de remetente marcado urgente.
- **Resposta pendente**: rascunho de resposta ou ação aguardando aprovação.
- **Pedido para você**: alguém pediu algo e ninguém assumiu.
- **Atrasado**: pedido sem resposta, promessa ou conversa sem andamento.
- **Concluído**: relatório recebido ou agente que terminou trabalho.
- **Informativo**: informação que pode ser lida sem ação.
- **Agente trabalhando**: nada para você até agente parar ou perguntar; aparece acima do fluxo.

Fluxo contém itens não lidos. Mostrar item na conversa marca como lido e remove do fluxo. Pendências voltam sozinhas: rascunho adiado, agente parado ou contato ainda não retomado. Configurações → Assistente limita período e quantidade de itens. Número identifica tarefa; `+2` indica mais mensagens da mesma conversa.

**Conversa**, à direita: Taskuary apresenta trabalho já avaliado pela triagem. Agentes e redator executam. Cartões permitem aprovar e enviar, responder ao agente, delegar, dispensar, concluir ou adiar. Botões usam mesmas operações disponíveis em outras telas.

Pedidos em linguagem natural recebem confirmação do que aconteceu:

- **próximo, concluído, depois, amanhã**: avançar ou adiar.
- **responda dizendo X**: incluir intenção no rascunho.
- **aprovar**: enviar rascunho como está.
- **não é nosso, nunca mais, remetente irrelevante**: arquivar e registrar veredito.
- **lembre que X**: guardar nota.
- **enviar ao agente de código**: criar tarefa e iniciar agente.
- **encerrar**: concluir tarefa; dispensar antes eventual rascunho pendente.
- **parar agente, finalizar sessão**: terminar sessão; finalização também arquiva relatório e encerra tarefa.
- **dividir**: separar mensagem com dois trabalhos em duas tarefas.
- **ignorar todos X de Y**: marcar como lidos e registrar regra permanente.
- **configurar algo**: abrir orientação com assistente, sem exigir código.

Pergunta recebe resposta, não execução. Correção é acolhida, não tratada como pedido de próximo item.

## Etapas pelas quais mensagens passam

Regras determinísticas primeiro. Documentos orientam interpretação; configurações, políticas, vereditos e regras do fluxo atuam fora do modelo, antes e depois dele.

1. **Já recebida?** ID existente impede duplicação.
2. **Configuração do conector.** Fonte `feed` vai apenas à linha do tempo: sem triagem, chamada de IA ou tarefa. Permissões de tracker e respostas do GitHub também prevalecem.
3. **Suas políticas.** Configurações → Políticas aplica ações por palavra-chave, remetente, domínio, endereço automático ou primeiro contato, antes da IA.
4. **Veredito sobre conversa.** Decisão de que não há trabalho pode arquivar próximas mensagens da mesma conversa. Veredito sobre remetente ou assunto é evidência, não veto permanente.
5. **Atalhos sem modelo.** Convites, notificações de trackers e ruído evidente.
6. **Triagem (`TRIAGE.md`).** Lê regras, `SOUL.md`, responsabilidades em `JOB.md`, aprendizado em `LEARNED.md`, notas pertinentes e contexto da mensagem. Decide se há trabalho e quem executa. Valores técnicos continuam `task`, `reply_only`, `fyi`, `coding` e `general` conforme contrato.
7. **Limites após decisão.** Primeiro contato desconhecido não inicia agente automaticamente. Resposta sempre passa por revisão. Mensagem de tarefa aberta se associa àquela tarefa, não a outra parecida; resposta após encerramento pode representar novo trabalho.
8. **Fluxo.** Marketing, itens arquivados e seus próprios e-mails enviados ficam fora. Período, limite e regras permanentes filtram itens tranquilos sem esconder pedidos reais.

## Onde instruções ficam

- **Configuração ou opção do conector**: decisão determinística, prevalece sobre demais instruções. Mudanças propostas exigem aprovação. Somente roteamento e visibilidade podem ser propostos.
- **Política**: filtro determinístico por remetente, palavra-chave ou domínio, em Configurações → Políticas.
- **Regra permanente**: filtro do fluxo por remetente e família de assuntos. Não apaga mensagens; elas continuam na linha do tempo.
- **Nota de memória**: evidência para triagem avaliar semelhança. Orienta julgamento sem esconder exceções importantes.

Se orientação não produzir efeito esperado: nota convence, regra filtra, configuração decide.
