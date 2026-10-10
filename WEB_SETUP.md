# PDV Web — versão inicial de desenvolvimento

O branch `web-pdv` introduz uma interface responsiva com FastAPI, mantendo o `core.py` e banco SQLite existentes.

## Windows PowerShell

```powershell
git fetch origin
git switch web-pdv
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PDV_TOKEN = (py -c "import secrets; print(secrets.token_urlsafe(32))")
py -m uvicorn web_server:app --host 127.0.0.1 --port 8000
```

Abra http://127.0.0.1:8000 e clique em **Entrar**. A chave exibida apenas na variável de ambiente do PowerShell pode ser consultada com `echo $env:PDV_TOKEN`. Não envie essa chave ao GitHub.

**Importante:** Esta é uma versão de desenvolvimento, **não pronta para exposição pública**. Antes de configurar um túnel, implementar autenticação por sessão, proteção contra CSRF, controle de acesso e testes de concorrência. Não exponha a porta 8000 à internet. A chave em sessionStorage é provisória. O SQLite atual usa uma conexão compartilhada e deve ser refatorado para acesso concorrente antes de múltiplos clientes.

O pagamento atual é dinheiro, Pix ou cartão; pagamento misto e distinção entre débito e crédito continuam pendentes. Impressão USB também não foi implementada.
