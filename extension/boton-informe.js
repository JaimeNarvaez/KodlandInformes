// Botón "Generar informe" en la ficha del alumno (bo.kodland.org/students/<ID>).
//
// Reúne aquí, con la sesión que ya tiene abierta quien lo usa, las respuestas
// de la API que necesita el informe, y se las pasa al puente local, que solo
// arma el PDF. Así no hace falta iniciar sesión en otro Chrome ni tener cuenta
// de tutor: sirve para cualquier cuenta que pueda ver la ficha (ventas / ISM).
// El token no sale del navegador: al puente solo llegan las respuestas.
//
// El backoffice es una SPA (Vuetify): no recarga la página al pasar de un
// grupo a un alumno, así que se vigila la URL y el botón aparece o desaparece.

(function () {
  if (window.__kiBotonInforme) return;   // evitar duplicados
  window.__kiBotonInforme = true;

  const ID_BOTON = 'ki-boton-informe';
  const API = 'https://backoffice.kodland.org/api/v2';
  const EN_PARALELO = 6;   // consultas de tareas a la vez, para no saturar

  function idAlumno() {
    const m = location.pathname.match(/^\/students\/(\d+)\/?$/);
    return m ? m[1] : null;
  }

  // la web manda el token de la cookie "access" como Bearer; solo con las
  // cookies la API responde 401
  function token() {
    const m = document.cookie.match(/(?:^|;\s*)access=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  async function pedir(ruta) {
    const t = token();
    try {
      const r = await fetch(API + ruta, {
        credentials: 'include',
        headers: Object.assign({ Accept: 'application/json' },
                               t ? { Authorization: 'Bearer ' + t } : {}),
      });
      let cuerpo = null;
      try { cuerpo = await r.json(); } catch (e) { /* sin JSON */ }
      return { status: r.status, cuerpo };
    } catch (e) {
      return { status: -1, cuerpo: null };
    }
  }

  // Las mismas rutas, en el mismo orden, que consulta generar_reportes_grupo
  // en kodland_datos.py: allí se leen de este paquete en vez de en vivo.
  async function reunir(sid, avisar) {
    const resp = {};
    const guardar = async (ruta) => (resp[ruta] = await pedir(ruta));

    avisar('⏳ Leyendo los grupos del alumno…');
    const lista = await guardar(`/students/${sid}/backoffice_groups/`);
    if (lista.status === 401 || lista.status === 403) {
      throw new Error('Kodland no dio permiso (' + lista.status + '). Recarga la página (F5) y reintenta.');
    }
    if (lista.status !== 200) {
      throw new Error('No pude leer los grupos del alumno (status ' + lista.status + ').');
    }
    await guardar(`/students/${sid}/get_general_info_for_student_backoffice_page/`);

    const lecciones = [];
    for (const g of Array.isArray(lista.cuerpo) ? lista.cuerpo : []) {
      const gid = g && g.group_id;
      if (!gid) continue;
      const info = await guardar(`/student_groups/${gid}/get_general_info_for_group_backoffice_page`);
      if (info.cuerpo && info.cuerpo.passed_lessons_count === 0) continue;   // aún no empezó
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
      avisar(`⏳ Leyendo tareas y asistencia… ${Math.round(100 * i / rutas.length)} %`);
      await Promise.all(rutas.slice(i, i + EN_PARALELO).map(guardar));
    }
    return resp;
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
    estilo(estado, {
      display: 'none', maxWidth: '300px', padding: '8px 10px', borderRadius: '8px',
      background: '#fff', color: '#223', fontSize: '12px', whiteSpace: 'pre-wrap',
      boxShadow: '0 2px 10px rgba(0,0,0,.2)',
    });

    const boton = document.createElement('button');
    boton.textContent = '📄 Generar informe';
    boton.title = 'Genera el PDF de desarrollo de este alumno (uno por cada grupo en que esté)';
    estilo(boton, {
      background: '#6c2bd9', color: '#fff', border: 'none', borderRadius: '24px',
      padding: '10px 16px', fontWeight: '600', fontSize: '14px', cursor: 'pointer',
      boxShadow: '0 2px 10px rgba(0,0,0,.25)',
    });

    function avisar(texto, error) {
      estado.textContent = texto;
      estado.style.color = error ? '#b3261e' : '#223';
      estado.style.display = 'block';
    }

    function enviar(alumno, respuestas) {
      return new Promise((resolve) => {
        chrome.runtime.sendMessage({ tipo: 'informe', alumno, respuestas }, (resp) => {
          if (chrome.runtime.lastError) {
            resolve({ ok: false, error: chrome.runtime.lastError.message });
          } else {
            resolve(resp || { ok: false, error: 'El puente no respondió.' });
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
        const respuestas = await reunir(alumno, avisar);
        avisar('⏳ Enviando al generador de PDF…');
        const resp = await enviar(alumno, respuestas);
        if (resp.ok) {
          avisar('✅ ' + (resp.mensaje || 'Generando el informe.') +
                 '\nSigue el progreso en la ventana que se abrió; al terminar se abre la carpeta.');
        } else {
          avisar('❌ ' + (resp.error ||
                 'El puente no respondió. ¿Ejecutaste puente\\instalar_puente.bat?'), true);
        }
      } catch (e) {
        // también pasa si se recargó la extensión sin recargar la página
        avisar('❌ ' + (e && e.message ? e.message : e), true);
      } finally {
        boton.disabled = false;
        boton.style.opacity = '1';
      }
    });

    caja.appendChild(estado);
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
