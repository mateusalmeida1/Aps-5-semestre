# Aps-5-semestre
# Chat Ambiental TCP em Python

## Descrição

Aplicação de comunicação em rede desenvolvida em Python usando sockets TCP/IP.
O sistema permite comunicação em tempo real entre inspetores ambientais e uma central de monitoramento.

## Funcionalidades

- Comunicação cliente-servidor
- Múltiplos usuários simultâneos
- Mensagens públicas em tempo real
- Mensagens privadas
- Identificação de usuário e local
- Níveis de alerta (NORMAL, ALERTA, CRÍTICO)
- Registro de mensagens em log

## Tecnologias

- Python
- Socket
- Threading
- Tkinter (interface gráfica)

## Estrutura

- servidor.py: servidor TCP multithread
- cliente.py: cliente em modo terminal
- interace.py: cliente com interface gráfica Tkinter
- launcher.py: inicializador que abre servidor e dois clientes
- log.txt: arquivo de log gerado pelo servidor

## Como executar (Windows + PowerShell)

### Abrir tudo de uma vez

Se você quiser iniciar o ambiente completo com um clique, execute o launcher:

```powershell
& ".\.venv\Scripts\python.exe" ".\launcher.py"
```

Ele abre o servidor em segundo plano e duas janelas de interface já prontas para cadastro, mas sem conectar automaticamente. Assim você pode ajustar nome, status e localização antes de entrar.

### 1. Ir para a pasta do projeto

```powershell
Set-Location -LiteralPath "C:\Users\mateu\OneDrive\Área de Trabalho\aps 5\Aps-5-semestre"
```

### 2. Iniciar o servidor (Terminal 1)

```powershell
& ".\.venv\Scripts\python.exe" ".\servidor.py"
```

Saída esperada:

```text
[*] Servidor iniciado em 0.0.0.0:5000
```

### 3. Iniciar clientes

Cliente em terminal (Terminal 2, 3, 4...):

```powershell
& ".\.venv\Scripts\python.exe" ".\cliente.py"
```

O cliente de terminal agora pergunta host e porta ao iniciar.
Se apertar Enter sem digitar, usa padrão 127.0.0.1 e 5000.

Cliente com interface gráfica Tkinter:

```powershell
& ".\.venv\Scripts\python.exe" ".\interace.py"
```

Observação: para simular vários usuários, abra vários terminais e execute o cliente em cada um.

## Comandos no chat

- /online: lista usuários conectados
- /msg <usuario> <mensagem>: envia mensagem privada
- /sair: desconecta do chat

## Exemplo rápido de uso

```text
[+] Conectado ao servidor 127.0.0.1:5000
Informe seu nome de usuário: Ana
Informe sua localização: Torre A
Informe o nível de alerta: ALERTA
[12:00:01] Bem-vindo, Ana! Digite /online para ver usuários ou /sair para sair.
Comandos: /online  /msg <usuário> <mensagem>  /sair
```

## Problemas comuns

### Erro: WinError 10061 (conexão recusada)

O servidor não está rodando.
Inicie primeiro o servidor em um terminal separado e mantenha ele aberto.

### Erro no PowerShell com Set-Location

Use aspas no caminho com espaço e acento:

```powershell
Set-Location -LiteralPath "C:\Users\mateu\OneDrive\Área de Trabalho\aps 5\Aps-5-semestre"
```

### Erro ao executar comando com ..venv

O caminho correto é .\.venv (com ponto e barra).

Correto:

```powershell
& ".\.venv\Scripts\python.exe" ".\cliente.py"
```

## Notas

- O cliente de terminal permite informar host/porta ao iniciar, sem editar código.
- Para conexões remotas, use o IP da máquina do servidor ao abrir cliente.py ou interace.py.
- O nível CRITICO (sem acento) também é aceito e normalizado para CRÍTICO.
- O launcher abre dois clientes com cadastro automático para facilitar testes rápidos.

## Gerar executável

Para criar um `.exe` no Windows, instale o PyInstaller e gere o launcher:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install pyinstaller
& ".\.venv\Scripts\pyinstaller.exe" --onefile --noconsole --name ChatAmbiental ".\launcher.py"
```

O executável final ficará em `dist\ChatAmbiental.exe`.

## Conceitos aplicados

- TCP/IP
- Sockets
- Threads
- Sistemas distribuídos

## Autor

Projeto acadêmico - APS
