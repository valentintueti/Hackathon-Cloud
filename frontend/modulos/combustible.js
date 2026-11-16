(() => {
  const CASOS = { propio: 'Sobre su propio historial', modelo: 'Sobre su modelo', tendencia: 'Tendencia al alza' };
  let raiz;

  function montar(nodo) {
    raiz = nodo;
    raiz.innerHTML = `
      <p class="nota">Consumo de combustible del día anterior comparado con el historial de cada máquina, con las demás de su modelo y con su tendencia.</p>
      <form class="filtros" data-filtros>
        <label>Zona <input name="zona" placeholder="ID de zona"></label>
        <label>Máquina <input name="maquina" placeholder="ID de máquina"></label>
        <label>Severidad <select name="severidad">${opciones([['alta', 'Alta'], ['media', 'Media']], '', 'Todas')}</select></label>
        <label>Límite <input name="limite" type="number" min="1" max="500" step="1" value="100"></label>
        <button type="submit">Aplicar</button>
      </form>
      <div data-lista></div>`;
    alFiltrar(raiz.querySelector('[data-filtros]'), actualizar);
  }

  function metrica(etiqueta, valorHtml) {
    return `<div class="metrica"><span>${esc(etiqueta)}</span><strong>${valorHtml}</strong></div>`;
  }

  function tarjeta(a) {
    const m = a.metricas || {};
    const unidad = m.unidad ? ` ${esc(m.unidad)}` : '';
    return `<article class="tarjeta borde-${esc(a.severidad || 'ninguna')}">
      <header class="tarjeta-cabecera">${severidad(a.severidad)}<strong>${esc(a.maquina_id)}</strong><time>${fecha(a.ts)}</time></header>
      <p>Zona ${esc(a.zona_id || '—')} · Modelo ${esc(a.modelo_id || '—')}</p>
      <div class="chips">${(a.casos || []).map(c => insignia(CASOS[c] || c, 'sev-media')).join('')}</div>
      <div class="metricas">
        ${metrica('Consumo de ayer', numero(m.consumo_ayer, 2) + unidad)}
        ${metrica('Media propia', numero(m.media_propia, 2) + unidad)}
        ${metrica('Sobre su media', porcentaje(m.pct_propio, true))}
        ${metrica('Sobre su modelo', porcentaje(m.pct_modelo, true))}
        ${metrica('Tendencia diaria', `${numero(m.pendiente_diaria, 3)}${unidad}/día`)}
      </div>
      ${a.descripcion ? `<p class="texto">${autor(a.explicado_por)} ${esc(a.descripcion)}</p>` : ''}
    </article>`;
  }

  async function actualizar() {
    const params = { ...filtrosDe(raiz.querySelector('[data-filtros]')), origen: 'combustible' };
    await llenar(raiz.querySelector('[data-lista]'), async () => {
      const r = await api('nucleo', '/alertas', { params });
      const alertas = r.alertas || [];
      if (!alertas.length) return vacio('No hay alertas de combustible con esos filtros.');
      return `<p class="meta">Mostrando ${numero(r.cantidad, 0)} de ${numero(r.total, 0)} alerta(s)</p><div class="tarjetas">${alertas.map(tarjeta).join('')}</div>`;
    });
  }

  registrarPestana({ id: 'combustible', titulo: 'Combustible', modulo: 'nucleo', montar, actualizar });
})();
