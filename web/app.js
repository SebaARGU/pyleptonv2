const $ = (id) => document.getElementById(id);

const emissivity = $("emissivity");
const background = $("background");
const material = $("material");
const colormap = $("colormap");

// ── populate selects from /meta ───────────────────────────────────────────────
async function loadMeta() {
  const meta = await (await fetch("/meta")).json();

  for (const [name, value] of Object.entries(meta.materials)) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = `${name} (${value})`;
    material.appendChild(opt);
  }
  material.value = "";  // start on no preset

  for (const name of meta.colormaps) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    colormap.appendChild(opt);
  }
  colormap.value = "ironblack";
}

// ── send settings to the server ───────────────────────────────────────────────
async function postSettings(body) {
  await fetch("/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

emissivity.addEventListener("input", () => {
  $("e-val").textContent = parseFloat(emissivity.value).toFixed(2);
  postSettings({ emissivity: parseFloat(emissivity.value) });
});

background.addEventListener("input", () => {
  $("bg-val").textContent = `${background.value} C`;
  postSettings({ background_temp: parseFloat(background.value) });
});

material.addEventListener("change", () => {
  if (material.value === "") return;
  emissivity.value = material.value;
  $("e-val").textContent = parseFloat(material.value).toFixed(2);
  postSettings({ emissivity: parseFloat(material.value) });
});

colormap.addEventListener("change", () => {
  postSettings({ colormap: colormap.value });
});

$("ffc").addEventListener("click", () => {
  postSettings({ ffc: true });
});

// ── poll stats ────────────────────────────────────────────────────────────────
const fmt = (v) => (v === null || v === undefined ? "—" : `${v.toFixed(1)} C`);

async function pollStats() {
  try {
    const s = await (await fetch("/stats")).json();
    $("fps").textContent = `${s.fps ?? 0} FPS`;
    $("r-min").textContent = fmt(s.min);
    $("r-avg").textContent = fmt(s.avg);
    $("r-max").textContent = fmt(s.max);
    $("r-fpa").textContent = fmt(s.fpa_temp);

    $("c-raw").textContent = fmt(s.center_raw);
    $("c-corr").textContent = fmt(s.center);
    if (s.center !== null && s.center_raw !== null) {
      const d = s.center - s.center_raw;
      $("c-diff").textContent = `${d >= 0 ? "+" : ""}${d.toFixed(1)} C`;
    }
  } catch (e) {
    $("fps").textContent = "offline";
  }
}

loadMeta();
setInterval(pollStats, 250);
pollStats();
