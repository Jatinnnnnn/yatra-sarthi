/* Home page: shared nav + assistant chat */
"use strict";
renderNav("/");

const chatWindow = $("#chatWindow");

function addMsg(html, who) {
  const div = document.createElement("div");
  div.className = `msg ${who}`;
  div.innerHTML = `<div class="msg-bubble">${html}</div>`;
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return div;
}

function poiMiniCards(pois) {
  return `<div class="mini-cards">` + pois.map((p) => `
    <div class="mini-card">
      <img src="${IMG(p.image)}" alt="${esc(p.name)}" loading="lazy" />
      <div><strong>${esc(p.name)}</strong>${esc(p.district)} · ★ ${p.rating}
      ${p.crowd_now ? "<br />" + crowdBadge(p.crowd_now) : ""}</div>
    </div>`).join("") + `</div>`;
}

function hotelsBlock(hotels) {
  return `<div class="mini-cards">` + hotels.map((h) => `
    <div class="mini-card"><div>
      <strong>${esc(h.name)}</strong>${esc(h.place)} · ${esc(h.band)}<br />
      ₹${Number(h.price_per_night).toLocaleString("en-IN")}/night · ★ ${h.rating}
    </div></div>`).join("") + `</div>`;
}

async function sendChat(text) {
  addMsg(esc(text), "user");
  const typing = addMsg('<span class="typing">Yatra Sarthi is thinking…</span>', "bot");
  try {
    const data = await api("/api/assistant", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    let html = esc(data.reply);
    if (data.weather) html += weatherStrip(data.weather);
    if (data.transport) html += transportBlock(data.transport);
    if (data.hotels) html += hotelsBlock(data.hotels);
    if (data.events) html += eventsBlock(data.events);
    if (data.pois) html += poiMiniCards(data.pois);
    if (data.plan) {
      sessionStorage.setItem("ys_plan", JSON.stringify(data.plan));
      html += `<div style="margin-top:.5rem"><a class="btn btn-primary" href="/planner" style="padding:.4rem 1rem;font-size:.85rem">Open full plan in Trip Planner →</a></div>`;
    }
    typing.querySelector(".msg-bubble").innerHTML = html;
  } catch (err) {
    typing.querySelector(".msg-bubble").textContent = "Sorry, something went wrong. Please try again.";
  }
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

$("#chatForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("#chatText").value.trim();
  if (!text) return;
  $("#chatText").value = "";
  sendChat(text);
});
$("#chatSuggest").addEventListener("click", (e) => {
  if (e.target.tagName === "BUTTON") sendChat(e.target.textContent);
});
