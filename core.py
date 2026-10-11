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
        self.db = sqlite3.connect(path)
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
        self.db.execute("PRAGMA busy_timeout = 5000")

    def set_product_image(self, product_id, filename):
        with self.db:
            cursor = self.db.execute("UPDATE products SET image=? WHERE id=?", (filename, product_id))
            if cursor.rowcount != 1:
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
        cash = self.db.execute("SELECT COALESCE(SUM(total),0) FROM sales WHERE session_id=? AND payment='Dinheiro'", (session['id'],)).fetchone()[0]
        return session['initial'] + moves + cash

    def add_product(self, name, price):
        if not name.strip() or price <= 0:
            raise ValueError('Informe nome e preço maior que zero.')
        with self.db:
            self.db.execute('INSERT INTO products(name,price) VALUES (?,?)', (name.strip(), price))

    def products(self):
        return self.db.execute('SELECT * FROM products ORDER BY name').fetchall()

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

    def sell(self, cart, payment):
        if not cart or payment not in ('Dinheiro', 'Pix', 'Cartão'):
            raise ValueError('Adicione produtos e selecione o pagamento.')
        # Trava de escrita antes de conferir estoque, evitando vendas simultâneas
        # que poderiam utilizar as mesmas unidades.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            session = self.required_session()
            lines = []
            for product_id, quantity in cart.items():
                product = self.db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
                if not product or type(quantity) is not int or quantity <= 0:
                    raise ValueError('Produto ou quantidade inválida.')
                if product['stock'] < quantity:
                    raise ValueError(f"Estoque insuficiente para {product['name']}. Disponível: {product['stock']}.")
                lines.append((product, quantity))
            total = sum(p['price'] * q for p, q in lines)
            sale_id = self.db.execute('INSERT INTO sales(session_id,payment,total) VALUES (?,?,?)',
                                      (session['id'], payment, total)).lastrowid
            self.db.executemany('INSERT INTO items VALUES (?,?,?,?,?)',
                                [(sale_id, p['id'], p['name'], p['price'], q) for p, q in lines])
            for product, quantity in lines:
                self.db.execute('UPDATE products SET stock=stock-? WHERE id=?',
                                (quantity, product['id']))
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
            "SELECT t.id,t.customer,t.created,COALESCE(SUM(i.price*i.quantity),0) AS total "
            "FROM tabs t LEFT JOIN tab_items i ON i.tab_id=t.id "
            "WHERE t.closed IS NULL GROUP BY t.id ORDER BY t.id DESC")]

    def create_tab(self, customer):
        customer = customer.strip()
        if not customer or len(customer) > 120:
            raise ValueError("Informe um nome de cliente com até 120 caracteres.")
        with self.db:
            return self.db.execute("INSERT INTO tabs(customer) VALUES (?)", (customer,)).lastrowid

    def tab_items(self, tab_id):
        if not self.db.execute("SELECT 1 FROM tabs WHERE id=? AND closed IS NULL", (tab_id,)).fetchone():
            raise ValueError("Comanda não encontrada ou já fechada.")
        return [dict(r) for r in self.db.execute(
            "SELECT product_id,name,price,quantity FROM tab_items WHERE tab_id=? ORDER BY name", (tab_id,))]

    def add_tab_item(self, tab_id, product_id):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            tab = self.db.execute("SELECT id FROM tabs WHERE id=? AND closed IS NULL", (tab_id,)).fetchone()
            product = self.db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
            if not tab or not product:
                raise ValueError("Comanda ou produto inválido.")
            reserved = self.db.execute(
                "SELECT COALESCE(SUM(quantity),0) FROM tab_items WHERE product_id=?", (product_id,)).fetchone()[0]
            if product["stock"] <= reserved:
                raise ValueError("Estoque insuficiente para " + product["name"])
            self.db.execute(
                "INSERT INTO tab_items(tab_id,product_id,name,price,quantity) VALUES (?,?,?,?,1) "
                "ON CONFLICT(tab_id,product_id) DO UPDATE SET quantity=quantity+1",
                (tab_id,product_id,product["name"],product["price"]))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def close_tab(self, tab_id, payment):
        if payment not in ("Dinheiro","Pix","Cartão"):
            raise ValueError("Forma de pagamento inválida.")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            tab = self.db.execute("SELECT id FROM tabs WHERE id=? AND closed IS NULL", (tab_id,)).fetchone()
            if not tab:
                raise ValueError("Comanda já fechada ou inexistente.")
            session = self.required_session()
            items = self.db.execute(
                "SELECT * FROM tab_items WHERE tab_id=?", (tab_id,)).fetchall()
            if not items:
                raise ValueError("Comanda sem produtos.")
            for item in items:
                product = self.db.execute("SELECT stock FROM products WHERE id=?", (item["product_id"],)).fetchone()
                if not product or product["stock"] < item["quantity"]:
                    raise ValueError("Estoque insuficiente para " + item["name"])
            total = sum(item["price"]*item["quantity"] for item in items)
            sale_id = self.db.execute(
                "INSERT INTO sales(session_id,payment,total) VALUES (?,?,?)",
                (session["id"],payment,total)).lastrowid
            self.db.executemany("INSERT INTO items VALUES (?,?,?,?,?)",
                [(sale_id,i["product_id"],i["name"],i["price"],i["quantity"]) for i in items])
            for item in items:
                self.db.execute("UPDATE products SET stock=stock-? WHERE id=?",
                                (item["quantity"],item["product_id"]))
            self.db.execute("UPDATE tabs SET closed=CURRENT_TIMESTAMP,sale_id=? WHERE id=?",
                            (sale_id,tab_id))
            self.db.commit()
            return sale_id,total
        except BaseException:
            self.db.rollback()
            raise
