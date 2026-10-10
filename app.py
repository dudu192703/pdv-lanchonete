from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from core import Store, cents, money


class App:
    def __init__(self, root):
        self.root = root
        self.store = Store(Path(__file__).with_name('pdv.sqlite3'))
        self.cart = {}
        root.title('PDV • Lanchonete')
        root.geometry('950x650')
        self.status = tk.StringVar()
        ttk.Label(root, textvariable=self.status, font=('Segoe UI', 14)).pack(pady=15)
        actions = ttk.Frame(root)
        actions.pack()
        for label, action in [('Abrir caixa', self.open), ('Sangria', lambda: self.move('Sangria')),
                              ('Suprimento', lambda: self.move('Suprimento')), ('Fechar caixa', self.close),
                              ('Cadastrar produto', self.product), ('Histórico', self.history)]:
            ttk.Button(actions, text=label, command=lambda fn=action: self.run(fn)).pack(side='left', padx=4)
        panel = ttk.Frame(root)
        panel.pack(fill='both', expand=True, padx=20, pady=20)
        self.catalog = ttk.Treeview(panel, columns=('name', 'price'), show='headings', selectmode='browse')
        self.catalog.heading('name', text='Produto — clique duas vezes para adicionar')
        self.catalog.heading('price', text='Preço')
        self.catalog.column('price', width=100)
        self.catalog.pack(side='left', fill='both', expand=True)
        self.catalog.bind('<Double-1>', lambda event: self.run(self.add))
        self.basket = ttk.Treeview(panel, columns=('name', 'qty', 'total'), show='headings', selectmode='browse')
        for col, title in [('name', 'Carrinho'), ('qty', 'Qtd.'), ('total', 'Subtotal')]:
            self.basket.heading(col, text=title)
            self.basket.column(col, width=140 if col == 'name' else 80)
        self.basket.pack(side='left', fill='both', expand=True, padx=(15, 0))
        footer = ttk.Frame(root)
        footer.pack(pady=15)
        self.total = tk.StringVar()
        ttk.Label(footer, textvariable=self.total, font=('Segoe UI', 16)).pack(side='left', padx=12)
        self.payment = ttk.Combobox(footer, values=['Dinheiro', 'Pix', 'Cartão'], state='readonly', width=12)
        self.payment.set('Dinheiro')
        self.payment.pack(side='left', padx=8)
        ttk.Button(footer, text='Remover item', command=lambda: self.run(self.remove)).pack(side='left', padx=8)
        ttk.Button(footer, text='Finalizar venda', command=lambda: self.run(self.sell)).pack(side='left', padx=8)
        self.refresh()
        root.protocol('WM_DELETE_WINDOW', self.quit)

    def run(self, action):
        try:
            action()
            self.refresh()
        except (ValueError, Exception) as error:
            messagebox.showerror('Não foi possível concluir', str(error))

    def ask_money(self, title):
        value = simpledialog.askstring(title, 'Valor em reais (ex.: 10,50):', parent=self.root)
        return None if value is None else cents(value)

    def refresh(self):
        session = self.store.session()
        self.status.set(f"Caixa #{session['id']} aberto • Dinheiro: {money(self.store.balance(session))}" if session else 'Caixa fechado')
        for tree in (self.catalog, self.basket):
            tree.delete(*tree.get_children())
        total = 0
        for p in self.store.products():
            self.catalog.insert('', 'end', iid=str(p['id']), values=(p['name'], money(p['price'])))
            q = self.cart.get(p['id'], 0)
            if q:
                subtotal = p['price'] * q
                total += subtotal
                self.basket.insert('', 'end', iid=str(p['id']), values=(p['name'], q, money(subtotal)))
        self.total.set('Total: ' + money(total))

    def product(self):
        name = simpledialog.askstring('Novo produto', 'Nome:', parent=self.root)
        if name is None:
            return
        price = self.ask_money('Preço')
        if price is not None:
            self.store.add_product(name, price)

    def add(self):
        selected = self.catalog.selection()
        if selected:
            key = int(selected[0])
            self.cart[key] = self.cart.get(key, 0) + 1

    def remove(self):
        selected = self.basket.selection()
        if selected:
            self.cart.pop(int(selected[0]), None)

    def open(self):
        value = self.ask_money('Fundo inicial do caixa')
        if value is not None:
            self.store.open(value)

    def move(self, kind):
        self.store.required_session()
        value = self.ask_money(kind)
        if value is None:
            return
        note = simpledialog.askstring(kind, 'Motivo:', parent=self.root)
        if note is not None:
            self.store.move(kind, value, note)

    def sell(self):
        self.store.required_session()
        if not self.cart:
            raise ValueError('Adicione produtos ao carrinho.')
        if messagebox.askyesno('Finalizar venda', f'{self.total.get()}\nPagamento: {self.payment.get()}\nConfirmar?'):
            sale_id, total = self.store.sell(self.cart, self.payment.get())
            self.cart.clear()
            messagebox.showinfo('Venda registrada', f'Venda #{sale_id} • {money(total)}')

    def close(self):
        session = self.store.required_session()
        if self.cart:
            raise ValueError('Finalize ou remova os itens do carrinho antes de fechar.')
        value = self.ask_money('Dinheiro contado no fechamento')
        if value is not None and messagebox.askyesno('Fechar caixa', f'Esperado: {money(self.store.balance(session))}\nContado: {money(value)}\nConfirmar fechamento?'):
            expected, difference = self.store.close(value)
            messagebox.showinfo('Caixa fechado', f'Esperado: {money(expected)}\nDiferença: {money(difference)}')

    def history(self):
        window = tk.Toplevel(self.root)
        window.title('Histórico de caixas')
        text = tk.Text(window, width=95, height=25)
        text.pack(fill='both', expand=True)
        for s in self.store.db.execute('SELECT * FROM sessions ORDER BY id DESC'):
            expected = self.store.balance(s)
            text.insert('end', f"Caixa #{s['id']} | abertura UTC: {s['opened']} | fechamento UTC: {s['closed'] or 'aberto'}\n")
            text.insert('end', f"  Dinheiro esperado: {money(expected)} | contado: {money(s['counted']) if s['counted'] is not None else '—'}\n")
            for sale in self.store.db.execute('SELECT * FROM sales WHERE session_id=?', (s['id'],)):
                text.insert('end', f"  Venda #{sale['id']} | {sale['payment']} | {money(sale['total'])}\n")
            for m in self.store.db.execute('SELECT * FROM movements WHERE session_id=?', (s['id'],)):
                text.insert('end', f"  {m['kind']} | {money(m['amount'])} | {m['note']}\n")
        text.configure(state='disabled')

    def quit(self):
        if self.cart and not messagebox.askyesno('Sair', 'Descartar o carrinho não finalizado?'):
            return
        self.store.db.close()
        self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
