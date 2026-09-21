KT.api("/api/v1/me").then((d) => {
  document.getElementById("me-status").innerHTML =
    `Appareil ${d.device_id.slice(0, 8)}… · ${d.phone ? "numéro lié" : "sans numéro"} · ` +
    `${d.is_premium ? "premium" : "gratuit"} · monétisation ${d.monetization_enabled ? "on" : "off"}`;
  if (d.monetization_enabled) document.getElementById("pay-box").classList.remove("hidden");
}).catch((e) => {
  document.getElementById("me-status").textContent = "Accepte d’abord les CGU sur la carte. " + e.message;
});

document.getElementById("otp-req").onclick = () => {
  KT.api("/api/v1/auth/otp/request", { method: "POST", body: JSON.stringify({ phone: document.getElementById("phone").value }) })
    .then((d) => { document.getElementById("otp-hint").textContent = d.dev_code ? ("Mode mock, code : " + d.dev_code) : "Code envoyé."; })
    .catch((e) => KT.toast(e.message));
};
document.getElementById("otp-ok").onclick = () => {
  KT.api("/api/v1/auth/otp/verify", {
    method: "POST",
    body: JSON.stringify({ phone: document.getElementById("phone").value, code: document.getElementById("otp").value })
  }).then(() => { KT.toast("Numéro lié"); location.reload(); }).catch((e) => KT.toast(e.message));
};
document.getElementById("btn-del").onclick = () => {
  if (!confirm("Anonymiser tes signalements et détacher le numéro ?")) return;
  fetch("/api/v1/me", { method: "DELETE", credentials: "include" }).then(() => location.href = "/");
};
