"""Agente de impressão do Piscibar do João (Windows).
Requer: py -m pip install pywin32
Configure PDV_SERVER_URL, PDV_PRINT_AGENT_TOKEN e PDV_LOCAL_PRINTER.
"""
import json
import os
import time
import urllib.error
import urllib.request

import win32print

SERVER = os.getenv("PDV_SERVER_URL", "https://piscibardojoao1.shardweb.app").rstrip("/")
TOKEN = os.getenv("PDV_PRINT_AGENT_TOKEN", "").strip()
PRINTER = os.getenv("PDV_LOCAL_PRINTER", "").strip()

def request(path, data=None):
    headers = {"X-PDV-Print-Agent": TOKEN}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        SERVER + path, data=json.dumps(data).encode("utf-8") if data is not None else None,
        headers=headers, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)

def print_ticket(content):
    handle = win32print.OpenPrinter(PRINTER)
    try:
        job = win32print.StartDocPrinter(handle, 1, ("Piscibar - Pedido cozinha", None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            try:
                payload = bytes([27, 64]) + content.encode("cp850", errors="replace") + bytes([10, 10, 10])
                written = win32print.WritePrinter(handle, payload)
                if written != len(payload):
                    raise RuntimeError("Impressão incompleta.")
            finally:
                win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)

def main():
    if not TOKEN or not PRINTER:
        raise SystemExit("Configure PDV_PRINT_AGENT_TOKEN e PDV_LOCAL_PRINTER.")
    print("Agente de impressão ativo:", SERVER, "| Impressora:", PRINTER, flush=True)
    last_failed_id = None
    while True:
        try:
            job = request("/api/print-agent/next")["job"]
            if job:
                if job["id"] == last_failed_id:
                    time.sleep(10)
                    continue
                try:
                    print_ticket(job["content"])
                    request("/api/print-agent/%s/result" % job["id"], {"ok": True})
                    last_failed_id = None
                    print("Pedido impresso: comanda", job["tab_id"], flush=True)
                except Exception as exc:
                    last_failed_id = job["id"]
                    print("Falha na impressão:", exc, flush=True)
                    try:
                        request("/api/print-agent/%s/result" % job["id"], {"ok": False, "error": str(exc)})
                    except Exception as report_error:
                        print("Falha ao registrar erro:", report_error, flush=True)
            else:
                last_failed_id = None
                time.sleep(3)
        except KeyboardInterrupt:
            break
        except urllib.error.HTTPError as exc:
            print("Servidor respondeu HTTP", exc.code, flush=True)
            time.sleep(10)
        except Exception as exc:
            print("Falha na comunicação:", exc, flush=True)
            time.sleep(10)

if __name__ == "__main__":
    main()
