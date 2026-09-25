// Arma el HTML del informe. Es el port a JavaScript de build_html de
// generar_reporte.py y tiene que producir EXACTAMENTE el mismo HTML: si se
// cambia allí hay que cambiarlo aquí, y pruebas/comparar_generadores.py lo
// comprueba carácter a carácter. Los textos y estilos no se duplican: vienen de
// textos.js, que genera sincronizar_extension.py.

import { UI, ESTILOS } from './textos.js';

// round() de Python: redondeo "del banquero" (round(2.5) == 2)
export function pyRound(x) {
  const f = Math.floor(x);
  const d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

// html.escape() de Python (con comillas)
export function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
}

// str.title() de Python para los títulos del pie
function titulo(s) {
  return s.replace(/\p{L}+/gu, (w) => w[0].toUpperCase() + w.slice(1).toLowerCase());
}

function sustituir(texto, alumno) {
  return (texto || '').split('{alumno}').join(alumno);
}

// len() de Python cuenta caracteres, no unidades UTF-16
function largo(s) {
  return [...String(s)].length;
}

// max()/min() de Python con key: ante empate gana el primero
function argMax(idx, val) {
  return idx.reduce((m, i) => (val[i] > val[m] ? i : m), idx[0]);
}
function argMin(idx, val) {
  return idx.reduce((m, i) => (val[i] < val[m] ? i : m), idx[0]);
}

export function pctPorModulo(progress) {
  const pares = (progress || []).map((m, i) => [
    m.module_number !== undefined ? m.module_number : i + 1,
    m.module_current_grade || 0,
    m.module_max_grade || 0,
  ]).sort((a, b) => a[0] - b[0]);
  return pares.map(([, cur, mx]) => (mx ? pyRound(100 * cur / mx) : 0));
}

function mensajeDesempeno(promedio, nombre, mods, pcts, ui) {
  const n = pcts.length;
  let idx = [];
  for (let i = 0; i < n; i++) if (pcts[i] > 0) idx.push(i);
  if (!idx.length) idx = [...Array(n).keys()];
  const mejor = idx.length ? mods[argMax(idx, pcts)].titulo : '';
  const peorI = idx.length ? argMin(idx, pcts) : 0;
  const peor = idx.length ? mods[peorI].titulo : '';
  const peorPct = idx.length ? pcts[peorI] : 0;
  const nivel = promedio >= 85 ? 0 : promedio >= 70 ? 1 : promedio >= 50 ? 2 : 3;
  return ui.msg_textos[nivel].split('{nombre}').join(String(nombre))
    .split('{mejor}').join(mejor).split('{peor}').join(peor)
    .split('{peor_pct}').join(String(peorPct));
}

function banda(pct, ui) {
  if (pct >= 70) return [ui.et_otimo, 'otimo'];
  if (pct >= 50) return [ui.et_bom, 'bom'];
  return [ui.et_dev, 'dev'];
}

// banner: data URI de la imagen (con el texto en el idioma del informe)
export function buildHtml(curso, alumno, altos = null, banner = '') {
  const idioma = alumno.idioma || curso.idioma || 'es';
  const ui = UI[idioma] || UI.es;
  const nombre = alumno.alumno;
  let pcts = alumno.pct;
  let mods = curso.modulos;
  const n = Math.min(mods.length, pcts.length);
  mods = mods.slice(0, n);
  pcts = pcts.slice(0, n).map((p) => Math.max(0, Math.min(100, pyRound(p))));

  let cursados = [];
  for (let i = 0; i < n; i++) if (pcts[i] > 0) cursados.push(i);
  if (!cursados.length) cursados = [...Array(n).keys()];
  const promedio = cursados.length
    ? pyRound(cursados.reduce((s, i) => s + pcts[i], 0) / cursados.length) : 0;
  const mejorI = cursados.length ? argMax(cursados, pcts) : 0;
  const mejorPct = n ? pcts[mejorI] : 0;
  const mejorMod = n ? mods[mejorI].numero : 0;

  const tareas = alumno.tareas;
  const puntos = alumno.puntos;
  const asis = alumno.asistencia;
  const combinado = Boolean(asis || (tareas && tareas.length));
  const tEnv = tareas ? tareas.reduce((s, [e]) => s + e, 0) : 0;
  const tTot = tareas ? tareas.reduce((s, [, t]) => s + t, 0) : 0;
  const aSi = asis ? asis.asistidas : 0;
  const aTot = asis ? asis.total : 0;

  let statsHtml;
  if (combinado) {
    statsHtml =
      `<div class="stat oscuro"><div class="num">${promedio}<small>%</small></div><div class="lbl">${ui.aprov}</div></div>` +
      `<div class="stat"><div class="num">${tEnv}<small>/${tTot}</small></div><div class="lbl">${ui.tareas}</div></div>` +
      `<div class="stat"><div class="num">${aSi}<small>/${aTot}</small></div><div class="lbl">${ui.asist}</div></div>` +
      `<div class="stat"><div class="num">${mejorPct}<small>%</small></div><div class="lbl">${ui.mejor} (M${mejorMod})</div></div>`;
  } else {
    statsHtml =
      `<div class="stat oscuro"><div class="num">${promedio}<small>%</small></div><div class="lbl">${ui.aprov}</div></div>` +
      `<div class="stat"><div class="num">${n}</div><div class="lbl">${ui.proyectos}</div></div>` +
      `<div class="stat"><div class="num">${mejorPct}<small>%</small></div><div class="lbl">${ui.mejor} (M${mejorMod})</div></div>` +
      `<div class="stat"><div class="num">${n}</div><div class="lbl">${ui.modulos}</div></div>`;
  }

  const msg = n ? mensajeDesempeno(promedio, nombre, mods, pcts, ui) : '';
  const mensajeHtml = msg
    ? `<div class="mensaje"><div class="k">${ui.msg}</div><p>${esc(msg)}</p></div>` : '';

  // --- carátula ---
  const d = alumno.datos || {};
  const modInf = d.modulo_informe ||
    ((n && cursados.length) ? `M${mods[cursados[cursados.length - 1]].numero}` : '');

  const celda = (v) => {
    const t = String(v || '').trim();
    return t ? `<td>${esc(t)}</td>` : '<td class="vacio">—</td>';
  };
  const filasDb = [
    [ui.f_alumno, nombre, ui.f_cod, d.codigo_grupo || ''],
    [ui.f_acu, d.acudiente || '', ui.f_tipo, d.tipo_grupo || ''],
    [ui.f_mail, d.email || '', ui.f_dia, d.dia_hora || ''],
    [ui.f_tel, d.telefono || '', ui.f_mod, modInf],
    [ui.f_pais, d.pais || '', ui.curso, curso.curso || ''],
  ];
  const tablaDb = filasDb.map(([a, b, c, e]) =>
    `<tr><th>${esc(a)}</th>${celda(b)}<th>${esc(c)}</th>${celda(e)}</tr>`).join('');

  let obj = curso.objetivo_informe || ui.objetivo_def;
  obj = sustituir(obj, nombre).split('{curso}').join(curso.curso || '');
  const items = ui.modo_items.map(([t, x]) => `<li><b>${esc(t)}</b> — ${esc(x)}</li>`).join('');

  const caratula = `
<div class="pagina">
  ${banner ? `<img class="banner" src="${banner}">` : ''}
  <div class="seccion"><div class="cuad"></div><h2>${ui.datos}</h2></div>
  <table class="dbasicos">${tablaDb}</table>

  <div class="seccion"><div class="cuad"></div><h2>${ui.objetivo}</h2></div>
  <div class="intro">${esc(obj)}</div>

  <div class="seccion"><div class="cuad"></div><h2>${ui.modo}</h2></div>
  <div class="modo">
    <ol>${items}</ol>
    <div class="pie-modo">${esc(sustituir(ui.modo_pie, nombre))}</div>
  </div>
  <div class="pie-num">Kodland · ${titulo(ui.titulo)} · ${ui.pagina} 1</div>
</div>
`;

  // --- portada ---
  let barras = '';
  const maxAlto = 175;
  mods.forEach((m, i) => {
    const p = pcts[i];
    const [, cls] = banda(p, ui);
    const alto = Math.trunc(maxAlto * p / 100);
    barras += `<div class="col ${cls}"><div class="pct">${p}%</div>` +
              `<div class="barra" style="height:${alto}px"></div></div>`;
  });
  const ejes = mods.map((m) => `<div class="e">M${m.numero}</div>`).join('');
  const mediaTop = Math.trunc(210 - (175 * promedio / 100));
  const enNegrita = (txt) => esc(sustituir(txt, nombre)).split(esc(nombre)).join('<b>' + esc(nombre) + '</b>');

  const portada = `
<div class="pagina">
  <div class="cab">
    <div class="logo">kodland</div>
    <div class="tit"><h1>${ui.titulo}</h1><p>${esc(nombre)} · ${esc(curso.curso)}</p></div>
  </div>

  <div class="fila">
    <div class="tarj"><div class="mut">${ui.area}</div><div class="val">${esc(curso.area_interes || '')}</div></div>
    <div class="tarj"><div class="mut">${ui.proximo}</div><div class="val">${esc(curso.proximo_nivel || '')}</div></div>
  </div>

  <div class="stats">${statsHtml}</div>

  <div class="seccion"><div class="cuad"></div><h2>${ui.vision}</h2></div>
  <div class="intro">${enNegrita(curso.vision_general || '')}</div>

  <div class="chart">
    <div class="barras">
      ${barras}
      <div class="media-linea" style="top:${mediaTop}px"></div>
      <div class="media-lbl" style="top:${mediaTop - 14}px">${ui.media} ${promedio}%</div>
    </div>
    <div class="ejes">${ejes}</div>
    <div class="leyenda">
      <span><i class="punto otimo"></i>${ui.bandas[0]}</span>
      <span><i class="punto bom"></i>${ui.bandas[1]}</span>
      <span><i class="punto dev"></i>${ui.bandas[2]}</span>
    </div>
  </div>
  ${mensajeHtml}
  <div class="pie-num">Kodland · ${titulo(ui.titulo)} · ${ui.pagina} 2</div>
</div>
`;

  // --- calificaciones y asistencia ---
  let califHtml = '';
  if (combinado) {
    let filas = '';
    mods.forEach((m, i) => {
      const p = pcts[i];
      const [, cls] = banda(p, ui);
      const [te, tt] = tareas && i < tareas.length ? tareas[i] : [0, 0];
      const [pc, px] = puntos && i < puntos.length ? puntos[i] : [0, 0];
      filas += `<tr><td>M${m.numero} · ${esc(m.titulo)}</td>` +
               `<td class="n">${te}/${tt}</td><td class="n">${pc}/${px}</td>` +
               `<td><span class="mini"><i class="${cls}" style="width:${p}%"></i></span>${p}%</td></tr>`;
    });
    const totPc = puntos ? puntos.reduce((s, [pc]) => s + pc, 0) : 0;
    const totPx = puntos ? puntos.reduce((s, [, px]) => s + px, 0) : 0;
    filas += `<tr class="total"><td>TOTAL</td><td class="n">${tEnv}/${tTot}</td>` +
             `<td class="n">${totPc}/${totPx}</td><td>${promedio}%</td></tr>`;
    const et = { presente: ['pres', ui.est_pres], ausente: ['aus', ui.est_aus],
                 justificada: ['just', ui.est_just] };
    let sesHtml = '';
    for (const s of (asis ? asis.sesiones : [])) {
      const [c, txt] = et[s.estado] || ['aus', s.estado];
      sesHtml += `<div class="ses ${c}"><div class="f">${esc(s.fecha)}</div><div class="e">${txt}</div></div>`;
    }
    const asisBloque = asis
      ? `<div class="seccion"><div class="cuad"></div><h2>${ui.asis_titulo}</h2></div>` +
        `<div class="asis-grid">${sesHtml}</div>` : '';
    califHtml = `
<div class="pagina">
  <div class="seccion"><div class="cuad"></div><h2>${ui.calif}</h2></div>
  <table class="calif">
    <tr><th>${ui.th_modulo}</th><th class="n">${ui.th_tareas}</th><th class="n">${ui.th_puntos}</th><th>${ui.th_avance}</th></tr>
    ${filas}
  </table>
  ${asisBloque}
  <div class="pie-num">Kodland · ${ui.pagina}</div>
</div>
`;
  }

  // --- detalle por módulo: se llena cada hoja hasta donde cabe ---
  let ALTO_HOJA = 995;
  let ALTO_HOJA_1 = 943;
  const altoMod = (m) => {
    const lineas = (txt, porLinea) => Math.max(1, Math.ceil(largo(txt || '') / porLinea));
    return 125 + 18 * lineas(m.descripcion || '', 128) +
      18 * (m.aprendizajes || []).reduce((s, a) => s + lineas(a, 46), 0);
  };
  const medido = Boolean(altos && altos.length) && altos.length >= n;
  const alturas = medido ? altos.slice(0, n) : mods.map(altoMod);
  if (medido) { ALTO_HOJA = 1005; ALTO_HOJA_1 = 953; }

  const repartir = () => {
    const hojas = [];
    let act = [];
    let alto = 0;
    alturas.forEach((a, i) => {
      const tope = hojas.length ? ALTO_HOJA : ALTO_HOJA_1;
      if (act.length && alto + a > tope) {
        hojas.push(act);
        act = [];
        alto = 0;
      }
      act.push(i);
      alto += a;
    });
    if (act.length) hojas.push(act);
    return hojas;
  };
  const gruposMod = n ? repartir() : [];
  for (let k = gruposMod.length - 1; k > 0; k--) {
    while (gruposMod[k - 1].length - gruposMod[k].length >= 2) {
      const i = gruposMod[k - 1][gruposMod[k - 1].length - 1];
      if (gruposMod[k].reduce((s, j) => s + alturas[j], 0) + alturas[i] > ALTO_HOJA) break;
      gruposMod[k].unshift(gruposMod[k - 1].pop());
    }
  }

  let paginasMod = '';
  let primera = true;
  for (const grupo of gruposMod) {
    let cuerpo = '';
    if (primera) {
      cuerpo += `<div class="seccion"><div class="cuad"></div><h2>${ui.detalle}</h2></div>`;
      primera = false;
    }
    for (const i of grupo) {
      const m = mods[i];
      const p = pcts[i];
      const [lbl, cls] = banda(p, ui);
      const aprs = (m.aprendizajes || []).map((a) => `<li>${esc(a)}</li>`).join('');
      const desc = esc(sustituir(m.descripcion || '', nombre));
      cuerpo += `
  <div class="mod">
    <div class="mod-cab">
      <div class="badge">${String(m.numero).padStart(2, '0')}</div>
      <div class="t"><div class="n">${ui.modulo} ${m.numero}</div><h3>${esc(m.titulo)}</h3></div>
      <div class="p"><div class="g">${p}<small>%</small></div><span class="pill ${cls}">${lbl}</span></div>
    </div>
    <div class="progreso"><i class="${cls}" style="width:${p}%"></i></div>
    <div class="desc">${desc}</div>
    <div class="mod-cols">
      <div class="izq"><div class="sublbl">${ui.aprendizajes}</div><ul class="apr">${aprs}</ul></div>
      <div class="der"><div class="sublbl">${ui.proyecto}</div><div class="proy">${esc(m.proyecto || '')}</div></div>
    </div>
  </div>`;
    }
    paginasMod += `<div class="pagina">${cuerpo}<div class="pie-num">Kodland · ${ui.pagina}</div></div>`;
  }

  // --- cierre ---
  const comp = (curso.competencias || []).map((c) => `<div class="c"><b>✓</b>${esc(c)}</div>`).join('');
  const paso = curso.proximo_paso || {};
  const cierre = `
<div class="pagina">
  <div class="seccion"><div class="cuad"></div><h2>${ui.consideraciones}</h2></div>
  <div class="intro">${enNegrita(curso.consideraciones || '')}</div>
  <div class="comp">${comp}</div>

  <div class="paso">
    <div class="k">${ui.paso}</div>
    <h2>→ ${esc(paso.titulo || '')}</h2>
    <p>${esc(sustituir(paso.texto || '', nombre))}</p>
  </div>

  <div class="firmas">
    <div class="col-tutor">
      <div class="fnombre">${esc(alumno.profesor || '') || '&nbsp;'}</div>
      <div class="frol">${ui.tutor}</div>
    </div>
    <div class="copy">© Kodland, ${new Date().getFullYear()}</div>
  </div>

  <div class="pie">
    <div class="barra"><span class="l">kodland</span><span class="c">${ui.pie_lema}</span><span style="color:#fff;font-weight:700;font-size:11px">kodland.com.br</span></div>
  </div>
  <div class="pie-num">Kodland · ${ui.pagina}</div>
</div>
`;

  return `<!doctype html><html><head><meta charset='utf-8'><style>${ESTILOS}</style></head><body>${caratula}${portada}${califHtml}${paginasMod}${cierre}</body></html>`;
}
