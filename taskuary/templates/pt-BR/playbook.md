# Lançar uma transação de cartão como conta a pagar
when:      uma transação ou linha de extrato do feed do cartão; um e-mail do emissor do cartão com um extrato anexado
uses:      quickbooks (write: bills, vendors)  ·  teller (read)
steps:     associe o estabelecimento a um fornecedor (crie um só se o dono disser) → escolha a
           conta de despesa pelo memo e pelo histórico do fornecedor → crie a conta com a data da
           transação, memo = últimos 4 dígitos do cartão + id da transação → anexe o recibo se tiver chegado um
alone:     contas abaixo de $500 de um fornecedor já visto, em um período aberto
ask first: um fornecedor novo · qualquer coisa acima de $500 · um período fechado · uma divisão entre contas
done when: a conta existe no QuickBooks e o DocNumber dela está na tarefa

<!-- Um playbook é como ESTA empresa faz UM tipo de trabalho, escrito para o agente que vai fazê-lo.
Mantenha as seis linhas acima - `when` é o que a triagem compara com uma mensagem nova, `uses` nomeia as
conexões que ele toca (o card de cada uma mostra este playbook), `alone` e `ask first` são a
linha entre "só faça" e "pergunte ao dono na sessão", e `done when` é o comprovante.
Tudo abaixo delas é seu: regras da casa, exemplos, os ids e nomes que um agente de outro modo
teria de perguntar. Apague este playbook se o exemplo não servir; o primeiro de verdade é redigido
para você quando um agente termina um tipo de trabalho pela primeira vez.
Os rótulos (when, uses, steps, alone, ask first, done when) e os nomes de conectores ficam em inglês: o Taskuary os lê. -->
