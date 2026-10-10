# PDV Lanchonete

Primeira versão de um PDV local em Python, com interface Tkinter e banco SQLite.

## Executar no Windows

Instale Python 3.11 ou superior pelo instalador oficial, incluindo Tkinter. No PowerShell, dentro da pasta do projeto:

```powershell
python app.py
```

Não há dependências externas. O arquivo `pdv.sqlite3` é criado ao lado do programa. Para backup, feche o programa e copie esse arquivo para um local seguro. Não envie o banco ao GitHub.

## Uso

1. Cadastre os produtos com nome e preço.
2. Abra o caixa com o fundo inicial em dinheiro.
3. Clique duas vezes nos produtos para adicioná-los ao carrinho.
4. Selecione Dinheiro, Pix ou Cartão e finalize a venda.
5. Registre sangrias e suprimentos com motivo.
6. Feche o caixa informando o dinheiro contado; o sistema mostra a diferença.

Pix e cartão são registros manuais, sem integração com bancos ou maquininhas. Apenas vendas em dinheiro afetam o saldo físico. O histórico mostra vendas, movimentações e caixas anteriores; datas são armazenadas em UTC.

## Validação

```powershell
python -m unittest -v
```

## Escopo desta versão

Uso local por um operador com acesso completo, sem login. Inclui cadastro, carrinho, vendas e controle de caixa. Ainda não inclui estoque, edição de produtos, cancelamento de vendas, emissão fiscal, impressão, acesso pelo celular ou túnel. Um túnel exige uma interface web e autenticação, a serem desenvolvidas em uma próxima etapa.
