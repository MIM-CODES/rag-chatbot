/**
 * لایه‌ی ارتباط با بک‌اند FastAPI — بدون هیچ کتابخانه‌ی خارجی.
 * آدرس API همان origin است؛ برای dev روی پورت دیگر، BASE را تغییر دهید.
 */

const BASE = "";

async function readError(response) {
  let message = `خطای سرور (${response.status})`;
  try {
    const body = await response.json();
    if (body && body.detail) {
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    }
  } catch {
    /* پاسخ JSON نبود */
  }
  return message;
}

async function request(path, options = {}) {
  const response = await fetch(BASE + path, options);
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return response.json();
}

export const api = {
  health: () => request("/api/health"),
  listDocuments: () => request("/api/documents"),
  deleteDocument: (docId) =>
    request(`/api/documents/${encodeURIComponent(docId)}`, { method: "DELETE" }),
  chat: (payload) =>
    request("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
};

/** آپلود چند فایل با نمایش درصد پیشرفت واقعی (XHR برای پشتیبانی از progress). */
export function uploadFiles(files, { onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", BASE + "/api/ingest");

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || typeof onProgress !== "function") return;
      onProgress(Math.round((event.loaded / event.total) * 100));
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error("پاسخ سرور قابل خواندن نبود."));
        }
        return;
      }
      let message = `خطای سرور (${xhr.status})`;
      try {
        const body = JSON.parse(xhr.responseText);
        if (body && typeof body.detail === "string") message = body.detail;
      } catch {
        /* ignore */
      }
      reject(new Error(message));
    };

    xhr.onerror = () => reject(new Error("اتصال به سرور برقرار نشد."));
    xhr.ontimeout = () => reject(new Error("آپلود سند زمان‌بر شد و متوقف شد."));
    xhr.send(form);
  });
}

function parseSseBlock(raw) {
  let event = "message";
  const dataLines = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return { event, data: {} };
  }
}

/** خواندن جریان SSE پاسخ چت: event های open / sources / token / done / error. */
export async function* streamChat(payload, signal) {
  const response = await fetch(BASE + "/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    throw new Error(await readError(response));
  }
  if (!response.body) {
    throw new Error("مرورگر از جریان پاسخ پشتیبانی نمی‌کند.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const raw = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = parseSseBlock(raw);
        if (parsed) yield parsed;
        boundary = buffer.indexOf("\n\n");
      }
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      const parsed = parseSseBlock(buffer);
      if (parsed) yield parsed;
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}
