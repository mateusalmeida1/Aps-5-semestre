"""
servidor.py — Servidor de chat TCP/IP multithreaded.

Responsabilidades:
  - Aceitar conexões de múltiplos clientes simultaneamente (threading)
  - Registrar cada cliente com username, localização e nível de alerta
  - Transmitir mensagens em tempo real para todos os clientes conectados
  - Suportar mensagens privadas e listagem de usuários online
  - Registrar todas as mensagens em log.txt com timestamp
"""

import argparse
import socket
import threading
import datetime
import os

# ─── Configurações ────────────────────────────────────────────────────────────
HOST = "0.0.0.0"   # Escuta em todas as interfaces de rede (necessário para aceitar clientes remotos)
PORT = 5000         # Porta padrão do servidor
LOG_FILE = "log.txt"

# ─── Estado global dos clientes ───────────────────────────────────────────────
# clients: { conn -> { "username": str, "localizacao": str, "alerta": str } }
clients: dict[socket.socket, dict] = {}
clients_lock = threading.Lock()
client_thread_count = 0
client_thread_count_lock = threading.Lock()


def log_message(message: str) -> None:
    """Grava *message* em log.txt com timestamp."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


def broadcast(message: str, sender_conn: socket.socket | None = None) -> None:
    """Envia *message* para todos os clientes (exceto o remetente, se fornecido)."""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    full_message = f"[{timestamp}] {message}"
    log_message(message)

    with clients_lock:
        for conn in list(clients.keys()):
            if conn is sender_conn:
                continue
            try:
                conn.sendall(full_message.encode("utf-8"))
            except OSError:
                # Conexão perdida; será tratada no handle_client
                pass


def send_to(conn: socket.socket, message: str) -> None:
    """Envia *message* diretamente para um único cliente."""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    try:
        conn.sendall(f"[{timestamp}] {message}".encode("utf-8"))
    except OSError:
        pass


def list_online() -> str:
    """Retorna string formatada com todos os usuários conectados."""
    with clients_lock:
        if not clients:
            return "Nenhum usuário conectado."
        lines = ["=== Usuários online ==="]
        for info in clients.values():
            lines.append(
                f"  • {info['username']} | "
                f"Local: {info['localizacao']} | "
                f"Alerta: {info['alerta']}"
            )
        lines.append("=" * 22)
        return "\n".join(lines)


def handle_client(conn: socket.socket, addr: tuple) -> None:
    """Gerencia toda a comunicação com um único cliente conectado."""
    global client_thread_count
    print(f"[+] Nova conexão: {addr}")

    try:
        # ── Etapa de registro ────────────────────────────────────────────────
        conn.sendall("Informe seu nome de usuário: ".encode("utf-8"))
        username = conn.recv(1024).decode("utf-8").strip()

        conn.sendall("Informe sua localização (ex: Sala 3 / Torre A): ".encode("utf-8"))
        localizacao = conn.recv(1024).decode("utf-8").strip()

        conn.sendall(
            "Informe o nível de alerta (NORMAL / ALERTA / CRÍTICO): ".encode("utf-8")
        )
        alerta = conn.recv(1024).decode("utf-8").strip().upper()
        if alerta not in ("NORMAL", "ALERTA", "CRÍTICO", "CRITICO"):
            alerta = "NORMAL"
        # Normaliza variante sem acento
        if alerta == "CRITICO":
            alerta = "CRÍTICO"

        # Registra o cliente
        with clients_lock:
            clients[conn] = {
                "username": username,
                "localizacao": localizacao,
                "alerta": alerta,
            }

        # Avisa os demais usuários (broadcast já grava em log)
        entry = f"{username} entrou no chat. [Local: {localizacao} | Alerta: {alerta}]"
        broadcast(entry, sender_conn=conn)
        send_to(conn, f"Bem-vindo, {username}! Digite /online para ver usuários ou /sair para sair.")

        # ── Loop principal de mensagens ──────────────────────────────────────
        while True:
            try:
                data = conn.recv(4096)
            except OSError:
                break

            if not data:
                break

            message = data.decode("utf-8").strip()

            # ── Comandos ────────────────────────────────────────────────────
            if message == "/sair":
                break

            elif message == "/online":
                online_list = list_online()
                send_to(conn, online_list)
                log_message(f"/online solicitado por {username}: {online_list}")

            elif message.startswith("/msg "):
                # Formato: /msg <usuário> <mensagem>
                parts = message[5:].split(" ", 1)
                if len(parts) < 2:
                    send_to(conn, "Uso: /msg <usuário> <mensagem>")
                else:
                    target_name, private_msg = parts
                    target_conn = None
                    with clients_lock:
                        for c, info in clients.items():
                            if info["username"] == target_name:
                                target_conn = c
                                break
                    if target_conn is None:
                        send_to(conn, f"Usuário '{target_name}' não encontrado.")
                    else:
                        pm = f"[PRIVADO de {username}]: {private_msg}"
                        log_message(pm)
                        send_to(target_conn, pm)
                        send_to(conn, f"[PRIVADO para {target_name}]: {private_msg}")

            else:
                # Mensagem pública
                broadcast_msg = f"[{alerta}] {username}: {message}"
                broadcast(broadcast_msg, sender_conn=conn)
                # Ecoa para o próprio remetente com timestamp
                send_to(conn, f"[{alerta}] Você: {message}")

    except Exception as exc:
        print(f"[!] Erro com cliente {addr}: {exc}")

    finally:
        # ── Desconexão ───────────────────────────────────────────────────────
        with clients_lock:
            info = clients.pop(conn, None)
        with client_thread_count_lock:
            client_thread_count -= 1
        if info:
            leave_msg = f"{info['username']} saiu do chat."
            print(f"[-] {leave_msg} ({addr})")
            # log_message is called inside broadcast
            broadcast(leave_msg)
        conn.close()


def main() -> None:
    """Inicializa e executa o servidor."""
    global client_thread_count

    parser = argparse.ArgumentParser(description="Servidor de chat TCP/IP")
    parser.add_argument("--host", default=HOST, help=f"Endereço de escuta (padrão: {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"Porta de escuta (padrão: {PORT})")
    args = parser.parse_args()
    host = args.host
    port = args.port

    # Cria o arquivo de log se ainda não existir
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8"):
            pass  # apenas cria o arquivo vazio

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen()

    print(f"[*] Servidor iniciado em {host}:{port}")
    print(f"[*] Logs salvos em: {os.path.abspath(LOG_FILE)}")

    try:
        while True:
            conn, addr = server.accept()
            # Cria uma thread dedicada para cada cliente
            with client_thread_count_lock:
                client_thread_count += 1
            thread = threading.Thread(
                target=handle_client, args=(conn, addr), daemon=True
            )
            thread.start()
            with client_thread_count_lock:
                print(f"[*] Clientes conectados: {client_thread_count}")
    except KeyboardInterrupt:
        print("\n[*] Servidor encerrado pelo usuário.")
    finally:
        server.close()


if __name__ == "__main__":
    main()
