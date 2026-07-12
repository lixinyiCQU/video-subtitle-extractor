const form = document.querySelector("#extractForm");
const platformSelect = document.querySelector("#platform");
const videoUrls = document.querySelector("#videoUrls");
const enableAsr = document.querySelector("#enableAsr");
const enableAsrValue = document.querySelector("#enableAsrValue");
const suppressHfWarnings = document.querySelector("#suppressHfWarnings");
const suppressHfWarningsValue = document.querySelector("#suppressHfWarningsValue");
const statusPill = document.querySelector("#statusPill");
const progressPanel = document.querySelector("#progressPanel");
const progressLabel = document.querySelector("#progressLabel");
const progressPercent = document.querySelector("#progressPercent");
const progressBar = document.querySelector("#progressBar");
const resultPicker = document.querySelector("#resultPicker");
const resultSelect = document.querySelector("#resultSelect");
const batchSummary = document.querySelector("#batchSummary");
const results = document.querySelector("#results");
const timelinePanel = document.querySelector("#timelinePanel");
const contextOutput = document.querySelector("#contextOutput");
const plainOutput = document.querySelector("#plainOutput");
const videoTitle = document.querySelector("#videoTitle");
const videoMeta = document.querySelector("#videoMeta");
const trackList = document.querySelector("#trackList");
const timeline = document.querySelector("#timeline");
const downloadMetadata = document.querySelector("#downloadMetadata");
const downloadSubtitle = document.querySelector("#downloadSubtitle");
const downloadBatch = document.querySelector("#downloadBatch");
const downloadAudio = document.querySelector("#downloadAudio");
const submitButton = form.querySelector("button[type='submit']");

let currentJobId = "";
let completedResults = [];

function setStatus(text, kind = "") {
  statusPill.textContent = text;
  statusPill.className = `status-pill ${kind}`.trim();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatDuration(seconds) {
  if (!seconds) return "Unknown";
  const value = Math.max(Number(seconds) || 0, 0);
  const h = Math.floor(value / 3600);
  const m = Math.floor((value % 3600) / 60);
  const s = Math.floor(value % 60);
  return [h, m, s].map((item) => String(item).padStart(2, "0")).join(":");
}

function platformLabel(platform) {
  return platform === "youtube" ? "YouTube" : "Bilibili";
}

function updatePlatformHints() {
  if (platformSelect.value === "youtube") {
    videoUrls.placeholder = "https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/watch?v=...";
  } else {
    videoUrls.placeholder = "https://www.bilibili.com/video/BV...\nhttps://www.bilibili.com/video/BV...";
  }
}

function setProgress(message, percent) {
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  progressPanel.hidden = false;
  progressLabel.textContent = message || "Working";
  progressPercent.textContent = `${value}%`;
  progressBar.style.width = `${value}%`;
}

function renderMeta(platform, video, selectedTrack, segments) {
  videoMeta.innerHTML = `
    <div><dt>Platform</dt><dd>${escapeHtml(platformLabel(platform))}</dd></div>
    <div><dt>Method</dt><dd>${escapeHtml(selectedTrack.source?.startsWith("asr") ? "Audio ASR" : "Existing subtitle")}</dd></div>
    <div><dt>Title</dt><dd>${escapeHtml(video.title || "Untitled video")}</dd></div>
    <div><dt>Creator</dt><dd>${escapeHtml(video.uploader || "Unknown")}</dd></div>
    <div><dt>Duration</dt><dd>${escapeHtml(formatDuration(video.duration))}</dd></div>
    <div><dt>Selected Track</dt><dd>${escapeHtml(`${selectedTrack.source} / ${selectedTrack.language} / ${selectedTrack.ext}`)}</dd></div>
    <div><dt>Segments</dt><dd>${segments.length}</dd></div>
  `;
}

function renderTracks(tracks, selectedTrack) {
  trackList.innerHTML = tracks
    .map((track) => {
      const active =
        track.language === selectedTrack.language &&
        track.source === selectedTrack.source &&
        track.ext === selectedTrack.ext;
      return `
        <div class="track">
          <strong>${active ? "Selected - " : ""}${escapeHtml(track.language)}</strong>
          ${escapeHtml(track.source)} - ${escapeHtml(track.ext)} - ${escapeHtml(track.name)}
        </div>
      `;
    })
    .join("");
}

function renderTimeline(segments) {
  timeline.innerHTML = segments
    .map(
      (segment) => `
        <div class="timeline-row">
          <div class="timestamp">${escapeHtml(segment.startText)}<br>${escapeHtml(segment.endText)}</div>
          <div class="line-text">${escapeHtml(segment.text)}</div>
        </div>
      `,
    )
    .join("");
}

function renderSelectedResult() {
  const data = completedResults[Number(resultSelect.value) || 0];
  if (!data) return;
  contextOutput.value = data.aiContext;
  plainOutput.value = data.plainText;
  videoTitle.textContent = data.video.title || "Subtitle Context";
  renderMeta(data.platform, data.video, data.selectedTrack, data.segments);
  renderTracks(data.availableTracks, data.selectedTrack);
  renderTimeline(data.segments);
}

function renderBatch(batch) {
  completedResults = batch.items
    .filter((item) => item.status === "completed" && item.result)
    .map((item) => item.result);
  resultSelect.innerHTML = completedResults
    .map((data, index) => `<option value="${index}">${escapeHtml(data.video.title || `Video ${index + 1}`)}</option>`)
    .join("");
  const failures = batch.items.filter((item) => item.status === "failed");
  const savedLocation = batch.outputDirectory
    ? `<div>Saved to: ${escapeHtml(batch.outputDirectory)}</div>`
    : "";
  batchSummary.innerHTML = `Completed ${completedResults.length} of ${batch.total} videos.${savedLocation}` +
    failures.map((item) => `<div class="failed-item">${escapeHtml(item.url)}: ${escapeHtml(item.error)}</div>`).join("");
  downloadBatch.hidden = completedResults.length < 2;
  resultPicker.hidden = completedResults.length === 0;
  results.hidden = completedResults.length === 0;
  timelinePanel.hidden = completedResults.length === 0;
  renderSelectedResult();
}

platformSelect.addEventListener("change", updatePlatformHints);
resultSelect.addEventListener("change", renderSelectedResult);
enableAsr.addEventListener("change", () => {
  enableAsrValue.value = enableAsr.checked ? "true" : "false";
});
suppressHfWarnings.addEventListener("change", () => {
  suppressHfWarningsValue.value = suppressHfWarnings.checked ? "true" : "false";
});
updatePlatformHints();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus("Parsing", "loading");
  setProgress("Queued", 0);
  resultPicker.hidden = true;
  results.hidden = true;
  timelinePanel.hidden = true;
  submitButton.disabled = true;

  const payload = new FormData(form);
  payload.set("enable_asr", enableAsr.checked ? "true" : "false");
  payload.set("suppress_hf_warnings", suppressHfWarnings.checked ? "true" : "false");
  try {
    const response = await fetch("/api/extract/batch/start", {
      method: "POST",
      body: payload,
    });
    const job = await response.json();
    if (!response.ok) {
      throw new Error(job.detail || "Subtitle extraction failed");
    }

    currentJobId = job.id;
    const batch = await waitForJob(job.id);
    renderBatch(batch);
    if (!completedResults.length) {
      throw new Error(batch.items.map((item) => item.error).filter(Boolean).join("\n") || "No video was extracted");
    }
    setStatus("Done");
    setProgress("Done", 100);
  } catch (error) {
    setStatus("Failed", "error");
    setProgress(error.message, 100);
    window.alert(error.message);
  } finally {
    submitButton.disabled = false;
  }
});

downloadAudio.addEventListener("click", async () => {
  const firstUrl = videoUrls.value.split(/\r?\n|,/).map((value) => value.trim()).find(Boolean);
  if (!firstUrl) {
    window.alert("Provide at least one video URL.");
    return;
  }
  setStatus("Downloading", "loading");
  setProgress("Downloading audio locally", 20);
  downloadAudio.disabled = true;
  submitButton.disabled = true;

  const payload = new FormData(form);
  payload.delete("urls");
  payload.set("url", firstUrl);
  try {
    const response = await fetch("/api/audio/download", {
      method: "POST",
      body: payload,
    });
    if (!response.ok) {
      let message = "Audio download failed";
      try {
        const error = await response.json();
        message = error.detail || message;
      } catch {
        message = await response.text();
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename\*?=(?:UTF-8''|\"?)([^\";]+)/i);
    const fallbackName = `${platformSelect.value || "video"}-audio`;
    const filename = match ? decodeURIComponent(match[1].replaceAll('"', "")) : fallbackName;
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus("Done");
    setProgress("Audio downloaded", 100);
  } catch (error) {
    setStatus("Failed", "error");
    setProgress(error.message, 100);
    window.alert(error.message);
  } finally {
    downloadAudio.disabled = false;
    submitButton.disabled = false;
  }
});

async function waitForJob(jobId) {
  while (true) {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
    const job = await response.json();
    if (!response.ok) {
      throw new Error(job.detail || "Failed to read extraction job");
    }
    setProgress(job.message, job.percent);
    if (job.status === "completed") {
      return job.result;
    }
    if (job.status === "failed") {
      throw new Error(job.error || job.message || "Extraction failed");
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
  }
}

document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-copy]");
  if (!target) return;

  const element = document.querySelector(`#${target.dataset.copy}`);
  await navigator.clipboard.writeText(element.value);
  const oldText = target.textContent;
  target.textContent = "Copied";
  window.setTimeout(() => {
    target.textContent = oldText;
  }, 1200);
});

downloadMetadata.addEventListener("click", () => downloadExport("metadata", Number(resultSelect.value) || 0));
downloadSubtitle.addEventListener("click", () => downloadExport("subtitles", Number(resultSelect.value) || 0));
downloadBatch.addEventListener("click", () => downloadExport("bundle"));

async function downloadExport(kind, item) {
  if (!currentJobId) return;
  const params = new URLSearchParams({ kind });
  if (item !== undefined) params.set("item", String(item));
  setStatus("Exporting", "loading");
  try {
    const response = await fetch(`/api/jobs/${encodeURIComponent(currentJobId)}/export?${params}`);
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Export failed");
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const encoded = disposition.match(/filename\*=utf-8''([^;]+)/i);
    const plain = disposition.match(/filename="?([^";]+)"?/i);
    const filename = encoded ? decodeURIComponent(encoded[1]) : (plain?.[1] || "video-subtitles");
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(objectUrl);
    setStatus("Done");
  } catch (error) {
    setStatus("Failed", "error");
    window.alert(error.message);
  }
}
