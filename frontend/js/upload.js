/** منطق آپلود، فهرست و حذف اسناد در پنل کناری. */

import { api, uploadFiles } from "./api.js";

const state = { documents: [], uploading: false };

const els = {
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("file-input"),
  pickBtn: document.getElementById("btn-pick-files"),
  progress: document.getElementById("upload-progress"),
  progressBar: document.getElementById("progress-bar"),
  percent: document.getElementById("upload-percent"),
  status: document.getElementById("upload-status"),
  results: document.getElementById("upload-results"),
  list: document.getElementById("doc-list"),
  empty: document.getElementById("doc-empty"),
  search: document.getElementById("doc-search"),
  count: document.getElementById("doc-count"),
};

const toPersianDigits = (value) =>
  String(value).replace(/[0-9]/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[digit]);

const escapeHtml = (value) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

function formatBytes(bytes) {
  if (!bytes) return "۰";
  const units = ["بایت", "کیلوبایت", "مگابایت"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${toPersianDigits(value.toFixed(unit === 0 ? 0 : 1))} ${units[unit]}`;
}

function formatDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("fa-IR", { year: "numeric", month: "short", day: "numeric" });
}

/* ------------------------------ فهرست اسناد ------------------------------ */

function createDocItem(doc) {
  const item = document.createElement("li");
  item.className = "doc-item";

  const info = document.createElement("div");
  info.className = "doc-info";

  const name = document.createElement("p");
  name.className = "doc-name";
  name.textContent = doc.filename;
  name.title = doc.filename;

  const meta = document.createElement("p");
  meta.className = "doc-meta";
  const parts = [
    `${toPersianDigits(doc.chunks)} قطعه`,
    doc.pages ? `${toPersianDigits(doc.pages)} صفحه` : null,
    formatBytes(doc.size_bytes),
    formatDate(doc.indexed_at),
  ].filter(Boolean);
  meta.textContent = parts.join(" · ");

  info.append(name, meta);

  if (doc.warning) {
    const warning = document.createElement("p");
    warning.className = "doc-warning";
    warning.textContent = doc.warning;
    info.appendChild(warning);
  }

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "doc-delete";
  remove.title = "حذف سند";
  remove.setAttribute("aria-label", `حذف سند ${doc.filename}`);
  remove.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13h10l1-13M10 11v6M14 11v6"/></svg>';
  remove.addEventListener("click", () => deleteDocument(doc));

  item.append(info, remove);
  return item;
}

function renderList() {
  const query = els.search.value.trim().toLowerCase();
  const documents = state.documents.filter(
    (doc) => !query || doc.filename.toLowerCase().includes(query),
  );

  els.count.textContent = toPersianDigits(state.documents.length);
  els.list.innerHTML = "";

  if (!state.documents.length) {
    els.empty.hidden = false;
    els.empty.textContent = "هنوز سندی ایندکس نشده است.";
    return;
  }
  els.empty.hidden = documents.length > 0;
  if (!documents.length) els.empty.textContent = "سندی با این نام پیدا نشد.";

  for (const doc of documents) els.list.appendChild(createDocItem(doc));
}

async function loadDocuments() {
  try {
    state.documents = await api.listDocuments();
  } catch (error) {
    state.documents = [];
    els.empty.hidden = false;
    els.empty.textContent = `دریافت فهرست اسناد ناموفق بود: ${error.message}`;
    return;
  }
  renderList();
  window.dispatchEvent(new CustomEvent("documents:updated", { detail: state.documents }));
}

async function deleteDocument(doc) {
  const confirmed = window.confirm(
    `سند «${doc.filename}» و همه‌ی قطعه‌های آن از پایگاه دانش حذف شود؟`,
  );
  if (!confirmed) return;

  try {
    await api.deleteDocument(doc.doc_id);
    await loadDocuments();
  } catch (error) {
    window.alert(`حذف سند ناموفق بود: ${error.message}`);
  }
}

/* ------------------------------ آپلود ------------------------------ */

function setProgress(percent, label) {
  els.progressBar.style.width = `${percent}%`;
  els.percent.textContent = `${toPersianDigits(percent)}٪`;
  if (label) els.status.textContent = label;
}

function renderResults(results) {
  els.results.innerHTML = "";
  for (const result of results) {
    const item = document.createElement("li");
    item.className = `upload-result ${result.status === "indexed" ? "is-ok" : "is-error"}`;
    const title = document.createElement("strong");
    title.textContent = result.filename;

    const detail = document.createElement("span");
    if (result.status === "indexed") {
      detail.textContent = ` — ${toPersianDigits(result.chunks)} قطعه ایندکس شد`;
    } else {
      detail.textContent = ` — ${result.error || "خطا در پردازش"}`;
    }

    item.append(title, detail);
    if (result.warning) {
      const warning = document.createElement("span");
      warning.className = "upload-warning";
      warning.textContent = ` ⚠ ${result.warning}`;
      item.appendChild(warning);
    }
    els.results.appendChild(item);
  }
}

async function handleFiles(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length || state.uploading) return;

  state.uploading = true;
  els.results.innerHTML = "";
  els.progress.classList.remove("hidden");
  setProgress(0, "در حال آپلود…");

  try {
    const response = await uploadFiles(files, {
      onProgress: (percent) =>
        setProgress(
          percent,
          percent < 100 ? "در حال آپلود…" : "در حال پردازش و ایندکس…",
        ),
    });
    setProgress(100, "پایان پردازش");
    renderResults(response.results || []);
    await loadDocuments();
  } catch (error) {
    els.results.innerHTML = `<li class="upload-result is-error">${escapeHtml(error.message)}</li>`;
  } finally {
    state.uploading = false;
    els.fileInput.value = "";
    setTimeout(() => els.progress.classList.add("hidden"), 900);
  }
}

/* ------------------------------ رویدادها ------------------------------ */

els.pickBtn.addEventListener("click", (event) => {
  event.stopPropagation();
  els.fileInput.click();
});

els.dropzone.addEventListener("click", () => els.fileInput.click());

els.dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    els.fileInput.click();
  }
});

els.fileInput.addEventListener("change", (event) => handleFiles(event.target.files));

for (const type of ["dragenter", "dragover"]) {
  els.dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    els.dropzone.classList.add("is-dragover");
  });
}

for (const type of ["dragleave", "dragend", "drop"]) {
  els.dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    els.dropzone.classList.remove("is-dragover");
  });
}

els.dropzone.addEventListener("drop", (event) => {
  if (event.dataTransfer?.files?.length) handleFiles(event.dataTransfer.files);
});

els.search.addEventListener("input", renderList);

loadDocuments();
