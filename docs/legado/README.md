# Legado: classificador anterior (taxonomia pública, score 0–100)

Substituído em 09/11/2026 pela **base de ofertas TLS** (`ofertas_tls_radar.json`, privada, guardada no Supabase) e pelo motor
`collector/radar/ofertas.py`, que segue o bloco `regras_de_match` do próprio JSON.

Guardado aqui só para consulta (não é usado pelo código):

| Arquivo | O que era |
|---|---|
| `portfolio_tls.yml` | taxonomia pública neutra: termos, sinônimos, fabricantes, pesos e limiares |
| `portfolio_private.example.yml` | formato do antigo secret `RADAR_PRIVATE_CONFIG` (não é mais usado) |
| `classifier.py` | motor de score 0–100 com justificativa |
| `PORTFOLIO.md` | fontes públicas da taxonomia |
| `avaliar_embeddings.py` | avaliação opcional de embeddings sobre o classificador antigo |
| `collector-tests/` | testes do classificador antigo (inclui trechos reais do PNCP) |

Na troca, a publicação foi redecidida uma única vez com a regra nova (o que não casa nenhuma oferta saiu do site);
depois disso voltou a valer "só sai quando vencer".
