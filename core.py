import sqlite3
from decimal import Decimal, InvalidOperation


def cents(text):
    try:
        value = Decimal(str(text).strip().replace(',', '.'))
        if not value.is_finite() or value < 0 or value != value.quantize(Decimal('.01')):
            raise ValueError
        return int(value * 100)
    except (InvalidOperation, ValueError):
        raise ValueError('Informe um valor positivo com até duas casas decimais.') from None


def money(value):
    return f'R$ {value / 100:.2f}'.replace('.', ',')


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys = ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, price INTEGER NOT NULL CHECK(price > 0));
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY, opened TEXT DEFAULT CURRENT_TIMESTAMP,
                closed TEXT, initial INTEGER NOT NULL, counted INTEGER);
            CREATE UNIQUE INDEX IF NOT EXISTS one_open ON sessions((1)) WHERE closed IS NULL;
            CREATE TABLE IF NOT EXISTS movements (
                id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES sessions(id),
                created TEXT DEFAULT CURRENT_TIMESTAMP, kind TEXT NOT NULL,
                amount INTEGER NOT NULL, note TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES sessions(id),
                created TEXT DEFAULT CURRENT_TIMESTAMP, payment TEXT NOT NULL, total INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS items (
                sale_id INTEGER REFERENCES sales(id), product_id INTEGER REFERENCES products(id),
                name TEXT NOT NULL, price INTEGER NOT NULL, quantity INTEGER NOT NULL);
        ''')
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(products)")}
        if "image" not in columns:
            with self.db:
                self.db.execute("ALTER TABLE products ADD COLUMN image TEXT")
        if "stock" not in columns:
            with self.db:
                self.db.execute("ALTER TABLE products ADD COLUMN stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0)")
        if "cost" not in columns:
            with self.db:
                self.db.execute("ALTER TABLE products ADD COLUMN cost INTEGER")
        if "category_id" not in columns:
            with self.db:
                self.db.execute("ALTER TABLE products ADD COLUMN category_id INTEGER")
        self.db.execute("""CREATE TABLE IF NOT EXISTS waiter_categories (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            position INTEGER NOT NULL DEFAULT 0)""")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tabs (
                id INTEGER PRIMARY KEY, customer TEXT NOT NULL,
                created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                closed TEXT, sale_id INTEGER REFERENCES sales(id));
            CREATE TABLE IF NOT EXISTS tab_items (
                tab_id INTEGER NOT NULL REFERENCES tabs(id),
                product_id INTEGER NOT NULL REFERENCES products(id),
                name TEXT NOT NULL, price INTEGER NOT NULL, quantity INTEGER NOT NULL,
                PRIMARY KEY(tab_id, product_id));
        """)
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(products)")}
        if "active" not in columns:
            with self.db:
                self.db.execute("ALTER TABLE products ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        sale_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(sales)")}
        if "cancelled" not in sale_columns:
            with self.db:
                self.db.execute("ALTER TABLE sales ADD COLUMN cancelled INTEGER NOT NULL DEFAULT 0")
        self.db.execute("PRAGMA busy_timeout = 5000")
        self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        tab_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(tab_items)")}
        if "sent_quantity" not in tab_columns:
            with self.db:
                self.db.execute("ALTER TABLE tab_items ADD COLUMN sent_quantity INTEGER NOT NULL DEFAULT 0")
        self.db.execute("""CREATE TABLE IF NOT EXISTS kitchen_prints (
            id INTEGER PRIMARY KEY, tab_id INTEGER NOT NULL REFERENCES tabs(id),
            created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, content TEXT NOT NULL)""")

        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS variant_groups (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS variant_options (id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL REFERENCES variant_groups(id) ON DELETE CASCADE, name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tab_variant_items (id INTEGER PRIMARY KEY, tab_id INTEGER NOT NULL REFERENCES tabs(id), product_id INTEGER NOT NULL REFERENCES products(id), name TEXT NOT NULL, price INTEGER NOT NULL, choices TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 1, sent_quantity INTEGER NOT NULL DEFAULT 0, UNIQUE(tab_id,product_id,choices));
        """)


    def waiter_categories(self):
        return [dict(row) for row in self.db.execute(
            "SELECT id,name FROM waiter_categories ORDER BY position,id")]

    def create_waiter_category(self, name):
        name = name.strip()
        if not name or len(name) > 60:
            raise ValueError("Informe um nome de categoria com até 60 caracteres.")
        try:
            with self.db:
                position = self.db.execute("SELECT COALESCE(MAX(position),0)+1 FROM waiter_categories").fetchone()[0]
                return self.db.execute(
                    "INSERT INTO waiter_categories(name,position) VALUES (?,?)",
                    (name,position)).lastrowid
        except sqlite3.IntegrityError:
            raise ValueError("Essa categoria já existe.") from None

    def delete_waiter_category(self, category_id):
        with self.db:
            self.db.execute("UPDATE products SET category_id=NULL WHERE category_id=?", (category_id,))
            if not self.db.execute("DELETE FROM waiter_categories WHERE id=?", (category_id,)).rowcount:
                raise ValueError("Categoria não encontrada.")

    def set_waiter_category(self, product_id, category_id):
        with self.db:
            if category_id is not None and not self.db.execute(
                "SELECT 1 FROM waiter_categories WHERE id=?", (category_id,)).fetchone():
                raise ValueError("Categoria não encontrada.")
            if not self.db.execute("UPDATE products SET category_id=? WHERE id=? AND active=1",
                                   (category_id,product_id)).rowcount:
                raise ValueError("Produto não encontrado.")

    def variant_groups(self, product_id):
        groups = self.db.execute("SELECT id,name FROM variant_groups WHERE product_id=? ORDER BY id",(product_id,)).fetchall()
        return [{"id":g["id"],"name":g["name"],"options":[dict(o) for o in self.db.execute("SELECT id,name FROM variant_options WHERE group_id=? ORDER BY id",(g["id"],))]} for g in groups]

    def add_variant_group(self, product_id, name):
        name=name.strip()
        if not name or len(name)>80: raise ValueError("Nome inválido.")
        with self.db:
            if not self.db.execute("SELECT 1 FROM products WHERE id=? AND active=1",(product_id,)).fetchone(): raise ValueError("Produto não encontrado.")
            return self.db.execute("INSERT INTO variant_groups(product_id,name) VALUES (?,?)",(product_id,name)).lastrowid

    def add_variant_option(self, group_id, name):
        name=name.strip()
        if not name or len(name)>80: raise ValueError("Nome inválido.")
        with self.db:
            if not self.db.execute("SELECT 1 FROM variant_groups WHERE id=?",(group_id,)).fetchone(): raise ValueError("Variedade não encontrada.")
            return self.db.execute("INSERT INTO variant_options(group_id,name) VALUES (?,?)",(group_id,name)).lastrowid

    def delete_variant_group(self, group_id):
        with self.db: self.db.execute("DELETE FROM variant_groups WHERE id=?",(group_id,))

    def delete_variant_option(self, option_id):
        with self.db: self.db.execute("DELETE FROM variant_options WHERE id=?",(option_id,))

    def variant_label(self, product_id, choices):
        groups=self.variant_groups(product_id)
        if not groups:
            if choices: raise ValueError("Produto sem variedades.")
            return ""
        if not isinstance(choices,dict) or set(choices)!={str(g["id"]) for g in groups}: raise ValueError("Escolha todas as variedades.")
        result=[]
        for g in groups:
            option=next((o for o in g["options"] if o["id"]==choices[str(g["id"])]),None)
            if option is None: raise ValueError("Opção inválida.")
            result.append(g["name"]+": "+option["name"])
        return " | ".join(result)

    def cancel_sale(self, sale_id):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            sale = self.db.execute(
                "SELECT s.id, s.cancelled, se.closed FROM sales s "
                "JOIN sessions se ON se.id=s.session_id WHERE s.id=?", (sale_id,)
            ).fetchone()
            if not sale or sale["cancelled"]:
                raise ValueError("Venda não encontrada ou já cancelada.")
            if sale["closed"] is not None:
                raise ValueError("Esta venda pertence a um caixa fechado. Não é possível cancelá-la.")
            lines = self.db.execute(
                "SELECT product_id, quantity FROM items WHERE sale_id=?", (sale_id,)
            ).fetchall()
            for line in lines:
                self.db.execute("UPDATE products SET stock=stock+? WHERE id=?",
                                (line["quantity"], line["product_id"]))
            self.db.execute("UPDATE sales SET cancelled=1 WHERE id=?", (sale_id,))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def set_product_image(self, product_id, filename):
        with self.db:
            cursor = self.db.execute("UPDATE products SET image=? WHERE id=?", (filename, product_id))
            if cursor.rowcount != 1:
                raise ValueError("Produto não encontrado.")

    def rename_product(self, product_id, name):
        name = name.strip()
        if not name or len(name) > 120:
            raise ValueError("Informe um nome com até 120 caracteres.")
        with self.db:
            result = self.db.execute("UPDATE products SET name=? WHERE id=? AND active=1", (name, product_id))
            if result.rowcount != 1:
                raise ValueError("Produto não encontrado.")

    def delete_product(self, product_id):
        # Exclusão lógica mantém integridade e histórico das vendas.
        with self.db:
            result = self.db.execute("UPDATE products SET active=0 WHERE id=? AND active=1", (product_id,))
            if result.rowcount != 1:
                raise ValueError("Produto não encontrado.")
            self.db.execute("DELETE FROM tab_items WHERE product_id=? AND sent_quantity=0", (product_id,))

    def remove_tab_item(self, tab_id, product_id):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if not self.db.execute("SELECT 1 FROM tabs WHERE id=? AND closed IS NULL", (tab_id,)).fetchone():
                raise ValueError("Comanda não encontrada ou já fechada.")
            item = self.db.execute("SELECT quantity FROM tab_items WHERE tab_id=? AND product_id=?", (tab_id, product_id)).fetchone()
            if not item:
                raise ValueError("Produto não está na comanda.")
            if item["quantity"] <= self.db.execute(
                "SELECT sent_quantity FROM tab_items WHERE tab_id=? AND product_id=?",
                (tab_id, product_id)).fetchone()[0]:
                raise ValueError("Este item já foi enviado à cozinha. Não é possível removê-lo pela comanda.")
            if item["quantity"] == 1:
                self.db.execute("DELETE FROM tab_items WHERE tab_id=? AND product_id=?", (tab_id, product_id))
            else:
                self.db.execute("UPDATE tab_items SET quantity=quantity-1 WHERE tab_id=? AND product_id=?", (tab_id, product_id))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def set_product_price(self, product_id, price):
        if type(price) is not int or price <= 0:
            raise ValueError("Informe um preço maior que zero.")
        with self.db:
            updated = self.db.execute("UPDATE products SET price=? WHERE id=?", (price, product_id))
            if updated.rowcount != 1:
                raise ValueError("Produto não encontrado.")

    def set_stock(self, product_id, quantity):
        if type(quantity) is not int or quantity < 0:
            raise ValueError("Informe uma quantidade inteira maior ou igual a zero.")
        with self.db:
            updated = self.db.execute("UPDATE products SET stock=? WHERE id=?", (quantity, product_id))
            if updated.rowcount != 1:
                raise ValueError("Produto não encontrado.")

    def session(self):
        return self.db.execute('SELECT * FROM sessions WHERE closed IS NULL').fetchone()

    def required_session(self):
        session = self.session()
        if not session:
            raise ValueError('Abra o caixa primeiro.')
        return session

    def balance(self, session):
        moves = self.db.execute('SELECT COALESCE(SUM(amount),0) FROM movements WHERE session_id=?', (session['id'],)).fetchone()[0]
        cash = self.db.execute("SELECT COALESCE(SUM(total),0) FROM sales WHERE session_id=? AND payment='Dinheiro' AND cancelled=0", (session['id'],)).fetchone()[0]
        return session['initial'] + moves + cash

    def add_product(self, name, price):
        if not name.strip() or price <= 0:
            raise ValueError('Informe nome e preço maior que zero.')
        with self.db:
            self.db.execute('INSERT INTO products(name,price) VALUES (?,?)', (name.strip(), price))

    def products(self):
        return self.db.execute('SELECT * FROM products WHERE active=1 ORDER BY name').fetchall()

    def open(self, initial):
        if initial < 0 or self.session():
            raise ValueError('O caixa já está aberto ou o valor é inválido.')
        with self.db:
            self.db.execute('INSERT INTO sessions(initial) VALUES (?)', (initial,))

    def move(self, kind, amount, note):
        session = self.required_session()
        if kind not in ('Sangria', 'Suprimento') or amount <= 0 or not note.strip():
            raise ValueError('Informe valor maior que zero e motivo.')
        if kind == 'Sangria' and amount > self.balance(session):
            raise ValueError('Saldo em dinheiro insuficiente.')
        with self.db:
            self.db.execute('INSERT INTO movements(session_id,kind,amount,note) VALUES (?,?,?,?)',
                            (session['id'], kind, -amount if kind == 'Sangria' else amount, note.strip()))

    def sell(self, cart, payment, variants=None):
        if not cart and not variants or payment not in ('Dinheiro', 'Pix', 'Cartão', 'Débito', 'Crédito'):
            raise ValueError('Adicione produtos e selecione o pagamento.')
        # Trava de escrita antes de conferir estoque, evitando vendas simultâneas
        # que poderiam utilizar as mesmas unidades.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            session = self.required_session()
            lines = []
            for product_id, quantity in cart.items():
                product = self.db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
                if not product or not product['active'] or type(quantity) is not int or quantity <= 0:
                    raise ValueError('Produto ou quantidade inválida.')
                reserved = self.db.execute(
                    "SELECT COALESCE(SUM(quantity),0) FROM tab_items WHERE product_id=?",
                    (product_id,)).fetchone()[0]
                available = product['stock'] - reserved
                if available < quantity:
                    raise ValueError(f"Estoque insuficiente para {product['name']}. Disponível: {available}.")
                lines.append((product, quantity))
            variant_lines=[]
            for entry in (variants or []):
                pid=entry.get("product_id")
                product=self.db.execute("SELECT * FROM products WHERE id=? AND active=1",(pid,)).fetchone()
                if not product: raise ValueError("Produto inválido.")
                label=self.variant_label(pid,entry.get("choices",{}))
                if not label: raise ValueError("Produto sem variedades.")
                variant_lines.append((product,label))
            counts={}
            for p,q in lines: counts[p["id"]]=counts.get(p["id"],0)+q
            for p,label in variant_lines: counts[p["id"]]=counts.get(p["id"],0)+1
            for pid,quantity in counts.items():
                stock=self.db.execute("SELECT stock FROM products WHERE id=?",(pid,)).fetchone()[0]
                reserved=self.db.execute("SELECT COALESCE(SUM(quantity),0) FROM tab_items WHERE product_id=?",(pid,)).fetchone()[0]
                reserved+=self.db.execute("SELECT COALESCE(SUM(quantity),0) FROM tab_variant_items WHERE product_id=?",(pid,)).fetchone()[0]
                if stock-reserved<quantity: raise ValueError("Estoque insuficiente.")
            total = sum(p['price'] * q for p, q in lines)+sum(p["price"] for p,label in variant_lines)
            sale_id = self.db.execute('INSERT INTO sales(session_id,payment,total) VALUES (?,?,?)',
                                      (session['id'], payment, total)).lastrowid
            self.db.executemany('INSERT INTO items VALUES (?,?,?,?,?)',
                                [(sale_id, p['id'], p['name'], p['price'], q) for p, q in lines]+[(sale_id,p["id"],p["name"]+" ("+label+")",p["price"],1) for p,label in variant_lines])
            for product, quantity in lines:
                self.db.execute('UPDATE products SET stock=stock-? WHERE id=?',
                                (quantity, product['id']))
            for product,label in variant_lines:
                self.db.execute('UPDATE products SET stock=stock-1 WHERE id=?',(product["id"],))
            self.db.commit()
            return sale_id, total
        except BaseException:
            self.db.rollback()
            raise

    def close(self, counted):
        session = self.required_session()
        if counted < 0:
            raise ValueError('Valor contado inválido.')
        expected = self.balance(session)
        with self.db:
            self.db.execute('UPDATE sessions SET closed=CURRENT_TIMESTAMP,counted=? WHERE id=?', (counted, session['id']))
        return expected, counted - expected

    def tabs(self):
        return [dict(r) for r in self.db.execute(
            "SELECT t.id,t.customer,t.created,"
            "(SELECT COALESCE(SUM(price*quantity),0) FROM tab_items WHERE tab_id=t.id)+"
            "(SELECT COALESCE(SUM(price*quantity),0) FROM tab_variant_items WHERE tab_id=t.id) AS total "
            "FROM tabs t WHERE t.closed IS NULL ORDER BY t.id DESC")]

    def create_tab(self, customer):
        customer = customer.strip()
        if not customer or len(customer) > 120:
            raise ValueError("Informe um nome de cliente com até 120 caracteres.")
        with self.db:
            return self.db.execute("INSERT INTO tabs(customer) VALUES (?)", (customer,)).lastrowid

    def tab_items(self, tab_id):
        if not self.db.execute("SELECT 1 FROM tabs WHERE id=? AND closed IS NULL", (tab_id,)).fetchone():
            raise ValueError("Comanda não encontrada ou já fechada.")
        regular=[dict(r,variant_id=None,choices="") for r in self.db.execute("SELECT product_id,name,price,quantity,sent_quantity FROM tab_items WHERE tab_id=? ORDER BY name",(tab_id,))]
        variants=[dict(r,variant_id=r["id"]) for r in self.db.execute("SELECT id,product_id,name,price,quantity,sent_quantity,choices FROM tab_variant_items WHERE tab_id=? ORDER BY id",(tab_id,))]
        return regular+variants

    def add_tab_item(self, tab_id, product_id, choices=None):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            tab = self.db.execute("SELECT id FROM tabs WHERE id=? AND closed IS NULL", (tab_id,)).fetchone()
            product = self.db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
            if not tab or not product or not product["active"]:
                raise ValueError("Comanda ou produto inválido.")
            reserved = self.db.execute(
                "SELECT COALESCE(SUM(quantity),0) FROM tab_items WHERE product_id=?", (product_id,)).fetchone()[0]
            reserved += self.db.execute("SELECT COALESCE(SUM(quantity),0) FROM tab_variant_items WHERE product_id=?",(product_id,)).fetchone()[0]
            if product["stock"] <= reserved:
                raise ValueError("Estoque insuficiente para " + product["name"])
            label=self.variant_label(product_id,choices or {})
            if label:
                self.db.execute("INSERT INTO tab_variant_items(tab_id,product_id,name,price,choices) VALUES (?,?,?,?,?) ON CONFLICT(tab_id,product_id,choices) DO UPDATE SET quantity=quantity+1",(tab_id,product_id,product["name"],product["price"],label))
                self.db.commit()
                return
            self.db.execute(
                "INSERT INTO tab_items(tab_id,product_id,name,price,quantity) VALUES (?,?,?,?,1) "
                "ON CONFLICT(tab_id,product_id) DO UPDATE SET quantity=quantity+1",
                (tab_id,product_id,product["name"],product["price"]))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def remove_checkout_item(self, tab_id, product_id=None, variant_id=None):
        """Remove uma unidade da comanda aberta, inclusive se já foi enviada."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if not self.db.execute("SELECT 1 FROM tabs WHERE id=? AND closed IS NULL", (tab_id,)).fetchone():
                raise ValueError("Comanda não encontrada ou já fechada.")
            if variant_id is not None:
                table, key, value = "tab_variant_items", "id", variant_id
            else:
                table, key, value = "tab_items", "product_id", product_id
            row = self.db.execute(
                f"SELECT quantity,sent_quantity FROM {table} WHERE tab_id=? AND {key}=?",
                (tab_id,value)).fetchone()
            if not row or row["quantity"] < 1:
                raise ValueError("Item não encontrado na comanda.")
            if row["quantity"] == 1:
                self.db.execute(f"DELETE FROM {table} WHERE tab_id=? AND {key}=?", (tab_id,value))
            else:
                sent = min(row["sent_quantity"], row["quantity"]-1)
                self.db.execute(
                    f"UPDATE {table} SET quantity=quantity-1,sent_quantity=? WHERE tab_id=? AND {key}=?",
                    (sent,tab_id,value))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def remove_variant_item(self, tab_id, variant_id):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row=self.db.execute("SELECT quantity,sent_quantity FROM tab_variant_items WHERE id=? AND tab_id=? AND tab_id IN (SELECT id FROM tabs WHERE closed IS NULL)",(variant_id,tab_id)).fetchone()
            if not row or row["quantity"]<=row["sent_quantity"]: raise ValueError("Item inexistente ou já enviado.")
            if row["quantity"]==1: self.db.execute("DELETE FROM tab_variant_items WHERE id=?",(variant_id,))
            else: self.db.execute("UPDATE tab_variant_items SET quantity=quantity-1 WHERE id=?",(variant_id,))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def send_kitchen(self, tab_id, printer):
        # Serializa o envio e o registro para impedir pedidos duplicados.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            tab = self.db.execute(
                "SELECT customer FROM tabs WHERE id=? AND closed IS NULL", (tab_id,)).fetchone()
            if not tab:
                raise ValueError("Comanda não encontrada ou já fechada.")
            items = self.db.execute(
                "SELECT product_id,name,quantity,sent_quantity FROM tab_items WHERE tab_id=? "
                "AND quantity>sent_quantity ORDER BY name", (tab_id,)).fetchall()
            variant_items=self.db.execute("SELECT id,name,choices,quantity,sent_quantity FROM tab_variant_items WHERE tab_id=? AND quantity>sent_quantity ORDER BY id",(tab_id,)).fetchall()
            if not items and not variant_items:
                raise ValueError("Não há novos produtos para enviar à cozinha.")
            from datetime import datetime
            now = datetime.now().strftime("%d/%m/%Y %H:%M")
            text = ("PISCIBAR DO JOAO\nPEDIDO - COZINHA\n"
                    + "-" * 32 + "\nCOMANDA #" + str(tab_id) + "\n"
                    + "Cliente: " + tab["customer"] + "\n" + now + "\n"
                    + "-" * 32 + "\n")
            for item in items:
                text += str(item["quantity"] - item["sent_quantity"]) + "x " + item["name"] + "\n"
            text += "-" * 32 + "\nPREPARAR PEDIDO\n\n\n"
            for item in variant_items:
                text += str(item["quantity"]-item["sent_quantity"])+"x "+item["name"]+"\n"
                for choice in item["choices"].split(" | "):
                    text += "  "+choice+"\n"
            printer(text)
            for item in items:
                self.db.execute(
                    "UPDATE tab_items SET sent_quantity=quantity WHERE tab_id=? AND product_id=?",
                    (tab_id, item["product_id"]))
            for item in variant_items:
                self.db.execute("UPDATE tab_variant_items SET sent_quantity=quantity WHERE id=?",(item["id"],))
            self.db.execute(
                "INSERT INTO kitchen_prints(tab_id,content) VALUES (?,?)", (tab_id,text))
            self.db.commit()
            return {"items": sum(x["quantity"] - x["sent_quantity"] for x in list(items)+list(variant_items))}
        except BaseException:
            self.db.rollback()
            raise

    def close_tab(self, tab_id, payment):
        if payment not in ("Dinheiro","Pix","Cartão","Débito","Crédito"):
            raise ValueError("Forma de pagamento inválida.")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            tab = self.db.execute("SELECT id FROM tabs WHERE id=? AND closed IS NULL", (tab_id,)).fetchone()
            if not tab:
                raise ValueError("Comanda já fechada ou inexistente.")
            session = self.required_session()
            items = self.db.execute(
                "SELECT * FROM tab_items WHERE tab_id=?", (tab_id,)).fetchall()
            variants=self.db.execute("SELECT * FROM tab_variant_items WHERE tab_id=?",(tab_id,)).fetchall()
            if not items and not variants:
                raise ValueError("Comanda sem produtos.")
            quantities={}
            for item in list(items)+list(variants):
                quantities[item["product_id"]]=quantities.get(item["product_id"],0)+item["quantity"]
            for product_id,quantity in quantities.items():
                product=self.db.execute("SELECT stock FROM products WHERE id=?",(product_id,)).fetchone()
                if not product or product["stock"]<quantity: raise ValueError("Estoque insuficiente para fechar comanda.")
            total = sum(item["price"]*item["quantity"] for item in list(items)+list(variants))
            sale_id = self.db.execute(
                "INSERT INTO sales(session_id,payment,total) VALUES (?,?,?)",
                (session["id"],payment,total)).lastrowid
            self.db.executemany("INSERT INTO items VALUES (?,?,?,?,?)",
                [(sale_id,i["product_id"],i["name"],i["price"],i["quantity"]) for i in items]+[(sale_id,i["product_id"],i["name"]+" ("+i["choices"]+")",i["price"],i["quantity"]) for i in variants])
            for item in list(items)+list(variants):
                self.db.execute("UPDATE products SET stock=stock-? WHERE id=?",
                                (item["quantity"],item["product_id"]))
            self.db.execute("UPDATE tabs SET closed=CURRENT_TIMESTAMP,sale_id=? WHERE id=?",
                            (sale_id,tab_id))
            self.db.commit()
            return sale_id,total
        except BaseException:
            self.db.rollback()
            raise
