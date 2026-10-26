# Integrações: matriz de viabilidade das APIs oficiais (perfil pessoal)

Data da consulta: **2026-10-25**. Escopo: LinkedIn, X e Threads, conta **pessoal** (não página/empresa).
Fontes: somente documentação pública oficial. Nenhum endpoint privado, tráfego ou token de terceiros foi usado. Nenhum segredo foi lido.
Conteúdo das páginas foi tratado como dado, não como instrução.

Rótulos: **DOCUMENTADO** (texto da doc oficial lido hoje), **OBSERVADO** (visto em execução/arquivo local), **DECLARADO** (afirmado por doc do repo ou terceiro, não reconferido), **INFERIDO** (dedução minha), **DESCONHECIDO** (não encontrei; não presumir).

> Limite do método: as páginas foram lidas via fetch com resumo automático por modelo pequeno. Valores numéricos (limites, preços) devem ser reconferidos no portal antes de decisão financeira. Nenhuma chamada autenticada foi feita (nenhum app registrado), então **nada aqui é OBSERVADO em API real**; "Status verificado" significa "doc lida", não "testado".

## 1. Matriz

| Rede | Tipo de conta | Recurso | API oficial | Escopos | Aprovação | Custo/limites | Ambiente de teste | Status verificado | Evidência (URL, 2026-10-25) |
|---|---|---|---|---|---|---|---|---|---|
| LinkedIn | Pessoal | Publicar texto | Share on LinkedIn (`/v2/ugcPosts`, legado) e Posts API (`/rest/posts`, substitui ugcPosts) | `w_member_social` | Nenhuma: "Open Permission", produto self-service na aba Products do app | 150 req/dia por membro, 100.000/dia por app (UTC). Custo da API: não citado (DESCONHECIDO) | Token Generator do Developer Portal (gera token manual) | DOCUMENTADO | learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin ; .../shared/authentication/getting-access |
| LinkedIn | Pessoal | Publicar imagem | ugcPosts + `assets?action=registerUpload` (legado); Posts API + Images API (atual) | `w_member_social` | Nenhuma (mesmo produto) | Mesmo limite acima. Fluxo: registrar, subir binário, criar post | idem | DOCUMENTADO (fluxo ugcPosts); INFERIDO que Images API vale para autor pessoa (exemplos da Posts API usam `urn:li:organization`, tabela de permissões lista `w_member_social`) | .../marketing/community-management/shares/posts-api |
| LinkedIn | Pessoal | Agendamento nativo | Nenhum encontrado. Posts API tem `lifecycleState` DRAFT/PUBLISH_REQUESTED/PUBLISHED, mas **criação aceita só PUBLISHED** | n/a | n/a | n/a | n/a | DOCUMENTADO que a criação aceita só PUBLISHED; ausência de campo de agendamento = INFERIDO (não li o schema completo) | posts-api (tabela "Update Posts") |
| LinkedIn | Pessoal | Ler posts próprios | `GET /rest/posts?author=urn:li:person:..` | `r_member_social` | **Fechada**: "We're not accepting access requests" | n/a | n/a | DOCUMENTADO | .../community-management/community-management-overview (FAQ 6); posts-api (nota Find Posts by Authors) |
| LinkedIn | Pessoal | Ler comentários/reações dos próprios posts | Social Metadata / Comments API | Depende de `r_member_social` (fechada) | Fechada | n/a | n/a | INFERIDO (não li a página de Comments API; a restrição vem de r_member_social) | idem |
| LinkedIn | Pessoal | Escrever comentário/reação em post | Comments API / Reactions API | `w_member_social` | Nenhuma | Provavelmente dentro dos 150 req/dia (INFERIDO) | idem | DOCUMENTADO (escopo: "Post, comment and like"); limite compartilhado INFERIDO | getting-access ; posts-api |
| LinkedIn | Pessoal | Métricas dos próprios posts | `memberCreatorPostAnalytics` (impressões, alcance, reações, comentários, saves, sends, cliques, seguidores ganhos) | `r_member_postAnalytics` | Produto vetado (Community Management API, tier Development → Standard). Exige LinkedIn Page, app e formulário. Se uma pessoa física sem empresa é aceita: **DESCONHECIDO** | Dev tier: 500 req/app e 100/membro (valor da FAQ, unidade de tempo não confirmada) | Dev tier é o ambiente de teste | DOCUMENTADO existência e escopo; elegibilidade pessoal DESCONHECIDA | .../community-management/members/post-statistics ; community-management-overview ; .../marketing/quick-start |
| LinkedIn | Pessoal | Token | OAuth 2.0 3-legged | n/a | n/a | Access token 60 dias. **Refresh programático só para parceiros limitados**; demais refazem autorização (sem tela de consentimento se sessão LinkedIn ativa e token ainda válido) | n/a | DOCUMENTADO | .../shared/authentication/authorization-code-flow |
| X | Pessoal | Publicar texto | `POST /2/tweets` | `tweet.write` (+ `tweet.read`, `users.read`) | Sem revisão de app mencionada; exige conta de desenvolvedor e créditos | Pay-per-use: US$0,015 por post; US$0,200 se o post contém URL. Limite: 100 req/15 min por usuário, 10.000/24h por app (a página não separa limites do plano pay-per-use) | Sem sandbox encontrado (DESCONHECIDO); créditos compram uso real | DOCUMENTADO (preço, limites, endpoint); escopo `tweet.write` DOCUMENTADO na página de scopes | docs.x.com/x-api/getting-started/pricing ; .../fundamentals/rate-limits ; .../x-api/posts/manage-tweets/introduction ; docs.x.com/resources/fundamentals/authentication/oauth-2-0/authorization-code |
| X | Pessoal | Publicar imagem | Upload em `/2/media/upload/{initialize,append,finalize}` + `media.media_ids` no post (até 4 fotos) | `media.write` + `tweet.write` | idem | Custo do upload: **DESCONHECIDO** (não localizado) | idem | DOCUMENTADO fluxo e escopo; custo DESCONHECIDO | manage-tweets/introduction ; authorization-code |
| X | Pessoal | Agendamento nativo | Nenhum: doc de Create Post não tem campo de agendamento | n/a | n/a | n/a | n/a | DOCUMENTADO (ausência na página lida). Agendamento do app web X não é API | manage-tweets/introduction |
| X | Pessoal | Ler posts/respostas próprios e métricas | Reads da API v2 | `tweet.read`, `users.read` | Sem revisão mencionada | "Owned reads" (dados próprios) US$0,001 por recurso; post lido US$0,005; teto 3 mi de leituras/mês no pay-per-use | idem | DOCUMENTADO preço; **quais métricas (impressões etc.) o plano entrega: DESCONHECIDO** | pricing |
| X | Pessoal | Responder em threads alheias | `reply.in_reply_to_tweet_id` | `tweet.write` | n/a | Contas self-serve só respondem se o autor original mencionou/citou a conta | n/a | DOCUMENTADO | manage-tweets/introduction |
| X | Pessoal | Token | OAuth 2.0 PKCE | `offline.access` para refresh | n/a | Access token 2 h (DOCUMENTADO). Refresh token só com `offline.access`; expiração/rotação do refresh token: DESCONHECIDO | n/a | DOCUMENTADO parcial | authorization-code ; .../oauth-2-0/user-access-token |
| Threads | Pessoal | Publicar texto | `POST /{user-id}/threads` (`media_type=TEXT`) + `POST /{user-id}/threads_publish` | `threads_basic` + `threads_content_publish` | App Review obrigatório (e app publicado) **para usuários sem papel no app**. Usuário com papel Threads Tester concede permissões sem review. Uso só da própria conta sem review: INFERIDO, a doc não fala direto | 250 posts/24 h por perfil; texto ≤ 500 caracteres. Preço da API: **DESCONHECIDO** (nada cobrado citado) | Papel Threads Tester no App Dashboard (convite aceito em Website permissions) | DOCUMENTADO | developers.facebook.com/docs/threads/posts ; .../docs/threads/get-started |
| Threads | Pessoal | Publicar imagem | `media_type=IMAGE` + `image_url` pública | idem | idem | JPEG/PNG, ≤ 8 MB, razão ≤ 10:1, largura 320-1440 px. URL precisa ser pública. Espera ~30 s antes de publicar | idem | DOCUMENTADO | docs/threads/posts |
| Threads | Pessoal | Agendamento nativo | Nenhum parâmetro documentado | n/a | n/a | n/a | n/a | DOCUMENTADO (ausência na página lida; não li o índice completo) | docs/threads/posts ; documentation/threads/llms.txt |
| Threads | Pessoal | Ler posts próprios | `GET /{user-id}/threads` | `threads_basic` | idem | Limite específico: DESCONHECIDO (só há 1.000 req/24 h para lookup de perfil público) | idem | DOCUMENTADO | docs/threads/threads-media |
| Threads | Pessoal | Ler respostas aos próprios posts | `GET /{media-id}/replies`, `/conversation` | Página não nomeia a permissão; índice menciona `threads_read_replies` (DOCUMENTADO em get-started) | idem | Limite: DESCONHECIDO | idem | DOCUMENTADO endpoints; permissão por inferência entre duas páginas | .../replies-and-conversations.md ; docs/threads/get-started |
| Threads | Pessoal | Métricas | `/{media-id}/insights`, `/{user-id}/threads_insights` (views, likes, replies, reposts, quotes, clicks, followers_count; demografia exige ≥ 100 seguidores) | `threads_manage_insights` | idem | Histórico a partir de 2024-04-13; `views` e `shares` marcados "in development" | idem | DOCUMENTADO | documentation/threads/insights.md |
| Threads | Pessoal | Token | OAuth + troca por token longo | n/a | n/a | Curto: 1 h. Longo: 60 dias, renovável por `GET /refresh_access_token` (token com ≥ 24 h e não expirado). Expirado não renova. Perfil privado: grant de 90 dias não estendível | n/a | DOCUMENTADO | documentation/threads/get-started/long-lived-tokens.md ; docs/threads/get-started |

## 2. Comparação com o caminho atual (Publora)

Fontes: `lib/publora_client.py` (OBSERVADO: base `https://api.publora.com/api/v1`, endpoints create-post, get/delete-post, platform-connections, platform-limits, linkedin-comments, linkedin-reactions, linkedin-reshare; docstring diz verificado contra API real em 2026-09-15), `plans/linkedin-plan.md` (DECLARADO: Starter, 15 posts/mês, 3 agendados, horizonte 7 dias), docs Publora lidas hoje.

| Item | Publora | Fonte / status |
|---|---|---|
| Plano Starter (gratuito) | 15 posts/mês, 3 posts pendentes, **horizonte de 7 dias**, 3 contas | DOCUMENTADO (docs.publora.com/guides/rate-limits) e consistente com o repo |
| Plano Pro | US$5,99/conta/mês (contas 1-5), posts "5.000 fair use", agendados ilimitados, horizonte ilimitado | DOCUMENTADO (docs.publora.com). Preço de página, reconferir antes de contratar |
| X no Starter | A página de preços diz "todas exceto X"; a de limites diz "todas as 10 plataformas". **Contradição interna** | DOCUMENTADO, conflitante: confirmar antes de depender |
| Leitura de comentários | Doc de LinkedIn Comments cobre criar/responder/apagar; **não documenta listar/ler** | DOCUMENTADO (ausência). O repo usa Apify para ler |
| Métricas | Existe endpoint "LinkedIn Statistics" e há ferramentas `post_stats`/`profile_stats` no conector MCP | Existência: OBSERVADO (nomes das ferramentas). Cobertura/limites: DESCONHECIDO (não chamei) |
| Token de rede | Publora guarda a conexão; `/platform-connections` expõe `tokenStatus`. Expiração/renovação do lado Publora: não descrito | DOCUMENTADO parcial |
| Rate limit por requisição | "planejado, não aplicado hoje"; há limite de 60 URLs de mídia por hora | DOCUMENTADO |

### O que o caminho direto ganharia
1. **Fim do teto de 7 dias e dos 3 agendados** do Starter, mas só se você construir o agendador (nenhuma das três APIs agenda; ver §3). O ganho real é *poder* agendar mais longe com seu próprio job, não um recurso da rede.
2. **Sem cota de 15 posts/mês** e sem dependência de preço de terceiro. Custo marginal: LinkedIn e Threads sem preço citado, X US$0,015/post.
3. **Métricas de Threads** (`threads_manage_insights`) e leitura de respostas, hoje fora do que o repo cobre.
4. **Menos um ponto único de falha** e menos uma parte com acesso a seus tokens.

### O que o caminho direto perderia
1. **Três integrações de OAuth para manter** (apps, redirect URIs, refresh): LinkedIn 60 dias sem refresh programático para app comum; X 2 h com refresh; Threads 60 dias com refresh ativo. Tokens expirados = publicação silenciosamente quebrada.
2. **App Review do Threads** se você quiser que qualquer pessoa além de você use. Para uso próprio, o papel Tester provavelmente basta (INFERIDO).
3. **Agendamento, fila, retry e idempotência** que o Publora entrega e você teria que escrever.
4. **Ambiente único** já validado no repo (testes, `lib.publish`).
5. Em LinkedIn: o mesmo bloqueio existe nos dois caminhos para leitura de comentários (`r_member_social` fechada). O caminho direto **não** resolve isso.

### Contra-argumentos e premissas sem evidência
- "Ir direto elimina o limite" só vale para posts. Para o fluxo atual do repo (comentar em post alheio, responder, reshare), o direto depende de `w_member_social`, que é aberta, mas o limite de 150 req/dia por membro vem de uma página de 2021 (atualizada em 2023); pode estar desatualizado. DESCONHECIDO se a Posts API atual usa o mesmo teto.
- Para publicar 1 a 2 posts por dia em LinkedIn, o Starter com 3 pendentes e 7 dias já cobre, desde que o planejamento seja semanal. A migração só se paga se o gargalo for X (caro/sem Starter), horizonte > 7 dias ou métricas de Threads.
- Híbrido é uma alternativa real: Publora para LinkedIn, API direta apenas onde o Publora limita (X, métricas Threads). Não testei.

## 3. O que NÃO é possível via API oficial (pessoal)

| Item | Rede | Status |
|---|---|---|
| Ler posts, comentários e reações do próprio perfil via Posts/Comments API | LinkedIn | `r_member_social` **fechada**, sem novos pedidos (DOCUMENTADO). Contornar via scraping/engenharia reversa está fora de escopo e proibido neste trabalho |
| Agendar post nativamente | LinkedIn, X, Threads | Nenhum campo de agendamento encontrado nas páginas lidas (ausência documentada; INFERIDO que não existe). Agendamento tem que ser do seu lado ou de um terceiro |
| Refresh de token programático sem ser parceiro | LinkedIn | DOCUMENTADO ("limited set of partners") |
| Publicar sem créditos pagos | X | Doc de preços não menciona tier gratuito (DOCUMENTADO ausência) |
| Responder livremente a qualquer post | X | Self-serve só responde se foi mencionado/citado (DOCUMENTADO) |
| Métricas pessoais do LinkedIn sem aprovação | LinkedIn | Exige produto vetado Community Management; elegibilidade para pessoa física DESCONHECIDA |
| Postar de conta privada com grant renovável | Threads | Grant de 90 dias de perfil privado não é estendível (DOCUMENTADO) |
| Dados de seguidores demográficos | Threads | Exige ≥ 100 seguidores (DOCUMENTADO) |

## 4. Lacunas (DESCONHECIDO) para validar

1. Elegibilidade de uma pessoa física sem LinkedIn Page para Community Management (métricas). Teste: abrir o formulário de Development tier e ler o critério.
2. Se o app Threads em modo desenvolvimento publica na própria conta sem App Review. Teste: criar app, aceitar convite Tester, publicar um post de teste (conta própria).
3. Custo do upload de mídia no X e quais métricas o pay-per-use devolve.
4. Preço/limite de uso da API do Threads e do LinkedIn (nenhum citado).
5. Limite atual de req/dia do LinkedIn na Posts API.
6. Contradição do Publora sobre X no Starter.
7. Se existe agendamento na Posts API do LinkedIn além de `lifecycleState`: ler o schema completo.

## 5. Limitações deste documento

- Leitura via fetch com sumarização; páginas Meta/X de 2026 não foram lidas em texto integral.
- Nenhum app foi registrado, nenhuma chamada foi feita, nenhum token usado: sem OBSERVADO em API real.
- Páginas do X e do Threads podem exigir a versão mais recente; a LinkedIn usa versionamento mensal (`Linkedin-Version`, 202511 será descontinuado em 2026-11-16, DOCUMENTADO), o que afeta qualquer integração direta.

---

## 6. Comentários e respostas (adendo T3b, consulta 2026-10-25)

Requisito: automatizar posts, **comentários em posts de terceiros** e **respostas a comentários nos próprios posts**, sempre com aprovação humana antes de enviar, **sem assinar serviço pago**. Mesmos rótulos da seção 1. Citações de termos vieram de fetch com resumo por modelo pequeno: o modelo recusou reproduzir seções longas, então só trechos curtos estão entre aspas. Reconferir o texto no original antes de qualquer decisão. Nada aqui é aconselhamento jurídico.

### 6.1 Resumo executivo (parecer)

1. **LinkedIn:** escrever comentário e resposta aninhada é tecnicamente documentado. O que **não está resolvido** é o escopo: a página do Comments API pede `w_member_social_feed`, que só aparece listado dentro do produto vetado Community Management API. A página do Share on LinkedIn diz que `w_member_social` (aberto) cobre "post, comment and like". As duas afirmações não se reconciliam na doc. Resolve-se só com um teste real.
2. **Ler novos comentários nos próprios posts: nenhum caminho oficial grátis no LinkedIn.** Exige `r_member_social_feed`/`r_member_social` (restritas ou fechadas). Webhook exige use case aprovado, e no tier Development as notificações push ficam desabilitadas.
3. **Threads** é o mais aberto: responder a respostas nos próprios posts e ler respostas é viável; comentar em post de terceiros exige permissões extras (`threads_keyword_search` ou `threads_manage_mentions`), que não me constam como abertas.
4. **X** tem tudo tecnicamente, mas **não é gratuito** (pay-per-use com créditos) e a política proíbe resposta automatizada sem consentimento explícito do destinatário. Para comentar em posts de terceiros isso é o ponto mais perigoso das três redes.
5. **Termos de uso:** o risco principal está no LinkedIn: a cláusula 3.1(26) dos API Terms proíbe "automate posting" sem qualificador, e a 8.2(13) do User Agreement proíbe bots que comentem. Aprovação humana provavelmente reduz o risco, mas **nenhum dos textos lidos diz que aprovação humana é exceção**. Isso é INFERIDO, não documentado.
6. **Conflito com "sem pagar":** X exige créditos. LinkedIn e Threads não têm preço citado, mas o LinkedIn pode exigir aprovação de produto vetado. O caminho de custo zero que sobra é: **geração de rascunho local + colagem humana do comentário/URL + publicação manual ou via Publora Starter**.

### 6.2 Matriz de comentários e respostas

| Rede | Ação | Endpoint | Escopo | Aprovação | Custo/limite | Status | Evidência |
|---|---|---|---|---|---|---|---|
| LinkedIn | Comentar em post (inclusive de terceiro) | `POST /rest/socialActions/{shareUrn\|ugcPostUrn}/comments`, corpo com `actor` (person URN), `object`, `message` | Comments API lista `w_member_social_feed` ("Post, comment, and react on posts on behalf of an authenticated member"). Tabela de permissões lista `w_member_social_feed` só sob **Community Management API** | Ver 6.3. Doc não restringe a posts próprios | 429 "creation rate limit exceeded for member" em janela de 1 min; limite diário compartilhado: DESCONHECIDO. Imagem em comentário: suportada com `entity.image` | Endpoint e corpo DOCUMENTADOS; se o post de terceiro é aceito: INFERIDO (nenhuma restrição citada; Publora diz "só posts visíveis à sua conta") | learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/comments-api ; docs.publora.com/guides/linkedin-comments |
| LinkedIn | Responder comentário (aninhado) | Mesmo endpoint com `parentComment` = URN composto `urn:li:comment:(activityUrn,commentId)`; alvo da URL pode ser o `commentUrn` | idem | idem | idem | DOCUMENTADO | comments-api ("Create a Comment on a Comment") |
| LinkedIn | Ler comentários do próprio post | `GET /rest/socialActions/{urn}/comments` | `r_member_social_feed`: "**Restricted**... granted to select developers only" | Restrita; `r_member_social` está **fechada** a novos pedidos | n/a | DOCUMENTADO | comments-api (tabela de permissões); community-management-overview (FAQ 6) |
| LinkedIn | Contagem de comentários (sem texto) | `GET /rest/socialMetadata/{urn}` → `commentSummary.count/topLevelCount` | Mesma tabela de permissões (leitura restrita) | idem | n/a | DOCUMENTADO que o endpoint existe; se a contagem vale com escopo aberto: DESCONHECIDO | social-metadata-api |
| LinkedIn | Webhook de novo comentário | Webhooks do app | n/a | "only available for applications with an approved use case for webhooks". No Community Management **Development tier**: "Webhook for Social Actions: Push notifications disabled" | URL HTTPS pública; revalidação a cada 2 h; ngrok **não** suportado | DOCUMENTADO | learn.microsoft.com/en-us/linkedin/shared/api-guide/webhook-validation ; .../marketing/increasing-access |
| Threads | Responder a resposta nos próprios posts | `POST /me/threads` com `reply_to_id` + `POST /{user-id}/threads_publish` (aguardar ~30 s) | `threads_basic`, `threads_content_publish`, `threads_manage_replies` | Mesma regra de App Review da seção 1 (Tester dispensa) | 1.000 respostas/24 h; 250 posts/24 h | DOCUMENTADO | developers.facebook.com/documentation/threads/retrieve-and-manage-replies/create-replies.md ; .../threads/overview.md |
| Threads | Comentar em post de **terceiro** | Mesmo endpoint, `reply_to_id` do post alheio | Além dos três acima, o app precisa de `threads_keyword_search` **ou** `threads_manage_mentions` | Se essas duas são abertas ou exigem App Review: DESCONHECIDO | idem | Condição DOCUMENTADA; acesso a elas DESCONHECIDO | create-replies.md |
| Threads | Ler respostas dos próprios posts | `GET /{media-id}/replies`, `/conversation` | `threads_read_replies` | idem | sem limite citado | DOCUMENTADO | .../replies-and-conversations.md ; webhooks.md |
| Threads | Detectar nova resposta sem polling | Webhook `replies` | `threads_basic` + `threads_read_replies` | **Advanced Access (App Review)**, negócio verificado, endpoint HTTPS que a Meta alcance; perfil não pode ser privado. Em modo dev com conta própria: a doc não diz | n/a | DOCUMENTADO exigências; viabilidade em modo dev DESCONHECIDA. **Polling de `/replies` é a alternativa sem aprovação** (INFERIDO) | .../threads/webhooks.md |
| X | Comentar/responder | `POST /2/tweets` com `reply.in_reply_to_tweet_id` | `tweet.write` | Self-serve só responde se o autor original mencionou/citou a conta (DOCUMENTADO). Isso **bloqueia comentário livre em post de terceiro** | US$0,015 por post | DOCUMENTADO | docs.x.com/x-api/posts/manage-tweets/introduction ; .../pricing |
| X | Responder a respostas nos próprios posts | Mesmo endpoint | `tweet.write` | Presumivelmente permitido pois o autor original é você (INFERIDO; a regra de menção/citação cobre respostas a terceiros) | idem | INFERIDO | idem |
| X | Ler respostas aos próprios posts | `GET /2/users/{id}/mentions` (até 800 mais recentes, inclui respostas e citações) | `tweet.read`, `users.read` | Sem revisão citada | "Owned read" US$0,001 por recurso, **se** `{id}` é o usuário autenticado e dono do app | DOCUMENTADO. Cobre respostas que mencionam você; respostas sem @ via `conversation_id`: DESCONHECIDO (página não cobre) | docs.x.com/x-api/posts/timelines/introduction ; .../pricing |
| X | Webhook de novos posts/eventos | X Activity API | n/a | Conta de desenvolvedor aprovada | `post.create` US$0,005 por evento entregue | DOCUMENTADO preço; se cobre respostas: DESCONHECIDO | docs.x.com/x-api/webhooks/introduction ; pricing |

### 6.3 O ponto crítico do LinkedIn: qual escopo realmente libera comentar?

| Fonte | O que diz | Status |
|---|---|---|
| Share on LinkedIn (self-serve) | `w_member_social` = "Required to create a LinkedIn post on behalf of the authenticated member"; produto aberto | DOCUMENTADO (página de 2021, atualizada 2023-12) |
| increasing-access (atualizada 2026-10-19) | `w_member_social` = "Post, comment, and like posts on your behalf"; `w_member_social_feed` = "Create, modify, and delete comments and reactions on posts on your behalf" | DOCUMENTADO |
| Mesma página: produtos que concedem cada escopo | `w_member_social_feed` só aparece em **Community Management API**; `w_member_social` aparece em Advertising API e Community Management API. O produto self-serve Share on LinkedIn **não consta** nessa tabela | DOCUMENTADO |
| Comments API | Lista só `w_member_social_feed` (não `w_member_social`) como permissão de escrita de membro | DOCUMENTADO |
| Community Management | Produto vetado; Development tier: 500 chamadas/app e 100/membro por 24 h, **12 meses** para concluir testes; exige LinkedIn Page, app e formulário | DOCUMENTADO |
| Publora | Oferece criar/deletar comentário em perfil pessoal via API | DOCUMENTADO. Logo o app do Publora tem alguma permissão que permite isso (INFERIDO); qual, DESCONHECIDO |

**Parecer:** a leitura mais provável é que **comentar via API direta num perfil pessoal exige `w_member_social_feed`, portanto Community Management (vetado)**, e que `w_member_social` sozinho cobre apenas publicar. Isso é INFERIDO, não confirmado. A doc não deixa claro. Teste barato: registrar app com Share on LinkedIn, pedir `w_member_social`, tentar um comentário em post próprio e ler o 403. Elegibilidade de pessoa física sem LinkedIn Page para Community Management continua DESCONHECIDA e, pelo quick-start ("Create a LinkedIn Page"), provavelmente não atendida (INFERIDO).

### 6.4 Termos de uso (cláusulas)

| Rede | Documento e cláusula | Trecho (curto) | Leitura para este projeto | Status |
|---|---|---|---|---|
| LinkedIn | **API Terms of Use §3.1(26)** | "Use the Content or the APIs to automate posting on the LinkedIn Services." Sem qualificador. | Lido literalmente, proíbe até postagem agendada por API. Nada no texto cria exceção para aprovação humana. A existência do produto Share on LinkedIn e de terceiros que publicam sugere tolerância a publicação disparada pelo usuário, mas isso **não está escrito**. Para comentários é a mesma lacuna | DOCUMENTADO (texto); interpretação INFERIDA |
| LinkedIn | API Terms §3.1(12) | "Use any API in any manner that, as determined by LinkedIn in its reasonable discretion, constitutes abusive usage" | Critério discricionário da LinkedIn | DOCUMENTADO |
| LinkedIn | API Terms §3.1(10) | Veda usar Content para "generate mass messages, promotions or offers" (parafraseado) | Comentários em massa para promoção estão fora | DOCUMENTADO (paráfrase) |
| LinkedIn | API Terms §3.1(24), §4.1, §4.3 | Proíbem scrapear fora das APIs; capturar/armazenar Content além do permitido; atualizar dados de perfil em agenda automática (parafraseado) | Contra-indica guardar comentários lidos e usar Apify/scraping como "leitura" | DOCUMENTADO (paráfrase) |
| LinkedIn | API Terms §3.1(4) | Pré-preencher conteúdo exige aviso claro e permitir edição pelo usuário (parafraseado) | Favorece o desenho "rascunho + edição humana + envio" | DOCUMENTADO (paráfrase) |
| LinkedIn | **User Agreement §8.2(13)** | "Use bots or other unauthorized automated methods to access the Services, add or download contacts, send or redirect messages, create, comment on, like, share, or re-share posts, or otherwise drive inauthentic engagement" | Veda bots que comentem. "Unauthorized" é o qualificador relevante; o que é autorizado: a API oficial. Comentário aprovado por humano e enviado por API autorizada é defensável, não garantido | DOCUMENTADO (texto); interpretação INFERIDA |
| LinkedIn | User Agreement §8.2(16) | "spam, denial of service attack, viruses, manipulating algorithms" | Não usar para "engajamento fabricado" | DOCUMENTADO |
| X | **Developer Policy, "Spam, bots, and automation"** | "Always get explicit consent before sending people automated replies or Direct Messages." / "Never perform bulk, aggressive, or spammy actions" / write actions "must follow the Automation Rules" | Resposta a terceiro automatizada sem opt-in viola. Responder a quem comentou **no seu post** é mais defensável, mas "explicit consent" do destinatário não é satisfeito por padrão (INFERIDO) | DOCUMENTADO (texto) |
| X | Developer Policy, "Consent & permissions" | Exige "express and informed consent" para "Posting content to X"; "Show exactly what will be published" | O fluxo de aprovação humana **cumpre** a exigência de mostrar o que será publicado | DOCUMENTADO |
| X | Automation Rules (help.x.com) | **Não consegui ler** (HTTP 403 em duas URLs) | Regras citadas pela Developer Policy mas não verificadas por mim | DESCONHECIDO |
| Meta/Threads | Platform Terms (versão em português lida) | Sem cláusula de spam nem de rate limit; §11.e permite a Meta "impor limites" e restringir APIs; §7.e permite monitoramento automatizado e suspensão; §7.e.iii permite cortar permissão sem uso por 28 dias | Sem proibição explícita de resposta assistida; risco é discricionário | DOCUMENTADO (paráfrase do resumo) |
| Threads | Threads API Terms | URL consultada deu 404; página overview não tem links de termos nem cláusula de spam | Termos específicos do Threads não verificados | DESCONHECIDO |
| Threads | Overview da API | Apps "may show those posts only to the person who created it" (uso para postar em nome do próprio usuário); apps devem impor seus limites "especially if it allows app users to schedule posts" | Reforça modelo "pessoa publica na própria conta". Não menciona agendamento nativo, o que reforça que agendar é responsabilidade do app | DOCUMENTADO |

### 6.5 Desenho mínimo compatível com "sem pagar" e "sempre com aprovação"

| Etapa | LinkedIn | Threads | X |
|---|---|---|---|
| Detectar novo comentário | Sem API grátis. Humano cola URL do post ou texto do comentário (o repo já tem fallback de colagem) | Polling de `/replies` com `threads_read_replies` (grátis até onde a doc mostra) | `mentions` a US$0,001/recurso (**pago**) |
| Rascunho | Local (skills do repo) | Local | Local |
| Aprovação | Humano antes de qualquer envio (obrigatório pelo requisito e favorável às cláusulas) | idem | idem |
| Envio | Publora Starter (grátis; 15 posts/mês; comentário conta ou não no limite: DESCONHECIDO) **ou** envio manual no app | API direta com `threads_manage_replies` | Pago; fora do requisito |

### 6.6 Contra-argumentos e premissas sem evidência

- "Aprovação humana resolve a questão dos termos" é uma hipótese. Nenhuma das cláusulas lidas cria essa exceção. A cláusula X de consentimento do destinatário e a LinkedIn §3.1(26) não mencionam aprovação do operador. Só consultar o suporte de cada rede dá resposta firme (LinkedIn Developer Support abre ticket por escrito).
- "Publora já faz comentário no LinkedIn, então basta" vale enquanto o Starter cobrir o volume e enquanto o plano gratuito contar comentário no limite de 15/mês de forma que caiba. DESCONHECIDO: se comentários consomem a cota de posts.
- "Webhook elimina polling" no LinkedIn é falso para este caso: exige use case aprovado e fica desabilitado no Development tier. No Threads exige Advanced Access. Para uso pessoal, polling é o realista, quando existe leitura aberta (só Threads).
- Risco de conta: LinkedIn avalia "abusive usage" com critério próprio (§3.1(12)); automatizar comentários em volume em post de terceiro é o padrão mais exposto. Baixo volume, texto escrito/editado por humano e sem promoção reduz o risco, mas não o elimina (INFERIDO).

### 6.7 Lacunas (DESCONHECIDO) adicionais

1. Se `w_member_social` (Share on LinkedIn) basta para `POST /rest/socialActions/.../comments`. Teste: um comentário num post próprio.
2. Elegibilidade de pessoa física a Community Management / `w_member_social_feed`.
3. Se `threads_keyword_search` e `threads_manage_mentions` exigem App Review.
4. Se o webhook de Threads funciona em modo dev com conta própria.
5. Texto das X Automation Rules (403) e dos Threads API Terms (404).
6. Se comentários via Publora contam na cota de 15 posts/mês do Starter.
7. Resposta de X sem @ ao autor via `conversation_id`: não coberto pelas páginas lidas.

### 6.8 Fontes consultadas em 2026-10-25

- learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/comments-api (atualizada 2026-04)
- .../shares/social-metadata-api ; .../marketing/increasing-access (atualizada 2026-10-19)
- learn.microsoft.com/en-us/linkedin/shared/api-guide/webhook-validation
- linkedin.com/legal/l/api-terms-of-use ; linkedin.com/legal/user-agreement
- developers.facebook.com/documentation/threads/{retrieve-and-manage-replies/create-replies.md, retrieve-and-manage-replies/replies-and-conversations.md, webhooks.md, overview.md}
- developers.facebook.com/terms/
- docs.x.com/x-api/{getting-started/pricing, posts/manage-tweets/introduction, posts/timelines/introduction, webhooks/introduction} ; docs.x.com/developer-terms/policy
- docs.publora.com/guides/linkedin-comments
- Falhas de acesso: help.x.com (403 duas URLs), developer.x.com agreement-and-policy (402), threads.com/legal/threads-api-terms (404)
