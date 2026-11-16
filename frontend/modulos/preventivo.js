(() => {
  let raiz;

  function montar(nodo) {
    raiz = nodo;
    raiz.innerHTML = `
      <p class="nota">Órdenes creadas cuando el uso efectivo de una máquina se acerca a su intervalo de mantenimiento. Al completarla se reinicia el contador de la máquina.</p>
      <div data-lista></div>`;
    alHacerClic(raiz, 'completar', completar);
  }

  function tarjeta(o) {
    const pct = Number(o.porcentaje_intervalo) || 0;
    const claseBarra = pct >= 100 ? 'alta' : pct >= 90 ? 'media' : '';
    return `<article class="tarjeta borde-${esc(o.prioridad || 'ninguna')}">
      <header class="tarjeta-cabecera">${severidad(o.prioridad)}${insignia(o.estado)}<time>${fecha(o.ts_creada)}</time></header>
      <p><strong>Máquina:</strong> ${esc(o.maquina_id)}</p>
      <p><strong>Intervalo usado:</strong> ${porcentaje(o.porcentaje_intervalo)}${o.horas_efectivas !== undefined ? ` · ${numero(o.horas_efectivas)} h efectivas` : ''}</p>
      <div class="barra ${claseBarra}"><span style="width:${Math.min(100, Math.max(0, pct))}%"></span></div>
      <p class="id">ID: ${esc(o.orden_id)}</p>
      <div class="acciones"><button type="button" data-accion="completar" data-orden="${esc(o.orden_id)}" data-maquina="${esc(o.maquina_id)}">Completar</button></div>
      <p class="resultado"></p>
    </article>`;
  }

  async function completar(boton) {
    if (!window.confirm(`¿Marcar como completado el mantenimiento preventivo de ${boton.dataset.maquina}?`)) return;
    const exito = await ejecutar(boton, async () => {
      await api('preventivo', `/ordenes/${encodeURIComponent(boton.dataset.orden)}/completar`, { metodo: 'POST' });
      return `Mantenimiento de ${boton.dataset.maquina} completado`;
    });
    if (exito) actualizar();
  }

  async function actualizar() {
    await llenar(raiz.querySelector('[data-lista]'), async () => {
      const r = await api('nucleo', '/ordenes', { params: { tipo: 'preventivo', estado: 'abiertas', limite: 500 } });
      const ordenes = (r.ordenes || []).sort((a, b) => Number(b.porcentaje_intervalo || 0) - Number(a.porcentaje_intervalo || 0));
      if (!ordenes.length) return vacio('No hay mantenimientos preventivos pendientes.');
      return `<p class="meta">${numero(r.total, 0)} orden(es) abierta(s), ordenadas por intervalo usado</p><div class="tarjetas">${ordenes.map(tarjeta).join('')}</div>`;
    });
  }

  registrarPestana({ id: 'preventivo', titulo: 'Preventivo', modulo: 'preventivo', montar, actualizar });
})();
