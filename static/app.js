const form = document.querySelector("#extractForm");
const platformSelect = document.querySelector("#platform");
const videoUrl = document.querySelector("#videoUrl");
const enableAsr = document.querySelector("#enableAsr");
const enableAsrValue = document.querySelector("#enableAsrValue");
const suppressHfWarnings = document.querySelector("#suppressHfWarnings");
const suppressHfWarningsValue = document.querySelector("#suppressHfWarningsValue");
const statusPill = document.querySelector("#statusPill");
const progressPanel = document.querySelector("#progressPanel");
const progressLabel = document.querySelector("#progressLabel");
const progressPercent = document.querySelector("#progressPercent");
const progressBar = document.querySelector("#progressBar");
const results = document.querySelector("#results");
const timelinePanel = document.querySelector("#timelinePanel");
const contextOutput = document.querySelector("#contextOutput");
const plainOutput = document.querySelector("#plainOutput");
const videoTitle = document.querySelector("#videoTitle");
const videoMeta = document.querySelector("#videoMeta");
const trackList = document.querySelector("#trackList");
const timeline = document.querySelector("#timeline");
const downloadMarkdown = document.querySelector("#downloadMarkdown");
const submitButton = form.querySelector("button[type='submit']");

let lastMarkdown = "";
let lastTitle = "video-subtitle";

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
    videoUrl.placeholder = "https://www.youtube.com/watch?v=...";
  } else {
    videoUrl.placeholder = "https://www.bilibili.com/video/BV...";
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

platformSelect.addEventListener("change", updatePlatformHints);
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
  results.hidden = true;
  timelinePanel.hidden = true;
  submitButton.disabled = true;

  const payload = new FormData(form);
  payload.set("enable_asr", enableAsr.checked ? "true" : "false");
  payload.set("suppress_hf_warnings", suppressHfWarnings.checked ? "true" : "false");
  try {
    const response = await fetch("/api/extract/start", {
      method: "POST",
      body: payload,
    });
    const job = await response.json();
    if (!response.ok) {
      throw new Error(job.detail || "Subtitle extraction failed");
    }

    const data = await waitForJob(job.id);

    lastMarkdown = data.aiContext;
    lastTitle = `${data.platform || "video"}-${data.video.title || "subtitle"}`
      .replace(/[\\/:*?"<>|]+/g, "_")
      .slice(0, 90);
    contextOutput.value = data.aiContext;
    plainOutput.value = data.plainText;
    videoTitle.textContent = data.video.title || "Subtitle Context";
    renderMeta(data.platform, data.video, data.selectedTrack, data.segments);
    renderTracks(data.availableTracks, data.selectedTrack);
    renderTimeline(data.segments);
    results.hidden = false;
    timelinePanel.hidden = false;
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

downloadMarkdown.addEventListener("click", () => {
  const blob = new Blob([lastMarkdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${lastTitle}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
});
