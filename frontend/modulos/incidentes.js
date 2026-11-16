(() => {
  const SEVERIDADES = [['baja', 'Baja'], ['media', 'Media'], ['alta', 'Alta'], ['critica', 'Crítica']];
  const SIGUIENTE = { pendiente: 'asignada', asignada: 'en_atencion', en_atencion: 'hecha' };
  const NOMBRE_ESTADO = { pendiente: 'Pendiente', asignada: 'Asignada', en_atencion: 'En atención', hecha: 'Hecha' };
  let raiz;
  let componentes = null;
  let avisoComponentes = '';

  function montar(nodo) {
    raiz = nodo;
    raiz.innerHTML = `
      <details class="panel">
        <summary>Reportar incidente</summary>
        <form class="formulario" data-nuevo>
          <div class="fila">
            <label>Máquina * <input name="maquina_id" required></label>
            <label>Severidad * <select name="severidad" required>${opciones(SEVERIDADES, 'media')}</select></label>
            <label>Categoría <input name="categoria" placeholder="motor, hidráulica, eléctrica…"></label>
          </div>
          <label>Descripción * <textarea name="descripcion" rows="3" required></textarea></label>
          <div class="acciones"><button type="submit">Registrar incidente</button></div>
          <p class="resultado"></p>
        </form>
      </details>
      <h3>Incidentes abiertos</h3>
      <div data-lista></div>
      <h3>Historial de una máquina</h3>
      <form class="filtros" data-historial>
        <label>Máquina * <input name="maquina_id" required></label>
        <button type="submit">Ver historial</button>
      </form>
      <div data-historial-salida></div>`;

    enviarFormulario(raiz.querySelector('[data-nuevo]'), async (datos, form) => {
      const orden = await api('historial', '/historial/incidentes', { metodo: 'POST', cuerpo: sinVacios(datos) });
      form.reset();
      cargarLista();
      return `Incidente registrado (${orden.orden_id})${orden.reincidente_de ? '. Se detectó una reincidencia.' : ''}`;
    });

    raiz.querySelector('[data-historial]').addEventListener('submit', evento => {
      evento.preventDefault();
      const maquina = evento.target.elements.maquina_id.value.trim();
      if (maquina) verHistorial(maquina);
    });

    alHacerClic(raiz, 'ver-historial', boton => {
      const form = raiz.querySelector('[data-historial]');
      form.elements.maquina_id.value = boton.dataset.maquina;
      verHistorial(boton.dataset.maquina);
      form.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    alHacerClic(raiz, 'agregar-componente', boton => {
      boton.previousElementSibling.insertAdjacentHTML('beforeend', filaComponente());
    });
    alHacerClic(raiz, 'quitar-componente', boton => boton.closest('.fila-componente').remove());
  }

  async function cargarComponentes() {
    if (!configurado('repuestos')) {
      componentes = null;
      avisoComponentes = 'El módulo de repuestos no está configurado: no se pueden registrar componentes reemplazados.';
      return;
    }
    try {
      componentes = (await api('repuestos', '/repuestos/componentes')).componentes || [];
      avisoComponentes = componentes.length ? '' : 'El catálogo de componentes está vacío. Regístralos en la pestaña Repuestos.';
    } catch (error) {
      componentes = null;
      avisoComponentes = `No se pudo cargar el catálogo de componentes: ${error.message}`;
    }
  }

  function filaComponente() {
    const lista = componentes.map(c => [c.componente_id, `${c.nombre || c.componente_id} (${c.componente_id})`]);
    return `<div class="fila-componente">
      <select required aria-label="Componente">${opciones([['', 'Elige un componente'], ...lista])}</select>
      <input type="number" min="1" step="1" value="1" required aria-label="Cantidad">
      <button type="button" class="secundario" data-accion="quitar-componente" aria-label="Quitar componente">✕</button>
    </div>`;
  }

  function formularioAvance(o, siguiente) {
    let campos = '';
    if (siguiente === 'asignada' || siguiente === 'en_atencion') {
      campos += `<label>Técnico <input name="tecnico_id" value="${esc(o.tecnico_id || '')}" placeholder="ID del técnico"></label>`;
    }
    if (siguiente === 'en_atencion') campos += '<label>Observaciones <input name="observaciones"></label>';
    if (siguiente === 'hecha') {
      const bloqueComponentes = componentes && componentes.length
        ? '<div data-filas-componentes></div><button type="button" class="secundario" data-accion="agregar-componente">Agregar componente</button>'
        : `<p class="nota">${esc(avisoComponentes)}</p>`;
      campos += `
        <label>Causa raíz * <input name="causa_raiz" required></label>
        <label>Trabajo realizado * <textarea name="trabajo_realizado" rows="2" required></textarea></label>
        <fieldset><legend>Componentes reemplazados</legend>${bloqueComponentes}</fieldset>
        <label>Observaciones <input name="observaciones"></label>`;
    }
    return `<form class="avance" data-avance data-orden="${esc(o.orden_id)}" data-siguiente="${siguiente}">
      ${campos}
      <div class="acciones"><button type="submit">Pasar a «${NOMBRE_ESTADO[siguiente]}»</button></div>
      <p class="resultado"></p>
    </form>`;
  }

  function tarjeta(o) {
    const siguiente = SIGUIENTE[o.estado];
    return `<article class="tarjeta borde-${esc(o.severidad || 'ninguna')}">
      <header class="tarjeta-cabecera">${severidad(o.severidad)}${insignia(NOMBRE_ESTADO[o.estado] || o.estado)}<time>${fecha(o.ts_creada)}</time></header>
      <p><strong>Máquina:</strong> ${esc(o.maquina_id)} · <strong>Categoría:</strong> ${esc(o.categoria || '—')} · <strong>Origen:</strong> ${esc(o.origen || '—')}</p>
      <p class="texto">${esc(o.descripcion || '')}</p>
      ${o.reincidente_de ? `<p class="nota">Reincidencia del incidente ${esc(o.reincidente_de)}</p>` : ''}
      ${o.tecnico_id ? `<p><strong>Técnico:</strong> ${esc(o.tecnico_id)}</p>` : ''}
      <p class="id">ID: ${esc(o.orden_id)}</p>
      ${siguiente ? formularioAvance(o, siguiente) : ''}
      <div class="acciones" style="margin-top:.5rem"><button type="button" class="secundario" data-accion="ver-historial" data-maquina="${esc(o.maquina_id)}">Ver historial de la máquina</button></div>
    </article>`;
  }

  async function avanzar(datos, form) {
    const siguiente = form.dataset.siguiente;
    const cuerpo = { estado: siguiente };
    ['tecnico_id', 'causa_raiz', 'trabajo_realizado', 'observaciones'].forEach(campo => {
      if (datos[campo]) cuerpo[campo] = datos[campo];
    });
    const filas = [...form.querySelectorAll('.fila-componente')].map(fila => ({
      componente: fila.querySelector('select').value,
      cantidad: parseInt(fila.querySelector('input').value, 10),
    }));
    if (filas.length) {
      if (filas.some(f => !f.componente || !(f.cantidad > 0))) throw new Error('Cada componente necesita un repuesto del catálogo y una cantidad mayor a 0');
      cuerpo.componentes_reemplazados = filas;
    }
    await api('historial', `/historial/incidentes/${encodeURIComponent(form.dataset.orden)}/estado`, { metodo: 'POST', cuerpo });
    return `Incidente pasado a «${NOMBRE_ESTADO[siguiente]}»`;
  }

  async function cargarLista() {
    const lista = raiz.querySelector('[data-lista]');
    await llenar(lista, async () => {
      const r = await api('nucleo', '/ordenes', { params: { tipo: 'correctivo', estado: 'abiertas', limite: 500 } });
      const ordenes = r.ordenes || [];
      if (!ordenes.length) return vacio('No hay incidentes abiertos.');
      return `<p class="meta">${numero(r.total, 0)} incidente(s) abierto(s)</p><div class="tarjetas">${ordenes.map(tarjeta).join('')}</div>`;
    });
    lista.querySelectorAll('form[data-avance]').forEach(form => enviarFormulario(form, avanzar, { alTerminar: cargarLista }));
  }

  function vistaHistorial(r) {
    const s = r.resumen || {};
    const componentesTop = (s.componentes_mas_reemplazados || []).map(([c, n]) => `${esc(c)} (${numero(n, 0)})`).join(', ') || '—';
    const ia = r.ultimo_resumen_ia;
    const incidentes = r.incidentes || [];
    const bloqueIa = ia ? `<div class="bloque-ia">
      <p><strong>Último resumen</strong> ${autor(ia.resumen_por)} <span class="nota">${fecha(ia.ts_completada)}</span></p>
      <p class="texto">${esc(ia.resumen_ia || '')}</p>
      ${Array.isArray(ia.acciones_ia) && ia.acciones_ia.length ? `<ul>${ia.acciones_ia.map(a => `<li>${esc(a)}</li>`).join('')}</ul>` : ''}
    </div>` : '';
    const tabla = incidentes.length ? `<div class="tabla-scroll"><table><thead><tr>
      <th>Fecha</th><th>Tipo</th><th>Estado</th><th>Severidad</th><th>Descripción</th><th>Causa raíz</th><th>Detenido</th><th>Componentes</th>
    </tr></thead><tbody>${incidentes.map(o => `<tr>
      <td>${fecha(o.ts_creada)}</td>
      <td>${esc(o.tipo || 'correctivo')}</td>
      <td>${esc(NOMBRE_ESTADO[o.estado] || o.estado)}</td>
      <td>${severidad(o.severidad || o.prioridad)}</td>
      <td>${esc(o.descripcion || '—')}</td>
      <td>${esc(o.causa_raiz || '—')}</td>
      <td class="num">${o.tiempo_detenido_min !== undefined && o.tiempo_detenido_min !== null ? `${numero(o.tiempo_detenido_min)} min` : '—'}</td>
      <td>${(o.componentes_reemplazados || []).map(c => `${esc(c.componente)} ×${numero(c.cantidad, 0)}`).join(', ') || '—'}</td>
    </tr>`).join('')}</tbody></table></div>` : vacio('Esta máquina no tiene órdenes registradas.');
    return `<p class="meta">Máquina ${esc(r.maquina_id)}</p>
      <div class="contadores">
        ${contador(numero(s.incidentes_correctivos, 0), 'Correctivos')}
        ${contador(numero(s.mantenimientos_preventivos, 0), 'Preventivos')}
        ${contador(numero(s.abiertos, 0), 'Abiertos')}
        ${contador(s.mttr_min !== null && s.mttr_min !== undefined ? `${numero(s.mttr_min)} min` : '—', 'MTTR')}
        ${contador(numero(s.reincidencias, 0), 'Reincidencias')}
        ${contador(`${numero(s.tiempo_detenido_total_min)} min`, 'Tiempo detenido')}
      </div>
      <p><strong>Componentes más reemplazados:</strong> ${componentesTop}</p>
      ${bloqueIa}
      ${tabla}`;
  }

  async function verHistorial(maquina) {
    await llenar(raiz.querySelector('[data-historial-salida]'), async () => {
      const r = await api('historial', `/historial/maquinas/${encodeURIComponent(maquina)}`);
      return vistaHistorial(r);
    });
  }

  async function actualizar() {
    await cargarComponentes();
    await cargarLista();
  }

  registrarPestana({ id: 'incidentes', titulo: 'Incidentes', modulo: 'historial', montar, actualizar });
})();
