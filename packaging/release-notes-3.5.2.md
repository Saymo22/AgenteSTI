STI Agente 3.5.2 — Serviço do Windows (piloto)

- Instalador MSI x64 por máquina, com autorização de administrador na instalação inicial.
- Serviço STIAgente com início automático antes do login e funcionamento após logoff.
- Reinício do serviço após falhas e parada controlada pelo Windows.
- Executável em Program Files; configuração, identidade, histórico e logs protegidos em ProgramData\STIService.
- Migração da configuração e do UUID anteriores, sem executar o agente antigo com privilégios elevados.
- Mensagens enviadas à sessão ativa; ausência de usuário é informada ao servidor.
- Atualizações futuras pelo serviço com assinatura, integridade e produto MSI verificados.
- Novo protocolo 3: a release não é oferecida automaticamente aos agentes por usuário.

Atualize primeiro o servidor. Execute o MSI a partir da sessão do usuário da instalação anterior,
confirme a pasta de migração e autorize como administrador. Em uma instalação nova, informe
agent-config.json ou coloque-o ao lado do MSI. Não distribua a chave privada de releases.

Valide em uma estação de teste: instalação, reinício do Windows, funcionamento antes do login,
logoff, atualização e comportamento com Kaspersky ativo. MSI não garante aceitação pelo antivírus.
Suspensão, hibernação e desligamento continuam impedindo o envio de dados.
O teste de internet passa a refletir o acesso da conta do serviço, que pode diferir do navegador.
