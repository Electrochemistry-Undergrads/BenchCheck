// BenchCheck frontend: vanilla JS, no build step. All dynamic text is escaped before insertion.

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const safeUrl = (u) => (typeof u === "string" && /^https?:\/\//i.test(u) ? u : null);
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
// Plotly cannot parse oklch(); resolve a colour token to rgb() through a 1x1 canvas.
const cssColor = (name) => {
  const ctx = Object.assign(document.createElement("canvas"), { width: 1, height: 1 }).getContext("2d");
  ctx.fillStyle = cssVar(name) || "gray";
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
  return `rgb(${r}, ${g}, ${b})`;
};
const fmt = (x, d = 2) => (x === null || x === undefined || Number.isNaN(x) ? "n/a" : Number(x).toFixed(d));
const sig = (x, s = 3) => {
  if (x === null || x === undefined || !Number.isFinite(x)) return "n/a";
  if (x === 0) return "0";
  const d = Math.max(0, Math.min(8, s - Math.floor(Math.log10(Math.abs(x))) - 1));
  return x.toFixed(d);
};

async function api(path, { method = "GET", json, form } = {}) {
  const opts = { method, headers: {} };
  if (json !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(json);
  }
  if (form) opts.body = form;
  const res = await fetch(path, opts);
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const detail = data && (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
    throw new Error(detail || `Request failed (HTTP ${res.status})`);
  }
  return data;
}

const UNITS = {
  potential: ["V", "mV"],
  current: ["A", "mA", "uA", "nA", "pA", "A/cm2", "mA/cm2", "uA/cm2"],
  time: ["s", "ms", "min", "h"],
};
const UNIT_LABEL = { uA: "µA", "uA/cm2": "µA cm⁻²", "mA/cm2": "mA cm⁻²", "A/cm2": "A cm⁻²" };
const uLabel = (u) => UNIT_LABEL[u] || u;
const LEVEL_CLASS = { "full text": "b-full", abstract: "b-abstract", "search snippet": "b-snippet" };
const APP_CLASS = { "condition-matched": "c-match", "partially matched": "c-related", "conditions not stated": "c-not_stated", "different conditions": "c-differs" };
const STATUS_TEXT = { match: "✓", related: "≈", differs: "✗", not_stated: "?", user_missing: "–" };

const GLOSSARY = [
  ["Forward / return sweep", "Within a cycle, the first sweep (here detected from the scan direction) and the sweep back after the vertex."],
  ["Vertex", "The potential where the scan reverses direction."],
  ["Peak height", "Current at the peak minus the baseline current at the same potential (disclosed baseline)."],
  ["Return/forward ratio", "Height of the return peak divided by the height of the paired forward peak. Close to 1 for a chemically reversible process."],
  ["Charge ratio", "Net charge passed on the return sweep divided by the net charge on the forward sweep (sign removed). Includes capacitive and side-reaction charge."],
  ["ΔEp (peak separation)", "Anodic minus cathodic peak potential for a candidate pair. About 57–59 mV for a reversible one-electron couple in solution at 25 °C; near 0 for an ideal surface-confined couple."],
  ["Midpoint potential", "Average of the paired anodic and cathodic peak potentials; approximates the formal potential for reversible couples."],
  ["FWHM", "Full width of a peak at half its height above the baseline. Reported as unresolved when neighbouring peaks overlap."],
  ["Savitzky–Golay smoothing", "Local polynomial smoothing used only to locate peaks; raw data are unchanged."],
  ["Evidence levels", "Full text: the retrieved page contained the paper body. Abstract: only the abstract was available. Search snippet: only Google Scholar's short excerpt."],
];

const META_FIELDS = [
  { key: "electrode_material", label: "Working electrode material", type: "text", required: true, span: 2 },
  { key: "process_type", label: "Redox-active species is…", type: "radio", required: true, span: 2,
    options: [["electrode_material", "in the electrode (film / insertion)"], ["dissolved_species", "dissolved in the electrolyte"]] },
  { key: "analyte", label: "Analyte", type: "text", required: true, showIf: (m) => m.process_type === "dissolved_species" },
  { key: "electrolyte", label: "Electrolyte (salt + concentration)", type: "text", required: true },
  { key: "solvent", label: "Solvent", type: "select", required: true,
    options: [["unknown", "— select —"], ["aqueous", "aqueous"], ["non-aqueous", "non-aqueous"]] },
  { key: "reference_electrode", label: "Reference electrode", type: "reference", required: true },
  { key: "reference_detail", label: "Reference details", type: "text", showIf: (m) => m.reference_electrode === "other" },
  { key: "scan_rate", label: "Scan rate", type: "quantity", units: ["mV/s", "V/s"], required: true },
  { key: "active_mass_mg", label: "Active-material mass (mg)", type: "number", showIf: (m) => m.process_type !== "dissolved_species" },
  { key: "analyte_concentration", label: "Analyte concentration", type: "quantity", units: ["mM", "M", "µM", "nM"], showIf: (m) => m.process_type === "dissolved_species" },
  { key: "diffusion_coefficient_cm2_s", label: "Diffusion coefficient (cm²/s)", type: "number", showIf: (m) => m.process_type === "dissolved_species" },
  { key: "electrons_n", label: "Electrons transferred, n", type: "number", showIf: (m) => m.process_type === "dissolved_species" },
  { key: "electrode_area_cm2", label: "Electrode area (cm²)", type: "number" },
  { key: "temperature_c", label: "Temperature (°C)", type: "number" },
  { key: "ph", label: "pH", type: "number", showIf: (m) => m.solvent !== "non-aqueous" },
  { key: "counter_electrode", label: "Counter electrode", type: "text" },
  { key: "ir_compensation", label: "iR compensation", type: "text" },
];

const blankMetadata = () => ({ process_type: "unknown", solvent: "unknown", scan_rate: { value: null, unit: "mV/s" } });

const state = {
  status: null,
  file: null,
  fileName: null,
  synthetic: false,
  inspect: null,
  mapping: { potential: null, current: null, time: null },
  units: { potential: "V", current: "A", time: "s" },
  suggested: {},
  convention: "iupac",
  forward: "auto",
  processing: { smoothing_mv: 10, baseline: "flat_prewave" },
  metadata: blankMetadata(),
  selectedCycle: null,
  referenceConversion: null,
  normalize: false,
  generation: 0,
  analysisRequest: 0,
  reportRequest: 0,
  analyzing: false,
  appliedConfig: null,
  analysis: null,
  report: null,
  evidence: freshEvidence(),
};

function freshEvidence() {
  return { running: false, done: false, mode: null, queries: [], log: [], sources: [], extractPlan: [], message: null, ranFor: null, outdated: false };
}

// ------------------------------------------------------------------ boot

async function init() {
  renderGlossary();
  bindStaticEvents();
  try {
    state.status = await api("/api/status");
  } catch (e) {
    showError(`Could not reach the BenchCheck server: ${e.message}`);
    return;
  }
  renderEvidencePill();
}

function bindStaticEvents() {
  ["input", "change"].forEach((event) => $("#setup").addEventListener(event, () => queueMicrotask(updateDraft)));
  window.addEventListener("beforeunload", (event) => { if (state.analysis) { event.preventDefault(); event.returnValue = ""; } });
  const dz = $("#dropzone");
  dz.addEventListener("keydown", (e) => {
    if (e.target === dz && ["Enter", " "].includes(e.key)) {
      e.preventDefault();
      $("#file-input").click();
    }
  });
  $("#file-input").addEventListener("change", (e) => e.target.files[0] && loadFile(e.target.files[0]));
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("drag"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault();
    dz.classList.remove("drag");
    if (e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]);
  });
  $("#analyze-btn").addEventListener("click", () => runAnalysis());
  ["#opt-all", "#opt-base", "#opt-smooth"].forEach((id) => $(id).addEventListener("change", renderPlot));
  $("#evidence-btn").addEventListener("click", runEvidence);
  $("#btn-png").addEventListener("click", async () => {
    await Plotly.relayout("plot", { paper_bgcolor: "#ffffff", plot_bgcolor: "#ffffff", "font.color": "#172522", "xaxis.color": "#172522", "yaxis.color": "#172522" });
    await Plotly.downloadImage("plot", { format: "png", width: 1400, height: 800, filename: `benchcheck-cv-${(state.fileName || "data").replace(/\.\w+$/, "")}` });
  });
  $("#btn-scale").addEventListener("click", openScaleDialog);
  $("#btn-area").addEventListener("click", openAreaDialog);
  $$("[data-export]").forEach((b) => b.addEventListener("click", () => exportReport(b.dataset.export)));
}

function showError(msg) {
  const box = $("#error-box");
  box.textContent = msg;
  box.hidden = !msg;
  if (msg) box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderEvidencePill() {
  const s = state.status;
  const pill = $("#evidence-pill");
  const cached = (s.cache_entries.live || 0) + (s.cache_entries.demo || 0);
  if (s.evidence_mode === "live") {
    pill.className = "pill pill-live";
    pill.textContent = "Evidence: live SerpApi";
    pill.title = "SerpApi key configured on the server. Searches run live; responses are cached locally and labeled when reused.";
  } else if (cached) {
    pill.className = "pill pill-cache";
    pill.textContent = "Evidence: cached only";
    pill.title = `No live SerpApi calls. ${cached} previously retrieved response(s) available, always labeled as cached.`;
  } else {
    pill.className = "pill pill-muted";
    pill.textContent = "Evidence: unavailable";
    pill.title = "No SerpApi key and no cached responses. Numerical analysis still works.";
  }
}

// ------------------------------------------------------------------ data loading

async function loadFile(file) {
  showError("");
  state.generation++;
  state.analysisRequest++;
  state.reportRequest++;
  state.analyzing = false;
  state.appliedConfig = null;
  state.metadata = blankMetadata();
  state.forward = "auto";
  $("#setup").open = true;
  $("#setup-line").textContent = "";
  state.file = file;
  state.fileName = file.name;
  state.synthetic = false;
  state.inspect = null;
  state.analysis = null;
  state.report = null;
  state.referenceConversion = null;
  state.normalize = false;
  state.selectedCycle = null;
  state.evidence = freshEvidence();
  $("#results").hidden = true;
  $("#mapping-card").hidden = true;
  $("#meta-card").hidden = true;
  $("#file-info").hidden = true;
  $("#analyze-btn").disabled = true;
  $("#analyze-btn").textContent = "Confirm & analyze";
  $("#dropzone").setAttribute("aria-busy", "true");
  $("#upload-title").textContent = "Reading your file…";
  const requestId = state.loadRequest = (state.loadRequest || 0) + 1;
  updateWorkspace("upload");
  const form = new FormData();
  form.append("file", file, file.name);
  try {
    const [inspection, preamble] = await Promise.all([
      api("/api/inspect", { method: "POST", form }),
      file.slice(0, 16384).text(),
    ]);
    if (requestId !== state.loadRequest) return;
    state.inspect = inspection;
    // Preserve explicit provenance markers in uploaded CSV/TXT comments.
    state.synthetic = /^\s*#\s*(?:synthetic|simulated)\b/im.test(preamble);
  } catch (e) {
    if (requestId === state.loadRequest) {
      state.fileName = null;
      $("#setup-line").textContent = "Choose another data file";
      $("#setup").open = true;
      updateWorkspace("upload");
      showError(`Could not read ${file.name}: ${e.message}`);
      $("#dropzone").focus();
    }
    return;
  } finally {
    if (requestId === state.loadRequest) {
      $("#dropzone").removeAttribute("aria-busy");
      $("#upload-title").textContent = state.inspect ? "Choose a different file" : "Drop your data here";
      $("#file-input").value = "";
    }
  }
  const sug = state.inspect.suggested;
  state.suggested = sug;
  state.mapping = {
    potential: sug.potential?.column || null,
    current: sug.current?.column || null,
    time: sug.time?.column || null,
  };
  state.units = {
    potential: sug.potential?.unit && UNITS.potential.includes(sug.potential.unit) ? sug.potential.unit : "V",
    current: sug.current?.unit && UNITS.current.includes(sug.current.unit) ? sug.current.unit : "A",
    time: sug.time?.unit && UNITS.time.includes(sug.time.unit) ? sug.time.unit : "s",
  };
  state.convention = "iupac";
  const t = state.inspect.table;
  $("#file-info").hidden = false;
  $("#file-info").innerHTML = `
    <strong>${esc(t.filename)}</strong><br>${esc(t.n_rows)} rows, ${esc(t.columns.length)} columns, ${esc(t.delimiter)}-delimited${t.decimal === "," ? ", decimal commas" : ""}<br>
    <span class="muted small">SHA-256 <code>${esc(t.sha256.slice(0, 16))}…</code>${t.notes.length ? "<br>" + esc(t.notes.join(" ")) : ""}</span>
    `;
  renderMapping();
  renderMetaForm();
  $("#mapping-card").hidden = false;
  $("#meta-card").hidden = false;
  $("#setup").open = true;
  updateSetupLine();
  $("#analyze-btn").disabled = false;
  updateWorkspace("confirm");
  $("#h-map").focus({ preventScroll: true });
}

function updateWorkspace(stage) {
  const loaded = stage !== "upload";
  $("#main").classList.toggle("has-file", loaded);
  $("#intro").hidden = loaded;
  $("#welcome-guide").hidden = loaded;
  ["upload", "confirm", "review"].forEach((step) => {
    const el = $(`#progress-${step}`);
    el.classList.toggle("is-complete", ["upload", "confirm", "review"].indexOf(step) < ["upload", "confirm", "review"].indexOf(stage));
    if (step === stage) el.setAttribute("aria-current", "step");
    else el.removeAttribute("aria-current");
  });
}

function columnSelect(role, allowNone) {
  const cols = state.inspect.columns;
  const cur = state.mapping[role];
  const opts = (allowNone ? [`<option value="">— none —</option>`] : [`<option value="">— select —</option>`])
    .concat(cols.map((c) => `<option value="${esc(c)}" ${c === cur ? "selected" : ""}>${esc(c)}</option>`));
  return `<select title="${esc(cur || "Select a column")}" aria-label="${role} column" data-map="${role}">${opts.join("")}</select>`;
}

function unitSelect(role) {
  return `<select aria-label="${role} unit" data-unit="${role}">${UNITS[role]
    .map((u) => `<option value="${esc(u)}" ${state.units[role] === u ? "selected" : ""}>${esc(uLabel(u))}</option>`)
    .join("")}</select>`;
}

function suggestionTag(role) {
  const s = state.suggested[role];
  if (s && s.column === state.mapping[role]) return `<span class="tag-suggested" title="Suggested from ${esc(s.basis)}">suggested</span>`;
  return "";
}

function renderMapping() {
  const focusSelector = activeControl();
  const ins = state.inspect;
  const mapped = new Set(Object.values(state.mapping).filter(Boolean));
  const head = ins.columns.map((c) => `<th${mapped.has(c) ? ' class="is-mapped"' : ""}>${esc(c)}</th>`).join("");
  const rows = ins.preview_rows.slice(0, 6)
    .map((r) => `<tr>${r.map((v) => `<td class="num">${v === null ? "—" : esc(sig(v, 5))}</td>`).join("")}</tr>`).join("");
  $("#mapping").innerHTML = `
    <div class="map-grid">
      <label class="field"><span>Potential column ${suggestionTag("potential")}</span><div class="inline">${columnSelect("potential")}${unitSelect("potential")}</div></label>
      <label class="field"><span>Current column ${suggestionTag("current")}</span><div class="inline">${columnSelect("current")}${unitSelect("current")}</div></label>
      <label class="field"><span>Time column (optional) ${suggestionTag("time")}</span><div class="inline">${columnSelect("time", true)}${unitSelect("time")}</div></label>
    </div>
    <div class="map-grid four">
      <label class="field"><span>Current sign convention</span>
        <select data-opt="convention">
          <option value="iupac" ${state.convention === "iupac" ? "selected" : ""}>Anodic + (IUPAC)</option>
          <option value="cathodic_positive" ${state.convention === "cathodic_positive" ? "selected" : ""}>Cathodic + (US)</option>
        </select></label>
      <label class="field"><span>Forward sweep of each cycle</span>
        <select data-opt="forward" title="Auto uses the initial scan direction, including a partial sweep">
          <option value="auto" ${state.forward === "auto" ? "selected" : ""}>Auto-detect</option>
          <option value="positive" ${state.forward === "positive" ? "selected" : ""}>Positive-going first</option>
          <option value="negative" ${state.forward === "negative" ? "selected" : ""}>Negative-going first</option>
        </select></label>
      <label class="field"><span>Smoothing (peak location only)</span>
        <select data-opt="smoothing" title="Savitzky–Golay window used to locate peaks; raw data are never changed">
          ${[0, 5, 10, 20].map((v) => `<option value="${v}" ${state.processing.smoothing_mv === v ? "selected" : ""}>${v ? `≈${v} mV window` : "none"}</option>`).join("")}
        </select></label>
      <label class="field"><span>Baseline for peak heights</span>
        <select data-opt="baseline">
          <option value="flat_prewave" ${state.processing.baseline === "flat_prewave" ? "selected" : ""}>Flat pre-wave</option>
          <option value="linear_prewave" ${state.processing.baseline === "linear_prewave" ? "selected" : ""}>Linear pre-wave</option>
          <option value="zero" ${state.processing.baseline === "zero" ? "selected" : ""}>None (from zero)</option>
        </select></label>
    </div>
    <div class="preview-wrap"><table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>
    <p class="muted small">First rows of the file as parsed. Mapped columns are highlighted. Nothing is modified until you analyze, and every conversion is listed with the results.</p>`;
  $$("[data-map]").forEach((s) => s.addEventListener("change", () => { state.mapping[s.dataset.map] = s.value || null; renderMapping(); updateSetupLine(); }));
  $$("[data-unit]").forEach((s) => s.addEventListener("change", () => { state.units[s.dataset.unit] = s.value; updateSetupLine(); }));
  $$("[data-opt]").forEach((s) => s.addEventListener("change", () => {
    const k = s.dataset.opt;
    if (k === "convention") state.convention = s.value;
    if (k === "forward") state.forward = s.value;
    if (k === "smoothing") state.processing.smoothing_mv = Number(s.value);
    if (k === "baseline") state.processing.baseline = s.value;
  }));
  restoreControl(focusSelector);
}

function metaValueMissing(f, m) {
  const v = m[f.key];
  if (f.type === "quantity") return !v || v.value === null || v.value === "" || v.value === undefined;
  if (f.key === "process_type" || f.key === "solvent") return !v || v === "unknown";
  return v === null || v === undefined || v === "";
}

function metaFieldRequired(field, metadata) {
  return Boolean(field.required || (field.key === "reference_detail" && metadata.reference_electrode === "other"));
}

function renderMetaForm() {
  const focusSelector = activeControl();
  const m = state.metadata;
  const refs = state.status.reference_electrodes;
  const fields = META_FIELDS.filter((f) => !f.showIf || f.showIf(m));
  const renderField = (f) => {
    const missing = metaFieldRequired(f, m) && metaValueMissing(f, m) ? `<span class="tag-missing">missing</span>` : "";
    const cls = f.span ? `field span${f.span}` : "field";
    let control = "";
    if (f.type === "text" || f.type === "number") {
      const val = m[f.key] ?? "";
      control = `<input data-meta="${f.key}" type="${f.type === "number" ? "number" : "text"}" ${f.type === "number" ? numericAttrs(f.key) : 'maxlength="500"'} value="${esc(val)}">`;
    } else if (f.type === "select") {
      control = `<select data-meta="${f.key}">${f.options.map(([v, l]) => `<option value="${esc(v)}" ${m[f.key] === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
    } else if (f.type === "reference") {
      control = `<select data-meta="${f.key}"><option value="">— select —</option>${Object.entries(refs)
        .map(([k, r]) => `<option value="${esc(k)}" ${m.reference_electrode === k ? "selected" : ""}>${esc(r.label)}</option>`).join("")}</select>`;
    } else if (f.type === "radio") {
      control = `<div class="radio-row">${f.options.map(([v, l]) => `<label><input type="radio" name="${f.key}" data-meta="${f.key}" value="${esc(v)}" ${m[f.key] === v ? "checked" : ""}> ${esc(l)}</label>`).join("")}</div>`;
    } else if (f.type === "quantity") {
      const q = m[f.key] || { value: null, unit: f.units[0] };
      control = `<div class="inline"><input data-qty="${f.key}" type="number" min="0" step="any" value="${esc(q.value ?? "")}">
        <select aria-label="${esc(f.label)} unit" data-qunit="${f.key}">${f.units.map((u) => `<option ${q.unit === u ? "selected" : ""}>${esc(u)}</option>`).join("")}</select></div>`;
    }
    if (f.type === "radio") return `<fieldset class="${cls}"><legend><span>${esc(f.label)} ${missing}</span></legend>${control}</fieldset>`;
    return `<label class="${cls}"><span>${esc(f.label)} ${missing}</span>${control}</label>`;
  };
  $("#meta-form").innerHTML = [
    { id: "required", title: "Required", description: "Key details for comparing literature conditions.", required: true },
    { id: "optional", title: "Optional", description: "Additional details to refine the analysis.", required: false },
  ].map((group) => `<section class="meta-section" aria-labelledby="meta-${group.id}-title">
    <div class="meta-section-heading"><h3 id="meta-${group.id}-title">${group.title}</h3><p class="muted small">${group.description}</p></div>
    <div class="meta-grid">${fields.filter((field) => metaFieldRequired(field, m) === group.required).map(renderField).join("")}</div>
  </section>`).join("");
  const rerenderKeys = new Set(["process_type", "solvent", "reference_electrode"]);
  $$("[data-meta]").forEach((el) => {
    const handler = () => {
      const key = el.dataset.meta;
      const field = META_FIELDS.find((f) => f.key === key);
      let v = el.value;
      if (field.type === "number") v = v === "" ? null : Number(v);
      if (v === "") v = null;
      state.metadata[key] = v;
      if (key === "electrode_area_cm2") state.normalize = false;
      if (rerenderKeys.has(key)) renderMetaForm();
      else refreshMissingTags();
      updateSetupLine();
    };
    el.addEventListener(el.tagName === "SELECT" || el.type === "radio" ? "change" : "input", handler);
  });
  $$("[data-qty]").forEach((el) => el.addEventListener("input", () => {
    const k = el.dataset.qty;
    state.metadata[k] = { ...(state.metadata[k] || { unit: META_FIELDS.find((f) => f.key === k).units[0] }), value: el.value === "" ? null : Number(el.value) };
    refreshMissingTags();
    updateSetupLine();
  }));
  $$("[data-qunit]").forEach((el) => el.addEventListener("change", () => {
    const k = el.dataset.qunit;
    state.metadata[k] = { ...(state.metadata[k] || { value: null }), unit: el.value };
  }));
  refreshMissingTags();
  restoreControl(focusSelector);
}

function refreshMissingTags() {
  const missing = META_FIELDS.filter((f) => metaFieldRequired(f, state.metadata) && (!f.showIf || f.showIf(state.metadata)) && metaValueMissing(f, state.metadata));
  $("#analyze-msg").innerHTML = missing.length
    ? `Missing: ${missing.map((f) => esc(f.label)).join(", ")}. You can still analyze; literature comparison will be weaker.`
    : "All key experiment details provided.";
  $$("#meta-form .field").forEach((label) => {
    const input = label.querySelector("[data-meta],[data-qty]");
    if (!input) return;
    const key = input.dataset.meta || input.dataset.qty;
    const f = META_FIELDS.find((x) => x.key === key);
    const tag = label.querySelector(".tag-missing");
    const isMissing = metaFieldRequired(f, state.metadata) && metaValueMissing(f, state.metadata);
    if (isMissing && !tag) label.querySelector("span").insertAdjacentHTML("beforeend", ` <span class="tag-missing">missing</span>`);
    if (!isMissing && tag) tag.remove();
  });
}

function updateSetupLine() {
  if (!state.fileName) return;
  const m = state.metadata;
  const refs = state.status?.reference_electrodes || {};
  const parts = [state.fileName];
  if (state.mapping.potential) parts.push(`E: ${state.mapping.potential} ${headerHasUnit(state.mapping.potential) ? "" : `(${uLabel(state.units.potential)})`}`);
  if (state.mapping.current) parts.push(`i: ${state.mapping.current} ${headerHasUnit(state.mapping.current) ? "" : `(${uLabel(state.units.current)})`}`);
  if (m.electrode_material) parts.push(m.electrode_material);
  if (m.electrolyte) parts.push(m.electrolyte);
  if (m.reference_electrode) parts.push(refs[m.reference_electrode]?.label || m.reference_electrode);
  if (m.scan_rate?.value) parts.push(`${m.scan_rate.value} ${m.scan_rate.unit}`);
  $("#setup-line").textContent = parts.join(", ");
}

// ------------------------------------------------------------------ analysis

function buildConfig() {
  const meta = {};
  for (const [k, v] of Object.entries(state.metadata)) {
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "object" && (v.value === null || v.value === undefined || Number.isNaN(v.value))) continue;
    meta[k] = v;
  }
  return {
    mapping: { potential: state.mapping.potential, current: state.mapping.current, time: state.mapping.time || null },
    units: state.units,
    current_convention: state.convention,
    forward_direction: state.forward,
    selected_cycle: state.selectedCycle,
    processing: state.processing,
    metadata: meta,
    reference_conversion: state.referenceConversion,
    normalize_by_area: state.normalize,
    normalize_by_area_confirmed: state.normalize,
    example_id: state.synthetic ? "uploaded_synthetic" : null,
  };
}

function evidenceKey(a) {
  return JSON.stringify({ meta: a.metadata, triggered: triggeredIds(a), plan: (a.evidence_plan || []).map((q) => q.query) });
}
const triggeredIds = (a) => (a.hypotheses || []).filter((h) => h.triggered).map((h) => h.id);

async function runAnalysis({ cycleChange = false } = {}) {
  showError("");
  if (!state.file) return showError("Load a data file first.");
  if (!state.mapping.potential || !state.mapping.current) return showError("Select the potential and current columns.");
  const columns = Object.values(state.mapping).filter(Boolean);
  if (new Set(columns).size !== columns.length) return showError("Potential, current and time must use different columns.");
  validateInputs();
  const invalid = $$("#meta-form input").find((input) => !input.checkValidity());
  if (invalid) { invalid.reportValidity(); return; }
  const requestId = ++state.analysisRequest;
  const generation = state.generation;
  const config = structuredClone(buildConfig());
  state.analyzing = true;
  updateDraft();
  const btn = $("#analyze-btn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Analyzing…`;
  const form = new FormData();
  form.append("file", state.file, state.fileName);
  form.append("config", JSON.stringify(config));
  try {
    const result = await api("/api/analyze", { method: "POST", form });
    if (requestId !== state.analysisRequest || generation !== state.generation) return;
    state.analysis = result;
    state.appliedConfig = config;
    state.normalize = Boolean(result.display.density && config.normalize_by_area);
  } catch (e) {
    if (requestId !== state.analysisRequest || generation !== state.generation) return;
    state.normalize = Boolean(state.analysis?.display.density && state.appliedConfig?.normalize_by_area);
    showError(`Analysis failed: ${e.message}`);
    return;
  } finally {
    if (requestId === state.analysisRequest && generation === state.generation) {
      state.analyzing = false;
      btn.disabled = false;
      btn.textContent = "Confirm & analyze";
      updateDraft();
    }
  }
  state.selectedCycle = state.analysis.selected_cycle;
  if (state.evidence.done && state.evidence.ranFor !== evidenceKey(state.analysis)) state.evidence.outdated = true;
  $("#results").hidden = false;
  $("#setup").open = false;
  renderResults();
  updateWorkspace("review");
  await refreshReport();
  if (requestId !== state.analysisRequest || generation !== state.generation) return;
  updateDraft();
  if (cycleChange) $(`[data-cycle="${state.selectedCycle}"]`)?.focus({ preventScroll: true });
  else $("#h-plot").focus({ preventScroll: true });
}

function renderResults() {
  const a = state.analysis;
  const banner = $("#synthetic-banner");
  banner.hidden = !state.synthetic;
  banner.textContent = "Simulated data. The uploaded file identifies its data as simulated. These results are not experimental measurements.";
  const notices = [...(a.notices || [])];
  $("#notices").innerHTML = notices.map((n) => `<div class="alert alert-warn">${esc(n)}</div>`).join("");
  const scaleNote = $("#scale-note");
  scaleNote.hidden = !a.potential_scale?.converted;
  scaleNote.textContent = `${a.potential_scale?.label || ""}${a.potential_scale?.note ? `; source: ${a.potential_scale.note}` : ""}`;
  renderCycleButtons();
  renderPlot();
  renderKeyStats();
  renderObserved();
  renderEvidence();
  renderNextCheck();
  renderReport();
}

function renderCycleButtons() {
  const a = state.analysis;
  $("#cycle-buttons").innerHTML = `<span class="seg-label">Cycle</span>` + a.cycle_list
    .map((c) => `<button type="button" data-cycle="${c.number}" aria-pressed="${c.number === a.selected_cycle}" class="${c.number === a.selected_cycle ? "on" : ""}" title="${c.complete ? "complete cycle" : "incomplete cycle"}">${c.number}${c.complete ? "" : "*"}</button>`)
    .join("");
  $$("[data-cycle]").forEach((b) => b.addEventListener("click", async () => {
    state.selectedCycle = Number(b.dataset.cycle);
    await runAnalysis({ cycleChange: true });
  }));
}

function indices(arr, value) {
  const out = [];
  for (let k = 0; k < arr.length; k++) if (arr[k] === value) out.push(k);
  return out;
}

function renderPlot() {
  const a = state.analysis;
  if (!a) return;
  const d = a.data;
  const sc = a.display.current_scale;
  const E = d.E;
  const I = d.i.map((v) => (v === null ? null : v * sc));
  const S = d.i_smooth.map((v) => (v === null ? null : v * sc));
  const sel = a.selected;
  const traces = [];
  const annotations = [];
  const narrowPlot = document.getElementById("plot").clientWidth < 480;
  const lineType = E.length > 20000 ? "scattergl" : "scatter"; // WebGL keeps large files responsive
  const showAll = $("#opt-all").checked;
  const showBase = $("#opt-base").checked;
  const showSmooth = $("#opt-smooth").checked;
  const unit = a.display.current_label;
  const colors = { forward: cssColor("--forward"), return: cssColor("--return"), other: cssColor("--other"), text: cssColor("--text"), warn: cssColor("--warn") };

  if (showAll) {
    for (const c of a.cycle_list) {
      if (c.number === sel.number) continue;
      const idx = indices(d.cycle, c.number);
      traces.push({
        type: lineType, x: idx.map((k) => E[k]), y: idx.map((k) => I[k]), mode: "lines", name: `Cycle ${c.number}`,
        line: { color: colors.other, width: 1.3 }, hovertemplate: `Cycle ${c.number}<br>E = %{x:.3f} V<br>i = %{y:.4g} ${unit}<extra></extra>`,
      });
    }
    const lead = indices(d.cycle, 0);
    if (lead.length > 1) {
      traces.push({ x: lead.map((k) => E[k]), y: lead.map((k) => I[k]), mode: "lines", name: "Outside cycles",
        line: { color: colors.other, width: 1, dash: "dot" }, hoverinfo: "skip" });
    }
  }
  for (const key of ["forward", "return"]) {
    const sw = sel[key];
    if (!sw) continue;
    const idx = [];
    for (let k = sw.start_index; k <= sw.end_index; k++) idx.push(k);
    const label = `Cycle ${sel.number}, ${key} sweep (${sw.direction_label})`;
    traces.push({
      type: lineType, x: idx.map((k) => E[k]), y: idx.map((k) => I[k]), mode: "lines", name: label,
      line: { color: colors[key], width: 2.4 },
      hovertemplate: `${esc(label)}<br>E = %{x:.3f} V<br>i = %{y:.4g} ${unit}<extra></extra>`,
    });
    if (showSmooth) {
      traces.push({ x: idx.map((k) => E[k]), y: idx.map((k) => S[k]), mode: "lines", name: `${key} (smoothed)`,
        line: { color: colors.text, width: 1, dash: "dot" }, hoverinfo: "skip" });
    }
    const n = sw.end_index - sw.start_index;
    for (const f of [0.28, 0.7]) {
      const k0 = sw.start_index + Math.round(f * n);
      const k1 = Math.min(sw.end_index, k0 + Math.max(3, Math.round(0.035 * n)));
      if (I[k0] === null || I[k1] === null) continue;
      annotations.push({ x: E[k1], y: I[k1], ax: E[k0], ay: I[k0], xref: "x", yref: "y", axref: "x", ayref: "y",
        showarrow: true, arrowhead: 2, arrowsize: 1.3, arrowwidth: 2.4, arrowcolor: colors[key], text: "" });
    }
    const b = sw.baseline;
    if (showBase && b && b.method !== "zero" && sw.peaks.length) {
      const dir = sw.direction;
      const far = dir > 0 ? Math.max(...sw.peaks.map((p) => p.potential)) : Math.min(...sw.peaks.map((p) => p.potential));
      const yAt = (e) => (b.intercept + b.slope * e) * sc;
      traces.push({ x: [b.e_from, b.e_to], y: [yAt(b.e_from), yAt(b.e_to)], mode: "lines", name: `${key} baseline window`,
        line: { color: colors[key], width: 6 }, opacity: 0.25, hovertemplate: `Baseline fit window (${esc(b.method)})<extra></extra>` });
      traces.push({ x: [b.e_to, far], y: [yAt(b.e_to), yAt(far)], mode: "lines", name: `${key} baseline`,
        line: { color: colors[key], width: 1.2, dash: "dash" }, hovertemplate: `Baseline (${esc(b.method)})<extra></extra>` });
    }
  }
  const peaks = [...(sel.forward?.peaks || []), ...(sel.return?.peaks || [])];
  if (peaks.length) {
    traces.push({
      x: peaks.map((p) => p.potential), y: peaks.map((p) => p.current * sc), mode: "markers+text", name: "Peaks",
      text: peaks.map((p) => p.label), textposition: peaks.map((p) => (p.kind === "anodic" ? "top center" : "bottom center")),
      textfont: { size: 12, color: colors.text },
      marker: { size: 10, color: colors.text, symbol: peaks.map((p) => (p.kind === "anodic" ? "triangle-up" : "triangle-down")) },
      customdata: peaks.map((p) => [sig(p.height * sc), p.width_v ? `${(p.width_v * 1000).toFixed(0)} mV` : "unresolved (overlap)", p.sweep]),
      hovertemplate: `%{text} (%{customdata[2]} sweep)<br>E = %{x:.3f} V<br>height above baseline = %{customdata[0]} ${unit}<br>FWHM = %{customdata[1]}<extra></extra>`,
    });
  }
  const fv = sel.forward?.vertex;
  if (fv?.rising) {
    annotations.push({ x: fv.potential, y: fv.current * sc, text: narrowPlot ? "still rising" : "current still rising<br>at the vertex", showarrow: true,
      arrowhead: 0, ax: narrowPlot ? -36 : -70, ay: narrowPlot ? 44 : -34, font: { size: 11.5, color: colors.warn }, arrowcolor: colors.warn, align: "right" });
  }
  const grid = cssColor("--border");
  const layout = {
    margin: { l: 70, r: 18, t: 12, b: 54 },
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: cssVar("--font-body"), size: 13, color: cssColor("--text") },
    xaxis: { title: { text: `E / ${esc(a.display.potential_label)}` }, gridcolor: grid, zeroline: false, linecolor: grid, mirror: true, showline: true },
    yaxis: { title: { text: `${a.display.density ? "j" : "i"} / ${unit}` }, gridcolor: grid, zerolinecolor: cssColor("--muted"), zerolinewidth: 1, linecolor: grid, mirror: true, showline: true },
    showlegend: false, hovermode: "closest", annotations,
  };
  Plotly.react("plot", traces, layout, { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"] });
  $("#plot-legend").innerHTML =
    `<span class="sw sw-fwd"></span>forward sweep <span class="sw sw-ret"></span>return sweep` +
    (showAll && a.cycle_list.length > 1 ? `<span class="sw sw-other"></span>other cycles` : "") +
    `. Arrows show scan direction; ▲▼ mark detected peaks${showBase ? "; dashed lines are baselines (shaded: fit window)" : ""}.`;
}

function renderKeyStats() {
  const a = state.analysis;
  const sel = a.selected;
  const th = a.thresholds;
  const pairs = sel.pairs || [];
  const weakest = pairs.filter((p) => p.height_ratio !== null).sort((x, y) => x.height_ratio - y.height_ratio)[0];
  const main = sel.main_pair !== null && sel.main_pair !== undefined ? pairs[sel.main_pair] : null;
  const limit = a.metadata.process_type === "dissolved_species" ? th.delta_ep_dissolved_v : th.delta_ep_material_v;
  const tr = a.trends;
  const fv = sel.forward?.vertex;
  const tiles = [
    { label: "Return / forward peak height", tip: "Weakest candidate pair, baseline-corrected heights", value: weakest ? fmt(weakest.height_ratio) : "n/a",
      sub: weakest ? `pair ${weakest.anodic}/${weakest.cathodic}` : "no pair detected", flag: weakest && weakest.height_ratio < th.ratio_low },
    { label: "Return / forward charge", tip: "Net charge on the return sweep ÷ net charge on the forward sweep", value: fmt(sel.charge_ratio),
      sub: sel.charge_ratio === null ? "needs time column or scan rate" : "net sweep charge", flag: sel.charge_ratio !== null && sel.charge_ratio < th.charge_ratio_low },
    { label: "Peak separation ΔEp", tip: "Anodic minus cathodic peak potential of the main pair", value: main ? `${(main.delta_ep * 1000).toFixed(0)} mV` : "n/a",
      sub: main ? `pair ${main.anodic}/${main.cathodic}` : "", flag: main && main.delta_ep > limit },
    { label: "Cycle-to-cycle peak change", tip: "Tracked forward peak height, first vs last complete cycle", value: tr && tr.height_change_pct !== undefined && tr.height_change_pct !== null ? `${tr.height_change_pct > 0 ? "+" : ""}${tr.height_change_pct.toFixed(0)}%` : "n/a",
      sub: tr && tr.first_cycle ? `cycles ${tr.first_cycle} to ${tr.last_cycle}` : "needs ≥ 2 complete cycles", flag: tr && tr.height_change_pct < th.fade_pct },
  ];
  if (fv) {
    tiles.push({ label: "Current at forward vertex", tip: "Rise over the post-peak minimum, as a share of the largest forward peak", value: fv.rise_fraction !== null ? `${(fv.rise_fraction * 100).toFixed(0)}%` : "n/a",
      sub: fv.rising ? "still rising" : "decaying or flat", flag: fv.rising });
  }
  $("#key-stats").innerHTML = tiles.map((t) => `
    <div class="stat ${t.flag ? "flag" : ""}" title="${esc(t.tip)}${t.flag ? ", outside the rule threshold" : ""}">
      <div class="stat-label">${esc(t.label)}</div>
      <div class="stat-value">${esc(t.value)}</div>
      <div class="stat-sub">${esc(t.sub)}${t.flag ? ", flagged" : ""}</div>
    </div>`).join("") +
    `<p class="muted small stats-note">Flagged tiles exceed a published rule threshold (see each explanation). Flags are not verdicts.</p>`;
}

function renderObserved() {
  const a = state.analysis;
  const sel = a.selected;
  const sc = a.display.current_scale;
  const unit = a.display.current_label;
  const peaks = [...(sel.forward?.peaks || []), ...(sel.return?.peaks || [])].sort((x, y) => x.label.localeCompare(y.label));
  const peakRows = peaks.map((p) => `<tr><td><strong>${esc(p.label)}</strong></td><td>${esc(p.sweep)}</td>
      <td class="num">${p.potential.toFixed(3)}</td><td class="num">${esc(sig(p.height * sc))}</td>
      <td class="num">${p.width_v ? (p.width_v * 1000).toFixed(0) : "—"}</td>
      <td class="small">${p.near_vertex ? "near vertex" : ""}${p.width_v ? "" : " overlapping"}</td></tr>`).join("");
  const pairRows = (sel.pairs || []).map((r) => `<tr><td><strong>${esc(r.anodic)}/${esc(r.cathodic)}</strong></td>
      <td class="num">${(r.delta_ep * 1000).toFixed(0)}</td><td class="num">${r.e_mid.toFixed(3)}</td>
      <td class="num">${fmt(r.height_ratio)}</td>${a.metadata.process_type === "dissolved_species" ? `<td class="num">${fmt(r.nicholson_ratio)}</td>` : ""}
      <td class="num">${fmt(r.width_ratio)}</td></tr>`).join("");
  const flags = (a.quality || []).map((q) => `<div class="flag-row sev-${esc(q.severity)}">${esc(q.message)}</div>`).join("");
  const proc = (a.processing || []).map((p) => `<li><strong>${esc(p.step)}:</strong> ${esc(p.detail)}</li>`).join("");
  const missing = (a.metadata_status || []).filter((m) => m.status === "missing");
  $("#observed").innerHTML = `
    <div class="obs-grid">
      <div>
        <ul class="obs-list">${a.observations.map((o) => `<li>${esc(o.text)}</li>`).join("")}</ul>
        ${flags ? `<div class="flags">${flags}</div>` : `<p class="muted small">No data-quality flags (clipping, scan-rate mismatch, coarse steps, noise, sign convention).</p>`}
        ${missing.length ? `<div class="alert alert-info small"><strong>Missing metadata:</strong> ${missing.map((m) => `<span class="tip" title="${esc(m.why)}">${esc(m.label)}</span>`).join(", ")}</div>` : ""}
        <details class="disclose"><summary>Processing disclosed (${a.processing.length} steps)</summary><ul>${proc}</ul>
          <p class="muted small">Raw data preserved: ${esc(a.rows_used)} rows used${a.rows_excluded ? `, ${esc(a.rows_excluded)} excluded` : ""}; file SHA-256 <code>${esc(a.provenance.sha256.slice(0, 16))}…</code></p></details>
      </div>
      <div>
        <div class="table-wrap"><table>
          <thead><tr><th>Peak</th><th>Sweep</th><th>E<sub>p</sub> / V</th><th>Height / ${esc(unit)}</th><th>FWHM / mV</th><th></th></tr></thead>
          <tbody>${peakRows || `<tr><td colspan="6" class="muted">No peaks above the detection threshold.</td></tr>`}</tbody></table></div>
        <div class="table-wrap table-spaced"><table>
          <thead><tr><th>Pair</th><th>ΔE<sub>p</sub> / mV</th><th>Midpoint / V</th><th>Height ratio</th>${a.metadata.process_type === "dissolved_species" ? "<th>Nicholson</th>" : ""}<th>Width ratio</th></tr></thead>
          <tbody>${pairRows || `<tr><td colspan="6" class="muted">No forward/return pair.</td></tr>`}</tbody></table></div>
        <p class="muted small">Pairs are geometric (matched by potential order), not mechanistic assignments. Potentials: ${esc(a.display.potential_label)}.</p>
      </div>
    </div>`;
}

// ------------------------------------------------------------------ report

async function refreshReport() {
  const analysis = state.analysis;
  if (!analysis) return;
  const requestId = ++state.reportRequest;
  const { data, ...summary } = analysis;
  const ev = state.evidence;
  const evidence = ev.done && !ev.outdated
    ? { mode: ev.mode, queries: ev.queries.map(({ id, query, purpose, hypotheses, status }) => ({ id, query, purpose, hypotheses, status })), log: ev.log, sources: ev.sources, message: ev.message }
    : { mode: "not run", message: "Literature evidence has not been retrieved yet." };
  try {
    const report = await api("/api/report", { method: "POST", json: { analysis_id: analysis.analysis_id, evidence } });
    if (requestId !== state.reportRequest || analysis !== state.analysis) return;
    state.report = report;
  } catch (e) {
    if (requestId === state.reportRequest && analysis === state.analysis) showError(`Report failed: ${e.message}`);
    return;
  }
  renderNextCheck();
  renderReport();
  updateDraft();
}

function evidenceBadge(status) {
  return {
    "condition-matched": `<span class="badge b-full">condition-matched evidence</span>`,
    related: `<span class="badge b-abstract">related evidence (different or partial conditions)</span>`,
    none: `<span class="badge b-none">no supporting passage retrieved</span>`,
    "not needed": `<span class="badge b-none">assumption-based check</span>`,
    unavailable: `<span class="badge b-error">literature evidence unavailable</span>`,
    "not run": `<span class="badge b-none">literature not searched yet</span>`,
  }[status] || `<span class="badge b-none">evidence not retrieved yet</span>`;
}

function renderNextCheck() {
  const r = state.report;
  if (!r) {
    $("#next-check").innerHTML = `<p class="muted"><span class="spinner"></span> Building recommendation…</p>`;
    return;
  }
  const nc = r.next_check;
  if (!nc) {
    $("#next-check").innerHTML = `<p class="muted">No check available.</p>`;
    return;
  }
  const ev = state.evidence;
  const note = !ev.done
    ? `Ranking uses the measured features only. Run “Find literature evidence” to weigh retrieved literature.`
    : r.evidence_summary.n_sources
      ? `Ranking weighed ${r.evidence_summary.n_sources} retrieved source(s) (${esc(ev.mode)} evidence).`
      : `Literature evidence was unavailable, so the ranking uses the measured features only.`;
  $("#next-check").innerHTML = `
    <p class="next-title">${esc(nc.title)}</p>
    <p class="next-proc">${esc(nc.procedure)}</p>
    <div class="label small muted"><strong>Why this check</strong></div>
    <ul class="reasons">${nc.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
    ${nc.tests.length ? `<dl class="outcomes">${nc.tests.map((t) => `<dt>${esc(t.title)}</dt><dd>${esc(t.outcome)}</dd>`).join("")}</dl>` : ""}
    <div class="evidence-note">${note}</div>`;
}

function passageHtml(p) {
  const text = p.text || "";
  let out = "";
  let last = 0;
  for (const [a, b] of p.highlights || []) {
    if (a < last || b > text.length) continue;
    out += esc(text.slice(last, a)) + `<mark>${esc(text.slice(a, b))}</mark>`;
    last = b;
  }
  out += esc(text.slice(last));
  return out;
}

function renderReport() {
  const r = state.report;
  if (!r) {
    $("#report").innerHTML = `<p class="muted"><span class="spinner"></span> Building report…</p>`;
    return;
  }
  const obs = `<div class="rcol"><h3>Observed</h3><ul class="obs-list small">${r.observed.map((o) => `<li>${esc(o)}</li>`).join("")}</ul>
    ${r.quality.length ? `<p class="small"><strong>${r.quality.length} data-quality flag(s)</strong> listed above.</p>` : ""}</div>`;
  const hyps = r.explanations.length
    ? r.explanations.map((h, k) => `
      <div class="hyp">
        <div class="hyp-title">H${k + 1}. ${esc(h.title)}</div>
        <div class="ev-status">${evidenceBadge(h.evidence_status)}</div>
        <p>${esc(h.statement)}</p>
        <div class="label">Connected to observed features</div>
        <ul>${h.observations.map((o) => `<li>${esc(o)}</li>`).join("")}${(h.metadata_gaps || []).map((g) => `<li class="small is-bad">Missing metadata: ${esc(g)}</li>`).join("")}</ul>
        ${(h.evidence || []).length ? `<div class="label">Evidence</div>${h.evidence.map((e) => `
          <div class="passage">“${passageHtml({ text: e.passage, highlights: [] })}”
            <div class="passage-meta">${safeUrl(e.link) ? `<a href="${esc(safeUrl(e.link))}" target="_blank" rel="noopener noreferrer">${esc(e.title)}</a>` : esc(e.title)}${e.year ? ` (${esc(e.year)})` : ""}<br><span class="badge ${LEVEL_CLASS[e.level] || "b-none"}">${esc(e.level)}</span> <span class="app-level">${esc(e.applicability)}</span>${e.cached ? ` <span class="badge b-cached">cached</span>` : ""}</div></div>`).join("")}` : ""}
        ${(h.evidence_limits || []).length ? `<div class="label">Limits</div><ul>${h.evidence_limits.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
        <details class="disclose"><summary>Rule and assumptions</summary><ul><li>Rule: ${esc(h.trigger_rule)}</li>
          ${h.assumptions.map((x) => `<li>${esc(x)}</li>`).join("")}${h.background ? `<li>Background: ${esc(h.background)}</li>` : ""}</ul></details>
      </div>`).join("")
    : `<p class="small">No troubleshooting rule was triggered by the measured features. Review the data-quality flags and stated assumptions before interpreting reversibility.</p>`;
  const considered = r.considered.length
    ? `<details class="disclose"><summary>Also considered, not indicated (${r.considered.length})</summary><ul>${r.considered.map((c) => `<li><strong>${esc(c.title)}</strong>: ${esc(c.reason)}</li>`).join("")}</ul></details>` : "";
  const nc = r.next_check;
  const next = `<div class="rcol"><h3>Next check</h3>
    ${nc ? `<p><strong>${esc(nc.title)}</strong></p><p class="small">${esc(nc.procedure)}</p>` : ""}
    ${r.other_checks.length ? `<div class="label small muted"><strong>Other useful checks</strong></div><ol class="small" start="2">${r.other_checks.map((c) => `<li>${esc(c.title)}</li>`).join("")}</ol>` : ""}
    ${r.metadata_checks.length ? `<div class="label small muted"><strong>Metadata to record</strong></div><ul class="small">${r.metadata_checks.map((m) => `<li><span class="tip" title="${esc(m.why)}">${esc(m.label)}</span></li>`).join("")}</ul>` : ""}
  </div>`;
  $("#report").innerHTML = obs + `<div class="rcol"><h3>Possible explanations</h3>${hyps}${considered}</div>` + next;
}

// ------------------------------------------------------------------ evidence

function evidenceContext() {
  const a = state.analysis;
  return { metadata: a.metadata, hypothesis_ids: triggeredIds(a), measured_scan_rate_v_s: a.scan_rate_measured };
}

async function pool(items, size, fn) {
  const queue = [...items];
  const workers = Array.from({ length: Math.min(size, queue.length) }, async () => {
    while (queue.length) await fn(queue.shift());
  });
  await Promise.all(workers);
}

async function runEvidence() {
  const a = state.analysis;
  if (!a || state.evidence.running) return;
  const plan = a.evidence_plan || [];
  const preferCache = $("#opt-prefer-cache").checked;
  state.evidence = { ...freshEvidence(), running: true, queries: plan.map((q) => ({ ...q, status: "pending" })) };
  const ev = state.evidence;
  const current = () => state.evidence === ev && state.analysis === a;
  $("#evidence-btn").disabled = true;
  renderEvidence();
  const ctx = evidenceContext();
  const records = [];
  for (const q of ev.queries) {
    q.status = "running";
    if (!current()) return;
    renderEvidence();
    try {
      const r = await api("/api/evidence/search", { method: "POST", json: { analysis_id: a.analysis_id, query_id: q.id, query: q.query, purpose: q.purpose, hypothesis_ids: q.hypotheses, context: ctx, prefer_cache: preferCache } });
      if (!current()) return;
      q.status = r.log.status;
      q.log = r.log;
      ev.log.push(r.log);
      records.push(...r.sources);
    } catch (e) {
      q.status = "error";
      q.log = { error: e.message };
      ev.log.push({ engine: "google_scholar", query: q.query, status: "error", error: e.message });
    }
    if (!current()) return;
    renderEvidence();
  }
  if (records.length) {
    try {
      const sel = await api("/api/evidence/select", { method: "POST", json: { analysis_id: a.analysis_id, sources: records, context: ctx } });
      if (!current()) return;
      ev.sources = sel.sources;
      ev.extractPlan = sel.extract.map((x) => ({ ...x, status: "pending" }));
    } catch (e) {
      ev.message = `Could not rank sources: ${e.message}`;
    }
    if (!current()) return;
    renderEvidence();
    await pool(ev.extractPlan, 2, async (item) => {
      item.status = "running";
      if (!current()) return;
      renderEvidence();
      const idx = ev.sources.findIndex((s) => s.source_id === item.source_id);
      try {
        const r = await api("/api/evidence/extract", { method: "POST", json: { analysis_id: a.analysis_id, source: ev.sources[idx], context: ctx, prefer_cache: preferCache } });
        if (!current()) return;
        ev.sources[idx] = r.source;
        item.status = r.log.ok ? (r.log.cached ? "cached" : "live") : r.log.status;
        item.classification = r.log.classification;
        ev.log.push(r.log);
      } catch (e) {
        item.status = "error";
        ev.log.push({ engine: "extract", url: item.url, status: "error", error: e.message });
      }
      if (!current()) return;
      renderEvidence();
    });
  }
  if (!current()) return;
  const okLogs = ev.log.filter((l) => l.ok);
  const live = okLogs.some((l) => l.status === "live");
  const cached = okLogs.some((l) => l.cached || l.status === "cached" || l.status === "provider-cached");
  ev.mode = live && cached ? "live + cached" : live ? "live" : cached ? "cached" : "unavailable";
  if (!okLogs.length) {
    const reason = ev.log.find((l) => l.error)?.error || "No response.";
    ev.message = `Literature evidence unavailable: ${reason} The numerical analysis above is unaffected.`;
  }
  ev.running = false;
  ev.done = true;
  ev.ranFor = evidenceKey(a);
  $("#evidence-btn").disabled = false;
  $("#evidence-btn").textContent = "Re-run evidence search";
  renderEvidence();
  await refreshReport();
}

function statusChip(status, extra = "") {
  const cls = { live: "b-live", cached: "b-cached", "provider-cached": "b-cached", error: "b-error", unavailable: "b-none", pending: "b-none", running: "b-none" }[status] || "b-none";
  const text = status === "running" ? `<span class="spinner"></span> running` : esc(status);
  return `<span class="badge ${cls}">${text}</span>${extra}`;
}

function renderEvidence() {
  const ev = state.evidence;
  const a = state.analysis;
  const s = state.status;
  if (!a) return;
  let head = "";
  if (!ev.running && !ev.done) {
    const plan = a.evidence_plan || [];
    const modeText = s.evidence_mode === "live"
      ? "Live: each query uses one SerpApi Google Scholar search; each extracted page uses one Extract credit."
      : "No live SerpApi key on this server: only previously retrieved, cached responses can be shown (labeled cached).";
    head = `<div class="alert alert-info small">${esc(modeText)} Budget: ${s.max_queries} queries, ${s.max_extracts} page extractions.</div>
      <div class="query-list">${plan.map((q) => `<div class="query-row"><code>${esc(q.query)}</code><span class="q-purpose">${esc(q.purpose)}</span></div>`).join("") || `<p class="muted">No queries planned: enter the electrode material or analyte.</p>`}</div>`;
  } else {
    head = `<div class="query-list">${ev.queries.map((q) => {
      const n = q.log?.results_count;
      const when = q.log?.retrieved_at ? `, retrieved ${esc(q.log.retrieved_at)}` : "";
      const err = q.log?.error ? `<span class="small is-bad">${esc(q.log.error)}</span>` : "";
      return `<div class="query-row">${statusChip(q.status)}<code>${esc(q.query)}</code><span class="q-purpose">${esc(q.purpose)}${n !== undefined ? `, ${n} results` : ""}${when}</span>${err}</div>`;
    }).join("")}
    ${ev.extractPlan.length ? `<div class="query-row"><span class="small"><strong>SerpApi Extract:</strong> ${ev.extractPlan.filter((x) => ["live", "cached", "provider-cached"].includes(x.status)).length}/${ev.extractPlan.length} pages retrieved</span>
      ${ev.extractPlan.some((x) => x.status === "running") ? `<span class="spinner"></span>` : ""}</div>` : ""}</div>`;
    if (ev.message) head += `<div class="alert alert-warn small">${esc(ev.message)}</div>`;
    if (ev.outdated) head += `<div class="alert alert-warn small">The analysis changed since this evidence was retrieved. Re-run the evidence search to update it.</div>`;
  }
  $("#evidence-status").innerHTML = head;
  if (!ev.sources.length) {
    $("#evidence-table").innerHTML = ev.done && !ev.message ? `<p class="muted">No sources returned.</p>` : "";
    return;
  }
  const levelRank = { "full text": 0, abstract: 1, "search snippet": 2 };
  const appRank = { "condition-matched": 0, "partially matched": 1, "conditions not stated": 2, "different conditions": 3 };
  const triggered = new Set(triggeredIds(a));
  const titleFor = (id) => (a.hypotheses.find((h) => h.id === id) || {}).title || (id === "context" ? "Matching conditions" : id);
  const sources = [...ev.sources].sort((x, y) =>
    (appRank[x.applicability?.level] ?? 3) - (appRank[y.applicability?.level] ?? 3) ||
    (levelRank[x.evidence_level] ?? 3) - (levelRank[y.evidence_level] ?? 3) ||
    (y.passages?.length || 0) - (x.passages?.length || 0));
  const rows = sources.map((src) => {
    const url = safeUrl(src.link) || safeUrl(src.content?.final_url) || safeUrl(src.content?.url);
    const extracting = ev.extractPlan.find((x) => x.source_id === src.source_id && x.status === "running");
    const linkNote = !src.content?.via
      ? "Scholar link (page not fetched)"
      : src.content.status === "retrieval failed"
        ? "SerpApi Extract could not retrieve this page"
        : "page retrieved via SerpApi Extract";
    const grouped = new Map();
    for (const p of src.passages || []) {
      if (p.hypothesis_id !== "context" && !triggered.has(p.hypothesis_id)) continue;
      const g = grouped.get(p.text) || { ...p, labels: [] };
      g.labels.push(titleFor(p.hypothesis_id));
      grouped.set(p.text, g);
    }
    const passages = [...grouped.values()]
      .sort((p, q) => (p.labels.length === 1 && p.hypothesis_id === "context") - (q.labels.length === 1 && q.hypothesis_id === "context"))
      .slice(0, 3)
      .map((p) => `<div class="passage">“${passageHtml(p)}”<div class="passage-meta">${p.labels.map(esc).join("; ")}<br>${esc(p.location)}${p.verbatim_verified ? (p.level === "search snippet" ? ", matches search snippet" : ", matches retrieved text ✓") : ""}</div></div>`)
      .join("") || `<span class="muted small">No passage matched the hypotheses' terms.</span>`;
    const conds = (src.conditions || []).map((c) => `<span class="chip c-${esc(c.status)}" title="${esc(c.note)}${c.paper ? ". Paper: " + esc(c.paper) : ""}">${STATUS_TEXT[c.status] || ""} ${esc(c.condition)}</span>`).join("");
    const app = src.applicability || {};
    const diffs = [
      ...(app.differences || []).map((d) => `<li>${esc(d.note)}</li>`),
      ...((app.not_stated || []).length ? [`<li class="muted">Not stated in retrieved text: ${esc(app.not_stated.join(", "))}</li>`] : []),
    ].join("");
    return `<tr>
      <td class="col-src"><div class="src-title">${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(src.title)}</a>` : esc(src.title)}</div>
        <div class="src-meta">${esc(src.venue || "")}${src.year ? `, ${esc(src.year)}` : ""}${src.cited_by ? `, cited by ${esc(src.cited_by)}` : ""}</div>
        <div class="src-meta">${esc(linkNote)}${src.cached ? ` <span class="badge b-cached">cached ${esc(src.retrieved_at || "")}</span>` : ""}</div></td>
      <td class="col-pass">${passages}</td>
      <td>${extracting ? `<span class="spinner"></span>` : `<span class="badge ${LEVEL_CLASS[src.evidence_level] || "b-none"}">${esc(src.evidence_level)}</span>`}
        <div class="src-meta src-reason">${esc(src.content?.reason || "")}</div></td>
      <td class="col-app"><div class="app-level app-${APP_CLASS[app.level] || "none"}">${esc(app.level || "")}</div><div class="cond">${conds}</div></td>
      <td class="col-diff">${diffs ? `<ul class="diff-list">${diffs}</ul>` : `<span class="muted small">None found in retrieved text.</span>`}</td>
    </tr>`;
  }).join("");
  $("#evidence-table").innerHTML = `<div class="table-wrap"><table class="ev-table">
    <thead><tr><th>Paper &amp; source link</th><th>Retrieved passage (verbatim)</th><th>Evidence level</th><th>Conditions vs yours</th><th>Differences / missing</th></tr></thead>
    <tbody>${rows}</tbody></table></div>
    <p class="muted small">✓ match, ≈ related, ✗ differs, ? not stated in the retrieved text, – not entered by you. Hover chips for details. Search snippets are Google Scholar excerpts, not full-paper evidence.</p>`;
}

// ------------------------------------------------------------------ dialogs

function confirmDialog(title, bodyHtml, { okText = "Confirm", onRender } = {}) {
  const dlg = $("#confirm-dialog");
  $("#dlg-title").textContent = title;
  $("#dlg-body").innerHTML = bodyHtml;
  $("#dlg-ok").textContent = okText;
  $("#dlg-ok").disabled = false;
  if (onRender) onRender(dlg);
  return new Promise((resolve) => {
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true });
    dlg.showModal();
  });
}

async function openScaleDialog() {
  const a = state.analysis;
  if (!a || draftDirty() || state.analyzing) return;
  const m = state.metadata;
  const refLabel = state.status.reference_electrodes[m.reference_electrode]?.label || "the recorded reference";
  let preview = null;
  const ok = await confirmDialog("Potential scale", `
    <p class="small">Potentials are shown as recorded (vs ${esc(refLabel)}). A conversion is applied only after you confirm the offset below.</p>
    <label class="field"><span>Convert to</span><select id="scale-target">
      <option value="">Recorded scale (no conversion)</option><option value="SHE">SHE</option><option value="RHE">RHE (needs pH)</option><option value="custom">Custom offset</option></select></label>
    <label class="field" id="ph-field" hidden><span>pH</span><input id="scale-ph" type="number" step="any" value="${esc(m.ph ?? "")}"></label>
    <div id="custom-fields" hidden>
      <label class="field"><span>Offset to add (V)</span><input id="scale-offset" type="number" step="any"></label>
      <label class="field"><span>Source of this offset</span><input id="scale-desc" type="text"></label>
    </div>
    <div id="scale-preview" class="alert alert-info small">Choose a target scale.</div>`, {
    okText: "Apply conversion",
    onRender: (dlg) => {
      const target = $("#scale-target", dlg);
      let previewRequest = 0;
      const update = async () => {
        const request = ++previewRequest;
        preview = null;
        $("#dlg-ok").disabled = true;
        $("#ph-field", dlg).hidden = target.value !== "RHE";
        $("#custom-fields", dlg).hidden = target.value !== "custom";
        if (!target.value) {
          preview = null;
          $("#dlg-ok").disabled = false;
          $("#scale-preview", dlg).textContent = "No conversion: potentials stay on the recorded scale.";
          return;
        }
        const ph = $("#scale-ph", dlg).value;
        const off = $("#scale-offset", dlg).value;
        let nextPreview;
        try { nextPreview = await api("/api/conversion-preview", { method: "POST", json: {
          from: m.reference_electrode, target: target.value, ph: ph === "" ? null : Number(ph), temperature_c: m.temperature_c ?? null,
          offset_v: target.value !== "custom" || off === "" ? null : Number(off), description: $("#scale-desc", dlg).value || null } });
        } catch (error) {
          if (request === previewRequest) $("#scale-preview", dlg).textContent = error.message;
          return;
        }
        if (request !== previewRequest || !dlg.open) return;
        preview = nextPreview;
        $("#dlg-ok").disabled = !preview.possible;
        $("#scale-preview", dlg).innerHTML = preview.possible
          ? `<strong>${esc(preview.to_label)}</strong><br>${esc(preview.explanation)}<br>${preview.caveats.map(esc).join("<br>")}${preview.note ? `<br>Source: ${esc(preview.note)}` : ""}`
          : esc(preview.reason);
      };
      dlg.querySelectorAll("select,input").forEach((el) => el.addEventListener("input", update));
    },
  });
  if (!ok) return;
  const target = $("#scale-target").value;
  if (!target) state.referenceConversion = null;
  else if (preview?.possible) {
    if (target === "RHE") state.metadata.ph = Number($("#scale-ph").value);
    state.referenceConversion = { target, offset_v: target === "custom" ? preview.offset_v : null,
      description: target === "custom" ? $("#scale-desc").value || null : null, confirmed: true };
  } else return;
  await runAnalysis();
}

async function openAreaDialog() {
  if (draftDirty() || state.analyzing) return;
  const area = state.metadata.electrode_area_cm2;
  if (state.normalize) {
    const ok = await confirmDialog("Current density", `<p>Currents are divided by ${esc(area)} cm². Switch back to current?</p>`, { okText: "Show current" });
    if (ok) {
      state.normalize = false;
      await runAnalysis();
    }
    return;
  }
  if (!area) {
    await confirmDialog("Current density", `<p>Enter the electrode area in Experiment details first. BenchCheck never assumes an area.</p>`, { okText: "OK" });
    return;
  }
  const ok = await confirmDialog("Normalize current by electrode area?", `
    <p>All currents will be divided by <strong>${esc(area)} cm²</strong> (the area you entered).</p>
    <p class="small muted">For porous or composite electrodes the electrochemically active area can differ greatly from the geometric area. The conversion is recorded in the processing log and the report.</p>`,
    { okText: "Normalize" });
  if (!ok) return;
  state.normalize = true;
  await runAnalysis();
}

// ------------------------------------------------------------------ export and glossary

function download(name, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function exportReport(kind) {
  const r = state.report;
  if (!r || draftDirty() || state.analyzing) return;
  const base = `benchcheck-report-${(state.fileName || "data").replace(/\.\w+$/, "")}`;
  if (kind === "md") download(`${base}.md`, r.markdown, "text/markdown");
  if (kind === "html") download(`${base}.html`, r.html, "text/html");
  if (kind === "json") {
    const { data, ...analysis } = state.analysis;
    const { markdown, html, ...report } = r;
    download(`${base}.json`, JSON.stringify({ report, analysis, evidence: state.evidence.outdated ? { mode: "outdated", log: [], sources: [], message: "Evidence from older settings excluded." } : { mode: state.evidence.mode, log: state.evidence.log, sources: state.evidence.sources } }, null, 2), "application/json");
  }
}

function renderGlossary() {
  $("#glossary").innerHTML = GLOSSARY.map(([t, d]) => `<dt>${esc(t)}</dt><dd>${esc(d)}</dd>`).join("");
}

function activeControl() {
  const el = document.activeElement;
  if (!el) return null;
  const attribute = ["data-meta", "data-qty", "data-qunit", "data-map", "data-unit", "data-opt"].find((key) => el.hasAttribute(key));
  return attribute ? `[${attribute}="${CSS.escape(el.getAttribute(attribute))}"]${el.type === "radio" ? `[value="${CSS.escape(el.value)}"]` : ""}` : null;
}
function restoreControl(selector) { if (selector) $(selector)?.focus({ preventScroll: true }); }
function numericAttrs(key) {
  if (key === "electrons_n") return 'min="1" step="1"';
  if (key === "temperature_c") return 'min="-273.149999" step="any"';
  if (["electrode_area_cm2", "active_mass_mg", "diffusion_coefficient_cm2_s"].includes(key)) return 'min="0" step="any"';
  return 'step="any"';
}
function headerHasUnit(name) { return /(?:\([^)]*\)|\[[^\]]*\]|\/(?:m?V|[munpµ]?A)(?:\/cm2)?)$/.test(name || ""); }
function draftDirty() {
  if (!state.analysis || !state.appliedConfig) return false;
  const comparable = (config) => { const copy = structuredClone(config); delete copy.selected_cycle; return JSON.stringify(copy); };
  return comparable(buildConfig()) !== comparable(state.appliedConfig);
}
function validateInputs() {
  const positive = new Set(["electrode_area_cm2", "active_mass_mg", "diffusion_coefficient_cm2_s"]);
  $$("#meta-form input").forEach((input) => {
    input.setCustomValidity("");
    if ((input.dataset.qty || positive.has(input.dataset.meta)) && input.value !== "" && Number(input.value) <= 0) input.setCustomValidity("Enter a positive value.");
    const invalid = !input.validity.valid;
    input.setAttribute("aria-invalid", String(invalid));
    let message = input.closest(".field").querySelector(".field-error");
    if (invalid && !message) { message = document.createElement("span"); message.className = "field-error"; message.setAttribute("role", "alert"); input.closest(".field").append(message); }
    if (message) { message.hidden = !invalid; message.textContent = invalid ? input.validationMessage : ""; }
  });
}
function updateDraft() {
  validateInputs();
  const dirty = draftDirty();
  let banner = $("#draft-warning");
  if (!banner) { banner = document.createElement("div"); banner.id = "draft-warning"; banner.className = "alert alert-warn"; banner.setAttribute("role", "status"); $("#results").prepend(banner); }
  banner.hidden = !dirty;
  banner.textContent = "Settings changed: results are out of date. Confirm & analyze to update results and exports.";
  $$("[data-cycle], [data-export], #btn-scale, #btn-area, #evidence-btn").forEach((button) => { button.disabled = dirty || state.analyzing || (button.id === "evidence-btn" && state.evidence.running); });
  $$("[data-export]").forEach((button) => { button.disabled ||= !state.report; });
}

init();
