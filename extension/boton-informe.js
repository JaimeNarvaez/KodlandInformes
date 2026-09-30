// Botón "Generar informe" en la ficha del alumno (bo.kodland.org/students/<ID>).
//
// Reúne aquí, con la sesión que ya tiene abierta quien lo usa, las respuestas
// de la API que necesita el informe y se las pasa a background.js, que arma los
// PDF dentro del propio Chrome. No hace falta instalar nada más ni tener cuenta
// de tutor: sirve para cualquier cuenta que pueda ver la ficha (ventas / ISM).
//
// El backoffice es una SPA (Vuetify): no recarga la página al pasar de un
// grupo a un alumno, así que se vigila la URL y el botón aparece o desaparece.

(function () {
  if (window.__kiBotonInforme) return;   // evitar duplicados
  window.__kiBotonInforme = true;

  const ID_BOTON = 'ki-boton-informe';
  const API = 'https://backoffice.kodland.org/api/v2';
  const EN_PARALELO = 6;   // consultas de tareas a la vez, para no saturar

  // textos del botón en el idioma de la página
  const TXT = {
    es: {
      boton: '📄 Generar informe',
      ayuda: 'Genera el PDF de desarrollo de este alumno (uno por cada grupo en que esté)',
      grupos: '⏳ Leyendo los grupos del alumno…',
      tareas: (p) => `⏳ Leyendo tareas y asistencia… ${p} %`,
      grupo: (n, t, c) => `⏳ Preparando el informe ${n} de ${t} (${c})…`,
      permiso: (s) => `Kodland no dio permiso (${s}). Recarga la página (F5) y reintenta.`,
      sinGrupos: (s) => `No pude leer los grupos del alumno (status ${s}).`,
      hecho: (n) => `✅ ${n === 1 ? 'Informe generado' : n + ' informes generados'}.`,
      ninguno: 'No se generó ningún informe.',
      motivos: {
        sin_empezar: (r) => `el grupo aún no ha empezado${r.inicio ? ' (primera clase el ' + r.inicio + ')' : ''}`,
        terminado: () => 'grupo terminado o el alumno ya no está en él',
        sin_curso: () => 'falta el contenido de este curso en la extensión',
        sin_alumnos: () => 'no se pudo leer la lista de alumnos del grupo',
        no_esta: () => 'el alumno no figura en la lista del grupo',
      },
      error: 'No se pudo generar el informe',
      recargar: 'La extensión se actualizó: recarga esta página (F5) y vuelve a intentarlo.',
      secciones: 'Secciones del informe',
      sec: {
        notas: 'Notas y asistencia',
        asistencia: 'Asistencia a clases',
        modulos: 'Detalle por módulo',
        consideraciones: 'Consideraciones finales',
      },
    },
    pt: {
      boton: '📄 Gerar relatório',
      ayuda: 'Gera o PDF de desenvolvimento deste aluno (um para cada turma em que ele estiver)',
      grupos: '⏳ Lendo as turmas do aluno…',
      tareas: (p) => `⏳ Lendo tarefas e presença… ${p} %`,
      grupo: (n, t, c) => `⏳ Preparando o relatório ${n} de ${t} (${c})…`,
      permiso: (s) => `O Kodland não deu permissão (${s}). Recarregue a página (F5) e tente de novo.`,
      sinGrupos: (s) => `Não consegui ler as turmas do aluno (status ${s}).`,
      hecho: (n) => `✅ ${n === 1 ? 'Relatório gerado' : n + ' relatórios gerados'}.`,
      ninguno: 'Nenhum relatório foi gerado.',
      motivos: {
        sin_empezar: (r) => `a turma ainda não começou${r.inicio ? ' (primeira aula em ' + r.inicio + ')' : ''}`,
        terminado: () => 'turma encerrada ou o aluno não está mais nela',
        sin_curso: () => 'falta o conteúdo deste curso na extensão',
        sin_alumnos: () => 'não foi possível ler a lista de alunos da turma',
        no_esta: () => 'o aluno não aparece na lista da turma',
      },
      error: 'Não foi possível gerar o relatório',
      recargar: 'A extensão foi atualizada: recarregue esta página (F5) e tente de novo.',
      secciones: 'Seções do relatório',
      sec: {
        notas: 'Notas e presença',
        asistencia: 'Presença nas aulas',
        modulos: 'Detalhamento por módulo',
        consideraciones: 'Considerações finais',
      },
    },
  };

  function idAlumno() {
    const m = location.pathname.match(/^\/students\/(\d+)\/?$/);
    return m ? m[1] : null;
  }

  function cookie(nombre) {
    const m = document.cookie.match(new RegExp('(?:^|;\\s*)' + nombre + '=([^;]+)'));
    return m ? decodeURIComponent(m[1]) : '';
  }

  // idioma elegido en el backoffice (cookie materio-language: "es-ES", "pt-BR"…)
  function idiomaPagina() {
    const corto = cookie('materio-language').slice(0, 2).toLowerCase();
    return corto in TXT ? corto : 'es';
  }
  const t = () => TXT[idiomaPagina()];

  // la web manda el token de la cookie "access" como Bearer; solo con las
  // cookies la API responde 401
  async function pedir(ruta) {
    const token = cookie('access');
    try {
      const r = await fetch(API + ruta, {
        credentials: 'include',
        headers: Object.assign({ Accept: 'application/json' },
                               token ? { Authorization: 'Bearer ' + token } : {}),
      });
      let cuerpo = null;
      try { cuerpo = await r.json(); } catch (e) { /* sin JSON */ }
      return { status: r.status, cuerpo };
    } catch (e) {
      return { status: -1, cuerpo: null };
    }
  }

  // Las mismas rutas que consulta generar_reportes_grupo en kodland_datos.py
  // (y informe/datos.js, que es quien las lee).
  async function reunir(sid, avisar) {
    const resp = {};
    const guardar = async (ruta) => (resp[ruta] = await pedir(ruta));

    avisar(t().grupos);
    const lista = await guardar(`/students/${sid}/backoffice_groups/`);
    if (lista.status === 401 || lista.status === 403) throw new Error(t().permiso(lista.status));
    if (lista.status !== 200) throw new Error(t().sinGrupos(lista.status));
    await guardar(`/students/${sid}/get_general_info_for_student_backoffice_page/`);

    const lecciones = [];
    for (const g of Array.isArray(lista.cuerpo) ? lista.cuerpo : []) {
      const gid = g && g.group_id;
      // grupos terminados o de los que salió: no llevan informe (ver datos.js)
      if (!gid || String(g.status || '').toLowerCase() !== 'active') continue;
      const info = await guardar(`/student_groups/${gid}/get_general_info_for_group_backoffice_page`);
      const c = info.cuerpo || {};
      if (c.passed_lessons_count === 0 || c.group_graduated || c.group_is_archive) continue;
      const alumnos = await guardar(`/student_groups/${gid}/get_students_main_data`);
      const suyo = (Array.isArray(alumnos.cuerpo) ? alumnos.cuerpo : [])
        .find((a) => String((a.main_info || {}).student_id) === sid);
      for (const m of (suyo && suyo.progress_info) || []) {
        for (const l of m.lessons_data || []) {
          if (l.lesson_id) lecciones.push(l.lesson_id);
        }
      }
    }

    const rutas = lecciones.flatMap((lid) => [
      `/students/${sid}/lesson/${lid}/get_progress_for_class_tasks/`,
      `/students/${sid}/lesson/${lid}/get_progress_for_homework_tasks/`,
    ]);
    for (let i = 0; i < rutas.length; i += EN_PARALELO) {
      avisar(t().tareas(Math.round(100 * i / rutas.length)));
      await Promise.all(rutas.slice(i, i + EN_PARALELO).map(guardar));
    }
    return resp;
  }

  // Resumen para quien pulsó el botón: qué se guardó y qué no, y por qué
  function resumen(resp) {
    const tx = t();
    if (!resp.ok) {
      if (resp.error === 'grupos') return [tx.sinGrupos(resp.status), true];
      return [`${tx.error}${resp.detalle ? ': ' + resp.detalle : '.'}`, true];
    }
    const hechos = resp.resultados.filter((r) => r.ok);
    const lineas = hechos.length ? [tx.hecho(hechos.length)] : [tx.ninguno];
    for (const r of resp.resultados) {
      if (r.ok) lineas.push(`• ${r.codigo}`);
      else lineas.push(`• ${r.codigo}: ${(tx.motivos[r.motivo] || (() => r.motivo))(r)}`);
    }
    return [lineas.join('\n'), !hechos.length];
  }

  function estilo(el, obj) { Object.assign(el.style, obj); }

  function crearBoton() {
    const caja = document.createElement('div');
    caja.id = ID_BOTON;
    // abajo a la IZQUIERDA: abajo a la derecha está el panel de KodlandFaster
    estilo(caja, {
      position: 'fixed', bottom: '18px', left: '18px', zIndex: 2147483646,
      display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '6px',
      fontFamily: 'Segoe UI, system-ui, sans-serif',
    });

    const estado = document.createElement('div');
    estado.id = 'ki-aviso';
    estilo(estado, {
      display: 'none', maxWidth: '320px', padding: '8px 10px', borderRadius: '8px',
      background: '#fff', color: '#223', fontSize: '12px', whiteSpace: 'pre-wrap',
      boxShadow: '0 2px 10px rgba(0,0,0,.2)',
    });

    const boton = document.createElement('button');
    boton.id = 'ki-generar';
    boton.textContent = t().boton;
    boton.title = t().ayuda;
    estilo(boton, {
      background: '#6c2bd9', color: '#fff', border: 'none', borderRadius: '24px',
      padding: '10px 16px', fontWeight: '600', fontSize: '14px', cursor: 'pointer',
      boxShadow: '0 2px 10px rgba(0,0,0,.25)',
    });

    // Casillas para elegir qué lleva el informe. Siempre arrancan todas
    // marcadas: nadie debe generar un informe recortado sin querer.
    const panel = document.createElement('div');
    estilo(panel, {
      display: 'none', padding: '10px 12px', borderRadius: '8px', background: '#fff',
      color: '#223', fontSize: '13.5px', boxShadow: '0 2px 10px rgba(0,0,0,.2)',
    });
    const casillas = {};
    for (const clave of ['notas', 'asistencia', 'modulos', 'consideraciones']) {
      const fila = document.createElement('label');
      estilo(fila, {
        display: 'flex', alignItems: 'center', gap: '8px',
        padding: '4px 0', cursor: 'pointer', whiteSpace: 'nowrap',
      });
      const marca = document.createElement('input');
      marca.type = 'checkbox';
      marca.checked = true;
      estilo(marca, { width: '16px', height: '16px', margin: '0', cursor: 'pointer' });
      casillas[clave] = marca;
      const texto = document.createElement('span');
      texto.textContent = t().sec[clave];
      fila.appendChild(marca);
      fila.appendChild(texto);
      panel.appendChild(fila);
    }

    // El enlace no tiene fondo propio, así que hereda el de la página. El
    // backoffice tiene tema claro y oscuro: sobre el oscuro el morado del botón
    // se pierde, así que se aclara sólo cuando hace falta.
    const fondoOscuro = () => {
      for (const el of [document.body, document.documentElement]) {
        const n = el && getComputedStyle(el).backgroundColor.match(/[\d.]+/g);
        if (n && n.length >= 3 && (n.length < 4 || Number(n[3]) > 0)) {
          return 0.299 * Number(n[0]) + 0.587 * Number(n[1]) + 0.114 * Number(n[2]) < 140;
        }
      }
      return true;   // sin fondo declarado, el del backoffice es oscuro
    };

    const alterna = document.createElement('button');
    alterna.textContent = '⚙ ' + t().secciones;
    estilo(alterna, {
      background: 'none', border: 'none', padding: '4px 2px',
      color: fondoOscuro() ? '#c9b3ff' : '#6c2bd9',
      fontSize: '14px', fontWeight: '600', cursor: 'pointer', textAlign: 'left',
    });
    alterna.addEventListener('click', () => {
      panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    });

    function avisar(texto, error) {
      estado.textContent = texto;
      estado.style.color = error ? '#b3261e' : '#223';
      estado.style.display = 'block';
    }

    // progreso que va mandando background.js mientras arma los PDF
    chrome.runtime.onMessage.addListener((msg) => {
      if (msg && msg.tipo === 'progreso' && msg.paso === 'grupo') {
        avisar(t().grupo(msg.n, msg.total, msg.codigo));
      }
    });

    function enviar(alumno, respuestas, secciones) {
      return new Promise((resolve) => {
        chrome.runtime.sendMessage({ tipo: 'informe', alumno, respuestas, secciones, idioma: idiomaPagina() }, (resp) => {
          if (chrome.runtime.lastError) {
            resolve({ ok: false, error: 'excepcion', detalle: chrome.runtime.lastError.message });
          } else {
            resolve(resp || { ok: false, error: 'excepcion' });
          }
        });
      });
    }

    boton.addEventListener('click', async () => {
      const alumno = idAlumno();
      if (!alumno || boton.disabled) return;
      boton.disabled = true;
      boton.style.opacity = '.6';
      try {
        const secciones = {};
        for (const clave of Object.keys(casillas)) secciones[clave] = casillas[clave].checked;
        const respuestas = await reunir(alumno, avisar);
        const [texto, error] = resumen(await enviar(alumno, respuestas, secciones));
        avisar(texto, error);
      } catch (e) {
        const texto = String((e && e.message) || e);
        // pasa si se recargó la extensión sin recargar la página
        avisar(/context invalidated/i.test(texto) ? t().recargar : '❌ ' + texto, true);
      } finally {
        boton.disabled = false;
        boton.style.opacity = '1';
      }
    });

    caja.appendChild(estado);
    caja.appendChild(panel);
    caja.appendChild(alterna);
    caja.appendChild(boton);
    return caja;
  }

  function actualizar() {
    const existente = document.getElementById(ID_BOTON);
    if (idAlumno()) {
      if (!existente && document.body) document.body.appendChild(crearBoton());
    } else if (existente) {
      existente.remove();
    }
  }

  actualizar();
  setInterval(actualizar, 1000);
})();
