(() => {
  const TIPOS = {
    reasignar: 'Reasignar máquinas',
    repartir_jornada: 'Repartir jornada',
    revisar_asignacion: 'Revisar asignación',
    revisar_operacion: 'Revisar operación',
  };
  const HALLAZGOS = {
    baja_utilizacion: 'Baja utilización',
    jornada_excesiva: 'Jornada excesiva',
    baja_productividad_alto_costo: 'Baja productividad y alto costo',
  };
  let raiz;

  function montar(nodo) {
    raiz = nodo;
    const looker = String((window.CONFIG || {}).lookerStudio || '').trim();
    raiz.innerHTML = `
      <form class="filtros" data-filtros>
        <label>Fecha <input name="fecha" type="date"></label>
        <button type="submit">Consultar</button>
      </form>
      <p class="nota">Sin fecha se muestra la recomendación de hoy o, si aún no existe, la de ayer.</p>
      <div data-contenido></div>
      ${looker ? `<h3>Informe de productividad</h3><iframe class="looker" src="${esc(looker)}" title="Informe de productividad en Looker Studio" loading="lazy" allowfullscreen sandbox="allow-storage-access-by-user-activation allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"></iframe>` : ''}`;
    alFiltrar(raiz.querySelector('[data-filtros]'), actualizar);
  }

  function vistaAcciones(acciones) {
    if (!acciones.length) return vacio('No hay acciones sugeridas.');
    const grupos = {};
    acciones.forEach(a => { (grupos[a.tipo] = grupos[a.tipo] || []).push(a); });
    const orden = [...Object.keys(TIPOS), ...Object.keys(grupos).filter(t => !TIPOS[t])];
    return orden.filter(tipo => grupos[tipo]).map(tipo => `<section class="grupo-acciones">
      <h4>${esc(TIPOS[tipo] || tipo)} (${grupos[tipo].length})</h4>
      <ul>${grupos[tipo].map(a => `<li>${esc(a.detalle)}</li>`).join('')}</ul>
    </section>`).join('');
  }

  function vistaMaquinas(maquinas) {
    if (!maquinas.length) return vacio('No hay máquinas con hallazgos.');
    return `<div class="tabla-scroll"><table><thead><tr>
      <th>Máquina</th><th>Modelo</th><th>Zona</th><th>Utilización</th><th>Horas/día</th><th>Días excesivos</th><th>Ralentí</th><th>Costo total</th><th>Costo h/t</th><th>Hallazgos</th>
    </tr></thead><tbody>${maquinas.map(m => `<tr>
      <td><strong>${esc(m.maquina_id)}</strong></td><td>${esc(m.modelo_id || '—')}</td><td>${esc(m.zona_id || '—')}</td>
      <td class="num">${porcentaje(m.utilizacion_pct)}</td><td class="num">${numero(m.horas_promedio, 2)}</td><td class="num">${numero(m.dias_excesivos, 0)}</td>
      <td class="num">${porcentaje(m.ralenti_pct)}</td><td class="num">${numero(m.costo_total, 2)}</td><td class="num">${numero(m.costo_hora_por_t, 3)}</td>
      <td>${chips((m.hallazgos || []).map(h => HALLAZGOS[h] || h))}</td>
    </tr>`).join('')}</tbody></table></div>`;
  }

  async function actualizar() {
    const params = filtrosDe(raiz.querySelector('[data-filtros]'));
    await llenar(raiz.querySelector('[data-contenido]'), async () => {
      let r;
      try {
        r = await api('productividad', '/productividad/recomendaciones', { params });
      } catch (error) {
        if (error.estado === 404) return vacio(params.fecha ? 'Sin recomendaciones para esa fecha.' : 'Sin recomendaciones para hoy ni ayer.');
        throw error;
      }
      const recomendaciones = r.recomendaciones || [];
      return `
        <p class="meta">Recomendación del ${fecha(r.fecha)}</p>
        <div class="bloque-ia"><p>${autor(r.redactado_por)} <span class="texto">${esc(r.resumen || '')}</span></p>
          ${recomendaciones.length ? `<ul>${recomendaciones.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
        </div>
        <h3>Acciones sugeridas</h3>
        ${vistaAcciones(r.acciones || [])}
        <h3>Máquinas con hallazgos</h3>
        ${vistaMaquinas(r.maquinas || [])}`;
    });
  }

  registrarPestana({ id: 'productividad', titulo: 'Productividad', modulo: 'productividad', montar, actualizar });
})();
