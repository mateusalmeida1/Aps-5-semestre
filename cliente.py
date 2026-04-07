"""
cliente.py — Cliente de chat TCP/IP com threads para envio e recebimento simultâneos.

Funcionalidades:
  - Registro interativo: username, localização e nível de alerta
  - Thread dedicada ao recebimento de mensagens (não bloqueia a entrada do usuário)
  - Comandos disponíveis:
      /sair          → desconectar do servidor
      /online        → listar usuários conectados
      /msg <u> <msg> → enviar mensagem privada para <u>
"""

from __future__ import annotations

import argparse
import socket
import threading
import sys
import time

# ─── Configurações ────────────────────────────────────────────────────────────
HOST = "127.0.0.1"  # Endereço IP do servidor
PORT = 5000          # Deve coincidir com o PORT do servidor

ALERTA_VALIDOS = ("NORMAL", "ALERTA", "CRÍTICO", "CRITICO")


def ask_server_address(default_host: str = HOST, default_port: int = PORT) -> tuple[str, int]:
    """Pergunta host/porta e retorna valores válidos com fallback para padrão."""
    host_input = input(f"Host do servidor [{default_host}]: ").strip()
    host = host_input or default_host

    while True:
        port_input = input(f"Porta do servidor [{default_port}]: ").strip()
        if not port_input:
            return host, default_port
        try:
            port = int(port_input)
        except ValueError:
            print("[!] Porta inválida. Digite um número (ex.: 5000).")
            continue

        if 1 <= port <= 65535:
            return host, port

        print("[!] Porta fora do intervalo válido (1-65535).")


def receive_messages(conn: socket.socket, stop_event: threading.Event) -> None:
    """
    Thread de recebimento: fica em loop recebendo mensagens do servidor
    e as imprimindo no terminal até que a conexão seja encerrada.
    """
    while not stop_event.is_set():
        try:
            data = conn.recv(4096)
            if not data:
                # Servidor encerrou a conexão
                print("\n[!] Servidor desconectado.")
                stop_event.set()
                break
            print(f"\n{data.decode('utf-8')}")
        except OSError:
            if not stop_event.is_set():
                print("\n[!] Conexão encerrada.")
            stop_event.set()
            break


def auto_send_messages(conn: socket.socket, stop_event: threading.Event, username: str) -> None:
    messages = [
        "Olá, sistema pronto para testes.",
        "/online",
        f"Mensagem automática de {username}.",
        "/sair",
    ]

    for message in messages:
        if stop_event.is_set():
            break
        time.sleep(1.5)
        try:
            conn.sendall(message.encode("utf-8"))
        except OSError:
            stop_event.set()
            break

        if message.strip() == "/sair":
            stop_event.set()
            break


def register(
    conn: socket.socket,
    username: str | None = None,
    localizacao: str | None = None,
    alerta: str | None = None,
) -> None:
    """
    Etapa de registro: responde às perguntas do servidor sobre
    username, localização e nível de alerta.
    """
    # O servidor envia 3 prompts em sequência; respondemos a cada um.
    prompts_answered = 0
    while prompts_answered < 3:
        try:
            data = conn.recv(4096)
        except OSError:
            print("[!] Falha ao receber prompt do servidor.")
            sys.exit(1)

        prompt = data.decode("utf-8")
        print(prompt, end="", flush=True)

        if prompts_answered == 0:
            if username is None:
                username = input().strip() or "Anônimo"
            conn.sendall(username.encode("utf-8"))

        elif prompts_answered == 1:
            if localizacao is None:
                localizacao = input().strip() or "Desconhecido"
            conn.sendall(localizacao.encode("utf-8"))

        elif prompts_answered == 2:
            if alerta is None:
                alerta = input().strip().upper() or "NORMAL"
            else:
                alerta = alerta.strip().upper() or "NORMAL"
            if alerta not in ALERTA_VALIDOS:
                print(f"[!] Valor inválido; usando NORMAL.")
                alerta = "NORMAL"
            conn.sendall(alerta.encode("utf-8"))

        prompts_answered += 1


def main(argv: list[str] | None = None) -> None:
    """Ponto de entrada do cliente de chat."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(description="Cliente de chat TCP/IP")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--user", default=None)
    parser.add_argument("--local", default=None)
    parser.add_argument("--alerta", default=None)
    parser.add_argument("--auto", action="store_true")
    args = parser.parse_args(argv)

    print("=" * 45)
    print("   Chat TCP/IP — Sistema de Inspeção")
    print("=" * 45)

    if argv:
        host, port = args.host, args.port
    else:
        host, port = ask_server_address(args.host, args.port)

    # Cria e conecta o socket ao servidor
    try:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.connect((host, port))
    except ConnectionRefusedError:
        print(f"[!] Não foi possível conectar ao servidor {host}:{port}.")
        print("    Verifique se o servidor está em execução.")
        sys.exit(1)

    print(f"[+] Conectado ao servidor {host}:{port}\n")

    # Fase de registro (bloqueante, sequencial)
    register(conn, username=args.user, localizacao=args.local, alerta=args.alerta)

    # Exibe a mensagem de boas-vindas enviada após o registro
    try:
        welcome = conn.recv(4096)
        if welcome:
            print(f"\n{welcome.decode('utf-8')}\n")
    except OSError:
        pass

    # ── Threads ──────────────────────────────────────────────────────────────
    stop_event = threading.Event()

    recv_thread = threading.Thread(
        target=receive_messages, args=(conn, stop_event), daemon=True
    )
    recv_thread.start()

    try:
        if args.auto:
            print("Modo automático ativado. A janela será fechada após alguns testes.")
            sender_thread = threading.Thread(
                target=auto_send_messages,
                args=(conn, stop_event, args.user or "Anônimo"),
                daemon=True,
            )
            sender_thread.start()
            sender_thread.join()
        else:
            print("Comandos: /online  /msg <usuário> <mensagem>  /sair\n")

            # ── Loop de envio (thread principal) ─────────────────────────────────────
            try:
                while not stop_event.is_set():
                    try:
                        message = input()
                    except EOFError:
                        # stdin fechou (ex.: pipe em testes)
                        break

                    if stop_event.is_set():
                        break

                    try:
                        conn.sendall(message.encode("utf-8"))
                    except OSError:
                        print("[!] Falha ao enviar mensagem.")
                        break

                    if message.strip() == "/sair":
                        print("[*] Desconectando...")
                        stop_event.set()
                        break

            except KeyboardInterrupt:
                print("\n[*] Interrompido pelo usuário.")
                try:
                    conn.sendall("/sair".encode("utf-8"))
                except OSError:
                    pass

    finally:
        stop_event.set()
        conn.close()
        print("[*] Conexão encerrada.")


if __name__ == "__main__":
    main()
