# Gap analysis: linkedin-skills vs. fluxo-alvo

Data da análise: 2026-10-25. Escopo: leitura de `lib/`, `skills/`, `references/`, `plans/`, `tests/`, `scripts/`, `README.md`. Nenhum código, manifest ou segredo foi tocado/lido (`.env`, `testing/` não abertos).

Legenda de evidência: **OBSERVADO** (li no repo), **DOCUMENTADO** (doc oficial pública, URL + data), **DECLARADO** (o repo/README afirma, não verifiquei), **INFERIDO** (dedução minha), **DESCONHECIDO**.

Fluxo-alvo: ideia → contexto/fontes → abordagem → rascunho → versão por rede (LinkedIn/X/Threads) → revisão → aprovação da versão exata (hash) → agendamento → publicação → métricas → aprendizado revisável.

## 1. Tabela por etapa

| # | Etapa | Status | Evidência | Classe |
|---|---|---|---|---|
| 1 | Captura de ideia | **Parcial** | `linkedin-interviewer` extrai material bruto para `references/story-bank.md` (arquivo pessoal, gitignored: `.gitignore` linhas finais; `scripts/check_no_secrets.py:50`). `post-writer/SKILL.md:80` "Gather inputs" pergunta tópico na hora. Não há inbox/lista de ideias persistente nem captura fora de sessão. | OBSERVADO |
| 2 | Contexto/fontes | **Coberto (leitura LinkedIn) / parcial (geral)** | Camada Apify: `lib/apify_client.py` + `lib.fetch_post` (`backend_selector.py:375`). `post-writer/SKILL.md:74` carrega voice-profile e story-bank. Fontes fora do LinkedIn (web, docs) dependem do agente; `repurposer` aceita tweet/blog colado. `scripts/schedule_post.py:54` registra `--source` apenas como log. | OBSERVADO |
| 3 | Abordagem (ângulo/formato) | **Coberto** | 20 fórmulas em `references/hook-formulas.md`; `content-planner/SKILL.md` (pilar, formato, CTA, janela). | OBSERVADO |
| 4 | Rascunho | **Coberto** | `post-writer/SKILL.md:80-92` (inclui humanizer e ilustração opcional via `lib.illustrate`/`quote_card`). | OBSERVADO |
| 5a | Versão por rede: LinkedIn | **Coberto** | Todo o código assume LinkedIn: `publish` usa `LINKEDIN_PLATFORM_ID` (`backend_selector.py:287`), limite 3000 em `schedule_post.py:68`. | OBSERVADO |
| 5b | Versão por rede: X | **Ausente** | Nenhuma ocorrência em `lib/`, `scripts/`, skills de geração de rascunho. X só aparece como *fonte* no `repurposer` (X→LinkedIn, `SKILL.md:25-38`) e como link para bundle irmão `x-skills` (`README.md:19,415`, DECLARADO, não verificado). Fixture mostra `platformSettings.twitter` na resposta da Publora (`tests/fixtures/publora_get_post.json:22`), ou seja, o provedor suporta; o repo não usa. | OBSERVADO |
| 5c | Versão por rede: Threads | **Ausente** | Idem; só fixture `platformSettings.threads` (`publora_get_post.json:18`) e menção no README (`README.md:200,53`, DECLARADO "optionally X, Threads"). Zero código, zero regras de formato (limite, thread, replyControl). | OBSERVADO |
| 6 | Revisão | **Coberto** | `linkedin-humanizer --mode audit` e passada de humanizer dentro de `post-writer`; evals com graders objetivos (`evals/run_evals.py`). Revisão é só-LinkedIn. | OBSERVADO |
| 7 | Aprovação da versão exata (hash) | **Parcial, só por convenção** | `lib/approval.py:1-7` diz explicitamente "thin conventions layer, not runtime enforcement". `publish()` não recebe nem valida nada que prove que `draft_text` é o texto aprovado. Nenhum `hashlib` no fluxo de publicação (o único sha256 do repo é `humanizer/scripts/test_detectors.py:248`, irrelevante). README:41 "Only after explicit approval" é DECLARADO, aplicado por prompt, não por código. | OBSERVADO |
| 8 | Agendamento | **Coberto (LinkedIn via Publora)** | `publish(kind="post", scheduled_time=...)` → `PubloraClient.create_post` (`publora_client.py:175-208`, rascunho se sem `scheduledTime`). `scripts/schedule_post.py:31` regra 10:00. `unpublish` (`backend_selector.py:162`) cancela agendado, mas não publicado (`:166-175`). Update de post agendado (`PUT /update-post`) está descrito no CLAUDE.md mas **não há método no cliente** (grep: só create/get/delete/comment/reaction/reshare). | OBSERVADO |
| 9 | Publicação | **Coberto (LinkedIn)** | Dispatch em `backend_selector.py:243-373`. `reshare/comment/reply` também. Sem confirmação pós-publicação (ler `get_post` e comparar texto/status) no fluxo das skills. | OBSERVADO |
| 10 | Métricas | **Ausente para posts próprios; parcial para engajamento** | Nenhum método de stats em `publora_client.py`. `engager-analytics` e `thread-monitor` leem engajadores/comentários via Apify (`apify_client.py:26,271`) — são análise de audiência, não desempenho do post publicado. Taxonomia só como texto: `references/engagement-metrics-taxonomy.md` (nenhuma skill a cita; grep em `skills/` e `SKILL.md` vazio). Existem tools de stats na Publora (`post_stats`, `profile_stats` expostas no MCP desta sessão = OBSERVADO como schema de ferramenta, não testado); o repo não as usa. | OBSERVADO |
| 11 | Aprendizado revisável | **Parcial, frágil** | Único estado estruturado: `testing/linkedin-routine-log.jsonl` (append-only, `schedule_post.py:12,26,105-115`), **gitignored** e usado só para rotação de ângulo. `voice-profile.md`/`story-bank.md` são arquivos pessoais editados à mão (`filled: yes`). Nada liga resultado (métrica) → decisão (ângulo/fórmula) → revisão humana. `plans/` é gitignored (`.gitignore`), logo plano e histórico não são versionados nem testáveis. | OBSERVADO |

### Pontos transversais pedidos

**Suporte real a X e Threads hoje: nenhum no código.** O README promete "optionally X, Threads" via Publora (DECLARADO). O que existe é (a) a API do provedor aceitar `platforms=[...]` com IDs de outras redes — `create_post` só normaliza strings (`publora_client.py:192-196`); (b) um teste que usa um ID `instagram-123` só para provar que não se confunde com LinkedIn (`tests/test_client_behaviour.py:247`). Não há teste, skill, limite de caracteres ou formatação de thread para X/Threads. **Mas** `publish(kind="post", platforms=[...])` repassaria um ID de X sem erro de código: o suporte seria "acidental e não validado", o que é pior que ausente se o texto de LinkedIn (até 3000 chars) for enviado cru a X.

**Armazenamento de estado/fila/histórico: inexistente como camada.** Único artefato: o `.jsonl` acima, em diretório gitignored, escrito só por um script CLI e não pelas skills (`post-writer` chama `lib.publish` direto, `SKILL.md:94`, sem registrar `postGroupId`). Fila = a própria Publora (estado remoto). Consequência: `unpublish` exige que o agente ainda tenha o `postGroupId` em contexto; depois de uma sessão encerrada, ele se perde (INFERIDO a partir de `SKILL.md:94` + ausência de persistência).

**Dispatch de `lib.publish`** (`backend_selector.py:243`): `active_backend()` (`:86`) decide pelo ambiente — `publora` se `PUBLORA_API_KEY`+`LINKEDIN_PLATFORM_ID`, senão `diy` se `LINKEDIN_SKILLS_CUSTOM_POSTER`, senão `manual`. Três ramos if/else repetidos em `publish` (`:274/282/346`) e `unpublish` (`:200/212/220`). Dentro do ramo publora, `kind` ramifica (comment/reply/post/reshare). O ramo `diy` é um contrato de subprocesso: argv `[kind, target_url]` + JSON em stdin (`:346-369`).

### Menor ponto para um adaptador de publicação

O ramo `diy` já é, na prática, uma interface de adaptador (comando externo, JSON de entrada, dict de saída), e o ramo `publora` do `kind == "post"` (`:321-330`) é um bloco de ~8 linhas. Proposta mínima, **aditiva**:

1. Novo módulo `lib/adapters.py` (não novo cliente HTTP): `Protocol PublishAdapter { network; max_chars; format(draft)->str; publish(text, *, scheduled_time, media_urls)->dict; get(id)->dict }`, com um `LinkedInPubloraAdapter` que apenas **delega** ao bloco existente e dois adaptadores X/Threads sobre o mesmo `PubloraClient.create_post` (só muda `platforms`, validação de tamanho, `platformSettings`).
2. `backend_selector.publish` ganha, no ramo `kind == "post"`, um parâmetro opcional `network="linkedin"`; default preserva comportamento e assinatura. Nenhum chamador existente muda.
3. `_LAZY_CLIENTS`/`__all__` em `lib/__init__.py` só crescem se algo novo for exportado (hoje 80 linhas; `lib/__init__.py:56-80`).

**Invariantes do CLAUDE.md a respeitar:** (a) 12 skills — nada disso cria skill; (b) camadas Apify/Publora/Pixfaro — o adaptador fica na camada Write, usando `PubloraClient`; (c) `tests/test_skill_contracts.py:61-90` valida que toda chamada `lib.xxx(kw=...)` documentada nas skills existe e aceita o kwarg: qualquer kwarg novo (`network=`) só pode ser documentado depois de existir no código; (d) `scripts/sync_codex_marketplace.py` copia `lib/`: rodar o sync após editar; (e) sem menção a schedulers concorrentes nos arquivos commitados; (f) `description:` sem travessão e ≤ ~400 chars.

## 2. Lacunas ranqueadas (reais, não reescrita)

1. **Aprovação por hash inexistente** (etapa 7). Menor correção: `approval.py` ganha `fingerprint(text, network)` (sha256) e `render_approval_card` o exibe; `publish(..., approved_hash=...)` recusa se `sha256(draft_text) != approved_hash`. Opcional por default → compatível. É a única lacuna que viola uma garantia que o README já promete.
2. **Sem registro do que foi agendado/publicado** (8, 9, 11). Um ledger append-only (`jsonl`) escrito por `publish`, fora de `testing/` ou em local configurável, com `postGroupId`, hash, rede, horário, status.
3. **X/Threads** (5b/5c): decidir antes de construir (ver riscos).
4. **Métricas do próprio post** (10): método `get_post_stats` no `PubloraClient` — endpoint específico DESCONHECIDO neste repo; precisa ser confirmado na doc oficial antes.
5. **Edição de post agendado**: CLAUDE.md prefere `PUT /update-post` a delete+recreate, mas o cliente não implementa.
6. **Testes de dispatch do `publish("post")`**: `grep publish( tests` só encontra `unpublish`; o caminho de post/diy/manual não tem teste direto (OBSERVADO). Qualquer adaptador deve vir com testes antes.

## 3. Riscos / Contra-argumentos

- **Contra "adicionar X e Threads":** o repo é posicionado como LinkedIn (12 skills LinkedIn, vozes, benchmarks do LinkedIn, `hook-formulas` calibradas no LinkedIn). O README já aponta bundles irmãos `x-skills`/`threads-skills` (DECLARADO). Duplicar essa capacidade aqui pode violar o posicionamento e inflar o escopo. Alternativa: o pipeline multi-rede viver fora do bundle e consumir `lib.publish`.
- **Plano gratuito da Publora e X (DOCUMENTADO, indireto):** consulta a https://docs.publora.com em 2026-10-25, via WebFetch (resumo de modelo, não li a página bruta): 10 plataformas suportadas; Starter gratuito com 3 contas e "15 posts/month account-wide", "All platforms, except X". Se correto, X pode exigir plano pago e a cota de 15 é compartilhada entre redes (um cross-post consome mais). **Verifique a página de preços antes de decidir**; não confirmei valores nem limites de caracteres (DESCONHECIDO).
- **Métricas em X/Threads:** a mesma consulta não listou endpoint de estatísticas para X ou Threads (só LinkedIn, Mastodon, Bluesky). Se for verdade, "métricas por rede" é inviável via Publora para X/Threads (INFERIDO; confirmar).
- **Hash dá menos garantia do que parece:** protege contra o agente alterar o texto entre aprovação e envio, mas não contra o agente mostrar um card e calcular o hash sobre outro texto, nem contra a Publora/rede normalizar o conteúdo depois. É integridade de uma etapa, não prova de aprovação humana. Enforcement real exigiria que a aprovação viesse de fora do agente (premissa não resolvida).
- **Estado local vs. estado remoto:** a Publora já é fila + histórico de status (`get_post`). Um ledger local duplica a fonte de verdade e pode divergir (post editado/deletado no painel). Menor risco: ledger guarda só `postGroupId`+hash e reconcilia via `get_post`.
- **`plans/` e `references/voice-profile.md` gitignored:** é decisão deliberada de privacidade, mas significa que parte do "aprendizado revisável" não terá diff/revisão em git. Quem decide: o usuário.
- **Aviso do pedido de engenharia reversa do LinkedIn** (contexto da sessão, fora deste repo): este documento não propõe nem avalia isso. A trilha de adaptadores usa só a API oficial da Publora e o ramo `diy` (poster do próprio usuário). Contornar limites/paywall de terceiros é fora do escopo autorizado deste papel.
- **Premissa sem evidência:** "o fluxo-alvo precisa de fila local". Não vi requisito/medição mostrando que a fila remota da Publora é insuficiente. Validar primeiro com `get_post` + `list-posts` (CLAUDE.md cita `GET /list-posts`).

## 4. Limitações desta análise

- Não executei testes nem `selftest.py` (a tarefa pedia leitura). A cobertura de testes é afirmada por leitura de nomes de teste.
- Documentação Publora consultada uma vez, por resumo automático; limites de caracteres, `platformSettings` e preços ficam DESCONHECIDOS.
- Não li `.env`, `testing/`, nem o conteúdo pessoal de `references/voice-profile.md`/`story-bank.md` além do necessário para ver o cabeçalho `filled:`.
- Números de linha do `backend_selector.py` referem-se ao estado em 2026-10-25 (há alterações não commitadas no repo: `references/story-bank.md`, `references/voice-profile.md`, `.gitignore`).

## 5. Próxima tarefa recomendada

Implementar, em um único PATCH, (1) `fingerprint` + `approved_hash` opcional em `publish` e (2) testes de dispatch de `publish("post")` para os três backends. Só depois decidir sobre adaptadores X/Threads, após confirmar na doc/preços oficiais da Publora.

## 6. Adendo (T1b, 2026-10-25): plano GRÁTIS da Publora, reconciliado

Fontes consultadas em 2026-10-25 via WebFetch (resumo de modelo sobre a página; não é leitura bruta, então valores devem ser reconferidos antes de qualquer decisão financeira). Nenhuma conta, token ou chamada autenticada foi usada.

**Divergência resolvida: não há contradição, só recortes diferentes do mesmo plano Starter.** Meu relato anterior ("15 posts/mês compartilhados, all platforms except X") e o da Ponte ("7 dias / 3 pendentes") aparecem juntos na mesma doc.

| Item | Starter (grátis) | Classe / fonte |
|---|---|---|
| Preço | Grátis ("Free forever", sem cartão) | DOCUMENTADO https://publora.com/pricing |
| Posts/mês | 15, "account-wide" (compartilhado entre redes/contas) | DOCUMENTADO https://publora.com/pricing e https://docs.publora.com/guides/rate-limits |
| Contas conectadas | 3 | DOCUMENTADO idem |
| Agendamento | até 7 dias à frente; 3 posts agendados pendentes por vez | DOCUMENTADO idem (rate-limits: "3 pending scheduled posts, 7-day horizon") |
| Plataformas | "All platforms, except X" | DOCUMENTADO; **a própria página de rate-limits é inconsistente** (tabela exclui X, nota posterior diz sem restrição) → X no grátis: **incerto** |
| API/MCP | Incluídos | DOCUMENTADO https://publora.com/pricing |
| Comentários (`POST /linkedin-comments`) contam na cota de 15? | **Não declarado** | DESCONHECIDO (guide e rate-limits omitem) https://docs.publora.com/guides/linkedin-comments |
| Reações (`/linkedin-reactions`) contam na cota? | **Não declarado** | DESCONHECIDO https://docs.publora.com/guides/linkedin-reactions |
| Rascunhos contam? | Não declarado | DESCONHECIDO |
| Rate limit por requisição | "planned but not currently enforced" | DOCUMENTADO rate-limits |
| Pro (referência, não será assinado) | a partir de US$ 5,99/conta/mês; posts "ilimitados" (cap justo 5.000/mês) | DOCUMENTADO pricing/rate-limits |

**Limites técnicos de comentário (independem do plano)**: `message` aceita até 10.000 chars, mas o texto enviado ao LinkedIn é limitado a **1.250** após processar menções; imagem opcional 1 arquivo ≤10 MB; só em posts visíveis à conta conectada; `postedId` deve ser `urn:li:share:`/`urn:li:ugcPost:` (activity pode dar 403 com menção). Reação: uma por usuário por post; para trocar, apagar e recriar; URN idem. (DOCUMENTADO, guides acima.)

**Leitura de comentários**: `/linkedin-comments` documenta só POST e DELETE, **não** leitura (DOCUMENTADO). Logo, ler comentários de terceiros continua dependendo da camada Apify (`lib/apify_client.py:181`, pago por uso, conforme README) ou de colagem manual. Isso é o ponto que depende da resposta da Ponte (ver `docs/architecture/approval-queue.md` §9).

**Implicações para o `plans/linkedin-plan.md` (orçamento)**: o plano assume 15 posts/mês e tem um TODO sobre comentários contarem na cota. Esse TODO continua aberto: a doc oficial não responde. Tratar como contando, até que o painel da Publora (ou o suporte) confirme. O limite de **3 pendentes** é mais restritivo que a cota para quem agenda a semana inteira (2 posts/semana cabem; 8 agendados no começo do mês não cabem, o que contradiz a regra "agendar no começo do mês" do plano, INFERIDO). Não verifiquei X nem os limites de caracteres por rede (`/guides/platform-limits`, não lido).

Contra-argumento: o fato de a doc ser silenciosa sobre cota de comentário não significa que não contem. Só um teste real de cota (que exigiria usar a conta do usuário) responde; fora do escopo autorizado aqui.
