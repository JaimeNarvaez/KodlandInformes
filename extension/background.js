// Genera los informes dentro de Chrome, sin programas externos.
//
// El botón de la ficha (boton-informe.js) reúne las respuestas de la API con la
// sesión de quien lo usa y las manda aquí. Aquí se sacan los datos de cada
// informe (datos.js), se arma el HTML (generador.js) y se convierte a PDF con
// el propio Chrome (chrome.debugger + Page.printToPDF), en dos pasadas como el
// generador de Python: se renderiza, se mide lo que ocupa cada módulo y se
// rehace el reparto de hojas con esas medidas. Cada PDF se guarda con la
// ventana de "Guardar como", sugiriendo "<alumno> - <código del grupo>.pdf".

import { buildHtml } from './informe/generador.js';
import { gruposDeLista, idiomaInforme, informeDeGrupo, nombreArchivo, rutas }
  from './informe/datos.js';

async function leerJson(ruta) {
  const r = await fetch(chrome.runtime.getURL(ruta));
  if (!r.ok) throw new Error(`no encuentro ${ruta}`);
  return r.json();
}

function aBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(s);
}

// banner de la carátula: el texto va en la imagen, hay uno por idioma
async function banner(idioma) {
  for (const nombre of [`banner_kodland_${idioma}.png`, 'banner_kodland.png']) {
    const r = await fetch(chrome.runtime.getURL(`img/${nombre}`)).catch(() => null);
    if (r && r.ok) return 'data:image/png;base64,' + aBase64(await r.arrayBuffer());
  }
  return '';
}

// Ventana minimizada con una pestaña en blanco, controlada por el protocolo de
// depuración de Chrome: ahí se pinta cada informe y se imprime a PDF.
async function abrirMotor() {
  const ventana = await chrome.windows.create({ url: 'about:blank', focused: false, state: 'minimized' });
  const destino = { tabId: ventana.tabs[0].id };
  await chrome.debugger.attach(destino, '1.3');
  const cdp = (metodo, params = {}) => chrome.debugger.sendCommand(destino, metodo, params);
  // mismo tamaño de ventana que usa Playwright en Python, para medir igual
  await cdp('Emulation.setDeviceMetricsOverride', { width: 1280, height: 720, deviceScaleFactor: 1, mobile: false });
  const { frameTree } = await cdp('Page.getFrameTree');

  async function poner(html) {
    await cdp('Page.setDocumentContent', { frameId: frameTree.frame.id, html });
    await cdp('Runtime.evaluate', {
      expression: `Promise.all([document.fonts.ready,
        ...[...document.images].map(i => i.complete ? 0 : new Promise(r => { i.onload = i.onerror = r; }))])
        .then(() => true)`,
      awaitPromise: true,
    });
  }

  return {
    async pdf(construir) {
      await poner(construir(null));
      const { result } = await cdp('Runtime.evaluate', {
        expression: `JSON.stringify([...document.querySelectorAll('.mod')]
          .map(m => Math.round(m.getBoundingClientRect().height) + 8))`,
        returnByValue: true,
      });
      const altos = JSON.parse(result.value || '[]');
      await poner(construir(altos.length ? altos : null));
      const { data } = await cdp('Page.printToPDF', {
        printBackground: true, paperWidth: 8.27, paperHeight: 11.7,
        marginTop: 0, marginBottom: 0, marginLeft: 0, marginRight: 0,
      });
      return data;
    },
    async cerrar() {
      await chrome.debugger.detach(destino).catch(() => {});
      await chrome.windows.remove(ventana.id).catch(() => {});
    },
  };
}

async function generarInformes(msg, avisar) {
  const sid = String(msg.alumno || '');
  if (!/^\d{1,12}$/.test(sid)) return { ok: false, error: 'id' };
  const resp = msg.respuestas;
  if (!resp || typeof resp !== 'object') return { ok: false, error: 'datos' };
  const idioma = idiomaInforme(msg.idioma);

  const lista = resp[rutas.grupos(sid)];
  if (!lista || lista.status !== 200) return { ok: false, error: 'grupos', status: lista && lista.status };
  const todos = gruposDeLista(lista.cuerpo);
  const grupos = todos.filter((g) => g.activo);
  const slugs = await leerJson('cursos/indice.json');
  const cargar = (slug, idi) => leerJson(`cursos/${idi}/curso_${slug}.json`).catch(() => null);

  const resultados = [];
  let motor = null;
  try {
    for (const grupo of todos) {
      // terminados o de los que salió: se dice en el aviso, en el orden de la ficha
      if (!grupo.activo) {
        resultados.push({ codigo: grupo.codigo, curso: grupo.curso, motivo: 'terminado' });
        continue;
      }
      avisar({ paso: 'grupo', n: grupos.indexOf(grupo) + 1, total: grupos.length, codigo: grupo.codigo });
      const r = await informeDeGrupo(resp, sid, grupo, idioma, slugs, cargar);
      if (!r.alumno) {
        resultados.push({ codigo: grupo.codigo, curso: grupo.curso, ...r });
        continue;
      }
      if (!motor) motor = await abrirMotor();
      const imagen = await banner(r.alumno.idioma);
      const pdf = await motor.pdf((altos) => buildHtml(r.curso, r.alumno, altos, imagen, msg.secciones));
      const archivo = nombreArchivo(r.alumno.alumno, grupo.codigo);
      await chrome.downloads.download({
        url: 'data:application/pdf;base64,' + pdf, filename: archivo,
        conflictAction: 'uniquify', saveAs: true,
      });
      resultados.push({ codigo: grupo.codigo, curso: grupo.curso, ok: true, archivo,
                        estado: r.estado, idioma: r.alumno.idioma });
    }
  } finally {
    if (motor) await motor.cerrar();
  }
  return { ok: true, resultados };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.tipo !== 'informe') return;  // no es para nosotros
  const tabId = sender.tab && sender.tab.id;
  const avisar = (progreso) => {
    if (tabId !== undefined) chrome.tabs.sendMessage(tabId, { tipo: 'progreso', ...progreso }).catch(() => {});
  };
  generarInformes(msg, avisar)
    .then(sendResponse)
    .catch((e) => sendResponse({ ok: false, error: 'excepcion', detalle: String((e && e.message) || e) }));
  return true;  // la respuesta llega de forma asíncrona
});
