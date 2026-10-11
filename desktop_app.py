"""Aplicativo desktop offline do PDV para Windows."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog
import webbrowser

def main():
    root = tk.Tk()
    root.title("PDV Lanchonete")
    root.geometry("410x190")
    root.resizable(False, False)
    data = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PDVLanchonete"
    data.mkdir(parents=True, exist_ok=True)
    password_file = data / "password.json"
    if not password_file.exists():
        root.withdraw()
        password = simpledialog.askstring("Primeiro acesso", "Crie uma senha para o PDV (mínimo 10 caracteres):", show="*", parent=root)
        if password is None:
            root.destroy()
            return
        if len(password) < 10:
            messagebox.showerror("Senha inválida", "Use pelo menos 10 caracteres.")
            root.destroy()
            return
        confirm = simpledialog.askstring("Confirmar senha", "Digite novamente a senha:", show="*", parent=root)
        if confirm != password:
            messagebox.showerror("Erro", "As senhas não conferem.")
            root.destroy()
            return
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 300_000)
        password_file.write_text(json.dumps({"salt": salt.hex(), "hash": digest.hex()}), encoding="utf-8")
        root.deiconify()
    # Migra dados da instalação anterior somente se o destino ainda não existir.
    old = Path.home() / "Documents" / "pdv-web"
    for name in ("pdv.sqlite3",):
        source, target = old / name, data / name
        if source.exists() and not target.exists():
            try:
                shutil.copy2(source, target)
            except OSError as exc:
                messagebox.showerror("Migração", f"Não foi possível copiar o banco: {exc}")
                root.destroy()
                return
    source_images, target_images = old / "product_images", data / "product_images"
    if source_images.is_dir() and not target_images.exists():
        shutil.copytree(source_images, target_images)
    import uvicorn
    from web_server import app
    host, port = "127.0.0.1", 8000
    with socket.socket() as sock:
        if sock.connect_ex((host, port)) == 0:
            messagebox.showerror("PDV já aberto", "A porta 8000 já está ocupada. Feche o servidor anterior.")
            root.destroy()
            return
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://{host}:{port}"
    def open_pdv():
        webbrowser.open(url)
    tk.Label(root, text="PDV Lanchonete", font=("Segoe UI", 16, "bold")).pack(pady=(20, 8))
    tk.Label(root, text="Funcionando localmente, sem internet.").pack()
    tk.Button(root, text="Abrir PDV", command=open_pdv, width=22).pack(pady=12)
    def close():
        server.should_exit = True
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(1800, open_pdv)
    root.mainloop()

if __name__ == "__main__":
    main()
