STI Agente 3.5.3 — Correção do MSI de serviço (piloto)

- Corrige a passagem da pasta anterior para as ações do MSI: caminhos com espaços e barra final não juntam mais argumentos nem provocam falha na configuração/migração.
- Quando o JSON da instalação anterior foi apagado, permite usar agent-config.json ao lado do MSI, preservando a identidade anterior encontrada.
- Mantém a rejeição de caminhos explícitos inválidos e de migração sem identidade, para não recriar o cadastro silenciosamente.
- Ativa o log do Windows Installer para facilitar o diagnóstico.
- Mantém serviço STIAgente, início automático antes do login, funcionamento após logoff e dados protegidos em ProgramData\STIService.
- Corrige o servidor para importar releases do serviço (formato 3), mantendo a chave STI original e distinguindo incompatibilidade de formato de assinatura inválida.

Atualize primeiro o servidor para aceitar releases de serviço (protocolo 3).
Não substitua a release 3.5.2 por outro conteúdo: importe a nova 3.5.3.
A migração inicial exige administrador. Coloque agent-config.json ao lado do MSI;
se a instalação anterior foi apagada completamente, deixe a pasta de migração vazia.
Preserve qualquer identity.db restante para manter o cadastro anterior.
Desinstale pelo Windows em vez de apagar arquivos de uma instalação MSI.

Valide instalação, reinício, logoff e comunicação em uma estação piloto com Kaspersky ativo.
Os testes locais de pacote e migração não substituem essa validação real do serviço.
Suspensão, hibernação e desligamento continuam impedindo a execução.
