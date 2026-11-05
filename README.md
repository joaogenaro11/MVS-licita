# RADAR TLS — Radar de Demanda Pública

Sistema de inteligência comercial que encontra, no **PNCP (Portal Nacional de Contratações Públicas)**,
contratações públicas e atas de registro de preços aderentes ao portfólio **IBM Technology Lifecycle Services**:
Networking, Security, MVS (multivendor), Data Center, Hardware Refresh e suporte de software de terceiros.

- **Coleta real e automática:** GitHub Actions, duas vezes por dia, com custo zero.
- **Estágios cobertos:** PCA (planejamento), edital/aviso publicado, propostas abertas, julgamento, atas vigentes e contratos.
- **Classificação TLS explicável:** score de 0 a 100 com justificativa baseada só em termos encontrados no texto oficial.
- **Link direto** para a disputa no portal de origem (`linkSistemaOrigem` oficial), para o PNCP e para os documentos publicados.
- **Radar de Atas:** vigência, vencimento e potencial de adesão (indicativo, nunca afirmado sem evidência).
- **Site estático no GitHub Pages**, sem servidor ligado o tempo todo.
- **Dados comerciais internos protegidos** por autenticação real (Supabase Auth + RLS, opcional e gratuito).

> **Guia da equipe (como funciona, quando busca, quando um item sai do site):** [docs/COMO-FUNCIONA.md](docs/COMO-FUNCIONA.md)
> Escopo do MVP, limitações e contrato validado da API: [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

---

## Estrutura

```
.
├── config/
│   ├── portfolio_tls.yml               # taxonomia TLS pública: termos, sinônimos, fabricantes, pesos, limiares
│   ├── fontes.yml                      # modalidades, janelas, carga histórica, enriquecimento, publicação
│   └── portfolio_private.example.yml   # ESTRUTURA da configuração comercial privada (sem dados)
├── collector/                          # coletor + classificador (Python)
│   ├── radar/
│   │   ├── pncp.py        # cliente HTTP: retry/backoff, paginação, 204 ≠ erro
│   │   ├── normalize.py   # modelo de dados, estágios, links oficiais, vigência/adesão de atas
│   │   ├── classifier.py  # motor de classificação TLS
│   │   ├── pipeline.py    # orquestração incremental/histórica, enriquecimento, export do site
│   │   ├── store.py       # JSON versionado, escrita atômica, base nunca encolhe
│   │   ├── probe.py       # diagnóstico das fontes (roda no CI)
│   │   └── cli.py
│   ├── tests/             # pytest (inclui registros reais do PNCP)
│   └── tools/avaliar_embeddings.py   # avaliação opcional de IA (local)
├── web/                   # React + Vite + Tailwind (GitHub Pages)
├── docs/                  # arquitetura, portfólio, IA, SQL do Supabase
└── .github/workflows/
    ├── ci.yml             # testes + diagnóstico real do PNCP + amostra classificada
    └── update-radar.yml   # coleta agendada -> branch data -> GitHub Pages
```

---

## Implantação (passo a passo)

### 1. Repositório

O código já está neste repositório. Para criar outra cópia:

```bash
git clone https://github.com/joaogenaro11/MVS-licita.git
```

> **Repositório público:** o GitHub Pages gratuito exige repositório público, e o Actions é gratuito nos runners padrão.
> Tudo o que é commitado fica visível, por isso **nenhum dado comercial interno vai para arquivos do repositório**.

### 2. Ativar o GitHub Pages

1. **Settings > Pages > Build and deployment > Source: GitHub Actions**.
2. **Settings > Actions > General > Workflow permissions: Read and write permissions**. O workflow grava a base no branch `data`.

### 3. Primeira coleta (carga histórica)

**Actions > Atualizar Radar TLS > Run workflow**, com `budget_min = 300` e `backfill = true`.

- O workflow coleta, classifica, cria o branch `data`, publica o site e mostra um resumo por fonte.
- **O PNCP limita a taxa de requisições** (HTTP 429 a partir de cerca de 25 req/min no teste real). O coletor desacelera sozinho.
  Por isso, a carga histórica de 12 meses e a varredura de cerca de 480 mil atas vigentes levam **alguns dias** de execuções.
  Elas continuam sozinhas nas execuções agendadas (06:23 e 17:41, horário de Brasília), e o progresso aparece no Dashboard.
  As propostas abertas e as publicações recentes aparecem já na primeira execução.
- O endereço do site aparece em **Settings > Pages** (ex.: `https://joaogenaro11.github.io/MVS-licita/`).

### 4. (Opcional) Configuração comercial privada da coleta

Para aplicar parâmetros internos ao score (cobertura validada por fabricante, peso relativo das ofertas):

**Settings > Secrets and variables > Actions > New repository secret**
- Nome: `RADAR_PRIVATE_CONFIG`
- Valor: o YAML no formato de `config/portfolio_private.example.yml`.

Só valores numéricos e enumerados são aplicados na coleta. Notas, órgãos prioritários e parceiros
**nunca** são gravados nos dados públicos: eles ficam no Supabase (passo 5).

### 5. (Opcional) Acompanhamento compartilhado com login real

**É necessário?** Para os dados públicos de licitações, não: eles já são públicos no PNCP. Já status comercial,
responsável, observações, órgãos prioritários e parceiros são **internos**. Uma "senha no JavaScript" não protege
nada, então o Radar usa autenticação real com o **Supabase** (plano gratuito). Sem o Supabase, favoritos e
anotações ficam só no navegador de cada pessoa, e a interface avisa isso.

1. Crie um projeto em https://supabase.com (plano gratuito).
2. **SQL Editor:** execute [`docs/supabase.sql`](docs/supabase.sql) e depois cadastre os 3 e-mails:
   ```sql
   insert into public.allowed_users (email) values ('a@empresa.com'), ('b@empresa.com'), ('c@empresa.com');
   ```
3. **Authentication > Sign In / Providers:** desative "Allow new users to sign up".
4. **Authentication > Users > Add user > Create new user:** crie os 3 usuários com senha ("Auto Confirm").
5. **Authentication > URL Configuration:** em Site URL, coloque o endereço do GitHub Pages.
6. No GitHub, em **Settings > Secrets and variables > Actions > Variables**, crie:
   - `SUPABASE_URL` = `https://<projeto>.supabase.co`
   - `SUPABASE_ANON_KEY` = a chave `anon` (Project Settings > API)

   A chave `anon` é pública por definição. A proteção está nas políticas RLS: sem login e sem estar na
   allowlist, nenhuma linha é lida ou gravada.
7. Rode o workflow de novo. No site, em **Acompanhamento > Entrar**, cada usuário faz login. A configuração
   comercial (órgãos prioritários, parceiros, notas) é colada em "Configuração comercial privada".

Para testar o isolamento sem login, rode no SQL Editor `set role anon; select * from tracking;`. O resultado deve vir vazio ou com erro de permissão.

---

## Desenvolvimento local

```bash
# Coletor (Python 3.11+)
cd collector
pip install -r requirements.txt
python -m pytest -q                                  # testes
python -m radar probe                                # diagnóstico das fontes (rede)
python -m radar update --data-dir ../data --budget-min 20
python -m radar export --data-dir ../data --out ../web/public/data

# Interface
cd ../web
npm install
npm test
npm run dev           # http://localhost:5173 (lê web/public/data)
```

Os dados locais (`/data` e `web/public/data`) são ignorados pelo git.

---

## Manutenção

| Tarefa | Como |
|---|---|
| Ajustar termos, fabricantes, pesos ou limiares | Editar `config/portfolio_tls.yml` → `pytest` → commit (a próxima execução reclassifica tudo) |
| Ajustar regras comerciais internas | Atualizar o secret `RADAR_PRIVATE_CONFIG` |
| Fazer uma nova busca agora | Botão **Nova busca** no Dashboard (ou Actions → Atualizar Radar TLS → Run workflow) |
| Mudar frequência | `cron` em `.github/workflows/update-radar.yml` |
| Quando um registro sai do site | `config/fontes.yml > vencimento` (só sai ao vencer; a base guarda tudo) |
| Modalidades, horizonte, carga histórica | `config/fontes.yml` |
| Reduzir ou ampliar o volume publicado | `storage.publish_min_score` em `config/fontes.yml` |
| Ver saúde das fontes | Dashboard ("Atualização dos dados") ou resumo da execução no Actions |
| Diagnosticar a API do PNCP | `python -m radar probe` ou o job `source-probe` do CI |
| Recomeçar a varredura de atas | Remover a chave `atas_varredura` de `state.json` no branch `data` |

### Problemas comuns

- **Site mostra "Não foi possível carregar os dados":** a primeira execução ainda não terminou ou falhou. Veja a aba Actions.
- **Fonte com "Falha" no Dashboard:** o PNCP retornou erro (5xx/timeout) depois das novas tentativas. Os dados anteriores foram mantidos e a próxima execução tenta de novo, sem avançar o cursor.
- **Push no branch `data` negado:** habilite "Read and write permissions" (passo 2).
- **PCA com "Falha" ou sem resultados:** o `/v1/pca/` do PNCP exige o código da classe do catálogo, e o `/v1/pca/atualizacao`
  traz cerca de 170 mil itens por dia de todos os assuntos, o que é inviável com o limite de requisições.
  Rode `python -m radar probe --pca` (ou veja o job `source-probe` do CI), que lista as classes com itens aderentes ao TLS.
  Depois copie os códigos para `config/fontes.yml > pncp.pca.classificacoes`.

---

## Decisões de projeto

- **Regras antes de IA:** veja [docs/IA.md](docs/IA.md). O ganho de recall vem de ler itens e documentos, não de um modelo sobre o mesmo objeto curto.
- **Separação público × privado:** taxonomia pública neutra ([docs/PORTFOLIO.md](docs/PORTFOLIO.md)). Regras e listas comerciais ficam no secret e no Supabase.
- **Honestidade dos dados:** nada é inventado. Campos ausentes aparecem como "Não informado", vigências impossíveis aparecem como "a conferir", adesão é só indicativa e a busca opera sobre a base coletada (a interface informa isso).

## Próximas versões (fora do MVP)

Análise de TR/edital completos, exportação CSV/Excel, relatórios por órgão e por oferta, alertas por e-mail ou Teams,
IRPs, histórico de alterações e o módulo **Análise de Compras** (PCA × PDTI/PDTIC × PETI por órgão). Esse módulo
já aparece no menu como "Em breve".
