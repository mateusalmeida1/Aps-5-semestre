"""
interace.py — Interface gráfica (Tkinter) para o cliente do chat TCP/IP.

Como usar:
  1) Inicie o servidor (servidor.py)
  2) Execute este arquivo para abrir a interface
"""

from __future__ import annotations

import queue
import socket
import threading
import os
import sys
import tkinter as tk
from tkinter import ttk


class ChatApp:
	def __init__(self, root: tk.Tk) -> None:
		self.root = root
		self.root.title("Chat Ambiental TCP — Interface")
		self.root.geometry("780x540")

		# Rede/threads
		self.conn: socket.socket | None = None
		self.recv_thread: threading.Thread | None = None
		self.stop_event = threading.Event()
		self.ui_queue: queue.Queue[str] = queue.Queue()
		self.connected = False
		self.registered = False

		# ── Variáveis de UI ────────────────────────────────────────────────
		self.host_var = tk.StringVar(value="127.0.0.1")
		self.port_var = tk.StringVar(value="5000")
		self.user_var = tk.StringVar()
		self.local_var = tk.StringVar()
		self.alerta_var = tk.StringVar(value="NORMAL")
		self.target_var = tk.StringVar()
		self.private_var = tk.StringVar()

		self._build_ui()
		self._set_initial_state()

		self.root.protocol("WM_DELETE_WINDOW", self.on_close)
		self.root.after(100, self.process_ui_queue)

	def _build_ui(self) -> None:
		container = ttk.Frame(self.root, padding=12)
		container.pack(fill="both", expand=True)

		# Conexão
		conn_frame = ttk.LabelFrame(container, text="Conexão", padding=10)
		conn_frame.pack(fill="x")

		ttk.Label(conn_frame, text="Host:").grid(row=0, column=0, sticky="w", padx=(0, 6))
		ttk.Entry(conn_frame, textvariable=self.host_var, width=18).grid(row=0, column=1, sticky="w")

		ttk.Label(conn_frame, text="Porta:").grid(row=0, column=2, sticky="w", padx=(12, 6))
		ttk.Entry(conn_frame, textvariable=self.port_var, width=10).grid(row=0, column=3, sticky="w")

		self.btn_connect = ttk.Button(conn_frame, text="Conectar", command=self.connect)
		self.btn_connect.grid(row=0, column=4, padx=(12, 6))

		self.btn_disconnect = ttk.Button(conn_frame, text="Desconectar", command=self.disconnect)
		self.btn_disconnect.grid(row=0, column=5)

		# Registro
		reg_frame = ttk.LabelFrame(container, text="Cadastro", padding=10)
		reg_frame.pack(fill="x", pady=(10, 0))

		ttk.Label(reg_frame, text="Usuário:").grid(row=0, column=0, sticky="w", padx=(0, 6))
		ttk.Entry(reg_frame, textvariable=self.user_var, width=20).grid(row=0, column=1, sticky="w")

		ttk.Label(reg_frame, text="Localização:").grid(row=0, column=2, sticky="w", padx=(12, 6))
		ttk.Entry(reg_frame, textvariable=self.local_var, width=24).grid(row=0, column=3, sticky="w")

		ttk.Label(reg_frame, text="Alerta:").grid(row=0, column=4, sticky="w", padx=(12, 6))
		self.cmb_alerta = ttk.Combobox(
			reg_frame,
			textvariable=self.alerta_var,
			values=("NORMAL", "ALERTA", "CRÍTICO"),
			width=10,
			state="readonly",
		)
		self.cmb_alerta.grid(row=0, column=5, sticky="w")

		self.btn_register = ttk.Button(reg_frame, text="Entrar no chat", command=self.register)
		self.btn_register.grid(row=0, column=6, padx=(12, 0))

		# Área de mensagens
		chat_frame = ttk.LabelFrame(container, text="Mensagens", padding=10)
		chat_frame.pack(fill="both", expand=True, pady=(10, 0))

		self.txt_chat = tk.Text(chat_frame, wrap="word", state="disabled", height=18)
		self.txt_chat.pack(fill="both", expand=True, side="left")

		scroll = ttk.Scrollbar(chat_frame, orient="vertical", command=self.txt_chat.yview)
		scroll.pack(fill="y", side="right")
		self.txt_chat.configure(yscrollcommand=scroll.set)

		# Envio de mensagens públicas
		send_frame = ttk.Frame(container)
		send_frame.pack(fill="x", pady=(10, 0))

		self.entry_msg = ttk.Entry(send_frame)
		self.entry_msg.pack(side="left", fill="x", expand=True)
		self.entry_msg.bind("<Return>", lambda _e: self.send_public_message())

		self.btn_send = ttk.Button(send_frame, text="Enviar", command=self.send_public_message)
		self.btn_send.pack(side="left", padx=(8, 0))

		self.btn_online = ttk.Button(send_frame, text="/online", command=self.send_online)
		self.btn_online.pack(side="left", padx=(8, 0))

		# Mensagem privada
		pm_frame = ttk.LabelFrame(container, text="Mensagem privada", padding=10)
		pm_frame.pack(fill="x", pady=(10, 0))

		ttk.Label(pm_frame, text="Para:").grid(row=0, column=0, sticky="w", padx=(0, 6))
		ttk.Entry(pm_frame, textvariable=self.target_var, width=18).grid(row=0, column=1, sticky="w")

		ttk.Label(pm_frame, text="Mensagem:").grid(row=0, column=2, sticky="w", padx=(12, 6))
		ttk.Entry(pm_frame, textvariable=self.private_var, width=42).grid(row=0, column=3, sticky="we")

		self.btn_private = ttk.Button(pm_frame, text="Enviar privado", command=self.send_private)
		self.btn_private.grid(row=0, column=4, padx=(10, 0))

		pm_frame.columnconfigure(3, weight=1)

	def _set_initial_state(self) -> None:
		self.btn_disconnect.configure(state="disabled")
		self.btn_register.configure(state="disabled")
		self.entry_msg.configure(state="disabled")
		self.btn_send.configure(state="disabled")
		self.btn_online.configure(state="disabled")
		self.btn_private.configure(state="disabled")

	def _enable_chat_controls(self) -> None:
		self.entry_msg.configure(state="normal")
		self.btn_send.configure(state="normal")
		self.btn_online.configure(state="normal")
		self.btn_private.configure(state="normal")

	def _disable_chat_controls(self) -> None:
		self.entry_msg.configure(state="disabled")
		self.btn_send.configure(state="disabled")
		self.btn_online.configure(state="disabled")
		self.btn_private.configure(state="disabled")

	def append_chat(self, text: str) -> None:
		self.txt_chat.configure(state="normal")
		self.txt_chat.insert("end", f"{text}\n")
		self.txt_chat.see("end")
		self.txt_chat.configure(state="disabled")

	def process_ui_queue(self) -> None:
		while True:
			try:
				msg = self.ui_queue.get_nowait()
			except queue.Empty:
				break
			self.append_chat(msg)
		self.root.after(100, self.process_ui_queue)

	def connect(self) -> None:
		if self.connected:
			return

		host = self.host_var.get().strip() or "127.0.0.1"
		try:
			port = int(self.port_var.get().strip())
		except ValueError:
			self.append_chat("[!] Porta inválida.")
			return

		try:
			self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.conn.connect((host, port))
		except OSError as exc:
			self.append_chat(f"[!] Falha ao conectar: {exc}")
			self.conn = None
			return

		self.connected = True
		self.registered = False
		self.stop_event.clear()

		self.btn_connect.configure(state="disabled")
		self.btn_disconnect.configure(state="normal")
		self.btn_register.configure(state="normal")

		self.append_chat(f"[+] Conectado ao servidor {host}:{port}")
		self.append_chat("[*] Preencha o cadastro e clique em 'Entrar no chat'.")

	def register(self) -> None:
		if not self.connected or not self.conn or self.registered:
			return

		username = (self.user_var.get().strip() or "Anônimo").strip()
		localizacao = (self.local_var.get().strip() or "Desconhecido").strip()
		alerta = (self.alerta_var.get().strip().upper() or "NORMAL").strip()
		if alerta not in ("NORMAL", "ALERTA", "CRÍTICO", "CRITICO"):
			alerta = "NORMAL"
		if alerta == "CRITICO":
			alerta = "CRÍTICO"

		threading.Thread(
			target=self._register_worker,
			args=(username, localizacao, alerta),
			daemon=True,
		).start()

	def _register_worker(self, username: str, localizacao: str, alerta: str) -> None:
		assert self.conn is not None
		conn = self.conn
		try:
			# Protocolo do servidor: prompt -> resposta (3 vezes)
			conn.recv(4096)  # prompt username
			conn.sendall(username.encode("utf-8"))

			conn.recv(4096)  # prompt localização
			conn.sendall(localizacao.encode("utf-8"))

			conn.recv(4096)  # prompt alerta
			conn.sendall(alerta.encode("utf-8"))

			welcome = conn.recv(4096)
			if welcome:
				self.ui_queue.put(welcome.decode("utf-8"))

			self.registered = True
			self.root.after(0, self._on_registered)

			self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
			self.recv_thread.start()

		except OSError as exc:
			self.ui_queue.put(f"[!] Falha no cadastro: {exc}")
			self.root.after(0, self.disconnect)

	def _on_registered(self) -> None:
		self.btn_register.configure(state="disabled")
		self._enable_chat_controls()
		self.append_chat("[*] Cadastro concluído. Você já pode conversar.")

	def _recv_loop(self) -> None:
		if not self.conn:
			return
		while not self.stop_event.is_set():
			try:
				data = self.conn.recv(4096)
				if not data:
					self.ui_queue.put("[!] Servidor desconectado.")
					self.root.after(0, self.disconnect)
					break
				self.ui_queue.put(data.decode("utf-8"))
			except OSError:
				if not self.stop_event.is_set():
					self.ui_queue.put("[!] Conexão encerrada.")
					self.root.after(0, self.disconnect)
				break

	def send_raw(self, message: str) -> None:
		if not self.connected or not self.conn or not self.registered:
			self.append_chat("[!] Conecte e conclua o cadastro antes de enviar mensagens.")
			return
		try:
			self.conn.sendall(message.encode("utf-8"))
		except OSError as exc:
			self.append_chat(f"[!] Falha ao enviar: {exc}")
			self.disconnect()

	def send_public_message(self) -> None:
		msg = self.entry_msg.get().strip()
		if not msg:
			return
		self.entry_msg.delete(0, "end")
		self.send_raw(msg)

	def send_online(self) -> None:
		self.send_raw("/online")

	def send_private(self) -> None:
		target = self.target_var.get().strip()
		text = self.private_var.get().strip()
		if not target or not text:
			self.append_chat("[!] Informe destinatário e mensagem privada.")
			return
		self.private_var.set("")
		self.send_raw(f"/msg {target} {text}")

	def disconnect(self) -> None:
		if not self.connected:
			return

		self.stop_event.set()

		if self.conn:
			try:
				if self.registered:
					self.conn.sendall("/sair".encode("utf-8"))
			except OSError:
				pass
			try:
				self.conn.close()
			except OSError:
				pass

		self.conn = None
		self.connected = False
		self.registered = False

		self.btn_connect.configure(state="normal")
		self.btn_disconnect.configure(state="disabled")
		self.btn_register.configure(state="disabled")
		self._disable_chat_controls()

		self.append_chat("[*] Desconectado.")

	def on_close(self) -> None:
		self.disconnect()
		self.root.destroy()


def main() -> None:
	_configure_tk_env_windows()
	root = tk.Tk()
	app = ChatApp(root)
	root.mainloop()


def _configure_tk_env_windows() -> None:
	"""
	Fallback para ambientes Windows em que o Tkinter não encontra init.tcl.
	"""
	if os.name != "nt":
		return

	# Se já estiver configurado, não sobrescreve.
	if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
		return

	base_python = sys.base_prefix  # ex.: C:\Users\...\Python313
	tcl_dir = os.path.join(base_python, "tcl")
	tcl_lib = os.path.join(tcl_dir, "tcl8.6")
	tk_lib = os.path.join(tcl_dir, "tk8.6")

	if os.path.isdir(tcl_lib) and os.path.isdir(tk_lib):
		os.environ.setdefault("TCL_LIBRARY", tcl_lib)
		os.environ.setdefault("TK_LIBRARY", tk_lib)


if __name__ == "__main__":
	main()
