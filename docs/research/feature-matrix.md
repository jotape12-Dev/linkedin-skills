# Matriz de recursos — Otto × Typefully × Taplio

Consulta: 2026-10-25. Fontes públicas apenas. Cada célula aponta para o ID em `evidence-register.md`. Classificação entre colchetes: [D]=DECLARADO, [DOC]=DOCUMENTADO, [O]=OBSERVADO, [I]=INFERIDO, [?]=DESCONHECIDO.
Nada aqui foi testado com conta. "Documentado" não é "funciona".

| Recurso | Otto | Typefully | Taplio |
|---|---|---|---|
| Natureza | SaaS autosserviço + tier gerenciado Enterprise [D] E01,E22 | SaaS autosserviço [DOC] E30 | SaaS autosserviço, só LinkedIn como alvo [O] E40 |
| Moeda e preço | BRL: R$49,90 / 119,90 / 299,90 por mês; Enterprise R$5.000 [D] E02 | [?] oficial; terceiro cita US$0 / US$99 ano / US$20 por social set, não confiável E31 | "$" (código não dito): 39 / 69 / 199 por mês; 32 / 49 / 149 em "Compare plans" [O] E41 |
| Teste / reembolso | 7 dias [D]; reembolso [?] (Termos sem política) E02,E19 | [?] | 7 dias; 30 dias de reembolso [O] E41 |
| Limite de posts/geração | ~30 / ~85 / ~240 posts simples por mês, cota compartilhada com revisões, imagens, links [D] E04 | [?] (terceiro: Free 10/mês, Creator 1.000/mês) E31 | Créditos de IA 250 ou ilimitado; comentário 500 ou ilimitado; mapeamento por plano ambíguo [O] E42 |
| LinkedIn | Sim, API oficial declarada; até 20 imagens; sem threads; página de empresa com ID [D][DOC] E05,E06 | Sim, perfil e página; menciona empresas, não pessoas [DOC] E33 | Sim, núcleo do produto [O] E40 |
| X | Sim, API oficial declarada; X Articles agendados pelo próprio Otto [D][DOC] E05,E20 | Sim [DOC] E30 | Não é foco [I] |
| Threads | Doc/blog: disponível (500 chars, 1 imagem); home: "em breve" [DOC][D] E06 | Sim, só posts [DOC] E30 | Não declarado [?] |
| Como autentica nas redes | Login oficial de cada rede; tokens criptografados [D] E05,E12 | Não declarado; menção a "limites da API do LinkedIn" [?]/[I] E33 | Não declarado [?] E45 |
| MCP | Sim: `mcp.otto.doti.gg/mcp`, escopos read/draft/publish [DOC] E08,E09 | Não encontrado [?] E34 | Sim: `mcp.taplio.com`, 14 ferramentas, "beta" [DOC][D] E43,E44 |
| API pública | Não encontrada; só chave `otk_` do MCP [?] E17 | Sim, REST v2 com Bearer e níveis de permissão [DOC] E32 | "Taplio API" citada na página de preços; doc não lida [?] E40 |
| Telegram | Sim, todos os planos [D]; função exata [?] E13 | [?] | [?] |
| Permissões | 3 escopos + admin; ferramentas fora do escopo ficam ocultas [DOC] E09 | READ/WRITE/PUBLISH/ADMIN herdados do usuário da chave [DOC] E32 | Autorização por login; granularidade [?] E43 |
| Aprovação humana | App: obrigatória [D]. MCP: delegada ao cliente; `schedule_posts` sem clique [DOC] E10,E14 | [?] | "Sempre exige confirmação" [D]; mecanismo [?] E44 |
| Voz | Perfil de voz a partir de até 50 tweets; editável; reanálise gasta cota [D] E15 | [?] | [?] |
| Memória | Memórias visíveis/editáveis; guarda anti-repetição [D] E16 | [?] | [?] |
| Limites de taxa | MCP 120 chamadas/min; conflito de agenda <10 min [DOC] E11 | 429 com cabeçalhos; números não vistos [DOC] E32 | [?] |
| Roadmap | Instagram, TikTok, Shorts, Facebook "em breve" [D] E21 | [?] | [?] |

## Parecer crítico (premissas e contra-argumentos)

1. **"Otto é diferenciado por MCP/Telegram" não se sustenta sozinho.** Taplio tem MCP documentado, e Typefully tem API REST. O diferencial real do Otto, pelo que está escrito, é a combinação voz + memória + escopos explícitos + cota em BRL. Isso é DECLARADO, não validado.
2. **Garantia de "1 milhão de views" contradiz os Termos §9** (sem garantia de alcance). Tratar o marketing Enterprise como não confiável até ver as condições (E03).
3. **O fluxo "aprovação obrigatória" depende do canal.** No app é do produto; via MCP a doc diz que a confirmação é do cliente e agendar não pede clique. Quem conectar um agente com `publishing:execute` assume o controle de aprovação. Se a ideia é replicar o Otto no projeto, isso é uma decisão de design explícita, não um detalhe (E10).
4. **Preços de Typefully não são confiáveis aqui.** A única fonte numérica é de um concorrente e agregadores divergem. Não usar em decisão (E31).
5. **Comparação de custo entre produtos é frágil:** moedas diferentes (BRL vs "$"), cota em unidades internas no Otto, créditos no Taplio, posts/mês no Typefully. Não há unidade comum.
6. **Inconsistências do próprio Otto** (Threads "em breve" vs disponível; X Articles Premium vs piloto @doti.gg) sugerem documentação adiantada ou desatualizada em relação ao produto.
7. **Pergunta de conformidade em aberto:** Taplio e Typefully não declaram o vínculo com a API do LinkedIn; só o Otto afirma "API oficial". Mesmo assim o Otto não diz se é parceiro. Para o projeto, o ponto relevante é o que o repositório (Publora) já cobre, não copiar a arquitetura de terceiros, que é DESCONHECIDA.
8. **O que exigiria conta:** comportamento real de voz, qualidade, telas de consentimento, limites efetivos, Telegram, preços do top-up. Ver lista no fim de `sources.md`.
