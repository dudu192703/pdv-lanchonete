import unittest
from core import Store, cents


class CashTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(':memory:')
        self.store.add_product('Suco', 750)
        self.store.set_stock(1, 10)

    def tearDown(self):
        self.store.db.close()

    def test_cash_cycle(self):
        self.store.open(10000)
        self.store.sell({1: 2}, 'Dinheiro')
        self.store.sell({1: 1}, 'Pix')
        self.store.sell({1: 1}, 'Cartão')
        self.store.move('Sangria', 2000, 'Retirada')
        self.store.move('Suprimento', 500, 'Troco')
        self.assertEqual(self.store.balance(self.store.session()), 10000)
        self.assertEqual(self.store.close(9900), (10000, -100))
        self.assertIsNone(self.store.session())

    def test_invalid_operations_do_not_write(self):
        with self.assertRaises(ValueError):
            self.store.sell({1: 1}, 'Dinheiro')
        self.store.open(0)
        for action in [lambda: self.store.open(0), lambda: self.store.move('Sangria', 1, 'Retirada'),
                       lambda: self.store.sell({1: -1}, 'Dinheiro'), lambda: self.store.sell({999: 1}, 'Pix')]:
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM sales').fetchone()[0], 0)

    def test_stock_decreases_after_sale(self):
        self.store.open(0)
        self.store.sell({1: 3}, 'Pix')
        self.assertEqual(self.store.products()[0]['stock'], 7)

    def test_sale_cannot_exceed_stock(self):
        self.store.open(0)
        with self.assertRaisesRegex(ValueError, 'Estoque insuficiente'):
            self.store.sell({1: 11}, 'Dinheiro')
        self.assertEqual(self.store.products()[0]['stock'], 10)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM sales').fetchone()[0], 0)

    def test_stock_edit_validation(self):
        for qty in [-1, 1.5, '2']:
            with self.assertRaises(ValueError):
                self.store.set_stock(1, qty)

    def test_money(self):
        self.assertEqual(cents('10,50'), 1050)
        for value in ['-1', 'NaN', 'Infinity', '1.001', 'abc']:
            with self.assertRaises(ValueError):
                cents(value)


if __name__ == '__main__':
    unittest.main()
