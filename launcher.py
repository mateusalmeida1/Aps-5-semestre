from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

import cliente
import interace
import servidor


HOST = "127.0.0.1"
PORT = 5000


def _project_root() -> str:
	return os.path.dirname(os.path.abspath(__file__))


def _entry_command(extra_args: list[str] | None = None) -> list[str]:
	extra_args = extra_args or []
	if getattr(sys, "frozen", False):
		return [sys.executable, *extra_args]
	return [sys.executable, os.path.join(_project_root(), "launcher.py"), *extra_args]


def _spawn(extra_args: list[str] | None = None, new_console: bool = False, hide_console: bool = False) -> subprocess.Popen[bytes]:
	creationflags = 0
	if os.name == "nt":
		if new_console:
			creationflags |= subprocess.CREATE_NEW_CONSOLE
		if hide_console:
			creationflags |= subprocess.CREATE_NO_WINDOW
	return subprocess.Popen(
		_entry_command(extra_args),
		cwd=_project_root(),
		creationflags=creationflags,
	)


def _spawn_client(user: str, local: str, alerta: str, host: str = HOST, port: int = PORT) -> subprocess.Popen[bytes]:
	return _spawn(
		[
			"--gui-client",
			"--host",
			host,
			"--port",
			str(port),
			"--user",
			user,
			"--local",
			local,
			"--alerta",
			alerta,
		],
		new_console=False,
	)


def _spawn_server(port: int) -> subprocess.Popen[bytes]:
	return _spawn(["--server", "--port", str(port)], new_console=False, hide_console=True)


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
	if process.poll() is not None:
		return
	try:
		process.terminate()
		process.wait(timeout=2)
	except Exception:
		try:
			process.kill()
		except Exception:
			pass


def main() -> None:
	parser = argparse.ArgumentParser(description="Inicializador do chat ambiental TCP")
	parser.add_argument("--server", action="store_true", help="Inicia apenas o servidor")
	parser.add_argument("--gui-client", action="store_true", help="Inicia apenas um cliente com interface")
	parser.add_argument("--host", default=HOST)
	parser.add_argument("--port", type=int, default=PORT)
	parser.add_argument("--user", default="Anônimo")
	parser.add_argument("--local", default="Desconhecido")
	parser.add_argument("--alerta", default="NORMAL")
	args, _remaining = parser.parse_known_args()

	if args.server:
		servidor.main(port=args.port)
		return

	if args.gui_client:
		interace.main(
			initial_values={
				"host": args.host,
				"port": str(args.port),
				"user": args.user,
				"local": args.local,
				"alerta": args.alerta,
			},
			auto_connect=False,
		)
		return

	print("[launcher] Iniciando servidor e duas interfaces...")
	server_process = _spawn_server(args.port)
	time.sleep(1.2)

	if server_process.poll() is not None:
		print("[launcher] O servidor encerrou antes de ficar pronto.")
		return

	client_processes = [
		_spawn_client("Usuário 1", "Sala 1", "NORMAL", host=HOST, port=args.port),
		_spawn_client("Usuário 2", "Sala 2", "ALERTA", host=HOST, port=args.port),
	]

	print("[launcher] Interfaces abertas.")
	print("[launcher] Feche as janelas quando terminar.")

	try:
		while True:
			if server_process.poll() is not None:
				print("[launcher] O servidor foi encerrado.")
				break
			if all(process.poll() is not None for process in client_processes):
				print("[launcher] As duas interfaces foram encerradas.")
				break
			time.sleep(0.5)
	except KeyboardInterrupt:
		print("[launcher] Encerrando processos...")
	finally:
		for process in client_processes:
			_terminate_process(process)
		_terminate_process(server_process)


if __name__ == "__main__":
	main()
