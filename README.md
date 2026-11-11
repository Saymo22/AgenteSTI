# STI Command Center — V3.4.3

Monitoramento e gerenciamento de máquinas Windows, com servidor Flask/Waitress, banco SQLite e agente para os computadores dos usuários.

A rede padrão foi preservada: **10.2.116.0/22**, com os segmentos **116, 117, 118 e 119** no painel. O endereço padrão do servidor nos agentes continua **10.2.116.121:5000**.

## O que esta versão melhora

- Instalador Windows por usuário, inicialização com o login e desinstalação pelas configurações do Windows.
- Releases assinadas, versões dos agentes no painel, distribuição por grupo piloto ou para todos e janela de horário.
- Atualização automática pela comunicação com o servidor STI, com verificação do pacote e recuperação da versão anterior quando a nova não inicia ou não confirma comunicação.
- Telemetria validada: nome, usuário, versão do Windows, CPU, RAM, disco, uptime e impressoras.
- Presença da máquina por ping separada da comunicação recente do agente.
- Comandos condicionados às capacidades e à disponibilidade do agente.
- Reentrega de comandos sem confirmação, expiração e registro local de resultados para evitar execução duplicada após falhas.
- Histórico persistente e pesquisa corrigidos; acompanhamento do resultado dos comandos no painel.
- Cadastro por setor, sala e responsável, com filtros combinados, agrupamento e exportação no inventário.
- Escape seguro de atributos HTML, proteção dos CSVs contra fórmulas, limitação de tentativas de login e cabeçalhos de segurança.
- Configuração externa, sem senha ou token embutido nos fontes ou no executável.
- JavaScript/CSS separados e Chart.js 4.5.1 distribuído localmente para funcionar sem CDN. Fontes externas são opcionais; há fontes de fallback.
- Migração aditiva do SQLite: mantém os registros existentes ao acrescentar os novos campos.

## Estrutura

```text
AgenteSTI/
├── app.py                      # Entrada do servidor no PyCharm / WSGI
├── agente.py                   # Entrada do agente Windows
├── preparar_config.py          # Entrada da preparação inicial
├── requirements.txt            # Dependências de execução
├── sti/
│   ├── servidor/
│   │   ├── app.py              # API, scanner, autenticação e fila
│   │   ├── relatorios.py       # Relatórios e exportação
│   │   ├── organizacao.py      # Cadastro administrativo das máquinas
│   │   ├── releases.py         # Publicação e distribuição das atualizações
│   │   ├── templates/          # Páginas HTML
│   │   └── static/             # CSS, JavaScript, imagens e bibliotecas
│   ├── agente/
│   │   ├── cliente.py          # Telemetria e comandos do agente
│   │   ├── instalacao.py       # Instalação e registro no Windows
│   │   └── atualizacao.py      # Download, troca e recuperação do executável
│   └── comum/
│       ├── configuracao.py     # Configuração compartilhada
│       ├── versao.py           # Versão única do agente
│       └── releases.py         # Assinatura e validação dos pacotes
├── scripts/
│   ├── preparar_config.py      # Geração dos arquivos locais
│   ├── chave_release.py        # Preparação da chave de assinatura
│   └── gerar_release.py        # Build e release assinada
├── config/
│   └── sti-config.example.json # Exemplo sem credenciais
├── requirements/
│   ├── dev.txt                 # Dependências para build
│   └── windows-lock.txt        # Versões validadas no Windows
├── packaging/
│   ├── STI_Agente_V3_4.spec     # Build atual do agente
│   ├── STI_Agente_Setup.spec    # Build do instalador
│   └── legacy/                 # Especificações antigas
└── tests/                      # Testes Python e JavaScript
```

Os três arquivos de entrada na raiz são pequenos inicializadores; a implementação fica em `sti/`. Isso mantém os nomes usados nas configurações de execução do PyCharm. Os URLs `/static/...` e as rotas do painel permanecem iguais.

O `monitor.db`, o `sti-config.json` do servidor e o `agent-config.json` continuam na raiz local para preservar a instalação existente. O código resolve esses caminhos a partir da raiz do projeto, mesmo quando iniciado de outro diretório. No executável, o JSON continua sendo lido ao lado do `.exe`.

Banco, configurações com segredos, ambiente virtual, cache, `.idea/`, `build/` e `dist/` são locais e ficam fora do versionamento. Os arquivos antigos continuam existindo no histórico Git; o token anteriormente publicado deve ser substituído em todos os agentes.

## Instalar no PyCharm

Use Python **3.12** para reproduzir o ambiente validado nesta entrega. O agente exige Windows e `pywin32`. O backend também contém suporte a ping em Linux, mas a validação desta versão ocorreu em Windows.

1. Abra a pasta do projeto no PyCharm.
2. Configure o interpretador do projeto para um ambiente virtual. Nesta cópia local, foi preparado `.venv\Scripts\python.exe`.
3. Instale `requirements.txt` com esse interpretador. Para gerar executáveis, use `requirements/dev.txt`.
4. Crie configurações de execução separadas para `preparar_config.py`, `app.py` e `agente.py`, com a pasta do projeto como diretório de trabalho.

Pelo terminal PowerShell, uma instalação nova pode ser feita assim:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements/windows-lock.txt` registra as versões exatas usadas nos testes e no build Windows/Python 3.12. Para reproduzir o ambiente completo, instale esse arquivo em um ambiente virtual novo. Ele também inclui as ferramentas de build.

## Preparar a configuração

Execute **uma vez** `preparar_config.py`, pelo PyCharm ou pelo terminal:

```powershell
.\.venv\Scripts\python.exe preparar_config.py
```

Ele cria dois arquivos ignorados pelo Git:

- **`sti-config.json`**: configuração do servidor, incluindo senha administrativa, token dos agentes e chave de sessão, gerados aleatoriamente.
- **`agent-config.json`**: configuração para distribuir aos agentes; inclui somente endereço, token e opções do agente, sem senha administrativa ou chave de sessão.

O script não sobrescreve configurações existentes. Na cópia local desta entrega, os dois arquivos já foram gerados. Abra `sti-config.json` no PyCharm para consultar ou editar a senha de login. Confira se `STI_SERVER_IP` em `agent-config.json` corresponde à máquina que executará o servidor.

**Não distribua o `sti-config.json` do servidor aos usuários.** No instalador, importe `agent-config.json`. Na execução portátil, renomeie uma cópia dele para `sti-config.json` ao lado do executável.

As variáveis de ambiente têm prioridade sobre o JSON. `STI_CONFIG_FILE` permite apontar para outro arquivo. Sem essa variável, o JSON é procurado na raiz do projeto ou junto ao executável empacotado. Não há leitura automática de `.env`.

## Iniciar o servidor

Execute `app.py` no PyCharm ou:

```powershell
.\.venv\Scripts\python.exe app.py
```

O processo valida os segredos, prepara/migra o banco, carrega o inventário, inicia o scanner e serve a aplicação com Waitress. A configuração gerada escuta em `0.0.0.0:5000` para receber os agentes da rede. Acesse pelo IP real do servidor, por exemplo [10.2.116.121:5000](http://10.2.116.121:5000), ou [localmente](http://127.0.0.1:5000).

Permita a porta necessária no firewall para a rede de trabalho. Para manter os dados existentes, o padrão usa `monitor.db` junto de `app.py`. Faça backup antes da primeira atualização. Se for copiar o banco diretamente, pare o servidor; para backup enquanto ele estiver ativo, use a API de backup do SQLite que considere o modo WAL.

### Configuração do servidor

| Chave | Padrão do código | Finalidade |
| --- | --- | --- |
| `STI_ADMIN_PASSWORD` | vazio | Senha administrativa; obrigatória. |
| `STI_AGENT_TOKEN` | vazio | Token compartilhado com os agentes; obrigatório. |
| `STI_SECRET_KEY` | vazio | Assinatura das sessões; obrigatória. |
| `STI_HOST` | `127.0.0.1` | Interface de escuta; o arquivo gerado usa `0.0.0.0`. |
| `STI_PORT` | `5000` | Porta do servidor. |
| `STI_DB_FILE` | `monitor.db` junto ao código | Caminho do SQLite. |
| `NETWORK` | `10.2.116.0/22` | Rede IPv4 autorizada e varrida; limite de 4096 endereços. |
| `SCAN_INTERVAL` | `30` | Pausa após cada varredura, em segundos; mínimo 10. |
| `OFFLINE_THRESHOLD` | `90` | Prazo de presença da máquina e heartbeat do agente; mínimo 30 segundos. |
| `MAX_WORKERS` | `40` | Concorrência dos pings; de 1 a 100. |
| `COMMAND_TTL` | `300` | Prazo de entrega/aceitação do comando, em segundos; mínimo 60. |
| `COMMAND_RUNNING_TTL` | `3600` | Prazo para resultado após aceitação; nunca menor que `COMMAND_TTL`. |
| `STI_HTTPS` | `false` | Marca cookies como Secure quando o acesso ocorre por HTTPS; não configura TLS. |

Use **um único processo** do servidor: o inventário e o scanner ficam em memória. Para WSGI externo, utilize a factory `app:create_app`, com inicialização, em vez de importar `app:app` diretamente. Exemplo: `waitress-serve --call --host=0.0.0.0 --port=5000 app:create_app`.

A duração do ciclo inclui a varredura mais `SCAN_INTERVAL`. Para que um agente seja considerado disponível, seu intervalo de envio deve ser menor que `OFFLINE_THRESHOLD`, com margem para coleta e conexão.

## Executar nas máquinas dos usuários

O agente pode rodar a partir de `agente.py` com as dependências instaladas, ou pelo executável independente:

```powershell
.\.venv\Scripts\python.exe agente.py
```

Para distribuir, use **`STI_Agente_Setup_3.4.3.exe`**, importe `agent-config.json`, confira o servidor e instale. Não é necessário instalar Python na estação. O instalador também permite preencher servidor, porta, token e HTTPS diretamente.

A instalação fica em **`%LOCALAPPDATA%\STI\Agent`**, na conta que executa o instalador. Por padrão, registra a inicialização no login dessa conta e uma entrada em **Aplicativos instalados** do Windows. O agente funciona na sessão do usuário, preservando as mensagens no desktop; não é um serviço de sistema. Os dados de usuário priorizam uma sessão Windows ativa e usam o usuário do processo como fallback.

Agentes V3.3 e anteriores precisam receber este instalador **uma vez** para habilitar a atualização automática. Execute-o na mesma conta usada pelo agente atual, importe sua configuração e preserve o arquivo de identidade. Feche manualmente o agente portátil antigo antes de instalar: o instalador recusa encerrá-lo apenas pelo nome do arquivo. Somente processos da instalação de destino e da mesma conta podem ser encerrados automaticamente. Remova tarefas, atalhos ou outros mecanismos manuais de inicialização do executável antigo para que ele não volte no próximo login.

O instalador preserva configurações existentes e o UUID; permite atualização manual e recusa uma versão inferior à instalada. A desinstalação remove executáveis e registros de inicialização, preservando configuração, identidade, logs e diário de comandos.

Desde a V3.4.2, o Setup espera até 45 segundos por uma confirmação local com identificador único e versão, emitida após preparar configuração, identidade e diário de comandos. Se o processo encerrar ou não confirmar no prazo, informa falha em vez de anunciar sucesso. Essa confirmação verifica a inicialização local; a conexão ao servidor deve ser conferida no painel. Com `--no-launch`, os arquivos são instalados sem iniciar ou confirmar o agente.

As etapas e falhas ficam em `%LOCALAPPDATA%\STI\logs\instalador.log`, com rotação, sem gravar token nem conteúdo da configuração. Se o Endpoint interromper o Setup, o último registro ajuda a localizar a etapa; consulte também os eventos do antivírus. A instalação não altera a proteção do Endpoint. Não há validação desta versão no Kaspersky da empresa nem garantia de eliminação do alerta.

Telemetria e confirmação de comandos recusam redirecionamentos HTTP, assim como os downloads, evitando encaminhar `X-Agent-Token` para outro destino. Configure o endereço final do servidor. HTTP continua disponível para compatibilidade com a rede existente; use HTTPS configurado no servidor para proteger o conteúdo em trânsito.

Para instalação sem interface, com configuração já preparada:

```powershell
.\STI_Agente_Setup_3.4.3.exe --silent --config .\agent-config.json
```

As opções `--no-startup` e `--no-launch` desabilitam, respectivamente, o início no login e a execução ao terminar a instalação. A instalação silenciosa também é por usuário: executá-la como outra conta instala para essa outra conta.

### Configuração do agente

| Chave | Padrão | Finalidade |
| --- | --- | --- |
| `STI_SERVER_IP` | `10.2.116.121` | IP/DNS do servidor. |
| `STI_SERVER_PORT` | `5000` | Porta do servidor. |
| `STI_AGENT_TOKEN` | vazio | Mesmo token do servidor. |
| `STI_USE_HTTPS` | `false` | Usa um endpoint HTTPS já configurado. |
| `STI_IDENTITY_FILE` | automático | Caminho opcional para o SQLite de identidade da estação. Não reutilize o arquivo entre computadores. |
| `STI_ALLOW_POWER_COMMANDS` | `false` | Habilita explicitamente reiniciar/desligar nesse agente. |
| `AGENT_INTERVAL` | `30` | Pausa após envio bem-sucedido, em segundos. |
| `RETRY_INTERVAL` | `10` | Pausa após falha, em segundos. |

Trocar endereço ou token no JSON exige reiniciar o agente, mas não recompilar. O servidor também lê sua configuração na inicialização.

Os logs ficam em `%LOCALAPPDATA%\STI\logs\agente_v3_1.log`, com rotação de 2 MiB e até três backups. O nome legado do log foi mantido para continuidade. O registro de comandos fica em `%LOCALAPPDATA%\STI\commands.db`. Não apague esse registro durante uma recuperação: ele evita repetir ações. Registros confirmados com mais de sete dias são removidos ao iniciar o agente.

Para validar coleta e configuração sem iniciar o loop, sem comunicar com o servidor e sem executar comandos:

```powershell
.\.venv\Scripts\python.exe agente.py --check
# Ou, na máquina do usuário:
.\STI_Agente.exe --check
```

O diagnóstico mostra dados da máquina local. RAM e disco são enviados em unidades de 1024³ bytes; falha na consulta de disco é enviada como valor ausente, sem fingir disco de tamanho zero.

## Mensagens, reinicialização e desligamento

Mensagens são recebidas no próximo heartbeat do agente e consideradas concluídas quando o usuário fecha a janela.

As ações de energia permanecem **desabilitadas por padrão**. Para habilitá-las em uma máquina, configure `STI_ALLOW_POWER_COMMANDS` como `true` no JSON do agente e reinicie-o. O painel habilita os botões somente após receber essa capacidade de um agente com comunicação recente.

Reiniciar/desligar usa a API nativa do Windows, com aviso e prazo de **60 segundos**, sem forçar o fechamento dos aplicativos. Depende das permissões do usuário. O estado `initiated` significa que o Windows aceitou o agendamento; não comprova que a máquina terminou a ação. Aplicativos com alterações pendentes podem impedir a conclusão, conforme a [documentação da Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/winreg/nf-winreg-initiatesystemshutdownw).

O painel acompanha `queued → delivered → accepted → completed/rejected/failed/initiated`. Entregas não aceitas são reenviadas com o mesmo ID. O agente persiste resultados e tenta confirmar novamente sem repetir a ação. Se reiniciar durante uma execução, informa resultado incerto e não reexecuta automaticamente.

Ao exceder o prazo, o job passa para `expired`, libera a fila e registra que a execução não foi confirmada. Confira a máquina antes de reenviar. Nenhum protocolo de confirmação garante conhecer o efeito de uma ação interrompida exatamente durante sua execução.

## Gerar instalador e release

No Windows, com Python 3.12 de 64 bits:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements/dev.txt
.\.venv\Scripts\python.exe scripts/gerar_release.py --notes "Instalador e atualização automática do agente."
```

Nesta cópia, a chave de publicação já foi criada em **`.release-keys/agent-signing-key.pem`**, ignorada pelo Git. Guarde uma cópia segura dessa chave na máquina usada para publicar versões. Ela não deve ir para Git, instaladores, estações ou pacotes de release. A chave pública em `sti/comum/release-public-key.pem` é versionada e embutida no agente e no servidor.

Em um projeto novo, sem chaves anteriores, `python scripts/chave_release.py` cria o par inicial sem sobrescrever arquivos existentes. Em outra máquina de desenvolvimento deste projeto, restaure a **mesma chave privada**; gerar outra chave não permite atualizar os agentes já distribuídos. A rotação da confiança exige uma migração própria.

O build gera:

| Arquivo | Uso |
| --- | --- |
| `dist/STI_Agente.exe` | Executável portátil; não habilita atualização automática sem instalação. |
| `dist/releases/3.4.3/STI_Agente_Setup_3.4.3.exe` | Instalação inicial nas estações, sem Python. |
| `dist/releases/3.4.3/STI_Release_3.4.3.sti` | Pacote assinado para importar no painel STI. |
| `dist/releases/3.4.3/manifest.json` | Versão, notas, hashes e assinatura. |
| `dist/releases/3.4.3/agent.zip` | Executável empacotado para download pelos agentes. |

O executável mantém o nome `STI_Agente.exe` entre versões; a versão é definida em `sti/comum/versao.py`. Para gerar a próxima correção, por exemplo `3.4.4`:

```powershell
.\.venv\Scripts\python.exe scripts/gerar_release.py --bump patch --notes "Descrição das correções desta versão."
```

Também são aceitos `--bump minor`, `--bump major` e `--notes-file arquivo.txt`. O incremento altera o fonte da versão; inclua essa alteração no próximo commit. Uma versão importada no servidor é imutável: alterações de código exigem outro número de versão. `dist/` e `build/` permanecem fora do Git.

Os builds são sem console. Para diagnóstico com saída visível, execute o fonte pelo PyCharm. Configurações com credenciais não são embutidas. A assinatura Ed25519 protege o mecanismo de atualização do STI; o build padrão não configura assinatura Authenticode. Para usar um certificado Windows existente, consulte a seção a seguir.

### Assinatura Authenticode no build

O publicador aceita `--sign-cert` com o thumbprint de um certificado de assinatura de código existente no repositório pessoal do Windows, `--signtool` com o caminho do SignTool do Windows SDK e `--timestamp-url` com o servidor RFC 3161 indicado pelo emissor do certificado. Nenhum certificado é criado ou instalado pelo script, e nenhuma chave privada é exportada.

```powershell
.\.venv\Scripts\python.exe scripts/gerar_release.py --sign-cert "THUMBPRINT_DO_CERTIFICADO" --signtool "CAMINHO_DO_SIGNTOOL.exe" --timestamp-url "URL_RFC3161_DO_EMISSOR" --notes "Descrição da versão"
```

Substitua os três valores de exemplo pelos dados reais. O agente é assinado e verificado antes de entrar no Setup; o Setup é assinado e verificado antes da geração dos hashes e do pacote `.sti`. Uma falha ao assinar ou verificar interrompe o build. Sem essas opções, o build continua disponível para desenvolvimento e informa explicitamente que não há assinatura Windows. A assinatura Ed25519 da release é mantida nos dois modos.

Uma assinatura Authenticode não equivale a aprovação do Endpoint e não garante ausência de detecção. O projeto não desativa a proteção, instala certificados de confiança ou recria executáveis removidos pelo antivírus. Antes de distribuir automaticamente em produção, valide instalação, atualização e permanência do agente com a proteção ativa. Uma estação cujo agente foi removido precisa de uma nova instalação aceita pela política da empresa; o servidor não consegue atualizar um processo que não existe.

Referência: [SignTool e verificação Authenticode na documentação da Microsoft](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool).

### Distribuir pelo servidor STI

1. Atualize primeiro o servidor, instale as dependências atualizadas (`pip install -r requirements.txt`) e reinicie-o. O upload usa Flask 3.1; a migração do banco é aditiva.
2. Entre no painel e abra **Atualizações**. Importe `STI_Release_3.4.3.sti`; importar não inicia a distribuição.
3. Baixe o instalador pela lista de versões ou use o arquivo local e instale uma vez nas estações com agente antigo. Máquinas descobertas apenas por ping não podem receber instalação remota por este mecanismo.
4. Nas próximas releases, selecione a versão e comece com **Grupo piloto**, escolhendo equipamentos pelo ID permanente. Depois de conferir o resultado, libere para **Todos os agentes**.
5. Opcionalmente, defina início e fim da janela de horário. O painel mostra o horário do servidor; uma janela como `22:00–06:00` atravessa a meia-noite. Sem janela, a oferta pode ocorrer a qualquer horário.
6. Clique em **Liberar atualização** e acompanhe versão instalada, compatibilidade e resultado por estação. **Suspender distribuição** impede novas ofertas; uma atualização já iniciada pode terminar.

A versão disponível é oferecida na resposta ao heartbeat existente. O agente baixa o pacote do próprio servidor STI com autenticação; a estação não precisa acessar GitHub nem consultar outro serviço. Somente instalações compatíveis e com versão inferior recebem a atualização. Agentes executados pelo fonte ou de forma portátil continuam funcionando e aparecem como instalação manual.

Quando o último estado recebido é download, instalação ou atualização concluída, mas não há mais comunicação recente, a tela mostra **Sem confirmação recente**. Ela conserva a última versão e o último resultado como histórico, sem afirmar que o processo continua instalado ou que uma instalação antiga ainda está em andamento. Esse estado tem filtro próprio; não identifica o motivo da perda de comunicação. Logs da estação e eventos do Endpoint continuam necessários para confirmar bloqueio ou remoção.

Antes de trocar o executável, o agente valida assinatura, tamanho e SHA-256. Aguarda comandos em execução e resultados pendentes antes de atualizar. Um processo auxiliar troca o arquivo, inicia a nova versão e espera até **90 segundos** pela confirmação de comunicação com o servidor. Em caso de falha de inicialização ou ausência dessa confirmação, tenta restaurar e iniciar a versão anterior. Configuração, UUID e diário de comandos são preservados. A versão anterior fica em `previous-agent.exe`; pastas temporárias concluídas são limpas na próxima tentativa de atualização.

Falhas transitórias de download podem ser tentadas novamente após cinco minutos. Uma versão rejeitada por integridade ou recuperada após falha não fica sendo reinstalada em ciclo: corrija a release e publique outra versão, ou libere a distribuição novamente para autorizar uma nova tentativa. O estado fica em `%LOCALAPPDATA%\STI\update-state.json`, além do log do agente. Atualizações interrompidas por reinicialização são conferidas após a próxima comunicação.

### Releases no GitHub

O funcionamento interno não depende de uma release no GitHub. Para publicar os artefatos também lá, instale o GitHub CLI, execute `gh auth login`, faça commit e push do código correspondente e use explicitamente:

```powershell
.\.venv\Scripts\python.exe scripts/gerar_release.py --notes-file notas.txt --github-release
```

Essa opção cria a tag/release `v<versão>` no commit atual e envia o instalador, o pacote `.sti` e o manifesto. Não reutilize um número já publicado. Publicar o código com `git push` não envia os executáveis e não ativa distribuição nas estações. A integração com GitHub CLI exige credenciais locais e não foi executada nesta entrega.

## Acabamento visual do painel

O painel mantém a composição original: identificação STI e relógio à esquerda, indicadores no topo, cartões de máquinas no centro e saúde da rede à direita.

- Os ícones são SVG locais, compartilhados em `sti/servidor/static/icons/sti.svg`, sem depender de emojis ou serviços externos de ícones.
- Os cartões recebem iluminação sutil acompanhando o cursor, e os botões têm transições de interação. Os contadores animados terminam nos valores reais recebidos do servidor.
- Os indicadores e as legendas permitem filtrar online, offline e latência elevada, combinando com a busca, a organização e a faixa de IP.
- O menu lateral é aberto pelo botão de navegação nas telas pequenas. `/` leva à busca e `Esc` fecha os detalhes, com confirmação quando há cadastro não salvo.
- As animações respeitam a preferência de movimento reduzido do sistema/navegador. A atualização automática dos dados não repete a animação de entrada dos cartões.

O layout estrutural continua em `sti/servidor/static/painel.css`; os efeitos e refinamentos ficam em `sti/servidor/static/premium-effects.css`.

## Organização por setor, sala e responsável

1. Abra o cartão da máquina no painel.
2. Preencha **Setor**, **Sala** e **Responsável** na seção **Localização e responsável**.
3. Clique em **Salvar cadastro**. Campos vazios removem o valor anterior.
4. Use a busca ou os filtros acima dos cartões para localizar máquinas pelo cadastro. Os filtros combinam entre si e com as faixas de IP existentes.
5. Escolha **Agrupar por** para reunir os cartões por setor, sala ou responsável. A opção **Não informado** nos filtros localiza equipamentos ainda sem cadastro.

O responsável é um dado administrativo e pode ser diferente do usuário conectado ao Windows. O cadastro pode ser editado mesmo com a máquina offline e é incluído no CSV de inventário, respeitando os filtros selecionados. Os indicadores gerais continuam mostrando toda a rede.

Os dados de equipamentos identificados ficam em `machine_organization`; `device_organization` mantém o cadastro legado por IP, no mesmo SQLite. A tabela é criada automaticamente na inicialização, preservando o inventário existente. Os heartbeats do agente e as varreduras não modificam esse cadastro; para a identificação permanente, atualize os agentes para V3.3.

Alterações são registradas na auditoria, na categoria **Cadastro de máquinas** (`inventario`). A atualização automática da tela preserva os campos em edição. Se outra sessão salvar primeiro, o painel avisa sobre o conflito em vez de sobrescrever silenciosamente.

Com o agente V3.3, o cadastro acompanha o ID permanente do equipamento, mesmo após mudanças de IP. Agentes anteriores continuam operando por IP até serem atualizados. Na primeira comunicação do agente novo, o cadastro administrativo legado do endereço atual é associado à identidade permanente uma única vez.

## Identificação dos dispositivos

Os cartões e o mapa mostram ícones de Windows, Linux, Android, iOS, macOS, impressoras e equipamentos de rede, com a origem da classificação. O sistema informado pelo agente tem prioridade. Sem essa informação, abra **Identificar dispositivo** ou **Ver detalhes**, preencha **Nome para identificar** e **Sistema ou tipo** e clique em **Salvar cadastro**. Nome e sistema cadastrados entram na busca e no CSV; apagar a seleção retorna ao modo automático. Esses campos acompanham o ID permanente dos equipamentos com agente; na descoberta sem agente, ficam ligados ao IP e precisam de revisão se o endereço passar para outro equipamento.

Nomes de rede com termos explícitos como `iPhone`, `android`, `ubuntu` e `windows` podem gerar sugestões marcadas como **prováveis**. Elas não comprovam o sistema. IP, resposta ao ping e marca do fabricante não distinguem com segurança Windows, Linux, Android ou iOS. Sem evidência ou cadastro, o painel mostra um ícone neutro e **Não identificado**, sem atribuir um sistema por suposição. A consulta DNS existente é mantida; esta melhoria não acrescenta sondagens de portas nem depende de alterações no agente Windows.

Os cartões destacam o endereço IP, sistema operacional completo, usuário, conexão do agente e latência do ping. **Online na rede** indica presença; **Agente conectado** indica telemetria recente. O pop-up reúne esses sinais, a data do último envio, os recursos e o cadastro administrativo. Quando o agente deixa de se comunicar, sistema e usuário são sinalizados como históricos e os recursos atuais ficam indisponíveis.

A varredura tenta resolver nomes pelo DNS reverso do servidor, em segundo plano, com dois trabalhadores e intervalo de 15 minutos entre tentativas por IP. A fila é limitada para não bloquear a varredura quando o DNS está lento. Sem registro PTR/DNS disponível, aparece **Dispositivo sem nome**, sempre com o IP completo. Nomes como `host-33` do inventário antigo são tratados como provisórios; nomes enviados pelo agente têm prioridade sobre o DNS. A faixa padrão continua `10.2.116.0/22`.

Ping e DNS não informam o usuário conectado nem o sistema operacional. Para esses dados, mantenha o agente em execução na máquina e confira `STI_SERVER_IP`, `STI_SERVER_PORT`, `STI_AGENT_TOKEN`, o acesso à porta do servidor e o log do agente. Para receber a correção da escolha da sessão Windows, atualize também o agente nas estações (recompile o executável se essa for a distribuição utilizada). Uma sessão vazia limpa o usuário anterior; contas de serviço conhecidas não são apresentadas como usuário conectado.

Latência sem medição recente aparece como **Não medida**, em vez de `0 ms`. O valor zero continua válido quando retornado pelo ping. Após reiniciar o servidor, o horário histórico do agente é preservado, mas uma nova comunicação é necessária para habilitar ações remotas.

## Remapear a descoberta da rede

Na seção **Dispositivos**, clique em **Remapear rede**. O painel mostra quantos registros sem agente serão removidos, quantos estão offline, quantos equipamentos com agente serão mantidos e a faixa que será escaneada. Confirme para limpar a descoberta anterior e iniciar uma nova varredura. O andamento e o resultado aparecem junto aos filtros.

A limpeza remove os registros de descoberta por IP, tanto online quanto offline. Equipamentos identificados pelo agente, inclusive agentes antigos e cadastros permanentes sem IP atual, continuam no inventário. Setor, sala, responsável, auditoria e histórico são mantidos. O cadastro administrativo por IP reaparece quando aquele endereço é descoberto novamente. Comandos pendentes associados a registros removidos são encerrados.

O remapeamento aguarda a conclusão de qualquer varredura em andamento. Durante a limpeza e a nova varredura, os botões de escaneamento e remapeamento ficam desativados. A faixa padrão é `10.2.116.0/22`. Os equipamentos descobertos são os que respondem ao ping, além dos que enviam dados pelo agente. Sem agente, endereços antigos podem acumular novamente após mudanças de IP, e celulares ou outros dispositivos também podem responder à varredura.

## Som personalizado dos alertas

Clique no ícone de som da barra superior para configurar o áudio. Use **Escolher arquivo de áudio** para selecionar MP3, WAV, OGG ou M4A (até 10 MB), ajuste o volume e clique em **Testar som**. Depois, clique em **Ativar alertas sonoros**. Cada alerta de queda reproduz até os primeiros 10 segundos; ocorrências simultâneas geram uma única reprodução por atualização, sem sobrepor arquivos.

O áudio é validado pelo navegador antes de substituir o anterior. O arquivo fica no IndexedDB e o volume no armazenamento local desse navegador; não são enviados ao servidor nem compartilhados com outras máquinas. Ao recarregar o painel, o arquivo e o volume são restaurados, mas é necessário ativar novamente o som, respeitando as regras de reprodução do navegador. **Usar som padrão** remove o arquivo salvo e retorna ao sinal original do STI. Se o navegador impedir o armazenamento, o painel informa que a configuração vale apenas para a sessão atual.

## Identidade permanente, MACs e reinstalações

O agente V3.3 gera um **UUID da instalação** e o persiste em `%ProgramData%\STI\identity.db`. Reiniciar ou substituir o executável não altera esse UUID. `STI_IDENTITY_FILE` permite escolher outro caminho persistente. Se o arquivo compartilhado já existir e puder ser lido, o agente reutiliza o UUID mesmo com acesso somente leitura. Se não puder criar o arquivo compartilhado, tenta `%LOCALAPPDATA%\STI\identity.db` e registra o fallback no log; nesse caso, mantenha a mesma conta para executá-lo. Um arquivo corrompido não é substituído silenciosamente. Faça a instalação com acesso ao mesmo arquivo de identidade durante as atualizações.

O servidor cria seu próprio **ID permanente do equipamento**, associado ao UUID recebido. Setor, sala, responsável e novos eventos acompanham esse ID; o IP passa a ser apenas o endereço atual. Os cartões, o pop-up, a busca e o CSV mostram as referências de identidade. A busca também encontra MAC, número de série, fabricante e modelo. O pop-up permite consultar os últimos 20 eventos do equipamento; o relatório aceita `device_id` para filtrar e exportar o histórico entre diferentes IPs.

O agente informa os MACs unicast das interfaces disponíveis, incluindo placas virtuais quando houver. A coleta de série, fabricante, modelo e UUID SMBIOS usa CIM do Windows com prazo limitado; valores genéricos de série são descartados. Uma referência hash do SMBIOS (ou de `MachineGuid` como fallback) auxilia a detecção de cópias e a revisão de reinstalações. MAC, nome e série isolados **não provocam união automática** de cadastros.

Quando o IP muda, o cadastro permanece na mesma identidade. Comandos pendentes são encerrados e devem ser solicitados novamente no endereço atualizado. Se outro equipamento assumir o IP antigo, ele recebe seu próprio cadastro. O equipamento anterior continua no inventário, offline, com **Último IP**, preservando seu cadastro e histórico. Ações já executadas não são desfeitas por essa mudança.

### Atualização e migração

1. Faça backup do `monitor.db` e atualize o servidor primeiro. A migração adiciona colunas e tabelas, preservando as tabelas existentes.
2. Distribua o instalador V3.4 e importe a configuração de agente já utilizada, mantendo IP do servidor, token e permissões de energia. A rede padrão continua `10.2.116.0/22`.
3. Preserve o arquivo `identity.db` nas atualizações. O primeiro envio do agente atualizado associa o cadastro legado do seu IP à identidade permanente. Antes desse primeiro envio, o inventário antigo só possui a associação por IP; confira o cadastro se houve troca de equipamento naquele endereço.
4. Confirme o ID permanente, os MACs e a série no pop-up. Agentes antigos funcionam nos endereços ainda sem identidade permanente; um agente antigo é recusado em endereço já vinculado a uma identidade nova, para não sobrescrevê-la.

O banco acrescenta `machine_inventory`, `machine_organization`, `identity_conflicts` e `retired_agent_ids`, além de `device_id` em estado, auditoria e comandos. A auditoria anterior por IP é associada no primeiro registro legado; eventos novos usam a identidade diretamente.

### Reinstalação do Windows

Se o arquivo de identidade for preservado e a referência de hardware permanecer igual, o agente mantém seu UUID. Se a instalação gerar um UUID novo, aparece um cadastro separado. O pop-up mostra **Possível reinstalação** quando encontra um cadastro sem envio recente com a mesma referência de hardware, ou série válida igual e pelo menos um MAC em comum.

Confira os nomes, IDs, IPs, série e MACs; selecione o cadastro anterior e clique em **Recuperar cadastro anterior**. A confirmação mostra o setor, a sala e o responsável que serão preservados. A operação reúne o histórico, preserva o cadastro anterior e encerra comandos pendentes. Um cadastro que ainda recebe telemetria recente não pode ser recuperado dessa forma. Sem referências compatíveis, os cadastros permanecem separados para conferência, sem adivinhar a associação.

### Clonagem e UUID duplicado

Não inclua `identity.db` nem `commands.db` em imagens de distribuição. Ao detectar referência de hardware diferente, do mesmo tipo daquela gravada no arquivo copiado, o agente gera outro UUID. Uma mudança temporária de método de coleta (SMBIOS para MachineGuid, por exemplo) preserva a identidade anterior. O diário local encerra comandos da identidade anterior, sem executá-los na nova máquina.

O servidor recusa o mesmo UUID com hardware diferente, ou com outra instância recente em outro IP, registra o conflito e o apresenta no painel. Uma mesma instância pode mudar de IP normalmente. Se o UUID e todas as referências forem clonados, a origem não pode ser distinguida com garantia apenas por esses dados, sobretudo se as cópias não funcionarem simultaneamente.

Para renovar explicitamente a identidade da cópia, pare o agente e execute pelo terminal do PyCharm:

```powershell
.\.venv\Scripts\python.exe agente.py --new-identity
```

Ou use `STI_Agente.exe --new-identity` na estação. A operação é local, não envia comandos e exige que outra instância não esteja rodando. O novo UUID fica registrado no log. Depois, inicie o agente normalmente e confira o novo equipamento. UUIDs de instalações substituídas pela recuperação são recusados, evitando que uma cópia antiga retome o cadastro.

## APIs e relatórios

| Método | Rota | Uso |
| --- | --- | --- |
| GET/POST | `/login` | Formulário e login. Cinco tentativas por IP a cada cinco minutos. |
| POST | `/logout` | Encerra a sessão administrativa. |
| GET | `/api/devices` | Inventário, disponibilidade da máquina/agente, capacidades e progresso do scanner. |
| PATCH | `/api/devices/<ip>/organization` | Sessão administrativa; aceita ID permanente ou IP legado; edita setor (`department`), sala (`room`) e responsável (`responsible`). |
| POST | `/api/inventory/<device_id>/reconcile` | Sessão administrativa; recupera um cadastro anterior após revisão de reinstalação. |
| POST | `/api/scan` | Solicita varredura manual. |
| GET/POST | `/api/remap` | Prévia e remapeamento da descoberta sem agente. POST exige `{"confirm": true}`. |
| GET | `/api/history` | Últimos 300 snapshots. |
| GET | `/api/events` | Auditoria; filtros `device_id`, `ip`, `category`, `limit` (1–500). |
| POST | `/api/command/<ip>` | JSON com `command`, `message` quando for `msg`, e `device_id` para máquinas identificadas; retorna `202` e `command_id`. |
| GET | `/api/commands/<id>` | Estado e resultado do comando. |
| POST | `/api/agent` | Telemetria e recebimento de comandos; exige `X-Agent-Token`. |
| POST | `/api/agent/command-status` | JSON com `id`, `status`, `result`; exige token e mesmo IP de destino. |
| GET/POST | `/api/releases` | Lista ou importa release assinada via multipart com campo `release`; sessão administrativa. |
| POST | `/api/releases/activate` | Libera versão para todos ou IDs selecionados, com janela de horário opcional. |
| POST | `/api/releases/pause` | Suspende novas ofertas de atualização. |
| GET | `/api/releases/<version>/installer` | Download do instalador; sessão administrativa. |
| GET | `/api/agent/releases/<version>/package` | Download autenticado por token e `X-Agent-ID`, vinculado ao IP atual da estação. |
| POST | `/api/agent/update-status` | Informa progresso autenticado durante a atualização. |
| GET | `/relatorios` | Relatórios com filtros `start`, `end`, `device_id`, `ip`, `category`. |
| GET | `/api/report/events.csv` | Exportação dos eventos com os mesmos filtros. |

Todas as rotas administrativas exigem sessão. A página de relatórios mostra até 500 eventos e o CSV até 10.000; datas no formato `AAAA-MM-DD`. Categorias: `dispositivo`, `inventario`, `comando`, `scanner`, `seguranca`.

O cadastro aceita alterações parciais em JSON, com textos de até 120 caracteres. Um campo enviado como `""` é limpo; campos omitidos são preservados. `GET /api/devices` inclui o objeto `organization`, com esses três campos e `updated_at`. Ao enviar `expected_updated_at` no PATCH, uma versão diferente da atual retorna HTTP `409` para evitar sobrescrita concorrente.

## Testes e verificações

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/test_painel.cjs
```

Os testes usam bancos temporários e não executam ações de energia. Foram validados: autenticação, isolamento por IP, faixas originais, métricas, migração do banco, concorrência da fila, transições, expiração, perda de confirmações, recuperação após reinício, CSV, histórico e escape de HTML. O cadastro tem testes de persistência após heartbeat, scanner e reinício, edição parcial, conflitos, filtros, grupos e preservação de campos durante edição. Também houve coleta real de hardware no Windows e teste do painel no Edge headless, com dados fictícios e scanner desativado.

O módulo de releases cobre assinatura e adulteração, autenticação, isolamento do download, versões imutáveis, grupos, janelas atravessando a meia-noite, preservação da instalação, confirmação de saúde, retomada após download interrompido e recuperação da versão anterior. Foi realizada uma atualização real entre executáveis Windows `3.4.0 → 3.4.1`, preservando UUID e configuração, seguida de uma release inválida para confirmar a recuperação. Esses testes usaram diretórios temporários, sem registrar inicialização no Windows nem alterar agentes de produção. No Edge, foram verificados upload do pacote real, grupo piloto, suspensão, download do instalador e layout entre 360 e 1600 px.

Na V3.4.2, os testes adicionais verificam recusa de redirecionamentos 301/302/303/307/308 sem encaminhar token, encerramento limitado à instalação e conta corretas, fechamento manual de agentes portáteis, falha de inicialização sem falso sucesso e logs sem token. A gravação de JSON usa arquivo temporário exclusivo e repete a substituição por até três segundos em caso de bloqueio temporário do Windows. Também foram verificadas gravações concorrentes e instalação/reinstalação reais do executável V3.4.2 sem servidor disponível, preservando UUID e configuração.

## Publicação

Faça o merge das alterações na `main` antes de executar `deploy.ps1`. O script publica primeiro no remoto `production`, depois no `origin`, e consulta o serviço por SSH no host `agente-sti`; esses destinos precisam estar configurados no ambiente de implantação. Ele recusa outras branches e interrompe a execução se a preparação ou o commit falhar.

Para publicar somente o código no GitHub, utilize `git push origin main`, sem executar o script de deploy da intranet.

Não houve implantação nem teste nas máquinas reais dos usuários. Antes de distribuir a todos, valide um computador da rede, especialmente firewall, impressoras da sessão e permissões das ações habilitadas.

## Operação

- Faça backup e restrinja acesso ao banco e aos arquivos de configuração. O histórico ainda não possui retenção automática.
- HTTP continua disponível para a rede interna. Para criptografar credenciais e telemetria, configure um endpoint HTTPS; ativar as flags isoladamente não cria certificado nem TLS. O servidor usa o UUID para identificar o equipamento e o IP da conexão direta como endereço atual. Um proxy que oculte o IP das estações continua exigindo adaptação antes de ser usado.
- Não publique configurações reais nem reutilize o token que aparecia no código antigo. Os arquivos gerados usam um novo token; atualize os agentes junto com o servidor.
- O repositório não define uma licença própria. A licença do Chart.js está em `sti/servidor/static/vendor/Chart.js-LICENSE.md`.

Referências: [execução com Waitress na documentação do Flask](https://flask.palletsprojects.com/en/stable/deploying/waitress/), [API do Flask](https://flask.palletsprojects.com/en/stable/api/), [assinaturas Ed25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/) e [Chart.js 4.5.1](https://github.com/chartjs/Chart.js/tree/v4.5.1).
