# RADAR TLS — Radar de Demanda Pública

Sistema de inteligência comercial que encontra, no **PNCP (Portal Nacional de Contratações Públicas)**,
contratações públicas e atas de registro de preços aderentes ao portfólio **IBM Technology Lifecycle Services**:
Networking, Security, MVS (multivendor), Data Center, Hardware Refresh e suporte de software de terceiros.

- **Coleta real e automática:** GitHub Actions, duas vezes por dia, com custo zero.
- **Estágios cobertos:** PCA (planejamento), edital/aviso publicado, propostas abertas, julgamento, atas vigentes e contratos.
- **Classificação pela base de ofertas TLS (61 ofertas, privada):** ofertas casadas, portfólio (Logo IBM, MVS, Logo IBM + MVS ou
  Transversal), pontuação, termos que deram match destacados no texto e selos (possível falso positivo, oferta indisponível no Brasil).
- **Link direto** para a disputa no portal de origem (`linkSistemaOrigem` oficial), para o PNCP e para os documentos publicados.
- **Radar de Atas:** vigência, vencimento e potencial de adesão (indicativo, nunca afirmado sem evidência).
- **Site estático no GitHub Pages**, sem servidor ligado o tempo todo.
- **Acesso individual com login** (Supabase Auth + RLS, gratuito): cada pessoa tem usuário e senha; favoritos, filtros e buscas
  salvas são pessoais; status, responsável e observações são da equipe. Nenhum dado aparece sem login.
- **Busca:** vírgula = qualquer um dos termos; aspas = frase exata. Filtro **Tudo / Logo / MVS** com contadores.

> **Guia da equipe (como funciona, quando busca, quando um item sai do site):** [docs/COMO-FUNCIONA.md](docs/COMO-FUNCIONA.md)
> Escopo do MVP, limitações e contrato validado da API: [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

---

## Estrutura

```
.
├── config/
│   └── fontes.yml                      # modalidades, janelas, carga histórica, enriquecimento, vencimento
│   (a base de ofertas ofertas_tls_radar.json é PRIVADA: fica no Supabase, nunca no repositório)
├── collector/                          # coletor + classificador (Python)
│   ├── radar/
│   │   ├── pncp.py        # cliente HTTP: retry/backoff, paginação, 204 ≠ erro
│   │   ├── normalize.py   # modelo de dados, estágios, links oficiais, vigência/adesão de atas
│   │   ├── ofertas.py     # motor de casamento da base de ofertas (regras_de_match do JSON)
│   │   ├── supa.py        # leitura da base de ofertas e publicação dos dados no Supabase
│   │   ├── pipeline.py    # orquestração incremental/histórica, enriquecimento, export do site
│   │   ├── store.py       # JSON versionado, escrita atômica, base nunca encolhe
│   │   ├── probe.py       # diagnóstico das fontes (roda no CI)
│   │   └── cli.py
│   └── tests/             # pytest (base de ofertas sintética + 12 casos de aceite com a base real)
├── web/                   # React + Vite + Tailwind (GitHub Pages)
├── docs/                  # arquitetura, guia da equipe, SQL do Supabase; docs/legado = classificador anterior
└── .github/workflows/
    ├── ci.yml             # testes + diagnóstico real do PNCP + ponta a ponta com base sintética
    └── update-radar.yml   # coleta agendada -> branch data (público, sem classificação) -> Supabase -> GitHub Pages
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

- O workflow coleta, classifica, cria o branch `data`, publica os dados no Supabase e o site no Pages, e mostra um resumo por fonte.
- **O PNCP limita a taxa de requisições** (HTTP 429 a partir de cerca de 25 req/min no teste real). O coletor desacelera sozinho.
  Por isso, a carga histórica de 12 meses e a varredura de cerca de 480 mil atas vigentes levam **alguns dias** de execuções.
  Elas continuam sozinhas nas execuções agendadas (06:23 e 17:41, horário de Brasília); o progresso por fonte aparece no resumo de cada execução no Actions.
  As propostas abertas e as publicações recentes aparecem já na primeira execução.
- O endereço do site aparece em **Settings > Pages** (ex.: `https://joaogenaro11.github.io/MVS-licita/`).

### 4. Supabase: login, dados privados e base de ofertas

O projeto Supabase `radar-tls` já está configurado (schema em [`docs/supabase.sql`](docs/supabase.sql): tabelas, RLS e
funções de administração). Para outro projeto: execute esse arquivo no SQL Editor.

1. **Secret do GitHub (obrigatório):** *Settings > Secrets and variables > Actions > New repository secret*
   - Nome: `SUPABASE_SERVICE_ROLE_KEY`
   - Valor: no Supabase, *Project Settings > API Keys* → a chave **secret** (`sb_secret_...`) ou a `service_role` legada.

   A coleta usa essa chave para ler a base de ofertas e publicar os dados classificados. Sem ela, a coleta para com uma
   mensagem clara e o site continua com a última publicação.
2. **Authentication > Sign In / Providers:** desative "Allow new users to sign up" (usuários são criados pelo admin).
3. **Primeiro acesso:** cada pessoa entra com o usuário e a senha temporária recebidos e cria a própria senha.
4. **Administração (só admin):** menu **Usuários** → criar usuário, redefinir senha (gera nova temporária, mostrada uma vez),
   desativar/reativar e enviar nova versão da **base de ofertas** (`ofertas_tls_radar.json`).

Como funciona o login: o usuário digita só o nome de usuário; internamente o Supabase Auth usa `<usuario>@radar-tls.invalid`
(domínio reservado, nenhum e-mail é enviado). Senhas com hash bcrypt; sessão JWT; o Supabase limita tentativas por IP e o
site bloqueia por 60 s após 5 erros seguidos. A chave publicável do site é pública por definição: sem login, as políticas RLS
não deixam ler nem gravar nada.

O que é de cada um e o que é da equipe:

| Dado | Escopo |
|---|---|
| Oportunidades, atas, base de ofertas, status da coleta | Equipe (somente leitura; a base de ofertas só o admin vê) |
| Status comercial, responsável, observação, próximo acompanhamento, órgãos prioritários/parceiros | Equipe |
| Favoritos, filtro Tudo/Logo/MVS, filtros, ordenação, buscas salvas | **Pessoal** |

---

## Desenvolvimento local

```bash
# Coletor (Python 3.11+)
cd collector
pip install -r requirements.txt
python -m pytest -q                                  # testes (base sintética)
RADAR_OFERTAS_REAL_FILE=~/ofertas_tls_radar.json python -m pytest -q tests/test_ofertas_casos.py   # 12 casos com a base real
python -m radar probe                                # diagnóstico das fontes (rede)
export RADAR_OFERTAS_FILE=~/ofertas_tls_radar.json     # base privada (ou copie para config/, não versionado)
python -m radar update --data-dir ../data --budget-min 20
python -m radar export --data-dir ../data --out ../web/public/data   # modo local, sem Supabase

# Interface
cd ../web
npm install
npm test
npm run dev           # http://localhost:5173 (lê web/public/data)
```

Os dados locais (`/data`, `web/public/data`, `config/ofertas_tls_radar.json`) são ignorados pelo git. Sem as variáveis
`VITE_SUPABASE_*`, o site roda em modo local: sem login, lendo `web/public/data`, com favoritos no navegador.

---

## Manutenção

| Tarefa | Como |
|---|---|
| Ajustar termos, marcas, exclusões ou ofertas | Editar o `ofertas_tls_radar.json` e enviar em **Usuários > Base de ofertas** (a próxima coleta reclassifica tudo). O JSON é a única fonte das palavras-chave |
| Criar usuário / redefinir senha / desativar | Menu **Usuários** (admin) |
| Fazer uma nova busca agora | Botão **Nova busca** no Dashboard (ou Actions → Atualizar Radar TLS → Run workflow) |
| Mudar frequência | `cron` em `.github/workflows/update-radar.yml` |
| Quando um registro sai do site | `config/fontes.yml > vencimento` (só sai ao vencer; a base guarda tudo) |
| Modalidades, horizonte, carga histórica | `config/fontes.yml` |
| Ver o efeito de uma nova base de ofertas antes de enviar | `RADAR_OFERTAS_FILE=caminho.json python -m radar reprocessar --data-dir <cópia do branch data> --nao-salvar` |
| Ver saúde das fontes | Dashboard mostra última coleta e status geral; o detalhe por fonte fica no resumo da execução no Actions |
| Diagnosticar a API do PNCP | `python -m radar probe` ou o job `source-probe` do CI |
| Recomeçar a varredura de atas | Remover a chave `atas_varredura` de `state.json` no branch `data` |

### Problemas comuns

- **Site mostra "Não foi possível carregar os dados":** a primeira execução ainda não terminou ou falhou. Veja a aba Actions.
- **Status geral "Parcial" ou "Falha" no Dashboard:** o PNCP retornou erro (5xx/timeout) depois das novas tentativas. Os dados anteriores foram mantidos e a próxima execução tenta de novo, sem avançar o cursor.
- **Push no branch `data` negado:** habilite "Read and write permissions" (passo 2).
- **PCA com "Falha" ou sem resultados:** o `/v1/pca/` do PNCP exige o código da classe do catálogo, e o `/v1/pca/atualizacao`
  traz cerca de 170 mil itens por dia de todos os assuntos, o que é inviável com o limite de requisições.
  Rode `python -m radar probe --pca` (ou veja o job `source-probe` do CI), que lista as classes com itens aderentes ao TLS.
  Depois copie os códigos para `config/fontes.yml > pncp.pca.classificacoes`.

---

## Decisões de projeto

- **Regras antes de IA:** veja [docs/IA.md](docs/IA.md). O ganho de recall vem de ler itens e documentos, não de um modelo sobre o mesmo objeto curto.
- **Separação público × privado:** o repositório e o branch `data` são públicos e só têm dados públicos do PNCP. A base de
  ofertas, a classificação e tudo o que é comercial ficam no Supabase, atrás do login. O GitHub Pages publica só a aplicação.
  Os testes e o CI usam uma base de ofertas **sintética** (`collector/tests/fixtures/`); o classificador anterior está em `docs/legado/`.
- **Honestidade dos dados:** nada é inventado. Campos ausentes aparecem como "Não informado", vigências impossíveis aparecem como "a conferir", adesão é só indicativa e a busca opera sobre a base coletada (a interface informa isso).

## Próximas versões (fora do MVP)

Análise de TR/edital completos, exportação CSV/Excel, relatórios por órgão e por oferta, alertas por e-mail ou Teams,
IRPs, histórico de alterações e o módulo **Análise de Compras** (PCA × PDTI/PDTIC × PETI por órgão). Esse módulo
já aparece no menu como "Em breve".
