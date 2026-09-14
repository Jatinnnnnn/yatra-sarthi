/* Travel Info page: transport + weather + events + feedback */
"use strict";
renderNav("/info");

/* transport */
$("#transportForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const dest = $("#transportDest").value.trim();
  if (!dest) return;
  const box = $("#transportResult");
  box.innerHTML = `<p style="text-align:center;color:var(--muted)">Finding routes…</p>`;
  try {
    const t = await api(`/api/transport?destination=${encodeURIComponent(dest)}`);
    box.innerHTML = `
      <div class="tr-head"><h3>Reaching ${esc(t.destination)}</h3>
        <p style="color:var(--muted);font-size:.85rem">Gateway: ${esc(t.gateway)}</p></div>
      <div class="tr-reco">✅ <strong>Recommended:</strong> ${esc(t.recommended)}</div>
      ${transportBlock(t)}`;
  } catch (err) {
    box.innerHTML = `<p style="text-align:center;color:var(--alert)">${esc(err.message)}. Try a suggestion from the list.</p>`;
  }
});

/* weather */
$("#weatherForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const place = $("#weatherPlace").value.trim();
  if (!place) return;
  const box = $("#weatherResult");
  box.innerHTML = `<p style="text-align:center;color:var(--muted)">Fetching forecast…</p>`;
  try {
    const wx = await api(`/api/weather?place=${encodeURIComponent(place)}`);
    const worst = wx.forecast.find((d) => d.safety === "alert") ||
                  wx.forecast.find((d) => d.safety === "caution");
    const srcBadge = wx.source === "live"
      ? '<span class="live-badge">● LIVE — Open-Meteo</span>'
      : '<span class="live-badge model">seasonal model (offline)</span>';
    box.innerHTML = `
      <h3 style="text-align:center;color:var(--pine);margin:.4rem 0 .8rem">${esc(wx.place)} · next 7 days ${srcBadge}</h3>
      <div class="wx-grid">` + wx.forecast.map((d) => `
        <div class="wx-cell">
          <div class="d">${d.day}, ${d.date.slice(8)}/${d.date.slice(5, 7)}</div>
          <div class="ico">${WX_ICON[d.condition] || "🌡️"}</div>
          <div class="t">${d.temp_max}° / ${d.temp_min}°</div>
          <div class="c">${esc(d.condition)} · rain ${d.rain_chance}%</div>
          ${badge(d.safety)}
        </div>`).join("") + `</div>
      <div class="wx-advice">💡 ${esc((worst || wx.forecast[0]).advice)}</div>`;
  } catch (err) {
    box.innerHTML = `<p style="text-align:center;color:var(--alert)">${esc(err.message)}</p>`;
  }
});

/* events */
async function loadEvents() {
  const m = $("#eventMonth").value;
  const data = await api(`/api/events${m ? `?month=${m}` : ""}`);
  $("#eventGrid").innerHTML = data.events.map((e) => `
    <div class="event-card">
      <h4>${esc(e.name)}</h4>
      <div class="ev-meta">📍 ${esc(e.place)} · 🗓️ ${MONTHS[e.month]} · ${e.duration_days} day${e.duration_days > 1 ? "s" : ""}</div>
      <p>${esc(e.note)}</p>
    </div>`).join("") || `<p style="text-align:center;color:var(--muted)">No events listed for this month.</p>`;
}
$("#eventMonth").addEventListener("change", loadEvents);

/* feedback */
let fbRating = 0;
$("#stars").addEventListener("click", (e) => {
  if (e.target.dataset.v) {
    fbRating = Number(e.target.dataset.v);
    document.querySelectorAll("#stars button").forEach((b) =>
      b.classList.toggle("on", Number(b.dataset.v) <= fbRating));
  }
});
$("#feedbackForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!fbRating) { $("#feedbackDone").textContent = "Please select a star rating first."; return; }
  await api("/api/feedback", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating: fbRating, comment: $("#feedbackComment").value.trim() }),
  });
  $("#feedbackDone").textContent = "Dhanyavaad! Your feedback has been recorded. 🙏";
  $("#feedbackComment").value = "";
});

/* datalist */
(async function init() {
  loadEvents();
  try {
    const d = await api("/api/transport/destinations");
    $("#destList").innerHTML = d.destinations.concat(
      ["Kedarnath", "Badrinath", "Auli", "Valley of Flowers", "Jim Corbett", "Mukteshwar"])
      .map((x) => `<option value="${esc(x)}">`).join("");
  } catch (_) {}
})();
