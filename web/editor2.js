/* KrlzCut 2.0 — Mega Clip Editor (Split-Screen Game Layer, Visual Filmstrip Timeline, Live Draggable Subtitles, Outline & AI Caption) */
(function () {
  "use strict";

  const ED_SVG = {
    play: '<svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true"><polygon points="6 4 20 12 6 20 6 4"/></svg>',
    pause: '<svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>',
    volOn: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a9 9 0 0 1 0 14"/></svg>',
    volOff: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>',
    face: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="9" r="3.5"/><path d="M6 20a6 6 0 0 1 12 0"/></svg>',
    center: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="6" y="4" width="12" height="16" rx="2"/><circle cx="12" cy="12" r="2"/></svg>',
    blur: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><rect x="8" y="8" width="8" height="8" rx="1"/></svg>',
    wand: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v3m0 12v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1m0-12.8-2.1 2.1M7.7 16.3l-2.1 2.1"/></svg>',
  };

  const SPLIT_RATIOS = ["50/50", "55/45", "60/40", "65/35", "70/30"];
  const ANIM_OPTIONS = [
    ["none", "Нет"],
    ["pop", "Pop"],
    ["fade", "Fade"],
    ["slide", "Slide"],
    ["bounce", "Bounce"],
  ];
  const SPEED_OPTIONS = [
    ["calm", "Спокойно"],
    ["normal", "Обычно"],
    ["fast", "Быстро"],
  ];
  const OUTLINE_SWATCHES = ["#000000", "#ffffff", "#111827", "#3b0764", "#9f1239", "#0f766e"];

  const ACCENT_HEX = {
    yellow: "#ffd60a",
    amber: "#fbbf24",
    orange: "#fb923c",
    coral: "#ff6b6b",
    red: "#ef4444",
    rose: "#f43f5e",
    pink: "#ec4899",
    magenta: "#d946ef",
    purple: "#a855f7",
    violet: "#8b5cf6",
    indigo: "#6366f1",
    blue: "#3b82f6",
    sky: "#38bdf8",
    cyan: "#06b6d4",
    teal: "#14b8a6",
    mint: "#34d399",
    green: "#22c55e",
    lime: "#a3e635",
    peach: "#fdba74",
    lavender: "#c4b5fd",
    white: "#ffffff",
  };

  function accentToHex(val) {
    const s = String(val || "yellow").trim();
    if (/^#[0-9a-fA-F]{6}$/.test(s)) return s;
    return ACCENT_HEX[s] || "#ffd60a";
  }

  function fontCssFamily(key) {
    if (typeof FONT_CSS !== "undefined" && FONT_CSS && FONT_CSS[key]) {
      return FONT_CSS[key];
    }
    return "VCMontserrat";
  }

  function makeOutlineShadow(enabled, width, color) {
    if (!enabled || width <= 0) return "0 2px 8px rgba(0,0,0,0.65)";
    const w = Math.max(1, Math.min(3, Math.round(width * 0.25)));
    const c = accentToHex(color || "#000000");
    const pts = [
      [-w, -w], [0, -w], [w, -w],
      [-w, 0], [w, 0],
      [-w, w], [0, w], [w, w],
    ];
    return pts.map(([x, y]) => `${x}px ${y}px 0 ${c}`).join(", ") + `, 0 ${w + 2}px ${w + 6}px rgba(0,0,0,0.72)`;
  }

  function buildLocalCues(clip, customText) {
    const baseStart = Number(clip.start || 0);
    const baseEnd = Number(clip.end || baseStart + 10);
    const clipLen = Math.max(0.5, baseEnd - baseStart);
    const rawWords = Array.isArray(clip.words) ? clip.words : [];
    const words = [];
    if (rawWords.length) {
      for (const w of rawWords) {
        const s = Number(w.start) - baseStart;
        const e = Number(w.end) - baseStart;
        if (e <= 0 || s >= clipLen) continue;
        const txt = String(w.word || "").trim();
        if (txt) words.push({ word: txt, start: Math.max(0, s), end: Math.min(clipLen, Math.max(s + 0.08, e)) });
      }
    }
    if (!words.length && customText) {
      const toks = customText.trim().split(/\s+/).filter(Boolean);
      const step = clipLen / Math.max(1, toks.length);
      toks.forEach((t, i) => words.push({ word: t, start: i * step, end: (i + 0.92) * step }));
    }
    if (!words.length) {
      return [{ start: 0, end: clipLen, words: [{ word: "ПРИМЕР", start: 0, end: clipLen * 0.5 }, { word: "СУБТИТРОВ", start: clipLen * 0.5, end: clipLen }] }];
    }
    const cues = [];
    let cur = [];
    for (const w of words) {
      const chars = cur.reduce((n, x) => n + x.word.length + 1, 0);
      if (cur.length && (cur.length >= 4 || chars + w.word.length > 26 || (w.start - cur[cur.length - 1].end) > 0.7)) {
        cues.push({ start: cur[0].start, end: cur[cur.length - 1].end, words: cur });
        cur = [];
      }
      cur.push(w);
    }
    if (cur.length) cues.push({ start: cur[0].start, end: cur[cur.length - 1].end, words: cur });
    return cues;
  }

  async function loadGameClipsList() {
    try {
      const res = await api("/api/game-clips");
      state.gameClips = Array.isArray(res.clips) ? res.clips : [];
    } catch (_) {
      state.gameClips = [];
    }
    return state.gameClips;
  }

  async function loadBgmList() {
    try {
      const res = await api("/api/bgm");
      state.bgmTracks = Array.isArray(res.tracks) ? res.tracks : [];
    } catch (_) {
      state.bgmTracks = [];
    }
    return state.bgmTracks;
  }

  window.openEditor = async function openMegaEditor(clipId) {
    if (!state.detail) return;
    const project = state.detail.project;
    const clip = state.detail.clips.find((c) => c.id === clipId);
    if (!clip) return;

    await Promise.all([loadGameClipsList(), loadBgmList()]);
    const s = { ...(project.options || {}), ...(clip.settings || {}) };
    const glIn = s.game_layer && typeof s.game_layer === "object" ? s.game_layer : {};
    const bgmIn = s.bgm && typeof s.bgm === "object" ? s.bgm : {};
    const defaultGameId = glIn.clip_id || (state.gameClips[0] ? state.gameClips[0].id : "builtin_neon_waves");
    const defaultBgmId = bgmIn.track_id || (state.bgmTracks[0] ? state.bgmTracks[0].id : "");

    const origStart = Number(clip.start || 0);
    const origEnd = Number(clip.end || origStart + 15);
    const projDur = Number(project.duration || 0);
    const maxSourceDur = projDur > 0 ? Math.max(origEnd, projDur) : origEnd;
    let windowMin = Math.max(0, origStart - 12);
    let windowMax = Math.min(maxSourceDur, origEnd + 12);
    const MIN_CLIP_DUR = 3.0;

    const ed = {
      start: origStart,
      end: origEnd,
      aspect: normalizeAspect(s.aspect || "9:16"),
      mode: s.mode || "auto",
      audioTrack: Number(s.audio_track ?? project.options?.audio_track ?? 0),
      subtitles: s.subtitles !== false,
      showHook: s.show_hook !== false,
      hook: clip.hook || "",
      text: clip.text || (Array.isArray(clip.words) ? clip.words.map((w) => w.word).join(" ") : ""),
      textDirty: false,
      caption: clip.caption || "",
      subFont: s.sub_font || "montserrat",
      subSize: Number(s.sub_size || 118),
      subPos: s.sub_position === "center" ? "middle" : (s.sub_position || "bottom"),
      subOffset: Number(s.sub_offset || 0),
      subFree: Array.isArray(s.sub_free) && s.sub_free.length >= 2 ? [Number(s.sub_free[0]), Number(s.sub_free[1])] : null,
      subSpeed: s.sub_speed || "calm",
      subAnim: s.sub_anim || "pop",
      accent: s.accent || "yellow",
      uppercase: s.uppercase !== false,
      subOutline: s.sub_outline !== false,
      subOutlineWidth: Number(s.sub_outline_width ?? 7),
      subOutlineColor: s.sub_outline_color || "#000000",
      cutPauses: Boolean(s.cut_pauses),
      punchInZoom: Boolean(s.punch_in_zoom),
      autoDualSplit: s.auto_dual_split !== false,
      watermark: s.watermark && typeof s.watermark === "object" ? { ...s.watermark } : null,
      introAssetId: String(s.intro_asset_id || ""),
      outroAssetId: String(s.outro_asset_id || ""),
      keepWatermark: Boolean(s.watermark && typeof s.watermark === "object" && s.watermark.enabled && s.watermark.asset_id),
      keepIntro: Boolean(s.intro_asset_id),
      keepOutro: Boolean(s.outro_asset_id),
      bgm: {
        enabled: Boolean(bgmIn.enabled && defaultBgmId),
        track_id: defaultBgmId,
        volume_db: Number(bgmIn.volume_db ?? -14),
        ducking: bgmIn.ducking !== false,
        duck_db: Number(bgmIn.duck_db ?? -22),
      },
      game: {
        enabled: Boolean(glIn.enabled),
        clip_id: defaultGameId,
        split: SPLIT_RATIOS.includes(glIn.split) ? glIn.split : "60/40",
        start: Number(glIn.start ?? glIn.start_offset ?? 0),
        game_zoom: Number(glIn.game_zoom || 1.0),
        top_zoom: Number(glIn.top_zoom || 1.0),
        top_pan: Array.isArray(glIn.top_pan) ? [...glIn.top_pan] : [0, 0],
        game_pan: Array.isArray(glIn.game_pan) ? [...glIn.game_pan] : [0, 0],
        audio: Boolean(glIn.audio ?? glIn.game_audio),
      },
    };

    const hasInitWm = ed.keepWatermark;
    const hasInitIntro = ed.keepIntro;
    const hasInitOutro = ed.keepOutro;

    const modal = $("#modal");
    modal.classList.remove("hidden");
    const videoSrc = clipUrl(clip);
    const stripUrl = `/api/projects/${project.id}/clips/${clip.id}/strip.jpg?start=${windowMin.toFixed(2)}&end=${windowMax.toFixed(2)}`;

    modal.innerHTML = `
      <div class="modal-backdrop" data-close></div>
      <div class="modal-panel mega-editor" role="dialog" aria-modal="true" aria-label="Мега-редактор клипа">
        <div class="mega-topbar">
          <div class="mega-top-left">
            <h3>${esc(clip.title || `Клип #${(clip.idx || 0) + 1}`)}</h3>
            <span class="status-pill" id="megaAspectBadge">${esc(ed.aspect)}</span>
          </div>
          <div class="mega-quick-pills">
            <button class="mega-pill ${ed.mode === "auto" ? "active" : ""}" data-top-mode="auto" type="button">По лицу</button>
            <button class="mega-pill ${ed.mode === "crop" ? "active" : ""}" data-top-mode="crop" type="button">По центру</button>
            <button class="mega-pill ${ed.mode === "blur" ? "active" : ""}" data-top-mode="blur" type="button">Размытие</button>
            <button class="mega-pill ${ed.subtitles ? "active" : ""}" id="topSubsPill" type="button">Субтитры</button>
            <button class="mega-pill ${ed.game.enabled ? "active" : ""}" id="topGamePill" type="button">Слой игры</button>
            <button class="modal-close" id="megaClose" type="button" aria-label="Закрыть">×</button>
          </div>
        </div>

        <div class="mega-body">
          <div class="mega-stage">
            <div class="mega-canvas-wrap">
              <div class="mega-viewport ${ed.game.enabled ? "split-on" : ""}" id="megaViewport" data-aspect="${esc(ed.aspect)}">
                <div class="mega-pane top-pane" id="megaTopPane">
                  <video id="megaMainVideo" src="${esc(videoSrc)}" playsinline preload="metadata"></video>
                </div>
                <div class="mega-pane game-pane" id="megaGamePane">
                  <video id="megaGameVideo" loop muted playsinline preload="metadata"></video>
                </div>
                <div class="mega-hook-overlay" id="megaHookOverlay"></div>
                <div class="mega-sub-overlay anim-${esc(ed.subAnim)}" id="megaSubOverlay" title="Перетащите субтитры мышкой">
                  <div class="sub-cue-inner" id="megaSubInner"></div>
                </div>
              </div>
            </div>

            <div class="mega-transport">
              <button class="mega-play-btn" id="megaPlayBtn" type="button" aria-label="Воспроизвести / Пауза">${ED_SVG.play}</button>
              <span class="mega-time" id="megaTime">00:00.0 / 00:00.0</span>
              <input class="mega-scrubber" id="megaScrub" type="range" min="0" max="100" step="0.1" value="0" aria-label="Позиция воспроизведения" />
              <button class="mini-chip" id="megaMuteBtn" type="button" aria-label="Звук">${ED_SVG.volOn}</button>
            </div>

            <div class="filmstrip-box" id="megaFilmstrip">
              <img class="filmstrip-img" src="${esc(stripUrl)}" alt="Раскадровка клипа" onerror="this.style.opacity='0'" />
              <div class="filmstrip-shade-l" id="fsShadeL"></div>
              <div class="filmstrip-shade-r" id="fsShadeR"></div>
              <div class="filmstrip-window" id="fsWindow"></div>
              <div class="filmstrip-handle" id="fsHandleL" title="Начало клипа"></div>
              <div class="filmstrip-handle" id="fsHandleR" title="Конец клипа"></div>
              <div class="filmstrip-playhead" id="fsPlayhead" style="left:0%"></div>
            </div>

            <div class="trim-num-row">
              <label class="trim-num-cell">
                <span>Начало (сек)</span>
                <input id="edStart" type="number" step="0.1" min="0" value="${ed.start.toFixed(1)}" />
              </label>
              <label class="trim-num-cell">
                <span>Длительность</span>
                <input id="edDur" type="text" readonly value="${Math.max(0.5, ed.end - ed.start).toFixed(1)} с" />
              </label>
              <label class="trim-num-cell">
                <span>Конец (сек)</span>
                <input id="edEnd" type="number" step="0.1" min="0.5" value="${ed.end.toFixed(1)}" />
              </label>
            </div>
          </div>

          <div class="mega-inspector">
            <section class="insp-card">
              <div class="insp-card-head">
                <h4>Кадрирование и формат</h4>
                <div class="chip-row">
                  ${["9:16", "1:1", "16:9", "4:5"].map((a) => `<button class="mini-chip ${ed.aspect === a ? "active" : ""}" data-ed-aspect="${a}" type="button">${a}</button>`).join("")}
                </div>
              </div>
              <div class="frame-cards">
                <button class="frame-card ${ed.mode === "auto" ? "active" : ""}" data-ed-mode="auto" type="button">
                  <span class="frame-glyph">${ED_SVG.face}</span><span>По лицу</span>
                </button>
                <button class="frame-card ${ed.mode === "crop" ? "active" : ""}" data-ed-mode="crop" type="button">
                  <span class="frame-glyph">${ED_SVG.center}</span><span>По центру</span>
                </button>
                <button class="frame-card ${ed.mode === "blur" ? "active" : ""}" data-ed-mode="blur" type="button">
                  <span class="frame-glyph">${ED_SVG.blur}</span><span>Размытый фон</span>
                </button>
              </div>
              <div id="megaAudioRow" style="display:none">
                <div class="hint" style="margin-bottom:4px">Аудиодорожка исходника</div>
                <select id="megaAudioSel" style="width:100%;height:34px;padding:0 10px;border-radius:10px;background:rgba(255,255,255,0.06);border:1px solid var(--separator)"></select>
              </div>
            </section>

            <section class="insp-card" id="inspGameCard">
              <div class="insp-card-head">
                <h4>Слой игры (Split-Screen)</h4>
                <label class="switch" style="margin:0"><input type="checkbox" id="edGameEnabled" ${ed.game.enabled ? "checked" : ""} /><span></span></label>
              </div>
              <div id="edGameBody" style="display:${ed.game.enabled ? "flex" : "none"};flex-direction:column;gap:10px">
                <div style="display:flex;gap:6px;align-items:center">
                  <select id="edGameClipSel" style="flex:1;height:36px;padding:0 10px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border)"></select>
                  <button class="mini-chip" id="edGameUploadBtn" type="button" title="Загрузить свой игровой ролик">+ Видео</button>
                  <button class="mini-chip" id="edGameDelBtn" type="button" title="Удалить выбранный загруженный ролик">✕</button>
                </div>
                <div id="edGameTagsRow" style="display:none;gap:6px;align-items:center">
                  <input id="edGameTagsInput" type="text" placeholder="Теги пула (через запятую: minecraft, gta)" style="flex:1;height:32px;padding:0 10px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12px" />
                  <button class="mini-chip" id="edGameTagsSaveBtn" type="button">Теги</button>
                </div>
                <div>
                  <div class="hint" style="margin-bottom:5px">Пропорция разделения (верх / игра)</div>
                  <div class="chip-row">
                    ${SPLIT_RATIOS.map((r) => `<button class="mini-chip ${ed.game.split === r ? "active" : ""}" data-ed-split="${r}" type="button">${r}</button>`).join("")}
                  </div>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
                  <label style="font-size:12px;color:var(--muted)">
                    Зум видео: <b id="edTopZoomVal">${ed.game.top_zoom.toFixed(2)}×</b>
                    <input id="edTopZoom" type="range" min="1" max="2.5" step="0.05" value="${ed.game.top_zoom}" style="width:100%" />
                  </label>
                  <label style="font-size:12px;color:var(--muted)">
                    Зум игры: <b id="edGameZoomVal">${ed.game.game_zoom.toFixed(2)}×</b>
                    <input id="edGameZoom" type="range" min="1" max="2.5" step="0.05" value="${ed.game.game_zoom}" style="width:100%" />
                  </label>
                </div>
                <label style="font-size:12px;color:var(--muted)">
                  Смещение старта игры: <b id="edGameOffVal">${ed.game.start.toFixed(0)} с</b>
                  <input id="edGameOff" type="range" min="0" max="120" step="1" value="${ed.game.start}" style="width:100%" />
                </label>
                <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
                  <label style="display:inline-flex;align-items:center;gap:8px;font-size:12.5px">
                    <input type="checkbox" id="edGameAudio" ${ed.game.audio ? "checked" : ""} /> Звук игры (тихий микс)
                  </label>
                  <button class="mini-chip" id="edResetPanBtn" type="button">Сбросить кадр</button>
                </div>
                <div class="hint">Совет: тяните верхнюю или нижнюю часть видео мышкой и крутите колёсико для точного зума.</div>
              </div>
            </section>

            <section class="insp-card" id="inspSubsCard">
              <div class="insp-card-head">
                <h4>Субтитры и оформление</h4>
                <label class="switch" style="margin:0"><input type="checkbox" id="edSubsOn" ${ed.subtitles ? "checked" : ""} /><span></span></label>
              </div>
              <div style="display:flex;gap:12px;flex-wrap:wrap;font-size:12.5px">
                <label style="display:inline-flex;align-items:center;gap:6px"><input type="checkbox" id="edUpper" ${ed.uppercase ? "checked" : ""} /> КАПСОМ</label>
                <label style="display:inline-flex;align-items:center;gap:6px"><input type="checkbox" id="edShowHook" ${ed.showHook ? "checked" : ""} /> Хук сверху</label>
                <label style="display:inline-flex;align-items:center;gap:6px"><input type="checkbox" id="edCutPauses" ${ed.cutPauses ? "checked" : ""} /> Вырезать паузы</label>
              </div>

              <div style="display:flex;gap:6px;align-items:center">
                <select id="edFontSel" style="flex:1;height:36px;padding:0 10px;border-radius:10px;background:rgba(255,255,255,0.06);border:1px solid var(--separator)">${fontOptionsHTML(ed.subFont)}</select>
                <button class="mini-chip" id="edFontUpload" type="button" title="Загрузить свой TTF/OTF шрифт">+ Шрифт</button>
              </div>

              <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
                <label style="font-size:12px;color:var(--muted)">
                  Размер: <b id="edSubSizeVal">${ed.subSize}</b>
                  <input id="edSubSize" type="range" min="70" max="180" step="2" value="${ed.subSize}" style="width:100%" />
                </label>
                <label style="font-size:12px;color:var(--muted)">
                  Сдвиг: <b id="edSubOffVal">${ed.subOffset}</b>
                  <input id="edSubOff" type="range" min="-120" max="180" step="5" value="${ed.subOffset}" style="width:100%" />
                </label>
              </div>

              <div>
                <div class="hint" style="margin-bottom:5px;display:flex;justify-content:space-between">
                  <span>Положение (можно перетаскивать мышкой прямо на видео)</span>
                  <button class="mini-chip" id="edResetSubPos" type="button" style="padding:2px 8px;font-size:11px">Сбросить</button>
                </div>
                <div class="chip-row">
                  ${[["bottom", "Снизу"], ["middle", "По центру"], ["top", "Сверху"]].map(([k, lbl]) => `<button class="mini-chip ${!ed.subFree && ed.subPos === k ? "active" : ""}" data-ed-pos="${k}" type="button">${lbl}</button>`).join("")}
                </div>
              </div>

              <div>
                <div class="hint" style="margin-bottom:5px">Анимация появления</div>
                <div class="chip-row">
                  ${ANIM_OPTIONS.map(([k, lbl]) => `<button class="mini-chip ${ed.subAnim === k ? "active" : ""}" data-ed-anim="${k}" type="button">${lbl}</button>`).join("")}
                </div>
              </div>

              <div>
                <div class="hint" style="margin-bottom:5px">Темп показа</div>
                <div class="chip-row">
                  ${SPEED_OPTIONS.map(([k, lbl]) => `<button class="mini-chip ${ed.subSpeed === k ? "active" : ""}" data-ed-speed="${k}" type="button">${lbl}</button>`).join("")}
                </div>
              </div>

              <div>
                <div class="hint" style="margin-bottom:5px">Цвет акцента (пресеты + свой цвет)</div>
                <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                  <div class="swatches" id="edAccentSwatches" style="flex:1">${swatchesHTML(ed.accent)}</div>
                  <label class="color-pick-field" title="Свой цвет акцента">
                    <input type="color" id="edAccentPicker" value="${esc(accentToHex(ed.accent))}" />
                  </label>
                </div>
              </div>

              <div style="padding-top:12px;border-top:1px solid var(--border);display:flex;flex-direction:column;gap:9px">
                <div style="display:flex;justify-content:space-between;align-items:center">
                  <span style="font-size:12.5px;font-weight:600">Обводка текста</span>
                  <label style="display:inline-flex;align-items:center;gap:6px;font-size:12px"><input type="checkbox" id="edOutlineOn" ${ed.subOutline ? "checked" : ""} /> Вкл</label>
                </div>
                <label style="font-size:12px;color:var(--muted)">
                  Толщина: <b id="edOutlineWVal">${ed.subOutlineWidth} px</b>
                  <input id="edOutlineW" type="range" min="0" max="14" step="1" value="${ed.subOutlineWidth}" style="width:100%" />
                </label>
                <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                  ${OUTLINE_SWATCHES.map((hex) => `<button type="button" class="swatch ${ed.subOutlineColor.toLowerCase() === hex ? "active" : ""}" data-out-color="${hex}" style="background:${hex};width:22px;height:22px;border:1px solid rgba(255,255,255,0.28)" title="${hex}"></button>`).join("")}
                  <label class="color-pick-field" style="margin-left:auto">
                    <span>Свой</span>
                    <input type="color" id="edOutlinePicker" value="${esc(accentToHex(ed.subOutlineColor))}" />
                  </label>
                </div>
              </div>

              <div>
                <div class="hint" style="margin-bottom:4px">Заголовок сверху (хук)</div>
                <input id="edHookInput" type="text" value="${esc(ed.hook)}" style="width:100%;height:36px;padding:0 11px;border-radius:10px;background:rgba(255,255,255,0.05);border:1px solid var(--separator);font-size:13px" />
              </div>
              <div>
                <div class="hint" style="margin-bottom:4px">Текст субтитров (тайминги сохраняются)</div>
                <textarea id="edTextInput" rows="3" style="width:100%;padding:9px 11px;border-radius:10px;background:rgba(255,255,255,0.05);border:1px solid var(--separator);font-size:12.5px;resize:vertical">${esc(ed.text)}</textarea>
              </div>
            </section>

            <section class="insp-card">
              <div class="insp-card-head">
                <h4>Фоновая музыка (BGM) и эффекты</h4>
                <label style="display:inline-flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">
                  <input type="checkbox" id="edBgmOn" ${ed.bgm.enabled ? "checked" : ""} ${state.bgmTracks.length ? "" : "disabled"} /> BGM
                </label>
              </div>
              <div style="display:flex;gap:6px;align-items:center">
                <select id="edBgmSel" style="flex:1;height:34px;padding:0 10px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border);font-size:12.5px">
                  ${state.bgmTracks.length
                    ? state.bgmTracks.map((t) => `<option value="${esc(t.id)}" ${t.id === ed.bgm.track_id ? "selected" : ""}>${esc(t.name)} (${t.duration} с)</option>`).join("")
                    : `<option value="">Треков пока нет</option>`}
                </select>
                <button class="mini-chip" id="edBgmUploadBtn" type="button">+ Загрузить</button>
                <input id="edBgmFile" type="file" accept=".mp3,.wav,.m4a,.ogg,.flac,audio/*" class="hidden" />
              </div>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:12px;color:var(--muted)">
                <label>
                  Громкость: <b id="edBgmVolVal">${ed.bgm.volume_db} дБ</b>
                  <input id="edBgmVol" type="range" min="-30" max="-6" step="1" value="${ed.bgm.volume_db}" style="width:100%" />
                </label>
                <label>
                  Приглушение: <b id="edBgmDuckVal">${ed.bgm.duck_db} дБ</b>
                  <input id="edBgmDuck" type="range" min="-28" max="-12" step="1" value="${ed.bgm.duck_db}" style="width:100%" />
                </label>
              </div>
              <div style="display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--text)">
                <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="edBgmDuckOn" ${ed.bgm.ducking ? "checked" : ""} /> Авто-приглушение под речью</label>
                <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="edPunchZoom" ${ed.punchInZoom ? "checked" : ""} /> Hook Punch-In Zoom</label>
                <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="edDualSplit" ${ed.autoDualSplit ? "checked" : ""} /> Авто 2-спикерный сплит</label>
              </div>
              ${(hasInitWm || hasInitIntro || hasInitOutro) ? `
              <div style="padding-top:10px;border-top:1px solid var(--border);display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--text)">
                ${hasInitWm ? `<label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="edKeepWm" ${ed.keepWatermark ? "checked" : ""} /> Водяной знак</label>` : ""}
                ${hasInitIntro ? `<label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="edKeepIntro" ${ed.keepIntro ? "checked" : ""} /> Интро</label>` : ""}
                ${hasInitOutro ? `<label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer"><input type="checkbox" id="edKeepOutro" ${ed.keepOutro ? "checked" : ""} /> Аутро</label>` : ""}
              </div>` : ""}
            </section>

            <section class="insp-card">
              <div class="insp-card-head">
                <h4>Описание и хэштеги</h4>
                <button class="mini-chip active" id="edGenCaptionBtn" type="button">${ED_SVG.wand}<span>Сгенерировать</span></button>
              </div>
              <textarea id="edCaptionInput" rows="3" placeholder="Описание для публикации клипа…" style="width:100%;padding:9px 11px;font-size:12.5px;resize:vertical">${esc(ed.caption)}</textarea>
            </section>
          </div>
        </div>

        <div class="mega-footer">
          <button class="btn-ghost" id="megaCancel" type="button">Отмена</button>
          <div class="mega-footer-right">
            <button class="btn-ghost" id="megaApplyAll" type="button">Применить ко всем</button>
            ${clip.status === "ready" ? `<a class="btn-ghost" href="${esc(videoSrc)}" download="${esc((clip.title || "clip") + ".mp4")}">Скачать MP4</a>` : ""}
            <button class="btn-primary" id="megaSaveBtn" type="button">Перерендерить клип</button>
          </div>
        </div>
      </div>
    `;

    const vp = $("#megaViewport");
    const mainVid = $("#megaMainVideo");
    const gameVid = $("#megaGameVideo");
    const topPane = $("#megaTopPane");
    const gamePane = $("#megaGamePane");
    const subOverlay = $("#megaSubOverlay");
    const subInner = $("#megaSubInner");
    const hookOverlay = $("#megaHookOverlay");
    const playBtn = $("#megaPlayBtn");
    const scrub = $("#megaScrub");
    const timeEl = $("#megaTime");
    const fsPlayhead = $("#fsPlayhead");

    let cues = buildLocalCues(clip, ed.text);
    let lastCueIdx = -1;

    function populateGameSelect() {
      const sel = $("#edGameClipSel");
      if (!sel) return;
      sel.innerHTML = state.gameClips.map((c) => `<option value="${esc(c.id)}" ${c.id === ed.game.clip_id ? "selected" : ""}>${esc(c.name)}${c.builtin ? "" : ` (${c.duration} с)`}</option>`).join("");
      const chosen = state.gameClips.find((c) => c.id === ed.game.clip_id) || state.gameClips[0];
      if (chosen) ed.game.clip_id = chosen.id;
      const delBtn = $("#edGameDelBtn");
      if (delBtn) delBtn.disabled = !chosen || Boolean(chosen.builtin);
      const tagsRow = $("#edGameTagsRow");
      const tagsInp = $("#edGameTagsInput");
      if (tagsRow && tagsInp) {
        const canTag = Boolean(chosen && !chosen.builtin);
        tagsRow.style.display = canTag ? "flex" : "none";
        tagsInp.value = canTag && Array.isArray(chosen.tags) ? chosen.tags.join(", ") : "";
      }
    }

    function syncGameVideoSrc() {
      if (!ed.game.enabled || !ed.game.clip_id) {
        gameVid.pause();
        gameVid.removeAttribute("src");
        return;
      }
      const nextUrl = `/api/game-clips/${encodeURIComponent(ed.game.clip_id)}/video`;
      if (gameVid.getAttribute("src") !== nextUrl) {
        gameVid.src = nextUrl;
        gameVid.load();
      }
      gameVid.muted = !ed.game.audio;
      gameVid.volume = 0.25;
      if (!mainVid.paused) gameVid.play().catch(() => {});
    }

    function applyVisualState(triggerAnim) {
      vp.dataset.aspect = ed.aspect;
      if ($("#megaAspectBadge")) $("#megaAspectBadge").textContent = ed.aspect;
      vp.classList.toggle("split-on", ed.game.enabled);
      $("#topGamePill")?.classList.toggle("active", ed.game.enabled);
      $("#topSubsPill")?.classList.toggle("active", ed.subtitles);
      const gb = $("#edGameBody");
      if (gb) gb.style.display = ed.game.enabled ? "flex" : "none";

      if (ed.game.enabled) {
        const [tPct, bPct] = ed.game.split.split("/").map((n) => Number(n) || 50);
        topPane.style.height = `${tPct}%`;
        gamePane.style.height = `${bPct}%`;
        mainVid.style.transform = `translate(${ed.game.top_pan[0] * 30}%, ${ed.game.top_pan[1] * 30}%) scale(${ed.game.top_zoom})`;
        gameVid.style.transform = `translate(${ed.game.game_pan[0] * 30}%, ${ed.game.game_pan[1] * 30}%) scale(${ed.game.game_zoom})`;
      } else {
        topPane.style.height = "100%";
        gamePane.style.height = "0%";
        mainVid.style.transform = "none";
      }

      // Subtitle position & typography
      subOverlay.style.display = ed.subtitles ? "block" : "none";
      subOverlay.style.fontFamily = `"${fontCssFamily(ed.subFont)}", sans-serif`;
      subOverlay.style.fontWeight = "800";
      const vpW = vp.clientWidth || 290;
      const pxSize = Math.max(13, Math.round((ed.subSize / 118) * (vpW / 14.2)));
      subOverlay.style.fontSize = `${pxSize}px`;
      subOverlay.style.setProperty("--sub-accent", accentToHex(ed.accent));
      subOverlay.style.textShadow = makeOutlineShadow(ed.subOutline, ed.subOutlineWidth, ed.subOutlineColor);

      if (ed.subFree) {
        subOverlay.style.left = `${Math.round(ed.subFree[0] * 100)}%`;
        subOverlay.style.top = `${Math.round(ed.subFree[1] * 100)}%`;
      } else {
        subOverlay.style.left = "50%";
        const splitTopPct = Number((ed.game.split || "60/40").split("/")[0]) || 60;
        const baseY = ed.subPos === "top" ? 20 : ed.subPos === "middle" ? 50 : (ed.game.enabled ? splitTopPct : 78);
        const yPct = Math.max(10, Math.min(90, baseY - ed.subOffset * 0.14));
        subOverlay.style.top = `${yPct}%`;
      }

      subOverlay.classList.remove("anim-none", "anim-pop", "anim-fade", "anim-slide", "anim-bounce");
      subOverlay.classList.add(`anim-${ed.subAnim}`);
      if (triggerAnim) {
        subInner.style.animation = "none";
        void subInner.offsetWidth;
        subInner.style.animation = "";
      }

      hookOverlay.style.display = ed.subtitles && ed.showHook && ed.hook.trim() ? "block" : "none";
      hookOverlay.style.fontFamily = `"${fontCssFamily(ed.subFont)}", sans-serif`;
      hookOverlay.style.fontSize = `${Math.max(12, Math.round(pxSize * 0.85))}px`;
      hookOverlay.textContent = ed.uppercase ? ed.hook.toUpperCase() : ed.hook;

      renderLiveCue(mainVid.currentTime || 0, triggerAnim);
    }

    function renderLiveCue(t, forceAnim) {
      let idx = cues.findIndex((c) => t >= c.start - 0.05 && t <= c.end + 0.35);
      if (idx === -1) idx = 0;
      const cue = cues[idx];
      if (!cue) return;
      const changed = idx !== lastCueIdx || forceAnim;
      lastCueIdx = idx;
      subInner.innerHTML = cue.words.map((w, wi) => {
        const isActive = (t >= w.start - 0.04 && t <= w.end + 0.08) || (t < 0.05 && wi === 0);
        const txt = ed.uppercase ? w.word.toUpperCase() : w.word;
        return `<span class="sub-word ${isActive ? "active" : ""}">${esc(txt)}</span>`;
      }).join(" ");
      if (changed && ed.subAnim !== "none") {
        subInner.style.animation = "none";
        void subInner.offsetWidth;
        subInner.style.animation = "";
      }
    }

    let curLPct = 0;
    let curRPct = 100;

    function updatePlayheadUI(frac) {
      const clamped = Math.max(0, Math.min(1, Number(frac) || 0));
      const posPct = curLPct + clamped * (curRPct - curLPct);
      fsPlayhead.style.left = `${posPct}%`;
    }

    function updateTrimUI() {
      const span = Math.max(1, windowMax - windowMin);
      const lPct = Math.max(0, Math.min(95, ((ed.start - windowMin) / span) * 100));
      const rPct = Math.max(lPct + 4, Math.min(100, ((ed.end - windowMin) / span) * 100));
      curLPct = lPct;
      curRPct = rPct;
      $("#fsShadeL").style.width = `${lPct}%`;
      $("#fsShadeR").style.width = `${100 - rPct}%`;
      $("#fsWindow").style.left = `${lPct}%`;
      $("#fsWindow").style.width = `${rPct - lPct}%`;
      $("#fsHandleL").style.left = `calc(${lPct}% - 7px)`;
      $("#fsHandleR").style.left = `calc(${rPct}% - 7px)`;
      if ($("#edStart")) $("#edStart").value = ed.start.toFixed(1);
      if ($("#edEnd")) $("#edEnd").value = ed.end.toFixed(1);
      if ($("#edDur")) $("#edDur").value = `${Math.max(0.5, ed.end - ed.start).toFixed(1)} с`;
      const dur = mainVid.duration || Math.max(0.5, ed.end - ed.start);
      updatePlayheadUI((mainVid.currentTime || 0) / dur);
    }

    // Draggable filmstrip handles
    function bindTrimHandle(el, side) {
      el.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        el.setPointerCapture(e.pointerId);
        const box = $("#megaFilmstrip").getBoundingClientRect();
        const move = (ev) => {
          const pct = Math.max(0, Math.min(1, (ev.clientX - box.left) / box.width));
          const val = windowMin + pct * (windowMax - windowMin);
          if (side === "left") ed.start = Math.max(0, Math.min(ed.end - MIN_CLIP_DUR, val));
          else ed.end = Math.min(maxSourceDur, Math.max(ed.start + MIN_CLIP_DUR, val));
          updateTrimUI();
        };
        const up = () => {
          el.removeEventListener("pointermove", move);
          el.removeEventListener("pointerup", up);
        };
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerup", up);
      });
    }
    bindTrimHandle($("#fsHandleL"), "left");
    bindTrimHandle($("#fsHandleR"), "right");

    // Draggable live subtitle overlay directly inside the Clip Editor!
    subOverlay.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      e.stopPropagation();
      subOverlay.classList.add("dragging");
      subOverlay.setPointerCapture(e.pointerId);
      const rect = vp.getBoundingClientRect();
      const move = (ev) => {
        const nx = Math.max(0.1, Math.min(0.9, (ev.clientX - rect.left) / rect.width));
        const ny = Math.max(0.1, Math.min(0.9, (ev.clientY - rect.top) / rect.height));
        ed.subFree = [Number(nx.toFixed(3)), Number(ny.toFixed(3))];
        $$("[data-ed-pos]").forEach((b) => b.classList.remove("active"));
        applyVisualState(false);
      };
      const up = () => {
        subOverlay.classList.remove("dragging");
        subOverlay.removeEventListener("pointermove", move);
        subOverlay.removeEventListener("pointerup", up);
      };
      subOverlay.addEventListener("pointermove", move);
      subOverlay.addEventListener("pointerup", up);
    });

    // Interactive pan + mouse wheel zoom on top & game panes
    function bindPanePanZoom(paneEl, panKey, zoomKey, sliderId, valId) {
      paneEl.addEventListener("pointerdown", (e) => {
        if (!ed.game.enabled) return;
        e.preventDefault();
        paneEl.setPointerCapture(e.pointerId);
        const startX = e.clientX, startY = e.clientY;
        const initPan = [...ed.game[panKey]];
        const rect = paneEl.getBoundingClientRect();
        const move = (ev) => {
          ed.game[panKey][0] = Math.max(-1, Math.min(1, initPan[0] + (ev.clientX - startX) / Math.max(80, rect.width * 0.5)));
          ed.game[panKey][1] = Math.max(-1, Math.min(1, initPan[1] + (ev.clientY - startY) / Math.max(80, rect.height * 0.5)));
          applyVisualState(false);
        };
        const up = () => {
          paneEl.removeEventListener("pointermove", move);
          paneEl.removeEventListener("pointerup", up);
        };
        paneEl.addEventListener("pointermove", move);
        paneEl.addEventListener("pointerup", up);
      });
      paneEl.addEventListener("wheel", (e) => {
        if (!ed.game.enabled) return;
        e.preventDefault();
        const next = Math.max(1.0, Math.min(2.5, ed.game[zoomKey] + (e.deltaY < 0 ? 0.08 : -0.08)));
        ed.game[zoomKey] = Number(next.toFixed(2));
        if ($(sliderId)) $(sliderId).value = String(ed.game[zoomKey]);
        if ($(valId)) $(valId).textContent = `${ed.game[zoomKey].toFixed(2)}×`;
        applyVisualState(false);
      }, { passive: false });
    }
    bindPanePanZoom(topPane, "top_pan", "top_zoom", "#edTopZoom", "#edTopZoomVal");
    bindPanePanZoom(gamePane, "game_pan", "game_zoom", "#edGameZoom", "#edGameZoomVal");

    // Video playback & sync
    const fmtSec = (x) => {
      const m = Math.floor(x / 60);
      const sec = (x % 60).toFixed(1).padStart(4, "0");
      return `${String(m).padStart(2, "0")}:${sec}`;
    };
    const togglePlay = () => {
      if (mainVid.paused) {
        mainVid.play().catch(() => {});
        if (ed.game.enabled && gameVid.src) {
          try { gameVid.currentTime = (ed.game.start + mainVid.currentTime) % Math.max(1, gameVid.duration || 8); } catch (_) {}
          gameVid.play().catch(() => {});
        }
      } else {
        mainVid.pause();
        gameVid.pause();
      }
    };
    playBtn.addEventListener("click", togglePlay);
    timeEl.textContent = `${fmtSec(0)} / ${fmtSec(Math.max(0.5, ed.end - ed.start))}`;
    mainVid.addEventListener("loadedmetadata", () => {
      const dur = mainVid.duration || Math.max(0.5, ed.end - ed.start);
      timeEl.textContent = `${fmtSec(mainVid.currentTime || 0)} / ${fmtSec(dur)}`;
    });
    mainVid.addEventListener("play", () => { playBtn.innerHTML = ED_SVG.pause; });
    mainVid.addEventListener("pause", () => { playBtn.innerHTML = ED_SVG.play; gameVid.pause(); });
    mainVid.addEventListener("timeupdate", () => {
      const dur = mainVid.duration || Math.max(1, ed.end - ed.start);
      const frac = Math.max(0, Math.min(1, mainVid.currentTime / dur));
      scrub.value = String(frac * 100);
      timeEl.textContent = `${fmtSec(mainVid.currentTime)} / ${fmtSec(dur)}`;
      updatePlayheadUI(frac);
      renderLiveCue(mainVid.currentTime, false);
    });
    scrub.addEventListener("input", () => {
      const dur = mainVid.duration || Math.max(1, ed.end - ed.start);
      const frac = Math.max(0, Math.min(1, Number(scrub.value) / 100));
      const t = frac * dur;
      mainVid.currentTime = t;
      if (ed.game.enabled && gameVid.duration) {
        gameVid.currentTime = (ed.game.start + t) % gameVid.duration;
      }
      updatePlayheadUI(frac);
      renderLiveCue(t, false);
    });
    $("#megaMuteBtn")?.addEventListener("click", (e) => {
      mainVid.muted = !mainVid.muted;
      e.currentTarget.innerHTML = mainVid.muted ? ED_SVG.volOff : ED_SVG.volOn;
    });

    // Inspector bindings
    const setMode = (m) => {
      ed.mode = m;
      $$("[data-ed-mode], [data-top-mode]").forEach((b) => {
        b.classList.toggle("active", (b.dataset.edMode || b.dataset.topMode) === m);
      });
    };
    $$("[data-ed-mode]").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.edMode)));
    $$("[data-top-mode]").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.topMode)));

    $$("[data-ed-aspect]").forEach((b) => {
      b.addEventListener("click", () => {
        ed.aspect = b.dataset.edAspect;
        $$("[data-ed-aspect]").forEach((x) => x.classList.toggle("active", x.dataset.edAspect === ed.aspect));
        applyVisualState(false);
      });
    });

    $("#topSubsPill")?.addEventListener("click", () => {
      ed.subtitles = !ed.subtitles;
      if ($("#edSubsOn")) $("#edSubsOn").checked = ed.subtitles;
      applyVisualState(false);
    });
    $("#edSubsOn")?.addEventListener("change", (e) => { ed.subtitles = e.target.checked; applyVisualState(false); });
    $("#edUpper")?.addEventListener("change", (e) => { ed.uppercase = e.target.checked; applyVisualState(false); });
    $("#edShowHook")?.addEventListener("change", (e) => { ed.showHook = e.target.checked; applyVisualState(false); });
    $("#edCutPauses")?.addEventListener("change", (e) => { ed.cutPauses = e.target.checked; });
    $("#edFontSel")?.addEventListener("change", (e) => { ed.subFont = e.target.value; applyVisualState(false); });
    $("#edFontUpload")?.addEventListener("click", () => { state.fontTarget = "#edFontSel"; $("#fontInput")?.click(); });
    $("#edSubSize")?.addEventListener("input", (e) => {
      ed.subSize = Number(e.target.value);
      if ($("#edSubSizeVal")) $("#edSubSizeVal").textContent = String(ed.subSize);
      applyVisualState(false);
    });
    $("#edSubOff")?.addEventListener("input", (e) => {
      ed.subOffset = Number(e.target.value);
      ed.subFree = null;
      if ($("#edSubOffVal")) $("#edSubOffVal").textContent = String(ed.subOffset);
      applyVisualState(false);
    });
    $$("[data-ed-pos]").forEach((b) => {
      b.addEventListener("click", () => {
        ed.subPos = b.dataset.edPos;
        ed.subFree = null;
        $$("[data-ed-pos]").forEach((x) => x.classList.toggle("active", x.dataset.edPos === ed.subPos));
        applyVisualState(false);
      });
    });
    $("#edResetSubPos")?.addEventListener("click", () => {
      ed.subFree = null;
      ed.subPos = "bottom";
      ed.subOffset = 0;
      if ($("#edSubOff")) $("#edSubOff").value = "0";
      if ($("#edSubOffVal")) $("#edSubOffVal").textContent = "0";
      $$("[data-ed-pos]").forEach((x) => x.classList.toggle("active", x.dataset.edPos === "bottom"));
      applyVisualState(false);
    });
    $$("[data-ed-anim]").forEach((b) => {
      b.addEventListener("click", () => {
        ed.subAnim = b.dataset.edAnim;
        $$("[data-ed-anim]").forEach((x) => x.classList.toggle("active", x.dataset.edAnim === ed.subAnim));
        applyVisualState(true);
      });
    });
    $$("[data-ed-speed]").forEach((b) => {
      b.addEventListener("click", () => {
        ed.subSpeed = b.dataset.edSpeed;
        $$("[data-ed-speed]").forEach((x) => x.classList.toggle("active", x.dataset.edSpeed === ed.subSpeed));
      });
    });

    $("#edAccentSwatches")?.addEventListener("click", (e) => {
      const sw = e.target.closest(".swatch");
      if (!sw || !sw.dataset.val) return;
      ed.accent = sw.dataset.val;
      $$("#edAccentSwatches .swatch").forEach((x) => x.classList.toggle("active", x === sw));
      if ($("#edAccentPicker")) $("#edAccentPicker").value = accentToHex(ed.accent);
      applyVisualState(false);
    });
    $("#edAccentPicker")?.addEventListener("input", (e) => {
      ed.accent = e.target.value;
      $$("#edAccentSwatches .swatch").forEach((x) => x.classList.remove("active"));
      applyVisualState(false);
    });

    $("#edOutlineOn")?.addEventListener("change", (e) => { ed.subOutline = e.target.checked; applyVisualState(false); });
    $("#edOutlineW")?.addEventListener("input", (e) => {
      ed.subOutlineWidth = Number(e.target.value);
      if ($("#edOutlineWVal")) $("#edOutlineWVal").textContent = `${ed.subOutlineWidth} px`;
      applyVisualState(false);
    });
    $$("[data-out-color]").forEach((b) => {
      b.addEventListener("click", () => {
        ed.subOutlineColor = b.dataset.outColor;
        $$("[data-out-color]").forEach((x) => x.classList.toggle("active", x === b));
        if ($("#edOutlinePicker")) $("#edOutlinePicker").value = ed.subOutlineColor;
        applyVisualState(false);
      });
    });
    $("#edOutlinePicker")?.addEventListener("input", (e) => {
      ed.subOutlineColor = e.target.value;
      $$("[data-out-color]").forEach((x) => x.classList.remove("active"));
      applyVisualState(false);
    });

    $("#edHookInput")?.addEventListener("input", (e) => { ed.hook = e.target.value; applyVisualState(false); });
    $("#edTextInput")?.addEventListener("input", (e) => {
      ed.text = e.target.value;
      ed.textDirty = true;
      cues = buildLocalCues(clip, ed.text);
      renderLiveCue(mainVid.currentTime || 0, false);
    });
    $("#edCaptionInput")?.addEventListener("input", (e) => { ed.caption = e.target.value; });

    // Game Layer bindings
    const setGameEnabled = (on) => {
      ed.game.enabled = Boolean(on);
      if ($("#edGameEnabled")) $("#edGameEnabled").checked = ed.game.enabled;
      syncGameVideoSrc();
      applyVisualState(false);
    };
    $("#topGamePill")?.addEventListener("click", () => setGameEnabled(!ed.game.enabled));
    $("#edGameEnabled")?.addEventListener("change", (e) => setGameEnabled(e.target.checked));
    $("#edGameClipSel")?.addEventListener("change", (e) => {
      ed.game.clip_id = e.target.value;
      populateGameSelect();
      syncGameVideoSrc();
    });
    $$("[data-ed-split]").forEach((b) => {
      b.addEventListener("click", () => {
        ed.game.split = b.dataset.edSplit;
        $$("[data-ed-split]").forEach((x) => x.classList.toggle("active", x.dataset.edSplit === ed.game.split));
        applyVisualState(false);
      });
    });
    $("#edTopZoom")?.addEventListener("input", (e) => {
      ed.game.top_zoom = Number(e.target.value);
      if ($("#edTopZoomVal")) $("#edTopZoomVal").textContent = `${ed.game.top_zoom.toFixed(2)}×`;
      applyVisualState(false);
    });
    $("#edGameZoom")?.addEventListener("input", (e) => {
      ed.game.game_zoom = Number(e.target.value);
      if ($("#edGameZoomVal")) $("#edGameZoomVal").textContent = `${ed.game.game_zoom.toFixed(2)}×`;
      applyVisualState(false);
    });
    $("#edGameOff")?.addEventListener("input", (e) => {
      ed.game.start = Number(e.target.value);
      if ($("#edGameOffVal")) $("#edGameOffVal").textContent = `${ed.game.start.toFixed(0)} с`;
      if (gameVid.duration > 0) {
        try {
          gameVid.currentTime = (ed.game.start + (mainVid.currentTime || 0)) % gameVid.duration;
        } catch (_) {}
      }
    });
    $("#edGameAudio")?.addEventListener("change", (e) => {
      ed.game.audio = e.target.checked;
      gameVid.muted = !ed.game.audio;
    });
    $("#edResetPanBtn")?.addEventListener("click", () => {
      ed.game.top_zoom = 1.0;
      ed.game.game_zoom = 1.0;
      ed.game.top_pan = [0, 0];
      ed.game.game_pan = [0, 0];
      if ($("#edTopZoom")) $("#edTopZoom").value = "1";
      if ($("#edGameZoom")) $("#edGameZoom").value = "1";
      if ($("#edTopZoomVal")) $("#edTopZoomVal").textContent = "1.00×";
      if ($("#edGameZoomVal")) $("#edGameZoomVal").textContent = "1.00×";
      applyVisualState(false);
    });

    $("#edGameUploadBtn")?.addEventListener("click", () => {
      const inp = $("#gameInput");
      if (!inp) return;
      inp.onchange = async () => {
        const file = inp.files?.[0];
        inp.value = "";
        if (!file) return;
        const fd = new FormData();
        fd.append("file", file);
        toast("Загружаю игровой ролик…");
        try {
          const added = await api("/api/game-clips", { method: "POST", body: fd });
          await loadGameClipsList();
          ed.game.clip_id = added.id;
          populateGameSelect();
          syncGameVideoSrc();
          toast(`Добавлен ролик «${added.name}»`);
        } catch (err) { toast(err.message, "err"); }
      };
      inp.click();
    });
    $("#edGameDelBtn")?.addEventListener("click", async () => {
      const chosen = state.gameClips.find((c) => c.id === ed.game.clip_id);
      if (!chosen || chosen.builtin) return;
      if (!confirm(`Удалить игровой ролик «${chosen.name}»?`)) return;
      try {
        await api(`/api/game-clips/${chosen.id}`, { method: "DELETE" });
        await loadGameClipsList();
        ed.game.clip_id = state.gameClips[0]?.id || "builtin_neon_waves";
        populateGameSelect();
        syncGameVideoSrc();
        toast("Ролик удалён");
      } catch (err) { toast(err.message, "err"); }
    });
    const saveGameTags = async () => {
      const chosen = state.gameClips.find((c) => c.id === ed.game.clip_id);
      if (!chosen || chosen.builtin) return;
      const raw = ($("#edGameTagsInput")?.value || "").trim();
      const tags = raw ? raw.split(/[,\s;]+/).map((t) => t.trim()).filter(Boolean) : [];
      try {
        const updated = await api(`/api/game-clips/${encodeURIComponent(chosen.id)}`, {
          method: "PATCH",
          body: JSON.stringify({ tags }),
        });
        chosen.tags = Array.isArray(updated.tags) ? updated.tags : tags;
        if ($("#edGameTagsInput")) $("#edGameTagsInput").value = chosen.tags.join(", ");
        toast("Теги ролика сохранены");
      } catch (err) { toast(err.message, "err"); }
    };
    $("#edGameTagsSaveBtn")?.addEventListener("click", saveGameTags);
    $("#edGameTagsInput")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); saveGameTags(); }
    });

    // Numeric trim inputs (expand filmstrip window when edited outside bounds)
    function ensureTrimBounds() {
      let expanded = false;
      if (ed.start < windowMin) {
        windowMin = Math.max(0, ed.start - 6);
        expanded = true;
      }
      if (ed.end > windowMax) {
        windowMax = Math.min(maxSourceDur, Math.max(ed.end + 6, windowMin + MIN_CLIP_DUR));
        expanded = true;
      }
      if (expanded) {
        const img = $("#megaFilmstrip .filmstrip-img");
        if (img) {
          img.style.opacity = "";
          img.src = `/api/projects/${project.id}/clips/${clip.id}/strip.jpg?start=${windowMin.toFixed(2)}&end=${windowMax.toFixed(2)}`;
        }
      }
    }
    $("#edStart")?.addEventListener("change", (e) => {
      ed.start = Math.max(0, Math.min(ed.end - MIN_CLIP_DUR, Number(e.target.value) || 0));
      ensureTrimBounds();
      updateTrimUI();
    });
    $("#edEnd")?.addEventListener("change", (e) => {
      ed.end = Math.min(maxSourceDur, Math.max(ed.start + MIN_CLIP_DUR, Number(e.target.value) || ed.start + MIN_CLIP_DUR));
      ensureTrimBounds();
      updateTrimUI();
    });

    // Generate Caption + Hashtags
    $("#edGenCaptionBtn")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.textContent = "Генерирую…";
      try {
        const res = await api(`/api/clips/${clip.id}/caption`, { method: "POST" });
        ed.caption = res.caption || "";
        if ($("#edCaptionInput")) $("#edCaptionInput").value = ed.caption;
        toast(res.source === "ai" ? "Описание сгенерировано ИИ" : "Описание и хэштеги готовы");
      } catch (err) { toast(err.message, "err"); }
      finally {
        btn.disabled = false;
        btn.innerHTML = `${ED_SVG.wand}<span>Сгенерировать</span>`;
      }
    });

    // Load audio tracks safely (escaped)
    api(`/api/projects/${project.id}/audio`).then((res) => {
      const tracks = Array.isArray(res.tracks) ? res.tracks : [];
      if (tracks.length > 1 && $("#megaAudioRow") && $("#megaAudioSel")) {
        $("#megaAudioRow").style.display = "block";
        $("#megaAudioSel").innerHTML = tracks.map((t, i) => {
          const lbl = [t.language, t.title, t.channels ? `${t.channels}ch` : ""].filter(Boolean).join(" · ") || `Дорожка ${i + 1}`;
          return `<option value="${i}" ${i === ed.audioTrack ? "selected" : ""}>${esc(lbl)}</option>`;
        }).join("");
        $("#megaAudioSel").addEventListener("change", (ev) => { ed.audioTrack = Number(ev.target.value); });
      }
    }).catch(() => {});

    // BGM & Effects controls
    function populateBgmSelect() {
      const sel = $("#edBgmSel");
      const bgmOn = $("#edBgmOn");
      if (bgmOn) bgmOn.disabled = state.bgmTracks.length === 0;
      if (!sel) return;
      if (!state.bgmTracks.length) {
        sel.innerHTML = `<option value="">Треков пока нет</option>`;
        return;
      }
      sel.innerHTML = state.bgmTracks.map((t) => `<option value="${esc(t.id)}" ${t.id === ed.bgm.track_id ? "selected" : ""}>${esc(t.name)} (${t.duration} с)</option>`).join("");
      if (!ed.bgm.track_id && state.bgmTracks[0]) ed.bgm.track_id = state.bgmTracks[0].id;
    }
    $("#edBgmOn")?.addEventListener("change", (e) => { ed.bgm.enabled = e.target.checked; });
    $("#edBgmSel")?.addEventListener("change", (e) => { ed.bgm.track_id = e.target.value; });
    $("#edBgmVol")?.addEventListener("input", (e) => {
      ed.bgm.volume_db = Number(e.target.value);
      if ($("#edBgmVolVal")) $("#edBgmVolVal").textContent = `${ed.bgm.volume_db} дБ`;
    });
    $("#edBgmDuck")?.addEventListener("input", (e) => {
      ed.bgm.duck_db = Number(e.target.value);
      if ($("#edBgmDuckVal")) $("#edBgmDuckVal").textContent = `${ed.bgm.duck_db} дБ`;
    });
    $("#edBgmDuckOn")?.addEventListener("change", (e) => { ed.bgm.ducking = e.target.checked; });
    $("#edPunchZoom")?.addEventListener("change", (e) => { ed.punchInZoom = e.target.checked; });
    $("#edDualSplit")?.addEventListener("change", (e) => { ed.autoDualSplit = e.target.checked; });
    $("#edKeepWm")?.addEventListener("change", (e) => { ed.keepWatermark = e.target.checked; });
    $("#edKeepIntro")?.addEventListener("change", (e) => { ed.keepIntro = e.target.checked; });
    $("#edKeepOutro")?.addEventListener("change", (e) => { ed.keepOutro = e.target.checked; });
    $("#edBgmUploadBtn")?.addEventListener("click", () => $("#edBgmFile")?.click());
    $("#edBgmFile")?.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;
      try {
        const fd = new FormData();
        fd.append("file", file);
        const added = await api("/api/bgm", { method: "POST", body: fd });
        await loadBgmList();
        ed.bgm.track_id = added.id;
        ed.bgm.enabled = true;
        const bgmOn = $("#edBgmOn");
        if (bgmOn) { bgmOn.disabled = false; bgmOn.checked = true; }
        populateBgmSelect();
        toast(`Трек добавлен: ${added.name}`);
      } catch (err) { toast(err.message, "err"); }
    });

    function buildPayload() {
      const payload = {
        start: Number(ed.start.toFixed(2)),
        end: Number(ed.end.toFixed(2)),
        aspect: ed.aspect,
        mode: ed.mode,
        audio_track: ed.audioTrack,
        subtitles: ed.subtitles,
        show_hook: ed.showHook,
        hook: ed.hook,
        caption: ed.caption,
        sub_font: ed.subFont,
        sub_size: ed.subSize,
        sub_position: ed.subPos,
        sub_offset: ed.subOffset,
        sub_speed: ed.subSpeed,
        sub_anim: ed.subAnim,
        accent: ed.accent,
        uppercase: ed.uppercase,
        sub_outline: ed.subOutline,
        sub_outline_width: ed.subOutlineWidth,
        sub_outline_color: ed.subOutlineColor,
        cut_pauses: ed.cutPauses,
        game_layer: ed.game,
        bgm: ed.bgm.enabled && ed.bgm.track_id ? ed.bgm : null,
        punch_in_zoom: ed.punchInZoom,
        auto_dual_split: ed.autoDualSplit,
      };
      if (hasInitWm) payload.watermark = ed.keepWatermark ? ed.watermark : null;
      else if (ed.watermark) payload.watermark = ed.watermark;
      if (hasInitIntro) payload.intro_asset_id = ed.keepIntro ? ed.introAssetId : "";
      else if (ed.introAssetId) payload.intro_asset_id = ed.introAssetId;
      if (hasInitOutro) payload.outro_asset_id = ed.keepOutro ? ed.outroAssetId : "";
      else if (ed.outroAssetId) payload.outro_asset_id = ed.outroAssetId;
      if (ed.textDirty) payload.text = ed.text;
      if (ed.subFree) payload.sub_free = ed.subFree;
      return payload;
    }

    const doClose = () => {
      mainVid.pause();
      gameVid.pause();
      closeModal();
    };
    $("#megaClose")?.addEventListener("click", doClose);
    $("#megaCancel")?.addEventListener("click", doClose);

    $("#megaApplyAll")?.addEventListener("click", async () => {
      const p = buildPayload();
      delete p.start; delete p.end; delete p.text; delete p.hook; delete p.caption;
      try {
        const res = await api(`/api/projects/${project.id}/style/apply`, { method: "POST", body: JSON.stringify(p) });
        toast(`Стиль и Слой игры применены к ${res.clips} клипам`);
        doClose();
        await loadDetail(true);
        schedulePoll(700);
      } catch (err) { toast(err.message, "err"); }
    });

    $("#megaSaveBtn")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.textContent = "Запускаю рендер…";
      try {
        await api(`/api/clips/${clip.id}/rerender`, { method: "POST", body: JSON.stringify(buildPayload()) });
        toast("Клип отправлен на перерендер");
        doClose();
        await loadDetail(true);
        schedulePoll(700);
      } catch (err) {
        toast(err.message, "err");
        btn.disabled = false;
        btn.textContent = "Перерендерить клип";
      }
    });

    populateGameSelect();
    syncGameVideoSrc();
    updateTrimUI();
    applyVisualState(false);
  };
})();
