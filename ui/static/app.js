(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const statusLine = $("status-line");
  const uploadPanel = $("upload-panel");
  const uploadHeading = $("upload-heading");
  const uploadForm = $("upload-form");
  const pdfFilesInput = $("pdf-files");
  const uploadSubmit = $("upload-submit");
  const uploadCancel = $("upload-cancel");
  const uploadProgress = $("upload-progress");
  const uploadLog = $("upload-log");
  const scoutsPanel = $("scouts-panel");
  const scoutsTableBody = document.querySelector("#scouts-table tbody");
  const tableWrap = document.querySelector("#scouts-panel .table-wrap");
  const downloadBtn = $("download-btn");
  const pauseResumeBtn = $("pause-resume-btn");
  const reloadPdfsBtn = $("reload-pdfs-btn");
  const downloadProgress = $("download-progress");
  const downloadStatus = $("download-status");
  const runsPanel = $("runs-panel");
  const runsEmpty = $("runs-empty");
  const runsTable = $("runs-table");
  const runsTableBody = document.querySelector("#runs-table tbody");
  const toast = $("toast");

  let scoutRows = [];

  function showToast(message, isError = false) {
    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.hidden = false;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => { toast.hidden = true; }, 5000);
  }

  function setProgress(bar, index, total) {
    bar.hidden = false;
    const pct = total > 0 ? Math.round((index / total) * 100) : 0;
    bar.querySelector(".progress-fill").style.width = `${pct}%`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        if (body.detail) message = body.detail;
      } catch { /* ignore */ }
      throw new Error(message);
    }
    if (response.status === 204) return null;
    return response.json();
  }

  function streamOperation(operationId, onEvent) {
    const source = new EventSource(`/api/operations/${operationId}/events`);
    source.onmessage = (message) => {
      const event = JSON.parse(message.data);
      onEvent(event);
    };
    source.onerror = () => {
      source.close();
    };
    return source;
  }

  // ---- Scouts table / download progress ----

  function renderScoutsTable() {
    scoutsTableBody.innerHTML = scoutRows.map((row, index) => `
      <tr data-index="${index}">
        <td>${escapeHtml(row.name)}</td>
        <td>${escapeHtml(row.registrant_type)}</td>
        <td class="status-cell"><span class="badge pending">Not downloaded yet</span></td>
      </tr>
    `).join("") || `<tr><td colspan="3" class="meta">No scouts found.</td></tr>`;
  }

  function rowFor(index) {
    return scoutsTableBody.querySelector(`tr[data-index="${index}"]`);
  }

  function statusCellFor(index) {
    return rowFor(index)?.querySelector(".status-cell") ?? null;
  }

  function scrollRowIntoView(row) {
    if (!row) return;
    const wrapRect = tableWrap.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    const headerHeight = scoutsTableBody.parentElement.querySelector("thead").offsetHeight;
    if (rowRect.top < wrapRect.top + headerHeight) {
      tableWrap.scrollTop -= (wrapRect.top + headerHeight - rowRect.top);
    } else if (rowRect.bottom > wrapRect.bottom) {
      tableWrap.scrollTop += (rowRect.bottom - wrapRect.bottom);
    }
  }

  async function loadScouts() {
    scoutRows = await fetchJson("/api/scouts");
    renderScoutsTable();
  }

  // ---- Panel visibility per state ----

  async function refreshStatusAndRuns() {
    const [status, runs] = await Promise.all([
      fetchJson("/api/status"),
      fetchJson("/api/runs"),
    ]);
    renderRuns(runs);

    if (status.scouts_csv_exists) {
      statusLine.textContent = `${status.scouts_count} scout(s) loaded — scouts.csv updated ${new Date(status.scouts_mtime).toLocaleString()}`;
      uploadPanel.hidden = true;
      scoutsPanel.hidden = false;
      await loadScouts();
    } else {
      statusLine.textContent = "No scouts.csv yet — upload class-schedule PDFs to get started.";
      uploadPanel.hidden = false;
      uploadHeading.textContent = "Upload class-schedule PDFs";
      uploadCancel.hidden = true;
      scoutsPanel.hidden = true;
    }
  }

  function renderRuns(runs) {
    if (!runs.length) {
      runsEmpty.hidden = false;
      runsTable.hidden = true;
      return;
    }
    runsEmpty.hidden = true;
    runsTable.hidden = false;
    const STALE_MS = 4 * 60 * 60 * 1000;
    runsTableBody.innerHTML = runs.map((run) => {
      const errorBadge = run.scouts_with_errors
        ? `<span class="badge warn">${run.scouts_with_errors}</span>`
        : `<span class="badge success">0</span>`;
      const isStale = run.generated_at_iso &&
        Math.abs(Date.now() - new Date(run.generated_at_iso).getTime()) > STALE_MS;
      const staleBadge = isStale
        ? ` <span class="badge warn" title="Report is over 4 hours old">Stale</span>`
        : "";
      const openButton = run.report_url
        ? `<button type="button" class="secondary open-report" data-run-id="${escapeHtml(run.run_id)}">Open Report</button>`
        : `<span class="meta">No report</span>`;
      return `<tr>
        <td>${escapeHtml(run.run_id)}${staleBadge}</td>
        <td>${escapeHtml(run.scouts_processed)}</td>
        <td>${errorBadge}</td>
        <td>${openButton}</td>
      </tr>`;
    }).join("");
    for (const button of runsTableBody.querySelectorAll(".open-report")) {
      button.addEventListener("click", () => openReport(button.dataset.runId));
    }
  }

  async function openReport(runId) {
    try {
      await fetchJson(`/api/runs/${encodeURIComponent(runId)}/open-report`, { method: "POST" });
      showToast("Opened in your browser.");
    } catch (err) {
      showToast(`Could not open report: ${err.message}`, true);
    }
  }

  // ---- Upload / PDF extraction ----

  uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const files = pdfFilesInput.files;
    if (!files.length) {
      showToast("Choose at least one PDF first.", true);
      return;
    }
    const formData = new FormData();
    for (const file of files) formData.append("files", file);

    uploadSubmit.disabled = true;
    downloadBtn.disabled = true;
    reloadPdfsBtn.disabled = true;
    uploadLog.textContent = "Starting extraction…";

    let operationId;
    try {
      const started = await fetchJson("/api/pdf-extract", { method: "POST", body: formData });
      operationId = started.operation_id;
    } catch (err) {
      showToast(`Could not start extraction: ${err.message}`, true);
      uploadSubmit.disabled = false;
      downloadBtn.disabled = false;
      reloadPdfsBtn.disabled = false;
      return;
    }

    streamOperation(operationId, async (evt) => {
      if (evt.type === "pdf_start") {
        setProgress(uploadProgress, evt.index - 1, evt.total);
        uploadLog.textContent = `Reading ${evt.path}… (${evt.index}/${evt.total})`;
      } else if (evt.type === "batch_done") {
        setProgress(uploadProgress, evt.total ?? 1, evt.total ?? 1);
        uploadLog.textContent = `Wrote ${evt.rows_written} row(s), ${evt.decoded_count} QR code(s) decoded` +
          (evt.warnings ? `, ${evt.warnings} warning(s)` : "");
        showToast(`scouts.csv updated: ${evt.rows_written} scout(s).`);
        uploadSubmit.disabled = false;
        downloadBtn.disabled = false;
        reloadPdfsBtn.disabled = false;
        pdfFilesInput.value = "";
        await refreshStatusAndRuns();
      } else if (evt.type === "error") {
        showToast(`Extraction failed: ${evt.message}`, true);
        uploadLog.textContent = "";
        uploadSubmit.disabled = false;
        downloadBtn.disabled = false;
        reloadPdfsBtn.disabled = false;
      }
    });
  });

  reloadPdfsBtn.addEventListener("click", () => {
    uploadPanel.hidden = false;
    uploadHeading.textContent = "Reload PDFs (replaces scouts.csv)";
    uploadCancel.hidden = false;
    uploadPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  uploadCancel.addEventListener("click", () => {
    uploadPanel.hidden = true;
    uploadCancel.hidden = true;
  });

  // ---- Schedule download ----

  function setPauseResumeState(paused) {
    pauseResumeBtn.dataset.paused = paused ? "true" : "false";
    pauseResumeBtn.textContent = paused ? "Resume" : "Pause after current scout";
  }

  function endDownload() {
    downloadBtn.disabled = false;
    reloadPdfsBtn.disabled = false;
    uploadSubmit.disabled = false;
    pauseResumeBtn.hidden = true;
    pauseResumeBtn.disabled = false;
    downloadStatus.textContent = "";
  }

  pauseResumeBtn.addEventListener("click", async () => {
    const isPaused = pauseResumeBtn.dataset.paused === "true";
    pauseResumeBtn.disabled = true;
    try {
      const result = await fetchJson(`/api/schedule-download/${isPaused ? "resume" : "pause"}`, { method: "POST" });
      setPauseResumeState(result.paused);
      if (result.paused) {
        downloadStatus.textContent = "Pausing — the current scout will finish, then downloading will stop.";
      }
    } catch (err) {
      showToast(`Could not ${isPaused ? "resume" : "pause"}: ${err.message}`, true);
    } finally {
      pauseResumeBtn.disabled = false;
    }
  });

  downloadBtn.addEventListener("click", async () => {
    downloadBtn.disabled = true;
    reloadPdfsBtn.disabled = true;
    uploadSubmit.disabled = true;
    pauseResumeBtn.hidden = false;
    setPauseResumeState(false);
    downloadStatus.textContent = "";

    let started;
    try {
      started = await fetchJson("/api/schedule-download", { method: "POST" });
    } catch (err) {
      showToast(`Could not start download: ${err.message}`, true);
      endDownload();
      return;
    }

    streamOperation(started.operation_id, async (evt) => {
      if (evt.type === "batch_start") {
        setProgress(downloadProgress, 0, evt.total);
      } else if (evt.type === "scout_start") {
        setProgress(downloadProgress, evt.index - 1, evt.total);
        const cell = statusCellFor(evt.index - 1);
        if (cell) cell.innerHTML = `<span class="badge active">Downloading…</span>`;
        scrollRowIntoView(rowFor(evt.index - 1));
      } else if (evt.type === "scout_done") {
        setProgress(downloadProgress, evt.index, evt.total);
        const cell = statusCellFor(evt.index - 1);
        if (cell) {
          const badgeClass = evt.errors ? "warn" : "success";
          cell.innerHTML = `<span class="badge ${badgeClass}">classes=${evt.classes}, requirements=${evt.requirements}` +
            (evt.errors ? `, errors=${evt.errors}` : "") + `</span>`;
        }
      } else if (evt.type === "paused") {
        setPauseResumeState(true);
        downloadStatus.textContent = `Paused before scout ${evt.index}/${evt.total}. Click Resume to continue.`;
      } else if (evt.type === "resumed") {
        setPauseResumeState(false);
        downloadStatus.textContent = "";
      } else if (evt.type === "batch_done") {
        showToast(`Download complete: ${evt.scouts_processed} scout(s), ${evt.scouts_with_errors} with errors.`);
        endDownload();
        await refreshStatusAndRuns();
        if (evt.run_id) openReport(evt.run_id);
      } else if (evt.type === "error") {
        showToast(`Download failed: ${evt.message}`, true);
        endDownload();
      }
    });
  });

  refreshStatusAndRuns().catch((err) => {
    statusLine.textContent = `Failed to load status: ${err.message}`;
  });
})();
