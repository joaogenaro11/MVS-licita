# Arquitetura e validação das fontes

## Visão geral

```
GitHub Actions (2x/dia + manual)
  └─ collector/ (Python)
       ├─ PNCP API de Consulta ──► contratações, propostas abertas, atas, contratos, PCA
       ├─ PNCP API (leitura)   ──► itens e documentos oficiais (enriquecimento)
       ├─ classificador TLS (regras configuráveis em config/)
       └─ base JSON versionada ──► branch `data`  (items.json, atas.json, state.json, meta.json)
  └─ export ──► web/public/data (somente dados públicos, score ≥ mínimo)
  └─ web/ (React + Vite + Tailwind) ──► GitHub Pages (estático)

Navegador
  ├─ lê os JSON estáticos (busca e filtros locais sobre a base coletada)
  └─ (opcional) Supabase Auth + RLS ──► acompanhamento compartilhado e configuração comercial privada
```

Não há servidor ligado o tempo todo. Se uma coleta falhar, o site continua publicado com a última base válida.

## Contrato real da API (validado no CI em 04/11/2026)

O job `source-probe` do CI consulta o PNCP a cada push e registra no log os campos e as respostas reais.

| Endpoint | Uso no Radar | Observações confirmadas |
|---|---|---|
| `GET /api/consulta/v1/contratacoes/publicacao` | Carga histórica (12 meses), por dia e modalidade | `tamanhoPagina=50` aceito; envelope com `totalPaginas` e `paginasRestantes` |
| `GET /api/consulta/v1/contratacoes/atualizacao` | Incremental diário | Mesmo formato; inclui contratações antigas que foram atualizadas |
| `GET /api/consulta/v1/contratacoes/proposta` | Snapshot das propostas abertas | `codigoModalidadeContratacao` opcional; `dataFinal` limita o encerramento |
| `GET /api/consulta/v1/atas` | Varredura de atas vigentes | `dataInicial = dataFinal = hoje` traz **atas vigentes nessa data** (~482 mil em 04/11/2026); há o campo `possibilidadeAdesao` |
| `GET /api/consulta/v1/atas/atualizacao` | Incremental de atas | — |
| `GET /api/consulta/v1/contratos[/atualizacao]` | Contratos e vínculos com atas | Traz `numeroControlePncpAta`, `frutoAdesao` e o fornecedor |
| `GET /api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{seq}` | Detalhe da compra de origem da ata | — |
| `GET /api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens` | Itens (melhora a classificação) | — |
| `GET /api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos` | Documentos oficiais (edital, TR...) | Devolve `url` oficial de download |
| `GET /api/consulta/v1/pca/` | PCA por classificação | Exige `codigoClassificacaoSuperior` (HTTP 400 sem ele) |
| `GET /api/consulta/v1/pca/atualizacao` | PCA por data (opcional) | Instável (HTTP 500 numa execução, 200 em outra). Cada registro é um PCA com `itens`; `totalRegistros` conta itens: cerca de 340 mil em 2 dias, inviável com o limite de requisições |

### Links oficiais

- **Portal de origem (disputa):** campo `linkSistemaOrigem` informado pelo órgão ao PNCP. Exemplos reais
  observados: Compras.gov.br (`cnetmobile.estaleiro.serpro.gov.br/...acompanhamento-compra?compra=...`),
  Pregão Banrisul, Licitanet, Licitar Digital, Portal de Compras Públicas. O Radar **não monta** esse
  endereço: usa exatamente o que a fonte informa, após validar o esquema e o host (`safe_url`).
  Quando o campo está vazio, a interface diz que o endereço direto não foi identificado e oferece o PNCP.
- **PNCP:** `https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}`, `/app/atas/{cnpj}/{ano}/{seqCompra}/{seqAta}`
  e `/app/contratos/{cnpj}/{ano}/{seq}`. São derivados do identificador oficial `numeroControlePNCP`.
  O probe do CI lê as rotas declaradas pelo próprio portal para confirmar essa estrutura.
- **Documentos:** URLs devolvidas pela API de arquivos, abertas diretamente.

### Atas — vigência e adesão

- Vigência calculada a partir de `vigenciaFim`. Datas impossíveis publicadas na fonte (ex.: `7203-07-27`,
  visto em dado real) viram "vigência a conferir" e não são exibidas como fato.
- A **adesão** nunca é presumida pela vigência. Status possíveis:
  - **potencial a verificar:** `possibilidadeAdesao = true`, texto público mencionando adesão, ou contratos já publicados como fruto de adesão;
  - **restrição identificada:** `possibilidadeAdesao = false` ou texto com vedação;
  - **não determinada:** sem evidência pública;
  - **encerrada.**
- Órgão gerenciador não federal gera alerta: órgãos federais não podem aderir (Lei 14.133/2021, art. 86, §8º).
- O fornecedor/detentor vem de contratos publicados que referenciam a ata. Saldo não é verificado.

## Estratégia de coleta

| Etapa | Frequência | Retomada |
|---|---|---|
| Atualizações de contratações, atas e contratos (janelas diárias) | Toda execução | Cursor por dia, com 1 dia de sobreposição |
| Snapshot de propostas abertas | Toda execução | — |
| Varredura de atas vigentes | A cada 30 dias, em fatias | Página salva, com 10 páginas de sobreposição |
| Carga histórica de contratações (12 meses) e de contratos (90 dias) | Fatias por execução | Dia salvo; retoma de onde parou |
| Enriquecimento (itens e documentos) | Candidatos com score ≥ 30, até 1.500 requisições por execução | Por registro |

Garantias:
- Os cursores só avançam depois que um dia inteiro é processado.
- Uma falha de fonte é registrada em `meta.json` e no resumo do Actions, e as demais fontes continuam.
- A base nunca encolhe (a gravação é abortada se isso acontecer).
- A escrita é atômica, com validação do JSON antes de substituir o arquivo.
- `concurrency` do Actions impede execuções simultâneas.

## Volume e custo

- Repositório público: os minutos do GitHub Actions são gratuitos nos runners padrão.
- A base completa fica no branch `data`, com um registro por linha para manter os diffs pequenos.
- O site recebe apenas registros com score ≥ 35 (configurável em `config/fontes.yml`).
- A carga histórica inicial leva algumas execuções. Para acelerar, rode o workflow manualmente com `budget_min=300`.

## Limitações conhecidas

- **ETP e pesquisa de preços:** não há dados estruturados no PNCP. O estágio "Preparação" cobre apenas manifestação de interesse e pré-qualificação.
- **PDTI/PDTIC/PETI:** não há API. Ficam para o módulo futuro "Análise de Compras".
- **PCA:** é coletado apenas pelas classes de TIC configuradas, com snapshot semanal. Até os códigos serem configurados, a fonte aparece como "Falha" com a instrução de configuração.
- **Limite de requisições do PNCP:** HTTP 429 a partir de cerca de 25 req/min no teste real. O throttle é adaptativo, mas a carga histórica leva dias.
- **PDFs:** não são lidos. A classificação usa objeto, informação complementar e itens.
- **Cobertura:** limitada ao que os órgãos publicam no PNCP. Portais estaduais e municipais que não publicam no PNCP não são cobertos.
