/* Crowd Advisor page */
"use strict";
renderNav("/crowd");

function meter(score, level) {
  const cls = { overcrowded: "alert", busy: "caution", comfortable: "good" }[level];
  return `<div class="meter"><div class="meter-fill ${cls}" style="width:${score}%"></div></div>`;
}

function altCards(alts) {
  if (!alts.length) return "";
  return `<div class="alt-wrap"><div class="alt-title">✅ Beat the crowd — go here instead:</div>` +
    alts.map((a) => `
      <div class="alt-card">
        <div class="alt-head">
          <strong>${esc(a.alternative)}</strong>
          <span>📍 ${a.distance_km} km · ${esc(a.travel_time)} away · crowd: ${esc(a.typical_crowd)}</span>
        </div>
        <p>${esc(a.reason)}</p>
        <div class="alt-best">Best for: ${esc(a.best_for)}</div>
      </div>`).join("") + `</div>`;
}

function entryCard(e) {
  return `<div class="crowd-card ${e.level}">
    <img src="${IMG(e.image)}" alt="${esc(e.name)}" loading="lazy" />
    <div class="crowd-body">
      <div class="crowd-top">
        <h4>${esc(e.name)}</h4>
        ${crowdBadge(e)}
      </div>
      <div class="crowd-loc">📍 ${esc(e.district)} district · near ${esc(e.nearest_hub)} · ★ ${e.rating}</div>
      ${meter(e.score, e.level)}
      <p class="crowd-advice">${esc(e.advice)}</p>
      ${altCards(e.alternatives)}
    </div>
  </div>`;
}

async function loadBoard() {
  const data = await api("/api/crowd/board");
  const d = new Date(data.date + "T00:00:00");
  $("#boardDate").textContent =
    `Crowd estimates for ${d.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })} — overcrowded spots show their decongestion alternative.`;
  $("#crowdBoard").innerHTML = data.board.map(entryCard).join("");
}

$("#crowdForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#crowdPlace").value.trim();
  if (!q) return;
  const box = $("#crowdSearchResult");
  box.innerHTML = `<p style="text-align:center;color:var(--muted);margin-top:1rem">Checking…</p>`;
  try {
    const r = await api(`/api/crowd/check?place=${encodeURIComponent(q)}`);
    box.innerHTML = `<div style="margin-top:1.2rem">${entryCard(r)}</div>`;
  } catch (err) {
    box.innerHTML = `<p style="text-align:center;color:var(--alert);margin-top:1rem">${esc(err.message)}</p>`;
  }
});

loadBoard();
