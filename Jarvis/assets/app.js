const API = "";

// ---------------- Modo mini (PIP, Fase 10) ----------------
// Misma página/JS que la ventana principal, ?modo=mini solo oculta contenido
// vía CSS y salta el wiring que no aplica (ver body.mini en style.css).
const MODO_MINI = new URLSearchParams(location.search).get("modo") === "mini";
if (MODO_MINI) document.body.classList.add("mini");

function $(sel) { return document.querySelector(sel); }
function $all(sel) { return Array.from(document.querySelectorAll(sel)); }

async function api(path, options) {
  const res = await fetch(API + path, options);
  return res.json();
}

// ---------------- Modales ----------------

function abrirModal(id) {
  $(id).classList.remove("hidden");
}
function cerrarModal(id) {
  $(id).classList.add("hidden");
  // El test de mic abre un stream de audio real en el backend: si se cierra
  // el modal sin apretar "Detener" antes, no debe quedar huérfano corriendo.
  if (id === "#overlayConfig" && micTestActivo) detenerMicTest();
}

$all(".btn-cerrar").forEach((btn) => {
  btn.addEventListener("click", () => cerrarModal("#" + btn.dataset.close));
});
$all(".overlay").forEach((overlay) => {
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) cerrarModal("#" + overlay.id);
  });
});

$("#btnTareas").addEventListener("click", () => { abrirModal("#overlayTareas"); cargarTareas(); });
$("#btnRecordatorios").addEventListener("click", () => { abrirModal("#overlayRecordatorios"); cargarRecordatorios(); });
$("#btnConfig").addEventListener("click", () => { abrirModal("#overlayConfig"); cargarConfig(); });

$all(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    const grupo = tab.dataset.group;
    $all(`.tab[data-group="${grupo}"]`).forEach((t) => t.classList.remove("activa"));
    $all(`.tab-panel[data-group="${grupo}"]`).forEach((p) => p.classList.remove("activa"));
    tab.classList.add("activa");
    $(`.tab-panel[data-panel="${tab.dataset.tab}"][data-group="${grupo}"]`).classList.add("activa");
    if (grupo === "tareas" && tab.dataset.tab === "lista") cargarTareas();
    if (grupo === "rec" && tab.dataset.tab === "lista") cargarRecordatorios();
  });
});

// ---------------- Tareas ----------------

async function cargarTareas() {
  const cont = $("#listaTareas");
  const tareas = await api("/api/tareas");
  if (!tareas.length) {
    cont.innerHTML = '<p class="msg-vacio">No hay tareas todavía.</p>';
    return;
  }
  cont.innerHTML = "";
  tareas.forEach((t) => {
    const div = document.createElement("div");
    div.className = "item-lista" + (t.done ? " completada" : "");
    const cuando = [t.date, t.time].filter(Boolean).join(" ");
    div.innerHTML = `
      <input type="checkbox" ${t.done ? "checked disabled" : ""} data-id="${t.id}">
      <span class="item-texto">${escapeHtml(t.description)}${cuando ? `<span class="item-cuando">${escapeHtml(cuando)}</span>` : ""}</span>
      <button class="btn-borrar" data-id="${t.id}">&times;</button>
    `;
    cont.appendChild(div);
  });
  $all("#listaTareas input[type=checkbox]:not(:disabled)").forEach((cb) => {
    cb.addEventListener("change", async () => {
      await api("/api/tareas", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "complete", task_id: cb.dataset.id }) });
      cargarTareas();
    });
  });
  $all("#listaTareas .btn-borrar").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api("/api/tareas", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "delete", task_id: btn.dataset.id }) });
      cargarTareas();
    });
  });
}

$("#formTarea").addEventListener("submit", async (e) => {
  e.preventDefault();
  const resp = await api("/api/tareas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "add",
      description: $("#tareaDesc").value,
      date: $("#tareaFecha").value,
      time: $("#tareaHora").value,
    }),
  });
  $("#tareaMsg").textContent = resp.message;
  e.target.reset();
  cargarTareas();
});

// ---------------- Recordatorios ----------------

$("#recRepetir").addEventListener("change", () => {
  $("#recDiasGrupo").classList.toggle("hidden", $("#recRepetir").value !== "weekdays");
});

async function cargarRecordatorios() {
  const cont = $("#listaRecordatorios");
  const items = await api("/api/recordatorios");
  if (!items.length) {
    cont.innerHTML = '<p class="msg-vacio">No hay recordatorios todavía.</p>';
    return;
  }
  cont.innerHTML = "";
  items.forEach((r) => {
    const div = document.createElement("div");
    div.className = "item-lista";
    const tipo = r.kind === "alarm" ? "ALARMA" : "RECORDATORIO";
    div.innerHTML = `
      <span class="item-texto">[${tipo}] ${escapeHtml(r.message)}<span class="item-cuando">${escapeHtml(r.trigger_at || "")}</span></span>
      <button class="btn-borrar" data-id="${r.id}">&times;</button>
    `;
    cont.appendChild(div);
  });
  $all("#listaRecordatorios .btn-borrar").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api("/api/recordatorios", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "delete", id: btn.dataset.id }) });
      cargarRecordatorios();
    });
  });
}

$("#formRecordatorio").addEventListener("submit", async (e) => {
  e.preventDefault();
  const dias = $all("#recDiasGrupo input:checked").map((i) => Number(i.value));
  const resp = await api("/api/recordatorios", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "add",
      kind: $("#recTipo").value,
      message: $("#recMensaje").value,
      when: $("#recFecha").value,
      time: $("#recHora").value,
      recurrence: $("#recRepetir").value,
      weekdays: dias,
      action_prompt: $("#recAccion").value,
    }),
  });
  $("#recMsg").textContent = resp.message;
  e.target.reset();
  $("#recDiasGrupo").classList.add("hidden");
  cargarRecordatorios();
});

// ---------------- Configuración ----------------

async function cargarConfig() {
  const cfg = await api("/api/config");
  $("#cfgApiKey").value = cfg.gemini_api_key || "";
  $("#cfgAuriculares").checked = !!cfg.usar_auriculares;
  $("#cfgUltratumba").checked = !!cfg.voz_ultratumba;
  $("#cfgLocation").value = cfg.location || "";
  $("#cfgMorningBrief").value = cfg.morning_brief_time || "";

  const selVoz = $("#cfgVoz");
  selVoz.innerHTML = "";
  (cfg.voces_disponibles || []).forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    if (v === cfg.voice) opt.selected = true;
    selVoz.appendChild(opt);
  });

  await poblarDispositivos(cfg.mic_device_index, cfg.speaker_device_index);
}

// Los dispositivos se piden al backend (PortAudio), NO a
// navigator.mediaDevices.enumerateDevices(): los índices del navegador no
// coinciden con los de PortAudio, y guardar uno del navegador terminaba
// mandando el audio a un dispositivo que no suena (Jarvis respondía pero no
// se lo escuchaba).
async function poblarDispositivos(micIdx, speakerIdx) {
  const selMic = $("#cfgMic");
  const selSpeaker = $("#cfgSpeaker");
  try {
    const data = await api("/api/audio-devices");
    const llenar = (sel, items, elegido, defIdx) => {
      sel.innerHTML = "";
      const opt0 = document.createElement("option");
      opt0.value = "-1";
      opt0.textContent = `Predeterminado del sistema (${defIdx})`;
      sel.appendChild(opt0);
      (items || []).forEach((d) => {
        const opt = document.createElement("option");
        opt.value = d.index;
        opt.textContent = `${d.index}: ${d.nombre}`;
        if (d.index === elegido) opt.selected = true;
        sel.appendChild(opt);
      });
      if (elegido === -1 || elegido === undefined || elegido === null) opt0.selected = true;
    };
    llenar(selMic, data.entrada, micIdx, data.default_entrada);
    llenar(selSpeaker, data.salida, speakerIdx, data.default_salida);
  } catch (e) {
    // ponytail: si falla el listado, quedan los <option> "Predeterminado"
    // del HTML, que mandan -1 y dejan que PortAudio elija.
  }
}

$("#btnMostrarKey").addEventListener("click", () => {
  const input = $("#cfgApiKey");
  const mostrar = input.type === "password";
  input.type = mostrar ? "text" : "password";
  $("#btnMostrarKey").textContent = mostrar ? "OCULTAR" : "MOSTRAR";
});

$("#formConfig").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      gemini_api_key: $("#cfgApiKey").value,
      usar_auriculares: $("#cfgAuriculares").checked,
      voz_ultratumba: $("#cfgUltratumba").checked,
      voice: $("#cfgVoz").value,
      mic_device_index: Number($("#cfgMic").value),
      speaker_device_index: Number($("#cfgSpeaker").value),
      location: $("#cfgLocation").value,
      morning_brief_time: $("#cfgMorningBrief").value,
    }),
  });
  $("#configMsg").textContent = "Configuración guardada.";
});

// ---------------- Test de micrófono (Fase 13) ----------------

let micTestActivo = false;
let micTestPollTimer = null;

async function pollMicTestNivel() {
  try {
    const data = await api("/api/mic-test/nivel");
    if (!data.activo) {
      // El backend lo paró por su cuenta (ej. error del stream) — reflejarlo.
      await detenerMicTest(false);
      return;
    }
    $("#micTestNivel").style.width = Math.min(100, data.nivel) + "%";
    const conSenal = data.nivel >= data.umbral;
    $("#micTestMsg").textContent = conSenal ? "Te escucho" : "Sin señal";
    $("#micTestMsg").classList.toggle("con-senal", conSenal);
  } catch (e) {
    // ponytail: mismo criterio que el resto de los pollings, se reintenta solo.
  }
}

async function detenerMicTest(avisarBackend = true) {
  clearInterval(micTestPollTimer);
  micTestPollTimer = null;
  micTestActivo = false;
  $("#btnMicTest").textContent = "PROBAR";
  $("#btnMicTest").classList.remove("activo");
  $("#micTestNivel").style.width = "0%";
  $("#micTestMsg").textContent = "Sin señal";
  $("#micTestMsg").classList.remove("con-senal");
  if (avisarBackend) {
    await api("/api/mic-test/detener", { method: "POST" });
  }
}

$("#btnMicTest").addEventListener("click", async () => {
  if (micTestActivo) {
    await detenerMicTest();
    return;
  }
  const resp = await api("/api/mic-test/iniciar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mic_device_index: Number($("#cfgMic").value) }),
  });
  if (!resp.activo) {
    $("#micTestMsg").textContent = resp.error || "No se pudo iniciar la prueba del micrófono.";
    return;
  }
  micTestActivo = true;
  $("#btnMicTest").textContent = "DETENER";
  $("#btnMicTest").classList.add("activo");
  micTestPollTimer = setInterval(pollMicTestNivel, 150);
});

// ---------------- Test de salida (Fase 17) ----------------
// Sin polling ni estado: un disparo único que bloquea hasta que termina de
// sonar (menos de 1s), no un stream continuo como el de mic.

$("#btnSpeakerTest").addEventListener("click", async () => {
  $("#speakerTestMsg").textContent = "Sonando...";
  $("#speakerTestMsg").classList.remove("con-senal");
  const resp = await api("/api/speaker-test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ speaker_device_index: Number($("#cfgSpeaker").value) }),
  });
  if (!resp.ok) {
    $("#speakerTestMsg").textContent = resp.error || "No se pudo reproducir el tono.";
    return;
  }
  $("#speakerTestMsg").textContent = "¿Escuchaste el tono?";
  $("#speakerTestMsg").classList.add("con-senal");
});

// ---------------- Chat de texto ----------------

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = String(s ?? "");
  return div.innerHTML;
}

function agregarLinea(quien, texto) {
  const log = $("#chatLog");
  const div = document.createElement("div");
  div.className = "linea";
  div.innerHTML = `<span class="quien">${quien}:</span> ${escapeHtml(texto)}`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  $("#caption").textContent = texto;
}

$("#chatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#chatInput");
  const texto = input.value.trim();
  if (!texto) return;
  agregarLinea("VOS", texto);
  input.value = "";
  const resp = await api("/api/mensaje", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ texto }),
  });
  agregarLinea("JARVIS", resp.respuesta);
  actualizarEstadoVoz();
});

// ---------------- Estado / voz ----------------

let vozActiva = false;

async function actualizarEstadoVoz() {
  const estado = await api("/api/voz/estado");
  vozActiva = estado.activo;
  $("#btnVoz").classList.toggle("activo", vozActiva);
  $("#btnVozTexto").textContent = vozActiva ? "DESACTIVAR VOZ" : "ACTIVAR VOZ";
}

$("#btnVoz").addEventListener("click", async () => {
  if (vozActiva) {
    await api("/api/voz/detener", { method: "POST" });
  } else {
    transcripcionesMostradas = 0; // el backend reinicia su lista al arrancar sesión
    await api("/api/voz/iniciar", { method: "POST" });
  }
  actualizarEstadoVoz();
});

actualizarEstadoVoz();
setInterval(actualizarEstadoVoz, 3000);

// ---------------- Transcripción de voz (Fase 06/09) ----------------
// La Live API solo manda audio; sin esto, no había ninguna forma de ver en
// pantalla lo que el usuario dijo ni lo que Jarvis respondió (reportado
// probando la app real).
let transcripcionesMostradas = 0;

async function pollTranscripcionVoz() {
  if (!vozActiva) return;
  try {
    const data = await api("/api/voz/transcripcion");
    const items = data.items || [];
    for (let i = transcripcionesMostradas; i < items.length; i++) {
      const it = items[i];
      agregarLinea(it.quien === "usuario" ? "VOS" : "JARVIS", it.texto);
    }
    transcripcionesMostradas = items.length;
  } catch (e) {
    // ponytail: mismo criterio que pollEstado, se reintenta solo.
  }
}
setInterval(pollTranscripcionVoz, 700);

// ---------------- Toggle ventana mini (PIP, Fase 10) ----------------
// No aplica dentro de la propia ventana mini.
if (!MODO_MINI) {
  const actualizarPip = async () => {
    const estado = await api("/api/pip/estado");
    $("#btnPip").classList.toggle("activo", estado.habilitado);
    $("#btnPipTexto").textContent = estado.habilitado ? "OCULTAR MINI" : "MOSTRAR MINI";
  };
  $("#btnPip").addEventListener("click", async () => {
    await api("/api/pip/toggle", { method: "POST" });
    actualizarPip();
  });
  actualizarPip();
}

// ---------------- Panel ASCII (calavera reactiva) ----------------
// Arte base portado de plans/material/skull-illustration-source.tsx (Fase 09):
// 1 solo frame estático, extraído a Jarvis/assets/skull_frame.json con la
// técnica de regex + JSON.parse documentada en plans/material/ascii_skull.json.
// Los 4 estados NO son frames distintos: se modulan sobre este mismo frame.

const ASCII_CHARSET = " .:░▒▓█";

const ESTADO_LABELS = {
  inactivo: "INACTIVO",
  escuchando: "ESCUCHANDO",
  hablando: "HABLANDO",
  procesando: "PROCESANDO",
};

const GLITCH_INTERVALO_MS = {
  inactivo: [5000, 8000],
  procesando: [2000, 4000],
  escuchando: [1000, 2000],
  hablando: [1000, 2000],
};

let asciiOriginal = null; // Array<string>, copia intacta del frame para restaurar
let asciiChars = null; // Array<string>, copia mutable (ruido de "hablando")
let asciiNoEspacio = []; // índices de asciiChars que no son " " ni "\n"
let estadoActual = "inactivo";
let glitchTimer = null;
let ruidoTimer = null;

async function cargarAsciiSkull() {
  const res = await fetch("/skull_frame.json");
  const data = await res.json();
  asciiOriginal = Array.from(data.frame);
  asciiChars = asciiOriginal.slice();
  asciiOriginal.forEach((ch, i) => {
    if (ch !== " " && ch !== "\n") asciiNoEspacio.push(i);
  });
  renderAscii();
  ajustarEscalaAscii();
}

function renderAscii() {
  $("#asciiPre").textContent = asciiChars.join("");
}

// Alto máximo del panel ASCII — sin este tope, un arte de 99 líneas escalado
// solo por ancho sigue midiendo cientos de px de alto y se come el espacio
// del chat de abajo (reportado por el usuario probando la app real).
const ALTURA_MAX_PANEL_ASCII = 260;

function ajustarEscalaAscii() {
  const cont = $("#panelAscii");
  const pre = $("#asciiPre");
  const wrap = $("#asciiScaleWrap");
  if (!cont || !pre || !pre.textContent) return;
  const disponibleAncho = cont.clientWidth - 32; // resta padding horizontal del panel
  const disponibleAlto = ALTURA_MAX_PANEL_ASCII - 32;
  const naturalAncho = pre.scrollWidth;
  const naturalAlto = pre.scrollHeight;
  const escalaAncho = disponibleAncho > 0 && naturalAncho > 0 ? disponibleAncho / naturalAncho : 1;
  const escalaAlto = disponibleAlto > 0 && naturalAlto > 0 ? disponibleAlto / naturalAlto : 1;
  const escala = Math.min(escalaAncho, escalaAlto, 1);
  wrap.style.transform = `scale(${escala})`;
  // ponytail: transform no cambia el tamaño de layout, así que fijamos la
  // altura del contenedor a mano al tamaño ya escalado (si no, queda un
  // hueco vacío del alto sin escalar debajo del arte).
  cont.style.height = Math.ceil(naturalAlto * escala + 32) + "px";
}

new ResizeObserver(ajustarEscalaAscii).observe($("#panelAscii"));

function dispararGlitch() {
  const el = $("#panelAscii");
  el.classList.remove("glitch");
  void el.offsetWidth;
  el.classList.add("glitch");
}

function programarGlitch() {
  clearTimeout(glitchTimer);
  const [min, max] = GLITCH_INTERVALO_MS[estadoActual] || GLITCH_INTERVALO_MS.inactivo;
  const espera = min + Math.random() * (max - min);
  glitchTimer = setTimeout(() => {
    dispararGlitch();
    programarGlitch();
  }, espera);
}

function ruidoCaracteres() {
  if (!asciiChars || !asciiNoEspacio.length) return;
  const porcentaje = 0.01 + Math.random() * 0.02; // 1-3%
  const cantidad = Math.max(1, Math.floor(asciiNoEspacio.length * porcentaje));
  for (let i = 0; i < cantidad; i++) {
    const idx = asciiNoEspacio[Math.floor(Math.random() * asciiNoEspacio.length)];
    asciiChars[idx] = ASCII_CHARSET[Math.floor(Math.random() * ASCII_CHARSET.length)];
  }
  renderAscii();
}

function iniciarRuido() {
  clearInterval(ruidoTimer);
  ruidoTimer = setInterval(ruidoCaracteres, 100 + Math.random() * 50);
}

function detenerRuido() {
  clearInterval(ruidoTimer);
  ruidoTimer = null;
  if (asciiOriginal && asciiChars) {
    asciiChars = asciiOriginal.slice();
    renderAscii();
  }
}

function aplicarEstadoAscii(nuevo) {
  if (nuevo === estadoActual) return;
  estadoActual = nuevo;
  $("#estadoTexto").textContent = ESTADO_LABELS[nuevo] || nuevo.toUpperCase();
  $("#panelAscii").className = "panel-ascii " + nuevo;
  dispararGlitch();
  programarGlitch();
  if (nuevo === "hablando") {
    iniciarRuido();
  } else {
    detenerRuido();
  }
}

async function pollEstado() {
  try {
    const data = await api("/api/estado");
    aplicarEstadoAscii(data.estado);
  } catch (e) {
    // ponytail: si el fetch falla (server reiniciando, etc.), se reintenta solo en el próximo tick.
  }
}

cargarAsciiSkull();
programarGlitch();
pollEstado();
setInterval(pollEstado, 500);
