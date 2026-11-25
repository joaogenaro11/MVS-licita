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
| Automática | Todos os dias às **11:07** e **18:07** (Brasília) | até ~2h30 |
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
2. **Órgãos relevantes** (lista em `config/orgaos_relevantes.yml`, ~400 órgãos: federais de grande porte,
   Judiciário, Ministério Público, Legislativo, empresas de TI, governos estaduais, capitais e universidades):
   os editais abertos de cada um são consultados pelo CNPJ em toda busca; a lista continua de onde parou.
3. **Propostas abertas:** fotografia completa das licitações com prazo aberto (~600 páginas). Não cabe numa
   busca: continua da página em que parou na busca seguinte e, terminada, é refeita a cada 7 dias.
4. **PCA** (planos de contratação 2026/2027): classes de TIC, uma vez por semana.
5. **Carga histórica:** avança alguns dias por busca até cobrir 12 meses.
6. **Itens e documentos oficiais** das oportunidades relevantes (edital, TR etc.), começando pelas propostas
   abertas de **maior valor**.
7. **Classificação**, gravação na base e publicação do site.

**Edital com objeto genérico de TI.** Quando o objeto não cita nenhum termo da base de ofertas, mas fala em
"equipamentos de informática", "solução de TIC", "data center" etc. (lista em `config/fontes.yml`), o edital
entra como **candidato** se valer R$ 1 mi ou mais (ou R$ 100 mil, nos órgãos relevantes). Os itens são
coletados e a classificação decide: só aparece no site se os itens casarem com a base. Caso que motivou a
regra: Pregão 131/2026 da Embrapa (R$ 91 mi), com os switches só nos itens.

**Link de cada oportunidade:** o detalhe tem o botão **Copiar link** (`#/oportunidades?id=<id>`). O link abre
direto o detalhe e exige login, como o resto do site; se a oportunidade já venceu, o Radar avisa.

## Login e o que é de cada um

- Cada pessoa entra com **usuário e senha**. No primeiro acesso (e depois de uma redefinição) o site pede para criar uma senha pessoal.
- **Seus:** favoritos (estrela), filtro Tudo/Logo/MVS, filtros, ordenação e buscas salvas. Ninguém mais vê.
- **Seu CRM:** cada vendedor tem o próprio funil. No detalhe da oportunidade, **Salvar no meu CRM** e depois: etapa
  (Novo, Qualificando, Proposta, Negociação, Ganho, Perdido, Descartado), próximo acompanhamento, **código da oportunidade / SC**,
  valor do negócio, parceiro, motivo da perda, observação e um histórico com notas (cada mudança fica registrada).
  O menu **CRM** mostra os **acompanhamentos de hoje** (e os atrasados), os próximos 7 dias, os pedidos do gestor e o funil;
  exporta CSV. O número vermelho no menu = acompanhamentos de hoje + pedidos não vistos.
- **Gestor (master):** vê o CRM de todos, filtra por vendedor (tabela "Equipe" com abertos, atrasados, propostas, ganhos e
  valor) e, no detalhe, **pede para um vendedor olhar** a oportunidade, com mensagem e data. O vendedor vê o pedido no CRM.
- **Da equipe:** órgãos prioritários e parceiros (configuração comercial).
- **Administrador:** menu **Usuários** para criar usuário, escolher o papel (vendedor, gestor ou administrador), redefinir
  senha, **ver a senha temporária** de quem ainda não entrou (fica guardada criptografada até a pessoa criar a própria
  senha), desativar/reativar e enviar nova versão da base de ofertas, dos atestados e dos territórios.

## Atestados, territórios e região

- **Atestados:** cada oportunidade TLS é comparada com a base privada de atestados de capacidade técnica. **Atende** = o
  texto publicado pede o que o atestado comprova (ex.: tecnologia + serviço no mesmo texto); **Próximo** = cobre parte
  (mesma tecnologia sem o serviço, ou o serviço com outra marca). Filtro **Atestados** em Oportunidades e Atas; o detalhe
  lista quais atestados casaram e por quais termos. Validação humana sempre (o edital manda).
- **Territórios:** o órgão é procurado na carteira de clientes (por CNPJ ou pelo nome, desempatando pela UF) e recebe o
  vendedor BSB e o de renovação. Filtro **Território (vendedor)**, com "Meu território" quando o nome do login bate com o
  da carteira, e "Fora da carteira". Os órgãos públicos da carteira com CNPJ encontrado entram na varredura por órgão.
- **Região:** Nacional (padrão), DF + órgãos federais, Norte, Nordeste, Centro-Oeste, Sudeste ou Sul.
- As duas bases ficam só no banco protegido (nunca no GitHub nem no site público); quem tem login vê só o resultado.

## Como um registro é classificado

Regras do bloco `regras_de_match` da base de ofertas (rev. c):

- Comparação sem acento e sem maiúsculas, por **palavra inteira** ("Cisco" não casa com "Francisco"; "HP" não casa com "HPC").
- **Oferta:** casa se aparece um **termo exato** dela, ou uma **marca + um termo de serviço** dela no mesmo texto
  (objeto, item ou PCA). Termo de "excluir" da oferta impede o casamento.
- **Família (caminho sem marca):** se nenhuma oferta casou, uma das 8 famílias casa quando aparecem um **termo de
  categoria + um termo de serviço** dela no mesmo texto (ex.: "manutenção de switches e roteadores" → Networking).
  A oportunidade entra com a família, sem oferta específica.
- **Nota de aderência (0–100), modelo da versão anterior do Radar** (parâmetros no bloco `pontuacao` da base privada):
  - **aderência técnica:** portfólio (35) = força do casamento (termo exato 1,0 · marca + serviço 0,9 · só família 0,6)
    × prioridade da oferta principal (alta 1,0 · média 0,9 · baixa 0,75); suporte (25) por termos de suporte/manutenção
    (só aquisição vale 0,3); fabricante (15) se cita marca da aliança (outra marca vale 0,8); evidências (5);
  - **urgência comercial:** valor (10) e estágio (10), reduzidos quando a aderência técnica é baixa;
  - **tetos:** só família ≤ 69; com termo de exclusão global ≤ 45.
  - **Faixas:** 80+ **Alta prioridade** · 60–79 **Analisar** · 40–59 **Potencial indireto** · < 40 **Baixa aderência**.
    É a ordenação padrão das listas; filtro "Aderência mínima" (80+/60+/40+).
  - No detalhe: aderência técnica / urgência comercial, relação com o TLS (direta = suporte/manutenção/subscrição;
    indireta = só aquisição, via parceiro) e uma frase de justificativa feita só com os termos encontrados.
- **Família principal:** a da oferta de maior peso; empate → a família de menor ordem.
- **Exclusões globais** (notebook, Power BI, impressora…) não descartam: limitam a nota a 45 e geram o selo
  **"possível falso positivo"** (um edital pode ter lote de notebook e lote de switch).
- **Portfólio:** Logo IBM, MVS, **Logo IBM + MVS** (aparece nos dois filtros) ou Transversal (só em "Tudo"). Pelo caminho
  de família: Suporte IBM → Logo; as demais → MVS; marca citada no texto acrescenta o portfólio da marca.
- **No card:** aderência, família principal (até 2), portfólio e selos de alerta. **No detalhe ("Por que apareceu"):** as
  ofertas casadas pelo nome e os termos que deram match (ou a família e seus termos).
- **Painel "Oportunidades por família"** no Dashboard: quantidade e valor por família; clique filtra a lista; passe o mouse
  para ver as 3 ofertas mais frequentes.
- **Item de PCA é avaliado como um texto só** (ficha técnica + classe/descrição): um "excluir" de um lado vale para o outro
  (ex.: classe "SWITCH" com ficha "TIPO: NÃO GERENCIÁVEL" não entra). Contratação, ata e contrato continuam item a item,
  para que um lote de notebook não derrube o lote de switch do mesmo edital.
- **Valor mínimo (filtro pessoal):** atalhos de R$ 10 mil a R$ 1 mi ou valor digitado; usa o valor do card (estimado, ou
  homologado sem estimado; na ata, o valor da contratação). Registro sem valor continua aparecendo, a menos que você
  marque "Ocultar sem valor". Vale para a lista, os contadores Tudo/Logo/MVS e o painel por família.
- **Valor estimado agregado:** contratações + itens de PCA, **sem duplicidade** (o mesmo item nos planos de 2026 e 2027 e
  o edital republicado contam uma vez). Atas e contratos não entram (são a mesma demanda já contada).

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

**Aparece** quando casa ao menos uma oferta ou família da base de ofertas e não está vencido.

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
