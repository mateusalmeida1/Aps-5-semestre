# Chat TCP/IP — Sistema de Inspeção (APS 5º Semestre)

Aplicação de chat em tempo real baseada em sockets TCP/IP com arquitetura cliente-servidor.

---

## Estrutura do Projeto

```
.
├── servidor.py   # Servidor multithreaded — gerencia conexões e distribui mensagens
├── cliente.py    # Cliente — envio e recebimento simultâneos via threads
├── log.txt       # Gerado automaticamente; registra todas as mensagens com timestamp
└── README.md
```

---

## Pré-requisitos

- Python 3.10 ou superior (usa sintaxe `X | Y` para type hints)
- Nenhuma dependência externa — somente a biblioteca padrão do Python

---

## Como Executar

### 1. Iniciar o Servidor

Abra um terminal e execute:

```bash
python servidor.py
```

O servidor ficará escutando em `0.0.0.0:5000` e criará o arquivo `log.txt` automaticamente.

### 2. Conectar Clientes

Em terminais separados (quantos quiser), execute:

```bash
python cliente.py
```

Cada cliente passará por uma etapa de registro:

| Campo            | Exemplos de valor              |
|------------------|-------------------------------|
| Nome de usuário  | `Ana`, `Carlos`               |
| Localização      | `Sala 3`, `Torre A / Andar 2` |
| Nível de alerta  | `NORMAL`, `ALERTA`, `CRÍTICO` |

---

## Comandos Disponíveis

| Comando                        | Descrição                                    |
|-------------------------------|---------------------------------------------|
| `/online`                     | Lista todos os usuários conectados           |
| `/msg <usuário> <mensagem>`   | Envia uma mensagem privada para `<usuário>`  |
| `/sair`                       | Desconecta do servidor                       |

---

## Funcionalidades

- **Múltiplos clientes simultâneos** — cada conexão roda em uma thread dedicada no servidor.
- **Broadcast em tempo real** — mensagens públicas são enviadas a todos os clientes conectados.
- **Mensagens privadas** — via `/msg`.
- **Timestamp em todas as mensagens** — formato `HH:MM:SS`.
- **Log persistente** — todas as mensagens e eventos são gravados em `log.txt`.
- **Nível de alerta** — exibido junto a cada mensagem pública (`[NORMAL]`, `[ALERTA]`, `[CRÍTICO]`).

---

## Exemplo de Sessão

**Terminal do servidor:**
```
[*] Servidor iniciado em 0.0.0.0:5000
[+] Nova conexão: ('127.0.0.1', 54321)
[*] Threads ativas: 1
```

**Terminal do cliente (Ana):**
```
==============================================
   Chat TCP/IP — Sistema de Inspeção
==============================================
[+] Conectado ao servidor 127.0.0.1:5000

Informe seu nome de usuário: Ana
Informe sua localização: Torre A
Informe o nível de alerta: ALERTA

[12:00:01] Bem-vindo, Ana! Digite /online para ver usuários ou /sair para sair.

Comandos: /online  /msg <usuário> <mensagem>  /sair

Olá a todos!
[12:00:10] [ALERTA] Você: Olá a todos!
```

---

## Notas

- O arquivo `log.txt` é gerado na mesma pasta onde o servidor é executado.
- Para alterar o endereço/porta do servidor, edite as variáveis `HOST` e `PORT` em ambos os arquivos.
- O nível de alerta aceita variantes com ou sem acento (`CRITICO` / `CRÍTICO`).
