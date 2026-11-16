(() => {
  const ROLES = [['operador', 'Operador'], ['tecnico', 'Técnico'], ['jefe-mantenimiento', 'Jefe de mantenimiento'], ['supervisor', 'Supervisor'], ['gerencia', 'Gerencia']];
  const NOMBRE_ROL = Object.fromEntries(ROLES);
  const MINUTOS_CONFIRMACION = 15;
  const CLAVE_NOMBRE = 'arquifusion.confirmado_por';
  let raiz;

  function montar(nodo) {
    raiz = nodo;
    raiz.innerHTML = `
      <h3>Avisos por confirmar</h3>
      <div class="aviso">Los avisos importantes esperan confirmación. Si nadie confirma en ${MINUTOS_CONFIRMACION} minutos, se escalan al siguiente nivel: jefe de mantenimiento → supervisor → gerencia.</div>
      <form class="filtros" data-filtro-pendientes>
        <label>Rol <select name="rol">${opciones(ROLES, '', 'Todos')}</select></label>
        <button type="submit">Aplicar</button>
      </form>
      <div data-pendientes></div>

      <h3>Destinatarios</h3>
      <form class="filtros" data-filtro-destinatarios>
        <label>Rol <select name="rol">${opciones(ROLES, '', 'Todos')}</select></label>
        <button type="submit">Aplicar</button>
      </form>
      <div data-destinatarios></div>

      <details class="panel">
        <summary>Registrar destinatario</summary>
        <form class="formulario" data-destinatario>
          <div class="fila">
            <label>Nombre * <input name="nombre" required></label>
            <label>Rol * <select name="rol" required>${opciones([['', 'Elige un rol'], ...ROLES])}</select></label>
            <label>Contacto * <input name="contacto" required placeholder="correo@empresa.com o +51…"></label>
            <label>Zona <input name="zona_id"></label>
          </div>
          <p class="nota">Si el contacto es un correo, llegará un mensaje de confirmación de AWS SNS que hay que aceptar para empezar a recibir avisos.</p>
          <div class="acciones"><button type="submit">Registrar</button></div>
          <p class="resultado"></p>
        </form>
      </details>`;

    alFiltrar(raiz.querySelector('[data-filtro-pendientes]'), cargarPendientes);
    alFiltrar(raiz.querySelector('[data-filtro-destinatarios]'), cargarDestinatarios);
    enviarFormulario(raiz.querySelector('[data-destinatario]'), registrarDestinatario);
    alHacerClic(raiz, 'confirmar', confirmar);
  }

  function plazo(n) {
    const base = aFecha(n.ts_enviado);
    if (!base) return '';
    const limite = new Date(base.getTime() + MINUTOS_CONFIRMACION * 60000);
    return limite < new Date()
      ? '<p class="nota">El plazo ya venció; se escalará en la próxima verificación.</p>'
      : `<p class="nota">Se escala a las ${hora(limite)} si nadie confirma.</p>`;
  }

  function tarjeta(n) {
    const ref = n.incidente_ref || {};
    return `<article class="tarjeta borde-alta">
      <header class="tarjeta-cabecera">${insignia(NOMBRE_ROL[n.rol] || n.rol)}${autor(n.redactado_por)}<time>${fecha(n.ts_enviado)}</time></header>
      <p><strong>Máquina:</strong> ${esc(n.maquina_id || '—')}${ref.tipo ? ` · <strong>${esc(ref.tipo)}:</strong> <span class="id">${esc(ref.refId || '')}</span>` : ''}</p>
      <p class="mensaje">${esc(n.mensaje || '')}</p>
      ${plazo(n)}
      <div class="fila-confirmar">
        <input data-confirmado-por placeholder="Tu nombre" value="${esc(leerLocal(CLAVE_NOMBRE))}" aria-label="Confirmado por">
        <button type="button" data-accion="confirmar" data-id="${esc(n.notificacion_id)}">Confirmar</button>
      </div>
      <p class="resultado"></p>
    </article>`;
  }

  async function confirmar(boton) {
    const tarjetaNodo = boton.closest('.tarjeta');
    const nombre = tarjetaNodo.querySelector('[data-confirmado-por]').value.trim();
    if (!nombre) {
      mostrarResultado(tarjetaNodo.querySelector('.resultado'), 'Escribe tu nombre para confirmar', 'error');
      return;
    }
    guardarLocal(CLAVE_NOMBRE, nombre);
    const exito = await ejecutar(boton, async () => {
      await api('comunicacion', `/notificaciones/${encodeURIComponent(boton.dataset.id)}/confirmar`, {
        metodo: 'POST',
        cuerpo: { confirmado_por: nombre },
      });
      return 'Aviso confirmado';
    });
    if (exito) cargarPendientes();
  }

  async function registrarDestinatario(datos, form) {
    await api('comunicacion', '/destinatarios', { metodo: 'POST', cuerpo: sinVacios(datos) });
    form.reset();
    cargarDestinatarios();
    return datos.contacto.includes('@')
      ? `Destinatario registrado. Llegará un correo de confirmación de AWS SNS a ${datos.contacto}: hay que aceptarlo para recibir avisos.`
      : 'Destinatario registrado.';
  }

  async function cargarPendientes() {
    const params = { ...filtrosDe(raiz.querySelector('[data-filtro-pendientes]')), pendientes: 'true' };
    await llenar(raiz.querySelector('[data-pendientes]'), async () => {
      const r = await api('comunicacion', '/notificaciones', { params });
      const lista = r.notificaciones || [];
      if (!lista.length) return vacio('No hay avisos esperando confirmación.');
      return `<p class="meta">${numero(r.cantidad, 0)} aviso(s) por confirmar</p><div class="tarjetas">${lista.map(tarjeta).join('')}</div>`;
    });
  }

  async function cargarDestinatarios() {
    const params = filtrosDe(raiz.querySelector('[data-filtro-destinatarios]'));
    await llenar(raiz.querySelector('[data-destinatarios]'), async () => {
      const r = await api('comunicacion', '/destinatarios', { params });
      const lista = r.destinatarios || [];
      if (!lista.length) return vacio('No hay destinatarios registrados.');
      return `<div class="tabla-scroll"><table><thead><tr><th>Nombre</th><th>Rol</th><th>Contacto</th><th>Zona</th><th>Registrado</th></tr></thead><tbody>${lista.map(d => `<tr>
        <td>${esc(d.nombre)}</td><td>${esc(NOMBRE_ROL[d.rol] || d.rol)}</td><td>${esc(d.contacto)}</td><td>${esc(d.zona_id || '—')}</td><td>${fecha(d.ts_registrado)}</td>
      </tr>`).join('')}</tbody></table></div>`;
    });
  }

  async function actualizar() {
    await Promise.all([cargarPendientes(), cargarDestinatarios()]);
  }

  registrarPestana({ id: 'comunicacion', titulo: 'Comunicación', modulo: 'comunicacion', montar, actualizar });
})();
