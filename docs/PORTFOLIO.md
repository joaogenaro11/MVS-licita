# Portfólio TLS — base da taxonomia pública

A configuração pública (`config/portfolio_tls.yml`) contém **apenas** termos técnicos, nomes de fabricantes e
a cobertura que pode ser confirmada em **material público da IBM**. Regras comerciais internas (cobertura
validada internamente, prioridades de oferta, notas de escopo, contas prioritárias e parceiros) ficam na
**configuração privada**, fora do repositório: secret `RADAR_PRIVATE_CONFIG` e tabela `radar_config` no Supabase.

## Fontes públicas consultadas (nov/2026)

- IBM — Technology Lifecycle Services: https://www.ibm.com/services/technology-support
- IBM — Five Key Things to Know About IBM Technology Support Services: https://www.ibm.com/new/product-blog/five-key-things-to-know-about-ibm-technology-support-services
- IBM Support Services for Multivendor Server, Storage, Network and Security (PDF): https://www-api.ibm.com/adobe/assets/urn:aaid:aem:063f4151-07df-4507-a7fc-2c94bc99ccb3/original/as/IBM_Support_Services_for_Multivendor_Server_Storage_Network_and_Security_6.pdf
- IBM Technology Lifecycle Services — Infrastructure Services: https://www.ibm.com/support/pages/node/7167844

O que essas fontes indicam:

- Suporte multivendor a **servidores, storage, rede e segurança**, com ponto único de contato.
- Fabricantes de rede e segurança citados: Check Point, Cisco, F5, Juniper, Palo Alto Networks e Riverbed.
- Fabricantes de servidores e storage citados: Lenovo, NetApp, Oracle/Sun e Supermicro, além da IBM.
- Manutenção **durante e após a garantia**.

Na configuração pública, apenas esses fabricantes estão com `tls_coverage: confirmada`. Os demais estão como `validar`.

## Ofertas modeladas

| Chave | Oferta | Observação |
|---|---|---|
| `networking` | Networking | LAN/WAN/Wi-Fi, data center, campus, ambientes industriais, SD-WAN |
| `security` | Security | Firewalls, appliances, IPS, WAF, VPN, NAC |
| `datacenter` | Data Center | Servidores, storage, SAN, hiperconvergência, virtualização, mainframe, backup em fita |
| `mvs` | MVS — Multivendor | Suporte multifabricante, pós-garantia, extensão de vida útil |
| `hardware_refresh` | Hardware Refresh | Modernização ou expansão (em geral via parceiro licitante) |
| `software_terceiros` | Suporte de software de terceiros | Cobertura e alcance a confirmar caso a caso |
| `complementares` | Serviços complementares | Retenção de mídia, firmware assistido, infraestrutura física de DC |

## Como ajustar

1. Edite `config/portfolio_tls.yml` (termos `strong`/`medium`/`weak`, `neutralize`, `penalties`, `vendors`).
2. Rode `cd collector && python -m pytest -q`. Os testes incluem falsos positivos clássicos.
3. Faça commit. A próxima execução do workflow reclassifica toda a base.

Para mudar regras comerciais internas, altere o secret `RADAR_PRIVATE_CONFIG`, nunca o arquivo público.
