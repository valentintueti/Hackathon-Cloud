(() => {
  const ORIGENES = [['anomalias', 'Anomalías'], ['inusual', 'Comportamiento inusual'], ['masivos', 'Eventos masivos'], ['combustible', 'Combustible']];
  const NOMBRE_ORIGEN = Object.fromEntries(ORIGENES);
  const SEVERIDADES = [['critica', 'Crítica'], ['alta', 'Alta'], ['media', 'Media'], ['baja', 'Baja']];
  const REFERENCIAS = { propio: 'Su propio historial', pares: 'Su modelo' };
  let raiz;

  function montar(nodo) {
    raiz = nodo;
    raiz.innerHTML = `
      <form class="filtros" data-filtros>
        <label>Origen <select name="origen">${opciones(ORIGENES, '', 'Todos')}</select></label>
        <label>Severidad <select name="severidad">${opciones(SEVERIDADES, '', 'Todas')}</select></label>
        <label>Estado <select name="estado">${opciones([['abierta', 'Abierta'], ['cerrada', 'Cerrada']], '', 'Todos')}</select></label>
        <label>Zona <input name="zona" placeholder="ID de zona"></label>
        <label>Máquina <input name="maquina" placeholder="ID de máquina"></label>
        <label>Desde <input name="desde" type="date"></label>
        <label>Límite <input name="limite" type="number" min="1" max="500" step="1" value="100"></label>
        <button type="submit">Aplicar</button>
      </form>
      <div data-lista></div>`;
    alFiltrar(raiz.querySelector('[data-filtros]'), actualizar);
  }

  function tablaDesvios(desvios) {
    return `<div class="tabla-scroll"><table class="compacta"><thead><tr><th>Variable</th><th>Valor</th><th>Comparado con</th><th>Media</th><th>z</th></tr></thead><tbody>${desvios.map(d => `<tr>
      <td>${esc(d.variable)}</td><td class="num">${numero(d.valor, 2)}</td><td>${esc(REFERENCIAS[d.referencia] || d.referencia)}</td>
      <td class="num">${numero(d.media, 2)}</td><td class="num">${numero(d.z, 2)}</td></tr>`).join('')}</tbody></table></div>`;
  }

  function tarjeta(a) {
    const partes = [`<header class="tarjeta-cabecera">${severidad(a.severidad)}${insignia(NOMBRE_ORIGEN[a.origen] || a.origen, 'origen')}<time>${fecha(a.ts)}</time></header>`];
    const maquinas = Array.isArray(a.maquinas_afectadas) && a.maquinas_afectadas.length
      ? `<strong>Máquinas afectadas:</strong> ${listaTexto(a.maquinas_afectadas)}`
      : `<strong>Máquina:</strong> ${esc(a.maquina_id || '—')}`;
    partes.push(`<p>${maquinas}${a.zona_id ? ` · <strong>Zona:</strong> ${esc(a.zona_id)}` : ''}</p>`);
    if (a.variables_afectadas && a.variables_afectadas.length) partes.push(`<p><strong>Variables afectadas:</strong> ${listaTexto(a.variables_afectadas)}</p>`);
    if (a.origen === 'anomalias' && a.puntaje !== undefined) partes.push(`<p><strong>Puntaje de anomalía:</strong> ${numero(a.puntaje)} / 100${a.tendencia_creciente ? ' · tendencia creciente' : ''}</p>`);
    if (a.descripcion) partes.push(`<p class="texto">${esc(a.descripcion)} ${autor(a.explicado_por)}</p>`);
    if (a.explicacion_ia) {
      const pasos = Array.isArray(a.revisar_primero_ia) && a.revisar_primero_ia.length
        ? `<p><strong>Revisar primero:</strong></p><ol>${a.revisar_primero_ia.map(p => `<li>${esc(p)}</li>`).join('')}</ol>` : '';
      partes.push(`<div class="bloque-ia"><p>${autor('gemini')} ${esc(a.explicacion_ia)}</p>${pasos}</div>`);
    }
    if (Array.isArray(a.desvios) && a.desvios.length) partes.push(tablaDesvios(a.desvios));
    if (Array.isArray(a.factores_comunes) && a.factores_comunes.length) partes.push(`<p><strong>Factores comunes:</strong> ${listaTexto(a.factores_comunes)}</p>`);
    if (Array.isArray(a.casos) && a.casos.length) partes.push(`<p><strong>Casos:</strong> ${a.casos.map(c => insignia(c)).join(' ')}</p>`);
    return `<article class="tarjeta borde-${esc(a.severidad || 'ninguna')}">${partes.join('')}</article>`;
  }

  async function actualizar() {
    const params = filtrosDe(raiz.querySelector('[data-filtros]'));
    await llenar(raiz.querySelector('[data-lista]'), async () => {
      const r = await api('nucleo', '/alertas', { params });
      const alertas = r.alertas || [];
      if (!alertas.length) return vacio('No hay alertas con esos filtros.');
      return `<p class="meta">Mostrando ${numero(r.cantidad, 0)} de ${numero(r.total, 0)} alerta(s), las más recientes primero</p><div class="tarjetas">${alertas.map(tarjeta).join('')}</div>`;
    });
  }

  registrarPestana({ id: 'alertas', titulo: 'Alertas', modulo: 'nucleo', montar, actualizar });
})();
