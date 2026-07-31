(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("report-data").textContent);
  const classes = data.classes || [];
  const requirements = data.requirements || [];
  const scouts = data.scouts || [];
  const dayOrder = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
  const dayLabels = {Mo:"Monday", Tu:"Tuesday", We:"Wednesday", Th:"Thursday", Fr:"Friday", Sa:"Saturday", Su:"Sunday"};
  const state = { classSort: {key:"scout_name", desc:false}, reqSort: {key:"scout_name", desc:false} };

  const $ = id => document.getElementById(id);
  const escapeHtml = value => String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const boolBadge = (value, yes="Complete", no="Incomplete") => value
    ? `<span class="badge success">${escapeHtml(yes)}</span>`
    : `<span class="badge warn">${escapeHtml(no)}</span>`;
  const requirementBadge = item => {
    const reason = escapeHtml(item.calculated_status_reason || "");
    if (item.calculated_status === "complete") {
      return `<span class="badge success" title="${reason}">Completed</span>`;
    }
    if (item.calculated_status === "complete_check") {
      return `<span class="badge check" title="${reason}">Completed, but double check</span>`;
    }
    return `<span class="badge warn" title="${reason}">Not complete</span>`;
  };
  const requirementIsComplete = item => ["complete", "complete_check"].includes(item.calculated_status);
  const isPrereqRequirement = item => normalize(item.description).includes("(pre-req)");
  const tokensForDays = value => dayOrder.filter(token => String(value || "").includes(token));
  const normalize = value => String(value ?? "").trim().toLocaleLowerCase();
  const uniqueSorted = values => [...new Set(values.filter(Boolean))].sort((a,b) => a.localeCompare(b, undefined, {numeric:true}));
  const reqKey = item => `${item.scout_name}\u0000${item.class_p4_id}`;
  const requirementsByClass = new Map();
  for (const req of requirements) {
    const key = reqKey(req);
    if (!requirementsByClass.has(key)) requirementsByClass.set(key, []);
    requirementsByClass.get(key).push(req);
  }

  const generatedEl = $("generated-at");
  generatedEl.textContent = `Generated ${data.generated_at_local || ""}`;
  if (data.generated_at_iso) {
    const ageMs = Math.abs(Date.now() - new Date(data.generated_at_iso).getTime());
    if (Number.isFinite(ageMs) && ageMs > 4 * 60 * 60 * 1000) {
      generatedEl.classList.add("stale");
      generatedEl.insertAdjacentHTML("beforeend", ` — <strong>this report may be out of date; consider re-running it.</strong>`);
    }
  }

  const emailStatusEl = $("email-status");
  const generateEmailsBtn = $("generate-emails-btn");
  const openEmailsFolderBtn = $("open-emails-folder-btn");

  async function apiPost(path) {
    const response = await fetch(path, { method: "POST" });
    let body = null;
    try { body = await response.json(); } catch { /* ignore */ }
    if (!response.ok) {
      throw new Error(body?.detail || `${response.status} ${response.statusText}`);
    }
    return body;
  }

  generateEmailsBtn.addEventListener("click", async () => {
    generateEmailsBtn.disabled = true;
    emailStatusEl.textContent = "Generating emails…";
    try {
      const result = await apiPost(`/api/runs/${encodeURIComponent(data.run_id || "")}/generate-emails`);
      emailStatusEl.textContent =
        `${result.scouts_needing_email} scout(s) need an email, ${result.scouts_all_complete} fully complete.`;
    } catch (err) {
      emailStatusEl.textContent =
        "Could not generate emails. Open this report through the Scout Schedule app to use this feature.";
    } finally {
      generateEmailsBtn.disabled = false;
    }
  });

  openEmailsFolderBtn.addEventListener("click", async () => {
    openEmailsFolderBtn.disabled = true;
    try {
      await apiPost(`/api/runs/${encodeURIComponent(data.run_id || "")}/open-emails-folder`);
      emailStatusEl.textContent = "Opened the emails folder.";
    } catch (err) {
      emailStatusEl.textContent = /not.*generated/i.test(err.message)
        ? "Generate emails first."
        : "Could not open the emails folder. Open this report through the Scout Schedule app to use this feature.";
    } finally {
      openEmailsFolderBtn.disabled = false;
    }
  });

  $("summary").innerHTML = [
    [scouts.length, "Scouts"],
    [classes.length, "Scheduled classes"],
    [requirements.length, "Requirements"],
    [data.errors?.length || 0, "Errors"]
  ].map(([value,label]) => `<div class="summary-card"><div class="value">${value}</div><div class="label">${label}</div></div>`).join("");

  function fillSelect(id, values, labels = null) {
    const select = $(id);
    for (const value of values) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = labels?.[value] || value;
      select.appendChild(option);
    }
  }
  fillSelect("scout-filter", uniqueSorted(scouts.map(s => s.name)));
  fillSelect("class-filter", uniqueSorted(classes.map(c => c.class_name)));
  fillSelect("block-filter", uniqueSorted(classes.map(c => c.period_name)));
  fillSelect("day-filter", dayOrder.filter(day => classes.some(c => tokensForDays(c.days).includes(day))), dayLabels);
  fillSelect("location-filter", uniqueSorted(classes.map(c => c.location)));

  function filters() {
    return {
      search: normalize($("search").value), scout: $("scout-filter").value,
      className: $("class-filter").value, block: $("block-filter").value,
      day: $("day-filter").value, location: $("location-filter").value,
      completion: $("completion-filter").value,
      showCompletedRequirements: $("show-completed-requirements").checked,
      prereqOnly: $("prereq-filter").checked
    };
  }

  function classMatches(item, f = filters()) {
    const haystack = normalize([item.scout_name, item.class_name, item.class_number, item.location, item.period_name, item.days].join(" "));
    return (!f.search || haystack.includes(f.search))
      && (!f.scout || item.scout_name === f.scout)
      && (!f.className || item.class_name === f.className)
      && (!f.block || item.period_name === f.block)
      && (!f.day || tokensForDays(item.days).includes(f.day))
      && (!f.location || item.location === f.location)
      && (!f.completion || (f.completion === "complete") === Boolean(item.class_completed));
  }

  function requirementMatches(item, f = filters()) {
    const linkedClass = classes.find(c => c.scout_name === item.scout_name && c.class_p4_id === item.class_p4_id);
    const haystack = normalize([item.scout_name, item.merit_badge_name, item.class_number, item.requirement_number, item.description, item.present_days].join(" "));
    return (!f.search || haystack.includes(f.search))
      && (!f.scout || item.scout_name === f.scout)
      && (!f.className || item.merit_badge_name === f.className || linkedClass?.class_name === f.className)
      && (!f.block || linkedClass?.period_name === f.block)
      && (!f.day || tokensForDays(item.present_days).includes(f.day) || tokensForDays(linkedClass?.days).includes(f.day))
      && (!f.location || linkedClass?.location === f.location)
      && (!f.completion || (f.completion === "complete") === Boolean(item.completed_class))
      && (!(f.completion === "incomplete" && !f.showCompletedRequirements) || !requirementIsComplete(item))
      && (!f.prereqOnly || isPrereqRequirement(item));
  }

  function compareValues(a, b, key, desc) {
    let av = a[key], bv = b[key];
    if (typeof av === "boolean" || typeof bv === "boolean") { av = Number(Boolean(av)); bv = Number(Boolean(bv)); }
    const result = String(av ?? "").localeCompare(String(bv ?? ""), undefined, {numeric:true, sensitivity:"base"});
    return desc ? -result : result;
  }

  function renderScouts() {
    const f = filters();
    const sortKey = $("sort-select").value;
    const sortMap = {time:"start_time_24h", class:"class_name", block:"period_name", location:"location"};
    const grouped = new Map();
    for (const item of classes.filter(c => classMatches(c, f))) {
      if (!grouped.has(item.scout_name)) grouped.set(item.scout_name, []);
      grouped.get(item.scout_name).push(item);
    }
    const scoutNames = [...grouped.keys()].sort((a,b) => a.localeCompare(b));
    $("scout-count").textContent = `${scoutNames.length} scout(s), ${[...grouped.values()].reduce((n,v)=>n+v.length,0)} matching class(es)`;
    if (!scoutNames.length) {
      $("scout-results").innerHTML = '<div class="panel empty">No classes match the current filters.</div>';
      return;
    }
    $("scout-results").innerHTML = scoutNames.map(name => {
      const rows = grouped.get(name).slice().sort((a,b) => compareValues(a,b,sortMap[sortKey],false) || compareValues(a,b,"class_name",false));
      const content = rows.map(item => {
        const allReqs = requirementsByClass.get(reqKey(item)) || [];
        const hideCompleted = f.completion === "incomplete" && !f.showCompletedRequirements;
        let reqs = hideCompleted ? allReqs.filter(req => !requirementIsComplete(req)) : allReqs;
        if (f.prereqOnly) reqs = reqs.filter(isPrereqRequirement);
        const hiddenCount = allReqs.length - reqs.length;
        let reqHtml = "";
        if (allReqs.length) {
          const hiddenText = hiddenCount ? `; ${hiddenCount} hidden` : "";
          const reqBody = reqs.length
            ? `<ul class="requirement-list">${reqs.map(req => `<li><span class="requirement-number">${escapeHtml(req.requirement_number)}</span>${escapeHtml(req.description)} ${requirementBadge(req)}</li>`).join("")}</ul>`
            : `<p class="meta">No requirement rows match the current filters.</p>`;
          const completedCount = reqs.filter(requirementIsComplete).length;
          const prereqIncompleteCount = reqs.filter(req => !requirementIsComplete(req) && isPrereqRequirement(req)).length;
          const incompleteCount = reqs.length - completedCount - prereqIncompleteCount;
          reqHtml = `<details class="requirements"><summary>${reqs.length} visible requirement row(s), ${completedCount} completed, ${incompleteCount} incomplete, ${prereqIncompleteCount} incomplete (pre-reqs)${hiddenText}</summary>${reqBody}</details>`;
        }
        return `<div class="class-row">
          <div><strong>${escapeHtml(item.start_time)}</strong></div>
          <div>${escapeHtml(item.days)}</div>
          <div><div class="class-name">${escapeHtml(item.class_name)}</div><div class="meta">${escapeHtml(item.class_number)}</div></div>
          <div>${escapeHtml(item.period_name)}</div>
          <div>${escapeHtml(item.location)}</div>
          <div>${boolBadge(item.class_completed)}</div>
          ${reqHtml}
        </div>`;
      }).join("");
      return `<article class="scout-card"><h2><span>${escapeHtml(name)}</span><small>${rows.length} class(es)</small></h2><div class="class-list">${content}</div></article>`;
    }).join("");
  }

  function renderClasses() {
    const rows = classes.filter(item => classMatches(item)).slice().sort((a,b) => compareValues(a,b,state.classSort.key,state.classSort.desc));
    $("class-count").textContent = `${rows.length} matching class row(s)`;
    $("classes-table").querySelector("tbody").innerHTML = rows.map(item => `<tr>
      <td>${escapeHtml(item.scout_name)}</td><td>${escapeHtml(item.start_time)}</td><td>${escapeHtml(item.days)}</td>
      <td>${escapeHtml(item.period_name)}</td><td><strong>${escapeHtml(item.class_name)}</strong></td>
      <td>${escapeHtml(item.class_number)}</td><td>${escapeHtml(item.location)}</td><td>${boolBadge(item.class_completed)}</td>
    </tr>`).join("") || '<tr><td colspan="8" class="empty">No classes match the current filters.</td></tr>';
    updateSortHeaders("classes-table", state.classSort);
  }

  function renderRequirements() {
    const rows = requirements.filter(item => requirementMatches(item)).slice().sort((a,b) => compareValues(a,b,state.reqSort.key,state.reqSort.desc));
    $("requirement-count").textContent = `${rows.length} matching requirement row(s)`;
    $("requirements-table").querySelector("tbody").innerHTML = rows.map(item => `<tr>
      <td>${escapeHtml(item.scout_name)}</td><td>${escapeHtml(item.merit_badge_name)}</td><td>${escapeHtml(item.class_number)}</td>
      <td><strong>${escapeHtml(item.requirement_number)}</strong></td><td>${escapeHtml(item.description).replaceAll("\n", "<br>")}</td>
      <td>${escapeHtml(item.present_days)}</td><td>${requirementBadge(item)}</td>
      <td>${boolBadge(item.requirement_on_event, "Yes", "No")}</td>
    </tr>`).join("") || '<tr><td colspan="8" class="empty">No requirements match the current filters.</td></tr>';
    updateSortHeaders("requirements-table", state.reqSort);
  }

  function updateSortHeaders(tableId, sort) {
    for (const th of $(tableId).querySelectorAll("th[data-key]")) {
      th.classList.toggle("sorted", th.dataset.key === sort.key);
      th.classList.toggle("desc", th.dataset.key === sort.key && sort.desc);
    }
  }

  function syncCompletedRequirementsControl() {
    $("completed-requirements-control").hidden = $("completion-filter").value !== "incomplete";
  }

  function renderAll() {
    syncCompletedRequirementsControl();
    renderScouts();
    renderClasses();
    renderRequirements();
  }
  for (const id of ["search","scout-filter","class-filter","block-filter","day-filter","location-filter","completion-filter","sort-select","show-completed-requirements","prereq-filter"]) {
    $(id).addEventListener(id === "search" ? "input" : "change", renderAll);
  }
  $("reset").addEventListener("click", () => {
    for (const id of ["search","scout-filter","class-filter","block-filter","day-filter","location-filter","completion-filter"]) $(id).value = "";
    $("show-completed-requirements").checked = false;
    $("prereq-filter").checked = false;
    $("sort-select").value = "time";
    renderAll();
  });
  for (const button of document.querySelectorAll(".tabs button")) {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("active", b === button));
      document.querySelectorAll(".view").forEach(view => view.hidden = view.id !== button.dataset.view);
    });
  }
  for (const [tableId, sortState] of [["classes-table", state.classSort], ["requirements-table", state.reqSort]]) {
    for (const th of $(tableId).querySelectorAll("th[data-key]")) {
      th.addEventListener("click", () => {
        if (sortState.key === th.dataset.key) sortState.desc = !sortState.desc;
        else { sortState.key = th.dataset.key; sortState.desc = false; }
        tableId === "classes-table" ? renderClasses() : renderRequirements();
      });
    }
  }
  if (data.errors?.length) {
    $("errors").innerHTML = `<div class="error-box"><strong>${data.errors.length} extraction error(s)</strong><ul>${data.errors.map(e => `<li>${escapeHtml(e.scout_name)}: ${escapeHtml(e.error)}</li>`).join("")}</ul></div>`;
  }
  renderAll();
})();