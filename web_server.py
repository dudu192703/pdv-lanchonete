"""Servidor web do PDV. Execute: python -m uvicorn web_server:app --host 127.0.0.1 --port 8000"""
from pathlib import Path
import os
import secrets
import base64
import binascii
import io
import uuid
import time
import sys
import json
import hashlib
from collections import defaultdict
from PIL import Image, UnidentifiedImageError
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import FileResponse, Response
from fastapi import Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from core import Store, cents, money

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
DATA = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "PDVLanchonete" if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DATA.mkdir(parents=True, exist_ok=True)
IMAGES = DATA / 'product_images'
IMAGES.mkdir(exist_ok=True)
PASSWORD = os.getenv("PDV_PASSWORD", "")
PASSWORD_FILE = DATA / "password.json"
if not PASSWORD and not PASSWORD_FILE.exists():
    raise RuntimeError("Defina PDV_PASSWORD ou configure a senha pelo aplicativo Windows.")

def valid_password(value):
    if PASSWORD:
        return secrets.compare_digest(value, PASSWORD)
    settings = json.loads(PASSWORD_FILE.read_text(encoding="utf-8"))
    digest = hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"),
                                bytes.fromhex(settings["salt"]), 300_000)
    return secrets.compare_digest(digest, bytes.fromhex(settings["hash"]))
SESSIONS = {}
FAILED = defaultdict(list)
SESSION_SECONDS = 8 * 60 * 60

app = FastAPI(title="PDV Lanchonete", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "web"), name="static")

def auth(request: Request):
    sid = request.cookies.get("pdv_session", "")
    expires = SESSIONS.get(sid, 0)
    if not sid or expires < time.time():
        raise HTTPException(401, "Faça login para continuar.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        # Same-origin request header is required for state-changing operations.
        if request.headers.get("X-PDV-Request") != "1":
            raise HTTPException(403, "Requisição não autorizada.")
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Origem não autorizada.")
    SESSIONS[sid] = time.time() + SESSION_SECONDS

def get_store():
    """Uma conexão SQLite independente por requisição, fechada após o uso."""
    db = Store(DATA / "pdv.sqlite3")
    try:
        yield db
    finally:
        db.db.close()

class LoginInput(BaseModel):
    password: str

@app.post("/api/login")
def login(data: LoginInput, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    FAILED[ip] = [t for t in FAILED[ip] if now - t < 900]
    if len(FAILED[ip]) >= 8:
        raise HTTPException(429, "Muitas tentativas. Aguarde 15 minutos.")
    if not valid_password(data.password):
        FAILED[ip].append(now)
        raise HTTPException(401, "Senha incorreta.")
    FAILED.pop(ip, None)
    sid = secrets.token_urlsafe(32)
    SESSIONS[sid] = now + SESSION_SECONDS
    response.set_cookie("pdv_session", sid, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https", max_age=SESSION_SECONDS, path="/")
    return {"ok": True}

@app.post("/api/logout", dependencies=[Depends(auth)])
def logout(request: Request, response: Response):
    SESSIONS.pop(request.cookies.get("pdv_session"), None)
    response.delete_cookie("pdv_session", path="/")
    return {"ok": True}

class MoneyInput(BaseModel):
    amount: str

class MovementInput(MoneyInput):
    kind: str
    note: str

class ProductInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price: str

class NameInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)

class PriceInput(BaseModel):
    price: str

class StockInput(BaseModel):
    quantity: int = Field(ge=0)

class ImageInput(BaseModel):
    data: str

class SaleInput(BaseModel):
    cart: dict[int, int]
    payment: str

@app.get("/")
def home():
    return FileResponse(BASE / "web" / "index.html")

@app.get("/api/state", dependencies=[Depends(auth)])
def state(s: Store = Depends(get_store)):
    session = s.session()
    return {"products": [{"id": p["id"], "name": p["name"], "price": p["price"], "image": bool(p["image"]), "stock": p["stock"]} for p in s.products()],
            "session": {"id": session["id"], "balance": s.balance(session)} if session else None}

@app.post("/api/products", dependencies=[Depends(auth)])
def add_product(data: ProductInput, s: Store = Depends(get_store)):
    try:
        s.add_product(data.name, cents(data.price))
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.put("/api/products/{product_id}/name", dependencies=[Depends(auth)])
def update_product_name(product_id: int, data: NameInput, s: Store = Depends(get_store)):
    try:
        s.rename_product(product_id, data.name)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.delete("/api/products/{product_id}", dependencies=[Depends(auth)])
def delete_product(product_id: int, s: Store = Depends(get_store)):
    try:
        s.delete_product(product_id)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.put("/api/products/{product_id}/price", dependencies=[Depends(auth)])
def update_price(product_id: int, data: PriceInput, s: Store = Depends(get_store)):
    try:
        s.set_product_price(product_id, cents(data.price))
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.put("/api/products/{product_id}/stock", dependencies=[Depends(auth)])
def update_stock(product_id: int, data: StockInput, s: Store = Depends(get_store)):
    try:
        s.set_stock(product_id, data.quantity)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.put("/api/products/{product_id}/image", dependencies=[Depends(auth)])
def upload_product_image(product_id: int, payload: ImageInput, s: Store = Depends(get_store)):
    if len(payload.data) > 6_000_000:
        raise HTTPException(413, "Imagem muito grande (máximo 4 MB).")
    try:
        raw = base64.b64decode(payload.data, validate=True)
        if len(raw) > 4_000_000:
            raise ValueError("Imagem muito grande.")
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("Use JPG, PNG ou WEBP.")
            if source.width * source.height > 20_000_000:
                raise ValueError("Resolução muito alta.")
            source.load()
            image = source.convert("RGB")
            image.thumbnail((800, 800))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=83, optimize=True)
    except (ValueError, UnidentifiedImageError, OSError, binascii.Error) as exc:
        raise HTTPException(400, "Arquivo de imagem inválido.") from exc
    if not s.db.execute("SELECT 1 FROM products WHERE id=?", (product_id,)).fetchone():
        raise HTTPException(404, "Produto não encontrado.")
    filename = uuid.uuid4().hex + ".jpg"
    (IMAGES / filename).write_bytes(output.getvalue())
    s.set_product_image(product_id, filename)
    return {"ok": True}

@app.get("/api/products/{product_id}/image", dependencies=[Depends(auth)])
def product_image(product_id: int, s: Store = Depends(get_store)):
    row = s.db.execute("SELECT image FROM products WHERE id=?", (product_id,)).fetchone()
    if not row or not row["image"]:
        raise HTTPException(404, "Imagem não encontrada.")
    path = IMAGES / Path(row["image"]).name
    if not path.is_file():
        raise HTTPException(404, "Imagem não encontrada.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

@app.post("/api/open", dependencies=[Depends(auth)])
def open_cash(data: MoneyInput, s: Store = Depends(get_store)):
    try:
        s.open(cents(data.amount))
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post("/api/movement", dependencies=[Depends(auth)])
def movement(data: MovementInput, s: Store = Depends(get_store)):
    try:
        s.move(data.kind, cents(data.amount), data.note)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post("/api/sales", dependencies=[Depends(auth)])
def sale(data: SaleInput, s: Store = Depends(get_store)):
    try:
        sale_id, total = s.sell(data.cart, data.payment)
        return {"id": sale_id, "total": total}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post("/api/close", dependencies=[Depends(auth)])
def close_cash(data: MoneyInput, s: Store = Depends(get_store)):
    try:
        expected, difference = s.close(cents(data.amount))
        return {"expected": expected, "difference": difference}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.delete("/api/sales/{sale_id}", dependencies=[Depends(auth)])
def cancel_sale(sale_id: int, s: Store = Depends(get_store)):
    try:
        s.cancel_sale(sale_id)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.get("/api/history", dependencies=[Depends(auth)])
def history(date: str | None = None, s: Store = Depends(get_store)):
    from datetime import date as Date
    if date:
        try:
            Date.fromisoformat(date)
        except ValueError:
            raise HTTPException(400, "Data inválida.")
    where = "WHERE cancelled=0 AND date(created)=?" if date else "WHERE cancelled=0"
    sales = s.db.execute("SELECT id,created,payment,total FROM sales " + where + " ORDER BY id DESC" + ("" if date else " LIMIT 100"), (date,) if date else ()).fetchall()
    return [dict(row) for row in sales]

@app.get("/api/inventory", dependencies=[Depends(auth)])
def inventory(s: Store = Depends(get_store)):
    return [{"id": p["id"], "name": p["name"], "stock": p["stock"]} for p in s.products()]

@app.get("/api/sales/{sale_id}/items", dependencies=[Depends(auth)])
def sale_items(sale_id: int, s: Store = Depends(get_store)):
    if not s.db.execute("SELECT 1 FROM sales WHERE id=? AND cancelled=0", (sale_id,)).fetchone():
        raise HTTPException(404, "Venda não encontrada.")
    rows = s.db.execute("SELECT name,price,quantity FROM items WHERE sale_id=? ORDER BY rowid", (sale_id,)).fetchall()
    return [dict(row) for row in rows]

def filtered_sale_lines(s, product_ids=None, date=None):
    from datetime import date as Date
    if date:
        try:
            Date.fromisoformat(date)
        except ValueError:
            raise HTTPException(400, "Data inválida.")
    filters = ["s.cancelled=0"]
    params = []
    if product_ids:
        placeholders = ",".join("?" for _ in product_ids)
        filters.append("i.product_id IN (" + placeholders + ")")
        params.extend(product_ids)
    if date:
        filters.append("date(s.created)=?")
        params.append(date)
    return s.db.execute(
        "SELECT s.id AS sale_id,s.created,s.payment,i.product_id,i.name,i.price,i.quantity "
        "FROM items i JOIN sales s ON s.id=i.sale_id WHERE " + " AND ".join(filters) +
        " ORDER BY s.id DESC,i.rowid", params
    ).fetchall()

@app.get("/api/sales-summary", dependencies=[Depends(auth)])
def sales_summary(product_id: int | None = None, product_ids: list[int] | None = Query(None),
                  date: str | None = None, s: Store = Depends(get_store)):
    selected = list(product_ids or ([] if product_id is None else [product_id]))
    lines = filtered_sale_lines(s, selected, date)
    totals = {}
    for line in lines:
        key = (line["product_id"], line["name"])
        entry = totals.setdefault(key, {"product_id": line["product_id"], "name": line["name"], "quantity": 0, "total": 0})
        entry["quantity"] += line["quantity"]
        entry["total"] += line["quantity"] * line["price"]
    return sorted(totals.values(), key=lambda row: (-row["quantity"], row["name"]))

@app.get("/api/sales-report.pdf", dependencies=[Depends(auth)])
def sales_report_pdf(product_ids: list[int] | None = Query(None), date: str | None = None,
                     s: Store = Depends(get_store)):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from xml.sax.saxutils import escape
    lines = filtered_sale_lines(s, product_ids, date)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=35, leftMargin=35, topMargin=38, bottomMargin=38)
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    normal.fontSize = 9
    normal.leading = 13
    story = [Paragraph("Relatório de vendas", styles["Title"]),
             Paragraph("Data: " + escape(date or "Todos os dias"), normal), Spacer(1, 12)]
    summary = {}
    for line in lines:
        key = (line["product_id"], line["name"])
        record = summary.setdefault(key, [line["name"], 0, 0])
        record[1] += line["quantity"]
        record[2] += line["quantity"] * line["price"]
    story.append(Paragraph("Resumo dos produtos selecionados", styles["Heading2"]))
    def cell(value):
        return Paragraph(escape(str(value)), normal)
    table_rows = [[cell("Produto"), cell("Qtd."), cell("Valor")]]
    for name, quantity, total in sorted(summary.values(), key=lambda x: x[0]):
        table_rows.append([cell(name), cell(quantity), cell(money(total))])
    if len(table_rows) == 1:
        table_rows.append([cell("Nenhuma venda encontrada"), cell(""), cell("")])
    summary_table = Table(table_rows, colWidths=[310, 55, 115], repeatRows=1, hAlign="LEFT")
    summary_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                                       ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                       ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                                       ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.grey)]))
    story.extend([summary_table, Spacer(1, 12),
                  Paragraph("Total: " + str(sum(v[1] for v in summary.values())) +
                            " unidade(s) - " + money(sum(v[2] for v in summary.values())), styles["Heading3"]),
                  Spacer(1, 10), Paragraph("Detalhamento das vendas", styles["Heading2"])])
    by_sale = {}
    for line in lines:
        by_sale.setdefault(line["sale_id"], []).append(line)
    for sale_id, items in by_sale.items():
        first = items[0]
        parts = [Paragraph("Venda #" + str(sale_id) + " - " + escape(first["created"]) +
                           " - " + escape(first["payment"]), styles["Heading3"])]
        for item in items:
            parts.append(Paragraph(str(item["quantity"]) + " x " + escape(item["name"]) +
                                   " - " + money(item["quantity"] * item["price"]), normal))
        parts.append(Paragraph("Subtotal selecionado: " +
                               money(sum(x["quantity"] * x["price"] for x in items)), normal))
        parts.append(Spacer(1, 9))
        story.append(KeepTogether(parts))
    if not by_sale:
        story.append(Paragraph("Nenhuma venda encontrada.", normal))
    doc.build(story)
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="relatorio-vendas.pdf"',
                             "Cache-Control": "no-store"})

class TabInput(BaseModel):
    customer: str = Field(min_length=1, max_length=120)

class TabItemInput(BaseModel):
    product_id: int

class TabCloseInput(BaseModel):
    payment: str

@app.get("/api/tabs", dependencies=[Depends(auth)])
def list_tabs(s: Store = Depends(get_store)):
    return s.tabs()

@app.post("/api/tabs", dependencies=[Depends(auth)])
def new_tab(data: TabInput, s: Store = Depends(get_store)):
    try:
        return {"id": s.create_tab(data.customer)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.get("/api/tabs/{tab_id}", dependencies=[Depends(auth)])
def get_tab(tab_id: int, s: Store = Depends(get_store)):
    try:
        return s.tab_items(tab_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))

@app.post("/api/tabs/{tab_id}/items", dependencies=[Depends(auth)])
def add_to_tab(tab_id: int, data: TabItemInput, s: Store = Depends(get_store)):
    try:
        s.add_tab_item(tab_id, data.product_id)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.delete("/api/tabs/{tab_id}/items/{product_id}", dependencies=[Depends(auth)])
def remove_from_tab(tab_id: int, product_id: int, s: Store = Depends(get_store)):
    try:
        s.remove_tab_item(tab_id, product_id)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def print_kitchen_raw(content: str):
    """Envia ESC/POS diretamente para a fila de impressao do Windows."""
    if os.name != "nt":
        raise RuntimeError("A impressora da cozinha requer Windows.")
    import ctypes
    from ctypes import wintypes
    printer_name = os.getenv("PDV_KITCHEN_PRINTER", "").strip()
    if not printer_name:
        raise RuntimeError("Configure PDV_KITCHEN_PRINTER com o nome da impressora no Windows.")
    winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)
    class DOC_INFO_1(ctypes.Structure):
        _fields_ = [("pDocName", wintypes.LPWSTR), ("pOutputFile", wintypes.LPWSTR),
                    ("pDatatype", wintypes.LPWSTR)]
    winspool.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    winspool.OpenPrinterW.restype = wintypes.BOOL
    winspool.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(DOC_INFO_1)]
    winspool.StartDocPrinterW.restype = wintypes.DWORD
    winspool.StartPagePrinter.argtypes = [wintypes.HANDLE]
    winspool.StartPagePrinter.restype = wintypes.BOOL
    winspool.WritePrinter.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    winspool.WritePrinter.restype = wintypes.BOOL
    winspool.EndPagePrinter.argtypes = [wintypes.HANDLE]
    winspool.EndDocPrinter.argtypes = [wintypes.HANDLE]
    winspool.ClosePrinter.argtypes = [wintypes.HANDLE]
    handle = wintypes.HANDLE()
    if not winspool.OpenPrinterW(printer_name, ctypes.byref(handle), None):
        raise OSError(ctypes.get_last_error(), "Impressora da cozinha não encontrada: " + printer_name)
    try:
        info = DOC_INFO_1("Pedido da cozinha", None, "RAW")
        if not winspool.StartDocPrinterW(handle, 1, ctypes.byref(info)):
            raise OSError(ctypes.get_last_error(), "Falha ao iniciar impressão")
        try:
            if not winspool.StartPagePrinter(handle):
                raise OSError(ctypes.get_last_error(), "Falha ao iniciar página")
            try:
                # CP850 suporta caracteres portugueses na maioria das impressoras ESC/POS.
                data = b"\\x1b@" + b"\\x1bt\\x02" + content.encode("cp850", errors="replace") + b"\\n\\n\\n"
                buffer = ctypes.create_string_buffer(data)
                written = wintypes.DWORD()
                if not winspool.WritePrinter(handle, buffer, len(data), ctypes.byref(written)) or written.value != len(data):
                    raise OSError(ctypes.get_last_error(), "Falha ao enviar pedido à impressora")
            finally:
                winspool.EndPagePrinter(handle)
        finally:
            winspool.EndDocPrinter(handle)
    finally:
        winspool.ClosePrinter(handle)

@app.post("/api/tabs/{tab_id}/kitchen", dependencies=[Depends(auth)])
def send_tab_to_kitchen(tab_id: int, s: Store = Depends(get_store)):
    try:
        return s.send_kitchen(tab_id, print_kitchen_raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except (OSError, RuntimeError) as exc:
        raise HTTPException(503, "Impressão não concluída: " + str(exc))

@app.post("/api/tabs/{tab_id}/close", dependencies=[Depends(auth)])
def finish_tab(tab_id: int, data: TabCloseInput, s: Store = Depends(get_store)):
    try:
        sale_id,total = s.close_tab(tab_id, data.payment)
        return {"id": sale_id, "total": total}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
