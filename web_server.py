"""Servidor web do PDV. Execute: python -m uvicorn web_server:app --host 127.0.0.1 --port 8000"""
from pathlib import Path
import os
import secrets
import base64
import binascii
import io
import uuid
import time
from collections import defaultdict
from PIL import Image, UnidentifiedImageError
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from core import Store, cents, money

BASE = Path(__file__).resolve().parent
IMAGES = BASE / 'product_images'
IMAGES.mkdir(exist_ok=True)
PASSWORD = os.getenv("PDV_PASSWORD", "")
if len(PASSWORD) < 10:
    raise RuntimeError("Defina PDV_PASSWORD com pelo menos 10 caracteres antes de iniciar.")
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
    db = Store(BASE / "pdv.sqlite3")
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
    if not secrets.compare_digest(data.password, PASSWORD):
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

@app.get("/api/history", dependencies=[Depends(auth)])
def history(s: Store = Depends(get_store)):
    sales = s.db.execute("SELECT id,created,payment,total FROM sales ORDER BY id DESC LIMIT 100").fetchall()
    return [dict(row) for row in sales]
