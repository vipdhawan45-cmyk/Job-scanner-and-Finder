"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  profileId: null,
  profile: null,
  skills: [],
  jobs: [],
  sources: [],
  showSaved: false,
  saved: loadSaved(),
};

/* ---------- storage (best-effort) ---------- */
function loadSaved() {
  try { return JSON.parse(localStorage.getItem("jobmatch.saved") || "{}"); } catch { return {}; }
}
function persistSaved() {
  try { localStorage.setItem("jobmatch.saved", JSON.stringify(state.saved)); } catch { /* private mode */ }
  $("#savedCount").textContent = Object.keys(state.saved).length;
}

/* ---------- helpers ---------- */
const FRIENDLY_STATUS = {
  413: "That file is too large. Please upload a file under 8 MB.",
  429: "Too many requests — please wait a minute and try again.",
  500: "Something went wrong on the server. Please try again.",
  502: "The server restarted while handling your request (it may have been waking up). Wait 30 seconds and try again.",
  503: "The server is starting up. Wait 30 seconds and try again.",
  504: "The server took too long to respond. Please try again.",
};

async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(path, options);
  } catch {
    throw new Error("Couldn't reach the server. Check your internet connection and try again.");
  }
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON (e.g. a proxy error page) */ }
  if (!res.ok) {
    const detail = body && body.detail;
    if (typeof detail === "string") throw new Error(detail);
    throw new Error(FRIENDLY_STATUS[res.status] || `Request failed (${res.status}). Please try again.`);
  }
  return body;
}
function showError(el, msg) { el.textContent = msg; el.hidden = !msg; }
function timeAgo(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return months < 12 ? `${months} mo ago` : `${Math.floor(months / 12)} yr ago`;
}
function safeUrl(u) {
  try { const url = new URL(u); return ["http:", "https:"].includes(url.protocol) ? url.href : "#"; } catch { return "#"; }
}
function setBusy(btn, busy, label) {
  btn.disabled = busy;
  if (busy) { btn.dataset.label = btn.textContent; btn.innerHTML = `<span class="spinner"></span> ${label}`; }
  else if (btn.dataset.label) btn.textContent = btn.dataset.label;
}

/* ---------- upload view ---------- */
let selectedFile = null;
let activeTab = "file";

$$(".tab").forEach((tab) => tab.addEventListener("click", () => {
  activeTab = tab.dataset.tab;
  $$(".tab").forEach((t) => { t.classList.toggle("active", t === tab); t.setAttribute("aria-selected", t === tab); });
  $$(".tab-panel").forEach((p) => { p.hidden = p.dataset.panel !== activeTab; });
  updateAnalyzeBtn();
}));

function updateAnalyzeBtn() {
  $("#analyzeBtn").disabled = activeTab === "file" ? !selectedFile : $("#resumeText").value.trim().length < 50;
}
$("#resumeText").addEventListener("input", updateAnalyzeBtn);

function pickFile(file) {
  if (!file) return;
  if (file.size > 8 * 1024 * 1024) { showError($("#uploadError"), "That file is larger than 8 MB."); return; }
  selectedFile = file;
  $("#dropzone").classList.add("has-file");
  $("#dzTitle").textContent = file.name;
  $("#dzHint").textContent = `${(file.size / 1024).toFixed(0)} KB · click to choose another file`;
  showError($("#uploadError"), "");
  updateAnalyzeBtn();
}
$("#fileInput").addEventListener("change", (e) => pickFile(e.target.files[0]));
const dz = $("#dropzone");
["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
dz.addEventListener("drop", (e) => pickFile(e.dataTransfer.files[0]));

$("#uploadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#analyzeBtn");
  showError($("#uploadError"), "");
  const fd = new FormData();
  if (activeTab === "file" && selectedFile) fd.append("file", selectedFile);
  else fd.append("text", $("#resumeText").value);
  setBusy(btn, true, "Reading your resume…");
  try {
    const data = await api("/api/resume", { method: "POST", body: fd });
    state.profileId = data.profile_id;
    state.profile = data.profile;
    state.skills = [...data.profile.skills];
    renderProfile(data);
    $("#uploadView").hidden = true;
    $("#resultsView").hidden = false;
    $("#restartBtn").hidden = false;
    $("#savedToggle").hidden = false;
    window.scrollTo({ top: 0 });
    await runSearch();
  } catch (err) {
    showError($("#uploadError"), err.message);
  } finally {
    setBusy(btn, false);
  }
});

/* ---------- profile ---------- */
function renderProfile(data) {
  const p = data.profile;
  $("#yearsInput").value = p.years_experience;
  $("#seniority").textContent = p.seniority;
  $("#titlesWrap").hidden = !p.titles.length;
  $("#titles").replaceChildren(...p.titles.map((t) => chip(t, "title")));
  $("#keywordsInput").placeholder = data.suggested_queries.join(" · ");
  $("#queryHint").textContent = "Leave blank to search using your detected roles and skills.";
  if (p.location && !$("#locationInput").value) $("#locationInput").value = p.location;
  $("#profileWarnings").replaceChildren(...(p.warnings || []).map((w) => {
    const d = document.createElement("div"); d.className = "alert warn"; d.textContent = w; return d;
  }));
  if (!data.suggested_queries.length) $("#keywordsInput").placeholder = "e.g. Site Engineer";
  renderSkills();
}

function chip(text, cls = "", onRemove) {
  const el = document.createElement("span");
  el.className = `chip ${cls}`.trim();
  el.textContent = text;
  if (onRemove) {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("aria-label", `Remove ${text}`);
    b.textContent = "×";
    b.addEventListener("click", onRemove);
    el.append(b);
  }
  return el;
}

function renderSkills() {
  const wrap = $("#skills");
  if (!state.skills.length) { wrap.innerHTML = '<span class="muted small">No skills yet — add a few below.</span>'; return; }
  wrap.replaceChildren(...state.skills.map((s) => chip(s, "", () => {
    state.skills = state.skills.filter((x) => x !== s);
    renderSkills();
  })));
}

$("#addSkillForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = $("#addSkillInput");
  const v = input.value.trim();
  if (v && !state.skills.some((s) => s.toLowerCase() === v.toLowerCase())) {
    state.skills.unshift(v);
    renderSkills();
  }
  input.value = "";
});

/* ---------- sources ---------- */
async function loadSources() {
  try {
    const data = await api("/api/sources");
    state.sources = data.sources;
    $("#sourcesList").replaceChildren(...data.sources.map((s) => {
      const label = document.createElement("label");
      label.className = `source-opt${s.enabled ? "" : " disabled"}`;
      label.title = s.disabled_reason || s.description;
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = s.name;
      cb.disabled = !s.enabled || data.demo_mode;
      cb.checked = data.demo_mode ? s.name === "sample" : s.enabled && s.name !== "sample";
      const text = document.createElement("span");
      text.textContent = s.label;
      const small = document.createElement("small");
      small.textContent = s.enabled ? s.description : s.disabled_reason;
      text.append(small);
      label.append(cb, text);
      return label;
    }));
    $("#coverageNotice").hidden = !data.limited_coverage;
    if (data.demo_mode) {
      const n = $("#demoNotice");
      n.textContent = "Demo mode: showing bundled sample listings from fictional companies. Configure live sources to search real jobs.";
      n.hidden = false;
    }
  } catch { /* sources list is optional */ }
}

/* ---------- search ---------- */
$("#searchForm").addEventListener("submit", (e) => { e.preventDefault(); runSearch(); });

async function runSearch() {
  const btn = $("#searchBtn");
  showError($("#searchError"), "");
  state.showSaved = false;
  const checked = $$("#sourcesList input:checked").map((c) => c.value);
  const years = parseFloat($("#yearsInput").value);
  const body = {
    profile_id: state.profileId,
    skills: state.skills,
    years_experience: isNaN(years) ? null : years,
    keywords: $("#keywordsInput").value.trim(),
    location: $("#locationInput").value.trim(),
    remote_only: $("#remoteInput").checked,
    sources: checked.length ? checked : null,
    limit: 60,
  };
  setBusy(btn, true, "Searching job boards…");
  $("#jobList").innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
  $("#resultsMeta").textContent = "Searching LinkedIn and job boards, then ranking against your profile…";
  try {
    const data = await api("/api/jobs/search", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    state.jobs = data.jobs;
    const weak = data.hidden_weak ? ` · ${data.hidden_weak} weak matches hidden` : "";
    $("#resultsMeta").textContent =
      `${data.jobs.length} good matches from ${data.total_found} jobs${weak} · searched “${data.queries.join("”, “")}” · ${(data.elapsed_ms / 1000).toFixed(1)}s`;
    renderSourceStatus(data.source_status);
    renderJobs();
  } catch (err) {
    $("#jobList").innerHTML = "";
    $("#resultsMeta").textContent = "";
    showError($("#searchError"), err.message);
    if (/expired/i.test(err.message)) setTimeout(() => location.reload(), 2500);
  } finally {
    setBusy(btn, false);
  }
}

function renderSourceStatus(status) {
  const chips = Object.entries(status).map(([, s]) => {
    const failed = s.errors.length && !s.count;
    const el = chip(`${s.label}: ${failed ? "unavailable" : s.count}${s.fallback ? " (fallback)" : ""}`, failed ? "err" : "");
    if (s.errors.length) el.title = s.errors[0];
    return el;
  });
  $("#sourceStatus").replaceChildren(...chips);
  const fellBack = Object.values(status).some((s) => s.fallback);
  const n = $("#demoNotice");
  if (fellBack) {
    n.textContent = "Live sources returned no results (or were unreachable), so these are sample listings from fictional companies.";
    n.hidden = false;
  }
}

/* ---------- results ---------- */
$("#filterInput").addEventListener("input", renderJobs);
$("#sortSelect").addEventListener("change", renderJobs);
$("#savedToggle").addEventListener("click", () => { state.showSaved = !state.showSaved; renderJobs(); });
$("#restartBtn").addEventListener("click", () => location.reload());

function renderJobs() {
  const list = $("#jobList");
  let jobs = state.showSaved ? Object.values(state.saved) : state.jobs.slice();
  $("#resultsTitle").textContent = state.showSaved ? "Saved jobs" : "Matching jobs";
  $("#savedToggle").classList.toggle("active", state.showSaved);
  const q = $("#filterInput").value.trim().toLowerCase();
  if (q) jobs = jobs.filter((j) => `${j.title} ${j.company} ${j.location} ${j.source}`.toLowerCase().includes(q));
  if ($("#sortSelect").value === "date") jobs.sort((a, b) => (Date.parse(b.posted_at) || 0) - (Date.parse(a.posted_at) || 0));
  else jobs.sort((a, b) => b.score - a.score);

  if (!jobs.length) {
    list.innerHTML = `<div class="card empty">${state.showSaved ? "No saved jobs yet — tap ☆ on a job to save it."
      : "No good matches found. Try clearing the location, turning off “Remote only”, or typing a different job title in Keywords."}</div>`;
    return;
  }
  list.replaceChildren(...jobs.map(jobCard));
}

function scoreColor(score) {
  return score >= 70 ? "var(--good)" : score >= 50 ? "var(--ring-mid)" : "var(--bad)";
}

function jobCard(job) {
  const node = $("#jobTpl").content.firstElementChild.cloneNode(true);
  const pct = Math.max(0, Math.min(100, Math.round(job.score)));
  const fg = $(".fg", node);
  fg.style.stroke = scoreColor(pct);
  fg.setAttribute("stroke-dasharray", `${pct} 100`);
  $(".score", node).setAttribute("aria-label", `Match score ${pct} out of 100`);
  $(".score-num", node).textContent = pct;
  $(".job-title", node).textContent = job.title;
  $(".job-company", node).textContent = job.company;

  const meta = $(".meta", node);
  const add = (text, cls) => { if (!text) return; const s = document.createElement("span"); if (cls) s.className = cls; s.textContent = text; meta.append(s); };
  add(job.source, `badge${job.source === "Sample" ? " sample" : ""}`);
  if (job.remote) add("Remote", "badge remote");
  add(job.location ? `📍 ${job.location}` : "");
  add(job.salary ? `💰 ${job.salary}` : "");
  add(job.job_type || "");
  add(job.posted_at ? `🕒 ${timeAgo(job.posted_at)}` : "");

  $(".reasons", node).replaceChildren(...(job.reasons || []).slice(0, 3).map((r) => {
    const li = document.createElement("li"); li.textContent = r; return li;
  }));

  const rows = $(".skill-rows", node);
  const row = (label, skills, cls) => {
    if (!skills || !skills.length) return;
    const r = document.createElement("div"); r.className = "skill-row";
    const l = document.createElement("span"); l.textContent = label;
    const c = document.createElement("div"); c.className = "chips";
    c.replaceChildren(...skills.map((s) => chip(s, cls)));
    r.append(l, c); rows.append(r);
  };
  row("You have", job.matched_skills, "good");
  row("Missing", job.missing_skills, "warn");

  const names = { skills: "Skills", semantic: "Content fit", title: "Title fit", experience: "Experience" };
  $(".breakdown", node).replaceChildren(...Object.entries(job.breakdown || {}).map(([k, v]) => {
    const b = document.createElement("div"); b.className = "bar";
    b.innerHTML = `<div><span></span> <strong></strong></div><div class="track"><div class="fill"></div></div>`;
    b.querySelector("span").textContent = names[k] || k;
    b.querySelector("strong").textContent = `${v}%`;
    b.querySelector(".fill").style.width = `${v}%`;
    return b;
  }));
  const desc = job.description || "";
  $(".desc-text", node).textContent = desc.length > 2500 ? `${desc.slice(0, 2500)}…` : desc || "No description provided by this source.";

  const apply = $(".apply", node);
  apply.href = safeUrl(job.url);
  if (job.source === "Sample") { apply.textContent = "Sample listing"; apply.removeAttribute("href"); apply.classList.remove("primary"); }

  const saveBtn = $(".save", node);
  const sync = () => { const on = !!state.saved[job.id]; saveBtn.textContent = on ? "★" : "☆"; saveBtn.classList.toggle("on", on); saveBtn.setAttribute("aria-pressed", on); };
  saveBtn.addEventListener("click", () => {
    if (state.saved[job.id]) delete state.saved[job.id]; else state.saved[job.id] = job;
    persistSaved(); sync();
    if (state.showSaved) renderJobs();
  });
  sync();
  return node;
}

/* ---------- init ---------- */
persistSaved();
loadSources();
