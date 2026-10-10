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
