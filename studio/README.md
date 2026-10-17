# ArqFiel Studio — protótipo web privado

Frontend HTML/CSS/JS sem build, backend Node serverless no Vercel para acessar o MCP ArqFiel 3D já implantado. Todo o Studio deve ficar protegido por **Vercel Authentication (SSO), deploymentType: all**, na equipe proprietária. Não configure deployment desprotegido: o proxy confia no SSO do Vercel para a identidade da sessão.

## Requisitos

- Configure `ARQFIEL_MCP_API_KEY` como segredo criptografado no projeto do Studio. Não coloque essa chave no código/HTML/browser. A mesma chave autenticará no MCP existente.
- Vercel Authentication `all` em **todo** o projeto do Studio. Isso é obrigatório para proteção de plantas e da API /api/call.
- Após confirmar no painel que `ssoProtection.deploymentType` é `all`, defina `ARQFIEL_STUDIO_SSO_CONFIRMED=true` no servidor (environments production e preview). Sem essa confirmação, o proxy responde 503, para evitar que uma aplicação exposta acidentalmente use a chave MCP.
- Motor MCP remoto mantido em https://arq-fiel-3d-mcp.vercel.app/api/mcp com sua própria autenticação Bearer.

## Fluxo

1. Importar planta PDF vetorial, DXF ou imagem (máx. 1,5MB); extrair até 300 linhas candidatas.
2. Marcar dois pontos e informar uma medida real (escala). Nenhuma dimensão é inferida sem confirmação.
3. Desenhar perímetros ou adotar candidatos de poligonização (que precisam de aprovação humana).
4. Validar geometria confirmada e acrescentar aberturas, estilo e mobiliário conceitual.
5. Exportar GLB, baixar JSON de projeto e gerar perspectiva PNG de cada cômodo.

Processamento transitório no motor MCP, sem banco de dados de plantas, e estado da interface mantido só na memória desta aba. Use 'Salvar projeto' para conservar trabalho; reabra o JSON no campo 'Reabrir projeto salvo (JSON)' em outra sessão. O browser busca o módulo de exibição Three.js pela CDN `esm.sh`; o modelo GLB fica na memória do navegador. Caso CDN não carregue, faça download do GLB e visualize em software 3D.

## Limitações

Não reconstrói fielmente edifícios apenas a partir de imagens vagas. Requer medidas e aprovação dos perímetros. PDF escaneado sem vetores deve ser convertido para imagem pelo usuário. Mobiliário é conceitual, não fotorrealista. Projeto não equivale a as-built, revisão estrutural, aprovação de reforma ou certificação de instalações.

## Testes

`node --test tests/*.test.cjs`
