# Fila de aprovação local — esboço de desenho

Data: 2026-10-25. Status: **esboço, nenhuma linha de código**. Base: `docs/research/gap-analysis.md` (lacunas 1, 2 e 6). Classes: OBSERVADO (li no repo), INFERIDO, DESCONHECIDO.

## 1. Problema, em uma frase

Hoje a aprovação é convenção de prompt (`lib/approval.py:1-7` "not runtime enforcement"); `lib.publish` (`lib/backend_selector.py:243`) envia qualquer `draft_text` que receber, e nada registra o que foi aprovado, quando, para qual alvo/conta, nem o resultado (OBSERVADO). A fila torna "o que o usuário viu" = "o que foi enviado" verificável e deixa histórico.

Não-objetivo: provar que um humano aprovou. Uma fila local gerida pelo mesmo agente só dá **integridade** (o texto não mudou entre card e envio). Aprovação humana real exige canal fora do agente (ver §10, risco R1).

## 2. Itens e escopo

Três tipos, mapeados para `PublishKind` existente (`backend_selector.py:~40`: comment/reply/post/reshare):

| Tipo na fila | `kind` do publish | Skill que produz o rascunho (existente) | Alvo |
|---|---|---|---|
| `post` | `post` | `linkedin-post-writer`, `linkedin-repurposer` | feed próprio (+ rede, ver adaptador) |
| `comment` (post de terceiro) | `comment` | `linkedin-comment-drafter` (`SKILL.md:41` chama `lib.publish(kind="comment", ...)`) | URN do post alheio |
| `reply` (resposta em post próprio) | `reply` | `linkedin-reply-handler`, acionado por `linkedin-thread-monitor` | URN do post + `parent_comment` |

`reshare` fica fora desta fase (mesma estrutura, adicionável depois). Nenhuma skill nova: o invariante de 12 skills (CLAUDE.md) é mantido; a fila é biblioteca (`lib/`), não skill.

## 3. Registro de item (campos)

Arquivo-fonte de verdade: **JSONL append-only de eventos**, um evento por transição. Estado atual = último evento do `item_id`. (Escolha por simplicidade e auditoria; SQLite é alternativa se surgir consulta pesada, DESCONHECIDO se necessário.)

```
item_id        uuid
kind           post | comment | reply
network        linkedin | x | threads      (v1: só linkedin)
account_id     platformId do canal (ex.: linkedin-xxxx), nunca o token
target         { url, urn, parent_comment?, post_urn? }   (post: composer URL)
text           texto exato
text_hash      sha256(NFC(text))
approval_hash  sha256(canonical_json({kind, network, account_id, target.urn|url,
                                      parent_comment, text_hash, scheduled_time,
                                      media_urls}))
scheduled_time ISO 8601 UTC | null (null = publicar quando liberado)
media          [{url, sha256?}]
origin         { skill, source_urls[], source_comment_id? }
state          (ver §4)
events[]       { ts, from, to, actor(agent|user|system), note }
remote         { postGroupId?, comment_id?, status? }    (retorno da Publora)
dedupe_key     ver §7
```

O que o hash cobre (pedido: texto exato + alvo + conta + horário): tudo em `approval_hash`. Mudar **qualquer** campo coberto muda o hash e invalida a aprovação. `text_hash` isolado serve para dedupe e diff.

Armazenamento: caminho configurável, padrão **fora** de `testing/` e fora do repo público (ex.: `~/.linkedin-skills/queue.jsonl`), porque contém texto privado e IDs de conta. Nunca guardar `PUBLORA_API_KEY`. O repo ignora `plans/` e `testing/` por privacidade (`.gitignore`, OBSERVADO); a fila deve seguir o mesmo princípio e não ser commitada. Se ficar dentro do repo, precisa entrar no `.gitignore` e no `scripts/check_no_secrets.py`.

## 4. Estados e transições

```
 drafted ──submit──▶ pending_review ──approve(hash)──▶ approved ──release──▶ queued ──┐
    ▲                     │  ▲                            │                          │ (publora)
    │                     │  └──── edit ──────────────────┤ invalida                 ▼
    └────── edit ─────────┘                               │                       published ──▶ measured
                          reject ──▶ rejected             └─ cancel ─▶ cancelled        │
                                                                   failed ◀──────────────┘ (erro de API)
                                                                   expired (aprovado, mas horário passou sem release)
```

- `drafted`: skill gerou o texto. `pending_review`: card apresentado ao usuário. `approved`: usuário aprovou **este** `approval_hash`.
- `release`: único ponto que chama `lib.publish`; só aceita item `approved` cujo hash recalculado agora == hash aprovado.
- `queued`: na Publora como agendado (resposta com `postGroupId`; `publora_client.py:175-208`). `published`: confirmado por `get_post` (status top-level, `tests/fixtures/publora_get_post.json`, OBSERVADO). `failed`: erro de API; nunca retenta sozinho (Publora não retenta, DOCUMENTADO em rate-limits; e retry cego de comentário duplicaria).
- `cancelled`: via `lib.unpublish` (`backend_selector.py:162`) se `queued`; se já `published`, **não** há cancelamento pela API (OBSERVADO, `:166-175`), registra-se `needs_manual_delete`.
- `measured` (opcional, lacuna 10): métrica anexada depois; fora da v1.

## 5. Invalidação ao editar

Regra única: **toda edição de campo coberto cria novo `approval_hash` e leva o item de volta a `pending_review`**, descartando a aprovação anterior (evento `invalidated`). Casos:

- Humanizer/audit reescreve o texto após aprovação → invalida (o caminho mais provável de erro hoje).
- Trocar horário, conta, alvo ou mídia → invalida.
- Item `queued` editado → é `update` remoto: v1 faz `cancel` + novo item (CLAUDE.md prefere editar agendado, mas o cliente não implementa `PUT /update-post`, OBSERVADO; ver gap 5). Evolução: método `update_post` no cliente.
- Aprovação em lote nunca sobrevive à edição de um item: só aquele item volta.

## 6. Aprovação em lote

- Lote = lista de `(item_id, approval_hash)` apresentada num único card; o usuário aprova **pares id+hash**, não "todos". Aprovar "tudo" = aprovar a lista exibida naquele instante; itens adicionados depois não entram.
- Cada item continua com seu hash e sua transição; falha de um não impede os demais (`failed` individual).
- Teto de lote sugerido pela cota (Publora grátis: 3 agendados pendentes, 15 posts/mês, comentário contando ou não é DESCONHECIDO; ver `gap-analysis.md` §6): a fila deve mostrar **cota restante estimada** no card, marcando "estimativa" porque não há endpoint de cota confirmado.
- Para comentários/respostas (volume alto, baixo risco por item), lote é o caso de uso principal; para `post`, recomenda-se aprovação individual.

## 7. Deduplicação

`dedupe_key = sha256(kind | account_id | target.urn_or_url | parent_comment | text_hash)`.

- Bloqueia: mesmo texto, mesmo alvo e conta já em `queued`/`published` (ex.: reenvio após resposta perdida, caso que o guia da Publora cobre com `idempotencyKey`, mencionado nas instruções do conector Publora desta sessão; para a REST `/create-post` o suporte a idempotência é DESCONHECIDO).
- Aviso (não bloqueio): mesmo alvo, texto diferente em < N horas (dois comentários na mesma thread), texto quase igual (similaridade) em alvos diferentes (comentário colado em vários posts).
- Reconciliação com o remoto: antes de reenviar um item em `failed`/incerto, `get_post(postGroupId)` ou, para comentário (sem leitura em `/linkedin-comments`, DOCUMENTADO), listar via Apify, se disponível, ou pedir confirmação manual. Sem isso, "falhou" pode ter sido "publicou e a resposta se perdeu".

## 8. Histórico e aprendizado

O JSONL é o histórico: rascunho → edições → aprovação → envio → resultado. Aproveita-se para:
- substituir o `testing/linkedin-routine-log.jsonl` (`scripts/schedule_post.py:26`) como fonte de rotação de ângulo (leitura, não migração obrigatória);
- alimentar `thread-monitor` com "o que eu respondi e quando" sem depender do contexto da sessão;
- base para métricas futuras (`measured`), por `postGroupId`.
Aprendizado revisável (etapa 11 do fluxo) fica fora desta fase; a fila só garante dados limpos para ele.

## 9. Encaixe no código existente (aditivo)

1. `lib/approval.py` (hoje 49 linhas, só `render_approval_card`): ganha `fingerprint(item)` e o card passa a exibir `approval_hash` curto (8 chars) + conta + horário + alvo.
2. `lib/queue.py` (novo módulo, fora de `__all__` até estabilizar): `enqueue`, `approve(item_id, approval_hash)`, `edit`, `release(item_id)`, `history(...)`. Sem dependência nova (stdlib; manual-tier continua sem `requests`, como exige `lib/__init__.py:32-34`).
3. `release` chama `backend_selector.publish(kind, draft_text, target_url, approved_hash=..., **kwargs)`; em `publish`, `approved_hash` opcional: se presente e `sha256(draft_text)`/payload ≠ aprovado, recusa antes de qualquer ramo (publora/manual/diy, `:274/282/346`). Ausente = comportamento atual (compatível).
4. Adaptador de publicação (proposto no gap-analysis §1): `network=` seleciona o adaptador; a fila só grava `network` e `account_id`, o adaptador define limite de caracteres e `platformSettings`. v1 só `linkedin`.
5. Skills existentes: trocam a etapa "On approval" por "enfileirar → card → aprovar → release" **sem criar skill**. `comment-drafter` (`SKILL.md:41`), `reply-handler` e `post-writer` (`SKILL.md:94`) mudam um passo cada. `thread-monitor` só lê a fila para saber o que já foi respondido.
6. Testes obrigatórios antes de documentar kwargs nas skills: `tests/test_skill_contracts.py:61-90` falha se uma skill citar kwarg que a função não aceita (OBSERVADO). Ordem: código + teste primeiro, doc depois. Adicionar testes de dispatch de `publish("post")` para os 3 backends (lacuna 6).
7. `scripts/sync_codex_marketplace.py` copia `lib/`: rodar após editar. Sem menção a schedulers concorrentes em arquivos commitados.

## 10. O que depende da resposta da Ponte sobre ler comentários

- `reply`/`thread-monitor` precisam **ler** comentários. `/linkedin-comments` não lê (DOCUMENTADO: só POST/DELETE). Hoje a leitura é Apify (`apify_client.py:181 fetch_post_comments`, `:234 fetch_user_recent_comments`), pago por uso (README, DECLARADO). Se a Ponte concluir que há outra via oficial e gratuita de leitura, muda: origem de `reply`, `dedupe` por `source_comment_id` e a reconciliação do §7.
- Sem leitura automática, o fluxo degrada para colar o comentário (o `reply-handler` já aceita fallback manual via `lib.fetch_post`, `backend_selector.py:375`). A fila funciona nos dois casos; só muda `origin`.
- `parent_comment` correto depende de dado lido (LinkedIn achata em 2 níveis, descrição do `reply-handler`): entra no hash, então erro de leitura vira aprovação do alvo errado. Mitigar mostrando o comentário-pai no card.
- Se a cota de 15 posts/mês contar comentários (DESCONHECIDO), a fila precisa de prioridade/orçamento por tipo (o `plans/linkedin-plan.md` já separa 3 comentários/mês via API).

## 11. Riscos e contra-argumentos

- **R1 — hash ≠ aprovação humana.** O agente que cria o card também chama `approve`. A fila impede divergência acidental, não má-fé nem erro de interpretação do "yes". Reduz risco só se `approve` exigir entrada que o agente não fabrica (ex.: código curto exibido no card digitado pelo usuário; fricção alta para lote).
- **R2 — Superengenharia.** Para ~15 posts/mês e poucos comentários, um JSONL com hash pode bastar; a máquina de estados completa (`expired`, `measured`, lote) talvez seja excessiva. Sugestão: v1 = `enqueue → approve(hash) → release → published/failed` + histórico; o resto vem com uso.
- **R3 — Duas fontes de verdade.** Publora guarda estado remoto; a fila local pode divergir (post editado/apagado no painel). Mitigação: reconciliar por `get_post` e tratar o remoto como autoridade para `status`.
- **R4 — Privacidade.** Fila contém texto não publicado e IDs de conta. Fora do repo; permissões 0600; sem segredos.
- **R5 — Concorrência.** Duas sessões do agente escrevendo no mesmo JSONL. Append atômico de linha única é suficiente na v1; `release` deve checar o último estado do item imediatamente antes de enviar (evita duplo envio).
- **R6 — Premissa não validada:** que os limites do plano grátis (3 pendentes) sejam o gargalo real. Só o uso mostra; a fila deve registrar `failed` com a razão da API para medir.
- **Fora do escopo autorizado:** qualquer caminho que contorne limites/autenticação do LinkedIn ou da Publora. O desenho usa só a API oficial e o ramo `diy` do próprio usuário.

## 12. Perguntas abertas

1. Comentários/reações contam na cota da Publora? (DESCONHECIDO; só o painel/suporte responde.)
2. Existe idempotência em `/create-post` e `/linkedin-comments`? (DESCONHECIDO, não lido: https://docs.publora.com/endpoints/linkedin-comments.)
3. Via oficial de leitura de comentários além do Apify? (Ponte.)
4. Local da fila e política de retenção (o usuário decide).

---

# Adendo v1.1 (2026-10-25): correções após revisão

Esta seção **prevalece** sobre as anteriores onde houver conflito (a v1 implementada é `lib/approval_queue.py`, `scripts/approval_queue.py`, gate em `lib.publish`).

## A. Aprovação só humana (B1)

- Não existe `approve` programático nem comando CLI `approve`. A única via é `review` (`lib.approval_queue.review_on_tty`), que lê **cada decisão e um código aleatório de 6 hex de `/dev/tty`**, não de stdin, argumento ou pipe. O cartão (texto exato, alvo, contas, horário, hash) e o código são impressos só nesse terminal. Sem `/dev/tty` a operação recusa (`ApprovalError`, exit 3).
- A aprovação fica presa ao hash exibido no cartão: item editado enquanto o cartão estava aberto volta `stale`.
- `list`/`show` imprimem o hash **somente** se stdout for um terminal. Saída em pipe nunca contém o hash (um agente que lê a saída não consegue montar o par).
- Caracteres de controle, ESC, bidi e zero-width aparecem escapados (`\uXXXX`) no cartão e na listagem, com aviso na linha `note`.
- **É barreira, não prova.** Um agente com permissão de alocar um pty próprio (ex.: `script`, `python -c "import pty"`) ou de editar o ledger direto pode contorná-la. Por isso, junto com o código, recomendam-se regras de permissão (abaixo). Hash e código dão integridade do que o humano viu; não provam quem digitou.

### Regras sugeridas para `settings.json` do Claude Code (NÃO aplicadas; o usuário decide)

Barreira adicional, em camadas. Ajuste caminhos ao seu ledger (`testing/approval-queue.jsonl` ou `$LINKEDIN_SKILLS_QUEUE_PATH`):

```json
{
  "permissions": {
    "deny": [
      "Bash(python3 scripts/approval_queue.py review:*)",
      "Bash(python scripts/approval_queue.py review:*)",
      "Bash(*approval_queue.py review*)",
      "Edit(testing/approval-queue.jsonl*)",
      "Write(testing/approval-queue.jsonl*)",
      "Edit(~/.linkedin-skills/**)",
      "Write(~/.linkedin-skills/**)"
    ],
    "ask": [
      "Bash(python3 scripts/approval_queue.py reconcile:*)",
      "Bash(python3 scripts/approval_queue.py reject:*)",
      "Bash(*pty*)",
      "Bash(*script -q*)"
    ]
  }
}
```

Limites das regras: padrões de Bash são por prefixo/glob e contornáveis (variável de ambiente, `bash -c`, outro caminho do script, `import lib.approval_queue`); negar `Edit/Write` não impede `Bash(echo >> ledger)`. Tratar como atrito, não como controle. A defesa de fato forte seria fora do agente (processo/usuário separado, ou um segundo fator no celular), não implementada na v1.

## B. Envio único (B2)

Fluxo: `pending -> approved -> sending -> sent | failed | unknown` (+ `rejected`).
- Sob `flock` (sidecar `<ledger>.lock` + lock de thread), a transição `approved -> sending` é gravada **antes** do dispatch; só quem fez a transição despacha. Quem chega depois recebe `ApprovalError`.
- `except BaseException` (inclui `KeyboardInterrupt`/`SystemExit`) grava o desfecho classificado e relança; o padrão é `unknown`.
- `sending` e `unknown` bloqueiam reenvio e reenfileiramento (o dedupe os trata como ativos). Se o processo morre no meio, o item fica `sending` até alguém reconciliar.
- Reconciliação manual: `scripts/approval_queue.py reconcile <id> sent|failed --note "o que foi conferido"` (nota obrigatória; só para `sending`/`unknown`; evento `reconciled` no histórico). Só depois de `failed` o mesmo texto pode ser reenfileirado (e reaprovado no terminal).
- Tier manual: nada é enviado, a reivindicação é liberada e o item volta a `approved`.

## C. O hash cobre o que é entregue (B3, M1)

- `accounts` = **lista efetiva completa** resolvida antes de enfileirar (`resolve_accounts(kind, platform_id=, platforms=)`, espelha `_dispatch`: post vai para `platforms` ou `[platform_id|LINKEDIN_PLATFORM_ID]`; comment/reply para `platform_id|LINKEDIN_PLATFORM_ID`). Ordem não importa. Conta não resolvida em backend não-manual => recusa.
- Entram no hash: kind, network, accounts, target, post_urn, parent_comment, **reaction_type**, texto (NFC, `\n`), horário (UTC), mídia (ordem importa). `HASH_VERSION = "v2"`.
- **Allowlist de kwargs** por kind (`ALLOWED_KWARGS`); qualquer outro kwarg com valor não-None => `ApprovalError` ("not covered"). `network != linkedin` => recusa (não há adaptador).
- `parent_comment` só existe em `reply`: enqueue exige, o gate recalcula com o mesmo valor, e um `comment` com `parent_comment` é recusado (nos dois lados).

## D. Classificação de erro (I1)

Decidida pelo status HTTP, nunca por nome de classe ou texto: 4xx exceto 408/429 => `failed`; 5xx, 408, 429, timeout, conexão caída, diy com exit != 0, qualquer outra coisa => `unknown`. Erro levantado **antes** de qualquer request (`PubloraError(request_sent=False)`: sem chave, limite local de 1.250) => `failed`. Para isso `PubloraError` ganhou `status_code` e `request_sent` (aditivo; mensagem inalterada, o retry existente continua funcionando).

## E. Exigir aprovação e reshare (I2)

`LINKEDIN_SKILLS_REQUIRE_APPROVAL=1` faz `lib.publish` recusar qualquer chamada sem `approved_hash`. `reshare`/`repost` ficam **fora da v1**: com o switch ligado, ou com hash, levantam `ApprovalError` explicando; sem o switch continuam como antes. Nenhuma skill foi alterada.

## F. Ledger (I4)

Linha truncada ou ilegível é ignorada com `RuntimeWarning` (número da linha), sem derrubar a fila; o próximo append começa em linha nova se o arquivo terminou sem `\n`.

## G. Ficou de fora e por quê

- Aprovação fora do agente (segundo fator, processo separado): exige infraestrutura e decisão do usuário.
- Retentativa interna do `PubloraClient` (`_retry`) em 5xx para `POST /create-post` pode, em tese, duplicar um envio se o servidor processou antes de falhar; a fila classifica o resultado final como `unknown` mas não impede o retry interno. Idempotência da API: DESCONHECIDO.
- Skills ainda não usam a fila; kwargs novos não estão documentados nelas (o `test_skill_contracts` exige código antes de doc).
- Adaptadores X/Threads, métricas, `update_post`, reshare no gate.

## Limites de segurança

A fila é um **guard-rail contra erro e contra injeção descuidada** (texto trocado entre o cartão e o envio, aprovação por engano, reenvio). **Não é uma fronteira de segurança.** Risco residual, todos ao alcance de um agente com shell:
- **pty próprio:** um processo que aloque seu próprio pseudo-terminal pode ser o "humano" que digita decisão e código em `/dev/tty`.
- **Escrita direta no ledger:** editar o JSONL (ou o `.lock`) à mão contorna estados e hashes.
- **Chamada direta ao `PubloraClient`** (ou a `lib.publish` sem hash, se `LINKEDIN_SKILLS_REQUIRE_APPROVAL` não estiver ligado): a Publora recebe o post sem passar pela fila.

Fronteira real exige que a credencial de publicação (`PUBLORA_API_KEY`, token do LinkedIn) fique **fora do alcance do agente** (outro usuário/processo/serviço que só publica itens aprovados), com a aprovação vindo de um canal que o agente não controla. Não implementado na v1.

Retry (v1.2): atrás do gate (`approved_hash`) o cliente não repete POST após 5xx/408/timeout/conexão caída; só repete em 429 e quando nenhuma conexão chegou a ser feita. O desfecho vai para `unknown`. Nenhum `idempotencyKey` é enviado (suporte no REST: DESCONHECIDO). Sem gate, o retry é o de antes.
