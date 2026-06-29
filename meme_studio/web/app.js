const state = {
  projectId: null,
  frames: [],
  slots: [],
  current: 0,
  drag: null,
  templates: [],
};

const queryParams = new URLSearchParams(window.location.search);
const queryToken = queryParams.get("token") || "";
const authToken = queryToken || localStorage.getItem("memeStudioToken") || "";
if (queryToken) {
  localStorage.setItem("memeStudioToken", queryToken);
}

const els = {
  status: document.getElementById("status"),
  commandName: document.getElementById("commandName"),
  message: document.getElementById("message"),
  outputType: document.getElementById("outputType"),
  shape: document.getElementById("shape"),
  fileInput: document.getElementById("fileInput"),
  uploadButton: document.getElementById("uploadButton"),
  copyButton: document.getElementById("copyButton"),
  previewButton: document.getElementById("previewButton"),
  exportButton: document.getElementById("exportButton"),
  applyButton: document.getElementById("applyButton"),
  newTemplateButton: document.getElementById("newTemplateButton"),
  refreshTemplatesButton: document.getElementById("refreshTemplatesButton"),
  frameImage: document.getElementById("frameImage"),
  canvasWrap: document.getElementById("canvasWrap"),
  empty: document.querySelector(".empty"),
  slot: document.getElementById("slot"),
  timeline: document.getElementById("timeline"),
  rotation: document.getElementById("rotation"),
  rotationValue: document.getElementById("rotationValue"),
  templateList: document.getElementById("templateList"),
  resultPreview: document.getElementById("resultPreview"),
  resultBox: document.getElementById("resultBox"),
};

els.uploadButton.addEventListener("click", uploadFiles);
els.copyButton.addEventListener("click", copySlotToAll);
els.previewButton.addEventListener("click", previewCurrentTemplate);
els.exportButton.addEventListener("click", () => submitTemplate("/api/export"));
els.applyButton.addEventListener("click", () => submitTemplate("/api/apply"));
els.newTemplateButton.addEventListener("click", resetNewTemplate);
els.refreshTemplatesButton.addEventListener("click", () => loadTemplates());
els.shape.addEventListener("change", renderSlot);
els.rotation.addEventListener("input", () => {
  const slot = currentSlot();
  if (!slot) return;
  slot.rotation = Number(els.rotation.value);
  els.rotationValue.textContent = String(slot.rotation);
  renderSlot();
});
els.frameImage.addEventListener("load", renderSlot);
window.addEventListener("resize", renderSlot);

els.slot.addEventListener("pointerdown", (event) => {
  if (!currentSlot()) return;
  const rect = imageMetrics();
  if (!rect) return;
  els.slot.setPointerCapture(event.pointerId);
  state.drag = {
    mode: event.target.classList.contains("handle") ? "resize" : "move",
    startX: event.clientX,
    startY: event.clientY,
    slot: {...currentSlot()},
    metrics: rect,
  };
});

els.slot.addEventListener("pointermove", (event) => {
  if (!state.drag) return;
  const slot = currentSlot();
  const frame = currentFrame();
  if (!slot || !frame) return;
  const dx = (event.clientX - state.drag.startX) / state.drag.metrics.scale;
  const dy = (event.clientY - state.drag.startY) / state.drag.metrics.scale;
  const nextSlot = {...slot};

  if (state.drag.mode === "move") {
    nextSlot.x = Math.round(state.drag.slot.x + dx);
    nextSlot.y = Math.round(state.drag.slot.y + dy);
  } else {
    nextSlot.width = Math.max(8, Math.round(state.drag.slot.width + dx));
    nextSlot.height = Math.max(8, Math.round(state.drag.slot.height + dy));
  }
  Object.assign(slot, clampSlotToFrame(nextSlot, frame));
  renderSlot();
});

els.slot.addEventListener("pointerup", () => {
  state.drag = null;
});
els.slot.addEventListener("pointercancel", () => {
  state.drag = null;
});
els.slot.addEventListener("lostpointercapture", () => {
  state.drag = null;
});

loadTemplates(false).catch((error) => setStatus(error.message));

async function uploadFiles() {
  try {
    const files = [...els.fileInput.files];
    if (!files.length) {
      setStatus("请选择素材");
      return;
    }

    setStatus("上传中...");
    const payload = {files: await Promise.all(files.map(readFilePayload))};
    const project = await postJson("/api/upload", payload);
    state.projectId = project.project_id;
    state.frames = project.frames;
    state.slots = project.frames.map(defaultSlotForFrame);
    state.current = 0;
    els.outputType.value = project.frames.length > 1 ? "gif" : "png";
    enableButtons(true);
    renderTimeline();
    renderFrame();
    setStatus(`已载入 ${project.frames.length} 帧`);
  } catch (error) {
    setStatus(error.message);
  }
}

function readFilePayload(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({name: file.name, data: reader.result});
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function defaultSlotForFrame(frame) {
  const side = Math.round(Math.min(frame.width, frame.height) * 0.34);
  return {
    x: Math.round((frame.width - side) / 2),
    y: Math.round((frame.height - side) / 2),
    width: side,
    height: side,
    rotation: 0,
  };
}

function renderTimeline() {
  els.timeline.innerHTML = "";
  state.frames.forEach((frame, index) => {
    const button = document.createElement("button");
    button.className = `frame-button${index === state.current ? " active" : ""}`;
    button.textContent = `${index + 1} 帧\n${frame.duration_ms}ms`;
    button.addEventListener("click", () => {
      state.current = index;
      renderTimeline();
      renderFrame();
    });
    els.timeline.appendChild(button);
  });
}

function renderFrame() {
  if (!state.frames.length) return;
  const fileName = state.frames[state.current].file.split("/").pop();
  els.frameImage.src = withAuthToken(`/api/projects/${state.projectId}/frames/${encodeURIComponent(fileName)}`);
  els.frameImage.style.display = "block";
  els.empty.style.display = "none";
  els.rotation.value = String(currentSlot().rotation);
  els.rotationValue.textContent = String(currentSlot().rotation);
}

function renderSlot() {
  const slot = currentSlot();
  const frame = currentFrame();
  const metrics = imageMetrics();
  if (!slot || !frame || !metrics) return;
  Object.assign(slot, clampSlotToFrame(slot, frame));

  els.slot.className = `slot ${els.shape.value}`;
  els.slot.style.display = "block";
  els.slot.style.left = `${metrics.left + slot.x * metrics.scale}px`;
  els.slot.style.top = `${metrics.top + slot.y * metrics.scale}px`;
  els.slot.style.width = `${slot.width * metrics.scale}px`;
  els.slot.style.height = `${slot.height * metrics.scale}px`;
  els.slot.style.transform = `rotate(${slot.rotation}deg)`;
}

function imageMetrics() {
  if (!els.frameImage.naturalWidth) return null;
  const imageRect = els.frameImage.getBoundingClientRect();
  const wrapRect = els.canvasWrap.getBoundingClientRect();
  return {
    left: imageRect.left - wrapRect.left,
    top: imageRect.top - wrapRect.top,
    scale: imageRect.width / els.frameImage.naturalWidth,
  };
}

function currentSlot() {
  return state.slots[state.current];
}

function currentFrame() {
  return state.frames[state.current];
}

function clampSlotToFrame(slot, frame) {
  const frameWidth = Math.max(1, Math.round(Number(frame.width) || 1));
  const frameHeight = Math.max(1, Math.round(Number(frame.height) || 1));
  const width = clampNumber(Math.round(Number(slot.width) || 8), 8, frameWidth);
  const height = clampNumber(Math.round(Number(slot.height) || 8), 8, frameHeight);
  const x = clampNumber(Math.round(Number(slot.x) || 0), 0, Math.max(0, frameWidth - width));
  const y = clampNumber(Math.round(Number(slot.y) || 0), 0, Math.max(0, frameHeight - height));
  const rotation = Number.isFinite(Number(slot.rotation)) ? Number(slot.rotation) : 0;
  return {x, y, width, height, rotation};
}

function clampNumber(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function copySlotToAll() {
  const slot = currentSlot();
  if (!slot) return;
  state.slots = state.slots.map(() => ({...slot}));
  setStatus("已复制到全部帧");
}

async function submitTemplate(endpoint) {
  try {
    if (!state.projectId) return;
    const payload = {project_id: state.projectId, manifest: buildManifest()};
    const result = await postJson(endpoint, payload);
    hideResultPreview();
    els.resultBox.textContent = result.path || JSON.stringify(result, null, 2);
    if (endpoint.endsWith("apply")) {
      state.templates = result.templates || state.templates;
      await loadTemplates(false);
      setStatus("已应用到机器人");
      return;
    }
    setStatus("已导出");
  } catch (error) {
    setStatus(error.message);
  }
}

async function previewCurrentTemplate() {
  try {
    if (!state.projectId) return;
    setStatus("生成预览中...");
    const payload = {project_id: state.projectId, manifest: buildManifest()};
    const result = await postJson("/api/preview-current", payload);
    showResultPreview(result.preview_url, "当前模板预览");
    els.resultBox.textContent = "当前模板预览使用 logo 作为头像生成。";
    setStatus("预览已生成");
  } catch (error) {
    setStatus(error.message);
  }
}

function buildManifest() {
  return {
    version: 1,
    command: els.commandName.value.trim(),
    output: els.outputType.value,
    message: els.message.value.trim() || "正在生成...",
    duration_ms: 80,
    avatar: {shape: els.shape.value, fit: "cover"},
    frames: state.frames.map((frame, index) => ({
      file: frame.file,
      duration_ms: frame.duration_ms,
      slot: clampSlotToFrame(state.slots[index], frame),
    })),
  };
}

async function postJson(url, payload) {
  const headers = {"Content-Type": "application/json"};
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }
  const response = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

async function getJson(url) {
  const headers = authToken ? {Authorization: `Bearer ${authToken}`} : {};
  const response = await fetch(url, {headers});
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

async function loadTemplates(showStatus = true) {
  try {
    if (showStatus) setStatus("读取机器人表情...");
    const data = await getJson("/api/templates");
    state.templates = data.templates || [];
    renderTemplateList();
    if (showStatus) setStatus(`已读取 ${state.templates.length} 个机器人表情`);
  } catch (error) {
    setStatus(error.message);
  }
}

function renderTemplateList() {
  els.templateList.innerHTML = "";
  if (!state.templates.length) {
    const empty = document.createElement("div");
    empty.className = "template-empty";
    empty.textContent = "暂无已加入的表情";
    els.templateList.appendChild(empty);
    return;
  }

  state.templates.forEach((template) => {
    const item = document.createElement("div");
    item.className = `template-item${template.exists ? "" : " missing"}`;

    const preview = document.createElement("img");
    preview.className = "template-preview";
    preview.loading = "lazy";
    preview.alt = `/${template.name} 预览`;
    preview.src = withAuthToken(template.preview_url);
    preview.addEventListener("click", () => showTemplateDetails(template));

    const info = document.createElement("div");
    info.className = "template-info";
    const name = document.createElement("strong");
    name.textContent = `/${template.name}`;
    const meta = document.createElement("span");
    meta.textContent = templateMetaText(template);
    info.append(name, meta);

    const buttons = document.createElement("div");
    buttons.className = "template-actions";
    const viewButton = document.createElement("button");
    viewButton.className = "secondary-button small-button";
    viewButton.textContent = "查看";
    viewButton.addEventListener("click", () => showTemplateDetails(template));
    buttons.appendChild(viewButton);
    if (template.deletable) {
      const deleteButton = document.createElement("button");
      deleteButton.className = "danger-button small-button";
      deleteButton.textContent = "删除";
      deleteButton.addEventListener("click", () => deleteTemplate(template));
      buttons.appendChild(deleteButton);
    }
    item.append(preview, info, buttons);
    els.templateList.appendChild(item);
  });
}

function templateMetaText(template) {
  const source = template.source === "builtin" ? "内置" : "新增";
  const people = template.is_double ? "双人" : "单人";
  const output = String(template.output || "").toUpperCase() || "未知";
  if (template.source === "generated") {
    return `${source} · ${output} · ${template.frame_count} 帧`;
  }
  return `${source} · ${people} · ${output}`;
}

function showTemplateDetails(template) {
  const source = template.source === "builtin" ? "内置脚本" : "制作器新增";
  showResultPreview(template.preview_url, `/${template.name} 预览`);
  els.resultBox.textContent = [
    `指令：/${template.name}`,
    `来源：${source}`,
    `输出：${String(template.output).toUpperCase()}`,
    `类型：${template.is_double ? "双人表情" : "单人表情"}`,
    template.source === "generated" ? `帧数：${template.frame_count}` : `脚本：${template.script}`,
    `头像形状：${template.avatar_shape || "未记录"}`,
    `提示语：${template.message || "未记录"}`,
    `素材状态：${template.exists ? "完整" : "缺失"}`,
    template.manifest ? `模板文件：${template.manifest}` : "模板文件：内置脚本生成",
    `本地目录：${template.data_path}`,
    `删除权限：${template.deletable ? "可删除" : "内置表情不可在此删除"}`,
  ].join("\n");
  setStatus(`正在查看 /${template.name}`);
}

async function deleteTemplate(template) {
  if (!template.deletable) {
    setStatus("内置表情不可在制作器中删除");
    return;
  }
  const confirmed = window.confirm(`确认删除「/${template.name}」吗？\n这会删除机器人里的这个新增表情。`);
  if (!confirmed) return;

  try {
    setStatus("删除中...");
    const result = await postJson("/api/delete-template", {command: template.name});
    state.templates = result.templates || [];
    renderTemplateList();
    hideResultPreview();
    els.resultBox.textContent = `已删除：/${result.deleted}\n目录：${result.path}`;
    setStatus(`已删除 /${result.deleted}`);
  } catch (error) {
    setStatus(error.message);
  }
}

function resetNewTemplate() {
  const names = new Set(state.templates.map((template) => template.name));
  let nextName = "新表情";
  let index = 2;
  while (names.has(nextName)) {
    nextName = `新表情${index}`;
    index += 1;
  }

  state.projectId = null;
  state.frames = [];
  state.slots = [];
  state.current = 0;
  state.drag = null;
  els.commandName.value = nextName;
  els.message.value = "正在生成...";
  els.outputType.value = "gif";
  els.shape.value = "circle";
  els.fileInput.value = "";
  els.timeline.innerHTML = "";
  els.frameImage.removeAttribute("src");
  els.frameImage.style.display = "none";
  els.slot.style.display = "none";
  els.empty.style.display = "block";
  hideResultPreview();
  els.resultBox.textContent = "";
  els.rotation.value = "0";
  els.rotationValue.textContent = "0";
  enableButtons(false);
  setStatus("准备新增表情");
  els.commandName.focus();
}

function enableButtons(enabled) {
  els.copyButton.disabled = !enabled;
  els.previewButton.disabled = !enabled;
  els.exportButton.disabled = !enabled;
  els.applyButton.disabled = !enabled;
}

function showResultPreview(src, alt) {
  els.resultPreview.src = withAuthToken(src);
  els.resultPreview.alt = alt;
  els.resultPreview.style.display = "block";
}

function hideResultPreview() {
  els.resultPreview.removeAttribute("src");
  els.resultPreview.alt = "";
  els.resultPreview.style.display = "none";
}

function setStatus(text) {
  els.status.textContent = text;
}

function withAuthToken(url) {
  if (!authToken) {
    return url;
  }
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}token=${encodeURIComponent(authToken)}`;
}

if (typeof window !== "undefined") {
  window.__memeStudioTest = {clampSlotToFrame};
}
