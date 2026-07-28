// selfheal web demo frontend: streams the agent loop from /api/run as
// newline-delimited JSON and renders it as a terminal log -- the same
// panel structure the real CLI prints with `rich` (see cli.py), just in
// the browser. No frameworks, no CDN dependencies.

const feed = document.getElementById("feed");
const runBtn = document.getElementById("runBtn");
const taskInput = document.getElementById("task");

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function highlightPython(code) {
  const escaped = escapeHtml(code);
  const KEYWORDS =
    /\b(def|return|if|elif|else|for|while|import|from|as|with|try|except|finally|raise|class|pass|break|continue|in|is|not|and|or|None|True|False|lambda|yield)\b/g;
  return escaped
    .replace(/(#.*)$/gm, '<span class="tok-com">$1</span>')
    .replace(/("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, '<span class="tok-str">$1</span>')
    .replace(KEYWORDS, '<span class="tok-kw">$1</span>')
    .replace(/\b(\d+\.?\d*)\b/g, '<span class="tok-num">$1</span>');
}

function removeCursor() {
  const c = feed.querySelector(".cursor");
  if (c) c.remove();
}

function scrollToEnd(el) {
  el.scrollIntoView({ behavior: "smooth", block: "end" });
}

function addLine(text, { cursor = false, tone = "" } = {}) {
  removeCursor();
  const div = document.createElement("div");
  div.className = "line" + (tone ? " " + tone : "");
  div.innerHTML = `<span class="glyph">#</span> ${escapeHtml(text)}`;
  if (cursor) {
    const span = document.createElement("span");
    span.className = "cursor";
    div.appendChild(span);
  }
  feed.appendChild(div);
  scrollToEnd(div);
}

function addPanel(cls, title, innerHTML) {
  removeCursor();
  const div = document.createElement("div");
  div.className = "panel " + cls;
  div.setAttribute("data-title", title);
  div.innerHTML = innerHTML;
  feed.appendChild(div);
  scrollToEnd(div);
}

function addAttempt(payload) {
  addPanel(
    "code",
    `attempt ${payload.attempt}: generated code`,
    `<pre><code>${highlightPython(payload.code)}</code></pre>`
  );

  if (payload.status === "success") {
    const out = payload.output
      ? `<pre><code>${escapeHtml(payload.output)}</code></pre>`
      : `<pre><code>(no stdout)</code></pre>`;
    addPanel("ok", `attempt ${payload.attempt}: output`, out);
  } else {
    const label = payload.status === "timeout" ? "timed out" : `exit code ${payload.exit_code}`;
    const err = payload.error
      ? `<pre><code>${escapeHtml(payload.error)}</code></pre>`
      : `<pre><code>(no stderr)</code></pre>`;
    addPanel("bad", `attempt ${payload.attempt}: error (${label})`, err);
  }
}

function addFinal(succeeded, attempts) {
  removeCursor();
  const div = document.createElement("div");
  div.className = "final " + (succeeded ? "ok" : "failed");
  div.textContent = (succeeded ? "✓ succeeded" : "✗ gave up") + ` after ${attempts} attempt(s)`;
  feed.appendChild(div);
  scrollToEnd(div);
}

document.querySelectorAll(".example-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    taskInput.value = btn.dataset.task;
    taskInput.focus();
  });
});

runBtn.addEventListener("click", async () => {
  const task = taskInput.value;
  const maxAttempts = Number(document.getElementById("maxAttempts").value);
  const timeout = Number(document.getElementById("timeout").value);
  const confirm = document.getElementById("confirm").checked;

  feed.innerHTML = "";
  runBtn.disabled = true;

  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task, max_attempts: maxAttempts, timeout, confirm }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let newlineIndex;
      while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, newlineIndex).trim();
        buffer = buffer.slice(newlineIndex + 1);
        if (!line) continue;

        const event = JSON.parse(line);
        if (event.type === "thinking") {
          addLine(event.message, { cursor: true });
        } else if (event.type === "attempt") {
          addAttempt(event);
        } else if (event.type === "done") {
          addFinal(event.succeeded, event.attempts);
        } else if (event.type === "error") {
          addLine(event.message, { tone: "error-tone" });
        }
      }
    }
  } catch (err) {
    addLine("connection error: " + err.message, { tone: "error-tone" });
  } finally {
    runBtn.disabled = false;
  }
});
