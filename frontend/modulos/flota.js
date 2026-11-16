(() => {
  const COLORES = {
    operando: '#2e7d32', operativa: '#2e7d32', activa: '#2e7d32', trabajando: '#2e7d32', encendida: '#2e7d32',
    ralenti: '#f9a825', mantenimiento: '#1565c0', detenida: '#6d4c41',
    requiere_intervencion: '#c62828', sin_senal: '#757575',
  };
  const NOMBRES = { sin_senal: 'Sin señal', requiere_intervencion: 'Requiere intervención', ralenti: 'Ralentí' };
  const zonas = new Set();
  const estados = new Set();
  let raiz;
  let mapa = null;
  let capa = null;

  const color = estado => COLORES[estado] || '#7b1fa2';
  const nombreEstado = estado => NOMBRES[estado] || String(estado || 'desconocido').replace(/_/g, ' ');
  const punto = estado => `<span class="punto" style="background:${color(estado)}"></span>`;
  const etiquetaEstado = estado => `<span class="estado-maquina">${punto(estado)}${esc(nombreEstado(estado))}</span>`;

  function montar(nodo) {
    raiz = nodo;
    raiz.innerHTML = `
      <div data-resumen></div>
      <form class="filtros" data-filtros>
        <label>Zona <select name="zona"><option value="">Todas</option></select></label>
        <label>Estado <select name="estado"><option value="">Todos</option></select></label>
        <button type="submit">Aplicar</button>
      </form>
      <div class="mapa" data-mapa></div>
      <div class="leyenda" data-leyenda></div>
      <div data-maquinas></div>
      <h3>Máquinas cercanas</h3>
      <form class="formulario panel" data-cercanas>
        <div class="fila">
          <label>Latitud * <input name="lat" type="number" step="any" min="-90" max="90" required></label>
          <label>Longitud * <input name="lon" type="number" step="any" min="-180" max="180" required></label>
          <label>Radio (km) * <input name="radio_km" type="number" step="any" min="0.1" value="5" required></label>
        </div>
        <div class="acciones">
          <button type="button" class="secundario" data-accion="mi-ubicacion">Usar mi ubicación</button>
          <button type="submit">Buscar</button>
        </div>
        <p class="resultado"></p>
      </form>
      <div data-cercanas-lista></div>`;
    crearMapa();
    alFiltrar(raiz.querySelector('[data-filtros]'), cargarMaquinas);
    enviarFormulario(raiz.querySelector('[data-cercanas]'), buscarCercanas, { espera: 'Buscando…' });
    alHacerClic(raiz, 'mi-ubicacion', usarMiUbicacion);
  }

  function crearMapa() {
    const nodo = raiz.querySelector('[data-mapa]');
    if (!window.L) {
      nodo.classList.add('sin-mapa');
      nodo.innerHTML = avisoError('No se pudo cargar el mapa (Leaflet). La lista de máquinas sigue disponible abajo.');
      return;
    }
    mapa = L.map(nodo).setView([-12.05, -77.04], 6);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap',
    }).addTo(mapa);
    capa = L.layerGroup().addTo(mapa);
  }

  function popup(m) {
    const filas = [`<strong>${esc(m.maquina_id)}</strong>`, `Estado: ${esc(nombreEstado(m.estado_visible))}`];
    if (m.modelo_id) filas.push(`Modelo: ${esc(m.modelo_id)}`);
    if (m.zona_id) filas.push(`Zona: ${esc(m.zona_id)}`);
    if (m.health_score !== undefined && m.health_score !== null) filas.push(`Salud: ${numero(m.health_score)} / 100`);
    if (m.porcentaje_intervalo !== undefined && m.porcentaje_intervalo !== null) filas.push(`Intervalo preventivo: ${porcentaje(m.porcentaje_intervalo)}`);
    if (m.distancia_km !== undefined) filas.push(`Distancia: ${numero(m.distancia_km, 2)} km`);
    return filas.join('<br>');
  }

  function pintarMapa(maquinas) {
    if (!mapa) return;
    capa.clearLayers();
    const puntos = [];
    maquinas.forEach(m => {
      const lat = Number(m.lat);
      const lon = Number(m.lon);
      if (m.lat === undefined || m.lat === null || m.lon === undefined || m.lon === null || !Number.isFinite(lat) || !Number.isFinite(lon)) return;
      L.circleMarker([lat, lon], {
        radius: 9, color: '#ffffff', weight: 2, fillColor: color(m.estado_visible), fillOpacity: 0.9,
      }).bindPopup(popup(m)).addTo(capa);
      puntos.push([lat, lon]);
    });
    if (puntos.length) mapa.fitBounds(puntos, { padding: [30, 30], maxZoom: 14 });
  }

  function tablaMaquinas(maquinas, conDistancia = false) {
    if (!maquinas.length) return vacio(conDistancia ? 'No hay máquinas en ese radio.' : 'No hay máquinas con esos filtros.');
    const filas = maquinas.map(m => `<tr>
      ${conDistancia ? `<td class="num">${numero(m.distancia_km, 2)} km</td>` : ''}
      <td><strong>${esc(m.maquina_id)}</strong></td>
      <td>${etiquetaEstado(m.estado_visible)}</td>
      <td>${esc(m.zona_id || '—')}</td>
      <td>${esc(m.modelo_id || '—')}</td>
      <td class="num">${numero(m.health_score)}</td>
      <td class="num">${porcentaje(m.porcentaje_intervalo)}</td>
      <td>${fecha(m.ultima_recepcion_ts || m.ultima_lectura_ts)}</td>
    </tr>`).join('');
    return `<div class="tabla-scroll"><table><thead><tr>
      ${conDistancia ? '<th>Distancia</th>' : ''}<th>Máquina</th><th>Estado</th><th>Zona</th><th>Modelo</th><th>Salud</th><th>% intervalo</th><th>Última señal</th>
    </tr></thead><tbody>${filas}</tbody></table></div>`;
  }

  function vistaResumen(r) {
    const porEstado = Object.entries(r.por_estado || {}).sort((a, b) => b[1] - a[1]);
    const porZona = Object.entries(r.por_zona || {}).sort(([a], [b]) => a.localeCompare(b));
    const columnas = porEstado.map(([estado]) => estado);
    const tarjetas = [contador(numero(r.total_maquinas, 0), 'Máquinas')]
      .concat(porEstado.map(([estado, cantidad]) => contador(numero(cantidad, 0), nombreEstado(estado), color(estado))))
      .join('');
    const tablaZonas = porZona.length ? `<div class="tabla-scroll"><table class="compacta"><thead><tr><th>Zona</th><th>Total</th>${columnas.map(e => `<th>${esc(nombreEstado(e))}</th>`).join('')}</tr></thead><tbody>${porZona.map(([zona, conteo]) => {
      const total = Object.values(conteo).reduce((a, b) => a + Number(b), 0);
      return `<tr><td>${esc(zona)}</td><td class="num">${numero(total, 0)}</td>${columnas.map(e => `<td class="num">${numero(conteo[e] || 0, 0)}</td>`).join('')}</tr>`;
    }).join('')}</tbody></table></div>` : '';
    return `<div class="contadores">${tarjetas}</div>${tablaZonas}`;
  }

  function actualizarSelects() {
    const form = raiz.querySelector('[data-filtros]');
    const zonaActual = form.elements.zona.value;
    const estadoActual = form.elements.estado.value;
    form.elements.zona.innerHTML = opciones([...zonas].filter(z => z !== 'sin_zona').sort(), zonaActual, 'Todas');
    form.elements.estado.innerHTML = opciones([...estados].sort().map(e => [e, nombreEstado(e)]), estadoActual, 'Todos');
  }

  async function cargarResumen() {
    await llenar(raiz.querySelector('[data-resumen]'), async () => {
      const r = await api('ubicacion', '/ubicacion/resumen');
      Object.keys(r.por_estado || {}).forEach(e => estados.add(e));
      Object.keys(r.por_zona || {}).forEach(z => zonas.add(z));
      actualizarSelects();
      return vistaResumen(r);
    });
  }

  async function cargarMaquinas() {
    const params = filtrosDe(raiz.querySelector('[data-filtros]'));
    const leyenda = raiz.querySelector('[data-leyenda]');
    const exito = await llenar(raiz.querySelector('[data-maquinas]'), async () => {
      const r = await api('ubicacion', '/ubicacion/maquinas', { params });
      const maquinas = (r.maquinas || []).sort((a, b) => String(a.maquina_id).localeCompare(String(b.maquina_id)));
      maquinas.forEach(m => {
        if (m.zona_id) zonas.add(m.zona_id);
        if (m.estado_visible) estados.add(m.estado_visible);
      });
      actualizarSelects();
      pintarMapa(maquinas);
      const presentes = [...new Set(maquinas.map(m => m.estado_visible))];
      leyenda.innerHTML = presentes.map(e => `<span>${punto(e)}${esc(nombreEstado(e))}</span>`).join('');
      return `<p class="meta">${numero(r.cantidad, 0)} máquina(s)</p>${tablaMaquinas(maquinas)}`;
    });
    if (!exito) {
      leyenda.innerHTML = '';
      if (capa) capa.clearLayers();
    }
  }

  async function buscarCercanas(datos) {
    const r = await api('ubicacion', '/ubicacion/cercanas', { params: datos });
    const maquinas = r.maquinas || [];
    raiz.querySelector('[data-cercanas-lista]').innerHTML = tablaMaquinas(maquinas, true);
    return `${numero(r.cantidad, 0)} máquina(s) a menos de ${datos.radio_km} km`;
  }

  function usarMiUbicacion(boton) {
    const form = boton.form;
    const salida = form.querySelector('.resultado');
    if (!navigator.geolocation) {
      mostrarResultado(salida, 'Este navegador no permite obtener la ubicación', 'error');
      return;
    }
    mostrarResultado(salida, 'Obteniendo ubicación…', '');
    navigator.geolocation.getCurrentPosition(posicion => {
      form.elements.lat.value = posicion.coords.latitude.toFixed(6);
      form.elements.lon.value = posicion.coords.longitude.toFixed(6);
      mostrarResultado(salida, 'Ubicación cargada', 'ok');
    }, error => {
      mostrarResultado(salida, `No se pudo obtener la ubicación: ${error.message}`, 'error');
    }, { enableHighAccuracy: true, timeout: 15000 });
  }

  async function actualizar() {
    await Promise.all([cargarResumen(), cargarMaquinas()]);
  }

  function alMostrar() {
    if (mapa) setTimeout(() => mapa.invalidateSize(), 0);
  }

  registrarPestana({ id: 'flota', titulo: 'Flota', modulo: 'ubicacion', montar, actualizar, alMostrar });
})();
