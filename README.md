# STI Command Center — V3.2

Monitoramento e gerenciamento de máquinas Windows, com servidor Flask/Waitress, banco SQLite e agente para os computadores dos usuários.

A rede padrão foi preservada: **10.2.116.0/22**, com os segmentos **116, 117, 118 e 119** no painel. O endereço padrão do servidor nos agentes continua **10.2.116.121:5000**.

## O que esta versão melhora

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
│   │   ├── organizacao.py     # Cadastro administrativo das máquinas
│   │   ├── templates/          # Páginas HTML
│   │   └── static/             # CSS, JavaScript, imagens e bibliotecas
│   ├── agente/
│   │   └── cliente.py          # Telemetria e comandos do agente
│   └── comum/
│       └── configuracao.py     # Configuração compartilhada
├── scripts/
│   └── preparar_config.py      # Geração dos arquivos locais
├── config/
│   └── sti-config.example.json # Exemplo sem credenciais
├── requirements/
│   ├── dev.txt                 # Dependências para build
│   └── windows-lock.txt        # Versões validadas no Windows
├── packaging/
│   ├── STI_Agente_V3_2.spec     # Build atual
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

**Não distribua o `sti-config.json` do servidor aos usuários.** Para os computadores dos usuários, copie `agent-config.json` e renomeie a cópia para `sti-config.json` ao lado do executável.

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

Distribua o executável atual e o `sti-config.json` preparado **a partir de `agent-config.json`**, na mesma pasta. Não é necessário instalar Python nas máquinas que usam o executável.

Execute na sessão interativa do usuário, para que as mensagens apareçam no desktop. O projeto não instala um serviço nem cria uma tarefa de inicialização automaticamente; para iniciar com o login, configure uma tarefa na sessão do usuário. Os dados de usuário priorizam uma sessão Windows ativa e usam o usuário do processo como fallback.

### Configuração do agente

| Chave | Padrão | Finalidade |
| --- | --- | --- |
| `STI_SERVER_IP` | `10.2.116.121` | IP/DNS do servidor. |
| `STI_SERVER_PORT` | `5000` | Porta do servidor. |
| `STI_AGENT_TOKEN` | vazio | Mesmo token do servidor. |
| `STI_USE_HTTPS` | `false` | Usa um endpoint HTTPS já configurado. |
| `STI_ALLOW_POWER_COMMANDS` | `false` | Habilita explicitamente reiniciar/desligar nesse agente. |
| `AGENT_INTERVAL` | `30` | Pausa após envio bem-sucedido, em segundos. |
| `RETRY_INTERVAL` | `10` | Pausa após falha, em segundos. |

Trocar endereço ou token no JSON exige reiniciar o agente, mas não recompilar. O servidor também lê sua configuração na inicialização.

Os logs ficam em `%LOCALAPPDATA%\STI\logs\agente_v3_1.log`, com rotação de 2 MiB e até três backups. O nome legado do log foi mantido para continuidade. O registro de comandos fica em `%LOCALAPPDATA%\STI\commands.db`. Não apague esse registro durante uma recuperação: ele evita repetir ações. Registros confirmados com mais de sete dias são removidos ao iniciar o agente.

Para validar coleta e configuração sem iniciar o loop, sem comunicar com o servidor e sem executar comandos:

```powershell
.\.venv\Scripts\python.exe agente.py --check
# Ou, na máquina do usuário:
.\STI_Agente_V3_2.exe --check
```

O diagnóstico mostra dados da máquina local. RAM e disco são enviados em unidades de 1024³ bytes; falha na consulta de disco é enviada como valor ausente, sem fingir disco de tamanho zero.

## Mensagens, reinicialização e desligamento

Mensagens são recebidas no próximo heartbeat do agente e consideradas concluídas quando o usuário fecha a janela.

As ações de energia permanecem **desabilitadas por padrão**. Para habilitá-las em uma máquina, configure `STI_ALLOW_POWER_COMMANDS` como `true` no JSON do agente e reinicie-o. O painel habilita os botões somente após receber essa capacidade de um agente com comunicação recente.

Reiniciar/desligar usa a API nativa do Windows, com aviso e prazo de **60 segundos**, sem forçar o fechamento dos aplicativos. Depende das permissões do usuário. O estado `initiated` significa que o Windows aceitou o agendamento; não comprova que a máquina terminou a ação. Aplicativos com alterações pendentes podem impedir a conclusão, conforme a [documentação da Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/winreg/nf-winreg-initiatesystemshutdownw).

O painel acompanha `queued → delivered → accepted → completed/rejected/failed/initiated`. Entregas não aceitas são reenviadas com o mesmo ID. O agente persiste resultados e tenta confirmar novamente sem repetir a ação. Se reiniciar durante uma execução, informa resultado incerto e não reexecuta automaticamente.

Ao exceder o prazo, o job passa para `expired`, libera a fila e registra que a execução não foi confirmada. Confira a máquina antes de reenviar. Nenhum protocolo de confirmação garante conhecer o efeito de uma ação interrompida exatamente durante sua execução.

## Gerar o executável atualizado

No Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements/dev.txt
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm packaging/STI_Agente_V3_2.spec
```

Saída: `dist\STI_Agente_V3_2.exe`. A configuração atual gera o executável sem console (`console=False`); a execução pelo PyCharm mantém seu terminal. Para diagnóstico com saída visível, use o fonte ou gere um build com console. Os `.spec` antigos ficam em `packaging/legacy/` como alternativas de nome; use V3.2 para a distribuição atual. O JSON com credenciais não é embutido no build.

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

Os dados ficam na tabela `device_organization` do mesmo banco SQLite. A tabela é criada automaticamente na inicialização, preservando o inventário existente. Os heartbeats do agente e as varreduras não modificam esse cadastro; não é necessário atualizar os agentes para usar o recurso.

Alterações são registradas na auditoria, na categoria **Cadastro de máquinas** (`inventario`). A atualização automática da tela preserva os campos em edição. Se outra sessão salvar primeiro, o painel avisa sobre o conflito em vez de sobrescrever silenciosamente.

O cadastro acompanha o IP registrado no inventário atual. Mudanças de IP por DHCP exigem conferir o cadastro; identificação permanente por equipamento ainda não está implementada.

## Identificação dos dispositivos

Os cartões destacam o endereço IP, sistema operacional completo, usuário, conexão do agente e latência do ping. **Online na rede** indica presença; **Agente conectado** indica telemetria recente. O pop-up reúne esses sinais, a data do último envio, os recursos e o cadastro administrativo. Quando o agente deixa de se comunicar, sistema e usuário são sinalizados como históricos e os recursos atuais ficam indisponíveis.

A varredura tenta resolver nomes pelo DNS reverso do servidor, em segundo plano, com dois trabalhadores e intervalo de 15 minutos entre tentativas por IP. A fila é limitada para não bloquear a varredura quando o DNS está lento. Sem registro PTR/DNS disponível, aparece **Dispositivo sem nome**, sempre com o IP completo. Nomes como `host-33` do inventário antigo são tratados como provisórios; nomes enviados pelo agente têm prioridade sobre o DNS. A faixa padrão continua `10.2.116.0/22`.

Ping e DNS não informam o usuário conectado nem o sistema operacional. Para esses dados, mantenha o agente em execução na máquina e confira `STI_SERVER_IP`, `STI_SERVER_PORT`, `STI_AGENT_TOKEN`, o acesso à porta do servidor e o log do agente. Para receber a correção da escolha da sessão Windows, atualize também o agente nas estações (recompile o executável se essa for a distribuição utilizada). Uma sessão vazia limpa o usuário anterior; contas de serviço conhecidas não são apresentadas como usuário conectado.

Latência sem medição recente aparece como **Não medida**, em vez de `0 ms`. O valor zero continua válido quando retornado pelo ping. Após reiniciar o servidor, o horário histórico do agente é preservado, mas uma nova comunicação é necessária para habilitar ações remotas.

## APIs e relatórios

| Método | Rota | Uso |
| --- | --- | --- |
| GET/POST | `/login` | Formulário e login. Cinco tentativas por IP a cada cinco minutos. |
| POST | `/logout` | Encerra a sessão administrativa. |
| GET | `/api/devices` | Inventário, disponibilidade da máquina/agente, capacidades e progresso do scanner. |
| PATCH | `/api/devices/<ip>/organization` | Sessão administrativa; edita setor (`department`), sala (`room`) e responsável (`responsible`). |
| POST | `/api/scan` | Solicita varredura manual. |
| GET | `/api/history` | Últimos 300 snapshots. |
| GET | `/api/events` | Auditoria; filtros `ip`, `category`, `limit` (1–500). |
| POST | `/api/command/<ip>` | JSON com `command` e `message`, quando for `msg`; retorna `202` e `command_id`. |
| GET | `/api/commands/<id>` | Estado e resultado do comando. |
| POST | `/api/agent` | Telemetria e recebimento de comandos; exige `X-Agent-Token`. |
| POST | `/api/agent/command-status` | JSON com `id`, `status`, `result`; exige token e mesmo IP de destino. |
| GET | `/relatorios` | Relatórios com filtros `start`, `end`, `ip`, `category`. |
| GET | `/api/report/events.csv` | Exportação dos eventos com os mesmos filtros. |

Todas as rotas administrativas exigem sessão. A página de relatórios mostra até 500 eventos e o CSV até 10.000; datas no formato `AAAA-MM-DD`. Categorias: `dispositivo`, `inventario`, `comando`, `scanner`, `seguranca`.

O cadastro aceita alterações parciais em JSON, com textos de até 120 caracteres. Um campo enviado como `""` é limpo; campos omitidos são preservados. `GET /api/devices` inclui o objeto `organization`, com esses três campos e `updated_at`. Ao enviar `expected_updated_at` no PATCH, uma versão diferente da atual retorna HTTP `409` para evitar sobrescrita concorrente.

## Testes e verificações

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/test_painel.cjs
```

Os testes usam bancos temporários e não executam ações de energia. Foram validados: autenticação, isolamento por IP, faixas originais, métricas, migração do banco, concorrência da fila, transições, expiração, perda de confirmações, recuperação após reinício, CSV, histórico e escape de HTML. O cadastro tem testes de persistência após heartbeat, scanner e reinício, edição parcial, conflitos, filtros, grupos e preservação de campos durante edição. Também houve coleta real de hardware no Windows e teste do painel no Edge headless, com dados fictícios e scanner desativado.

## Publicação

Faça o merge das alterações na `main` antes de executar `deploy.ps1`. O script publica primeiro no remoto `production`, depois no `origin`, e consulta o serviço por SSH no host `agente-sti`; esses destinos precisam estar configurados no ambiente de implantação. Ele recusa outras branches e interrompe a execução se a preparação ou o commit falhar.

Para publicar somente o código no GitHub, utilize `git push origin main`, sem executar o script de deploy da intranet.

Não houve implantação nem teste nas máquinas reais dos usuários. Antes de distribuir a todos, valide um computador da rede, especialmente firewall, impressoras da sessão e permissões das ações habilitadas.

## Operação

- Faça backup e restrinja acesso ao banco e aos arquivos de configuração. O histórico ainda não possui retenção automática.
- HTTP continua disponível para a rede interna. Para criptografar credenciais e telemetria, configure um endpoint HTTPS; ativar as flags isoladamente não cria certificado nem TLS. O servidor identifica agentes pelo IP da conexão direta. Um proxy que oculte esse IP exige adaptar a identificação antes de usá-lo.
- Não publique configurações reais nem reutilize o token que aparecia no código antigo. Os arquivos gerados usam um novo token; atualize os agentes junto com o servidor.
- O repositório não define uma licença própria. A licença do Chart.js está em `sti/servidor/static/vendor/Chart.js-LICENSE.md`.

Referências: [execução com Waitress na documentação do Flask](https://flask.palletsprojects.com/en/stable/deploying/waitress/) e [Chart.js 4.5.1](https://github.com/chartjs/Chart.js/tree/v4.5.1).
