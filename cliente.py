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

import argparse
import socket
import threading
import sys

# ─── Configurações ────────────────────────────────────────────────────────────
HOST = "127.0.0.1"  # Endereço IP do servidor
PORT = 5000          # Deve coincidir com o PORT do servidor

ALERTA_VALIDOS = ("NORMAL", "ALERTA", "CRÍTICO", "CRITICO")


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


def register(conn: socket.socket) -> None:
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
            # username
            username = input().strip() or "Anônimo"
            conn.sendall(username.encode("utf-8"))

        elif prompts_answered == 1:
            # localização
            localizacao = input().strip() or "Desconhecido"
            conn.sendall(localizacao.encode("utf-8"))

        elif prompts_answered == 2:
            # nível de alerta
            alerta = input().strip().upper() or "NORMAL"
            if alerta not in ALERTA_VALIDOS:
                print(f"[!] Valor inválido; usando NORMAL.")
                alerta = "NORMAL"
            conn.sendall(alerta.encode("utf-8"))

        prompts_answered += 1


def main() -> None:
    """Ponto de entrada do cliente de chat."""
    parser = argparse.ArgumentParser(description="Cliente de chat TCP/IP")
    parser.add_argument("--host", default=HOST, help=f"Endereço IP do servidor (padrão: {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"Porta do servidor (padrão: {PORT})")
    args = parser.parse_args()
    host = args.host
    port = args.port

    print("=" * 45)
    print("   Chat TCP/IP — Sistema de Inspeção")
    print("=" * 45)

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
    register(conn)

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
