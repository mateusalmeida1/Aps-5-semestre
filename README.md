# Aps-5-semestre
#  Chat Ambiental TCP em Python

## Descrição

Aplicação de comunicação em rede desenvolvida em Python utilizando sockets TCP/IP. O sistema permite a comunicação em tempo real entre inspetores ambientais e uma central de monitoramento.

## 🚀 Funcionalidades

* Comunicação cliente-servidor
* Múltiplos usuários simultâneos
* Mensagens em tempo real
* Identificação de usuário e local
* Níveis de alerta (NORMAL, ALERTA, CRÍTICO)
* Registro de mensagens (log)

## Tecnologias

* Python
* Socket
* Threading

## Como executar

### Servidor:

```bash
python servidor.py
```

### Cliente:

```bash
python cliente.py
```

   Chat TCP/IP — Sistema de Inspeção
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
## Conceitos aplicados

* TCP/IP
* Sockets
* Threads
* Sistemas distribuídos

## Autor

Projeto acadêmico - APS
