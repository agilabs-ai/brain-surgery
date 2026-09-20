(function () {
  "use strict";
  const $ = (selector) => document.querySelector(selector);
  const state = { mode: "upload", files: [], result: null };
  const views = { input: $("#input-view"), loading: $("#loading-view"), result: $("#result-view") };

  function showView(name) {
    Object.entries(views).forEach(([key, el]) => { el.hidden = key !== name; });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
    state.mode = tab.dataset.mode;
    document.querySelectorAll(".tab").forEach((item) => { item.classList.toggle("active", item === tab); item.setAttribute("aria-selected", item === tab ? "true" : "false"); });
    $("#upload-mode").hidden = state.mode !== "upload";
    $("#paste-mode").hidden = state.mode !== "paste";
    $("#input-error").hidden = true;
  }));

  const input = $("#file-input");
  $("#file-button").addEventListener("click", () => input.click());
  input.addEventListener("change", () => setFiles([...input.files]));
  const drop = $("#drop-zone");
  ["dragenter", "dragover"].forEach((name) => drop.addEventListener(name, (event) => { event.preventDefault(); $("#file-button").classList.add("drag"); }));
  ["dragleave", "drop"].forEach((name) => drop.addEventListener(name, (event) => { event.preventDefault(); $("#file-button").classList.remove("drag"); }));
  drop.addEventListener("drop", (event) => setFiles([...event.dataTransfer.files]));

  function setFiles(files) {
    const allowed = files.filter((file) => /\.(jsonl|json|txt|log)$/i.test(file.name) && file.size <= 25 * 1024 * 1024).slice(0, 20);
    state.files = allowed;
    $("#file-list").textContent = allowed.length ? `${allowed.length} file${allowed.length === 1 ? "" : "s"} ready · ${allowed.map((file) => file.name).join(" · ")}` : "";
  }

  async function readInput() {
    if (state.mode === "paste") return $("#prompt-input").value;
    if (!state.files.length) throw new Error("Choose at least one session log, or switch to Paste prompts.");
    return (await Promise.all(state.files.map((file) => file.text()))).join("\n");
  }

  $("#analyze-button").addEventListener("click", async () => {
    const error = $("#input-error");
    error.hidden = true;
    try {
      const raw = await readInput();
      state.result = GapAnalyzer.analyze(raw);
      showView("loading");
      const messages = ["Finding recurring task categories…", "Separating evidence from missing data…", "Matching skills to observed gaps…", "Building your share card…"];
      let index = 0;
      const timer = setInterval(() => { index += 1; if (index < messages.length) $("#loading-message").textContent = messages[index]; }, 320);
      setTimeout(() => { clearInterval(timer); renderResult(state.result); showView("result"); }, 1350);
    } catch (err) {
      error.textContent = err.message || "This sample could not be analyzed.";
      error.hidden = false;
    }
  });

  function renderResult(result) {
    $("#result-headline").textContent = result.headline;
    $("#sample-size").textContent = `${result.entries} entries read`;
    $("#surprising").textContent = result.surprising;
    $("#category-list").innerHTML = result.categories.map((item) => `<div class="category-row"><div><span>${escapeHtml(item.label)}</span><span class="evidence">${item.tasks ? `${item.tasks} relevant · ${item.friction} friction signal${item.friction === 1 ? "" : "s"}` : "No relevant evidence"}</span></div><strong class="rating ${item.level.toLowerCase().replace(/\s+/g, "-")}">${item.level}</strong></div>`).join("");
    $("#recommendation-count").textContent = result.recommended.length;
    $("#skill-list").innerHTML = result.recommended.length ? result.recommended.map((item) => `<li>${escapeHtml(item.skill)}<span>${escapeHtml(item.category)} · ${escapeHtml(item.urgency)}</span></li>`).join("") : "<li>No urgent additions from this sample.<span>Keep collecting evidence.</span></li>";
    drawCard(result);
  }

  function escapeHtml(value) { const node = document.createElement("span"); node.textContent = value; return node.innerHTML; }

  function wrapText(ctx, text, x, y, maxWidth, lineHeight, maxLines) {
    const words = text.split(/\s+/); let line = ""; let lines = 0;
    for (let i = 0; i < words.length; i += 1) {
      const test = `${line}${line ? " " : ""}${words[i]}`;
      if (ctx.measureText(test).width > maxWidth && line) { ctx.fillText(line, x, y); y += lineHeight; lines += 1; line = words[i]; if (lines === maxLines - 1) break; }
      else line = test;
    }
    if (line && lines < maxLines) ctx.fillText(line, x, y);
  }

  function drawCard(result) {
    const canvas = $("#share-card"); const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#080808"; ctx.fillRect(0, 0, 1200, 630);
    const glow = ctx.createRadialGradient(1030, 110, 10, 1030, 110, 420); glow.addColorStop(0, "rgba(23,105,255,.55)"); glow.addColorStop(1, "rgba(23,105,255,0)"); ctx.fillStyle = glow; ctx.fillRect(600, 0, 600, 630);
    ctx.fillStyle = "#ffffff"; ctx.font = "700 25px Arial"; ctx.fillText("EDGE", 64, 66);
    ctx.fillStyle = "#8faef5"; ctx.font = "700 17px ui-monospace, monospace"; ctx.fillText("AGENT SKILLS GAP TEST", 64, 112);
    ctx.fillStyle = "#ffffff"; ctx.font = "700 56px Arial"; wrapText(ctx, result.headline, 64, 190, 720, 62, 3);
    const shown = result.categories.filter((item) => item.level !== "Not measured").slice(0, 4);
    let y = 405; ctx.font = "600 21px Arial";
    for (const item of shown) {
      ctx.fillStyle = "#d0d0d0"; ctx.fillText(item.label, 64, y);
      ctx.fillStyle = item.level === "Covered" ? "#62d49b" : item.level === "Critical" ? "#ff6961" : item.level === "Weak" ? "#ff9a50" : "#77a6ff";
      ctx.font = "800 18px ui-monospace, monospace"; ctx.textAlign = "right"; ctx.fillText(item.level.toUpperCase(), 760, y); ctx.textAlign = "left"; ctx.font = "600 21px Arial"; y += 42;
    }
    ctx.fillStyle = "rgba(255,255,255,.12)"; ctx.fillRect(830, 68, 1, 490);
    ctx.fillStyle = "#fff"; ctx.font = "800 118px Arial"; ctx.fillText(String(result.recommended.length), 894, 245);
    ctx.fillStyle = "#8faef5"; ctx.font = "700 18px ui-monospace, monospace"; ctx.fillText("RECOMMENDED", 895, 287); ctx.fillText("SKILLS", 895, 314);
    ctx.fillStyle = "#aaa"; ctx.font = "500 17px Arial"; wrapText(ctx, `${result.entries} private entries analyzed locally.`, 895, 375, 230, 25, 3);
    ctx.fillStyle = "#fff"; ctx.font = "700 18px Arial"; ctx.fillText("getedge.cc", 895, 520);
  }

  $("#download-card").addEventListener("click", () => { const link = document.createElement("a"); link.download = "my-agent-skills-gap.png"; link.href = $("#share-card").toDataURL("image/png"); link.click(); });
  $("#copy-caption").addEventListener("click", async () => { const text = `${state.result.headline}\n\nI ran the Agent Skills Gap Test. ${state.result.recommended.length} skills could improve my setup.\n\nWhat is your AI terrible at?`; await navigator.clipboard.writeText(text); $("#copy-caption").textContent = "Copied"; setTimeout(() => { $("#copy-caption").textContent = "Copy caption"; }, 1400); });
  $("#start-over").addEventListener("click", () => showView("input"));
  const dialog = $("#privacy-dialog");
  $("#privacy-button").addEventListener("click", () => dialog.showModal());
  $(".dialog-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
})();
