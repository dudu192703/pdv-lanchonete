"""Interface escura do PDV. Execute com: python app.py"""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from core import Store, cents, money

BG = "#0a1119"
PANEL = "#111d29"
CARD = "#182634"
EDGE = "#2c3b49"
FG = "#f4f7fa"
MUTED = "#a9b8c6"
ORANGE = "#f5a623"
GREEN = "#13ad5c"
RED = "#c83f3f"
BLUE = "#1765cf"

class App:
    def __init__(self, root):
        self.root = root
        self.store = Store(Path(__file__).with_name("pdv.sqlite3"))
        self.cart = {}
        self.category = "Todos"
        self.search = tk.StringVar()
        self.payment = tk.StringVar(value="Dinheiro")
        self.status = tk.StringVar()
        self.total = tk.StringVar(value="R$ 0,00")
        root.title("Lanchonete | PDV")
        root.geometry("1320x790")
        root.minsize(1050, 640)
        root.configure(bg=BG)
        self.setup_styles()
        self.build()
        self.search.trace_add("write", lambda *_: self.render_products())
        self.refresh()
        root.protocol("WM_DELETE_WINDOW", self.quit)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Dark.Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=FG, rowheight=38, borderwidth=0, font=("Segoe UI", 11))
        style.configure("Dark.Treeview.Heading", background=CARD, foreground=FG,
                        relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Dark.Treeview", background=[("selected", "#31475c")])
        style.configure("Dark.TCombobox", fieldbackground=CARD, background=CARD,
                        foreground=FG, arrowcolor=FG)

    def label(self, parent, text, size=11, color=FG, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kwargs)

    def button(self, parent, text, command, color=CARD, fg=FG, width=None):
        return tk.Button(parent, text=text, command=lambda: self.run(command), bg=color, fg=fg,
                         activebackground=ORANGE, activeforeground=BG, bd=0, relief="flat",
                         cursor="hand2", padx=13, pady=11, width=width,
                         font=("Segoe UI", 10, "bold"))

    def build(self):
        header = tk.Frame(self.root, bg=BG, height=78)
        header.pack(fill="x")
        header.pack_propagate(False)
        self.label(header, "🍔  LANCHONETE  /  PDV", 19, FG, True).pack(side="left", padx=22)
        search = tk.Entry(header, textvariable=self.search, bg=CARD, fg=FG, insertbackground=FG,
                          relief="flat", font=("Segoe UI", 12), width=43)
        search.pack(side="left", padx=30, ipady=12)
        self.label(header, "Pesquisar produto", 10, MUTED).pack(side="left")
        self.button(header, "⚙  Configurações", self.settings).pack(side="right", padx=18)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)
        nav = tk.Frame(body, bg=PANEL, width=188)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        for name, action in [
            ("⌂   CAIXA", lambda: None),
            ("▣   PRODUTOS", self.product),
            ("▤   VENDAS", self.history),
            ("▣   MOVIMENTAR", self.movement_menu),
            ("◫   RELATÓRIOS", self.history),
            ("⚙   CONFIGURAÇÕES", self.settings),
        ]:
            self.button(nav, name, action, ORANGE if name.startswith("⌂") else PANEL,
                        BG if name.startswith("⌂") else FG).pack(fill="x", padx=9, pady=7)

        center = tk.Frame(body, bg=BG)
        center.pack(side="left", fill="both", expand=True, padx=14)
        tabs = tk.Frame(center, bg=BG)
        tabs.pack(fill="x", pady=(8, 10))
        for name in ("Todos", "Lanches", "Porções", "Bebidas", "Sobremesas", "Outros"):
            self.button(tabs, name, lambda n=name: self.set_category(n),
                        ORANGE if name == self.category else CARD,
                        BG if name == self.category else FG).pack(side="left", padx=3)

        self.catalog = ttk.Treeview(center, columns=("name", "price"), show="headings",
                                    style="Dark.Treeview", selectmode="browse")
        self.catalog.heading("name", text="PRODUTOS  •  clique duas vezes para adicionar")
        self.catalog.heading("price", text="PREÇO")
        self.catalog.column("name", minwidth=180, width=370)
        self.catalog.column("price", minwidth=100, width=115, anchor="center")
        self.catalog.pack(fill="both", expand=True)
        self.catalog.bind("<Double-1>", lambda _: self.run(self.add))
        self.label(center, "Dica: clique duas vezes no produto para adicionar ao pedido.", 10, MUTED).pack(anchor="w", pady=8)

        right = tk.Frame(body, bg=PANEL, width=380)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        top = tk.Frame(right, bg=PANEL)
        top.pack(fill="x", padx=14, pady=12)
        self.label(top, "Pedido Atual", 18, FG, True).pack(side="left")
        self.button(top, "Limpar", self.clear, RED).pack(side="right")
        self.basket = ttk.Treeview(right, columns=("name", "qty", "subtotal"),
                                   show="headings", style="Dark.Treeview", height=11)
        for col, text, width in [("name", "Produto", 180), ("qty", "Qtd", 48), ("subtotal", "Total", 105)]:
            self.basket.heading(col, text=text)
            self.basket.column(col, width=width, minwidth=45, anchor="center" if col != "name" else "w")
        self.basket.pack(fill="both", expand=True, padx=12)
        cart_actions = tk.Frame(right, bg=PANEL)
        cart_actions.pack(fill="x", padx=12, pady=8)
        self.button(cart_actions, "−  Retirar 1", self.remove_one).pack(side="left", padx=3)
        self.button(cart_actions, "+  Adicionar 1", self.add_selected).pack(side="left", padx=3)
        self.button(cart_actions, "Excluir", self.remove).pack(side="right", padx=3)

        total_row = tk.Frame(right, bg=PANEL)
        total_row.pack(fill="x", padx=16, pady=13)
        self.label(total_row, "TOTAL", 16, FG, True).pack(side="left")
        tk.Label(total_row, textvariable=self.total, bg=PANEL, fg=ORANGE,
                 font=("Segoe UI", 22, "bold")).pack(side="right")
        self.label(right, "FORMA DE PAGAMENTO", 10, MUTED, True).pack(anchor="w", padx=16)
        pay_grid = tk.Frame(right, bg=PANEL)
        pay_grid.pack(fill="x", padx=12, pady=10)
        options = [("Dinheiro", GREEN), ("Pix", BLUE), ("Débito", ORANGE), ("Crédito", RED), ("Cartão", CARD)]
        for i, (name, color) in enumerate(options):
            tk.Radiobutton(pay_grid, text=name, variable=self.payment, value=name,
                           indicatoron=False, bg=color, fg=BG if name == "Débito" else FG,
                           selectcolor=color, activebackground=color, relief="flat",
                           font=("Segoe UI", 10, "bold"), padx=10, pady=10
                           ).grid(row=i // 2, column=i % 2, sticky="ew", padx=3, pady=3)
        pay_grid.columnconfigure(0, weight=1)
        pay_grid.columnconfigure(1, weight=1)
        self.button(right, "✓  FINALIZAR VENDA", self.sell, GREEN).pack(fill="x", padx=14, pady=(6, 16))

        footer = tk.Frame(self.root, bg=BG, height=55)
        footer.pack(fill="x")
        footer.pack_propagate(False)
        tk.Label(footer, textvariable=self.status, bg=BG, fg=FG,
                 font=("Segoe UI", 11)).pack(side="left", padx=20)
        for name, action in [("Abrir caixa", self.open), ("Sangria", lambda: self.move("Sangria")),
                             ("Suprimento", lambda: self.move("Suprimento")), ("Fechar caixa", self.close)]:
            self.button(footer, name, action).pack(side="right", padx=5, pady=5)

    def run(self, action):
        try:
            action()
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Não foi possível concluir", str(exc))

    def set_category(self, category):
        self.category = category
        self.render_products()

    def render_products(self):
        self.catalog.delete(*self.catalog.get_children())
        query = self.search.get().casefold().strip()
        for p in self.store.products():
            if query not in p["name"].casefold():
                continue
            # O banco atual ainda não possui categorias; exibir todos até a migração.
            self.catalog.insert("", "end", iid=str(p["id"]), values=(p["name"], money(p["price"])))

    def refresh(self):
        session = self.store.session()
        self.status.set(("● Caixa aberto  •  #" + str(session["id"]) +
                         "  •  Dinheiro: " + money(self.store.balance(session)))
                        if session else "● Caixa fechado  •  Abra o caixa para iniciar vendas")
        self.render_products()
        self.basket.delete(*self.basket.get_children())
        total = 0
        products = {p["id"]: p for p in self.store.products()}
        for pid, quantity in list(self.cart.items()):
            p = products.get(pid)
            if not p:
                self.cart.pop(pid, None)
                continue
            subtotal = p["price"] * quantity
            total += subtotal
            self.basket.insert("", "end", iid=str(pid),
                               values=(p["name"], quantity, money(subtotal)))
        self.total.set(money(total))

    def ask_money(self, title):
        value = simpledialog.askstring(title, "Valor em reais (ex.: 10,50):", parent=self.root)
        return None if value is None else cents(value)

    def product(self):
        name = simpledialog.askstring("Cadastrar produto", "Nome do produto:", parent=self.root)
        if name is None:
            return
        price = self.ask_money("Preço")
        if price is not None:
            self.store.add_product(name, price)

    def add(self):
        selected = self.catalog.selection()
        if selected:
            pid = int(selected[0])
            self.cart[pid] = self.cart.get(pid, 0) + 1

    def add_selected(self):
        selected = self.basket.selection()
        if selected:
            pid = int(selected[0])
            self.cart[pid] += 1

    def remove_one(self):
        selected = self.basket.selection()
        if selected:
            pid = int(selected[0])
            self.cart[pid] -= 1
            if self.cart[pid] <= 0:
                del self.cart[pid]

    def remove(self):
        selected = self.basket.selection()
        if selected:
            self.cart.pop(int(selected[0]), None)

    def clear(self):
        self.cart.clear()

    def open(self):
        value = self.ask_money("Fundo inicial do caixa")
        if value is not None:
            self.store.open(value)

    def move(self, kind):
        self.store.required_session()
        value = self.ask_money(kind)
        if value is None:
            return
        note = simpledialog.askstring(kind, "Motivo:", parent=self.root)
        if note is not None:
            self.store.move(kind, value, note)

    def movement_menu(self):
        if messagebox.askyesno("Movimentar caixa", "Registrar uma sangria?\nSelecione Não para suprimento."):
            self.move("Sangria")
        else:
            self.move("Suprimento")

    def sell(self):
        self.store.required_session()
        if not self.cart:
            raise ValueError("Adicione produtos ao pedido.")
        payment = self.payment.get()
        # O núcleo atual só registra três modalidades; manter compatibilidade.
        stored_payment = "Cartão" if payment in ("Débito", "Crédito") else payment
        if messagebox.askyesno("Confirmar venda", f"Total: {self.total.get()}\nPagamento: {payment}\nConfirmar?"):
            sale_id, total = self.store.sell(self.cart, stored_payment)
            self.cart.clear()
            messagebox.showinfo("Venda registrada", f"Venda #{sale_id} • {money(total)}")

    def close(self):
        session = self.store.required_session()
        if self.cart:
            raise ValueError("Limpe ou finalize o pedido antes de fechar o caixa.")
        counted = self.ask_money("Dinheiro contado no fechamento")
        if counted is not None and messagebox.askyesno(
                "Fechar caixa", f"Esperado: {money(self.store.balance(session))}\nContado: {money(counted)}\nConfirmar?"):
            expected, difference = self.store.close(counted)
            messagebox.showinfo("Caixa fechado", f"Esperado: {money(expected)}\nDiferença: {money(difference)}")

    def history(self):
        window = tk.Toplevel(self.root)
        window.title("Histórico de caixas e vendas")
        window.geometry("820x550")
        text = tk.Text(window, bg=PANEL, fg=FG, insertbackground=FG,
                       font=("Consolas", 11), padx=15, pady=15)
        text.pack(fill="both", expand=True)
        for session in self.store.db.execute("SELECT * FROM sessions ORDER BY id DESC"):
            text.insert("end", f"CAIXA #{session['id']} | Aberto: {session['opened']} | Fechado: {session['closed'] or 'não'}\n")
            text.insert("end", f"  Esperado: {money(self.store.balance(session))}\n")
            for sale in self.store.db.execute("SELECT * FROM sales WHERE session_id=?", (session["id"],)):
                text.insert("end", f"  Venda #{sale['id']} | {sale['payment']} | {money(sale['total'])}\n")
            for move in self.store.db.execute("SELECT * FROM movements WHERE session_id=?", (session["id"],)):
                text.insert("end", f"  {move['kind']} | {money(move['amount'])} | {move['note']}\n")
            text.insert("end", "\n")
        text.configure(state="disabled")

    def settings(self):
        messagebox.showinfo("Configurações", "Personalizações e impressão serão adicionadas em outra etapa.")

    def quit(self):
        if self.cart and not messagebox.askyesno("Sair", "Descartar pedido não finalizado?"):
            return
        self.store.db.close()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
