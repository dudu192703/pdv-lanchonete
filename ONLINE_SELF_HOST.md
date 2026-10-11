# PDV online hospedado no próprio Windows — preparação

O módulo **Comandas** foi adicionado à aplicação FastAPI existente. Este commit **não publica** o sistema na internet nem ativa sincronização entre instalações.

## Teste local primeiro
1. Pare o aplicativo/servidor antigo e faça backup do banco e da pasta de fotos.
2. No repositório: `git pull origin web-pdv`.
3. Para testar no ambiente Python: `python -m uvicorn web_server:app --host 127.0.0.1 --port 8000` (configure `PDV_PASSWORD` antes).
4. Acesse `http://127.0.0.1:8000`, entre e abra a aba **Comandas**.
5. Abra o caixa financeiro, crie uma comanda, adicione produtos e feche a conta. Confira a venda e o estoque.

Se usar o aplicativo empacotado, gere novamente o EXE pelo `build_windows.ps1` para incluir as novas telas.

## Publicação segura
**Não** configure encaminhamento de portas do roteador diretamente para a porta 8000. O servidor local ainda não passou por uma revisão de segurança para exposição pública.

Para acesso remoto, use um túnel HTTPS com controle de acesso (por exemplo, Cloudflare Tunnel com Access) ou VPN privada; mantenha a aplicação ouvindo somente em `127.0.0.1`. Configure autenticação forte, restrinja usuários autorizados e mantenha Windows e dependências atualizados. Não exponha publicamente até a autenticação e o acesso remoto serem testados.

O computador precisa permanecer ligado, conectado à internet e com o servidor em execução.

## Dados e offline
O programa Windows e o servidor Python podem usar caminhos de banco diferentes:
- EXE: `%LOCALAPPDATA%\PDVLanchonete\pdv.sqlite3`
- Python no repositório: `pdv.sqlite3` na pasta do projeto.

**Eles não se sincronizam automaticamente.** Não execute duas cópias independentes para registrar vendas simultaneamente. A sincronização offline/online requer projeto separado de conflitos, IDs e reconciliação de estoque.

O fechamento de comandas exige caixa aberto e registra a venda uma única vez no banco usado pelo servidor. Produtos são adicionados à comanda e descontados do estoque no fechamento; enquanto a comanda estiver aberta, suas quantidades são consideradas reservadas nas novas vendas diretas.
