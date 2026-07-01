# 实施计划：新增背景音乐 m2，与 m1 循环轮播

## 需求（增强后）

- **目标**：3D 场景背景音乐从单曲 m1 循环 → m1 + m2 两首循环轮播（m1→m2→m1→m2…）。
- **约束**：
  - 导出 API 保持不变（`initSceneMusic` / `stopSceneMusic` / `toggleMute` / `isMuted` / `subscribeMute`），`App.tsx` 静音按钮 + `OfficeScene.tsx` lifecycle 零侵入。
  - 保留"首次 pointerdown/keydown 后播放"规避 autoplay 限制的机制。
  - 保留 remount 恢复（scene→dashboard→scene 不重启播放列表）。
  - 保留静音状态跨组件订阅。
- **范围**：3 处改动（1 前端逻辑 + 1 资源 + 1 后端挂载）。
- **验收标准**：
  1. `npm run build`（tsc + vite）零错误。
  2. dev 模式 `/sounds/m1.mp3` + `/sounds/m2.mp3` 均可访问。
  3. prod 模式 `/3d/sounds/m1.mp3` + `/3d/sounds/m2.mp3` 均返回 audio/mpeg（修挂载后）。
  4. 播放时 m1 播完自动接 m2，m2 播完接 m1，无限循环。
  5. 静音按钮对两首都生效。

## 方案

**核心改造**：`sceneMusic.ts` 的单例 `HTMLAudioElement` 从「硬编码单 src + `loop=true` 原生单曲循环」改为「播放列表数组 + `loop=false` + `onended` 手动切歌轮播」。

- `MUSIC_URL`（单常量）→ `PLAYLIST`（URL 数组）+ `currentIndex` 游标。
- `audio.loop = true` → `audio.loop = false` + `addEventListener("ended", 切下一首)`。
- 首次 start / remount resume / toggleMute / stopSceneMusic 逻辑全部不变（只动 src 来源）。

**理由**：浏览器 `HTMLAudioElement.loop` 只能单曲循环；多曲轮播必须 `loop=false` + `ended` 事件手动切。这是 Web Audio 最小改动方案，无需引入 Howler.js 等库。

## 步骤

### 1. `frontend/src/sounds/sceneMusic.ts`（核心逻辑改）
- 替换 `const MUSIC_URL = ...` → 播放列表：
  ```ts
  const SOUND_BASE = DEV ? "/sounds" : "/3d/sounds";
  const PLAYLIST = [`${SOUND_BASE}/m1.mp3`, `${SOUND_BASE}/m2.mp3`];
  let currentIndex = 0;
  ```
- `initSceneMusic` 内：`audio.loop = true` → `audio.loop = false`，新增 `ended` 监听器切下一首（`currentIndex = (currentIndex + 1) % PLAYLIST.length; audio.src = PLAYLIST[currentIndex]; audio.play()`）。
- 其余逻辑（start on pointerdown/keydown、remount resume、volume、preload）保持。

### 2. 资源复制
- `cp docs/m2.mp3 frontend/public/sounds/m2.mp3`（Vite 构建时随 m1 一起输出到 `app/static/3d/sounds/`）。

### 3. `app/main.py`（补 `/3d/sounds` 静态挂载，修既有 prod bug）
- 在 152 行（`/3d/office-assets` 挂载）之后追加：
  ```python
  _3d_sounds = _3D_STATIC_DIR / "sounds"
  if _3d_sounds.is_dir():
      app.mount("/3d/sounds", StaticFiles(directory=_3d_sounds), name="static-3d-sounds")
  ```
- **修既有 bug**：当前 prod 模式 `/3d/sounds/*.mp3` 被 `/3d/{full_path:path}` SPA fallback 返回 HTML，`Audio.play()` 静默失败。

## 影响范围

- **修改**：
  - `frontend/src/sounds/sceneMusic.ts`（~10 行改动）
  - `app/main.py`（+4 行挂载）
- **新增**：
  - `frontend/public/sounds/m2.mp3`（资源，从 `docs/m2.mp3` 复制）
- **不动**（API 兼容）：
  - `frontend/src/App.tsx`
  - `frontend/src/screens/OfficeScene.tsx`
- **测试**：无现成音频单测；以 `npm run build` 类型检查 + 手动验证 prod/dev 访问为准。

## 备注：Phase 3 双模型分析

本任务为机械改动（1 个单文件逻辑 + 配套资源/挂载），范围已完全确定，无架构决策点。双模型（Codex+Gemini）分析的边际价值低于调用成本，**建议跳过**直接进入实施。如需补跑双模型，告知即可。
