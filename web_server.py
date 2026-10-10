"""Servidor web do PDV. Execute: python -m uvicorn web_server:app --host 127.0.0.1 --port 8000"""
from pathlib import Path
from contextlib import asynccontextmanager
import os
import secrets
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from core import Store, cents, money

BASE = Path(__file__).resolve().parent
TOKEN = os.getenv("PDV_TOKEN")
if not TOKEN:
    raise RuntimeError("Defina PDV_TOKEN no ambiente antes de iniciar o servidor.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = Store(BASE / "pdv.sqlite3")
    try:
        yield
    finally:
        app.state.store.db.close()

app = FastAPI(title="PDV Lanchonete", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "web"), name="static")

def auth(authorization: str | None = Header(default=None)):
    if not authorization or not secrets.compare_digest(authorization, "Bearer " + TOKEN):
        raise HTTPException(401, "Acesso não autorizado")

def store():
    return app.state.store

class MoneyInput(BaseModel):
    amount: str

class MovementInput(MoneyInput):
    kind: str
    note: str

class ProductInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price: str

class SaleInput(BaseModel):
    cart: dict[int, int]
    payment: str

@app.get("/")
def home():
    return FileResponse(BASE / "web" / "index.html")

@app.get("/api/state", dependencies=[Depends(auth)])
def state():
    s = store()
    session = s.session()
    return {"products": [{"id": p["id"], "name": p["name"], "price": p["price"]} for p in s.products()],
            "session": {"id": session["id"], "balance": s.balance(session)} if session else None}

@app.post("/api/products", dependencies=[Depends(auth)])
def add_product(data: ProductInput):
    try:
        store().add_product(data.name, cents(data.price))
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post("/api/open", dependencies=[Depends(auth)])
def open_cash(data: MoneyInput):
    try:
        store().open(cents(data.amount))
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post("/api/movement", dependencies=[Depends(auth)])
def movement(data: MovementInput):
    try:
        store().move(data.kind, cents(data.amount), data.note)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post("/api/sales", dependencies=[Depends(auth)])
def sale(data: SaleInput):
    try:
        sale_id, total = store().sell(data.cart, data.payment)
        return {"id": sale_id, "total": total}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.post("/api/close", dependencies=[Depends(auth)])
def close_cash(data: MoneyInput):
    try:
        expected, difference = store().close(cents(data.amount))
        return {"expected": expected, "difference": difference}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

@app.get("/api/history", dependencies=[Depends(auth)])
def history():
    s = store()
    sales = s.db.execute("SELECT id,created,payment,total FROM sales ORDER BY id DESC LIMIT 100").fetchall()
    return [dict(row) for row in sales]
