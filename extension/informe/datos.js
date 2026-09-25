// De las respuestas de la API a los datos de cada informe. Es el port de la
// parte de generar_reportes_grupo (kodland_datos.py) que no toca el navegador:
// elegir el curso, calcular porcentajes, tareas y asistencia, y la carátula.
// pruebas/comparar_generadores.py comprueba que da lo mismo que Python.

import { pctPorModulo } from './generador.js';

export const DIAS = {
  es: { 1: 'Lunes', 2: 'Martes', 3: 'Miércoles', 4: 'Jueves', 5: 'Viernes', 6: 'Sábado', 7: 'Domingo' },
  pt: { 1: 'Segunda-feira', 2: 'Terça-feira', 3: 'Quarta-feira', 4: 'Quinta-feira',
        5: 'Sexta-feira', 6: 'Sábado', 7: 'Domingo' },
};

// "pt-BR", "es-ES" (cookie materio-language) -> "pt" / "es"
export function idiomaInforme(valor) {
  const corto = String(valor || '').trim().toLowerCase().slice(0, 2);
  return corto in DIAS ? corto : 'es';
}

export const rutas = {
  grupos: (sid) => `/students/${sid}/backoffice_groups/`,
  alumno: (sid) => `/students/${sid}/get_general_info_for_student_backoffice_page/`,
  infoGrupo: (gid) => `/student_groups/${gid}/get_general_info_for_group_backoffice_page`,
  alumnosGrupo: (gid) => `/student_groups/${gid}/get_students_main_data`,
  tareasClase: (sid, lid) => `/students/${sid}/lesson/${lid}/get_progress_for_class_tasks/`,
  tareasDeberes: (sid, lid) => `/students/${sid}/lesson/${lid}/get_progress_for_homework_tasks/`,
};

const esObjeto = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

// Grupos de /students/<ID>/backoffice_groups/. `activo` es si el alumno sigue
// en el grupo: los de cursos terminados o de los que salió vienen con otro
// status ("expelled"…) y no llevan informe (como grupos_de_lista en Python).
export function gruposDeLista(lista) {
  return (Array.isArray(lista) ? lista : [])
    .filter((g) => esObjeto(g) && g.group_id)
    .map((g) => ({
      gid: String(g.group_id),
      codigo: String(g.group_title || `grupo_${g.group_id}`).trim(),
      curso: (g.course_title || '').replace(/^\[\d+\]/, '').split('[')[0].trim(),
      estado: g.status || '',
      activo: String(g.status || '').toLowerCase() === 'active',
    }));
}

// Palabras de un título o slug; separa letra-dígito ("lvl2" -> "lvl 2")
function palabras(s) {
  return String(s).toLowerCase()
    .replace(/([a-z])(\d)/g, '$1 $2').replace(/(\d)([a-z])/g, '$1 $2')
    .split(/[^a-z0-9]+/).filter(Boolean);
}

// Curso cuyo slug tiene todas sus palabras en el título; ante varios, el más
// específico (más palabras) y, a igualdad, el último por orden alfabético,
// como max() sobre (n_palabras, ruta) en Python.
export function elegirCurso(tituloApi, slugs) {
  const enTitulo = new Set(palabras(tituloApi));
  let mejor = null;
  for (const slug of slugs) {
    const p = palabras(slug);
    if (!p.length || !p.every((w) => enTitulo.has(w))) continue;
    if (!mejor || p.length > mejor.n || (p.length === mejor.n && slug > mejor.slug)) {
      mejor = { slug, n: p.length };
    }
  }
  return mejor ? mejor.slug : null;
}

function contable(t) {
  return (t.task_max_grade || 0) > 0 && t.task_status_key !== 'TASK_NOT_GRADED';
}
function enviada(t) {
  return t.task_status_key !== undefined && t.task_status_key !== null &&
    t.task_status_key !== 'TASK_NOT_SUBMITTED';
}
export function contarTareas(...listas) {
  let env = 0;
  let tot = 0;
  for (const lst of listas) {
    for (const t of (Array.isArray(lst) ? lst : [])) {
      if (contable(t)) {
        tot += 1;
        if (enviada(t)) env += 1;
      }
    }
  }
  return [env, tot];
}

// _primer_valor de Python: primer valor no vacío entre varias claves,
// bajando un par de niveles si no está arriba
function primerValor(dic, claves, hondo = 0) {
  if (!esObjeto(dic) || hondo > 2) return '';
  for (const k of claves) {
    const v = dic[k];
    if ((typeof v === 'string' || typeof v === 'number') && String(v).trim()) return String(v).trim();
  }
  for (const v of Object.values(dic)) {
    if (esObjeto(v)) {
      const r = primerValor(v, claves, hondo + 1);
      if (r) return r;
    }
  }
  return '';
}

function tipoGrupo(info) {
  const kind = info.group_kind;
  const t = esObjeto(kind) ? (kind.title || '') : String(kind || '');
  let tipo = t.replace(/^\[\d+\]\s*/, '').split(',')[0].trim();
  if (tipo && info.group_is_premium) tipo += ' (premium)';
  return tipo;
}

function diaHora(info, idioma) {
  const horario = info.group_schedule;
  if (!Array.isArray(horario)) return '';
  const dias = DIAS[idioma] || DIAS.es;
  const partes = horario.filter(esObjeto)
    .map((h) => `${dias[h.day] || ''} ${h.time || ''}`.trim());
  const texto = partes.filter(Boolean).join(idioma === 'pt' ? ' e ' : ' y ');
  const zona = info.group_timezone;
  const offset = esObjeto(zona) ? zona.offset_utc : '';
  return texto && offset ? `${texto} (${offset})` : texto;
}

function datosCaratula(main, infoGrupo, codigo, infoAlumno, idioma) {
  const alumno = esObjeto(infoAlumno) ? infoAlumno : {};
  return {
    acudiente: primerValor(alumno, ['parent_name']) ||
      primerValor(main, ['parent_name', 'parent_full_name', 'representative_name', 'parent']),
    email: primerValor(alumno, ['parent_email']) ||
      primerValor(main, ['email', 'student_email', 'parent_email', 'login']),
    telefono: primerValor(alumno, ['parent_phone', 'student_phone']) ||
      primerValor(main, ['phone', 'phone_number', 'parent_phone', 'telephone']),
    pais: primerValor(alumno, ['client_country']) || primerValor(main, ['country', 'country_name']),
    codigo_grupo: codigo,
    tipo_grupo: tipoGrupo(infoGrupo),
    dia_hora: diaHora(infoGrupo, idioma),
  };
}

const ATT = { 2: 'presente', 1: 'justificada', 0: 'ausente' };

// Datos del informe de `sid` en un grupo. Devuelve {alumno} para build_html,
// o {motivo} si no hay informe que hacer.
// cargarCurso(slug, idioma) -> contenido del curso o null si no existe.
export async function informeDeGrupo(resp, sid, grupo, idioma, slugs, cargarCurso) {
  const api = (ruta) => resp[ruta] || { status: 404, cuerpo: null };
  const cuerpo200 = (r) => (r.status === 200 ? r.cuerpo : null);

  let infoGrupo = cuerpo200(api(rutas.infoGrupo(grupo.gid)));
  if (!esObjeto(infoGrupo)) infoGrupo = {};
  const tituloCurso = (esObjeto(infoGrupo.course) && infoGrupo.course.title) || '';
  const gt = infoGrupo.group_teacher;
  const profesor = (esObjeto(gt) && gt.full_name) || '';

  if (infoGrupo.passed_lessons_count === 0) {
    const inicio = String(infoGrupo.group_start_time || '').split(' ')[0];
    return { motivo: 'sin_empezar', inicio };
  }
  if (infoGrupo.group_graduated || infoGrupo.group_is_archive) return { motivo: 'terminado' };
  const slug = elegirCurso(tituloCurso, slugs.es);
  if (!slug) return { motivo: 'sin_curso', titulo: tituloCurso };
  let curso = null;
  if (idioma !== 'es' && (slugs[idioma] || []).includes(slug)) curso = await cargarCurso(slug, idioma);
  if (!curso) {
    idioma = 'es';   // sin traducción: entero en español, sin mezclar
    curso = await cargarCurso(slug, 'es');
  }

  const alumnos = cuerpo200(api(rutas.alumnosGrupo(grupo.gid)));
  if (!Array.isArray(alumnos)) return { motivo: 'sin_alumnos' };
  const s = alumnos.find((a) => String((a.main_info || {}).student_id) === String(sid));
  if (!s) return { motivo: 'no_esta' };
  const main = s.main_info || {};
  const prog = s.progress_info || [];

  let nombre = main.full_name || `Alumno ${sid}`;
  const infoAlumno = cuerpo200(api(rutas.alumno(sid)));
  if (esObjeto(infoAlumno)) {
    const completo = String(infoAlumno.student_full_name || '').trim();
    const nPal = (t) => t.split(/\s+/).filter(Boolean).length;
    if (nPal(completo) > nPal(nombre)) nombre = completo;
  }

  const pct = pctPorModulo(prog);
  const modsOrd = prog.map((m, i) => [m, i])
    .sort((a, b) => (a[0].module_number || 0) - (b[0].module_number || 0) || a[1] - b[1])
    .map(([m]) => m).slice(0, pct.length);
  const puntos = [];
  const tareas = [];
  const ses = [];
  for (const mm of modsOrd) {
    puntos.push([mm.module_current_grade || 0, mm.module_max_grade || 0]);
    let env = 0;
    let tot = 0;
    for (const l of mm.lessons_data || []) {
      const [e, t] = contarTareas(cuerpo200(api(rutas.tareasClase(sid, l.lesson_id))),
                                  cuerpo200(api(rutas.tareasDeberes(sid, l.lesson_id))));
      env += e;
      tot += t;
      if (l.attendance_status in ATT) {
        ses.push({ fecha: `M${mm.module_number} L${l.lesson_number}`, estado: ATT[l.attendance_status] });
      }
    }
    tareas.push([env, tot]);
  }
  const asistencia = {
    asistidas: ses.filter((x) => x.estado === 'presente').length,
    total: ses.length,
    sesiones: ses,
  };
  return {
    alumno: {
      alumno: nombre, profesor, pct, idioma, puntos, tareas, asistencia,
      datos: datosCaratula(main, infoGrupo, grupo.codigo, infoAlumno, idioma),
    },
    curso,
    estado: main.status || '',
  };
}

// Nombre que se sugiere al guardar: "<alumno> - <código del grupo>.pdf", sin
// caracteres que Windows no admite en un nombre de archivo
export function nombreArchivo(nombre, codigo) {
  const limpio = (t) => [...String(t || '')]
    .filter((ch) => /[\p{L}\p{N}]/u.test(ch) || ' _-.'.includes(ch)).join('').trim();
  return [limpio(nombre) || 'alumno', limpio(codigo)].filter(Boolean).join(' - ') + '.pdf';
}
