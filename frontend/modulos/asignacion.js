(() => {
  const ESTADOS_ASIGNACION = [['pendiente', 'Pendiente'], ['aceptada', 'Aceptada'], ['rechazada', 'Rechazada'], ['vencida', 'Vencida'], ['fallida', 'Fallida'], ['completada', 'Completada']];
  const ESTADOS_TECNICO = [['disponible', 'Disponible'], ['reservado', 'Reservado'], ['ocupado', 'Ocupado']];
  const MINUTOS_RESPUESTA = 15;
  let raiz;
  let tecnicos = [];

  function montar(nodo) {
    raiz = nodo;
    raiz.innerHTML = `
      <h3>Asignaciones</h3>
      <p class="nota">Cada orden se propone al técnico con mejor puntaje. Tiene ${MINUTOS_RESPUESTA} minutos para aceptar o rechazar; si no responde o rechaza, se pasa al siguiente candidato y, si no queda ninguno, se avisa al jefe de mantenimiento.</p>
      <form class="filtros" data-filtro-asignaciones>
        <label>Orden <input name="orden" placeholder="ID de orden"></label>
        <label>Técnico <input name="tecnico" placeholder="ID de técnico"></label>
        <label>Estado <select name="estado">${opciones(ESTADOS_ASIGNACION, '', 'Todos')}</select></label>
        <button type="submit">Aplicar</button>
      </form>
      <div data-asignaciones></div>

      <h3>Técnicos</h3>
      <form class="filtros" data-filtro-tecnicos>
        <label>Zona <input name="zona" placeholder="ID de zona"></label>
        <label>Estado <select name="estado">${opciones(ESTADOS_TECNICO, '', 'Todos')}</select></label>
        <button type="submit">Aplicar</button>
      </form>
      <div data-tecnicos></div>

      <div class="dos-columnas">
        <details class="panel">
          <summary>Registrar o actualizar técnico</summary>
          <form class="formulario" data-tecnico>
            <div class="fila">
              <label>ID del técnico <input name="tecnico_id" placeholder="Vacío para crear uno nuevo"></label>
              <label>Nombre * <input name="nombre" required></label>
            </div>
            <label>Contacto <input name="contacto" placeholder="correo@empresa.com o +51…"></label>
            <div class="fila">
              <label>Especialidades * <input name="especialidades" required placeholder="motor, hidráulica"></label>
              <label>Zona * <input name="zona_id" required></label>
            </div>
            <div class="fila">
              <label>Latitud <input name="lat" type="number" step="any" min="-90" max="90"></label>
              <label>Longitud <input name="lon" type="number" step="any" min="-180" max="180"></label>
            </div>
            <p class="nota">Si indicas un correo, llegará un mensaje de confirmación de AWS SNS que el técnico debe aceptar para recibir avisos.</p>
            <div class="acciones"><button type="submit">Guardar técnico</button></div>
            <p class="resultado"></p>
          </form>
        </details>
        <details class="panel">
          <summary>Suscribir jefe de mantenimiento</summary>
          <form class="formulario" data-jefe>
            <p class="nota">El jefe recibe un aviso cuando una orden se queda sin técnico disponible y requiere asignación manual.</p>
            <label>Contacto * <input name="contacto" required placeholder="correo@empresa.com o +51…"></label>
            <p class="nota">Si es un correo, llegará un mensaje de confirmación de AWS SNS que hay que aceptar.</p>
            <div class="acciones"><button type="submit">Suscribir</button></div>
            <p class="resultado"></p>
          </form>
        </details>
      </div>`;

    alFiltrar(raiz.querySelector('[data-filtro-asignaciones]'), cargarAsignaciones);
    alFiltrar(raiz.querySelector('[data-filtro-tecnicos]'), cargarTecnicos);
    enviarFormulario(raiz.querySelector('[data-tecnico]'), guardarTecnico);
    enviarFormulario(raiz.querySelector('[data-jefe]'), suscribirJefe);
    alHacerClic(raiz, 'responder', responder);
  }

  function nombreTecnico(id) {
    const tecnico = tecnicos.find(t => t.tecnico_id === id);
    return tecnico && tecnico.nombre ? `${tecnico.nombre} (${id})` : id;
  }

  function plazo(a) {
    const base = aFecha(a.ts_aviso || a.ts_creada);
    if (!base) return '';
    const limite = new Date(base.getTime() + MINUTOS_RESPUESTA * 60000);
    return limite < new Date()
      ? `<p class="nota">Ya pasaron los ${MINUTOS_RESPUESTA} minutos; es probable que la asignación haya vencido.</p>`
      : `<p class="nota">Responder antes de las ${hora(limite)}.</p>`;
  }

  function tarjeta(a) {
    const pendiente = a.estado === 'pendiente';
    return `<article class="tarjeta">
      <header class="tarjeta-cabecera">${insignia(a.estado, `asig-${a.estado}`)}${severidad(a.gravedad)}<time>${fecha(a.ts_creada)}</time></header>
      <p><strong>Técnico:</strong> ${esc(nombreTecnico(a.tecnico_id))}</p>
      <p><strong>Orden:</strong> <span class="id">${esc(a.orden_id)}</span>${a.maquina_id ? ` · <strong>Máquina:</strong> ${esc(a.maquina_id)}` : ''}</p>
      <p><strong>Puntaje:</strong> ${numero(a.puntaje, 2)}</p>
      ${a.justificacion ? `<p class="texto nota">${esc(a.justificacion)}</p>` : ''}
      ${a.motivo ? `<p><strong>Motivo:</strong> ${esc(a.motivo)}</p>` : ''}
      ${pendiente ? `${plazo(a)}
        <label>Motivo <input data-motivo placeholder="Obligatorio si rechazas"></label>
        <div class="acciones" style="margin-top:.5rem">
          <button type="button" data-accion="responder" data-acepta="si" data-id="${esc(a.asignacion_id)}">Aceptar</button>
          <button type="button" class="peligro" data-accion="responder" data-acepta="no" data-id="${esc(a.asignacion_id)}">Rechazar</button>
        </div>
        <p class="resultado"></p>` : ''}
    </article>`;
  }

  async function responder(boton) {
    const tarjetaNodo = boton.closest('.tarjeta');
    const motivo = tarjetaNodo.querySelector('[data-motivo]').value.trim();
    const acepta = boton.dataset.acepta === 'si';
    if (!acepta && !motivo) {
      mostrarResultado(tarjetaNodo.querySelector('.resultado'), 'Indica el motivo del rechazo', 'error');
      return;
    }
    const exito = await ejecutar(boton, async () => {
      await api('asignacion', `/asignaciones/${encodeURIComponent(boton.dataset.id)}/responder`, {
        metodo: 'POST',
        cuerpo: sinVacios({ acepta, motivo }),
      });
      return acepta ? 'Asignación aceptada' : 'Asignación rechazada; se buscará otro técnico';
    });
    if (exito) setTimeout(cargarAsignaciones, 1500);
  }

  async function guardarTecnico(datos, form) {
    const especialidades = datos.especialidades.split(',').map(e => e.trim()).filter(Boolean);
    if (!especialidades.length) throw new Error('Indica al menos una especialidad');
    if ((datos.lat === '') !== (datos.lon === '')) throw new Error('Completa latitud y longitud juntas');
    const cuerpo = sinVacios({ tecnico_id: datos.tecnico_id, nombre: datos.nombre, contacto: datos.contacto, zona_id: datos.zona_id });
    cuerpo.especialidades = especialidades;
    if (datos.lat !== '') {
      cuerpo.lat = Number(datos.lat);
      cuerpo.lon = Number(datos.lon);
    }
    const tecnico = await api('asignacion', '/tecnicos', { metodo: 'POST', cuerpo });
    form.reset();
    cargarTecnicos();
    return `Técnico ${tecnico.nombre} guardado (${tecnico.tecnico_id}).${cuerpo.contacto && cuerpo.contacto.includes('@') ? ' Debe aceptar el correo de confirmación de AWS SNS.' : ''}`;
  }

  async function suscribirJefe(datos, form) {
    await api('asignacion', '/jefes', { metodo: 'POST', cuerpo: { contacto: datos.contacto } });
    form.reset();
    return datos.contacto.includes('@')
      ? `Suscripción creada. Llegará un correo de confirmación de AWS SNS a ${datos.contacto}: hay que aceptarlo para recibir avisos.`
      : 'Suscripción creada.';
  }

  async function cargarTecnicos() {
    const params = filtrosDe(raiz.querySelector('[data-filtro-tecnicos]'));
    await llenar(raiz.querySelector('[data-tecnicos]'), async () => {
      const r = await api('asignacion', '/tecnicos', { params });
      const lista = r.tecnicos || [];
      if (!Object.keys(params).length) tecnicos = lista;
      if (!lista.length) return vacio('No hay técnicos con esos filtros.');
      return `<div class="tabla-scroll"><table><thead><tr><th>Nombre</th><th>ID</th><th>Zona</th><th>Especialidades</th><th>Estado</th><th>Activas</th><th>Contacto</th></tr></thead><tbody>${lista.map(t => `<tr>
        <td><strong>${esc(t.nombre)}</strong></td><td class="id">${esc(t.tecnico_id)}</td><td>${esc(t.zona_id || '—')}</td>
        <td>${listaTexto(t.especialidades)}</td><td>${esc(t.estado || '—')}</td><td class="num">${numero(t.asignaciones_activas, 0)}</td><td>${esc(t.contacto || '—')}</td>
      </tr>`).join('')}</tbody></table></div>`;
    });
  }

  async function cargarAsignaciones() {
    const params = filtrosDe(raiz.querySelector('[data-filtro-asignaciones]'));
    await llenar(raiz.querySelector('[data-asignaciones]'), async () => {
      const r = await api('asignacion', '/asignaciones', { params });
      const lista = r.asignaciones || [];
      if (!lista.length) return vacio('No hay asignaciones con esos filtros.');
      lista.sort((a, b) => (a.estado === 'pendiente' ? 0 : 1) - (b.estado === 'pendiente' ? 0 : 1));
      return `<p class="meta">${numero(r.cantidad, 0)} asignación(es); las pendientes primero</p><div class="tarjetas">${lista.map(tarjeta).join('')}</div>`;
    });
  }

  async function actualizar() {
    await cargarTecnicos();
    await cargarAsignaciones();
  }

  registrarPestana({ id: 'asignacion', titulo: 'Técnicos', modulo: 'asignacion', montar, actualizar });
})();
