# PDV Web — iniciar no Windows

Na pasta do projeto, execute no PowerShell:

```powershell
git pull origin web-pdv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PDV_PASSWORD = Read-Host "Defina a senha do PDV (mínimo 10 caracteres)"
.\.venv\Scripts\python.exe -m uvicorn web_server:app --host 127.0.0.1 --port 8000
```

Abra http://127.0.0.1:8000 e clique em Entrar. Informe a senha escolhida.

A senha fica na variável de ambiente apenas da sessão do PowerShell. Ao reiniciar em uma nova janela, configure-a novamente. Não coloque a senha em arquivos versionados nem envie ao GitHub. Para configuração permanente, será criado posteriormente um arquivo local seguro.

O login usa cookie HttpOnly com sessão de 8 horas e limite de tentativas incorretas. A sessão se perde ao reiniciar o servidor. Ainda **não exponha o PDV na internet**: falta revisar HTTPS atrás de proxy, CSRF, SQLite concorrente e testes.
