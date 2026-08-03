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
  $("#cfgUmbralEco").value = cfg.umbral_rms_eco ?? 500;
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
      umbral_rms_eco: Number($("#cfgUmbralEco").value) || 500,
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
    $("#micTestUmbralMarca").style.left = Math.min(100, data.umbral) + "%";
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

// Formato de la consola del mockup Orbital Command:
//   [HH:MM:SS] [JARVIS] texto
// El color de la línea depende de quién habla (ver .linea.jarvis/.usuario en
// style.css); el timestamp siempre va en rojo tenue.
function agregarLinea(quien, texto) {
  const log = $("#chatLog");
  const hora = new Date().toLocaleTimeString("es", { hour12: false });
  const rol = quien === "JARVIS" ? "jarvis" : "usuario";
  const div = document.createElement("div");
  div.className = "linea " + rol;
  div.innerHTML =
    `<span class="hora">[${hora}]</span>` +
    `<span class="texto">[${escapeHtml(quien)}] ${escapeHtml(texto)}</span>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  // El panel hero muestra siempre lo último que se dijo.
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
    $("#btnPipTexto").textContent = estado.habilitado ? "OCULTAR JARVIS" : "MOSTRAR JARVIS";
  };
  $("#btnPip").addEventListener("click", async () => {
    await api("/api/pip/toggle", { method: "POST" });
    actualizarPip();
  });
  actualizarPip();
}

// ---------------- Panel hero: espacio, nebulosa y estado ----------------

const ESTADO_LABELS = {
  inactivo: "INACTIVO",
  escuchando: "ESCUCHANDO",
  hablando: "HABLANDO",
  procesando: "PROCESANDO",
};

// Título del hero por estado -- reemplaza al "NEURAL ECHO" fijo del mockup
// (stitch_jarvis_cosmic_terminal/jarvis_main_console) para que el panel diga
// algo real sobre lo que Jarvis está haciendo.
const HERO_TITULOS = {
  inactivo: "NEURAL ECHO",
  escuchando: "SEÑAL ENTRANTE",
  hablando: "TRANSMITIENDO",
  procesando: "PROCESANDO",
};

// Cómo se comporta el núcleo ("la nebulosa que habla") en cada estado.
//   amplitud: cuánto vibra cada partícula, en px
//   pulso:    velocidad del latido del radio (0 = no late)
//   giro:     vueltas por segundo del cúmulo
//   brillo:   multiplicador general
// En `inactivo` todo va en 0: el panel queda COMPLETAMENTE quieto y el bucle
// de animación ni siquiera se agenda (ver `dibujar`).
const NUCLEO_POR_ESTADO = {
  inactivo:   { amplitud: 0,   pulso: 0,   giro: 0,    brillo: 0.55 },
  escuchando: { amplitud: 1.4, pulso: 1.6, giro: 0.06, brillo: 0.9 },
  hablando:   { amplitud: 3.2, pulso: 2.6, giro: 0.10, brillo: 1.0 },
  procesando: { amplitud: 0.8, pulso: 0.9, giro: 0.35, brillo: 0.75 },
};

let estadoActual = "inactivo";
let espacio = null; // API de la escena, la llena `iniciarEspacio`

function aplicarEstado(nuevo) {
  if (nuevo === estadoActual) return;
  estadoActual = nuevo;
  $("#estadoTexto").textContent = ESTADO_LABELS[nuevo] || nuevo.toUpperCase();
  $(".hero-titulo").textContent = HERO_TITULOS[nuevo] || HERO_TITULOS.inactivo;
  $("#panelHero").className = "panel-hero corner-accent " + nuevo;
  if (espacio) espacio.cambiarEstado(nuevo);
}

async function pollEstado() {
  try {
    const data = await api("/api/estado");
    aplicarEstado(data.estado);
  } catch (e) {
    // ponytail: si el fetch falla (server reiniciando, etc.), se reintenta solo en el próximo tick.
  }
}

// ---------------- Escena espacial del hero ----------------
// Canvas 2D, no WebGL: la escena es simple (gradientes + puntos) y así no
// depende de que el driver acepte compilar shaders.
//
// Dos capas:
//   1. FONDO estático -- nebulosa + estrellas, se dibuja UNA vez a un canvas
//      offscreen y de ahí se copia. Nunca cambia, así que no cuesta nada.
//   2. NÚCLEO dinámico -- el cúmulo de partículas que reacciona al estado.
//      Solo se redibuja mientras Jarvis está haciendo algo; en reposo se
//      dibuja un frame y el bucle se corta.

const NEBULOSAS = [
  // x, y y radio en fracción del panel; color y opacidad de la nube
  { x: 0.68, y: 0.42, r: 0.55, color: "120, 20, 40", alfa: 0.30 },
  { x: 0.52, y: 0.60, r: 0.48, color: "40, 25, 90", alfa: 0.26 },
  { x: 0.82, y: 0.28, r: 0.38, color: "90, 30, 110", alfa: 0.22 },
  { x: 0.25, y: 0.30, r: 0.42, color: "20, 35, 80", alfa: 0.20 },
  { x: 0.70, y: 0.45, r: 0.20, color: "200, 40, 60", alfa: 0.28 },
];

const NUCLEO_X = 0.70;  // a la derecha para no chocar con el texto del hero
const NUCLEO_Y = 0.44;
const NUCLEO_PARTICULAS = 420;
const ESTRELLAS = 260;

function iniciarEspacio() {
  const canvas = $("#canvasEspacio");
  if (!canvas || !canvas.getContext) return null;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  // Posiciones normalizadas [0,1]: sobreviven al resize sin "saltar".
  const estrellas = [];
  for (let i = 0; i < ESTRELLAS; i++) {
    estrellas.push({
      x: Math.random(),
      y: Math.random(),
      r: Math.random() < 0.88 ? 0.5 : 1.1,
      a: 0.15 + Math.random() * 0.7,
    });
  }

  // Cúmulo: más denso hacia el centro (Math.pow con exponente < 1 empuja los
  // valores hacia arriba, así que se invierte para concentrar cerca de 0).
  const nucleo = [];
  for (let i = 0; i < NUCLEO_PARTICULAS; i++) {
    nucleo.push({
      rad: Math.pow(Math.random(), 0.55),
      ang: Math.random() * Math.PI * 2,
      achat: 0.55 + Math.random() * 0.45,   // aplana el cúmulo, lo vuelve elipse
      fase: Math.random() * Math.PI * 2,
      brillo: 0.25 + Math.random() * 0.75,
    });
  }

  let ancho = 0;
  let alto = 0;
  let dpr = 1;
  let fondo = null;     // canvas offscreen con nebulosa + estrellas
  let animando = false;
  let t0 = performance.now();

  function dibujarFondo() {
    fondo = document.createElement("canvas");
    fondo.width = Math.max(1, Math.round(ancho * dpr));
    fondo.height = Math.max(1, Math.round(alto * dpr));
    const f = fondo.getContext("2d");
    f.scale(dpr, dpr);

    f.fillStyle = "#000";
    f.fillRect(0, 0, ancho, alto);

    // Nubes de nebulosa: gradientes radiales grandes y muy tenues.
    const diagonal = Math.hypot(ancho, alto);
    NEBULOSAS.forEach((n) => {
      const cx = n.x * ancho;
      const cy = n.y * alto;
      const r = n.r * diagonal * 0.6;
      const g = f.createRadialGradient(cx, cy, 0, cx, cy, r);
      g.addColorStop(0, `rgba(${n.color}, ${n.alfa})`);
      g.addColorStop(0.5, `rgba(${n.color}, ${n.alfa * 0.35})`);
      g.addColorStop(1, `rgba(${n.color}, 0)`);
      f.fillStyle = g;
      f.fillRect(0, 0, ancho, alto);
    });

    estrellas.forEach((e) => {
      f.fillStyle = `rgba(255, 255, 255, ${e.a})`;
      f.beginPath();
      f.arc(e.x * ancho, e.y * alto, e.r, 0, Math.PI * 2);
      f.fill();
    });
  }

  function dibujarNucleo(t) {
    const cfg = NUCLEO_POR_ESTADO[estadoActual] || NUCLEO_POR_ESTADO.inactivo;
    const cx = NUCLEO_X * ancho;
    const cy = NUCLEO_Y * alto;
    const base = Math.min(ancho, alto) * 0.26;
    const latido = cfg.pulso ? 1 + Math.sin(t * cfg.pulso) * 0.06 : 1;
    const radio = base * latido;

    // Halo detrás del cúmulo.
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, radio * 2.2);
    g.addColorStop(0, `rgba(224, 16, 42, ${0.30 * cfg.brillo})`);
    g.addColorStop(0.45, `rgba(224, 16, 42, ${0.08 * cfg.brillo})`);
    g.addColorStop(1, "rgba(224, 16, 42, 0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, ancho, alto);

    const giro = t * cfg.giro * Math.PI * 2;
    nucleo.forEach((p) => {
      const ang = p.ang + giro;
      const vib = cfg.amplitud ? Math.sin(t * 3 + p.fase) * cfg.amplitud : 0;
      const r = p.rad * radio + vib;
      const x = cx + Math.cos(ang) * r;
      const y = cy + Math.sin(ang) * r * p.achat;
      // El centro tira a blanco, el borde al rojo del sistema.
      const centro = 1 - p.rad;
      const alfa = Math.min(1, p.brillo * cfg.brillo * (0.35 + centro * 0.65));
      ctx.fillStyle = centro > 0.72
        ? `rgba(255, 235, 235, ${alfa})`
        : `rgba(224, 16, 42, ${alfa})`;
      ctx.fillRect(x, y, 1.2, 1.2);
    });
  }

  // Dibuja UN frame, sin agendar nada. Separado del bucle a propósito: hay
  // que poder pintar el panel sin depender de requestAnimationFrame, que no
  // corre si la ventana está oculta o minimizada (si no, el panel se queda
  // negro hasta que alguien la muestre).
  function dibujarFrame() {
    const t = (performance.now() - t0) / 1000;
    ctx.clearRect(0, 0, ancho, alto);
    if (fondo) ctx.drawImage(fondo, 0, 0, ancho, alto);
    dibujarNucleo(t);
  }

  function bucle() {
    dibujarFrame();
    const cfg = NUCLEO_POR_ESTADO[estadoActual] || NUCLEO_POR_ESTADO.inactivo;
    if (cfg.amplitud || cfg.pulso || cfg.giro) {
      requestAnimationFrame(bucle);
    } else {
      // Reposo: se corta el bucle. Nada se mueve hasta el próximo cambio de
      // estado, y la app no gasta CPU dibujando lo mismo 60 veces por segundo.
      animando = false;
    }
  }

  function arrancarBucle() {
    if (animando) return;
    animando = true;
    requestAnimationFrame(bucle);
  }

  function redimensionar() {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    dpr = window.devicePixelRatio || 1;
    ancho = rect.width;
    alto = rect.height;
    canvas.width = Math.round(ancho * dpr);
    canvas.height = Math.round(alto * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    dibujarFondo();
    dibujarFrame();  // síncrono: el panel nunca se ve negro
    arrancarBucle(); // y si hay estado activo, sigue el movimiento
  }

  new ResizeObserver(redimensionar).observe(canvas);
  redimensionar();

  // Al cambiar de estado se pinta un frame ya (para que se vea el cambio
  // aunque rAF no corra) y se reanuda el bucle si el estado nuevo se mueve.
  return {
    cambiarEstado() {
      dibujarFrame();
      arrancarBucle();
    },
  };
}

espacio = iniciarEspacio();
pollEstado();
setInterval(pollEstado, 500);
