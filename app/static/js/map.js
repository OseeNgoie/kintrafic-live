(function () {
  const mapEl = document.getElementById("map");
  if (!mapEl) return;

  const eula = document.getElementById("eula");
  const hour = new Date().toLocaleString("en-US", { hour: "numeric", hour12: false, timeZone: "Africa/Kinshasa" });
  const night = Number(hour) >= 18 || Number(hour) < 6;

  function showEula() {
    eula.classList.remove("hidden");
  }

  async function acceptEula() {
    await KT.api("/api/v1/session/bootstrap", {
      method: "POST",
      body: JSON.stringify({
        eula_version: KT.eulaVersion,
        privacy_version: KT.privacyVersion,
        continue_without_phone: true
      })
    });
    localStorage.setItem(KT.eulaKey, "1");
    eula.classList.add("hidden");
    bootMap();
  }

  document.getElementById("btn-accept").addEventListener("click", () => {
    acceptEula().catch((e) => KT.toast(e.message));
  });

  document.getElementById("legend-tog").addEventListener("click", () => {
    document.getElementById("legend-list").classList.toggle("hidden");
  });

  if (!localStorage.getItem(KT.eulaKey)) {
    showEula();
  } else {
    acceptEula().catch(() => showEula());
  }

  if (!localStorage.getItem("kt_data_banner")) {
    document.getElementById("data-banner").classList.remove("hidden");
    localStorage.setItem("kt_data_banner", "1");
    setTimeout(() => document.getElementById("data-banner").classList.add("hidden"), 8000);
  }

  window.addEventListener("offline", () => document.getElementById("offline-banner").classList.remove("hidden"));
  window.addEventListener("online", () => document.getElementById("offline-banner").classList.add("hidden"));

  let map, layer, pollTimer, pendingQueue;

  function bootMap() {
    if (map) return;
    map = L.map("map", { zoomControl: true, attributionControl: true }).setView([KT.defaultLat, KT.defaultLng], 13);
    L.tileLayer("/tiles/{z}/{x}/{y}.png", {
      minZoom: 10,
      maxZoom: 16,
      attribution: "© OpenStreetMap contributeurs · fond mis en cache localement"
    }).addTo(map);
    map.setMaxBounds(L.latLngBounds([KT.bbox[1], KT.bbox[0]], [KT.bbox[3], KT.bbox[2]]));
    layer = L.layerGroup().addTo(map);
    if (night) document.body.classList.add("night");
    refresh();
    startPoll();
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") startPoll();
      else stopPoll();
    });
  }

  function startPoll() {
    stopPoll();
    pollTimer = setInterval(refresh, 20000);
    refresh();
  }
  function stopPoll() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  async function refresh() {
    if (!map) return;
    const b = map.getBounds();
    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
    const err = document.getElementById("err-banner");
    try {
      const geo = await KT.api("/api/v1/reports/viewport?bbox=" + encodeURIComponent(bbox));
      err.classList.add("hidden");
      layer.clearLayers();
      if (geo.empty) {
        document.getElementById("net-chip").textContent = "Zone calme";
      } else {
        document.getElementById("net-chip").textContent = geo.features.length + " points";
      }
      geo.features.forEach((f) => {
        const [lng, lat] = f.geometry.coordinates;
        const p = f.properties;
        const m = L.circleMarker([lat, lng], {
          radius: 10,
          color: "#fff",
          weight: 2,
          fillColor: p.color,
          fillOpacity: p.trust_label === "Contesté" ? 0.4 : 0.9
        });
        m.on("click", () => openReport(f.id));
        m.bindTooltip(p.label + " · " + p.trust_label);
        m.addTo(layer);
      });
      if (geo.empty) {
        /* empty state handled in chip; keep map usable */
      }
    } catch (e) {
      err.textContent = "Impossible de rafraîchir. " + e.message + " Réessayer.";
      err.classList.remove("hidden");
    }
  }

  async function openReport(id) {
    const sheet = document.getElementById("sheet");
    try {
      const d = await KT.api("/api/v1/reports/" + id);
      sheet.classList.remove("hidden");
      sheet.innerHTML = `
        <h2>${d.label}</h2>
        <p>${d.trust_label}${d.commune ? " · " + d.commune : ""}${d.axis ? " · " + d.axis : ""}</p>
        <p class="hint">${d.disclaimer}</p>
        <p class="hint">${d.counts_hidden ? "Pas encore assez de confirmations." : (d.pos + " toujours là / " + d.neg + " plus rien")}</p>
        <div class="row-btns">
          <button class="btn primary" type="button" data-v="1">Toujours là</button>
          <button class="btn" type="button" data-v="-1">Plus rien</button>
        </div>
        <p><button class="btn ghost" type="button" id="abuse">Signaler un abus</button>
        <button class="btn ghost" type="button" id="close">Fermer</button></p>`;
      sheet.querySelectorAll("[data-v]").forEach((b) => {
        b.onclick = () => {
          KT.api("/api/v1/reports/" + id + "/vote", { method: "PUT", body: JSON.stringify({ value: Number(b.dataset.v) }) })
            .then(() => { KT.toast("Vote enregistré"); refresh(); sheet.classList.add("hidden"); })
            .catch((e) => KT.toast(e.message));
        };
      });
      sheet.querySelector("#close").onclick = () => sheet.classList.add("hidden");
      sheet.querySelector("#abuse").onclick = () => {
        KT.api("/api/v1/reports/" + id + "/abuse", { method: "POST", body: JSON.stringify({ reason: "faux" }) })
          .then(() => KT.toast("Abus transmis à la modération"))
          .catch((e) => KT.toast(e.message));
      };
    } catch (e) {
      KT.toast(e.message);
    }
  }

  function geoOnce() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) return reject(new Error("Géolocalisation indisponible"));
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve(pos),
        (err) => reject(new Error(err.message || "Position refusée")),
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
      );
    });
  }

  document.getElementById("btn-locate").addEventListener("click", async () => {
    try {
      const pos = await geoOnce();
      const lat = pos.coords.latitude, lng = pos.coords.longitude;
      map.setView([lat, lng], 15);
      L.circleMarker([lat, lng], { radius: 7, color: "#0f3d2e", fillColor: "#3ad07a", fillOpacity: 1 }).addTo(map);
      KT.api("/api/v1/me/location", { method: "POST", body: JSON.stringify({ lat, lng, accuracy: pos.coords.accuracy }) }).catch(() => {});
    } catch (e) {
      KT.toast("Carte utilisable sans GPS. Centrage Gombe / 30 Juin. " + e.message);
      map.setView([KT.defaultLat, KT.defaultLng], 13);
    }
  });

  document.getElementById("btn-report").addEventListener("click", () => {
    const sheet = document.getElementById("sheet");
    const types = Object.entries(KT.types).map(([code, t]) =>
      `<button type="button" data-type="${code}">${t.label}</button>`
    ).join("");
    sheet.classList.remove("hidden");
    sheet.innerHTML = `<h2>Que vois-tu ?</h2><p class="hint">Un geste : type, puis confirmation. Pas de commentaire.</p><div class="type-grid">${types}</div><p><button class="btn ghost" id="close">Annuler</button></p>`;
    sheet.querySelector("#close").onclick = () => sheet.classList.add("hidden");
    sheet.querySelectorAll("[data-type]").forEach((b) => {
      b.onclick = () => confirmReport(b.dataset.type, tLabel(b.dataset.type));
    });
  });

  function tLabel(code) { return (KT.types[code] && KT.types[code].label) || code; }

  async function confirmReport(type, label) {
    const sheet = document.getElementById("sheet");
    let lat = KT.defaultLat, lng = KT.defaultLng, acc = 999, fromGps = false;
    try {
      const pos = await geoOnce();
      lat = pos.coords.latitude; lng = pos.coords.longitude; acc = pos.coords.accuracy; fromGps = true;
    } catch (_) {}
    const needPin = !fromGps || acc > 80;
    sheet.innerHTML = `
      <h2>${label}</h2>
      <p>${needPin ? "GPS imprécis ou refusé : pose l’épingle sur l’axe (déplace la carte, le centre compte)." : "Ici, à ta position ?"}</p>
      <p class="hint">Précision ${Math.round(acc)} m</p>
      <div class="row-btns">
        <button class="btn primary" type="button" id="send">Envoyer</button>
        <button class="btn ghost" type="button" id="close">Annuler</button>
      </div>`;
    sheet.querySelector("#close").onclick = () => sheet.classList.add("hidden");
    sheet.querySelector("#send").onclick = async () => {
      const c = map.getCenter();
      const useLat = needPin ? c.lat : lat;
      const useLng = needPin ? c.lng : lng;
      try {
        await KT.api("/api/v1/reports", {
          method: "POST",
          body: JSON.stringify({ type_code: type, lat: useLat, lng: useLng, accuracy: acc })
        });
        KT.toast("Signalement envoyé. Merci.");
        sheet.classList.add("hidden");
        refresh();
      } catch (e) {
        if (!navigator.onLine) {
          KT.toast("Hors ligne : il sera envoyé au retour.");
        } else KT.toast(e.message);
      }
    };
  }
})();
