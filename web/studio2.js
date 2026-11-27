/* KrlzCut 2.0 — 5-Section Pro Studio UI (Dashboard, New Project, Projects Library, Queue, Full Settings) */
(function () {
  "use strict";

  const THEMES = [
    { key: "obsidian", name: "KrlzCut Obsidian", sub: "Монохромная студия", a: "#FAFAFA", b: "#0EA5E9", bg: "#111113" },
    { key: "amber", name: "Cinema Amber", sub: "Тёплый грейдинг", a: "#F59E0B", b: "#EA580C", bg: "#141210" },
    { key: "emerald", name: "Studio Emerald", sub: "Контрольный монитор", a: "#10B981", b: "#06B6D4", bg: "#0E1412" },
    { key: "cobalt", name: "Engineering Cobalt", sub: "Технический синий", a: "#3B82F6", b: "#0EA5E9", bg: "#0E1218" },
    { key: "crimson", name: "Director Red", sub: "Индикатор записи", a: "#EF4444", b: "#F97316", bg: "#161010" },
    { key: "custom", name: "Своя палитра", sub: "Любые два цвета", a: "#0EA5E9", b: "#F59E0B", bg: "#111113" },
  ];

  const PALETTE_SWATCHES = [
    ["#0ea5e9", "#f59e0b", "Студия"],
    ["#0ea5e9", "#22d3ee", "Арктика"],
    ["#ef4444", "#f97316", "Закат"],
    ["#10b981", "#84cc16", "Изумруд"],
    ["#3b82f6", "#06b6d4", "Кобальт"],
  ];

  const SVG = {
    folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
    palette: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 3v18M3 12h18"/></svg>',
    mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v4M8 21h8"/></svg>',
    plus: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
    arrow: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
  };

  const AI_PRESETS = [
    { key: "best", label: "Лучшие", desc: "Самые сильные, цепляющие и досматриваемые моменты видео." },
    { key: "funny", label: "Смешное", desc: "Шутки, ирония, смешные реакции, неловкие паузы и панчлайны." },
    { key: "emotions", label: "Эмоции", desc: "Искренние переживания, удивление, радость, злость и живые всплески." },
    { key: "drama", label: "Драма", desc: "Конфликты, споры, напряжение, острые заявления и переломные моменты." },
    { key: "insights", label: "Инсайты", desc: "Конкретные советы, цифры, лайфхаки, пошаговые выводы и польза." },
    { key: "action", label: "Экшн", desc: "Быстрый темп, кульминации, динамичные переходы и яркие события." },
    { key: "quotes", label: "Цитаты", desc: "Короткие афористичные мысли и фразы, которые хочется переслать." },
    { key: "story", label: "История", desc: "Законченные мини-истории с завязкой, развитием и неожиданной развязкой." },
  ];

  function normalizeThemeKey(key) {
    if (key === "ocean") return "cobalt";
    if (THEMES.some((t) => t.key === key)) return key;
    return "obsidian";
  }

  const ui = {
    sourceTab: "link",
    newUrl: "",
    libFilter: "all",
    libQuery: "",
    libView: "grid",
    selectedPid: null,
    selectedDetail: null,
    theme: normalizeThemeKey(localStorage.getItem("krlzTheme") || "obsidian"),
    paletteA: localStorage.getItem("krlzPalA") || "#0ea5e9",
    paletteB: localStorage.getItem("krlzPalB") || "#f59e0b",
    whisperPoll: null,
    activePoll: null,
    activeSig: "",
    saveThemeTimer: null,
    storage: null,
    profiles: [],
    brandAssets: [],
    bgmTracks: [],
    gameClips: [],
    botStatus: null,
    editingKitId: "",
  };

  async function loadProAssetsData() {
    try {
      const [prof, assets, bgmRes, glRes, bots] = await Promise.all([
        api("/api/profiles").catch(() => ({ profiles: [] })),
        api("/api/brand-assets").catch(() => ({ assets: [] })),
        api("/api/bgm").catch(() => ({ tracks: [] })),
        api("/api/game-clips").catch(() => ({ clips: [] })),
        api("/api/bots/status").catch(() => null),
      ]);
      ui.profiles = Array.isArray(prof?.profiles) ? prof.profiles : [];
      ui.brandAssets = Array.isArray(assets?.assets) ? assets.assets : [];
      ui.bgmTracks = Array.isArray(bgmRes?.tracks) ? bgmRes.tracks : [];
      ui.gameClips = Array.isArray(glRes?.clips) ? glRes.clips : [];
      ui.botStatus = bots;
    } catch (_) {}
  }

  function applyBrandKitToOpts(kit) {
    if (!kit || !kit.config) return;
    const c = kit.config;
    state.opts.profileId = kit.id;
    if (c.aspect) state.opts.aspect = c.aspect;
    if (c.mode) state.opts.mode = c.mode;
    if (c.cut_mode) state.opts.cutMode = c.cut_mode;
    if (c.count != null) state.opts.count = Number(c.count);
    if (c.min_dur != null || c.max_dur != null || c.target_dur != null) {
      const matchDur = Object.entries(DUR_PRESETS).find(([, v]) =>
        (c.min_dur == null || Number(v.min) === Number(c.min_dur)) &&
        (c.max_dur == null || Number(v.max) === Number(c.max_dur)) &&
        (c.target_dur == null || Number(v.target) === Number(c.target_dur))
      );
      if (matchDur) state.opts.dur = matchDur[0];
    }
    if (c.language) state.opts.language = c.language;
    if (c.cut_pauses != null) state.opts.cutPauses = Boolean(c.cut_pauses);
    if (c.subtitles != null) state.opts.subtitles = Boolean(c.subtitles);
    if (c.sub_font) state.opts.subFont = c.sub_font;
    if (c.sub_size) state.opts.subSize = Number(c.sub_size);
    if (c.sub_position) state.opts.subPos = c.sub_position;
    if (c.sub_offset != null) state.opts.subOffset = Number(c.sub_offset);
    if (c.sub_speed) state.opts.subSpeed = c.sub_speed;
    if (c.sub_anim) state.opts.subAnim = c.sub_anim;
    if (c.accent) state.opts.accent = c.accent;
    if (c.uppercase != null) state.opts.uppercase = Boolean(c.uppercase);
    if (c.show_hook != null) state.opts.showHook = Boolean(c.show_hook);
    if (c.sub_outline != null) state.opts.subOutline = Boolean(c.sub_outline);
    if (c.sub_outline_width != null) state.opts.subOutlineWidth = Number(c.sub_outline_width);
    if (c.sub_outline_color) state.opts.subOutlineColor = c.sub_outline_color;
    if (c.ai_mode != null) { state.opts.aiMode = Boolean(c.ai_mode); state.opts.aiModeTouched = true; }
    if (c.ai_preset) state.opts.aiPreset = c.ai_preset;
    if (c.ai_prompt != null) state.opts.aiPrompt = String(c.ai_prompt);
    state.opts.watermark = c.watermark || null;
    state.opts.introAssetId = c.intro_asset_id || "";
    state.opts.outroAssetId = c.outro_asset_id || "";
    state.opts.gamePool = c.game_pool || null;
    state.opts.bgm = c.bgm || null;
    state.opts.punchInZoom = Boolean(c.punch_in_zoom);
    state.opts.autoDualSplit = c.auto_dual_split !== false;
    state.opts.botDeliver = Boolean(c.bot_deliver);
  }

  function currentOptsAsKitConfig() {
    const o = state.opts;
    const d = DUR_PRESETS[o.dur] || DUR_PRESETS["20-45"];
    return {
      aspect: o.aspect || "9:16",
      mode: o.mode || "auto",
      cut_mode: o.cutMode || "ai",
      count: Number(o.count ?? 10),
      min_dur: d.min,
      max_dur: d.max,
      target_dur: d.target,
      language: o.language || "auto",
      cut_pauses: Boolean(o.cutPauses),
      subtitles: o.subtitles !== false,
      sub_font: o.subFont || "montserrat",
      sub_size: Number(o.subSize || 118),
      sub_position: o.subPos || "bottom",
      sub_offset: Number(o.subOffset || 0),
      sub_speed: o.subSpeed || "calm",
      sub_anim: o.subAnim || "pop",
      accent: o.accent || "yellow",
      uppercase: o.uppercase !== false,
      show_hook: o.showHook !== false,
      sub_outline: o.subOutline !== false,
      sub_outline_width: Number(o.subOutlineWidth ?? 7),
      sub_outline_color: o.subOutlineColor || "#000000",
      ai_mode: Boolean(o.aiMode),
      ai_preset: o.aiPreset || "best",
      ai_prompt: o.aiPrompt || "",
      watermark: o.watermark || null,
      intro_asset_id: o.introAssetId || "",
      outro_asset_id: o.outroAssetId || "",
      game_pool: o.gamePool || null,
      bgm: o.bgm || null,
      punch_in_zoom: Boolean(o.punchInZoom),
      auto_dual_split: o.autoDualSplit !== false,
      bot_deliver: Boolean(o.botDeliver),
    };
  }

  function fmtBytes(bytes) {
    const b = Number(bytes || 0);
    if (!b) return "—";
    if (b >= 1024 ** 3) return `${(b / 1024 ** 3).toFixed(2)} ГБ`;
    if (b >= 1024 ** 2) return `${(b / 1024 ** 2).toFixed(0)} МБ`;
    return `${Math.max(1, Math.round(b / 1024))} КБ`;
  }

  function statusInfo(status) {
    if (status === "done") return { cls: "done", text: "Готово" };
    if (status === "error") return { cls: "error", text: "Ошибка" };
    if (status === "cancelled") return { cls: "", text: "Отменено" };
    if (status === "review") return { cls: "running", text: "Ожидает старта" };
    if (["queued", "running", "preparing", "processing"].includes(status)) {
      return { cls: "running", text: "В работе" };
    }
    return { cls: "", text: status || "—" };
  }

  function contrastInk(hex) {
    const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(String(hex || ""));
    if (!m) return "#09090B";
    const lin = (c) => {
      const s = parseInt(c, 16) / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    const lum = 0.2126 * lin(m[1]) + 0.7152 * lin(m[2]) + 0.0722 * lin(m[3]);
    return lum > 0.34 ? "#09090B" : "#FAFAFA";
  }

  function applyTheme(theme, palA, palB, persist) {
    const valid = normalizeThemeKey(theme);
    ui.theme = valid;
    if (palA && /^#[0-9a-fA-F]{6}$/.test(palA)) ui.paletteA = palA;
    if (palB && /^#[0-9a-fA-F]{6}$/.test(palB)) ui.paletteB = palB;
    const root = document.documentElement;
    root.dataset.theme = ui.theme;
    if (ui.theme === "custom") {
      root.style.setProperty("--theme-a", ui.paletteA);
      root.style.setProperty("--theme-b", ui.paletteB);
      root.style.setProperty("--action-ink", contrastInk(ui.paletteA));
    } else {
      root.style.removeProperty("--theme-a");
      root.style.removeProperty("--theme-b");
      root.style.removeProperty("--action-ink");
    }
    try {
      localStorage.setItem("krlzTheme", ui.theme);
      localStorage.setItem("krlzPalA", ui.paletteA);
      localStorage.setItem("krlzPalB", ui.paletteB);
    } catch (_) {}
    if (persist) {
      clearTimeout(ui.saveThemeTimer);
      ui.saveThemeTimer = setTimeout(() => {
        api("/api/settings", {
          method: "POST",
          body: JSON.stringify({ theme: ui.theme, palette_a: ui.paletteA, palette_b: ui.paletteB }),
        }).catch(() => {});
      }, 220);
    }
  }

  async function syncSettings() {
    try {
      const conf = await api("/api/settings");
      state.settingsData = conf;
      applyTheme(conf.theme || "obsidian", conf.palette_a || "#0ea5e9", conf.palette_b || "#f59e0b", false);
    } catch (_) {}
  }

  function updateRing(ringId, valId, percent, color) {
    const ring = $(ringId);
    const val = $(valId);
    if (!ring || !val) return;
    const p = percent == null || Number.isNaN(Number(percent)) ? 0 : Math.max(0, Math.min(100, Math.round(Number(percent))));
    ring.value = p;
    ring.style.setProperty("--value", String(p));
    if (color) ring.style.setProperty("--ring-color", color);
    ring.textContent = `${p}%`;
    val.textContent = percent == null ? "н/д" : `${p}%`;
  }

  function onHealth(h) {
    const dot = $("#gpuDot");
    const nameEl = $("#gpuName");
    if (dot) {
      dot.classList.toggle("ok", Boolean(h && h.ok));
      dot.classList.toggle("err", Boolean(h && !h.ok));
    }
    if (nameEl && !state.sysData?.gpu?.name) {
      nameEl.textContent = h && h.ok ? "Движок готов" : "ffmpeg не найден";
    }
  }

  function onSystem(data) {
    if (!data) return;
    const gpu = data.gpu || {};
    const app = data.app || {};
    const ram = data.ram || {};
    const cpu = data.cpu;
    const hwRaw = String(app.hw || "").replace("h264_", "").toUpperCase();
    const chip = hwRaw || (gpu.discrete ? "GPU" : "CPU");
    const name = gpu.name ? String(gpu.name) : (hwRaw ? `Аппаратный ${hwRaw}` : "Процессор (CPU)");
    const wModel = String(app.whisper_model || "small");
    const wLabel = wModel === "large-v3-turbo" ? "Large v3 Turbo" : wModel === "medium" ? "Medium" : "Small";
    const loadPct = Math.round(gpu.percent != null ? gpu.percent : (cpu || 0));

    const nameEl = $("#gpuName");
    const chipEl = $("#gpuChip");
    const metaEl = $("#gpuMeta");
    const loadEl = $("#gpuLoad");
    const barEl = $("#gpuMiniBar");
    const dotEl = $("#gpuDot");
    if (nameEl) nameEl.textContent = name;
    if (chipEl) chipEl.textContent = chip;
    if (metaEl) metaEl.textContent = `Whisper ${wLabel}${app.whisper_cuda ? " · CUDA" : ""}`;
    if (loadEl) loadEl.textContent = `${loadPct}%`;
    if (barEl) barEl.style.width = `${Math.max(4, Math.min(100, loadPct))}%`;
    if (dotEl && !dotEl.classList.contains("err")) dotEl.classList.add("ok");

    // Live-update Dashboard circular rings without re-rendering DOM!
    if (!state.current && state.nav === "dashboard") {
      updateRing("#ringCpu", "#ringCpuVal", cpu, "var(--signal)");
      updateRing("#ringGpu", "#ringGpuVal", gpu.percent, "var(--signal-2)");
      updateRing("#ringRam", "#ringRamVal", ram.percent, "var(--success)");
      const subGpu = $("#ringGpuSub");
      const subRam = $("#ringRamSub");
      const subCpu = $("#ringCpuSub");
      if (subGpu) subGpu.textContent = gpu.name ? String(gpu.name).replace(/NVIDIA GeForce |AMD Radeon |\(R\)|\(TM\)| Graphics/gi, "").trim() : chip;
      if (subRam && ram.total_mb) subRam.textContent = `${fmtGb(ram.used_mb)} / ${fmtGb(ram.total_mb)} ГБ`;
      if (subCpu) subCpu.textContent = data.job?.stage ? "В работе" : "Простой";
      const hwPill = $("#dashHwPill");
      if (hwPill) hwPill.textContent = `Кодировщик: ${chip}`;
      const wPill = $("#dashWhisperPill");
      if (wPill) wPill.textContent = `Whisper: ${wLabel}${app.whisper_cuda ? " (CUDA)" : " (CPU)"}`;
    }
  }

  /* ---------------- 1. Dashboard (Главная) ---------------- */

  function dashboardHTML() {
    const sys = state.sysData || {};
    const cpu = Math.round(sys.cpu || 0);
    const gpuPct = Math.round(sys.gpu?.percent || 0);
    const ramPct = Math.round(sys.ram?.percent || 0);
    const gpuName = sys.gpu?.name ? String(sys.gpu.name).replace(/NVIDIA GeForce |AMD Radeon |\(R\)|\(TM\)| Graphics/gi, "").trim() : "Определяю…";
    const ramSub = sys.ram?.total_mb ? `${fmtGb(sys.ram.used_mb)} / ${fmtGb(sys.ram.total_mb)} ГБ` : "Память";
    const hwChip = String(sys.app?.hw || "").replace("h264_", "").toUpperCase() || "CPU";
    const wKey = String(sys.app?.whisper_model || "small");
    const wLabel = wKey === "large-v3-turbo" ? "Large v3 Turbo" : wKey === "medium" ? "Medium" : "Small";

    const recent = state.projects.slice(0, 5);
    const activeJobs = state.projects.filter((p) => ["queued", "running", "preparing", "processing"].includes(p.status));

    return `
      <section class="page-head">
        <div>
          <h1>Студия монтажа KrlzCut</h1>
          <p>Локальный рендер FFmpeg и распознавание речи Whisper на этом компьютере — видео остаётся на диске.</p>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <button class="btn-primary" id="dashNewBtn" type="button" style="display:inline-flex;align-items:center;gap:7px">${SVG.plus}<span>Создать проект</span></button>
        </div>
      </section>

      <section class="dash-modes">
        <button class="mode-launch-card featured" data-launch-mode="ai" type="button">
          <span class="mode-num"><span>01 · WHISPER + ИИ</span><span class="mode-pill-tag">Основной</span></span>
          <h3>Нарезка по речи</h3>
          <p>Транскрипция Whisper, 8 сценариев отбора фрагментов, автокадрирование по лицу и субтитры.</p>
          <span class="mode-cta">Настроить проект ${SVG.arrow}</span>
        </button>

        <button class="mode-launch-card" data-launch-mode="stream" type="button">
          <span class="mode-num"><span>02 · ПРЯМОЙ ЭФИР</span><span class="mode-pill-tag">Поток</span></span>
          <h3>Запись и нарезка стримов</h3>
          <p>Захват прямых трансляций YouTube, Twitch и Kick с выделением фрагментов во время эфира.</p>
          <span class="mode-cta">Подключить эфир ${SVG.arrow}</span>
        </button>

        <button class="mode-launch-card" data-launch-mode="even" type="button">
          <span class="mode-num"><span>03 · FFMPEG</span><span class="mode-pill-tag">Без Whisper</span></span>
          <h3>Равномерная нарезка</h3>
          <p>Деление длинного видео на равные отрезки напрямую через FFmpeg без этапа транскрипции.</p>
          <span class="mode-cta">Разделить видео ${SVG.arrow}</span>
        </button>
      </section>

      <section class="dash-grid">
        <div style="display:flex;flex-direction:column;gap:16px">
          <div class="studio-card">
            <div class="card-title-row">
              <h2>Недавние проекты</h2>
              <button class="btn-ghost" id="dashAllProjBtn" type="button" style="height:32px;padding:0 12px;font-size:12.5px">Открыть все (${state.projects.length})</button>
            </div>
            ${recent.length ? `<div class="recent-list">
              ${recent.map((p) => {
                const st = statusInfo(p.status);
                const clipsCnt = Number(p.clips_count ?? p.meta?.clips ?? 0);
                return `<div class="recent-row" data-open-pid="${p.id}">
                  <div class="recent-thumb">${p.thumb_url ? `<img src="${esc(p.thumb_url)}" alt="" loading="lazy" />` : "Нет кадра"}</div>
                  <div class="recent-info">
                    <div class="recent-title">${esc(p.title || p.url)}</div>
                    <div class="recent-meta">
                      <span>${clipsCnt} ${plural(clipsCnt, "клип", "клипа", "клипов")}</span>
                      ${p.duration ? `<span>${fmtDur(p.duration)}</span>` : ""}
                      ${p.size_bytes ? `<span>${fmtBytes(p.size_bytes)}</span>` : ""}
                    </div>
                  </div>
                  <span class="status-pill ${st.cls}">${esc(st.text)}</span>
                </div>`;
              }).join("")}
            </div>` : `<div class="hint" style="padding:18px 4px">Проектов пока нет — выберите режим выше или откройте локальный видеофайл.</div>`}

            <div class="quick-tools">
              <button class="quick-tool-btn" id="dashLocalBtn" type="button">
                ${SVG.folder}<span>Открыть видеофайл</span>
              </button>
              <button class="quick-tool-btn" id="dashThemeBtn" type="button">
                ${SVG.palette}<span>Настроить тему</span>
              </button>
              <button class="quick-tool-btn" id="dashWhisperBtn" type="button">
                ${SVG.mic}<span>Выбрать модель Whisper</span>
              </button>
            </div>
          </div>
        </div>

        <div style="display:flex;flex-direction:column;gap:16px">
          <div class="studio-card">
            <div class="card-title-row">
              <h2>Ресурсы системы</h2>
              <span class="status-pill done">Локально</span>
            </div>
            <div class="rings-row">
              <div class="ring-tile">
                <div class="ring-wrap">
                  <progress id="ringCpu" class="progress-ring" value="${cpu}" max="100" style="--value:${cpu};--ring-color:var(--signal)" aria-label="Загрузка процессора CPU">${cpu}%</progress>
                  <span class="ring-center" aria-hidden="true"><b id="ringCpuVal">${cpu}%</b><small>CPU</small></span>
                </div>
                <span class="ring-sub" id="ringCpuSub">${sys.job?.stage ? "В работе" : "Простой"}</span>
              </div>

              <div class="ring-tile">
                <div class="ring-wrap">
                  <progress id="ringGpu" class="progress-ring" value="${gpuPct}" max="100" style="--value:${gpuPct};--ring-color:var(--signal-2)" aria-label="Загрузка видеокарты GPU">${gpuPct}%</progress>
                  <span class="ring-center" aria-hidden="true"><b id="ringGpuVal">${sys.gpu?.percent == null ? "н/д" : `${gpuPct}%`}</b><small>GPU</small></span>
                </div>
                <span class="ring-sub" id="ringGpuSub" title="${esc(gpuName)}">${esc(gpuName)}</span>
              </div>

              <div class="ring-tile">
                <div class="ring-wrap">
                  <progress id="ringRam" class="progress-ring" value="${ramPct}" max="100" style="--value:${ramPct};--ring-color:var(--success)" aria-label="Использование оперативной памяти RAM">${ramPct}%</progress>
                  <span class="ring-center" aria-hidden="true"><b id="ringRamVal">${ramPct}%</b><small>RAM</small></span>
                </div>
                <span class="ring-sub" id="ringRamSub">${esc(ramSub)}</span>
              </div>
            </div>
            <div class="sys-hw-strip">
              <span class="sys-hw-pill" id="dashHwPill">Кодировщик: ${esc(hwChip)}</span>
              <span class="sys-hw-pill" id="dashWhisperPill">Whisper: ${esc(wLabel)}${sys.app?.whisper_cuda ? " (CUDA)" : " (CPU)"}</span>
            </div>
          </div>

          <div class="studio-card">
            <div class="card-title-row">
              <h2>Очередь рендера</h2>
              <button class="btn-ghost" id="dashQueueBtn" type="button" style="height:30px;padding:0 10px;font-size:12px">Перейти в очередь</button>
            </div>
            ${activeJobs.length ? activeJobs.slice(0, 3).map((p) => `
              <div style="margin-bottom:10px">
                <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:5px">
                  <b style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:75%">${esc(p.title || p.url)}</b>
                  <span style="font-variant-numeric:tabular-nums">${Math.round(p.progress || 0)}%</span>
                </div>
                <div class="queue-bar"><i style="width:${Math.max(4, Math.round(p.progress || 0))}%"></i></div>
                <div style="font-size:12px;color:var(--muted);margin-top:4px">${esc(p.stage || "Обработка…")}</div>
              </div>
            `).join("") : `<div class="hint">Активных задач рендера нет.</div>`}
          </div>
        </div>
      </section>
    `;
  }

  function bindDashboard() {
    $("#dashNewBtn")?.addEventListener("click", () => navigate("new"));
    $("#dashAllProjBtn")?.addEventListener("click", () => navigate("projects"));
    $("#dashQueueBtn")?.addEventListener("click", () => navigate("queue"));
    $("#dashThemeBtn")?.addEventListener("click", () => navigate("settings"));
    $("#dashWhisperBtn")?.addEventListener("click", () => navigate("settings"));
    $("#dashLocalBtn")?.addEventListener("click", () => {
      ui.sourceTab = "file";
      navigate("new");
    });
    $$("[data-launch-mode]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.opts.cutMode = btn.dataset.launchMode || "ai";
        navigate("new");
      });
    });
    $$("[data-open-pid]").forEach((row) => {
      row.addEventListener("click", () => openProject(row.dataset.openPid));
    });
  }

  /* ---------------- 2. New Project (Новый проект + 8 AI Presets + Sticky Summary) ---------------- */

  function newProjectHTML() {
    const o = state.opts;
    if (o.cutMode === "stream" && ui.sourceTab !== "link") ui.sourceTab = "link";
    const presetObj = AI_PRESETS.find((p) => p.key === (o.aiPreset || "best")) || AI_PRESETS[0];
    const modeTitle = o.cutMode === "stream" ? "Нарезка стримов" : o.cutMode === "even" ? "Обычная нарезка (FFmpeg)" : "ИИ-нарезка";
    const aspectLabels = { "9:16": "9:16 Вертикальный", "1:1": "1:1 Квадрат", "16:9": "16:9 Горизонтальный", "4:5": "4:5 Пост" };
    const framingLabels = { auto: "По лицу (AI)", crop: "По центру", blur: "Размытый фон" };
    const langLabels = { auto: "Автоопределение", ru: "Русский", en: "English" };

    return `
      <section class="page-head">
        <div>
          <h1>Новый проект</h1>
          <p>Настройте профиль канала, режим, пресет и стиль — справа сразу виден итог перед запуском.</p>
        </div>
      </section>

      ${ui.profiles.length ? `
      <div class="studio-card" style="margin-bottom:14px;padding:12px 16px">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            <span class="hint" style="font-weight:600;color:var(--text)">Brand Kit:</span>
            <button class="mini-chip ${!o.profileId ? "active" : ""}" data-apply-kit="" type="button">Без профиля</button>
            ${ui.profiles.map((k) => `<button class="mini-chip ${o.profileId === k.id ? "active" : ""}" data-apply-kit="${esc(k.id)}" type="button">${esc(k.name)}</button>`).join("")}
          </div>
          <button class="mini-chip" id="newManageKitsBtn" type="button">Настроить профили</button>
        </div>
      </div>` : ""}

      <div class="new-layout">
        <div class="new-col">
          <div class="studio-card">
            <div class="card-title-row"><h3>1. Источник видео</h3></div>
            <div class="source-tabs">
              <button class="source-tab ${ui.sourceTab === "link" ? "active" : ""}" data-src-tab="link" type="button">Ссылка</button>
              <button class="source-tab ${ui.sourceTab === "file" ? "active" : ""}" data-src-tab="file" type="button" ${o.cutMode === "stream" ? 'disabled title="Для записи прямых эфиров используется ссылка на поток"' : ""}>Локальный файл</button>
            </div>

            ${ui.sourceTab === "link" ? `
              <div style="display:flex;gap:10px;align-items:center">
                <input id="urlInput" class="input" type="url" value="${esc(ui.newUrl)}" style="flex:1;height:44px;padding:0 14px;font-size:13.5px" placeholder="${o.cutMode === "stream" ? "https://youtube.com/live/... или https://twitch.tv/..." : "Вставьте ссылку на YouTube, Twitch, Rutube, VK или прямой MP4…"}" />
              </div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;gap:10px;flex-wrap:wrap">
                <span class="hint">Поддерживается выбор дорожки озвучки и HD-качества перед стартом.</span>
                <select id="cookiesSel" style="height:32px;padding:0 10px;border-radius:9px;background:rgba(255,255,255,0.06);border:1px solid var(--separator);font-size:12px">
                  <option value="" ${!o.cookies ? "selected" : ""}>Cookies: без браузера</option>
                  <option value="chrome" ${o.cookies === "chrome" ? "selected" : ""}>Cookies: Chrome</option>
                  <option value="edge" ${o.cookies === "edge" ? "selected" : ""}>Cookies: Edge</option>
                  <option value="firefox" ${o.cookies === "firefox" ? "selected" : ""}>Cookies: Firefox</option>
                </select>
              </div>
            ` : `
              <div id="newDropzone" style="padding:30px 18px;border-radius:15px;border:1.5px dashed var(--accent-border);background:rgba(255,255,255,0.025);text-align:center;cursor:pointer">
                <div style="font-size:15px;font-weight:660;margin-bottom:6px">Перетащите видео или аудио сюда</div>
                <div class="hint" style="margin-bottom:14px">MP4, MOV, MKV, WebM, AVI, MP3, WAV — файлы до 64 ГБ открываются мгновенно без копирования</div>
                <button class="btn-primary" id="newPickFileBtn" type="button">Выбрать файл на компьютере</button>
              </div>
            `}
          </div>

          <div class="studio-card">
            <div class="card-title-row"><h3>2. Режим обработки</h3></div>
            <div class="mode-select-grid">
              <button class="mode-opt-card ${o.cutMode === "ai" ? "active" : ""}" data-cut-mode="ai" type="button">
                <b>ИИ-нарезка</b>
                <small>Whisper + поиск лучших моментов + живые субтитры</small>
              </button>
              <button class="mode-opt-card ${o.cutMode === "stream" ? "active" : ""}" data-cut-mode="stream" type="button">
                <b>Нарезка стримов</b>
                <small>Запись прямого эфира и автонарезка на лету</small>
              </button>
              <button class="mode-opt-card ${o.cutMode === "even" ? "active" : ""}" data-cut-mode="even" type="button">
                <b>Равномерная (FFmpeg)</b>
                <small>Деление на равные фрагменты напрямую через FFmpeg без Whisper</small>
              </button>
            </div>
          </div>

          ${o.cutMode !== "even" ? `
          <div class="studio-card">
            <div class="card-title-row">
              <h3>3. ИИ-пресет поиска моментов</h3>
              <label style="display:inline-flex;align-items:center;gap:8px;font-size:12.5px;color:var(--text);cursor:pointer">
                <input type="checkbox" id="newAiModeToggle" ${o.aiMode ? "checked" : ""} ${state.ai?.configured ? "" : "disabled"} />
                <span>Подбор через LLM</span>
              </label>
            </div>
            <div class="preset-grid">
              ${AI_PRESETS.map((p) => `<button class="preset-pill ${(o.aiPreset || "best") === p.key ? "active" : ""}" data-ai-preset="${p.key}" type="button">${esc(p.label)}</button>`).join("")}
            </div>
            <div class="preset-desc-box" id="presetDescBox">${esc(presetObj.desc)}</div>
            <div style="margin-top:10px">
              <input id="newAiPrompt" type="text" value="${esc(o.aiPrompt || "")}" placeholder="Своё уточнение для ИИ (необязательно), например: ищи только про деньги и кейсы…" style="width:100%;height:38px;padding:0 12px;font-size:13px" />
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:8px;flex-wrap:wrap">
              <span class="hint" id="newAiModeHint">${state.ai?.configured
                ? (o.aiMode
                    ? `LLM активен: ${esc(state.ai.model || state.ai.provider || "настроено")} — уточнение и пресет передаются модели.`
                    : "LLM выключен — отбор идёт локальной эвристикой по пресету.")
                : "API-ключ LLM не задан — используется локальный отбор по пресету. Уточнение выше работает после подключения ИИ."}</span>
              ${!state.ai?.configured ? `<button class="mini-chip" id="newSetupAiBtn" type="button" style="height:28px;font-size:12px">Настроить ИИ</button>` : ""}
            </div>
          </div>` : ""}

          <div class="studio-card">
            <div class="card-title-row"><h3>${o.cutMode !== "even" ? "4." : "3."} Формат, длительность и субтитры</h3></div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px">
              <div>
                <div class="hint" style="margin-bottom:6px">Количество клипов</div>
                <div class="chip-row">
                  ${[5, 10, 20, 0].map((n) => `<button class="mini-chip ${o.count === n ? "active" : ""}" data-opt-count="${n}" type="button">${n === 0 ? "Все" : n}</button>`).join("")}
                </div>
              </div>
              <div>
                <div class="hint" style="margin-bottom:6px">Длительность клипа</div>
                <div class="chip-row">
                  ${Object.entries(DUR_PRESETS).map(([k, v]) => `<button class="mini-chip ${o.dur === k ? "active" : ""}" data-opt-dur="${k}" type="button">${v.label}</button>`).join("")}
                </div>
              </div>
              <div>
                <div class="hint" style="margin-bottom:6px">Формат кадра</div>
                <div class="chip-row">
                  ${["9:16", "1:1", "16:9", "4:5"].map((a) => `<button class="mini-chip ${o.aspect === a ? "active" : ""}" data-opt-aspect="${a}" type="button">${a}</button>`).join("")}
                </div>
              </div>
              <div>
                <div class="hint" style="margin-bottom:6px">Кадрирование</div>
                <div class="chip-row">
                  ${[["auto", "По лицу"], ["crop", "По центру"], ["blur", "Размытие"]].map(([k, lbl]) => `<button class="mini-chip ${o.mode === k ? "active" : ""}" data-opt-mode="${k}" type="button">${lbl}</button>`).join("")}
                </div>
              </div>
              <div>
                <div class="hint" style="margin-bottom:6px">Язык речи</div>
                <div class="chip-row">
                  ${[["auto", "Авто"], ["ru", "Русский"], ["en", "English"]].map(([k, lbl]) => `<button class="mini-chip ${(o.language || "auto") === k ? "active" : ""}" data-opt-lang="${k}" type="button">${lbl}</button>`).join("")}
                </div>
              </div>
              <div>
                <div class="hint" style="margin-bottom:6px">Субтитры и анимация</div>
                <div class="chip-row">
                  <button class="mini-chip ${o.subtitles ? "active" : ""}" id="newToggleSubs" type="button">${o.subtitles ? "Субтитры: Вкл" : "Субтитры: Выкл"}</button>
                  ${[["pop", "Pop"], ["fade", "Fade"], ["slide", "Slide"], ["bounce", "Bounce"], ["none", "Нет"]].map(([k, lbl]) => `<button class="mini-chip ${(o.subAnim || "pop") === k ? "active" : ""}" data-opt-anim="${k}" type="button">${lbl}</button>`).join("")}
                </div>
              </div>
            </div>
          </div>

          <div class="studio-card">
            <div class="card-title-row"><h3>${o.cutMode !== "even" ? "5." : "4."} Автоматизация, пул фонов и музыка</h3></div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px">
              <div>
                <label style="display:flex;align-items:center;gap:7px;font-size:13px;font-weight:600;margin-bottom:8px;cursor:pointer">
                  <input type="checkbox" id="newGamePoolOn" ${o.gamePool?.enabled ? "checked" : ""} />
                  <span>Пул Слоя игры (случайный фон)</span>
                </label>
                ${o.gamePool?.enabled ? `
                  <div style="display:flex;flex-direction:column;gap:8px">
                    <select id="newGamePoolTag" style="height:34px;padding:0 10px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12.5px">
                      <option value="all" ${(o.gamePool.tag || "all") === "all" ? "selected" : ""}>Все фоны (приоритет своих)</option>
                      ${Array.from(new Set(ui.gameClips.flatMap((c) => c.tags || []))).map((tag) => `<option value="${esc(tag)}" ${o.gamePool.tag === tag ? "selected" : ""}>Тег: ${esc(tag)}</option>`).join("")}
                    </select>
                    <div class="chip-row">
                      ${["60/40", "50/50", "65/35", "70/30"].map((sp) => `<button class="mini-chip ${(o.gamePool.split || "60/40") === sp ? "active" : ""}" data-pool-split="${sp}" type="button">${sp}</button>`).join("")}
                    </div>
                  </div>
                ` : `<div class="hint">Каждому клипу подбирается свой случайный фон и старт без повторов.</div>`}
              </div>

              <div>
                <label style="display:flex;align-items:center;gap:7px;font-size:13px;font-weight:600;margin-bottom:8px;cursor:pointer">
                  <input type="checkbox" id="newBgmOn" ${o.bgm?.enabled ? "checked" : ""} ${ui.bgmTracks.length ? "" : "disabled"} />
                  <span>Фоновая музыка (BGM)</span>
                </label>
                ${ui.bgmTracks.length ? `
                  <div style="display:flex;flex-direction:column;gap:8px">
                    <select id="newBgmSel" style="height:34px;padding:0 10px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12.5px">
                      ${ui.bgmTracks.map((t) => `<option value="${esc(t.id)}" ${(o.bgm?.track_id || ui.bgmTracks[0]?.id) === t.id ? "selected" : ""}>${esc(t.name)} (${t.duration} с)</option>`).join("")}
                    </select>
                    <label style="display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);cursor:pointer">
                      <input type="checkbox" id="newBgmDuck" ${o.bgm?.ducking !== false ? "checked" : ""} /> Авто-приглушение под речью (-22 дБ)
                    </label>
                  </div>
                ` : `<div class="hint">Загрузите MP3/WAV треки в Настройках или Редакторе клипа.</div>`}
              </div>

              <div style="display:flex;flex-direction:column;gap:9px;justify-content:center">
                <label style="display:inline-flex;align-items:center;gap:7px;font-size:12.5px;cursor:pointer">
                  <input type="checkbox" id="newPunchZoom" ${o.punchInZoom ? "checked" : ""} />
                  <span>Hook Punch-In Zoom (первые 3 сек)</span>
                </label>
                <label style="display:inline-flex;align-items:center;gap:7px;font-size:12.5px;cursor:pointer">
                  <input type="checkbox" id="newDualSplit" ${o.autoDualSplit !== false ? "checked" : ""} />
                  <span>Авто 2-спикерный сплит (интервью)</span>
                </label>
                <label style="display:inline-flex;align-items:center;gap:7px;font-size:12.5px;cursor:pointer">
                  <input type="checkbox" id="newBotDeliver" ${o.botDeliver ? "checked" : ""} />
                  <span>Отправлять готовые клипы в бот</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        <aside class="studio-card summary-sticky">
          <div class="card-title-row" style="margin-bottom:4px">
            <h3>Итог проекта</h3>
            <span class="status-pill running">Готов к запуску</span>
          </div>
          <div class="summary-rows">
            <div class="summary-row"><span>Режим</span><b>${esc(modeTitle)}</b></div>
            ${o.cutMode !== "even" ? `<div class="summary-row"><span>ИИ-пресет</span><b>${esc(presetObj.label)}</b></div>` : ""}
            ${o.cutMode !== "even" ? `<div class="summary-row"><span>Отбор моментов</span><b>${o.aiMode && state.ai?.configured ? esc(state.ai.model || "LLM") : "Локальный"}</b></div>` : ""}
            <div class="summary-row"><span>Клипов</span><b>${o.count === 0 ? "Все подходящие" : `до ${o.count}`}</b></div>
            <div class="summary-row"><span>Длительность</span><b>${esc((DUR_PRESETS[o.dur] || DUR_PRESETS["20-45"]).label)}</b></div>
            <div class="summary-row"><span>Формат</span><b>${esc(aspectLabels[o.aspect] || o.aspect)}</b></div>
            <div class="summary-row"><span>Кадрирование</span><b>${esc(framingLabels[o.mode] || o.mode)}</b></div>
            <div class="summary-row"><span>Язык</span><b>${esc(langLabels[o.language || "auto"] || "Авто")}</b></div>
            <div class="summary-row"><span>Субтитры</span><b>${o.subtitles && o.cutMode !== "even" ? `Вкл · ${(o.subAnim || "pop").toUpperCase()}` : "Выкл"}</b></div>
            ${o.profileId ? `<div class="summary-row"><span>Brand Kit</span><b>${esc((ui.profiles.find((k) => k.id === o.profileId) || {}).name || "Выбран")}</b></div>` : ""}
            ${o.gamePool?.enabled ? `<div class="summary-row"><span>Пул фонов</span><b>${esc(o.gamePool.split || "60/40")} · ${esc(o.gamePool.tag || "all")}</b></div>` : ""}
            ${o.bgm?.enabled ? `<div class="summary-row"><span>Музыка</span><b>${o.bgm.ducking !== false ? "BGM + Ducking" : "BGM"}</b></div>` : ""}
            ${o.botDeliver ? `<div class="summary-row"><span>Одобрение</span><b>Telegram / Discord</b></div>` : ""}
          </div>

          <button class="btn-launch-big" id="newLaunchBtn" type="button">
            ${ui.sourceTab === "file" ? "Выбрать файл и запустить" : o.cutMode === "stream" ? "Подключиться к стриму" : o.cutMode === "even" ? "Нарезать через FFmpeg" : "Создать клипы"}
          </button>
          <div class="hint" style="text-align:center">Рендер выполняется локально на этом компьютере. После нарезки любой клип открывается в редакторе.</div>
        </aside>
      </div>
    `;
  }

  function bindNewProject() {
    $$("[data-apply-kit]").forEach((b) => {
      b.addEventListener("click", () => {
        const kid = b.dataset.applyKit;
        if (!kid) {
          state.opts.profileId = "";
          state.opts.watermark = null;
          state.opts.introAssetId = "";
          state.opts.outroAssetId = "";
          state.opts.gamePool = null;
          state.opts.bgm = null;
          state.opts.punchInZoom = false;
          state.opts.botDeliver = false;
          renderNavView(true);
          return;
        }
        const kit = ui.profiles.find((k) => k.id === kid);
        if (kit) {
          applyBrandKitToOpts(kit);
          toast(`Применён Brand Kit «${kit.name}»`);
          renderNavView(true);
        }
      });
    });
    $("#newManageKitsBtn")?.addEventListener("click", () => navigate("settings"));
    $("#newGamePoolOn")?.addEventListener("change", (e) => {
      if (e.target.checked) {
        state.opts.gamePool = { enabled: true, tag: state.opts.gamePool?.tag || "all", split: state.opts.gamePool?.split || "60/40", clip_ids: [] };
      } else {
        state.opts.gamePool = null;
      }
      renderNavView(true);
    });
    $("#newGamePoolTag")?.addEventListener("change", (e) => {
      if (state.opts.gamePool) state.opts.gamePool.tag = e.target.value;
      renderNavView(true);
    });
    $$("[data-pool-split]").forEach((b) => {
      b.addEventListener("click", () => {
        if (state.opts.gamePool) state.opts.gamePool.split = b.dataset.poolSplit;
        renderNavView(true);
      });
    });
    $("#newBgmOn")?.addEventListener("change", (e) => {
      if (e.target.checked && ui.bgmTracks.length) {
        const tid = $("#newBgmSel")?.value || ui.bgmTracks[0].id;
        state.opts.bgm = { enabled: true, track_id: tid, volume_db: -14, ducking: $("#newBgmDuck")?.checked !== false, duck_db: -22 };
      } else {
        state.opts.bgm = null;
      }
      renderNavView(true);
    });
    $("#newBgmSel")?.addEventListener("change", (e) => {
      if (state.opts.bgm) state.opts.bgm.track_id = e.target.value;
    });
    $("#newBgmDuck")?.addEventListener("change", (e) => {
      if (state.opts.bgm) state.opts.bgm.ducking = e.target.checked;
      renderNavView(true);
    });
    $("#newPunchZoom")?.addEventListener("change", (e) => { state.opts.punchInZoom = e.target.checked; });
    $("#newDualSplit")?.addEventListener("change", (e) => { state.opts.autoDualSplit = e.target.checked; });
    $("#newBotDeliver")?.addEventListener("change", (e) => { state.opts.botDeliver = e.target.checked; renderNavView(true); });

    $$("[data-src-tab]").forEach((b) => {
      b.addEventListener("click", () => {
        if (b.disabled) return;
        ui.sourceTab = b.dataset.srcTab;
        renderNavView(true);
      });
    });
    $$("[data-cut-mode]").forEach((b) => {
      b.addEventListener("click", () => {
        state.opts.cutMode = b.dataset.cutMode;
        if (state.opts.cutMode === "stream") ui.sourceTab = "link";
        renderNavView(true);
      });
    });
    $$("[data-ai-preset]").forEach((b) => {
      b.addEventListener("click", () => { state.opts.aiPreset = b.dataset.aiPreset; renderNavView(true); });
    });
    $$("[data-opt-count]").forEach((b) => {
      b.addEventListener("click", () => { state.opts.count = Number(b.dataset.optCount); renderNavView(true); });
    });
    $$("[data-opt-dur]").forEach((b) => {
      b.addEventListener("click", () => { state.opts.dur = b.dataset.optDur; renderNavView(true); });
    });
    $$("[data-opt-aspect]").forEach((b) => {
      b.addEventListener("click", () => { state.opts.aspect = b.dataset.optAspect; renderNavView(true); });
    });
    $$("[data-opt-mode]").forEach((b) => {
      b.addEventListener("click", () => { state.opts.mode = b.dataset.optMode; renderNavView(true); });
    });
    $$("[data-opt-lang]").forEach((b) => {
      b.addEventListener("click", () => { state.opts.language = b.dataset.optLang; renderNavView(true); });
    });
    $$("[data-opt-anim]").forEach((b) => {
      b.addEventListener("click", () => { state.opts.subAnim = b.dataset.optAnim; renderNavView(true); });
    });
    $("#newToggleSubs")?.addEventListener("click", () => {
      state.opts.subtitles = !state.opts.subtitles;
      renderNavView(true);
    });
    $("#cookiesSel")?.addEventListener("change", (e) => { state.opts.cookies = e.target.value; });
    $("#newAiPrompt")?.addEventListener("input", (e) => {
      state.opts.aiPrompt = e.target.value;
      if (e.target.value.trim() && state.ai?.configured && !state.opts.aiMode && !state.opts.aiModeTouched) {
        state.opts.aiMode = true;
        if ($("#newAiModeToggle")) $("#newAiModeToggle").checked = true;
      }
    });
    $("#newAiModeToggle")?.addEventListener("change", (e) => {
      state.opts.aiModeTouched = true;
      state.opts.aiMode = Boolean(e.target.checked);
      renderNavView(true);
    });
    $("#newSetupAiBtn")?.addEventListener("click", () => {
      if (typeof openSettings === "function") openSettings();
      else navigate("settings");
    });

    const pickLocal = async () => {
      const native = window.pywebview && window.pywebview.api;
      if (native && typeof native.choose_media_file === "function") {
        try {
          const res = await native.choose_media_file();
          if (res && res.ok && res.path) { openLocalFile(res.path); return; }
          if (res && res.cancelled) return;
        } catch (_) {}
      }
      $("#fileInput")?.click();
    };

    $("#newPickFileBtn")?.addEventListener("click", pickLocal);
    const dz = $("#newDropzone");
    if (dz) {
      dz.addEventListener("click", (e) => { if (!e.target.closest("button")) pickLocal(); });
      dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.style.background = "var(--accent-soft)"; });
      dz.addEventListener("dragleave", () => { dz.style.background = "rgba(255,255,255,0.025)"; });
      dz.addEventListener("drop", (e) => {
        e.preventDefault();
        dz.style.background = "rgba(255,255,255,0.025)";
        const file = e.dataTransfer?.files?.[0];
        if (file) uploadFile(file);
      });
    }

    const launch = async () => {
      if (ui.sourceTab === "file") {
        pickLocal();
        return;
      }
      const input = $("#urlInput");
      const url = (input && input.value || "").trim();
      if (!url) {
        input?.focus();
        toast("Вставьте ссылку на видео или эфир", "err");
        return;
      }
      if (state.opts.cutMode === "stream") {
        try {
          const project = await api("/api/streams", {
            method: "POST",
            body: JSON.stringify({ url, options: heroOptions() }),
          });
          ui.newUrl = "";
          await loadProjects();
          openProject(project.id);
        } catch (err) { toast(err.message, "err"); }
        return;
      }
      askQuality(url);
    };

    $("#newLaunchBtn")?.addEventListener("click", launch);
    $("#urlInput")?.addEventListener("input", (e) => { ui.newUrl = e.target.value; });
    $("#urlInput")?.addEventListener("keydown", (e) => { if (e.key === "Enter") launch(); });
  }

  /* ---------------- 3. Projects Library (Проекты + Фильтры + Предпросмотр + Переименование) ---------------- */

  function filteredProjects() {
    const q = ui.libQuery.trim().toLowerCase();
    return state.projects.filter((p) => {
      if (ui.libFilter === "done" && p.status !== "done") return false;
      if (ui.libFilter === "running" && !["queued", "running", "preparing", "processing", "review"].includes(p.status)) return false;
      if (ui.libFilter === "error" && p.status !== "error") return false;
      if (q && !(String(p.title || "") + " " + String(p.url || "")).toLowerCase().includes(q)) return false;
      return true;
    });
  }

  function projectsContentHTML() {
    const items = filteredProjects();
    const sel = items.find((p) => p.id === ui.selectedPid) || items[0] || null;
    if (sel) ui.selectedPid = sel.id;
    return `
      <div class="lib-layout ${sel ? "" : "no-preview"}">
        <div>
          ${items.length ? `<div class="lib-grid ${ui.libView === "list" ? "list-view" : ""}">
            ${items.map((p) => {
              const st = statusInfo(p.status);
              const clipsCnt = Number(p.clips_count ?? p.meta?.clips ?? 0);
              return `<article class="proj-card ${sel && sel.id === p.id ? "selected" : ""}" data-sel-pid="${p.id}">
                <div class="proj-thumb">
                  ${p.thumb_url ? `<img src="${esc(p.thumb_url)}" alt="" loading="lazy" />` : `<span>Нет превью</span>`}
                  <div class="proj-thumb-badges">
                    <span class="proj-badge">${clipsCnt} ${plural(clipsCnt, "клип", "клипа", "клипов")}</span>
                    ${p.duration ? `<span class="proj-badge">${fmtDur(p.duration)}</span>` : ""}
                  </div>
                </div>
                <div class="proj-card-body">
                  <div class="proj-card-title" title="${esc(p.title || p.url)}">${esc(p.title || p.url)}</div>
                  <div class="proj-card-meta">
                    <span class="status-pill ${st.cls}">${esc(st.text)}</span>
                    <span>${fmtBytes(p.size_bytes)}</span>
                  </div>
                </div>
              </article>`;
            }).join("")}
          </div>` : `<div class="studio-card" style="text-align:center;padding:42px 20px">
            <div style="font-size:16px;font-weight:600;margin-bottom:6px">Ничего не найдено</div>
            <div class="hint">Попробуйте сбросить фильтр или создайте новый проект.</div>
          </div>`}
        </div>

        ${sel ? `<aside class="studio-card inspector-panel">
          <div class="inspector-media">
            ${sel.thumb_url ? `<img src="${esc(sel.thumb_url)}" alt="" />` : `<div style="height:100%;display:grid;place-items:center;color:var(--muted)">Превью появится после загрузки</div>`}
          </div>
          <div>
            <h3 style="margin:0 0 6px;font-size:16px;line-height:1.3">${esc(sel.title || sel.url)}</h3>
            <div class="hint">${Number(sel.clips_count ?? 0)} ${plural(Number(sel.clips_count ?? 0), "клип", "клипа", "клипов")} · ${sel.duration ? fmtDur(sel.duration) : "—"} · ${fmtBytes(sel.size_bytes)}</div>
          </div>
          <div style="display:flex;flex-direction:column;gap:8px">
            <button class="btn-primary" id="inspOpenBtn" type="button" style="width:100%">Открыть проект</button>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
              <button class="btn-ghost" id="inspRenameBtn" type="button">Переименовать</button>
              <button class="btn-ghost danger" id="inspDeleteBtn" type="button">Удалить</button>
            </div>
          </div>
        </aside>` : ""}
      </div>
    `;
  }

  function projectsLibraryHTML() {
    const all = state.projects;
    const cntDone = all.filter((p) => p.status === "done").length;
    const cntRun = all.filter((p) => ["queued", "running", "preparing", "processing", "review"].includes(p.status)).length;
    const cntErr = all.filter((p) => p.status === "error").length;

    return `
      <section class="page-head">
        <div>
          <h1>Проекты</h1>
          <p>Вся библиотека нарезок с быстрым предпросмотром, поиском и переименованием.</p>
        </div>
        <button class="btn-primary" id="libNewBtn" type="button" style="display:inline-flex;align-items:center;gap:7px">${SVG.plus}<span>Создать проект</span></button>
      </section>

      <div class="lib-toolbar">
        <div class="filter-pills">
          <button class="filter-pill ${ui.libFilter === "all" ? "active" : ""}" data-lib-filter="all" type="button">Все (${all.length})</button>
          <button class="filter-pill ${ui.libFilter === "done" ? "active" : ""}" data-lib-filter="done" type="button">Готовые (${cntDone})</button>
          <button class="filter-pill ${ui.libFilter === "running" ? "active" : ""}" data-lib-filter="running" type="button">В работе (${cntRun})</button>
          <button class="filter-pill ${ui.libFilter === "error" ? "active" : ""}" data-lib-filter="error" type="button">Ошибки (${cntErr})</button>
        </div>
        <div class="lib-search">
          <input id="libSearchInput" type="search" value="${esc(ui.libQuery)}" placeholder="Поиск проекта…" />
          <button class="mini-chip ${ui.libView === "grid" ? "active" : ""}" data-lib-view="grid" type="button">Сетка</button>
          <button class="mini-chip ${ui.libView === "list" ? "active" : ""}" data-lib-view="list" type="button">Список</button>
        </div>
      </div>

      <div id="libContent">${projectsContentHTML()}</div>
    `;
  }

  function bindProjectsContent() {
    $$("[data-sel-pid]").forEach((card) => {
      card.addEventListener("click", () => {
        ui.selectedPid = card.dataset.selPid;
        const box = $("#libContent");
        if (box) { box.innerHTML = projectsContentHTML(); bindProjectsContent(); }
      });
      card.addEventListener("dblclick", () => openProject(card.dataset.selPid));
    });
    const sel = state.projects.find((p) => p.id === ui.selectedPid);
    $("#inspOpenBtn")?.addEventListener("click", () => sel && openProject(sel.id));
    $("#inspRenameBtn")?.addEventListener("click", () => sel && renameProject(sel));
    $("#inspDeleteBtn")?.addEventListener("click", async () => {
      if (!sel) return;
      if (!confirm(`Удалить проект «${sel.title || sel.url}» и все его клипы?`)) return;
      try {
        await api(`/api/projects/${sel.id}`, { method: "DELETE" });
        toast("Проект удалён");
        ui.selectedPid = null;
        await loadProjects();
        renderNavView(true);
      } catch (err) { toast(err.message, "err"); }
    });
  }

  function bindProjectsLibrary() {
    $("#libNewBtn")?.addEventListener("click", () => navigate("new"));
    $$("[data-lib-filter]").forEach((b) => {
      b.addEventListener("click", () => { ui.libFilter = b.dataset.libFilter; renderNavView(true); });
    });
    $$("[data-lib-view]").forEach((b) => {
      b.addEventListener("click", () => { ui.libView = b.dataset.libView; renderNavView(true); });
    });
    $("#libSearchInput")?.addEventListener("input", (e) => {
      ui.libQuery = e.target.value;
      const box = $("#libContent");
      if (box) { box.innerHTML = projectsContentHTML(); bindProjectsContent(); }
    });
    bindProjectsContent();
  }

  function renameProject(project) {
    if (!project) return;
    const modal = $("#modal");
    modal.classList.remove("hidden");
    modal.innerHTML = `
      <div class="modal-backdrop" data-close></div>
      <div class="modal-panel" style="max-width:460px">
        <div class="modal-head">
          <h3>Переименовать проект</h3>
          <button class="modal-close" id="renClose" type="button">×</button>
        </div>
        <div style="margin:14px 0">
          <input id="renInput" type="text" value="${esc(project.title || "")}" maxlength="160" style="width:100%;height:42px;padding:0 13px;border-radius:11px;background:rgba(255,255,255,0.06);border:1px solid var(--hairline)" />
        </div>
        <div style="display:flex;justify-content:flex-end;gap:8px">
          <button class="btn-ghost" id="renCancel" type="button">Отмена</button>
          <button class="btn-primary" id="renSave" type="button">Сохранить</button>
        </div>
      </div>
    `;
    const close = () => closeModal();
    $("#renClose")?.addEventListener("click", close);
    $("#renCancel")?.addEventListener("click", close);
    const save = async () => {
      const title = ($("#renInput")?.value || "").trim();
      if (!title) { toast("Введите название проекта", "err"); return; }
      try {
        await api(`/api/projects/${project.id}`, { method: "PATCH", body: JSON.stringify({ title }) });
        toast("Проект переименован");
        close();
        await loadProjects();
        if (state.current === project.id) await loadDetail(true);
        else renderNavView(true);
      } catch (err) { toast(err.message, "err"); }
    };
    $("#renSave")?.addEventListener("click", save);
    $("#renInput")?.addEventListener("keydown", (e) => { if (e.key === "Enter") save(); });
    $("#renInput")?.focus();
  }

  /* ---------------- 4. Queue (Очередь) ---------------- */

  function queueHTML() {
    const active = state.projects.filter((p) => ["queued", "running", "preparing", "processing"].includes(p.status));
    const finished = state.projects.filter((p) => !["queued", "running", "preparing", "processing"].includes(p.status)).slice(0, 10);

    return `
      <section class="page-head">
        <div>
          <h1>Очередь обработки</h1>
          <p>Отслеживание активных задач рендера, загрузок и завершённых проектов.</p>
        </div>
        <button class="btn-ghost" id="queueRefreshBtn" type="button">Обновить</button>
      </section>

      <div class="studio-card" style="margin-bottom:18px">
        <div class="card-title-row">
          <h2>В работе (${active.length})</h2>
        </div>
        ${active.length ? `<div class="queue-list">
          ${active.map((p) => `
            <div class="queue-item">
              <div class="queue-top">
                <div style="min-width:0">
                  <b style="font-size:15px">${esc(p.title || p.url)}</b>
                  <div class="hint">${esc(p.stage || "Обработка…")}</div>
                </div>
                <div style="display:flex;gap:8px;align-items:center">
                  <b>${Math.round(p.progress || 0)}%</b>
                  <button class="btn-ghost" data-q-open="${p.id}" type="button" style="padding:6px 11px;font-size:12px">Открыть</button>
                  <button class="btn-ghost danger" data-q-cancel="${p.id}" type="button" style="padding:6px 11px;font-size:12px">Отменить</button>
                </div>
              </div>
              <div class="queue-bar"><i style="width:${Math.max(4, Math.round(p.progress || 0))}%"></i></div>
            </div>
          `).join("")}
        </div>` : `<div class="hint" style="padding:12px 0">Сейчас очередь пуста.</div>`}
      </div>

      <div class="studio-card">
        <div class="card-title-row"><h2>Недавно завершённые</h2></div>
        ${finished.length ? `<div class="recent-list">
          ${finished.map((p) => {
            const st = statusInfo(p.status);
            return `<div class="recent-row" data-q-open="${p.id}">
              <div class="recent-thumb">${p.thumb_url ? `<img src="${esc(p.thumb_url)}" alt="" loading="lazy" />` : "—"}</div>
              <div class="recent-info">
                <div class="recent-title">${esc(p.title || p.url)}</div>
                <div class="recent-meta">
                  <span>${Number(p.clips_count ?? 0)} ${plural(Number(p.clips_count ?? 0), "клип", "клипа", "клипов")}</span>
                  <span>${esc(p.error ? p.error.slice(0, 70) : (p.stage || "Завершено"))}</span>
                </div>
              </div>
              <span class="status-pill ${st.cls}">${esc(st.text)}</span>
            </div>`;
          }).join("")}
        </div>` : `<div class="hint">История пока пуста.</div>`}
      </div>
    `;
  }

  function bindQueue() {
    $("#queueRefreshBtn")?.addEventListener("click", async () => { await loadProjects(); renderNavView(true); });
    $$("[data-q-open]").forEach((el) => el.addEventListener("click", () => openProject(el.dataset.qOpen)));
    $$("[data-q-cancel]").forEach((el) => {
      el.addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          await api(`/api/projects/${el.dataset.qCancel}/cancel`, { method: "POST" });
          toast("Задача отменена");
          await loadProjects();
          renderNavView(true);
        } catch (err) { toast(err.message, "err"); }
      });
    });
  }

  /* ---------------- 5. Full-Page Settings (Темы, 2-цветная палитра, Whisper, Рендер, ИИ, Диск) ---------------- */

  async function loadSettingsViewData() {
    try {
      const [conf, whisper, storage] = await Promise.all([
        api("/api/settings"),
        api("/api/whisper/models"),
        api("/api/storage"),
        loadProAssetsData(),
      ]);
      state.settingsData = conf;
      state.whisperData = whisper;
      ui.storage = storage;
      applyTheme(conf.theme || "obsidian", conf.palette_a || ui.paletteA, conf.palette_b || ui.paletteB, false);
    } catch (e) { console.error(e); }
  }

  function settingsPageHTML() {
    const conf = state.settingsData || {};
    const wData = state.whisperData || { active: "small", cuda: false, models: [] };
    const st = ui.storage || {};
    const rq = conf.render_quality || "balanced";
    const enc = conf.encoder || "auto";

    return `
      <section class="page-head">
        <div>
          <h1>Настройки KrlzCut</h1>
          <p>Темы, 2-цветная палитра, локальные модели Whisper, кодировщик и хранилище.</p>
        </div>
        <button class="btn-ghost" id="setDiagBtn" type="button">Журнал диагностики</button>
      </section>

      <div class="settings-grid">
        <div class="studio-card settings-span-2">
          <div class="card-title-row">
            <h2>Оформление и цветовая палитра</h2>
            <span class="hint">Применяется мгновенно</span>
          </div>
          <div class="theme-grid">
            ${THEMES.map((t) => {
              const g = t.key === "custom"
                ? `linear-gradient(135deg, ${ui.paletteA}, ${ui.paletteB})`
                : `linear-gradient(135deg, ${t.a}, ${t.b})`;
              return `<button class="theme-card ${ui.theme === t.key ? "active" : ""}" data-set-theme="${t.key}" type="button">
                <div class="theme-swatch-bar" style="background:${g}"></div>
                <b>${esc(t.name)}</b>
                <small>${esc(t.sub)}</small>
              </button>`;
            }).join("")}
          </div>

          <div class="palette-box">
            <b style="font-size:13px">Своя 2-цветная палитра:</b>
            <label class="color-pick-field">
              <span>Цвет 1</span>
              <input type="color" id="palAPicker" value="${esc(ui.paletteA)}" />
              <input type="text" id="palAHex" value="${esc(ui.paletteA)}" maxlength="7" />
            </label>
            <label class="color-pick-field">
              <span>Цвет 2</span>
              <input type="color" id="palBPicker" value="${esc(ui.paletteB)}" />
              <input type="text" id="palBHex" value="${esc(ui.paletteB)}" maxlength="7" />
            </label>
            <div class="chip-row" style="margin-left:auto">
              ${PALETTE_SWATCHES.map(([a, b, lbl]) => `<button class="mini-chip" data-pal-pair="${a},${b}" type="button" style="border-left:4px solid ${a};border-right:4px solid ${b}">${lbl}</button>`).join("")}
            </div>
          </div>
        </div>

        <div class="studio-card settings-span-2">
          <div class="card-title-row">
            <h2>Модели распознавания речи (Whisper)</h2>
            <span class="status-pill ${wData.cuda ? "done" : ""}">${wData.cuda ? "Ускорение GPU (CUDA)" : "Режим CPU"}</span>
          </div>
          <div class="whisper-grid">
            ${(wData.models || []).map((m) => `
              <div class="whisper-card ${m.active ? "active" : ""}">
                <div class="whisper-card-head">
                  <b>${esc(m.name)}</b>
                  ${m.active ? `<span class="status-pill done">Активна</span>` : m.downloaded ? `<span class="status-pill">Скачана</span>` : `<span class="status-pill">Не скачана</span>`}
                </div>
                <div class="whisper-meta">
                  <span>${esc(m.size_label)}</span>
                  <span>${esc(m.speed)}</span>
                  <span>Точность: ${esc(m.accuracy)}</span>
                </div>
                <p>${esc(m.desc)}</p>
                ${m.error ? `<div style="font-size:11.5px;color:#fca5a5">${esc(m.error)}</div>` : ""}
                <div class="whisper-actions">
                  ${m.downloading
                    ? `<button class="btn-ghost" disabled type="button" style="flex:1">Скачивается…</button>`
                    : m.downloaded
                      ? (m.active
                          ? `<button class="btn-ghost" disabled type="button" style="flex:1">Используется сейчас</button>`
                          : `<button class="btn-primary" data-w-select="${m.key}" type="button" style="flex:1">Выбрать</button>`)
                      : `<button class="btn-primary" data-w-dl="${m.key}" type="button" style="flex:1">Скачать (${esc(m.size_label)})</button>`
                  }
                  ${m.can_delete && !m.active ? `<button class="btn-ghost danger" data-w-del="${m.key}" type="button" title="Удалить с диска">Удалить</button>` : ""}
                </div>
              </div>
            `).join("")}
          </div>
        </div>

        <div class="studio-card">
          <div class="card-title-row"><h3>Обработка и рендер</h3></div>
          <div style="display:flex;flex-direction:column;gap:14px">
            <div>
              <div class="hint" style="margin-bottom:6px">Качество рендера</div>
              <div class="chip-row">
                ${[["fast", "Быстро"], ["balanced", "Сбалансировано"], ["high", "Высокое"]].map(([k, lbl]) => `<button class="mini-chip ${rq === k ? "active" : ""}" data-set-rq="${k}" type="button">${lbl}</button>`).join("")}
              </div>
            </div>
            <div>
              <div class="hint" style="margin-bottom:6px">Кодировщик видео</div>
              <div class="chip-row">
                ${[["auto", "Авто"], ["gpu", "Видеокарта (GPU)"], ["cpu", "Процессор (CPU)"]].map(([k, lbl]) => `<button class="mini-chip ${enc === k ? "active" : ""}" data-set-enc="${k}" type="button">${lbl}</button>`).join("")}
              </div>
            </div>
            <div>
              <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px">
                <span>Мощность рендера</span><b id="setPowerVal">${conf.power ?? 65}%</b>
              </div>
              <input id="setPowerRange" type="range" min="0" max="100" step="5" value="${conf.power ?? 65}" style="width:100%" />
            </div>
            <div>
              <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px">
                <span>Лимит нагрузки CPU (Windows)</span><b id="setCpuVal">${conf.cpu_limit ?? 100}%</b>
              </div>
              <input id="setCpuRange" type="range" min="25" max="100" step="5" value="${conf.cpu_limit ?? 100}" style="width:100%" />
            </div>
          </div>
        </div>

        <div class="studio-card">
          <div class="card-title-row"><h3>ИИ-модель (LLM), папки и диск</h3></div>
          <div style="display:flex;flex-direction:column;gap:12px">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.035);border:1px solid var(--separator)">
              <div>
                <b style="font-size:13.5px">Настройка LLM / API-ключа и папок</b>
                <div class="hint">Провайдер: ${esc(conf.ai?.provider || "выкл")} · Модель: ${esc(conf.ai?.model || "не выбрана")}</div>
              </div>
              <button class="btn-ghost" id="setAdvancedBtn" type="button">Открыть</button>
            </div>

            <div style="padding:12px;border-radius:12px;background:rgba(255,255,255,0.035);border:1px solid var(--separator)">
              <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:8px">
                <span>Занято на диске</span><b>${fmtBytes(st.total_bytes)}</b>
              </div>
              <div class="hint" style="margin-bottom:10px">Исходники: ${fmtBytes(st.sources_bytes)} · Клипы: ${fmtBytes(st.clips_bytes)} · Кэш и временные: ${fmtBytes((st.temp_bytes || 0) + (st.cache_bytes || 0))}</div>
              <div style="display:flex;gap:8px;flex-wrap:wrap">
                <button class="btn-ghost" id="setCleanCacheBtn" type="button">Очистить кэш</button>
                <button class="btn-ghost danger" id="setCleanAllBtn" type="button">Очистить кэш и исходники</button>
              </div>
            </div>
          </div>
        </div>

        <div class="studio-card settings-span-2">
          <div class="card-title-row">
            <h2>Brand Kits (Профили каналов) и брендовые ассеты</h2>
            <span class="hint">Водяной знак, интро/аутро (до 15 с) и библиотека BGM</span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;padding-top:12px;border-top:1px solid var(--border)">
            <div style="display:flex;flex-direction:column;gap:10px">
              <b style="font-size:13px">Сохранённые Brand Kits (${ui.profiles.length})</b>
              ${(() => {
                const editKit = ui.editingKitId ? ui.profiles.find((p) => p.id === ui.editingKitId) : null;
                if (ui.editingKitId && !editKit) ui.editingKitId = "";
                const editWmId = editKit?.config?.watermark?.enabled ? (editKit.config.watermark.asset_id || "") : "";
                const editWmPos = editKit?.config?.watermark?.position || "top-right";
                const editIntroId = editKit?.config?.intro_asset_id || "";
                const editOutroId = editKit?.config?.outro_asset_id || "";
                const listHtml = ui.profiles.length ? `<div style="display:flex;flex-direction:column">` + ui.profiles.map((k) => {
                  const isDef = conf.default_profile_id === k.id;
                  const isEd = Boolean(editKit && editKit.id === k.id);
                  return `
                  <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 0;border-top:1px solid var(--border)">
                    <div style="min-width:0">
                      <div style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(k.name)} ${isDef ? `<span class="status-pill done" style="font-size:10px;padding:1px 6px">По умолчанию</span>` : ""}</div>
                      <div class="hint" style="font-size:11.5px">${esc(k.config?.aspect || "9:16")} · ${esc(k.config?.sub_font || "montserrat")}${k.config?.watermark?.enabled ? " · логотип" : ""}${k.config?.intro_asset_id ? " · интро" : ""}${k.config?.outro_asset_id ? " · аутро" : ""}${k.config?.bgm?.enabled ? " · BGM" : ""}</div>
                    </div>
                    <div style="display:flex;gap:6px;flex:none">
                      <button class="mini-chip ${isDef ? "active" : ""}" data-kit-default="${esc(k.id)}" data-kit-is-default="${isDef ? "1" : ""}" type="button" title="${isDef ? "Снять профиль по умолчанию" : "Использовать по умолчанию для бота"}">${isDef ? "Снять" : "По умолч."}</button>
                      <button class="mini-chip ${isEd ? "active" : ""}" data-kit-edit="${esc(k.id)}" type="button" title="Изменить название, логотип, интро/аутро или настройки">${isEd ? "Редактируется" : "Изменить"}</button>
                      <button class="mini-chip" data-kit-del="${esc(k.id)}" type="button" style="color:#fca5a5">Удалить</button>
                    </div>
                  </div>`;
                }).join("") + `</div>` : `<div class="hint">Профилей пока нет — создайте профиль ниже из текущих настроек нового проекта.</div>`;
                return `${listHtml}
              <div style="display:flex;flex-direction:column;gap:8px;padding-top:10px;border-top:1px solid var(--border)">
                ${editKit ? `<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap">
                  <span style="font-size:12px;font-weight:600;color:var(--text)">Редактирование: ${esc(editKit.name)}</span>
                  <label style="display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);cursor:pointer"><input type="checkbox" id="kitSyncOpts" /> Подтянуть настройки «Нового проекта»</label>
                </div>` : ""}
                <input id="kitNewName" type="text" value="${esc(editKit ? editKit.name : "")}" placeholder="Название Brand Kit (например: Подкаст-канал)" style="height:36px;padding:0 11px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:13px" />
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
                  <select id="kitWmSel" style="height:34px;padding:0 8px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12px">
                    <option value="" ${!editWmId ? "selected" : ""}>Водяной знак: нет</option>
                    ${ui.brandAssets.filter((a) => a.kind === "watermark").map((a) => `<option value="${esc(a.id)}" ${editWmId === a.id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}
                  </select>
                  <select id="kitWmPos" style="height:34px;padding:0 8px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12px">
                    <option value="top-right" ${editWmPos === "top-right" ? "selected" : ""}>Угол: сверху справа</option>
                    <option value="top-left" ${editWmPos === "top-left" ? "selected" : ""}>Угол: сверху слева</option>
                    <option value="bottom-right" ${editWmPos === "bottom-right" ? "selected" : ""}>Угол: снизу справа</option>
                    <option value="bottom-left" ${editWmPos === "bottom-left" ? "selected" : ""}>Угол: снизу слева</option>
                  </select>
                  <select id="kitIntroSel" style="height:34px;padding:0 8px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12px">
                    <option value="" ${!editIntroId ? "selected" : ""}>Интро: нет</option>
                    ${ui.brandAssets.filter((a) => a.kind === "intro" || a.kind === "outro").map((a) => `<option value="${esc(a.id)}" ${editIntroId === a.id ? "selected" : ""}>${esc(a.name)} (${a.duration} с)</option>`).join("")}
                  </select>
                  <select id="kitOutroSel" style="height:34px;padding:0 8px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12px">
                    <option value="" ${!editOutroId ? "selected" : ""}>Аутро: нет</option>
                    ${ui.brandAssets.filter((a) => a.kind === "outro" || a.kind === "intro").map((a) => `<option value="${esc(a.id)}" ${editOutroId === a.id ? "selected" : ""}>${esc(a.name)} (${a.duration} с)</option>`).join("")}
                  </select>
                </div>
                <div style="display:flex;gap:8px">
                  <button class="btn-primary" id="kitCreateBtn" type="button" style="flex:1;height:36px">${editKit ? "Сохранить изменения" : "Сохранить Brand Kit"}</button>
                  ${editKit ? `<button class="btn-ghost" id="kitCancelEditBtn" type="button" style="height:36px">Отмена</button>` : ""}
                </div>
              </div>`;
              })()}
            </div>

            <div style="display:flex;flex-direction:column;gap:10px">
              <b style="font-size:13px">Ассеты и фоновая музыка (BGM)</b>
              <div style="display:flex;gap:8px;flex-wrap:wrap">
                <button class="mini-chip" id="upWmBtn" type="button">+ Логотип (PNG/WebP)</button>
                <button class="mini-chip" id="upIntroBtn" type="button">+ Интро (≤ 15 с)</button>
                <button class="mini-chip" id="upOutroBtn" type="button">+ Аутро (≤ 15 с)</button>
                <button class="mini-chip" id="upBgmBtn" type="button">+ Трек BGM</button>
                <input id="upWmFile" type="file" accept=".png,.webp,image/png,image/webp" class="hidden" />
                <input id="upIntroFile" type="file" accept=".mp4,.mov,.webm,video/*" class="hidden" />
                <input id="upOutroFile" type="file" accept=".mp4,.mov,.webm,video/*" class="hidden" />
                <input id="upBgmFile" type="file" accept=".mp3,.wav,.m4a,.ogg,.flac,audio/*" class="hidden" />
              </div>
              <div style="display:flex;flex-direction:column;max-height:210px;overflow:auto">
                ${ui.brandAssets.map((a) => `
                  <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 0;border-top:1px solid var(--border);font-size:12px">
                    <span><b>[${esc(a.kind)}]</b> ${esc(a.name)} ${a.duration ? `· ${a.duration} с` : `${a.width}×${a.height}`}</span>
                    <button class="mini-chip" data-del-asset="${esc(a.id)}" type="button" style="color:#fca5a5">Удалить</button>
                  </div>
                `).join("")}
                ${ui.bgmTracks.map((t) => `
                  <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 0;border-top:1px solid var(--border);font-size:12px">
                    <span><b>[BGM]</b> ${esc(t.name)} · ${t.duration} с</span>
                    <button class="mini-chip" data-del-bgm="${esc(t.id)}" type="button" style="color:#fca5a5">Удалить</button>
                  </div>
                `).join("")}
                ${!ui.brandAssets.length && !ui.bgmTracks.length ? `<div class="hint" style="padding-top:6px">Ассеты и треки BGM ещё не загружены.</div>` : ""}
              </div>
            </div>
          </div>
        </div>

        <div class="studio-card settings-span-2">
          <div class="card-title-row">
            <h2>Telegram / Discord бот одобрения</h2>
            <span class="status-pill ${(ui.botStatus?.telegram?.running || ui.botStatus?.discord?.running) ? "done" : ""}">${(ui.botStatus?.telegram?.running || ui.botStatus?.discord?.running) ? "Активен" : "Остановлен"}</span>
          </div>
          <div class="hint" style="margin-bottom:12px">Локальный исходящий клиент без проброса портов. Доступ строго по белому списку (пустой список блокирует всех пользователей).</div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;padding-top:12px;border-top:1px solid var(--border)">
            <div style="display:flex;flex-direction:column;gap:8px">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <label style="display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:600;cursor:pointer">
                  <input type="checkbox" id="botTgOn" ${conf.tg_enabled ? "checked" : ""} /> Telegram Bot (Long Polling)
                </label>
                <span class="hint">${conf.tg_token_set ? "Токен сохранён" : "Токен не задан"}</span>
              </div>
              <div style="display:flex;gap:6px">
                <input id="botTgToken" type="password" placeholder="${conf.tg_token_set ? "•••••••• (оставьте пустым, чтобы не менять)" : "Bot Token от @BotFather"}" style="flex:1;height:34px;padding:0 10px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12.5px" />
                ${conf.tg_token_set ? `<button class="mini-chip" id="botTgClear" type="button">Очистить</button>` : ""}
              </div>
              <input id="botTgAllowed" type="text" value="${esc(conf.tg_allowed_users || "")}" placeholder="Разрешённые User ID или @username (через запятую)" style="height:34px;padding:0 10px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12.5px" />
              <input id="botTgChatId" type="text" value="${esc(conf.tg_chat_id || "")}" placeholder="Chat ID (необязательно — определится после /start)" style="height:34px;padding:0 10px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12.5px" />
              <div style="display:flex;gap:8px;margin-top:2px">
                <button class="btn-ghost" id="botTgTest" type="button" style="height:32px;font-size:12px">Проверить Telegram</button>
              </div>
            </div>

            <div style="display:flex;flex-direction:column;gap:8px">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <label style="display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:600;cursor:pointer">
                  <input type="checkbox" id="botDcOn" ${conf.dc_enabled ? "checked" : ""} /> Discord Bot (Gateway v10)
                </label>
                <span class="hint">${conf.dc_token_set ? "Токен сохранён" : "Токен не задан"}</span>
              </div>
              <div style="display:flex;gap:6px">
                <input id="botDcToken" type="password" placeholder="${conf.dc_token_set ? "•••••••• (оставьте пустым, чтобы не менять)" : "Discord Bot Token"}" style="flex:1;height:34px;padding:0 10px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12.5px" />
                ${conf.dc_token_set ? `<button class="mini-chip" id="botDcClear" type="button">Очистить</button>` : ""}
              </div>
              <input id="botDcChannel" type="text" value="${esc(conf.dc_channel_id || "")}" placeholder="Channel ID для отправки превью" style="height:34px;padding:0 10px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12.5px" />
              <input id="botDcAllowed" type="text" value="${esc(conf.dc_allowed_users || "")}" placeholder="Разрешённые Discord User ID или @username" style="height:34px;padding:0 10px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12.5px" />
              <div style="display:flex;gap:8px;margin-top:2px">
                <button class="btn-ghost" id="botDcTest" type="button" style="height:32px;font-size:12px">Проверить Discord</button>
              </div>
            </div>
          </div>
          <div style="display:flex;justify-content:flex-end;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">
            <button class="btn-primary" id="botSaveBtn" type="button">Сохранить настройки ботов</button>
          </div>
        </div>
      </div>
    `;
  }

  function bindSettingsPage() {
    $$("[data-set-theme]").forEach((btn) => {
      btn.addEventListener("click", () => {
        applyTheme(btn.dataset.setTheme, ui.paletteA, ui.paletteB, true);
        renderNavView(true);
      });
    });

    const onPalChange = (a, b) => {
      applyTheme("custom", a, b, true);
      if ($("#palAPicker")) $("#palAPicker").value = ui.paletteA;
      if ($("#palAHex")) $("#palAHex").value = ui.paletteA;
      if ($("#palBPicker")) $("#palBPicker").value = ui.paletteB;
      if ($("#palBHex")) $("#palBHex").value = ui.paletteB;
      $$("[data-set-theme]").forEach((el) => el.classList.toggle("active", el.dataset.setTheme === "custom"));
      const customSwatch = document.querySelector('[data-set-theme="custom"] .theme-swatch-bar');
      if (customSwatch) customSwatch.style.background = `linear-gradient(135deg, ${ui.paletteA}, ${ui.paletteB})`;
    };

    $("#palAPicker")?.addEventListener("input", (e) => onPalChange(e.target.value, ui.paletteB));
    $("#palBPicker")?.addEventListener("input", (e) => onPalChange(ui.paletteA, e.target.value));
    $("#palAHex")?.addEventListener("change", (e) => onPalChange(e.target.value.trim(), ui.paletteB));
    $("#palBHex")?.addEventListener("change", (e) => onPalChange(ui.paletteA, e.target.value.trim()));
    $$("[data-pal-pair]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [a, b] = btn.dataset.palPair.split(",");
        onPalChange(a, b);
      });
    });

    $$("[data-w-dl]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await api(`/api/whisper/models/${btn.dataset.wDl}/download`, { method: "POST" });
          toast("Скачивание модели Whisper запущено…");
          await loadSettingsViewData();
          renderNavView(true);
          startWhisperPoll();
        } catch (err) { toast(err.message, "err"); }
      });
    });
    $$("[data-w-select]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          state.whisperData = await api(`/api/whisper/models/${btn.dataset.wSelect}/select`, { method: "POST" });
          toast("Активная модель Whisper обновлена");
          renderNavView(true);
        } catch (err) { toast(err.message, "err"); }
      });
    });
    $$("[data-w-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Удалить скачанную модель Whisper с диска?")) return;
        try {
          state.whisperData = await api(`/api/whisper/models/${btn.dataset.wDel}`, { method: "DELETE" });
          toast("Модель удалена");
          renderNavView(true);
        } catch (err) { toast(err.message, "err"); }
      });
    });

    $$("[data-set-rq]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          state.settingsData = await api("/api/settings", { method: "POST", body: JSON.stringify({ render_quality: btn.dataset.setRq }) });
          toast("Качество рендера сохранено");
          renderNavView(true);
        } catch (err) { toast(err.message, "err"); }
      });
    });
    $$("[data-set-enc]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          state.settingsData = await api("/api/settings", { method: "POST", body: JSON.stringify({ encoder: btn.dataset.setEnc }) });
          if (state.settingsData.encoder_warning) toast(state.settingsData.encoder_warning, "err");
          else toast("Кодировщик обновлён");
          renderNavView(true);
        } catch (err) { toast(err.message, "err"); }
      });
    });
    $("#setPowerRange")?.addEventListener("input", (e) => {
      if ($("#setPowerVal")) $("#setPowerVal").textContent = `${Number(e.target.value)}%`;
    });
    $("#setPowerRange")?.addEventListener("change", async (e) => {
      const val = Number(e.target.value);
      if ($("#setPowerVal")) $("#setPowerVal").textContent = `${val}%`;
      try {
        state.settingsData = await api("/api/settings", { method: "POST", body: JSON.stringify({ power: val }) });
        toast(`Мощность: ${val}%`);
      } catch (err) { toast(err.message, "err"); }
    });
    $("#setCpuRange")?.addEventListener("input", (e) => {
      if ($("#setCpuVal")) $("#setCpuVal").textContent = `${Number(e.target.value)}%`;
    });
    $("#setCpuRange")?.addEventListener("change", async (e) => {
      const val = Number(e.target.value);
      if ($("#setCpuVal")) $("#setCpuVal").textContent = `${val}%`;
      try {
        state.settingsData = await api("/api/settings", { method: "POST", body: JSON.stringify({ cpu_limit: val }) });
        toast(`Лимит CPU: ${val}%`);
      } catch (err) { toast(err.message, "err"); }
    });

    $("#setAdvancedBtn")?.addEventListener("click", () => { if (typeof openSettings === "function") openSettings(); });
    $("#setDiagBtn")?.addEventListener("click", async () => {
      try {
        const d = await api("/api/diagnostics?tail=80");
        const modal = $("#modal");
        modal.classList.remove("hidden");
        modal.innerHTML = `
          <div class="modal-backdrop" data-close></div>
          <div class="modal-panel" style="max-width:760px">
            <div class="modal-head">
              <h3>Журнал диагностики KrlzCut</h3>
              <button class="modal-close" id="diagClose" type="button">×</button>
            </div>
            <div class="hint" style="margin:8px 0">${esc(d.summary || "Лог приложения")} · ${esc(d.log_path || "")}</div>
            <pre style="max-height:55vh;overflow:auto;padding:12px;border-radius:12px;background:#07080d;border:1px solid var(--separator);font-size:12px;white-space:pre-wrap">${esc((d.tail || []).join("\n") || "Журнал пуст")}</pre>
            <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px">
              <button class="btn-ghost" id="diagCopy" type="button">Скопировать лог</button>
              <button class="btn-primary" id="diagOk" type="button">Закрыть</button>
            </div>
          </div>
        `;
        $("#diagClose")?.addEventListener("click", closeModal);
        $("#diagOk")?.addEventListener("click", closeModal);
        $("#diagCopy")?.addEventListener("click", () => {
          navigator.clipboard?.writeText((d.tail || []).join("\n")).then(() => toast("Лог скопирован"));
        });
      } catch (err) { toast(err.message, "err"); }
    });
    $("#setCleanCacheBtn")?.addEventListener("click", async () => {
      try {
        const res = await api("/api/storage/cleanup", { method: "POST", body: JSON.stringify({ include_sources: false }) });
        toast(`Освобождено ${fmtBytes(res.freed_bytes)}`);
        await loadSettingsViewData();
        renderNavView(true);
      } catch (err) { toast(err.message, "err"); }
    });
    $("#setCleanAllBtn")?.addEventListener("click", async () => {
      if (!confirm("Удалить временный кэш и исходники готовых проектов? Готовые клипы останутся.")) return;
      try {
        const res = await api("/api/storage/cleanup", { method: "POST", body: JSON.stringify({ include_sources: true }) });
        toast(`Освобождено ${fmtBytes(res.freed_bytes)}`);
        await loadSettingsViewData();
        renderNavView(true);
      } catch (err) { toast(err.message, "err"); }
    });

    if ((state.whisperData?.models || []).some((m) => m.downloading)) {
      startWhisperPoll();
    }

    // Brand Kits & Assets bindings
    $("#kitCreateBtn")?.addEventListener("click", async () => {
      const name = ($("#kitNewName")?.value || "").trim();
      if (!name) { toast("Введите название профиля", "err"); return; }
      const editKit = ui.editingKitId ? ui.profiles.find((p) => p.id === ui.editingKitId) : null;
      const wmId = $("#kitWmSel")?.value || "";
      const wmPos = $("#kitWmPos")?.value || "top-right";
      const introId = $("#kitIntroSel")?.value || "";
      const outroId = $("#kitOutroSel")?.value || "";
      if (editKit) {
        const cfg = $("#kitSyncOpts")?.checked ? currentOptsAsKitConfig() : { ...(editKit.config || {}) };
        const prevWm = editKit.config?.watermark || {};
        cfg.watermark = wmId
          ? { enabled: true, asset_id: wmId, position: wmPos, scale: prevWm.scale ?? 0.16, opacity: prevWm.opacity ?? 0.85, margin: prevWm.margin ?? 36 }
          : null;
        cfg.intro_asset_id = introId;
        cfg.outro_asset_id = outroId;
        try {
          const updated = await api(`/api/profiles/${encodeURIComponent(editKit.id)}`, {
            method: "PATCH",
            body: JSON.stringify({ name, config: cfg }),
          });
          ui.editingKitId = "";
          if (state.opts.profileId === editKit.id && updated) applyBrandKitToOpts(updated);
          toast(`Brand Kit «${name}» обновлён`);
          await loadSettingsViewData();
          renderNavView(true);
        } catch (err) { toast(err.message, "err"); }
        return;
      }
      const cfg = currentOptsAsKitConfig();
      cfg.watermark = wmId ? { enabled: true, asset_id: wmId, position: wmPos, scale: 0.16, opacity: 0.85, margin: 36 } : null;
      cfg.intro_asset_id = introId;
      cfg.outro_asset_id = outroId;
      try {
        await api("/api/profiles", { method: "POST", body: JSON.stringify({ name, config: cfg }) });
        toast(`Brand Kit «${name}» сохранён`);
        await loadSettingsViewData();
        renderNavView(true);
      } catch (err) { toast(err.message, "err"); }
    });
    $("#kitCancelEditBtn")?.addEventListener("click", () => {
      ui.editingKitId = "";
      renderNavView(true);
    });
    $$("[data-kit-default]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const nextId = btn.dataset.kitIsDefault === "1" ? "" : btn.dataset.kitDefault;
        try {
          await api("/api/settings", { method: "POST", body: JSON.stringify({ default_profile_id: nextId }) });
          toast(nextId ? "Профиль по умолчанию обновлён" : "Профиль по умолчанию снят");
          await loadSettingsViewData();
          renderNavView(true);
        } catch (err) { toast(err.message, "err"); }
      });
    });
    $$("[data-kit-edit]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const kid = btn.dataset.kitEdit || "";
        ui.editingKitId = ui.editingKitId === kid ? "" : kid;
        renderNavView(true);
        if (ui.editingKitId) $("#kitNewName")?.focus();
      });
    });
    $$("[data-kit-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("Удалить этот Brand Kit?")) return;
        const kid = btn.dataset.kitDel;
        try {
          await api(`/api/profiles/${encodeURIComponent(kid)}`, { method: "DELETE" });
          if (ui.editingKitId === kid) ui.editingKitId = "";
          toast("Brand Kit удалён");
          await loadSettingsViewData();
          renderNavView(true);
        } catch (err) { toast(err.message, "err"); }
      });
    });

    const bindAssetUpload = (btnId, inputId, kind) => {
      $(btnId)?.addEventListener("click", () => $(inputId)?.click());
      $(inputId)?.addEventListener("change", async (e) => {
        const file = e.target.files?.[0];
        e.target.value = "";
        if (!file) return;
        try {
          const fd = new FormData();
          fd.append("kind", kind);
          fd.append("file", file);
          const added = await api("/api/brand-assets", { method: "POST", body: fd });
          toast(`Загружено: ${added.name}`);
          await loadSettingsViewData();
          renderNavView(true);
        } catch (err) { toast(err.message, "err"); }
      });
    };
    bindAssetUpload("#upWmBtn", "#upWmFile", "watermark");
    bindAssetUpload("#upIntroBtn", "#upIntroFile", "intro");
    bindAssetUpload("#upOutroBtn", "#upOutroFile", "outro");
    $("#upBgmBtn")?.addEventListener("click", () => $("#upBgmFile")?.click());
    $("#upBgmFile")?.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;
      try {
        const fd = new FormData();
        fd.append("file", file);
        const added = await api("/api/bgm", { method: "POST", body: fd });
        toast(`Трек BGM добавлен: ${added.name}`);
        await loadSettingsViewData();
        renderNavView(true);
      } catch (err) { toast(err.message, "err"); }
    });
    $$("[data-del-asset]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await api(`/api/brand-assets/${btn.dataset.delAsset}`, { method: "DELETE" });
          toast("Ассет удалён");
          await loadSettingsViewData();
          renderNavView(true);
        } catch (err) { toast(err.message, "err"); }
      });
    });
    $$("[data-del-bgm]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await api(`/api/bgm/${btn.dataset.delBgm}`, { method: "DELETE" });
          toast("Трек BGM удалён");
          await loadSettingsViewData();
          renderNavView(true);
        } catch (err) { toast(err.message, "err"); }
      });
    });

    // Telegram & Discord Bot settings bindings
    $("#botSaveBtn")?.addEventListener("click", async () => {
      const body = {
        tg_enabled: Boolean($("#botTgOn")?.checked),
        tg_allowed_users: ($("#botTgAllowed")?.value || "").trim(),
        tg_chat_id: ($("#botTgChatId")?.value || "").trim(),
        dc_enabled: Boolean($("#botDcOn")?.checked),
        dc_channel_id: ($("#botDcChannel")?.value || "").trim(),
        dc_allowed_users: ($("#botDcAllowed")?.value || "").trim(),
      };
      const tgTok = ($("#botTgToken")?.value || "").trim();
      const dcTok = ($("#botDcToken")?.value || "").trim();
      if (tgTok) body.tg_token = tgTok;
      if (dcTok) body.dc_token = dcTok;
      try {
        await api("/api/settings", { method: "POST", body: JSON.stringify(body) });
        toast("Настройки ботов сохранены");
        await loadSettingsViewData();
        renderNavView(true);
      } catch (err) { toast(err.message, "err"); }
    });
    $("#botTgClear")?.addEventListener("click", async () => {
      try {
        await api("/api/settings", { method: "POST", body: JSON.stringify({ clear_tg_token: true, tg_enabled: false }) });
        toast("Токен Telegram очищен");
        await loadSettingsViewData();
        renderNavView(true);
      } catch (err) { toast(err.message, "err"); }
    });
    $("#botDcClear")?.addEventListener("click", async () => {
      try {
        await api("/api/settings", { method: "POST", body: JSON.stringify({ clear_dc_token: true, dc_enabled: false }) });
        toast("Токен Discord очищен");
        await loadSettingsViewData();
        renderNavView(true);
      } catch (err) { toast(err.message, "err"); }
    });
    $("#botTgTest")?.addEventListener("click", async () => {
      try {
        const res = await api("/api/bots/test", { method: "POST", body: JSON.stringify({ platform: "telegram" }) });
        toast(`Telegram подключён: @${res.username || "bot"}`);
      } catch (err) { toast(err.message, "err"); }
    });
    $("#botDcTest")?.addEventListener("click", async () => {
      try {
        const res = await api("/api/bots/test", { method: "POST", body: JSON.stringify({ platform: "discord" }) });
        toast(`Discord подключён: ${res.username || "bot"}`);
      } catch (err) { toast(err.message, "err"); }
    });
  }

  function startWhisperPoll() {
    clearInterval(ui.whisperPoll);
    ui.whisperPoll = setInterval(async () => {
      if (state.nav !== "settings" || state.current) {
        clearInterval(ui.whisperPoll);
        return;
      }
      try {
        state.whisperData = await api("/api/whisper/models");
        renderNavView(true);
        if (!(state.whisperData.models || []).some((m) => m.downloading)) {
          clearInterval(ui.whisperPoll);
        }
      } catch (_) {}
    }, 2200);
  }

  function projectsSignature() {
    return (state.projects || [])
      .map((p) => `${p.id}:${p.status}:${Math.round(p.progress || 0)}:${p.stage || ""}:${p.clips_count ?? ""}`)
      .join("|");
  }

  function hasActiveProjects() {
    return (state.projects || []).some((p) =>
      ["queued", "running", "preparing", "processing"].includes(p.status)
    );
  }

  function stopActivePoll() {
    if (ui.activePoll) {
      clearTimeout(ui.activePoll);
      ui.activePoll = null;
    }
  }

  function syncActivePoll() {
    const onLiveView = !state.current && (state.nav === "queue" || state.nav === "dashboard");
    if (!onLiveView || !hasActiveProjects()) {
      stopActivePoll();
      return;
    }
    ui.activeSig = projectsSignature();
    if (ui.activePoll) return;
    const tick = async () => {
      ui.activePoll = null;
      if (state.current || (state.nav !== "queue" && state.nav !== "dashboard")) {
        return;
      }
      try {
        await loadProjects();
        const sig = projectsSignature();
        if (sig !== ui.activeSig) {
          ui.activeSig = sig;
          if (!state.current) renderNavView(true);
        }
      } catch (_) {}
      if (!state.current && (state.nav === "queue" || state.nav === "dashboard") && hasActiveProjects()) {
        ui.activePoll = setTimeout(tick, 2500);
      }
    };
    ui.activePoll = setTimeout(tick, 2500);
  }

  /* ---------------- Navigation & Boot ---------------- */

  async function navigate(navKey) {
    state.nav = navKey || "dashboard";
    state.current = null;
    state.detail = null;
    state.mainKey = "";
    clearTimeout(state.pollTimer);
    stopActivePoll();
    history.replaceState(null, "", location.pathname);
    renderSidebar();
    if (state.nav === "settings") {
      await loadSettingsViewData();
    } else if (state.nav === "new") {
      await loadProAssetsData();
    } else if (state.nav === "projects" || state.nav === "queue" || state.nav === "dashboard") {
      loadProjects().then(() => {
        if (!state.current) {
          renderNavView(true);
          syncActivePoll();
        }
      });
    }
    renderNavView(true);
  }

  function renderNavView(force) {
    const main = $("#main");
    if (!main || state.current) {
      stopActivePoll();
      return;
    }
    const key = `nav:${state.nav}`;
    if (!force && state.mainKey === key) return;
    state.mainKey = key;
    if (state.nav === "new") {
      main.innerHTML = newProjectHTML();
      bindNewProject();
    } else if (state.nav === "projects") {
      main.innerHTML = projectsLibraryHTML();
      bindProjectsLibrary();
    } else if (state.nav === "queue") {
      main.innerHTML = queueHTML();
      bindQueue();
    } else if (state.nav === "settings") {
      main.innerHTML = settingsPageHTML();
      bindSettingsPage();
    } else {
      main.innerHTML = dashboardHTML();
      bindDashboard();
    }
    syncActivePoll();
  }

  function init() {
    applyTheme(ui.theme, ui.paletteA, ui.paletteB, false);
    syncSettings();
    $$(".nav-item[data-nav]").forEach((btn) => {
      if (btn.dataset.boundKrlz) return;
      btn.dataset.boundKrlz = "1";
      btn.addEventListener("click", () => navigate(btn.dataset.nav));
    });
    const brand = $("#brandHome");
    if (brand && !brand.dataset.boundKrlz) {
      brand.dataset.boundKrlz = "1";
      brand.addEventListener("click", () => navigate("dashboard"));
    }
    const allBtn = $("#sideAllProjects");
    if (allBtn && !allBtn.dataset.boundKrlz) {
      allBtn.dataset.boundKrlz = "1";
      allBtn.addEventListener("click", () => navigate("projects"));
    }
    if (!state.current) renderNavView(true);
  }

  window.KRLZ2 = {
    init,
    navigate,
    renderNavView,
    renameProject,
    applyTheme,
    clearNewUrl: () => { ui.newUrl = ""; },
    onSystem,
    onHealth,
    AI_PRESETS,
    THEMES,
  };

  // Run immediately on script parse so sidebar & theme are live before boot() resolves
  init();
})();
