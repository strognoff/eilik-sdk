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
  motors: {
    right_arm: 1500,
    left_arm: 1500,
    torso: 1500,
    head: 1500,
  },
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

function setOutput(label, value, isError = false) {
  $("#lastAction").textContent = label;
  $("#lastAction").className = `meta ${isError ? "error" : "ok"}`;
  $("#output").textContent = typeof value === "string" ? value : pretty(value);
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

async function loadMotions() {
  const { body } = await api.get("/motions");
  state.motions = body.motions || [];
  $("#motionCount").textContent = `${body.count} motions`;
  const grid = $("#motionButtons");
  grid.innerHTML = "";
  for (const motion of state.motions) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.motion = motion;
    button.innerHTML = `<i data-lucide="play"></i><span>${motion.replaceAll("_", " ")}</span>`;
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

function bindEvents() {
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
    if (!range) return;
    const motor = range.dataset.servoRange;
    state.motors[motor] = Number(range.value);
    const value = document.querySelector(`[data-servo-value="${motor}"]`);
    if (value) value.textContent = range.value;
  });

  $("#readAngles").addEventListener("click", () => {
    run("Read servo angles", async () => {
      const result = await api.get("/servo/angles");
      $("#angleReadout").textContent = pretty(result.body);
      return result;
    });
  });
}

async function boot() {
  renderServoControls();
  bindEvents();
  await refreshStatus();
  await loadMotions();
  await refreshLogs(false);
  renderIcons();
}

boot().catch((error) => {
  setOutput("Boot failed", error.message, true);
});
