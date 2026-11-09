# Como o Radar TLS funciona (guia da equipe)

## Visão geral

```
PNCP (Portal Nacional de Contratações Públicas)
   │  busca automática 2x/dia  (ou "Nova busca" quando vocês quiserem)
   ▼
Coletor (GitHub Actions, gratuito)
   ├─ baixa contratações, propostas abertas, atas, contratos e itens de PCA
   ├─ classifica cada registro com a BASE DE OFERTAS TLS (61 ofertas; arquivo privado guardado no Supabase)
   ├─ guarda os dados públicos na base histórica (branch "data"; a classificação não vai para lá)
   └─ envia ao Supabase os registros que casaram alguma oferta e ainda não venceram
   ▼
Site (GitHub Pages): https://joaogenaro11.github.io/MVS-licita/  → pede login; os dados vêm do Supabase
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
  (12 meses, ~480 mil atas vigentes) é feita em partes, ao longo de vários dias. O progresso por fonte aparece no resumo de cada execução no GitHub Actions.

## O que cada busca faz

1. **Atualizações recentes** (desde a última busca): contratações novas ou alteradas, atas e contratos.
2. **Propostas abertas:** fotografia completa das licitações com prazo aberto, uma vez por semana.
3. **PCA** (planos de contratação 2026/2027): classes de TIC, uma vez por semana.
4. **Carga histórica:** avança alguns dias por busca até cobrir 12 meses.
5. **Itens e documentos oficiais** das oportunidades relevantes (edital, TR etc.).
6. **Classificação**, gravação na base e publicação do site.

## Login e o que é de cada um

- Cada pessoa entra com **usuário e senha**. No primeiro acesso (e depois de uma redefinição) o site pede para criar uma senha pessoal.
- **Seus:** favoritos (estrela), filtro Tudo/Logo/MVS, filtros, ordenação e buscas salvas. Ninguém mais vê.
- **Da equipe:** status comercial, responsável, observação, próximo acompanhamento, órgãos prioritários e parceiros.
- **Administrador:** menu **Usuários** para criar usuário, redefinir senha, **ver a senha temporária** de quem ainda não
  entrou (fica guardada criptografada até a pessoa criar a própria senha), desativar/reativar e enviar nova versão da base de ofertas.

## Como um registro é classificado

Regras do bloco `regras_de_match` da base de ofertas:

- Comparação sem acento e sem maiúsculas, por **palavra inteira** ("Cisco" não casa com "Francisco"; "HP" não casa com "HPC").
- Uma oferta casa se aparece um **termo exato** dela, ou uma **marca + um termo de serviço** dela no mesmo texto (objeto, item ou PCA).
  Termo de "excluir" da oferta impede o casamento.
- **Pontuação:** termo exato = 3; marca + serviço = 2; ×1,5 para oferta de prioridade alta; soma das ofertas casadas.
- **Exclusões globais** (notebook, Power BI, impressora…) não descartam: cortam a pontuação pela metade e geram o selo
  **"possível falso positivo"** (um edital pode ter lote de notebook e lote de switch).
- **Portfólio:** Logo IBM, MVS, **Logo IBM + MVS** (aparece nos dois filtros) ou Transversal (aparece só em "Tudo").
- Oferta marcada como indisponível no Brasil gera o selo **"oferta indisponível no Brasil: ver alternativa"**.
- No card: ofertas casadas (chips), termos destacados em amarelo no texto e selos. No detalhe: como cada oferta casou.

## Busca

| Digite | Resultado |
|---|---|
| `Cisco` | registros com a palavra (também acha "Ciscos", não acha "Francisco") |
| `Cisco Red Hat` | todas as palavras, em qualquer posição |
| `Cisco, Red Hat, Fortinet` | **qualquer um** dos termos; quem casa mais termos aparece primeiro |
| `"switch core Cisco"` | só a **frase exata**, nessa ordem |
| `"suporte técnico", Cisco` | pode misturar |

Sem acento e sem diferenciar maiúsculas (`manutencao` acha `Manutenção`). O card mostra "casou: …". Use **Salvar esta busca**
para guardar (fica só para você).

## Quando um registro aparece e quando some do site

**Aparece** quando casa ao menos uma oferta da base de ofertas e não está vencido.

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
- O Dashboard mostra o status geral (OK, Parcial ou Falha); o detalhe por fonte fica no resumo da execução no GitHub Actions.
- A próxima busca tenta de novo a partir do ponto em que parou.
- **Limitação conhecida:** o endpoint de PCA do PNCP às vezes responde com erro 500 para algumas classes. O Radar registra e tenta de novo.

## Dados internos (favoritos, status, responsável, observações)

- Ficam no Supabase, protegidos por login (ver "Login e o que é de cada um").
- Nada disso, nem a base de ofertas nem a classificação, é publicado no GitHub.
