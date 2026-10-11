# PDV Lanchonete — aplicativo offline para Windows 10

## Antes de instalar
1. Feche o servidor Uvicorn antigo (Ctrl+C).
2. Faça backup do arquivo `pdv.sqlite3` e da pasta `product_images` da instalação atual.
3. No PowerShell, dentro da pasta do projeto, execute:
   ```powershell
   git pull origin web-pdv
   powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
   ```
4. Na Área de Trabalho, dê dois cliques em **PDV Lanchonete**.
5. No primeiro acesso, cadastre uma senha de pelo menos 10 caracteres. Essa senha será usada no botão Entrar do PDV.

O instalador de construção precisa de internet **uma única vez** para baixar bibliotecas. Depois disso, o programa funciona sem internet, desde que o computador esteja ligado.

O executável fica em `dist\PDV Lanchonete\PDV Lanchonete.exe`. Mantenha toda a pasta `PDV Lanchonete` junta; não mova só o EXE.

O aplicativo abre uma pequena janela de controle e o PDV no navegador padrão. Fechar a janela de controle encerra o servidor. A URL é `http://127.0.0.1:8000`, acessível apenas no próprio computador.

## Onde ficam os dados?
`%LOCALAPPDATA%\PDVLanchonete\` contém `pdv.sqlite3`, `product_images` e `password.json`.

No primeiro uso, o aplicativo tenta copiar os dados da pasta `%USERPROFILE%\Documents\pdv-web`. A cópia acontece apenas quando o banco de destino ainda não existe. Confira se os dados foram migrados antes de começar a vender. Não exclua a pasta antiga até confirmar.

**Backup:** feche o aplicativo e copie a pasta `%LOCALAPPDATA%\PDVLanchonete` para uma unidade externa. Sem backup, falhas no disco podem causar perda de dados.

**Segurança:** não exponha a porta 8000 na internet. O aplicativo foi projetado para uso local, não para rede pública.
