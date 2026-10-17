# Motor ArqFiel 3D (MCP)

API Python MCP protegida por token Bearer. O JSON de entrada é calibrado e revisado antes de construir geometria GLB e prévias PNG. Não é renderização fotorrealista nem atestado as-built.

No Vercel, configure a raiz do projeto como `mcp`, a variável de ambiente `ARQFIEL_MCP_API_KEY` como segredo criptografado e a rota MCP em `https://<dominio>/api/mcp`.

A rota de saúde `/api/health` não oferece acesso às plantas; ferramentas sensíveis exigem autenticação. Nunca publique a chave do MCP no GitHub ou em código do navegador.

O Studio web é outro projeto e usa o mesmo segredo somente no proxy do servidor, não em arquivos HTML ou JavaScript públicos.

Testes: `python -m pytest mcp/tests -q` a partir da raiz do repositório.
