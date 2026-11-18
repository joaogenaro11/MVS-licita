// Endereço próprio de cada oportunidade: #/oportunidades?id=<id> (ou #/atas?id=<id> para atas).
// Abre direto o detalhe. O site inteiro exige login, então o link também exige.
export const hashId = (hash = window.location.hash) => new URLSearchParams(hash.split('?')[1] || '').get('id')

export const linkDe = (r, loc = window.location) =>
  `${loc.origin}${loc.pathname}#/${r.tipo === 'ata' ? 'atas' : 'oportunidades'}?id=${encodeURIComponent(r.id)}`
