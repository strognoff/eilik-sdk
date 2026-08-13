const api = {
  async request(path, options = {}) {
    const started = performance.now();
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const text = await response.text();
    let body;
    try {
      body = text ? JSON.parse(text) : {};
    } catch {
      body = { raw: text };
    }
    if (!response.ok) {
      const message = body.detail || body.message || response.statusText;
      throw new Error(`${response.status} ${message}`);
    }
    return {
      body,
      ms: Math.round(performance.now() - started),
    };
  },
  get(path) {
    return this.request(path);
  },
  post(path, body = {}) {
    return this.request(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  busy: false,
  motions: [],
  sequence: [],
  draggedBlock: null,
  motors: {
    right_arm: 1500,
    left_arm: 1500,
    torso: 1500,
    head: 1500,
  },
};

const motionIcons = {
  bow: "corner-down-left",
  fist_bump: "hand",
  heart_hands: "heart",
  high_five: "hand",
  left_arm_down: "arrow-down-left",
  left_arm_up: "arrow-up-left",
  look_left: "arrow-left",
  look_right: "arrow-right",
  nod: "chevrons-up-down",
  nod_emphatic: "chevrons-up-down",
  peek: "eye",
  reset_pose: "rotate-ccw",
  shake_head: "move-horizontal",
  shake_head_emphatic: "move-horizontal",
  shrug: "shuffle",
  spin: "rotate-cw",
  surprise: "sparkles",
  thumbs_up: "thumbs-up",
  wave: "hand",
  wiggle: "waves",
};

function renderIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

function setBusy(busy) {
  state.busy = busy;
  $$("button").forEach((button) => {
    button.disabled = busy;
  });
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function titleCase(value) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function setOutput(label, value, isError = false) {
  $("#lastAction").textContent = label;
  $("#lastAction").className = `meta ${isError ? "error" : "ok"}`;
  $("#output").textContent = typeof value === "string" ? value : pretty(value);
}

function setGameOutput(label, value, isError = false) {
  $("#gameStatus").textContent = label;
  $("#gameStatus").className = `meta ${isError ? "error" : "ok"}`;
  $("#gameOutput").textContent = typeof value === "string" ? value : pretty(value);
}

async function run(label, fn) {
  setBusy(true);
  setOutput(label, "Running...");
  try {
    const result = await fn();
    setOutput(`${label} (${result.ms}ms)`, result.body);
    await refreshStatus();
    await refreshLogs(false);
    return result;
  } catch (error) {
    setOutput(label, error.message, true);
  } finally {
    setBusy(false);
    renderIcons();
  }
}

async function runGame(label, fn) {
  setBusy(true);
  setGameOutput(label, "Running...");
  try {
    const result = await fn();
    setGameOutput(`${label} (${result.ms}ms)`, result.body);
    await refreshStatus();
    await refreshLogs(false);
    return result;
  } catch (error) {
    setGameOutput(label, error.message, true);
  } finally {
    setBusy(false);
    renderIcons();
  }
}

async function refreshStatus() {
  try {
    const { body } = await api.get("/health");
    const port = body.port || "no port";
    $("#statusLine").textContent = `${body.service} | ${body.mode} | ${port} | connected=${body.connected} | protocol=${body.protocol}`;
  } catch (error) {
    $("#statusLine").textContent = `API unavailable: ${error.message}`;
  }
}

async function refreshLogs(writeOutput = true) {
  const result = await api.get("/logs/recent?lines=120");
  $("#logs").textContent = result.body.lines.length
    ? result.body.lines.join("\n")
    : "No log lines yet.";
  if (writeOutput) {
    setOutput("Logs refreshed", {
      path: result.body.path,
      line_count: result.body.line_count,
      rotated_files: result.body.rotated_files,
    });
  }
  return result;
}

function activePageFromLocation() {
  return window.location.pathname.endsWith("/game") ? "game" : "control";
}

function showPage(page, push = false) {
  const isGame = page === "game";
  $("#controlPage").hidden = isGame;
  $("#gamePage").hidden = !isGame;
  $("#controlPage").classList.toggle("active", !isGame);
  $("#gamePage").classList.toggle("active", isGame);
  $("#pageTitle").textContent = isGame ? "Eilik Kids Game" : "Eilik Control";
  $$("[data-page-link]").forEach((link) => {
    link.classList.toggle("active", link.dataset.pageLink === page);
  });
  if (push) {
    window.history.pushState({ page }, "", isGame ? "/app/game" : "/app");
  }
  closeDrawer();
}

function openDrawer() {
  $("#drawer").classList.add("open");
  $("#drawerBackdrop").classList.add("open");
}

function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#drawerBackdrop").classList.remove("open");
}

async function loadMotions() {
  const { body } = await api.get("/motions");
  state.motions = body.motions || [];
  $("#motionCount").textContent = `${body.count} motions`;
  $("#gameBlockCount").textContent = `${body.count} moves`;
  renderMotionButtons();
  renderPalette();
}

function renderMotionButtons() {
  const grid = $("#motionButtons");
  grid.innerHTML = "";
  for (const motion of state.motions) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.motion = motion;
    button.innerHTML = `<i data-lucide="${motionIcons[motion] || "play"}"></i><span>${titleCase(motion)}</span>`;
    grid.appendChild(button);
  }
  renderIcons();
}

function displayPayload() {
  return {
    text: $("#messageText").value,
    font_size: Number($("#fontSize").value),
    hold_seconds: Number($("#holdSeconds").value),
    auto_idle: $("#autoIdle").checked,
  };
}

function routinePayload() {
  return {
    text: $("#messageText").value,
    font_size: Number($("#fontSize").value),
    duration_seconds: Number($("#routineDuration").value),
    cleanup: $("#cleanupMode").value,
  };
}

function sequencePayload() {
  return {
    steps: state.sequence.map((block) => {
      if (block.type === "motion") {
        return { type: "motion", motion: block.motion };
      }
      if (block.type === "display_text") {
        return {
          type: "display_text",
          text: block.text,
          hold_seconds: block.hold_seconds,
          font_size: block.font_size,
        };
      }
      return { type: "wait", seconds: block.seconds };
    }),
    cleanup: $("#sequenceCleanup").value,
    step_pause_seconds: Number($("#sequencePause").value),
  };
}

function newMotionBlock(motion) {
  return {
    id: crypto.randomUUID(),
    type: "motion",
    motion,
    label: titleCase(motion),
    icon: motionIcons[motion] || "play",
  };
}

function newMessageBlock(text = $("#gameMessageText").value) {
  return {
    id: crypto.randomUUID(),
    type: "display_text",
    text: (text || "Hello Alice!!").slice(0, 80),
    hold_seconds: 1.5,
    font_size: 16,
    label: "Message",
    icon: "message-square",
  };
}

function newWaitBlock() {
  return {
    id: crypto.randomUUID(),
    type: "wait",
    seconds: 0.5,
    label: "Wait",
    icon: "timer",
  };
}

function renderPalette() {
  const palette = $("#paletteBlocks");
  palette.innerHTML = "";

  const message = document.createElement("button");
  message.type = "button";
  message.className = "game-block palette-block message-block";
  message.dataset.addBlock = "message";
  message.innerHTML = `<i data-lucide="message-square"></i><span>Message</span>`;
  palette.appendChild(message);

  for (const motion of state.motions) {
    const block = document.createElement("button");
    block.type = "button";
    block.className = "game-block palette-block motion-block";
    block.draggable = true;
    block.dataset.paletteMotion = motion;
    block.innerHTML = `<i data-lucide="${motionIcons[motion] || "play"}"></i><span>${titleCase(motion)}</span>`;
    palette.appendChild(block);
  }
  renderIcons();
}

function renderSequence() {
  const dropzone = $("#sequenceDropzone");
  dropzone.innerHTML = "";
  $("#sequenceCount").textContent = `${state.sequence.length} block${state.sequence.length === 1 ? "" : "s"}`;

  if (!state.sequence.length) {
    dropzone.innerHTML = `
      <div class="empty-sequence">
        <i data-lucide="move-down"></i>
        <span>Drop blocks</span>
      </div>
    `;
    renderIcons();
    return;
  }

  state.sequence.forEach((block, index) => {
    const item = document.createElement("div");
    item.className = `sequence-block ${block.type.replace("_", "-")}`;
    item.draggable = true;
    item.dataset.sequenceId = block.id;
    item.innerHTML = `
      <span class="sequence-index">${index + 1}</span>
      <i data-lucide="${block.icon}"></i>
      <div class="sequence-main">
        <strong>${block.label}</strong>
        ${sequenceFields(block)}
      </div>
      <button type="button" class="mini-button" data-move-block="up" title="Move up">
        <i data-lucide="arrow-up"></i>
      </button>
      <button type="button" class="mini-button" data-move-block="down" title="Move down">
        <i data-lucide="arrow-down"></i>
      </button>
      <button type="button" class="mini-button" data-remove-block title="Remove">
        <i data-lucide="x"></i>
      </button>
    `;
    dropzone.appendChild(item);
  });
  renderIcons();
}

function sequenceFields(block) {
  if (block.type === "display_text") {
    return `
      <input data-block-field="text" value="${escapeHtml(block.text)}" maxlength="80" />
      <label class="inline-field">
        <span>Hold</span>
        <input data-block-field="hold_seconds" type="number" min="0" max="15" step="0.5" value="${block.hold_seconds}" />
      </label>
    `;
  }
  if (block.type === "wait") {
    return `
      <label class="inline-field">
        <span>Seconds</span>
        <input data-block-field="seconds" type="number" min="0" max="10" step="0.25" value="${block.seconds}" />
      </label>
    `;
  }
  return `<span class="block-detail">${block.motion}</span>`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function addSequenceBlock(block, index = state.sequence.length) {
  state.sequence.splice(index, 0, block);
  renderSequence();
}

function moveBlock(id, direction) {
  const index = state.sequence.findIndex((block) => block.id === id);
  if (index < 0) return;
  const nextIndex = direction === "up" ? Math.max(0, index - 1) : Math.min(state.sequence.length - 1, index + 1);
  if (nextIndex === index) return;
  const [block] = state.sequence.splice(index, 1);
  state.sequence.splice(nextIndex, 0, block);
  renderSequence();
}

function renderServoControls() {
  const names = [
    ["right_arm", "Right arm"],
    ["left_arm", "Left arm"],
    ["torso", "Torso"],
    ["head", "Head"],
  ];
  const stack = $("#servoControls");
  stack.innerHTML = "";
  for (const [key, label] of names) {
    const row = document.createElement("div");
    row.className = "servo-row";
    row.innerHTML = `
      <strong>${label}</strong>
      <input type="range" min="0" max="3000" step="50" value="${state.motors[key]}" data-servo-range="${key}" />
      <span class="servo-value" data-servo-value="${key}">${state.motors[key]}</span>
      <button type="button" data-servo-send="${key}">
        <i data-lucide="send"></i>
        <span>Send</span>
      </button>
    `;
    stack.appendChild(row);
  }
  renderIcons();
}

function bindNavigation() {
  $("#menuToggle").addEventListener("click", openDrawer);
  $("#menuClose").addEventListener("click", closeDrawer);
  $("#drawerBackdrop").addEventListener("click", closeDrawer);
  $$("[data-page-link]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      showPage(link.dataset.pageLink, true);
    });
  });
  window.addEventListener("popstate", () => showPage(activePageFromLocation()));
}

function bindControlEvents() {
  $("#refreshStatus").addEventListener("click", () => run("Refresh status", () => api.get("/health")));
  $("#refreshLogs").addEventListener("click", () => run("Refresh logs", () => refreshLogs()));
  $("#clearOutput").addEventListener("click", () => {
    $("#output").textContent = "Ready.";
    $("#lastAction").textContent = "Idle";
    $("#lastAction").className = "meta";
  });

  $("#sendText").addEventListener("click", () => {
    run("Send text", () => api.post("/display/text", displayPayload()));
  });

  $("#textArms").addEventListener("click", () => {
    run("Text + arms", () => api.post("/routine/display_text_arms", routinePayload()));
  });

  document.body.addEventListener("click", (event) => {
    const motionButton = event.target.closest("[data-motion]");
    if (motionButton) {
      const motion = motionButton.dataset.motion;
      run(`Motion: ${motion}`, () => api.post(`/motion/${motion}`));
      return;
    }

    const servoButton = event.target.closest("[data-servo-send]");
    if (servoButton) {
      const motor = servoButton.dataset.servoSend;
      const position = state.motors[motor];
      run(`Servo: ${motor}`, () => api.post("/servo/move", { motor, position }));
    }
  });

  document.body.addEventListener("input", (event) => {
    const range = event.target.closest("[data-servo-range]");
    if (range) {
      const motor = range.dataset.servoRange;
      state.motors[motor] = Number(range.value);
      const value = document.querySelector(`[data-servo-value="${motor}"]`);
      if (value) value.textContent = range.value;
      return;
    }

    const field = event.target.closest("[data-block-field]");
    if (field) {
      const item = event.target.closest("[data-sequence-id]");
      const block = state.sequence.find((entry) => entry.id === item?.dataset.sequenceId);
      if (!block) return;
      const key = field.dataset.blockField;
      block[key] = field.type === "number" ? Number(field.value) : field.value;
    }
  });

  $("#readAngles").addEventListener("click", () => {
    run("Read servo angles", async () => {
      const result = await api.get("/servo/angles");
      $("#angleReadout").textContent = pretty(result.body);
      return result;
    });
  });
}

function bindGameEvents() {
  $("#addMessageBlock").addEventListener("click", () => addSequenceBlock(newMessageBlock()));
  $("#addWaitBlock").addEventListener("click", () => addSequenceBlock(newWaitBlock()));
  $("#clearSequence").addEventListener("click", () => {
    state.sequence = [];
    renderSequence();
    setGameOutput("Ready", "Ready.");
  });
  $("#playSequence").addEventListener("click", () => {
    if (!state.sequence.length) {
      setGameOutput("No blocks", "Add at least one block before pressing play.", true);
      return;
    }
    runGame("Play sequence", () => api.post("/routine/sequence", sequencePayload()));
  });

  $("#paletteBlocks").addEventListener("click", (event) => {
    const message = event.target.closest("[data-add-block='message']");
    if (message) {
      addSequenceBlock(newMessageBlock());
      return;
    }
    const motion = event.target.closest("[data-palette-motion]")?.dataset.paletteMotion;
    if (motion) {
      addSequenceBlock(newMotionBlock(motion));
    }
  });

  $("#paletteBlocks").addEventListener("dragstart", (event) => {
    const motion = event.target.closest("[data-palette-motion]")?.dataset.paletteMotion;
    if (!motion) return;
    state.draggedBlock = { source: "palette", motion };
    event.dataTransfer.effectAllowed = "copy";
  });

  $("#sequenceDropzone").addEventListener("dragstart", (event) => {
    const item = event.target.closest("[data-sequence-id]");
    if (!item) return;
    state.draggedBlock = { source: "sequence", id: item.dataset.sequenceId };
    event.dataTransfer.effectAllowed = "move";
  });

  $("#sequenceDropzone").addEventListener("dragover", (event) => {
    event.preventDefault();
    $("#sequenceDropzone").classList.add("drag-over");
  });

  $("#sequenceDropzone").addEventListener("dragleave", () => {
    $("#sequenceDropzone").classList.remove("drag-over");
  });

  $("#sequenceDropzone").addEventListener("drop", (event) => {
    event.preventDefault();
    $("#sequenceDropzone").classList.remove("drag-over");
    const targetItem = event.target.closest("[data-sequence-id]");
    const targetIndex = targetItem
      ? state.sequence.findIndex((block) => block.id === targetItem.dataset.sequenceId)
      : state.sequence.length;

    if (state.draggedBlock?.source === "palette") {
      addSequenceBlock(newMotionBlock(state.draggedBlock.motion), targetIndex < 0 ? state.sequence.length : targetIndex);
    } else if (state.draggedBlock?.source === "sequence") {
      const fromIndex = state.sequence.findIndex((block) => block.id === state.draggedBlock.id);
      if (fromIndex >= 0) {
        const [block] = state.sequence.splice(fromIndex, 1);
        const adjustedIndex = fromIndex < targetIndex ? targetIndex - 1 : targetIndex;
        state.sequence.splice(Math.max(0, adjustedIndex), 0, block);
        renderSequence();
      }
    }
    state.draggedBlock = null;
  });

  $("#sequenceDropzone").addEventListener("click", (event) => {
    const item = event.target.closest("[data-sequence-id]");
    if (!item) return;
    const id = item.dataset.sequenceId;
    if (event.target.closest("[data-remove-block]")) {
      state.sequence = state.sequence.filter((block) => block.id !== id);
      renderSequence();
      return;
    }
    const move = event.target.closest("[data-move-block]")?.dataset.moveBlock;
    if (move) {
      moveBlock(id, move);
    }
  });
}

async function boot() {
  renderServoControls();
  bindNavigation();
  bindControlEvents();
  bindGameEvents();
  renderSequence();
  showPage(activePageFromLocation());
  await refreshStatus();
  await loadMotions();
  await refreshLogs(false);
  renderIcons();
}

boot().catch((error) => {
  setOutput("Boot failed", error.message, true);
  setGameOutput("Boot failed", error.message, true);
});
