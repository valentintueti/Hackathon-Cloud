(() => {
  const CLASES = { regular: 'Regular', irregular: 'Irregular', sin_movimiento: 'Sin movimiento' };
  const zonas = new Set();
  let raiz;
  let componentes = [];

  function montar(nodo) {
    raiz = nodo;
    raiz.innerHTML = `
      <h3>Inventario por zona</h3>
      <form class="filtros" data-filtros>
        <label>Zona <input name="zona" list="zonas-repuestos" placeholder="ID de zona"></label>
        <label class="casilla"><input type="checkbox" name="bajo_reorden" value="true"> Solo bajo el punto de reorden</label>
        <button type="submit">Aplicar</button>
      </form>
      <div data-inventario></div>

      <div class="dos-columnas">
        <details class="panel">
          <summary>Registrar llegada o conteo</summary>
          <form class="formulario" data-ingreso>
            <label>Zona * <input name="zona_id" list="zonas-repuestos" required></label>
            <label>Componente * <select name="componente_id" data-select-componentes required></select></label>
            <fieldset class="radios"><legend>Tipo de registro</legend>
              <label><input type="radio" name="modo" value="sumar" checked> Llegaron piezas (se suman al stock)</label>
              <label><input type="radio" name="modo" value="fijar"> Conteo físico (reemplaza el stock)</label>
            </fieldset>
            <label>Cantidad * <input name="valor" type="number" min="0" step="1" required></label>
            <div class="acciones"><button type="submit">Guardar</button></div>
            <p class="resultado"></p>
          </form>
        </details>
        <details class="panel">
          <summary>Registrar consumo</summary>
          <form class="formulario" data-consumo>
            <label>Componente * <select name="componente_id" data-select-componentes required></select></label>
            <label>Cantidad * <input name="cantidad" type="number" min="1" step="1" required></label>
            <div class="fila">
              <label>Zona <input name="zona_id" list="zonas-repuestos"></label>
              <label>Máquina <input name="maquina_id"></label>
            </div>
            <label>Orden <input name="orden_id" placeholder="Opcional"></label>
            <p class="nota">Indica la zona o la máquina (de la máquina se toma su zona).</p>
            <div class="acciones"><button type="submit">Registrar consumo</button></div>
            <p class="resultado"></p>
          </form>
        </details>
      </div>

      <h3>Catálogo de componentes</h3>
      <div data-componentes></div>
      <details class="panel">
        <summary>Registrar componente</summary>
        <form class="formulario" data-componente>
          <div class="fila">
            <label>ID * <input name="componente_id" required></label>
            <label>Nombre * <input name="nombre" required></label>
            <label>Categoría <input name="categoria"></label>
            <label>Días de reposición <input name="dias_reposicion" type="number" min="0" step="1"></label>
            <label>Costo <input name="costo" type="number" min="0" step="any"></label>
          </div>
          <div class="acciones"><button type="submit">Guardar componente</button></div>
          <p class="resultado"></p>
        </form>
      </details>
      <datalist id="zonas-repuestos"></datalist>`;

    alFiltrar(raiz.querySelector('[data-filtros]'), cargarInventario);
    enviarFormulario(raiz.querySelector('[data-ingreso]'), registrarIngreso);
    enviarFormulario(raiz.querySelector('[data-consumo]'), registrarConsumo);
    enviarFormulario(raiz.querySelector('[data-componente]'), registrarComponente);
  }

  function actualizarSelects() {
    const lista = componentes.map(c => [c.componente_id, `${c.nombre || c.componente_id} (${c.componente_id})`]);
    raiz.querySelectorAll('[data-select-componentes]').forEach(select => {
      const actual = select.value;
      select.innerHTML = opciones([['', lista.length ? 'Elige un componente' : 'No hay componentes registrados'], ...lista], actual);
    });
  }

  function actualizarZonas() {
    raiz.querySelector('#zonas-repuestos').innerHTML = [...zonas].sort().map(z => `<option value="${esc(z)}"></option>`).join('');
  }

  async function cargarComponentes() {
    const exito = await llenar(raiz.querySelector('[data-componentes]'), async () => {
      const r = await api('repuestos', '/repuestos/componentes');
      componentes = r.componentes || [];
      if (!componentes.length) return vacio('Todavía no hay componentes en el catálogo.');
      return `<div class="tabla-scroll"><table><thead><tr><th>ID</th><th>Nombre</th><th>Categoría</th><th>Días de reposición</th><th>Costo</th></tr></thead><tbody>${componentes.map(c => `<tr>
        <td class="id">${esc(c.componente_id)}</td><td>${esc(c.nombre)}</td><td>${esc(c.categoria || '—')}</td>
        <td class="num">${numero(c.dias_reposicion, 0)}</td><td class="num">${numero(c.costo, 2)}</td>
      </tr>`).join('')}</tbody></table></div>`;
    });
    if (!exito) componentes = [];
    actualizarSelects();
  }

  async function cargarInventario() {
    const params = filtrosDe(raiz.querySelector('[data-filtros]'));
    await llenar(raiz.querySelector('[data-inventario]'), async () => {
      const r = await api('repuestos', '/repuestos/inventario', { params });
      const filas = r.inventario || [];
      filas.forEach(f => zonas.add(f.zona_id));
      actualizarZonas();
      if (!filas.length) return vacio('No hay inventario con esos filtros.');
      const bajos = filas.filter(f => f.bajo_reorden).length;
      return `<p class="meta">${numero(filas.length, 0)} pieza(s) · <strong>${numero(bajos, 0)}</strong> bajo el punto de reorden</p>
        <div class="tabla-scroll"><table><thead><tr>
          <th>Zona</th><th>Componente</th><th>Stock</th><th>Punto de reorden</th><th>Stock objetivo</th><th>Demanda diaria</th><th>Clasificación</th><th></th>
        </tr></thead><tbody>${filas.map(f => `<tr class="${f.bajo_reorden ? 'fila-alerta' : ''}">
          <td>${esc(f.zona_id)}</td>
          <td>${esc(f.nombre || f.componente_id)} <span class="id">${esc(f.componente_id)}</span></td>
          <td class="num"><strong>${numero(f.stock_actual, 0)}</strong></td>
          <td class="num">${numero(f.punto_reorden, 0)}</td>
          <td class="num">${numero(f.stock_objetivo, 0)}</td>
          <td class="num">${numero(f.demanda_diaria, 3)}</td>
          <td>${esc(CLASES[f.clasificacion] || f.clasificacion || '—')}</td>
          <td>${f.bajo_reorden ? insignia('Reponer', 'sev-critica') : ''}</td>
        </tr>`).join('')}</tbody></table></div>`;
    });
  }

  async function registrarIngreso(datos) {
    const valor = Number(datos.valor);
    if (!Number.isInteger(valor) || valor < 0) throw new Error('La cantidad debe ser un número entero de 0 o más');
    const pieza = { zona_id: datos.zona_id, componente_id: datos.componente_id };
    if (datos.modo === 'fijar') {
      pieza.stock_actual = valor;
    } else {
      if (valor < 1) throw new Error('Para registrar una llegada la cantidad debe ser mayor a 0');
      pieza.cantidad = valor;
    }
    const r = await api('repuestos', '/repuestos/inventario', { metodo: 'POST', cuerpo: pieza });
    if (r.errores && r.errores.length) throw new Error(r.errores.map(e => e.error).join('; '));
    cargarInventario();
    const guardado = (r.guardados || [])[0] || {};
    return `Stock de ${pieza.componente_id} en ${pieza.zona_id}: ${numero(guardado.stock_actual, 0)} unidades`;
  }

  async function registrarConsumo(datos, form) {
    if (!datos.zona_id && !datos.maquina_id) throw new Error('Indica la zona o la máquina donde se usó la pieza');
    const cantidad = parseInt(datos.cantidad, 10);
    if (!(cantidad > 0)) throw new Error('La cantidad debe ser mayor a 0');
    const pieza = sinVacios({
      componente_id: datos.componente_id, cantidad, zona_id: datos.zona_id, maquina_id: datos.maquina_id, orden_id: datos.orden_id,
    });
    const r = await api('repuestos', '/repuestos/consumos', { metodo: 'POST', cuerpo: [pieza] });
    if (r.errores && r.errores.length) throw new Error(r.errores.map(e => e.error).join('; '));
    form.reset();
    cargarInventario();
    return 'Consumo registrado; el stock se descontó';
  }

  async function registrarComponente(datos, form) {
    const item = sinVacios({ componente_id: datos.componente_id, nombre: datos.nombre, categoria: datos.categoria });
    if (datos.dias_reposicion !== '') item.dias_reposicion = Number(datos.dias_reposicion);
    if (datos.costo !== '') item.costo = Number(datos.costo);
    const r = await api('repuestos', '/repuestos/componentes', { metodo: 'POST', cuerpo: item });
    if (r.errores && r.errores.length) throw new Error(r.errores.map(e => e.error).join('; '));
    form.reset();
    cargarComponentes();
    return `Componente ${item.componente_id} guardado`;
  }

  async function actualizar() {
    await Promise.all([cargarComponentes(), cargarInventario()]);
  }

  registrarPestana({ id: 'repuestos', titulo: 'Repuestos', modulo: 'repuestos', montar, actualizar });
})();
