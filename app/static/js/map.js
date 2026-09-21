(function () {
  const mapEl = document.getElementById("map");
  if (!mapEl) return;

  const eula = document.getElementById("eula");
  const hour = new Date().toLocaleString("en-US", { hour: "numeric", hour12: false, timeZone: "Africa/Kinshasa" });
  const night = Number(hour) >= 18 || Number(hour) < 6;
  const geoBanner = document.getElementById("geo-banner");

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

  let map, pointsLayer, axesLayer, communesLayer, meLayer, meMarker, meAcc, pollTimer;

  function inKinBbox(lat, lng) {
    const b = KT.bbox;
    return lng >= b[0] && lat >= b[1] && lng <= b[2] && lat <= b[3];
  }

  function bootMap() {
    if (map) return;
    map = L.map("map", {
      zoomControl: true,
      attributionControl: true,
      maxBoundsViscosity: 0.35
    });
    const city = L.latLngBounds([KT.bbox[1], KT.bbox[0]], [KT.bbox[3], KT.bbox[2]]);
    map.setMaxBounds(city.pad(0.35));
    map.fitBounds(city, { padding: [24, 24], maxZoom: 12 });
    map.createPane("ktCommunes");
    map.getPane("ktCommunes").style.zIndex = 350;
    map.createPane("ktAxes");
    map.getPane("ktAxes").style.zIndex = 450;
    map.getPane("ktAxes").style.pointerEvents = "auto";
    map.createPane("ktPoints");
    map.getPane("ktPoints").style.zIndex = 550;
    L.tileLayer("/tiles/{z}/{x}/{y}.png", {
      minZoom: 10,
      maxZoom: 16,
      attribution: "© OpenStreetMap contributeurs · fond HOT OSM-FR mis en cache localement"
    }).addTo(map);
    communesLayer = L.layerGroup({ pane: "ktCommunes" }).addTo(map);
    axesLayer = L.layerGroup({ pane: "ktAxes" }).addTo(map);
    pointsLayer = L.layerGroup({ pane: "ktPoints" }).addTo(map);
    meLayer = L.layerGroup({ pane: "ktPoints" }).addTo(map);
    if (night) document.body.classList.add("night");
    map.on("click", (ev) => {
      inspectPoint(ev.latlng.lat, ev.latlng.lng);
    });
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

  function axisStyle(code, src) {
    const base = { pane: "ktAxes", lineCap: "round", lineJoin: "round", interactive: true };
    const dash = src === "user" ? null : src === "veille" ? "10 6" : "5 8";
    if (code === "sature") return Object.assign({ color: "#fb7185", weight: 9, opacity: 1, dashArray: dash }, base);
    if (code === "dense") return Object.assign({ color: "#ffb020", weight: 8, opacity: 0.98, dashArray: dash }, base);
    if (code === "fluide") return Object.assign({ color: "#34f5c5", weight: 8, opacity: 0.92, dashArray: dash }, base);
    if (code === "verifie") return Object.assign({ color: "#34f5c5", weight: 9, opacity: 1, dashArray: null }, base);
    if (code === "signale") return Object.assign({ color: "#ffb020", weight: 8, opacity: 0.98, dashArray: "14 7" }, base);
    if (code === "conteste") return Object.assign({ color: "#fb7185", weight: 8, opacity: 0.9, dashArray: "6 8" }, base);
    return Object.assign({ color: "#9eb0c8", weight: 7, opacity: 0.88, dashArray: "5 8" }, base);
  }

  function axisCasing(code) {
    return {
      pane: "ktAxes",
      color: "#041018",
      weight: (axisStyle(code).weight || 7) + 5,
      opacity: 0.75,
      lineCap: "round",
      lineJoin: "round",
      interactive: false
    };
  }

  async function refresh() {
    if (!map) return;
    const b = map.getBounds();
    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
    const err = document.getElementById("err-banner");
    try {
      const [geo, net, communes, global] = await Promise.all([
        KT.api("/api/v1/reports/viewport?bbox=" + encodeURIComponent(bbox)),
        KT.api("/api/v1/geo/network"),
        KT.api("/api/v1/geo/communes"),
        fetch("/api/traffic/status-global").then((r) => r.json())
      ]);
      err.classList.add("hidden");
      drawCommunes(communes);
      drawAxes(net, global);
      drawPoints(geo);
      const nSig = geo.features.length;
      const city = (global.city && global.city.l) || "—";
      const ns = (global.city && global.city.n) || {};
      document.getElementById("net-chip").textContent =
        "Ville " + city + " · S" + (ns.s || 0) + "/D" + (ns.d || 0) + "/F" + (ns.f || 0) + " · " + nSig + " pts";
    } catch (e) {
      err.textContent = "Impossible de rafraîchir. " + e.message + " Réessayer.";
      err.classList.remove("hidden");
    }
  }

  function drawCommunes(communes) {
    communesLayer.clearLayers();
    if (!communes || !communes.features) return;
    communes.features.forEach((f) => {
      const layer = L.geoJSON(f, {
        pane: "ktCommunes",
        style: { color: "#3d5a80", weight: 1, opacity: 0.28, fillColor: "#122033", fillOpacity: 0.04 },
        onEachFeature: (feat, lyr) => {
          lyr.bindTooltip(feat.properties.name, { sticky: true, className: "kt-tip" });
          lyr.on("click", (ev) => {
            L.DomEvent.stopPropagation(ev);
            inspectPoint(ev.latlng.lat, ev.latlng.lng);
          });
        }
      });
      layer.addTo(communesLayer);
    });
  }

  function drawAxes(net, global) {
    axesLayer.clearLayers();
    const byId = {};
    (global && global.axes ? global.axes : []).forEach((a) => {
      byId[a.i] = a;
    });
    (net.features || []).forEach((f) => {
      const p = f.properties;
      const g = byId[p.id];
      const code = (g && g.c) || p.congestion_code || p.status_code;
      const src = (g && g.s) || p.fusion_src;
      p.congestion_code = code;
      p.fusion_src = src;
      L.geoJSON(f, { pane: "ktAxes", style: axisCasing(code), interactive: false }).addTo(axesLayer);
      const layer = L.geoJSON(f, {
        pane: "ktAxes",
        style: axisStyle(code, src),
        onEachFeature: (feat, lyr) => {
          lyr.on("click", (ev) => {
            L.DomEvent.stopPropagation(ev);
            openAxisSheet(p, ev.latlng);
          });
        }
      });
      layer.addTo(axesLayer);
    });
  }

  function drawPoints(geo) {
    pointsLayer.clearLayers();
    geo.features.forEach((f) => {
      const [lng, lat] = f.geometry.coordinates;
      const p = f.properties;
      const verified = p.trust_label === "Vérifié";
      const m = L.circleMarker([lat, lng], {
        pane: "ktPoints",
        radius: verified ? 11 : 9,
        color: verified ? "#e8fff7" : "rgba(255,255,255,.75)",
        weight: verified ? 3 : 2,
        fillColor: p.color,
        fillOpacity: p.trust_label === "Contesté" ? 0.4 : 0.92
      });
      m.on("click", (ev) => {
        L.DomEvent.stopPropagation(ev);
        openReport(f.id);
      });
      m.bindTooltip(
        p.label + " · " + (p.source === "veille" ? p.source_tag || "Veille auto" : p.trust_label),
        { className: "kt-tip" }
      );
      m.addTo(pointsLayer);
    });
  }

  function condHtml(conditions) {
    if (!conditions || !conditions.length) {
      return `<p class="meta-row"><span class="k">État de la chaussée</span><span class="v muted">Pas de donnée</span></p>`;
    }
    return conditions
      .map(
        (c) =>
          `<p class="meta-row"><span class="k">${c.label}</span><span class="v badge ${c.trust_label === "Vérifié" ? "ok" : "sig"}">${c.trust_label}${c.n ? " · " + c.n : ""}</span></p>`
      )
      .join("");
  }

  function openAxisSheet(p, latlng) {
    const sheet = document.getElementById("sheet");
    sheet.classList.remove("hidden");
    const dist = "";
    sheet.innerHTML = `
      <p class="sheet-kicker">Axe instrumenté</p>
      <h2>${p.name}</h2>
      <p class="meta-row"><span class="k">Congestion</span><span class="v badge ${p.congestion_code || p.status_code}">${p.congestion_label || p.traffic_label}</span></p>
      <p class="meta-row"><span class="k">Source</span><span class="v">${p.fusion_src_label || p.fusion_src || "profil"}</span></p>
      ${condHtml(p.conditions)}
      <p class="hint">${p.fusion_src === "base" ? "Profil horaire Kinshasa (pointe 07–09 / 17–19). Un signalement usager remplace cette prévision jusqu’à expiration." : p.fusion_src === "veille" ? "Veille automatique — non vérifiée par un usager. Pas du trafic Google." : "Signalement usager actif : il prime sur le profil horaire."}</p>
      <p class="hint">Ce n’est pas un conseil de circulation ni d’infraction.</p>
      <p><button class="btn ghost" type="button" id="close">Fermer</button></p>`;
    sheet.querySelector("#close").onclick = () => sheet.classList.add("hidden");
  }

  async function inspectPoint(lat, lng, silent) {
    try {
      const d = await KT.api("/api/v1/geo/inspect?lat=" + encodeURIComponent(lat) + "&lng=" + encodeURIComponent(lng));
      if (silent && d.axis_id) return;
      const sheet = document.getElementById("sheet");
      sheet.classList.remove("hidden");
      const street = d.street_name || "Voie sans nom connu";
      const place = d.commune ? d.commune : d.in_coverage ? "Kinshasa (commune non calée)" : "Hors zone";
      const near = d.distance_m != null && d.axis_id ? ` · ${d.distance_m} m de l’axe` : "";
      const reports = (d.reports || [])
        .slice(0, 6)
        .map((r) => `<li><button type="button" class="linkish" data-id="${r.id || ""}">${r.label} · ${r.trust_label}</button></li>`)
        .join("");
      sheet.innerHTML = `
        <p class="sheet-kicker">${place}${near}</p>
        <h2>${street}</h2>
        <p class="meta-row"><span class="k">Congestion</span><span class="v badge ${d.congestion_code || d.status_code}">${d.congestion_label || d.traffic_label}</span></p>
        ${d.fusion_src_label ? `<p class="meta-row"><span class="k">Source</span><span class="v">${d.fusion_src_label}</span></p>` : ""}
        ${condHtml(d.conditions)}
        <p class="hint">${d.disclaimer || ""}</p>
        ${reports ? "<p class='k'>Signalements proches</p><ul class='rep-list'>" + reports + "</ul>" : "<p class='hint'>Pas de signalement à proximité.</p>"}
        <p><button class="btn ghost" type="button" id="close">Fermer</button></p>`;
      sheet.querySelector("#close").onclick = () => sheet.classList.add("hidden");
      sheet.querySelectorAll("[data-id]").forEach((b) => {
        if (!b.dataset.id) return;
        b.onclick = () => openReport(b.dataset.id);
      });
    } catch (e) {
      if (!silent) KT.toast(e.message);
    }
  }

  async function openReport(id) {
    const sheet = document.getElementById("sheet");
    try {
      const d = await KT.api("/api/v1/reports/" + id);
      sheet.classList.remove("hidden");
      sheet.innerHTML = `
        <p class="sheet-kicker">${d.commune || "Kinshasa"}${d.axis ? " · " + d.axis : ""}</p>
        <h2>${d.label}</h2>
        <p class="meta-row"><span class="k">Statut</span><span class="v badge ${d.trust_label === "Vérifié" ? "verifie" : "signale"}">${d.trust_label}</span></p>
        <p class="hint">${d.source_tag ? d.source_tag : ""} ${d.disclaimer}</p>
        <p class="hint">${d.source === "veille" ? "La veille n’est pas un vote usager." : d.counts_hidden ? "Pas encore assez de confirmations (votes)." : (d.pos + " toujours là / " + d.neg + " plus rien")}</p>
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

  function geoMessage(err) {
    if (!err) return "Position indisponible.";
    const code = err.code;
    if (code === 1) {
      return "Permission GPS refusée. Autorise la localisation pour ce site dans les réglages du navigateur. La carte Kinshasa reste utilisable sans te placer — on ne te met pas à Gombe à ta place.";
    }
    if (code === 2) return "Position indisponible (capteur ou réseau). Réessaie à l’air libre.";
    if (code === 3) return "Délai GPS dépassé. Sors à l’air libre, active la localisation précise, puis réessaie.";
    if (/denied|permission|refus/i.test(err.message || "")) {
      return "Permission GPS refusée. La carte reste lisible sans te localiser.";
    }
    return err.message || "Position refusée.";
  }

  function showGeoError(err) {
    geoBanner.textContent = geoMessage(err);
    geoBanner.classList.remove("hidden");
  }

  function clearGeoError() {
    geoBanner.classList.add("hidden");
    geoBanner.textContent = "";
  }

  function placeMe(lat, lng, accuracy, fly) {
    meLayer.clearLayers();
    const acc = Math.max(8, accuracy || 40);
    meAcc = L.circle([lat, lng], {
      radius: acc,
      color: "#34f5c5",
      weight: 1,
      fillColor: "#34f5c5",
      fillOpacity: 0.12
    }).addTo(meLayer);
    const icon = L.divIcon({
      className: "me-wrap",
      html: '<span class="me-pulse"></span><span class="me-dot"></span>',
      iconSize: [22, 22],
      iconAnchor: [11, 11]
    });
    meMarker = L.marker([lat, lng], { icon, zIndexOffset: 1000, title: "Ta position" }).addTo(meLayer);
    meMarker.bindTooltip("Toi · " + Math.round(acc) + " m", { permanent: true, direction: "top", className: "kt-tip me-tip" });
    const z = acc <= 25 ? 16 : acc <= 80 ? 15 : 14;
    if (fly && map) {
      map.flyTo([lat, lng], z, { duration: 1.15, easeLinearity: 0.4 });
    }
  }

  function waitForFix() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        const e = new Error("Géolocalisation indisponible sur cet appareil.");
        e.code = 2;
        return reject(e);
      }
      const opts = { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 };
      let best = null;
      let settled = false;
      let watchId = null;
      let timer = null;
      const finish = (fn, val) => {
        if (settled) return;
        settled = true;
        if (watchId != null) navigator.geolocation.clearWatch(watchId);
        if (timer) clearTimeout(timer);
        fn(val);
      };
      const consider = (pos) => {
        if (!best || pos.coords.accuracy < best.coords.accuracy) best = pos;
        if (pos.coords.accuracy <= 35) finish(resolve, pos);
      };
      const watchIdAssigned = navigator.geolocation.watchPosition(
        consider,
        (err) => {
          if (best) finish(resolve, best);
          else finish(reject, err);
        },
        opts
      );
      watchId = watchIdAssigned;
      navigator.geolocation.getCurrentPosition(consider, () => {}, opts);
      timer = setTimeout(() => {
        if (best) finish(resolve, best);
        else {
          const e = new Error("Délai GPS dépassé");
          e.code = 3;
          finish(reject, e);
        }
      }, 18000);
    });
  }

  document.getElementById("btn-locate").addEventListener("click", async () => {
    const btn = document.getElementById("btn-locate");
    btn.disabled = true;
    btn.textContent = "Fix GPS…";
    clearGeoError();
    try {
      const pos = await waitForFix();
      const lat = pos.coords.latitude;
      const lng = pos.coords.longitude;
      const acc = pos.coords.accuracy;
      placeMe(lat, lng, acc, true);
      if (!inKinBbox(lat, lng)) {
        geoBanner.textContent =
          "Position réelle reçue hors Kinshasa (précision " +
          Math.round(acc) +
          " m). Ce n’est pas un recentrage sur Gombe. Sur un téléphone à Kinshasa, le point doit coller à ta rue.";
        geoBanner.classList.remove("hidden");
      } else {
        KT.toast("Te voilà · précision " + Math.round(acc) + " m");
      }
      KT.api("/api/v1/me/location", { method: "POST", body: JSON.stringify({ lat, lng, accuracy: acc }) }).catch(() => {});
    } catch (e) {
      showGeoError(e);
      KT.toast(geoMessage(e));
    } finally {
      btn.disabled = false;
      btn.textContent = "Me situer";
    }
  });

  document.getElementById("btn-report").addEventListener("click", () => {
    const sheet = document.getElementById("sheet");
    const types = Object.entries(KT.types).map(([code, t]) =>
      `<button type="button" data-type="${code}">${t.label}</button>`
    ).join("");
    sheet.classList.remove("hidden");
    sheet.innerHTML = `<h2>Que vois-tu ?</h2><p class="hint">Un geste : type, puis confirmation. Pas de commentaire. Nids-de-poule et travaux sont des états de chaussée, distincts du trafic.</p><div class="type-grid">${types}</div><p><button class="btn ghost" id="close">Annuler</button></p>`;
    sheet.querySelector("#close").onclick = () => sheet.classList.add("hidden");
    sheet.querySelectorAll("[data-type]").forEach((b) => {
      b.onclick = () => confirmReport(b.dataset.type, tLabel(b.dataset.type));
    });
  });

  function tLabel(code) { return (KT.types[code] && KT.types[code].label) || code; }

  async function confirmReport(type, label) {
    const sheet = document.getElementById("sheet");
    let lat = map.getCenter().lat, lng = map.getCenter().lng, acc = 999, fromGps = false;
    try {
      const pos = await waitForFix();
      lat = pos.coords.latitude; lng = pos.coords.longitude; acc = pos.coords.accuracy; fromGps = true;
      placeMe(lat, lng, acc, false);
    } catch (e) {
      if (e && e.code === 1) showGeoError(e);
    }
    const needPin = !fromGps || acc > 80;
    sheet.innerHTML = `
      <h2>${label}</h2>
      <p>${needPin ? "GPS imprécis ou refusé : pose l’épingle sur l’axe (déplace la carte, le centre compte)." : "Ici, à ta position ?"}</p>
      <p class="hint">Précision ${fromGps ? Math.round(acc) + " m" : "indisponible"} — on n’invente pas un point à Gombe.</p>
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
