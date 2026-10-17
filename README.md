# ArqFiel 3D — MCP + Studio

Repositório do motor geométrico de plantas (`mcp/`) e da interface web privada (`studio/`).

O projeto lê traçados, exige escala conhecida e revisão humana dos cômodos, exporta modelos GLB em metros e gera prévias geométricas PNG. Não é levantamento as-built, certificação estrutural ou renderização fotorrealista.

## Componentes

- `mcp/`: API Python MCP implantável no Vercel. A rota `/api/mcp` exige `Authorization: Bearer <token>` configurado **somente** em `ARQFIEL_MCP_API_KEY` no servidor. `/api/health` reporta o estado do serviço.
- `studio/`: frontend com API Node no Vercel; deve ficar integralmente protegido por **Vercel Authentication — all**. Seu proxy depende de `ARQFIEL_STUDIO_SSO_CONFIRMED=true` e da mesma chave `ARQFIEL_MCP_API_KEY`, ambas exclusivamente no ambiente do servidor.

Os arquivos de entrada e projetos particulares **não devem ser adicionados a este repositório público**. Use apenas o exemplo sintético em `mcp/examples/`.

## Testes

`python -m pytest mcp/tests -q`

`cd studio && node --test tests/*.test.cjs`

## Publicação

Há projetos Vercel **separados e já existentes** para o motor e o Studio. Configure a raiz dos builds em `mcp` e `studio`, respectivamente. Não altere a proteção de implantação para conectar automaticamente serviços privados. Nenhuma credencial real é armazenada no Git.
