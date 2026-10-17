"use strict";
/* 主旋律提取器 — frontend. Bridges to the Python backend via pywebview's
   js_api; falls back to an in-page demo when opened in a plain browser. */

const $ = (id) => document.getElementById(id);
const HOP_S = 320 / 24000;
const SR = 24000;
const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const BLACK_KEYS = [1, 3, 6, 8, 10];
const PRESETS = [0.5, 0.75, 1, 1.25, 1.5, 2];
const STAGE_TITLES = ["解码与重采样", "人声分离", "旋律提取", "试听合成与导出"];

const fmt2 = (v) => v.toFixed(2);
const freqOf = (m) => 440 * Math.pow(2, (m - 69) / 12);
const midiName = (m) => {
  const i = Math.round(m);
  return NOTE_NAMES[((i % 12) + 12) % 12] + (Math.floor(i / 12) - 1);
};
const fmtTime = (s) => {
  if (!isFinite(s) || s < 0) s = 0;
  const m = Math.floor(s / 60), r = Math.floor(s % 60);
  return m + ":" + String(r).padStart(2, "0");
};
const fmtDur = (s) =>
  s < 60 ? s.toFixed(1) + " 秒" : Math.floor(s / 60) + " 分 " + Math.round(s % 60) + " 秒";

/* ================= state ================= */

const S = {
  demo: false,
  file: null,
  ratio: 1,
  demucs: true,
  gpu: true,
  outMidi: true,
  outTxt: true,
  outDir: "",
  running: false,
  stage: 0,
  stagePct: 0,
  done: false,
  cancelled: false,
  error: null,
  result: null,
  txtPrev: null,
  midiPrev: null,
  playing: "",
  sysinfo: null,
  poll: null,
  previewTimer: null,
};

/* ================= bridge ================= */

let DEMO = null; // demo backend

async function call(method, ...args) {
  if (S.demo) return DEMO[method](...args);
  const r = await window.pywebview.api[method](...args);
  if (r && r.ok === false) throw new Error(r.error || "unknown error");
  return r;
}

/* ================= demo backend (browser preview only) ================= */

function makeDemo() {
  // 小星星 14 音 + 处理流程模拟（与 UI 审核稿一致的演示数据）
  const MEL = [
    [60, 0.5], [60, 0.5], [67, 0.5], [67, 0.5], [69, 0.5], [69, 0.5], [67, 1.0],
    [65, 0.5], [65, 0.5], [64, 0.5], [64, 0.5], [62, 0.5], [62, 0.5], [60, 1.0],
  ];
  const framesOf = (t) => Math.round(t * 75);
  const notes = [];
  let acc = 0;
  for (const [midi, dur] of MEL) {
    notes.push([framesOf(acc), framesOf(acc + dur), midi - 36]);
    acc += dur;
  }
  const frames = 192 * 75; // 3:12
  const t0 = performance.now();
  const T = [1.0, 2.4, 1.3, 0.6]; // stage durations
  const tEnd = T.reduce((a, b) => a + b, 0);

  const peaksMelody = (() => {
    const bars = new Array(220).fill(0);
    for (const [s, e] of notes) {
      const a = Math.floor((s / frames) * 220), b = Math.max(a + 1, Math.ceil((e / frames) * 220));
      for (let i = a; i < b && i < 220; i++) bars[i] = 0.75 + 0.25 * Math.sin(i * 1.7);
    }
    return bars;
  })();
  const peaksOrig = Array.from({ length: 220 }, (_, i) =>
    0.25 + 0.75 * Math.abs(Math.sin(i * 0.37) * Math.sin(i * 0.11 + 1)));
  const txt = (ratio) => {
    const pairs = MEL.map(([m, d]) =>
      "{" + Math.round(freqOf(m) * ratio) + ", " + Math.round(d * 1000) + "}");
    const lines = [];
    for (let i = 0; i < pairs.length; i += 5) lines.push(pairs.slice(i, i + 5).join(", ") + ",");
    return lines;
  };

  return {
    async pick_file() { return this.probe("C:/示例/小星星.flac"); },
    async probe() {
      return { ok: true, path: "C:/示例/小星星.flac", name: "小星星.flac", size_mb: 21.4,
               duration_s: 192, sr: 44100, channels: 2, codec: "flac", media: "" };
    },
    async sysinfo() {
      return { ok: true, providers: ["DmlExecutionProvider", "CPUExecutionProvider"],
               dml: true, onnxruntime: "1.24.4", version: "1.0.0", model_ready: true };
    },
    async start() { DEMO._t0 = performance.now(); DEMO._done = false; return { ok: true }; },
    async progress() {
      const el = (performance.now() - DEMO._t0) / 1000;
      let acc = 0, stage = 4, pct = 1;
      for (let i = 0; i < T.length; i++) {
        if (el < acc + T[i]) { stage = i + 1; pct = (el - acc) / T[i]; break; }
        acc += T[i];
      }
      if (el >= tEnd) DEMO._done = true;
      return { ok: true, state: { running: !DEMO._done, stage: DEMO._done ? 4 : stage,
               stage_pct: DEMO._done ? 1 : pct, done: DEMO._done, cancelled: false, error: null } };
    },
    async cancel() { return { ok: true }; },
    async result() {
      return { ok: true, result: {
        notes, frames, duration_ms: Math.round(frames * HOP_S * 1000), n_notes: notes.length,
        voiced_pct: 3.6, midi_min: 60, midi_max: 69,
        peaks_orig: peaksOrig, peaks_melody: peaksMelody,
        info: { codec: "flac", sr: 44100, channels: 2, duration_s: 192 },
        demucs: S.demucs, ep: S.gpu ? "DmlExecutionProvider" : "CPUExecutionProvider",
        timings: { decode: 0.4, separate: S.demucs ? 118 : 0, infer: 1.2, preview: 0.0 },
        total_s: S.demucs ? 122.6 : 2.9, hop_s: HOP_S } };
    },
    async txt_preview(ratio) {
      const lines = txt(ratio);
      return { ok: true, head: lines, total_lines: lines.length, total_groups: 14,
               last_len: 4, shown: lines.length };
    },
    async midi_preview(ratio) {
      const shift = 12 * Math.log2(ratio);
      const names = MEL.slice(0, 6).map(([m]) => midiName(m + shift));
      const base = freqOf(60), ex = base * ratio, near = Math.round(60 + shift);
      const q = freqOf(near);
      return { ok: true, names, example: { name: "C4", base_hz: fmt2(base),
               ratio_hz: fmt2(ex), nearest: midiName(near), quant_hz: fmt2(q),
               cents: 1200 * Math.log2(ex / q) } };
    },
    async export(ratio, midi, txtFlag, out_dir) {
      const dir = out_dir || "C:/Users/example/Music/MelodyExtractor";
      const r = { ok: true, dir };
      if (midi) r.midi = dir + "/小星星_melody.mid";
      if (txtFlag) r.txt = dir + "/小星星_melody.txt";
      return r;
    },
    async open_folder() { return { ok: true }; },
    async pick_folder() { return { ok: true, dir: "C:/Users/example/Desktop" }; },
    async get_settings() {
      return { ok: true, settings: { ratio: 1, demucs: true, gpu: true, out_midi: true,
               out_txt: true, out_dir: "C:/Users/example/Music/MelodyExtractor", last_dir: "" } };
    },
    async save_settings() { return { ok: true }; },
  };
}

/* ================= melody synth playback ================= */

const MP = {
  ctx: null, buf: null, node: null, playing: false, offset: 0, t0: 0, dur: 0,
  ensureCtx() {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    return this.ctx;
  },
  build() {
    if (!S.result) return false;
    const notes = S.result.notes, frames = S.result.frames;
    const n = Math.max(1, frames) * 320;
    const data = new Float32Array(n);
    const nf = Math.round(0.006 * SR);
    for (const [s0, e0, q] of notes) {
      const f = freqOf(q + 36) * S.ratio;
      const a = Math.round(s0 * HOP_S * SR);
      const b = Math.min(Math.round(e0 * HOP_S * SR), n);
      const len = b - a;
      if (len <= 0) continue;
      const w = (2 * Math.PI * f) / SR;
      for (let i = 0; i < len; i++) {
        let env = 1;
        if (len > 2 * nf) {
          if (i < nf) env = i / (nf - 1);
          else if (i >= len - nf) env = (len - 1 - i) / (nf - 1);
        }
        const ph = w * i;
        data[a + i] = 0.28 * env * (Math.sin(ph) + 0.35 * Math.sin(2 * ph) + 0.12 * Math.sin(3 * ph));
      }
    }
    const ctx = this.ensureCtx();
    this.buf = ctx.createBuffer(1, n, SR);
    this.buf.copyToChannel(data, 0);
    this.dur = n / SR;
    return true;
  },
  play() {
    if (!S.result) return;
    if (!this.buf && !this.build()) return;
    const ctx = this.ensureCtx();
    if (ctx.state === "suspended") ctx.resume();
    const off = Math.min(this.offset, Math.max(0, this.dur - 0.01));
    this.node = ctx.createBufferSource();
    this.node.buffer = this.buf;
    this.node.connect(ctx.destination);
    this.node.onended = () => {
      if (this.playing) { this.playing = false; this.offset = 0; S.playing = ""; renderPlay(); }
    };
    this.node.start(0, off);
    this.t0 = ctx.currentTime;
    this.offset = off;
    this.playing = true;
    S.playing = "mel";
    renderPlay();
  },
  pause() {
    if (!this.node) return;
    this.offset = this.time();
    this.node.onended = null;
    try { this.node.stop(); } catch (e) { /* already stopped */ }
    this.node = null;
    this.playing = false;
    S.playing = "";
    renderPlay();
  },
  time() {
    return this.playing ? Math.min(this.dur, this.offset + (this.ctx.currentTime - this.t0)) : this.offset;
  },
  toggle() { this.playing ? this.pause() : this.play(); },
  invalidate() {
    const wasPlaying = this.playing, off = this.time();
    this.pause();
    this.buf = null;
    if (wasPlaying && S.result) {
      this.offset = off;
      this.play();
    }
  },
};

/* ================= source audio playback ================= */

function srcToggle() {
  const a = $("audioSrc");
  if (a.paused) {
    if (!a.src) { toast("尚未选择音频文件"); return; }
    a.play().then(() => { S.playing = "src"; renderPlay(); })
      .catch((e) => toast("无法播放原曲：" + e.message, true));
  } else {
    a.pause();
    S.playing = "";
    renderPlay();
  }
}

/* ================= rendering ================= */

function renderTitle() {
  const pill = $("pillEp");
  if (S.demo) { pill.textContent = "ONNX Runtime · 演示数据"; pill.className = "mx-pill"; return; }
  if (!S.sysinfo) { pill.textContent = "ONNX Runtime · 检测中…"; pill.className = "mx-pill"; return; }
  const dml = S.sysinfo.dml;
  if (dml && S.gpu) { pill.textContent = "ONNX Runtime · DirectML GPU"; pill.className = "mx-pill mx-pill-info"; }
  else if (dml) { pill.textContent = "ONNX Runtime · CPU（GPU 已关闭）"; pill.className = "mx-pill mx-pill-warn"; }
  else { pill.textContent = "ONNX Runtime · CPU"; pill.className = "mx-pill mx-pill-warn"; }
  if (S.sysinfo.version) $("tbVer").textContent = "v" + S.sysinfo.version;
}

function renderFile() {
  const has = !!S.file;
  $("fileEmpty").hidden = has;
  $("fileInfo").hidden = !has;
  if (has) {
    $("fileName").textContent = S.file.name;
    $("fileMeta").textContent = fmtTime(S.file.duration_s) + " · " + (S.file.sr / 1000).toFixed(1) +
      " kHz " + (S.file.channels === 1 ? "单声道" : "立体声") + " · " + S.file.size_mb + " MB";
    $("fileMeta").title = S.file.path;
  }
  const a = $("audioSrc");
  if (has && S.file.media) {
    a.src = S.file.media;
  } else {
    a.removeAttribute("src");
  }
  $("btnRun").disabled = !has && !S.running;
}

function renderOptions() {
  $("swDemucs").checked = S.demucs;
  $("swGpu").checked = S.gpu;
  $("ckMidi").checked = S.outMidi;
  $("ckTxt").checked = S.outTxt;
  $("outDir").value = S.outDir;
}

function renderRatio() {
  const shift = 12 * Math.log2(S.ratio);
  $("ratioLabel").textContent = "×" + fmt2(S.ratio);
  $("shiftLabel").textContent =
    (shift >= 0 ? "+" : "") + shift.toFixed(2) + " 半音 / " +
    (shift >= 0 ? "+" : "") + Math.round(shift * 100) + " 音分";
  $("ratioSlider").value = String(Math.min(2, Math.max(-2, Math.log2(S.ratio))));
  if (document.activeElement !== $("ratioInput")) $("ratioInput").value = fmt2(S.ratio);
  $("a4Label").textContent = "示例：A4 440.00 Hz → " + fmt2(440 * S.ratio) +
    " Hz。TXT 按整数 Hz 写出；MIDI 取整到最近半音；试听用精确频率。";
  $("txtRatioLbl").textContent = "×" + fmt2(S.ratio);
  renderPresets();
}

function renderPresets() {
  const box = $("presets");
  box.innerHTML = "";
  for (const p of PRESETS) {
    const b = document.createElement("button");
    b.className = "mx-tag" + (Math.abs(S.ratio - p) < 0.005 ? " active" : "");
    b.textContent = "×" + p;
    b.onclick = () => setRatio(p, true);
    box.appendChild(b);
  }
}

function stageDefs() {
  return [
    { d: "任意输入格式 → 24 kHz / 单声道" },
    { d: S.demucs ? "demucs（CPU，约 1.5× 实时）" : "已跳过 —— 直接从混音提取" },
    { d: S.gpu ? "MERT + BiGRU 模型 · DirectML GPU" : "MERT + BiGRU 模型 · CPU 回退" },
    { d: "应用倍率 ×" + fmt2(S.ratio) + " 写出 MIDI / TXT" },
  ];
}

function renderStages() {
  const box = $("stages");
  box.innerHTML = "";
  const defs = stageDefs();
  defs.forEach((def, i) => {
    const idx = i + 1;
    let st = "pending";
    if (S.error && S.stage === idx) st = "error";
    else if (S.done) st = "done";
    else if (S.running && S.stage === idx) st = "active";
    else if (S.stage > idx) st = "done";
    const row = document.createElement("div");
    row.className = "mx-stage";
    const dot = document.createElement("div");
    dot.className = "mx-dot-s " + st + (st === "active" ? " mx-pulse" : "");
    const body = document.createElement("div");
    body.className = "mx-stage-body";
    const title = document.createElement("div");
    title.className = "mx-stage-title";
    title.textContent = STAGE_TITLES[i];
    const desc = document.createElement("span");
    desc.className = "mx-stage-desc";
    desc.textContent = def.d;
    body.appendChild(title);
    body.appendChild(desc);
    const stTxt = document.createElement("span");
    stTxt.className = "mx-stage-st";
    if (st === "done") { stTxt.textContent = "已完成"; stTxt.style.color = "var(--ok)"; }
    else if (st === "active") {
      stTxt.textContent = "进行中… " + Math.round(S.stagePct * 100) + "%";
      stTxt.style.color = "var(--accent)";
    } else if (st === "error") { stTxt.textContent = "失败"; stTxt.style.color = "#d64545"; }
    else { stTxt.textContent = "等待"; stTxt.style.color = "var(--text-4)"; }
    row.appendChild(dot); row.appendChild(body); row.appendChild(stTxt);
    box.appendChild(row);
  });
  let pct = 0;
  if (S.done) pct = 100;
  else if (S.running) pct = ((S.stage - 1 + S.stagePct) / 4) * 100;
  else if (S.stage > 0 && S.error) pct = ((S.stage - 1) / 4) * 100;
  $("pbar").style.width = pct.toFixed(1) + "%";
}

function renderRun() {
  const btn = $("btnRun");
  if (S.running) {
    btn.textContent = "取消处理";
    btn.disabled = false;
    btn.className = "mx-btn mx-btn-secondary";
  } else {
    btn.textContent = S.done ? "重新处理" : "开始处理";
    btn.disabled = !S.file;
    btn.className = "mx-btn mx-btn-primary";
  }
  const hint = $("runHint");
  if (S.running) { hint.textContent = "处理中…点击按钮可取消"; hint.className = "mx-sm mx-quat"; }
  else if (S.error) { hint.textContent = S.error; hint.className = "mx-sm mx-err"; }
  else if (S.cancelled) { hint.textContent = "已取消"; hint.className = "mx-sm mx-quat"; }
  else if (S.done) { hint.textContent = "处理完成"; hint.className = "mx-sm mx-quat"; }
  else { hint.textContent = S.file ? "准备就绪" : "选择音频后开始处理"; hint.className = "mx-sm mx-quat"; }
}

function renderWaves() {
  const src = $("waveSrc"), mel = $("waveMel");
  fillWave(src, S.result ? S.result.peaks_orig : null, S.playing === "src");
  fillWave(mel, S.result ? S.result.peaks_melody : null, S.playing === "mel");
}

function fillWave(box, peaks, playing) {
  box.innerHTML = "";
  const n = 220;
  for (let i = 0; i < n; i++) {
    const bar = document.createElement("span");
    const v = peaks ? peaks[i] : 0.06 + 0.05 * Math.abs(Math.sin(i * 0.6));
    bar.style.height = Math.max(2, Math.round(2 + v * 24)) + "px";
    if (playing) bar.className = "on";
    box.appendChild(bar);
  }
}

function renderPlay() {
  $("btnPlaySrc").textContent = S.playing === "src" ? "暂停" : "播放";
  $("btnPlayMel").textContent = S.playing === "mel" ? "暂停" : "播放";
  $("btnPlaySrc").disabled = !S.file || S.demo;
  $("btnPlayMel").disabled = !S.result;
  renderWaves();
  const a = $("audioSrc");
  $("lblSrc").textContent = "原曲 · " +
    (S.file ? fmtTime(a.currentTime || 0) + " / " + fmtTime(S.file.duration_s) : "--:--");
  $("lblMel").textContent = "旋律试听 · " +
    (S.result ? fmtTime(MP.playing || MP.offset ? MP.time() : 0) + " / " + fmtTime(S.result.duration_ms / 1000) : "--:--");
}

function renderRoll() {
  const box = $("roll");
  box.innerHTML = "";
  if (!S.result || !S.result.notes.length) {
    const e = document.createElement("div");
    e.className = "mx-roll-empty";
    e.textContent = S.result ? "未检测到音符" : "处理完成后显示提取的音符";
    box.appendChild(e);
    return;
  }
  const shift = 12 * Math.log2(S.ratio);
  const midis = S.result.notes.map((n) => n[2] + 36);
  const minM = Math.min(...midis) + shift, maxM = Math.max(...midis) + shift;
  const floorM = Math.min(48, Math.floor(minM) - 1);
  const ceilM = Math.max(84, Math.ceil(maxM) + 1);
  const span = ceilM - floorM;
  const pxPer = Math.max(3, Math.min(12, Math.floor(210 / span)));
  box.style.height = Math.max(120, span * pxPer) + "px";
  const rowY = (m) => (ceilM - 1 - m) * pxPer;
  for (let m = floorM; m < ceilM; m++) {
    const r = document.createElement("div");
    r.className = "mx-roll-row";
    r.style.top = rowY(m) + "px";
    r.style.height = pxPer + "px";
    if (BLACK_KEYS.includes(((m % 12) + 12) % 12)) r.style.background = "var(--fill-3)";
    box.appendChild(r);
  }
  for (let m = Math.ceil(floorM / 12) * 12; m < ceilM; m += 12) {
    const line = document.createElement("div");
    line.className = "mx-roll-cline";
    line.style.top = rowY(m) + "px";
    box.appendChild(line);
    const lab = document.createElement("div");
    lab.className = "mx-roll-clabel";
    lab.style.top = rowY(m) + 1 + "px";
    lab.textContent = midiName(m);
    box.appendChild(lab);
  }
  const inner = document.createElement("div");
  inner.className = "mx-roll-inner";
  const frames = S.result.frames || 1;
  for (const [s, e, q] of S.result.notes) {
    const eff = q + 36 + shift;
    const d = document.createElement("div");
    d.className = "mx-note";
    d.style.left = (s / frames) * 100 + "%";
    d.style.width = "max(2px, " + ((e - s) / frames) * 100 + "%)";
    d.style.top = rowY(Math.floor(eff)) + 1 + "px";
    d.style.height = Math.max(2, pxPer - 2) + "px";
    d.title = midiName(eff) + " · " + fmt2(freqOf(eff) * S.ratio) + " Hz · " +
      fmt2((e - s) * HOP_S) + " s";
    inner.appendChild(d);
  }
  box.appendChild(inner);
  $("rollCap").textContent = "横轴 = 时间，纵向随倍率整体平移；悬停单音可见音名 / 频率 / 时长。当前音域 " +
    midiName(minM) + " – " + midiName(maxM);
}

function renderResults() {
  const r = S.result;
  $("resNote").textContent = S.file ? S.file.name : "";
  if (!r) {
    $("stNotes").textContent = "—";
    $("stNotesDesc").textContent = "";
    $("stRangeLbl").textContent = "音域";
    $("stRange").textContent = "—";
    $("stRangeDesc").textContent = "";
    $("stTime").textContent = "—";
    $("stTimeDesc").textContent = "";
    $("midiBox").hidden = !S.outMidi;
    $("txtBox").hidden = !S.outTxt;
    $("midiNames").textContent = "处理完成后显示";
    $("midiExample").textContent = "";
    $("txtPrev").textContent = "处理完成后显示预览";
    $("txtMeta").textContent = "";
  } else {
    const shift = 12 * Math.log2(S.ratio);
    $("stNotes").textContent = r.n_notes + " 个";
    $("stNotesDesc").textContent = "有声帧占比 " + fmt2(r.voiced_pct) + "%";
    $("stRangeLbl").textContent = "音域（×" + fmt2(S.ratio) + "）";
    if (r.n_notes) {
      $("stRange").textContent = midiName(r.midi_min + shift) + " – " + midiName(r.midi_max + shift);
      $("stRangeDesc").textContent = fmt2(freqOf(r.midi_min + shift)) + " – " + fmt2(freqOf(r.midi_max + shift)) + " Hz";
    } else {
      $("stRange").textContent = "—";
      $("stRangeDesc").textContent = "";
    }
    const t = r.timings || {};
    $("stTime").textContent = "≈ " + fmtDur(r.total_s);
    $("stTimeDesc").textContent = "推理 " + (t.infer || 0).toFixed(1) + " s · " +
      (r.demucs ? "分离 " + fmtDur(t.separate || 0) : "已跳过分离") +
      (r.ep && r.ep.includes("Dml") ? " · DirectML" : " · CPU");
    if (S.txtPrev) {
      $("txtPrev").textContent = S.txtPrev.head.join("\n");
      const m = S.txtPrev;
      $("txtMeta").textContent = "共 " + m.total_groups + " 组 · " + m.total_lines + " 行（每行 5 组，末行 " +
        m.last_len + " 组）；整数 Hz / 毫秒 / 行尾逗号" +
        (m.shown < m.total_lines ? "（仅显示前 " + m.shown + " 行）" : "");
    } else {
      $("txtPrev").textContent = "（生成预览中…）";
    }
    if (S.midiPrev) {
      $("midiNames").textContent = S.midiPrev.names.length
        ? S.midiPrev.names.join(" · ") + " …" : "（无音符）";
      const ex = S.midiPrev.example;
      $("midiExample").textContent = ex
        ? "示例取整：" + ex.name + " " + ex.base_hz + " Hz → ×" + fmt2(S.ratio) + " = " + ex.ratio_hz +
          " Hz → MIDI " + ex.nearest + "（" + ex.quant_hz + " Hz，偏差 " + (ex.cents >= 0 ? "+" : "") + ex.cents.toFixed(1) + " 音分）"
        : "";
    }
    $("midiBox").hidden = !S.outMidi;
    $("txtBox").hidden = !S.outTxt;
  }
  const ready = S.done && !!r;
  $("btnExpMidi").disabled = !(ready && S.outMidi);
  $("btnExpTxt").disabled = !(ready && S.outTxt);
  $("btnOpenOut").disabled = !ready;
  $("btnOpenOut2").disabled = !ready;
  $("expHint").textContent = ready ? "已应用倍率 ×" + fmt2(S.ratio) : "处理完成后可用";
  $("expHint").className = "mx-sm mx-quat";
}

function renderAll() {
  renderTitle(); renderFile(); renderOptions(); renderRatio();
  renderStages(); renderRun(); renderPlay(); renderRoll(); renderResults();
}

/* ================= actions ================= */

function setRatio(v, snapText) {
  if (!isFinite(v) || v < 0.1 || v > 10) return;
  S.ratio = v;
  renderRatio();
  MP.invalidate();
  if (S.result) {
    renderRoll();
    renderResults();
    clearTimeout(S.previewTimer);
    S.previewTimer = setTimeout(refreshPreviews, 180);
  }
  saveSettingsDebounced();
}

function refreshPreviews() {
  call("txt_preview", S.ratio).then((r) => { S.txtPrev = r; renderResults(); }).catch(() => {});
  call("midi_preview", S.ratio).then((r) => { S.midiPrev = r; renderResults(); }).catch(() => {});
}

function toast(msg, isErr) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "mx-toast" + (isErr ? " err" : "");
  t.hidden = false;
  clearTimeout(t._h);
  t._h = setTimeout(() => { t.hidden = true; }, isErr ? 5200 : 3200);
}

async function pickFile() {
  try {
    const r = await call("pick_file");
    if (r.cancelled) return;
    S.file = r;
    S.result = null; S.done = false; S.cancelled = false; S.error = null;
    S.txtPrev = null; S.midiPrev = null; S.stage = 0; S.stagePct = 0;
    MP.invalidate();
    renderAll();
  } catch (e) {
    toast("选择文件失败：" + e.message, true);
  }
}

function clearFile() {
  S.file = null; S.result = null; S.done = false; S.error = null; S.cancelled = false;
  S.stage = 0; S.stagePct = 0; S.txtPrev = null; S.midiPrev = null;
  MP.invalidate();
  renderAll();
}

async function startProcess() {
  if (S.running) { await cancelProcess(); return; }
  if (!S.file) return;
  S.running = true; S.done = false; S.error = null; S.cancelled = false;
  S.stage = 1; S.stagePct = 0; S.result = null; S.txtPrev = null; S.midiPrev = null;
  MP.invalidate();
  renderAll();
  try {
    await call("start", S.file.path, S.demucs, S.gpu);
  } catch (e) {
    S.running = false; S.error = e.message;
    renderAll();
    toast("无法开始处理：" + e.message, true);
    return;
  }
  stopPoll();
  S.poll = setInterval(pollProgress, 350);
}

async function cancelProcess() {
  try { await call("cancel"); } catch (e) { /* ignore */ }
}

function stopPoll() {
  if (S.poll) { clearInterval(S.poll); S.poll = null; }
}

async function pollProgress() {
  let r;
  try { r = await call("progress"); } catch (e) { return; }
  const st = r.state;
  S.running = !!st.running;
  S.stage = st.stage || 1;
  S.stagePct = st.stage_pct || 0;
  if (st.done) {
    stopPoll();
    S.done = true; S.running = false;
    try {
      const res = await call("result");
      S.result = res.result;
      refreshPreviews();
    } catch (e) {
      S.error = e.message;
    }
    renderAll();
    $("fileInfo").scrollIntoView?.({ behavior: "smooth", block: "nearest" });
    return;
  }
  if (st.error) {
    stopPoll();
    S.running = false; S.error = st.error;
    renderAll();
    toast("处理失败：" + st.error, true);
    return;
  }
  if (st.cancelled) {
    stopPoll();
    S.running = false; S.cancelled = true;
    renderAll();
    return;
  }
  renderStages(); renderRun();
}

async function exportFiles(wantMidi, wantTxt) {
  try {
    const r = await call("export", S.ratio, wantMidi, wantTxt, S.outDir);
    const parts = [];
    if (r.midi) parts.push("MIDI → " + r.midi);
    if (r.txt) parts.push("TXT → " + r.txt);
    toast("导出完成：\n" + parts.join("\n"));
  } catch (e) {
    toast("导出失败：" + e.message, true);
  }
}

let saveTimer = null;
function saveSettingsDebounced() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    if (S.demo) return;
    call("save_settings", {
      ratio: S.ratio, demucs: S.demucs, gpu: S.gpu,
      out_midi: S.outMidi, out_txt: S.outTxt, out_dir: S.outDir,
    }).catch(() => {});
  }, 400);
}

/* ================= wiring ================= */

function bindEvents() {
  $("btnPick").onclick = pickFile;
  $("btnChange").onclick = pickFile;
  $("btnClear").onclick = clearFile;
  $("btnRun").onclick = startProcess;
  $("btnOpenOut").onclick = () => call("open_folder", S.outDir).catch(() => {});
  $("btnOpenOut2").onclick = () => call("open_folder", S.outDir).catch(() => {});
  $("btnBrowse").onclick = async () => {
    try {
      const r = await call("pick_folder");
      if (r.cancelled) return;
      S.outDir = r.dir;
      $("outDir").value = r.dir;
      saveSettingsDebounced();
    } catch (e) { toast("选择目录失败：" + e.message, true); }
  };
  $("outDir").onchange = () => { S.outDir = $("outDir").value.trim(); saveSettingsDebounced(); };

  $("swDemucs").onchange = () => { S.demucs = $("swDemucs").checked; renderStages(); saveSettingsDebounced(); };
  $("swGpu").onchange = () => { S.gpu = $("swGpu").checked; renderTitle(); renderStages(); saveSettingsDebounced(); };
  $("ckMidi").onchange = () => { S.outMidi = $("ckMidi").checked; renderResults(); saveSettingsDebounced(); };
  $("ckTxt").onchange = () => { S.outTxt = $("ckTxt").checked; renderResults(); saveSettingsDebounced(); };

  $("ratioSlider").oninput = (e) => { setRatio(Math.pow(2, parseFloat(e.target.value))); };
  $("ratioInput").onchange = () => {
    const v = parseFloat($("ratioInput").value);
    if (isFinite(v) && v >= 0.1 && v <= 10) setRatio(v);
    else { $("ratioInput").value = fmt2(S.ratio); }
  };

  $("btnPlaySrc").onclick = srcToggle;
  $("btnPlayMel").onclick = () => MP.toggle();
  $("btnExpMidi").onclick = () => exportFiles(true, false);
  $("btnExpTxt").onclick = () => exportFiles(false, true);

  const a = $("audioSrc");
  a.addEventListener("timeupdate", () => {
    $("lblSrc").textContent = "原曲 · " + fmtTime(a.currentTime) + " / " + fmtTime(S.file ? S.file.duration_s : 0);
  });
  a.addEventListener("ended", () => { S.playing = ""; renderPlay(); });
  a.addEventListener("play", () => { S.playing = "src"; renderPlay(); });
  a.addEventListener("pause", () => { if (S.playing === "src") { S.playing = ""; renderPlay(); } });

  setInterval(() => { if (S.playing === "mel") renderPlay(); }, 250);
}

async function loadSettings() {
  try {
    const r = await call("get_settings");
    const s = r.settings || {};
    if (typeof s.ratio === "number") S.ratio = s.ratio;
    if (typeof s.demucs === "boolean") S.demucs = s.demucs;
    if (typeof s.gpu === "boolean") S.gpu = s.gpu;
    if (typeof s.out_midi === "boolean") S.outMidi = s.out_midi;
    if (typeof s.out_txt === "boolean") S.outTxt = s.out_txt;
    if (s.out_dir) S.outDir = s.out_dir;
  } catch (e) { /* defaults */ }
}

async function bootBridge(isDemo) {
  S.demo = isDemo;
  DEMO = makeDemo();
  if (isDemo) {
    $("pillDemo").hidden = false;
    $("pillEp").textContent = "ONNX Runtime · 演示数据";
    $("pillEp").className = "mx-pill";
    const r = await DEMO.probe();
    S.file = r; S.outDir = "C:/Users/example/Music/MelodyExtractor";
    renderAll();
    setTimeout(startProcess, 500);
    return;
  }
  try { S.sysinfo = await call("sysinfo"); } catch (e) { /* keep unknown */ }
  try { await loadSettings(); } catch (e) { /* defaults */ }
  if (!S.outDir) S.outDir = "";
  renderAll();
  call("save_settings", {
    ratio: S.ratio, demucs: S.demucs, gpu: S.gpu,
    out_midi: S.outMidi, out_txt: S.outTxt, out_dir: S.outDir,
  }).catch(() => {});
}

let booted = false;
function bootBridgeOnce(isDemo) {
  if (booted) return;
  booted = true;
  bootBridge(isDemo);
}

function boot() {
  bindEvents();
  renderAll();
  let tries = 0;
  const timer = setInterval(() => {
    if (window.pywebview && window.pywebview.api) {
      clearInterval(timer);
      bootBridgeOnce(false);
    } else if (++tries > 12) {
      clearInterval(timer);
      bootBridgeOnce(true);
    }
  }, 250);
  window.addEventListener("pywebviewready", () => {
    clearInterval(timer);
    bootBridgeOnce(false);
  });
}

document.addEventListener("DOMContentLoaded", boot);
