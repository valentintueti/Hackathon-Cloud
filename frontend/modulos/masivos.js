(() => {
  const TIPOS_FACTOR = { modelo: 'Mismo modelo', lote_combustible: 'Mismo lote de combustible', componente: 'Componente reemplazado', variable: 'Variable alterada' };
  let raiz;

  function montar(nodo) {
    raiz = nodo;
    raiz.innerHTML = `
      <p class="nota">Un evento masivo agrupa varias máquinas de una misma zona con alertas al mismo tiempo y busca qué tienen en común.</p>
      <form class="filtros" data-filtros>
        <label>Zona <input name="zona" placeholder="ID de zona"></label>
        <label>Estado <select name="estado">${opciones([['abierto', 'Abierto'], ['cerrado', 'Cerrado']], 'abierto', 'Todos')}</select></label>
        <button type="submit">Aplicar</button>
      </form>
      <div data-lista></div>`;
    alFiltrar(raiz.querySelector('[data-filtros]'), actualizar);
  }

  function tarjeta(e) {
    const abierto = e.estado === 'abierto';
    const factores = e.factores || [];
    const condiciones = e.condiciones_zona || {};
    const tablaFactores = factores.length ? `<div class="tabla-scroll"><table class="compacta"><thead><tr><th>Factor común</th><th>Valor</th><th>Máquinas</th></tr></thead><tbody>${factores.map(f => `<tr>
      <td>${esc(TIPOS_FACTOR[f.tipo] || f.tipo)}</td><td>${esc(f.valor)}</td><td class="num" title="${esc((f.maquinas || []).join(', '))}">${numero(f.cantidad, 0)}</td>
    </tr>`).join('')}</tbody></table></div>` : '<p class="nota">No se encontró un factor común.</p>';
    return `<article class="tarjeta ${abierto ? 'borde-alta' : ''}">
      <header class="tarjeta-cabecera"><strong>Zona ${esc(e.zona_id)}</strong>${insignia(abierto ? 'Abierto' : 'Cerrado', abierto ? 'sev-alta' : '')}</header>
      <p><strong>Inicio:</strong> ${fecha(e.inicio)}${e.ts_cierre ? ` · <strong>Cierre:</strong> ${fecha(e.ts_cierre)}` : ''}</p>
      <p><strong>Máquinas (${(e.maquinas || []).length}):</strong> ${listaTexto(e.maquinas)}</p>
      ${tablaFactores}
      ${condiciones.tipo_terreno || condiciones.clima_actual ? `<p><strong>Condiciones de la zona:</strong> terreno ${esc(condiciones.tipo_terreno || '—')}, clima ${esc(condiciones.clima_actual || '—')}</p>` : ''}
      ${e.descripcion ? `<p class="texto">${esc(e.descripcion)}</p>` : ''}
    </article>`;
  }

  async function actualizar() {
    const params = filtrosDe(raiz.querySelector('[data-filtros]'));
    await llenar(raiz.querySelector('[data-lista]'), async () => {
      const r = await api('masivos', '/masivos/eventos', { params });
      const eventos = r.eventos || [];
      if (!eventos.length) return vacio('No hay eventos masivos con esos filtros.');
      return `<p class="meta">${numero(r.cantidad, 0)} evento(s)</p><div class="tarjetas">${eventos.map(tarjeta).join('')}</div>`;
    });
  }

  registrarPestana({ id: 'masivos', titulo: 'Eventos masivos', modulo: 'masivos', montar, actualizar });
})();
