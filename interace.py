"""
interace.py - Interface grafica para o Chat de Inspetores Ambientais.

Recursos:
  - Cadastro/login ficticio de agente (local, em JSON)
  - Chat publico e privado
  - Transferencia de arquivos entre usuarios conectados
  - Atalho para envio de relatorio por e-mail (mailto)
  - Captura de webcam e envio da imagem no chat
  - Comunicacao multicast para alertas regionais
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import queue
import socket
import struct
import tempfile
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, ttk
from urllib.parse import quote

AUTH_FILE = "agents_auth.json"
RECEIVED_DIR = "arquivos_recebidos"
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB


def configure_tk_env_windows() -> None:
    if os.name != "nt":
        return

    if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
        return

    base_python = os.path.dirname(os.path.dirname(os.__file__))
    tcl_dir = os.path.join(base_python, "tcl")
    tcl_lib = os.path.join(tcl_dir, "tcl8.6")
    tk_lib = os.path.join(tcl_dir, "tk8.6")

    if os.path.isdir(tcl_lib) and os.path.isdir(tk_lib):
        os.environ.setdefault("TCL_LIBRARY", tcl_lib)
        os.environ.setdefault("TK_LIBRARY", tk_lib)


class AgentAuthStore:
    def __init__(self, file_path: str = AUTH_FILE) -> None:
        self.file_path = file_path
        self.data: dict[str, dict[str, str]] = self._load()

    def _load(self) -> dict[str, dict[str, str]]:
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                return raw
            return {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def register_agent(
        self,
        agent_id: str,
        name: str,
        password: str,
        base: str,
        alerta: str,
    ) -> tuple[bool, str]:
        if not agent_id or not name or not password:
            return False, "Preencha identificacao, nome e senha."
        if agent_id in self.data:
            return False, "Identificacao ja cadastrada."

        self.data[agent_id] = {
            "name": name,
            "password": password,
            "base": base or "Base Desconhecida",
            "alerta": alerta or "NORMAL",
        }
        self._save()
        return True, "Agente cadastrado com sucesso."

    def login(self, agent_id: str, password: str) -> tuple[bool, str, dict[str, str] | None]:
        profile = self.data.get(agent_id)
        if not profile:
            return False, "Identificacao nao encontrada.", None
        if profile.get("password") != password:
            return False, "Senha invalida.", None
        return True, "Login realizado com sucesso.", profile


class MulticastChannel:
    def __init__(self, callback) -> None:
        self.callback = callback
        self.sock: socket.socket | None = None
        self.group = ""
        self.port = 0
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self, group: str, port: int) -> tuple[bool, str]:
        if self.thread and self.thread.is_alive():
            return False, "Canal multicast ja ativo."

        self.group = group
        self.port = port
        self.stop_event.clear()

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("", port))
            mreq = struct.pack("=4sl", socket.inet_aton(group), socket.INADDR_ANY)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self.sock.settimeout(0.6)
        except OSError as exc:
            self.stop()
            return False, f"Falha ao iniciar multicast: {exc}"

        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        return True, f"Multicast ativo em {group}:{port}."

    def _listen_loop(self) -> None:
        assert self.sock is not None
        while not self.stop_event.is_set():
            try:
                data, addr = self.sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError:
                break

            msg = data.decode("utf-8", errors="ignore")
            self.callback(f"[MULTICAST {addr[0]}:{addr[1]}] {msg}")

    def send(self, message: str) -> tuple[bool, str]:
        if not self.sock:
            return False, "Ative o multicast antes de enviar."
        if not message.strip():
            return False, "Mensagem multicast vazia."

        try:
            self.sock.sendto(message.encode("utf-8"), (self.group, self.port))
            return True, "Mensagem multicast enviada."
        except OSError as exc:
            return False, f"Falha no envio multicast: {exc}"

    def stop(self) -> None:
        self.stop_event.set()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None


class ChatApp:
    def __init__(self, root: tk.Tk, initial_values: dict[str, str] | None = None, auto_connect: bool = False) -> None:
        self.root = root
        self.root.title("Centro de Inspecao Ambiental - Rio Tiete")
        self.root.geometry("1120x760")
        self.root.minsize(980, 680)

        self.conn: socket.socket | None = None
        self.recv_thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.ui_queue: queue.Queue[str] = queue.Queue()

        self.connected = False
        self.registered = False
        self.logged_in = False
        self.logged_agent_id = ""
        self.auto_connect = auto_connect

        self.auth_store = AgentAuthStore()
        self.multicast = MulticastChannel(self.ui_queue.put)
        initial_values = initial_values or {}

        self.host_var = tk.StringVar(value=str(initial_values.get("host", "127.0.0.1")))
        self.port_var = tk.StringVar(value=str(initial_values.get("port", "5000")))
        self.user_var = tk.StringVar(value=str(initial_values.get("user", "")))
        self.local_var = tk.StringVar(value=str(initial_values.get("local", "")))
        self.alerta_var = tk.StringVar(value=str(initial_values.get("alerta", "NORMAL")))
        self.target_var = tk.StringVar()
        self.private_var = tk.StringVar()

        self.cad_id_var = tk.StringVar()
        self.cad_name_var = tk.StringVar()
        self.cad_pass_var = tk.StringVar()
        self.cad_base_var = tk.StringVar(value="Salesopolis")
        self.cad_alerta_var = tk.StringVar(value="NORMAL")

        self.login_id_var = tk.StringVar()
        self.login_pass_var = tk.StringVar()
        self.login_status_var = tk.StringVar(value="Agente nao autenticado")

        self.email_var = tk.StringVar(value="central.monitoramento@exemplo.org")
        self.multi_group_var = tk.StringVar(value="224.1.1.1")
        self.multi_port_var = tk.StringVar(value="5007")
        self.multi_msg_var = tk.StringVar(value="Alerta de inspeção no trecho do Tiete")

        self._configure_styles()
        self._build_ui()
        self._set_initial_state()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(120, self.process_ui_queue)
        if self.auto_connect:
            self.root.after(450, self.auto_start)

    def _configure_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.configure(bg="#eef3f9")
        style.configure("Card.TFrame", background="#f7f9fc")
        style.configure("TopBar.TFrame", background="#17324d")
        style.configure("TopBarTitle.TLabel", background="#17324d", foreground="#f3fbff", font=("Segoe UI", 14, "bold"))
        style.configure("TopBarSub.TLabel", background="#17324d", foreground="#cde2f5", font=("Segoe UI", 9))
        style.configure("Section.TLabelframe", background="#f7f9fc")
        style.configure("Section.TLabelframe.Label", background="#f7f9fc", foreground="#223548", font=("Segoe UI", 10, "bold"))
        style.configure("SidebarValue.TLabel", background="#f7f9fc", foreground="#213447", font=("Segoe UI", 9, "bold"))
        style.configure("SidebarLabel.TLabel", background="#f7f9fc", foreground="#526476", font=("Segoe UI", 9))

    def _build_ui(self) -> None:
        top_bar = ttk.Frame(self.root, style="TopBar.TFrame", padding=(12, 10))
        top_bar.pack(fill="x")
        ttk.Label(top_bar, text="Rede de Fiscalizacao Ambiental", style="TopBarTitle.TLabel").pack(anchor="w")
        ttk.Label(
            top_bar,
            text="Monitoramento colaborativo de atividades industriais entre Salesopolis e Grande Sao Paulo",
            style="TopBarSub.TLabel",
        ).pack(anchor="w")

        container = ttk.Frame(self.root, style="Card.TFrame", padding=10)
        container.pack(fill="both", expand=True)

        main_split = ttk.Panedwindow(container, orient="horizontal")
        main_split.pack(fill="both", expand=True)

        sidebar = ttk.Frame(main_split, style="Card.TFrame", padding=(6, 2))
        main_split.add(sidebar, weight=1)

        content = ttk.Frame(main_split, style="Card.TFrame", padding=(10, 2, 2, 2))
        main_split.add(content, weight=4)

        status_card = ttk.LabelFrame(sidebar, text="Painel Operacional", padding=10, style="Section.TLabelframe")
        status_card.pack(fill="x", pady=(0, 8))

        ttk.Label(status_card, text="Regiao foco", style="SidebarLabel.TLabel").pack(anchor="w")
        ttk.Label(status_card, text="Bacia do Tiete", style="SidebarValue.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(status_card, text="Trecho prioritario", style="SidebarLabel.TLabel").pack(anchor="w")
        ttk.Label(status_card, text="Salesopolis -> RMSP", style="SidebarValue.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(status_card, text="Agente logado", style="SidebarLabel.TLabel").pack(anchor="w")
        self.lbl_sidebar_agent = ttk.Label(status_card, text="Nao autenticado", style="SidebarValue.TLabel")
        self.lbl_sidebar_agent.pack(anchor="w")

        quick_card = ttk.LabelFrame(sidebar, text="Conexao", padding=10, style="Section.TLabelframe")
        quick_card.pack(fill="x", pady=(0, 8))

        ttk.Label(quick_card, text="Host:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(quick_card, textvariable=self.host_var, width=14).grid(row=0, column=1, sticky="w")
        ttk.Label(quick_card, text="Porta:").grid(row=1, column=0, sticky="w", padx=(0, 4), pady=(6, 0))
        ttk.Entry(quick_card, textvariable=self.port_var, width=9).grid(row=1, column=1, sticky="w", pady=(6, 0))

        self.btn_connect = ttk.Button(quick_card, text="Conectar", command=self.connect)
        self.btn_connect.grid(row=2, column=0, pady=(10, 0), sticky="we")
        self.btn_disconnect = ttk.Button(quick_card, text="Desconectar", command=self.disconnect)
        self.btn_disconnect.grid(row=2, column=1, pady=(10, 0), sticky="we")

        self.auth_wrap = ttk.Frame(content, style="Card.TFrame")
        self.auth_wrap.pack(fill="x", pady=(0, 8))

        reg_agent_frame = ttk.LabelFrame(self.auth_wrap, text="Cadastro de Agente", padding=8, style="Section.TLabelframe")
        reg_agent_frame.pack(side="left", fill="x", expand=True, padx=(0, 4))

        ttk.Label(reg_agent_frame, text="Identificacao:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(reg_agent_frame, textvariable=self.cad_id_var, width=13).grid(row=0, column=1, sticky="w")

        ttk.Label(reg_agent_frame, text="Nome:").grid(row=0, column=2, sticky="w", padx=(8, 4))
        ttk.Entry(reg_agent_frame, textvariable=self.cad_name_var, width=16).grid(row=0, column=3, sticky="w")

        ttk.Label(reg_agent_frame, text="Senha:").grid(row=1, column=0, sticky="w", padx=(0, 4), pady=(6, 0))
        ttk.Entry(reg_agent_frame, textvariable=self.cad_pass_var, show="*", width=13).grid(row=1, column=1, sticky="w", pady=(6, 0))

        ttk.Label(reg_agent_frame, text="Base:").grid(row=1, column=2, sticky="w", padx=(8, 4), pady=(6, 0))
        ttk.Entry(reg_agent_frame, textvariable=self.cad_base_var, width=16).grid(row=1, column=3, sticky="w", pady=(6, 0))

        ttk.Label(reg_agent_frame, text="Alerta:").grid(row=0, column=4, sticky="w", padx=(8, 4))
        ttk.Combobox(
            reg_agent_frame,
            textvariable=self.cad_alerta_var,
            values=("NORMAL", "ALERTA", "CRITICO"),
            width=10,
            state="readonly",
        ).grid(row=0, column=5, sticky="w")

        self.btn_agent_register = ttk.Button(reg_agent_frame, text="Cadastrar agente", command=self.register_agent)
        self.btn_agent_register.grid(row=1, column=5, sticky="e", pady=(6, 0))

        login_frame = ttk.LabelFrame(self.auth_wrap, text="Login de Agente", padding=8, style="Section.TLabelframe")
        login_frame.pack(side="left", fill="x", expand=True, padx=(4, 0))

        ttk.Label(login_frame, text="Identificacao:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(login_frame, textvariable=self.login_id_var, width=13).grid(row=0, column=1, sticky="w")

        ttk.Label(login_frame, text="Senha:").grid(row=0, column=2, sticky="w", padx=(8, 4))
        ttk.Entry(login_frame, textvariable=self.login_pass_var, show="*", width=13).grid(row=0, column=3, sticky="w")

        self.btn_login = ttk.Button(login_frame, text="Fazer login", command=self.login_agent)
        self.btn_login.grid(row=0, column=4, padx=(8, 0))

        ttk.Label(login_frame, textvariable=self.login_status_var).grid(row=1, column=0, columnspan=5, sticky="w", pady=(6, 0))

        self.profile_frame = ttk.LabelFrame(content, text="Identidade em Operacao", padding=8, style="Section.TLabelframe")
        self.profile_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(self.profile_frame, text="Usuario:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        self.entry_user = ttk.Entry(self.profile_frame, textvariable=self.user_var, width=18)
        self.entry_user.grid(row=0, column=1, sticky="w")

        ttk.Label(self.profile_frame, text="Base de atuacao:").grid(row=0, column=2, sticky="w", padx=(8, 4))
        self.entry_local = ttk.Entry(self.profile_frame, textvariable=self.local_var, width=22)
        self.entry_local.grid(row=0, column=3, sticky="w")

        ttk.Label(self.profile_frame, text="Nivel:").grid(row=0, column=4, sticky="w", padx=(8, 4))
        self.cmb_alerta = ttk.Combobox(
            self.profile_frame,
            textvariable=self.alerta_var,
            values=("NORMAL", "ALERTA", "CRITICO"),
            width=10,
            state="readonly",
        )
        self.cmb_alerta.grid(row=0, column=5, sticky="w")

        self.btn_register = ttk.Button(self.profile_frame, text="Entrar no chat", command=self.register)
        self.btn_register.grid(row=0, column=6, padx=(10, 0))

        chat_frame = ttk.LabelFrame(content, text="Canal de Campo", padding=8, style="Section.TLabelframe")
        chat_frame.pack(fill="both", expand=True)

        self.txt_chat = tk.Text(chat_frame, wrap="word", state="disabled", height=14)
        self.txt_chat.pack(fill="both", expand=True, side="left")
        self.txt_chat.configure(
            bg="#0f1b2b",
            fg="#d6e6f2",
            insertbackground="#d6e6f2",
            selectbackground="#2f4f6f",
            font=("Consolas", 10),
            padx=10,
            pady=10,
            relief="flat",
            borderwidth=0,
        )
        self.txt_chat.tag_configure("system", foreground="#86d3ff")
        self.txt_chat.tag_configure("self", foreground="#94f2b8")
        self.txt_chat.tag_configure("alert", foreground="#ffd27d")
        self.txt_chat.tag_configure("error", foreground="#ff9f9f")

        scroll = ttk.Scrollbar(chat_frame, orient="vertical", command=self.txt_chat.yview)
        scroll.pack(fill="y", side="right")
        self.txt_chat.configure(yscrollcommand=scroll.set)

        send_frame = ttk.Frame(content, style="Card.TFrame")
        send_frame.pack(fill="x", pady=(8, 0))

        self.entry_msg = ttk.Entry(send_frame)
        self.entry_msg.pack(side="left", fill="x", expand=True)
        self.entry_msg.bind("<Return>", lambda _e: self.send_public_message())

        self.btn_send = ttk.Button(send_frame, text="Enviar", command=self.send_public_message)
        self.btn_send.pack(side="left", padx=(8, 0))

        self.btn_online = ttk.Button(send_frame, text="/online", command=self.send_online)
        self.btn_online.pack(side="left", padx=(8, 0))

        self.btn_send_file = ttk.Button(send_frame, text="Enviar arquivo", command=self.send_file_dialog)
        self.btn_send_file.pack(side="left", padx=(8, 0))

        pm_frame = ttk.LabelFrame(content, text="Mensagens Privadas e Transferencias", padding=8, style="Section.TLabelframe")
        pm_frame.pack(fill="x", pady=(8, 0))

        ttk.Label(pm_frame, text="Para:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(pm_frame, textvariable=self.target_var, width=16).grid(row=0, column=1, sticky="w")

        ttk.Label(pm_frame, text="Mensagem:").grid(row=0, column=2, sticky="w", padx=(8, 4))
        ttk.Entry(pm_frame, textvariable=self.private_var, width=40).grid(row=0, column=3, sticky="we")

        self.btn_private = ttk.Button(pm_frame, text="Enviar privado", command=self.send_private)
        self.btn_private.grid(row=0, column=4, padx=(8, 0))
        pm_frame.columnconfigure(3, weight=1)

        tools_frame = ttk.LabelFrame(content, text="Acoes Rapidas de Campo", padding=8, style="Section.TLabelframe")
        tools_frame.pack(fill="x", pady=(8, 0))

        ttk.Label(tools_frame, text="E-mail destino:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(tools_frame, textvariable=self.email_var, width=34).grid(row=0, column=1, sticky="w")

        self.btn_email = ttk.Button(tools_frame, text="Enviar relatorio por e-mail", command=self.open_email_report)
        self.btn_email.grid(row=0, column=2, padx=(8, 0))

        self.btn_webcam = ttk.Button(tools_frame, text="Capturar webcam e enviar", command=self.capture_webcam_and_send)
        self.btn_webcam.grid(row=0, column=3, padx=(8, 0))

        self.btn_open_received = ttk.Button(tools_frame, text="Abrir pasta recebidos", command=self.open_received_folder)
        self.btn_open_received.grid(row=0, column=4, padx=(8, 0))

        multi_frame = ttk.LabelFrame(content, text="Comunicacao Multicast (alerta regional)", padding=8, style="Section.TLabelframe")
        multi_frame.pack(fill="x", pady=(8, 0))

        ttk.Label(multi_frame, text="Grupo:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(multi_frame, textvariable=self.multi_group_var, width=13).grid(row=0, column=1, sticky="w")

        ttk.Label(multi_frame, text="Porta:").grid(row=0, column=2, sticky="w", padx=(8, 4))
        ttk.Entry(multi_frame, textvariable=self.multi_port_var, width=8).grid(row=0, column=3, sticky="w")

        self.btn_multi_start = ttk.Button(multi_frame, text="Ativar canal", command=self.start_multicast)
        self.btn_multi_start.grid(row=0, column=4, padx=(8, 0))

        self.btn_multi_stop = ttk.Button(multi_frame, text="Desativar canal", command=self.stop_multicast)
        self.btn_multi_stop.grid(row=0, column=5, padx=(8, 0))

        ttk.Entry(multi_frame, textvariable=self.multi_msg_var, width=60).grid(row=1, column=0, columnspan=4, sticky="we", pady=(6, 0))
        self.btn_multi_send = ttk.Button(multi_frame, text="Enviar multicast", command=self.send_multicast)
        self.btn_multi_send.grid(row=1, column=4, columnspan=2, padx=(8, 0), pady=(6, 0), sticky="e")

    def _set_initial_state(self) -> None:
        self.btn_disconnect.configure(state="disabled")
        self.btn_register.configure(state="disabled")
        self.entry_msg.configure(state="disabled")
        self.btn_send.configure(state="disabled")
        self.btn_online.configure(state="disabled")
        self.btn_private.configure(state="disabled")
        self.btn_send_file.configure(state="disabled")
        self.btn_email.configure(state="disabled")
        self.btn_webcam.configure(state="disabled")
        self.btn_open_received.configure(state="disabled")

    def _enable_chat_controls(self) -> None:
        self.entry_msg.configure(state="normal")
        self.btn_send.configure(state="normal")
        self.btn_online.configure(state="normal")
        self.btn_private.configure(state="normal")
        self.btn_send_file.configure(state="normal")
        self.btn_email.configure(state="normal")
        self.btn_webcam.configure(state="normal")
        self.btn_open_received.configure(state="normal")

    def _disable_chat_controls(self) -> None:
        self.entry_msg.configure(state="disabled")
        self.btn_send.configure(state="disabled")
        self.btn_online.configure(state="disabled")
        self.btn_private.configure(state="disabled")
        self.btn_send_file.configure(state="disabled")
        self.btn_email.configure(state="disabled")
        self.btn_webcam.configure(state="disabled")
        self.btn_open_received.configure(state="disabled")

    def _collapse_auth_area(self) -> None:
        if self.auth_wrap.winfo_ismapped():
            self.auth_wrap.pack_forget()

    def _lock_identity_area(self) -> None:
        self.entry_user.configure(state="disabled")
        self.entry_local.configure(state="disabled")
        self.cmb_alerta.configure(state="disabled")

    def append_chat(self, text: str) -> None:
        self.txt_chat.configure(state="normal")
        tag = "system"
        upper = text.upper()
        if "[!]" in text or "FALHA" in upper or "ERRO" in upper:
            tag = "error"
        elif "VOCÊ" in upper or "VOCE" in upper:
            tag = "self"
        elif "[ALERTA]" in upper or "[CRITICO]" in upper or "[CRÍTICO]" in upper:
            tag = "alert"
        self.txt_chat.insert("end", f"{text}\n", tag)
        self.txt_chat.see("end")
        self.txt_chat.configure(state="disabled")

    def process_ui_queue(self) -> None:
        while True:
            try:
                msg = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            if not self._handle_special_server_message(msg):
                self.append_chat(msg)

        self.root.after(120, self.process_ui_queue)

    def register_agent(self) -> None:
        ok, msg = self.auth_store.register_agent(
            agent_id=self.cad_id_var.get().strip(),
            name=self.cad_name_var.get().strip(),
            password=self.cad_pass_var.get().strip(),
            base=self.cad_base_var.get().strip(),
            alerta=self.cad_alerta_var.get().strip().upper(),
        )
        self.append_chat(f"[*] {msg}")
        if ok:
            self.cad_pass_var.set("")

    def login_agent(self) -> None:
        ok, msg, profile = self.auth_store.login(
            self.login_id_var.get().strip(),
            self.login_pass_var.get().strip(),
        )
        self.login_status_var.set(msg)

        if not ok or profile is None:
            self.logged_in = False
            self.logged_agent_id = ""
            return

        self.logged_in = True
        self.logged_agent_id = self.login_id_var.get().strip()
        self.user_var.set(profile.get("name", "Agente"))
        self.local_var.set(profile.get("base", "Salesopolis"))

        alerta = profile.get("alerta", "NORMAL").upper()
        if alerta not in ("NORMAL", "ALERTA", "CRITICO"):
            alerta = "NORMAL"
        self.alerta_var.set(alerta)
        self.lbl_sidebar_agent.configure(text=f"{self.user_var.get()} ({self.logged_agent_id})")
        self._collapse_auth_area()

        self.append_chat(
            f"[+] Agente autenticado: {self.user_var.get()} (ID {self.logged_agent_id})."
        )

    def connect(self) -> None:
        if self.connected:
            return
        if not self.logged_in:
            self.append_chat("[!] Faca login do agente antes de conectar ao chat.")
            return

        host = self.host_var.get().strip() or "127.0.0.1"
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            self.append_chat("[!] Porta invalida.")
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

        self.append_chat(f"[+] Conectado ao servidor {host}:{port}.")
        self.append_chat("[*] Clique em 'Entrar no chat' para concluir o registro no servidor.")

    def auto_start(self) -> None:
        if self.connected:
            return
        if not self.logged_in:
            self.append_chat("[!] Auto-connect ignorado: faca login primeiro.")
            return
        self.connect()
        if self.connected:
            self.root.after(250, self.register)

    def register(self) -> None:
        if not self.connected or not self.conn or self.registered:
            return

        username = (self.user_var.get().strip() or "Agente Sem Nome").strip()
        localizacao = (self.local_var.get().strip() or "Base Desconhecida").strip()
        alerta = (self.alerta_var.get().strip().upper() or "NORMAL").strip()
        if alerta not in ("NORMAL", "ALERTA", "CRITICO"):
            alerta = "NORMAL"

        threading.Thread(
            target=self._register_worker,
            args=(username, localizacao, alerta),
            daemon=True,
        ).start()

    def _register_worker(self, username: str, localizacao: str, alerta: str) -> None:
        assert self.conn is not None
        conn = self.conn
        try:
            conn.recv(4096)
            conn.sendall(username.encode("utf-8"))

            conn.recv(4096)
            conn.sendall(localizacao.encode("utf-8"))

            conn.recv(4096)
            conn.sendall(alerta.encode("utf-8"))

            welcome = conn.recv(4096)
            if welcome:
                self.ui_queue.put(welcome.decode("utf-8", errors="ignore"))

            self.registered = True
            self.root.after(0, self._on_registered)

            self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self.recv_thread.start()

        except OSError as exc:
            self.ui_queue.put(f"[!] Falha no cadastro: {exc}")
            self.root.after(0, self.disconnect)

    def _on_registered(self) -> None:
        self.btn_register.configure(state="disabled")
        self._lock_identity_area()
        self._enable_chat_controls()
        self.append_chat("[*] Registro concluido. Canal pronto para operacao.")

    def _recv_loop(self) -> None:
        if not self.conn:
            return

        while not self.stop_event.is_set():
            try:
                data = self.conn.recv(8192)
                if not data:
                    self.ui_queue.put("[!] Servidor desconectado.")
                    self.root.after(0, self.disconnect)
                    break
                self.ui_queue.put(data.decode("utf-8", errors="ignore"))
            except OSError:
                if not self.stop_event.is_set():
                    self.ui_queue.put("[!] Conexao encerrada.")
                    self.root.after(0, self.disconnect)
                break

    def _handle_special_server_message(self, msg: str) -> bool:
        marker = "[[FILE]] "
        idx = msg.find(marker)
        if idx == -1:
            return False

        payload = msg[idx + len(marker):].strip()
        parts = payload.split(" ", 2)
        if len(parts) < 3:
            self.append_chat("[!] Recebido token de arquivo invalido.")
            return True

        sender, filename, b64data = parts

        try:
            content = base64.b64decode(b64data.encode("utf-8"), validate=True)
        except Exception:
            self.append_chat("[!] Arquivo recebido corrompido (base64 invalido).")
            return True

        os.makedirs(RECEIVED_DIR, exist_ok=True)
        safe_name = filename.replace("..", "").replace("/", "_").replace("\\", "_")
        target_path = Path(RECEIVED_DIR) / safe_name

        # Evita sobrescrever arquivo existente adicionando timestamp.
        if target_path.exists():
            stem = target_path.stem
            suffix = target_path.suffix
            target_path = Path(RECEIVED_DIR) / f"{stem}_{int(time.time())}{suffix}"

        try:
            with open(target_path, "wb") as f:
                f.write(content)
        except OSError as exc:
            self.append_chat(f"[!] Falha ao salvar arquivo recebido: {exc}")
            return True

        self.append_chat(f"[ARQUIVO] Recebido de {sender}: {target_path}")
        return True

    def send_raw(self, message: str) -> None:
        if not self.connected or not self.conn or not self.registered:
            self.append_chat("[!] Conecte e conclua o registro antes de enviar mensagens.")
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
            self.append_chat("[!] Informe destinatario e mensagem privada.")
            return
        self.private_var.set("")
        self.send_raw(f"/msg {target} {text}")

    def _send_file_path(self, target: str, path: str, display_name: str | None = None) -> None:
        if not target:
            self.append_chat("[!] Informe o destinatario no campo 'Para'.")
            return

        file_path = Path(path)
        if not file_path.exists() or not file_path.is_file():
            self.append_chat("[!] Arquivo nao encontrado.")
            return

        size = file_path.stat().st_size
        if size > MAX_FILE_SIZE_BYTES:
            self.append_chat("[!] Arquivo muito grande. Limite de 2 MB.")
            return

        try:
            raw = file_path.read_bytes()
        except OSError as exc:
            self.append_chat(f"[!] Falha ao ler arquivo: {exc}")
            return

        b64 = base64.b64encode(raw).decode("utf-8")
        name = display_name or file_path.name

        # O protocolo do servidor usa espacos como separador; por isso o nome nao pode conter espaco.
        safe_name = name.replace(" ", "_")
        self.send_raw(f"/file {target} {safe_name} {b64}")

    def send_file_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecione o arquivo para enviar",
            filetypes=[("Todos os arquivos", "*.*")],
        )
        if not path:
            return

        self._send_file_path(self.target_var.get().strip(), path)

    def open_email_report(self) -> None:
        if not self.registered:
            self.append_chat("[!] Conecte-se ao chat para montar o relatorio.")
            return

        email = self.email_var.get().strip()
        if not email:
            self.append_chat("[!] Informe um e-mail de destino.")
            return

        subject = quote("Relatorio de inspeção ambiental - Rio Tiete")
        body = quote(
            f"Agente: {self.user_var.get()}\n"
            f"Base: {self.local_var.get()}\n"
            f"Nivel: {self.alerta_var.get()}\n\n"
            "Resumo: atividade industrial suspeita de poluicao no trecho monitorado."
        )
        url = f"mailto:{email}?subject={subject}&body={body}"

        webbrowser.open(url)
        self.append_chat("[*] Cliente de e-mail aberto para envio do relatorio.")

    def capture_webcam_and_send(self) -> None:
        target = self.target_var.get().strip()
        if not target:
            self.append_chat("[!] Defina o destinatario no campo 'Para' para enviar imagem da webcam.")
            return

        try:
            import cv2  # type: ignore
        except ImportError:
            self.append_chat("[!] OpenCV nao instalado. Instale com: pip install opencv-python")
            return

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            self.append_chat("[!] Nao foi possivel acessar a webcam.")
            return

        ok, frame = cap.read()
        cap.release()

        if not ok:
            self.append_chat("[!] Falha ao capturar imagem da webcam.")
            return

        tmp_dir = Path(tempfile.gettempdir())
        file_name = f"webcam_{int(time.time())}.jpg"
        file_path = tmp_dir / file_name

        try:
            cv2.imwrite(str(file_path), frame)
        except Exception as exc:
            self.append_chat(f"[!] Falha ao salvar captura de webcam: {exc}")
            return

        self._send_file_path(target, str(file_path), display_name=file_name)

    def open_received_folder(self) -> None:
        os.makedirs(RECEIVED_DIR, exist_ok=True)
        path = os.path.abspath(RECEIVED_DIR)
        webbrowser.open(path)

    def start_multicast(self) -> None:
        group = self.multi_group_var.get().strip() or "224.1.1.1"
        try:
            port = int(self.multi_port_var.get().strip())
        except ValueError:
            self.append_chat("[!] Porta multicast invalida.")
            return

        ok, msg = self.multicast.start(group, port)
        self.append_chat(f"[*] {msg}")

    def stop_multicast(self) -> None:
        self.multicast.stop()
        self.append_chat("[*] Canal multicast desativado.")

    def send_multicast(self) -> None:
        ok, msg = self.multicast.send(self.multi_msg_var.get())
        self.append_chat(f"[*] {msg}")

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
        self.lbl_sidebar_agent.configure(text="Nao autenticado" if not self.logged_in else f"{self.user_var.get()} ({self.logged_agent_id})")

        self.append_chat("[*] Desconectado.")

    def on_close(self) -> None:
        self.multicast.stop()
        self.disconnect()
        self.root.destroy()


def main(initial_values: dict[str, str] | None = None, auto_connect: bool = False) -> None:
    configure_tk_env_windows()
    root = tk.Tk()
    app = ChatApp(root, initial_values=initial_values, auto_connect=auto_connect)
    root.mainloop()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interface grafica do chat ambiental")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="5000")
    parser.add_argument("--user", default="")
    parser.add_argument("--local", default="")
    parser.add_argument("--alerta", default="NORMAL")
    parser.add_argument("--auto", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    initial = {
        "host": args.host,
        "port": args.port,
        "user": args.user,
        "local": args.local,
        "alerta": args.alerta,
    }
    main(initial_values=initial, auto_connect=args.auto)
