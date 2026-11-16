const pestanas = [];
const ORDEN_PESTANAS = ['flota', 'alertas', 'incidentes', 'preventivo', 'masivos', 'combustible', 'asignacion', 'planificacion', 'productividad', 'repuestos', 'comunicacion', 'decisiones'];
const FORMATO_LIMA = new Intl.DateTimeFormat('es-PE', {
  timeZone: 'America/Lima', day: '2-digit', month: '2-digit', year: 'numeric',
  hour: '2-digit', minute: '2-digit', hour12: false,
});
const FORMATO_HORA_LIMA = new Intl.DateTimeFormat('es-PE', {
  timeZone: 'America/Lima', hour: '2-digit', minute: '2-digit', hour12: false,
});
const AUTORES = {
  gemini: ['IA', 'ia'],
  plantilla: ['Reglas', 'reglas'],
  reglas: ['Reglas', 'reglas'],
  mixto: ['IA + Reglas', 'mixto'],
};
const TIEMPO_ESPERA_MS = 30000;

function registrarPestana(definicion) {
  pestanas.push(definicion);
}

function configurado(modulo) {
  return Boolean(window.CONFIG && String(window.CONFIG[modulo] || '').trim());
}

function mensajeDeError(datos, estado) {
  if (datos && typeof datos === 'object') {
    if (datos.error) return String(datos.error);
    if (Array.isArray(datos.errores) && datos.errores.length) {
      return datos.errores.map(e => e.error || JSON.stringify(e)).join('; ');
    }
    if (datos.message) return String(datos.message);
  }
  return `La API respondió con el código ${estado}`;
}

async function api(modulo, ruta, opciones = {}) {
  const base = String((window.CONFIG || {})[modulo] || '').trim().replace(/\/+$/, '');
  if (!base) throw new Error(`El módulo "${modulo}" no tiene URL en config.js`);
  const url = new URL(base + ruta);
  Object.entries(opciones.params || {}).forEach(([clave, valor]) => {
    if (valor !== undefined && valor !== null && valor !== '') url.searchParams.set(clave, valor);
  });
  const conCuerpo = opciones.cuerpo !== undefined;
  const control = new AbortController();
  const temporizador = setTimeout(() => control.abort(), opciones.espera || TIEMPO_ESPERA_MS);
  let respuesta;
  try {
    respuesta = await fetch(url, {
      method: opciones.metodo || 'GET',
      headers: conCuerpo ? { 'Content-Type': 'application/json' } : undefined,
      body: conCuerpo ? JSON.stringify(opciones.cuerpo) : undefined,
      signal: control.signal,
    });
  } catch (error) {
    throw new Error(error.name === 'AbortError' ? 'La API no respondió a tiempo' : 'No se pudo conectar con la API');
  } finally {
    clearTimeout(temporizador);
  }
  const texto = await respuesta.text();
  let datos = null;
  try {
    datos = texto ? JSON.parse(texto) : null;
  } catch (error) {
    datos = null;
  }
  if (!respuesta.ok) {
    const error = new Error(mensajeDeError(datos, respuesta.status));
    error.estado = respuesta.status;
    error.datos = datos;
    throw error;
  }
  return datos || {};
}

function esc(valor) {
  return String(valor ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function aFecha(valor) {
  if (!valor) return null;
  let texto = String(valor).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(texto)) return null;
  texto = texto.replace(' ', 'T').replace(/(\.\d{3})\d+/, '$1');
  if (/T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(texto)) texto += 'Z';
  const resultado = new Date(texto);
  return isNaN(resultado) ? null : resultado;
}

function fecha(valor) {
  if (!valor) return '—';
  const convertida = aFecha(valor);
  if (convertida) return FORMATO_LIMA.format(convertida);
  if (/^\d{4}-\d{2}-\d{2}$/.test(String(valor))) return String(valor).split('-').reverse().join('/');
  return esc(valor);
}

function hora(valor) {
  return FORMATO_HORA_LIMA.format(valor);
}

function autor(valor) {
  const datos = AUTORES[String(valor || '').toLowerCase()];
  return datos ? `<span class="autor autor-${datos[1]}" title="Redactado por: ${esc(valor)}">${datos[0]}</span>` : '';
}

function insignia(texto, clase = '') {
  return texto ? `<span class="insignia ${esc(clase)}">${esc(texto)}</span>` : '';
}

function severidad(valor) {
  return valor ? insignia(valor, `sev-${valor}`) : '';
}

function numero(valor, decimales = 1) {
  if (valor === null || valor === undefined || valor === '') return '—';
  const convertido = Number(valor);
  return Number.isFinite(convertido) ? convertido.toLocaleString('es-PE', { maximumFractionDigits: decimales }) : esc(valor);
}

function porcentaje(valor, conSigno = false) {
  if (valor === null || valor === undefined || valor === '') return '—';
  const signo = conSigno && Number(valor) > 0 ? '+' : '';
  return `${signo}${numero(valor)}%`;
}

function listaTexto(valores) {
  return Array.isArray(valores) && valores.length ? valores.map(esc).join(', ') : '—';
}

function chips(valores) {
  return Array.isArray(valores) && valores.length ? `<div class="chips">${valores.map(v => `<span class="chip">${esc(v)}</span>`).join('')}</div>` : '';
}

function vacio(texto) {
  return `<p class="vacio">${esc(texto)}</p>`;
}

function avisoError(texto) {
  return `<div class="aviso aviso-error" role="alert">${esc(texto)}</div>`;
}

function contador(valorHtml, etiqueta, colorBorde = '') {
  return `<div class="contador"${colorBorde ? ` style="border-top-color:${colorBorde}"` : ''}><span class="valor">${valorHtml}</span><span class="etiqueta">${esc(etiqueta)}</span></div>`;
}

function opciones(valores, seleccionado = '', textoTodos = null) {
  const lista = textoTodos !== null ? [['', textoTodos], ...valores] : valores;
  return lista.map(item => {
    const [valor, texto] = Array.isArray(item) ? item : [item, item];
    const marcado = String(valor) === String(seleccionado ?? '') ? ' selected' : '';
    return `<option value="${esc(valor)}"${marcado}>${esc(texto)}</option>`;
  }).join('');
}

function datosFormulario(form) {
  const datos = {};
  new FormData(form).forEach((valor, clave) => {
    datos[clave] = typeof valor === 'string' ? valor.trim() : valor;
  });
  return datos;
}

function sinVacios(objeto) {
  return Object.fromEntries(Object.entries(objeto).filter(([, valor]) => valor !== '' && valor !== null && valor !== undefined));
}

function mostrarResultado(nodo, texto, tipo) {
  if (!nodo) return;
  nodo.className = `resultado ${tipo || ''}`.trim();
  nodo.textContent = texto;
}

function notificar(texto, tipo = 'ok') {
  const contenedor = document.getElementById('avisos');
  if (!contenedor) return;
  const aviso = document.createElement('div');
  aviso.className = `toast toast-${tipo}`;
  aviso.setAttribute('role', 'status');
  aviso.textContent = texto;
  contenedor.appendChild(aviso);
  setTimeout(() => aviso.remove(), 4500);
}

async function llenar(nodo, funcion) {
  nodo.setAttribute('aria-busy', 'true');
  nodo.innerHTML = '<div class="cargando"><span class="giro"></span>Cargando…</div>';
  try {
    nodo.innerHTML = (await funcion()) ?? '';
    return true;
  } catch (error) {
    nodo.innerHTML = avisoError(error.message);
    return false;
  } finally {
    nodo.removeAttribute('aria-busy');
  }
}

function enviarFormulario(form, funcion, { espera = 'Enviando…', alTerminar = null } = {}) {
  form.addEventListener('submit', async evento => {
    evento.preventDefault();
    if (!form.reportValidity()) return;
    const salida = form.querySelector('.resultado');
    const botones = [...form.querySelectorAll('button')];
    botones.forEach(boton => { boton.disabled = true; });
    mostrarResultado(salida, espera, '');
    try {
      const mensaje = (await funcion(datosFormulario(form), form)) || 'Listo';
      mostrarResultado(salida, mensaje, 'ok');
      if (alTerminar) {
        notificar(mensaje);
        alTerminar();
      }
    } catch (error) {
      mostrarResultado(salida, error.message, 'error');
    } finally {
      botones.forEach(boton => { boton.disabled = false; });
    }
  });
}

async function ejecutar(boton, funcion) {
  const tarjeta = boton.closest('.tarjeta') || boton.parentElement;
  const salida = tarjeta.querySelector('.resultado');
  const botones = [...tarjeta.querySelectorAll('button')];
  botones.forEach(b => { b.disabled = true; });
  mostrarResultado(salida, 'Enviando…', '');
  try {
    const mensaje = await funcion();
    mostrarResultado(salida, mensaje, 'ok');
    notificar(mensaje);
    return true;
  } catch (error) {
    mostrarResultado(salida, error.message, 'error');
    return false;
  } finally {
    botones.forEach(b => { b.disabled = false; });
  }
}

function alHacerClic(raiz, accion, funcion) {
  raiz.addEventListener('click', evento => {
    const objetivo = evento.target.closest(`[data-accion="${accion}"]`);
    if (objetivo && raiz.contains(objetivo)) funcion(objetivo, evento);
  });
}

function alFiltrar(form, funcion) {
  form.addEventListener('submit', evento => {
    evento.preventDefault();
    if (form.reportValidity()) funcion();
  });
  form.addEventListener('change', evento => {
    if (evento.target.matches('select, input[type="checkbox"]')) funcion();
  });
}

function filtrosDe(form) {
  return sinVacios(datosFormulario(form));
}

function leerLocal(clave) {
  try {
    return localStorage.getItem(clave) || '';
  } catch (error) {
    return '';
  }
}

function guardarLocal(clave, valor) {
  try {
    localStorage.setItem(clave, valor);
  } catch (error) {
    return;
  }
}

function iniciarApp() {
  const menu = document.getElementById('menu');
  const principal = document.getElementById('principal');
  pestanas.sort((a, b) => ORDEN_PESTANAS.indexOf(a.id) - ORDEN_PESTANAS.indexOf(b.id));
  const visibles = pestanas.filter(p => configurado(p.modulo));
  if (!visibles.length) {
    principal.innerHTML = '<div class="aviso">No hay módulos configurados. Completa las URL de cada API en config.js.</div>';
    return;
  }
  visibles.forEach(pestana => {
    const boton = document.createElement('button');
    boton.type = 'button';
    boton.textContent = pestana.titulo;
    boton.setAttribute('role', 'tab');
    boton.setAttribute('aria-controls', `pestana-${pestana.id}`);
    boton.addEventListener('click', () => abrir(pestana.id));
    menu.appendChild(boton);

    const seccion = document.createElement('section');
    seccion.className = 'pestana';
    seccion.id = `pestana-${pestana.id}`;
    seccion.setAttribute('role', 'tabpanel');
    seccion.hidden = true;
    seccion.innerHTML = `<div class="encabezado"><h2>${esc(pestana.titulo)}</h2><button type="button" class="secundario" data-actualizar>Actualizar</button></div><div class="cuerpo"></div>`;
    principal.appendChild(seccion);

    pestana.boton = boton;
    pestana.seccion = seccion;
    pestana.cuerpo = seccion.querySelector('.cuerpo');
    seccion.querySelector('[data-actualizar]').addEventListener('click', () => refrescar(pestana));
  });
  window.addEventListener('hashchange', () => {
    const id = location.hash.slice(1);
    if (visibles.some(p => p.id === id)) abrir(id);
  });
  const inicial = visibles.find(p => p.id === location.hash.slice(1)) || visibles[0];
  abrir(inicial.id);
}

function abrir(id) {
  let elegida = null;
  pestanas.forEach(pestana => {
    if (!pestana.seccion) return;
    const activa = pestana.id === id;
    pestana.seccion.hidden = !activa;
    pestana.boton.classList.toggle('activa', activa);
    pestana.boton.setAttribute('aria-selected', String(activa));
    if (activa) elegida = pestana;
  });
  if (!elegida) return;
  if (location.hash.slice(1) !== id) {
    try {
      history.replaceState(null, '', `#${id}`);
    } catch (error) {
      location.hash = id;
    }
  }
  elegida.boton.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  if (!elegida.montada) {
    elegida.montada = true;
    try {
      elegida.montar(elegida.cuerpo);
    } catch (error) {
      elegida.cuerpo.innerHTML = avisoError(error.message);
      return;
    }
    refrescar(elegida);
  } else if (elegida.alMostrar) {
    elegida.alMostrar();
  }
}

async function refrescar(pestana) {
  const boton = pestana.seccion.querySelector('[data-actualizar]');
  boton.disabled = true;
  try {
    await pestana.actualizar();
  } catch (error) {
    notificar(`${pestana.titulo}: ${error.message}`, 'error');
  } finally {
    boton.disabled = false;
  }
}

registrarPestana({
  id: 'decisiones',
  titulo: 'Decisiones',
  modulo: 'decisiones',
  montar(raiz) {
    raiz.innerHTML = vacio('Este módulo todavía está en preparación.');
  },
  actualizar() {},
});

document.addEventListener('DOMContentLoaded', iniciarApp);
