# Como o Radar TLS funciona (guia da equipe)

## Visão geral

```
PNCP (Portal Nacional de Contratações Públicas)
   │  busca automática 2x/dia  (ou "Nova busca" quando vocês quiserem)
   ▼
Coletor (GitHub Actions, gratuito)
   ├─ baixa contratações, propostas abertas, atas, contratos e itens de PCA
   ├─ classifica cada registro pela aderência ao portfólio TLS (0 a 100)
   ├─ guarda tudo na base histórica (branch "data" do repositório)
   └─ publica no site os registros relevantes e ainda não vencidos
   ▼
Site (GitHub Pages): https://joaogenaro11.github.io/MVS-licita/
```

## Quando a busca acontece

| Tipo | Quando | Duração |
|---|---|---|
| Automática | Todos os dias às **06:23** e **17:41** (Brasília) | até ~2h30 |
| Manual ("Nova busca") | Quando vocês quiserem | ~40 min por padrão |

- O GitHub às vezes **atrasa** as buscas automáticas (minutos ou algumas horas). Elas acontecem mesmo assim.
- **Nova busca:** no Dashboard, clique em **Nova busca**. O GitHub abre; clique em **Run workflow** e depois em **Run workflow** de novo.
  Também dá pelo app GitHub no celular: *Actions → Atualizar Radar TLS → Run workflow*.
  Ao final, recarregue o site.
- Duas buscas nunca rodam ao mesmo tempo. Se uma já estiver em andamento, a nova espera a anterior terminar.
- O PNCP limita o número de consultas por minuto. Por isso uma busca leva dezenas de minutos e a carga histórica
  (12 meses, ~480 mil atas vigentes) é feita em partes, ao longo de vários dias. O progresso aparece no Dashboard.

## O que cada busca faz

1. **Atualizações recentes** (desde a última busca): contratações novas ou alteradas, atas e contratos.
2. **Propostas abertas:** fotografia completa das licitações com prazo aberto, uma vez por semana.
3. **PCA** (planos de contratação 2026/2027): classes de TIC, uma vez por semana.
4. **Carga histórica:** avança alguns dias por busca até cobrir 12 meses.
5. **Itens e documentos oficiais** das oportunidades relevantes (edital, TR etc.).
6. **Classificação**, gravação na base e publicação do site.

## Quando um registro aparece e quando some do site

**Aparece** quando atinge aderência mínima de **35** e não está vencido.

**Depois que aparece, só sai do site quando VENCE.** Mudanças de pontuação não tiram ninguém do site.

| Registro | Vence (sai do site) em |
|---|---|
| Licitação / edital / aviso | Encerramento do prazo de propostas. Revogada ou anulada sai na hora. Sem prazo informado: 120 dias após a publicação. |
| Item de PCA | 31/12 do ano do plano |
| Ata de registro de preços | Fim da vigência. Cancelada sai na hora. Vigência ausente ou com data impossível **fica** (marcada "a conferir"). |
| Contrato | Fim da vigência. Sem vigência informada: 365 dias após a publicação. |

- Cada card mostra **"No Radar até dd/mm/aaaa"**. O detalhe mostra o motivo.
- **Nada é apagado:** o registro vencido continua na base histórica (branch `data`). Só deixa de aparecer no site.
- Os prazos são ajustáveis em `config/fontes.yml > vencimento`. Por exemplo, para manter licitações por alguns dias
  após o encerramento das propostas: `contratacoes_dias_apos_encerramento: 15`.

## Se uma busca falhar

- O site **continua com os últimos dados válidos**. Uma falha nunca apaga a base.
- O Dashboard mostra a fonte com falha e o motivo.
- A próxima busca tenta de novo a partir do ponto em que parou.
- **Limitação conhecida:** o endpoint de PCA do PNCP às vezes responde com erro 500 para algumas classes. O Radar registra e tenta de novo.

## Dados internos (favoritos, status, responsável, observações)

- **Sem Supabase:** ficam só no navegador de cada pessoa (o site avisa).
- **Com Supabase** (README, passo 5): ficam compartilhados entre os 3 usuários, com login real.
- A configuração comercial privada (órgãos prioritários, parceiros, notas por fabricante) nunca é publicada no site.
