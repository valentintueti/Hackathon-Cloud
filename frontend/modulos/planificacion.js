(() => {
  const NIVELES = [['alto', 'Alto'], ['medio', 'Medio'], ['bajo', 'Bajo']];
  const FACTORES = { patrones: 'Patrones de falla', preventivo: 'Preventivo', salud: 'Salud', historial: 'Historial' };
  let raiz;
  let datos = null;

  function montar(nodo) {
    raiz = nodo;
    raiz.innerHTML = `
      <p class="nota">Puntaje de riesgo de falla (0 a 100) según patrones del historial, avance del preventivo, salud y fallas recientes.</p>
      <form class="filtros" data-filtros>
        <label>Nivel <select name="nivel">${opciones(NIVELES, '', 'Todos')}</select></label>
        <label>Zona <select name="zona" data-zona><option value="">Todas</option></select></label>
        <button type="submit">Aplicar</button>
      </form>
      <div data-lista></div>`;
    const form = raiz.querySelector('[data-filtros]');
    form.addEventListener('submit', evento => {
      evento.preventDefault();
      actualizar();
    });
    form.elements.nivel.addEventListener('change', actualizar);
    form.elements.zona.addEventListener('change', () => {
      if (datos) raiz.querySelector('[data-lista]').innerHTML = vista();
    });
  }

  function tarjeta(m, indice) {
    const puntaje = Math.max(0, Math.min(100, Number(m.puntaje) || 0));
    const factores = Object.entries(m.factores || {});
    const patrones = m.patrones_presentes || [];
    return `<article class="tarjeta nivel-${esc(m.nivel)}">
      <header class="tarjeta-cabecera"><span class="rango">#${indice + 1}</span><strong>${esc(m.maquina_id)}</strong>${insignia(m.nivel, `nivel-${m.nivel}`)}<time>${fecha(m.ts)}</time></header>
      <p>Zona ${esc(m.zona_id || '—')} · Modelo ${esc(m.modelo_id || '—')}</p>
      <div class="barra" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${puntaje}"><span style="width:${puntaje}%"></span></div>
      <p><strong>${numero(m.puntaje)}</strong> / 100</p>
      ${factores.length ? `<div class="chips">${factores.map(([clave, valor]) => `<span class="chip">${esc(FACTORES[clave] || clave)}: ${numero(valor)}</span>`).join('')}</div>` : ''}
      ${patrones.length ? `<p><strong>Patrones presentes:</strong></p><ul>${patrones.map(p => `<li>${esc(p.combinacion)} <span class="nota">(soporte ${numero(p.soporte, 0)}, lift ${numero(p.lift, 2)})</span></li>`).join('')}</ul>` : ''}
      ${m.niveles_hoy && m.niveles_hoy.length ? `<p><strong>Niveles de hoy:</strong></p>${chips(m.niveles_hoy)}` : ''}
      ${m.recomendacion ? `<div class="bloque-ia"><p>${autor(m.recomendado_por)} ${esc(m.recomendacion)}</p>${m.ajuste_modelo ? `<p class="nota"><strong>Ajuste para el modelo:</strong> ${esc(m.ajuste_modelo)}</p>` : ''}</div>` : ''}
    </article>`;
  }

  function vista() {
    const zona = raiz.querySelector('[data-zona]').value;
    const maquinas = (datos.maquinas || []).filter(m => !zona || m.zona_id === zona);
    const aviso = datos.sin_patrones_suficientes ? '<div class="aviso">Aún no hay patrones suficientes en el historial: por ahora el puntaje usa solo preventivo, salud e historial de fallas.</div>' : '';
    if (!maquinas.length) return aviso + vacio('No hay máquinas con esos filtros.');
    return `${aviso}<p class="meta">${numero(maquinas.length, 0)} máquina(s), de mayor a menor riesgo</p><div class="tarjetas">${maquinas.map(tarjeta).join('')}</div>`;
  }

  async function actualizar() {
    const form = raiz.querySelector('[data-filtros]');
    const nivel = form.elements.nivel.value;
    await llenar(raiz.querySelector('[data-lista]'), async () => {
      datos = await api('planificacion', '/planificacion/riesgo', { params: { nivel } });
      const zonaActual = form.elements.zona.value;
      const zonas = [...new Set((datos.maquinas || []).map(m => m.zona_id).filter(Boolean))].sort();
      form.elements.zona.innerHTML = opciones(zonas, zonaActual, 'Todas');
      return vista();
    });
  }

  registrarPestana({ id: 'planificacion', titulo: 'Planificación', modulo: 'planificacion', montar, actualizar });
})();
