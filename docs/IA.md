# IA open-source no Radar TLS — avaliação e decisão

## Decisão para o MVP

**O MVP usa apenas o classificador por regras** (`config/portfolio_tls.yml` + `collector/radar/classifier.py`).
Ele é explicável (cada ponto do score vem de um termo encontrado no texto), roda em milissegundos
dentro do GitHub Actions e pode ser calibrado sem reprogramar o sistema.

Nenhum modelo foi adicionado ao pipeline automático. Isso segue o critério do projeto: incluir IA
somente quando ela demonstrar ganho real.

## Onde estão os erros de verdade

| Problema | Causa | Embeddings ajudam? | O que ajuda de fato |
|---|---|---|---|
| Objeto genérico ("aquisição de equipamentos de TIC conforme TR") | A informação está nos itens/PDF, não no objeto | Pouco: o texto não contém a informação | **Coleta dos itens** (já implementada no enriquecimento) |
| Sinônimos não previstos ("comutadores", "concentradores") | Vocabulário | Sim, moderadamente | Incluir o termo no YAML (imediato) |
| Falsos positivos ("servidores públicos", "rede de ensino") | Polissemia | Parcialmente | Lista `neutralize` (já implementada, testada) |
| Escopo comercial (o que o TLS vende) | Regra de negócio | Não | Configuração privada (cobertura por fabricante) |

Conclusão: o maior ganho de **recall** vem de ler mais texto oficial (itens, e no futuro TR/edital), não
de um modelo semântico sobre o mesmo objeto curto.

## Opções avaliadas (execução em CPU, sem API paga)

| Modelo | Tamanho | Licença | Português | Observação |
|---|---|---|---|---|
| `intfloat/multilingual-e5-small` | ~118M parâmetros | MIT | Bom | Melhor custo/benefício; viável em CPU |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | ~118M | Apache-2.0 | Bom | Muito usado; um pouco inferior ao e5 em recuperação |
| `BAAI/bge-m3` | ~568M | MIT | Muito bom | Mais preciso, porém ~4× mais lento e mais memória |
| `PORTULAN/serafim-100m-portuguese-pt-sentence-encoder` | ~100M | verificar no repositório | Específico PT | Alternativa focada em português |
| LLM pequeno (ex.: Qwen2.5-1.5B-Instruct) | 1,5B | verificar licença por tamanho | Razoável | Só se for para ler TR/edital longos; caro em CPU |

> Licenças e versões devem ser conferidas no repositório do modelo antes do uso. Os modelos mudam com frequência.

### Viabilidade no GitHub Actions (plano gratuito)

- Runner padrão: CPU de 4 núcleos e cerca de 16 GB de RAM em repositórios públicos.
- Um modelo de cerca de 118M parâmetros processa algumas dezenas a centenas de textos curtos por segundo em CPU.
  Aplicar o modelo **apenas aos candidatos que passaram pelo pré-filtro** (milhares por dia) é viável.
  Aplicar a **todos** os registros publicados (centenas de milhares por mês) não compensa: ocupa horas de execução e exige cache do modelo.
- Um LLM generativo em CPU para ler PDFs não é viável no Actions com qualidade e tempo aceitáveis. Isso fica para execução local ou para um serviço próprio no futuro.

## Módulo opcional de avaliação (execução local)

`collector/tools/avaliar_embeddings.py` compara, sobre um conjunto **rotulado por vocês**, o classificador por
regras e um re-ranqueamento por similaridade semântica.

```bash
pip install sentence-transformers           # não faz parte do requirements.txt
python collector/tools/avaliar_embeddings.py rotulos.csv --modelo intfloat/multilingual-e5-small
```

`rotulos.csv` tem as colunas `texto,relevante` (1/0). Uma forma prática de montá-lo é exportar as
oportunidades que a equipe marcou como "Qualificado" ou "Descartado" no Acompanhamento.

**Critério para adotar:** só vale a pena se o modelo aumentar o recall em pelo menos 10 pontos percentuais
com a mesma precisão, num conjunto de pelo menos 200 exemplos reais. Se aumentar, o módulo entra como
um componente extra e limitado do score, sem substituir as regras explicáveis.
