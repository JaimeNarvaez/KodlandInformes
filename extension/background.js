// Reenvía al puente local (Native Messaging) los datos que reunió el botón.
// Los content scripts no pueden hablar con un host nativo; el service worker sí.
// Solo viajan el ID del alumno y las respuestas de la API: el puente vuelve a
// validarlo todo y decide qué ejecutar.

const NOMBRE_PUENTE = 'com.kodland.informes';

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.tipo !== 'informe') return;  // no es para nosotros

  const alumno = String(msg.alumno || '');
  if (!/^\d{1,12}$/.test(alumno)) {
    sendResponse({ ok: false, error: 'ID de alumno no válido.' });
    return;
  }
  const respuestas = msg.respuestas;
  if (!respuestas || typeof respuestas !== 'object' || Array.isArray(respuestas)) {
    // pasa si el botón de la página es de una versión anterior de la
    // extensión (solo mandaba el ID): Chrome no lo cambia hasta recargarla
    sendResponse({ ok: false, error: 'El botón de esta página es de una versión anterior. ' +
      'Recarga la extensión en chrome://extensions (↻) y luego esta página (F5).' });
    return;
  }
  try {
    chrome.runtime.sendNativeMessage(NOMBRE_PUENTE, { alumno, respuestas }, (respuesta) => {
      if (chrome.runtime.lastError) {
        sendResponse({ ok: false, error: chrome.runtime.lastError.message });
      } else {
        sendResponse(respuesta || { ok: false, error: 'El puente no respondió.' });
      }
    });
  } catch (e) {
    sendResponse({ ok: false, error: String(e) });
  }
  return true;  // la respuesta llega de forma asíncrona
});
