# KinTrafic Live

Carte communautaire du trafic à **Kinshasa** (PWA mobile-first). Signalements, votes de fiabilité, admin chiffré, module payant **éteint** au lancement.

Stack : FastAPI, SQLAlchemy 2, Pydantic v2, PostgreSQL 16 + PostGIS, HTML/CSS/JS, Leaflet (tuiles mises en cache côté serveur et dans le service worker). Pas de GPS en arrière-plan.

## Lancer en local

### 1. Base PostGIS

Avec Docker :

```bash
docker compose up -d db
```

Sans Docker (paquet Ubuntu `postgresql-16-postgis-3`) :

```bash
sudo pg_ctlcluster 16 main start
sudo -u postgres psql -c "CREATE USER kintrafic WITH PASSWORD 'kintrafic';" || true
sudo -u postgres psql -c "CREATE DATABASE kintrafic OWNER kintrafic;" || true
sudo -u postgres psql -d kintrafic -c "CREATE EXTENSION IF NOT EXISTS postgis;"
sudo -u postgres psql -d kintrafic -c "GRANT ALL ON SCHEMA public TO kintrafic;"
```

### 2. Application

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 43147
```

Ouvre [http://127.0.0.1:43147](http://127.0.0.1:43147).

- Carte publique : accepter CGU + lien politique de confidentialité (loi 23/010). GPS seulement via **Me situer** / **Signaler** (haute précision, vol de carte vers le vrai point — jamais un GPS Kinshasa inventé).
- Dès l’ouverture : overlay des **18 axes** colorés Fluide / Dense / Saturé (profil horaire + fusion). Types **nids-de-poule** et **travaux**. Toucher un axe ou un point pour le nom de voie et l’état connu.
- Admin : [http://127.0.0.1:43147/admin/login](http://127.0.0.1:43147/admin/login) — identifiant `osee`, mot de passe `KinTrafic-Local-2026!` (haché Argon2, pas une URL secrète). TOTP off en local (`ADMIN_TOTP_REQUIRED=false`).
- Santé : `GET /health`. État ville compact : `GET /api/traffic/status-global`.

Les signalements de démo (30 Juin, Lumumba, Masina, Matadi, Ndjili…) et 14 jours de métriques sont semés au premier démarrage **si** `SEED_DEMO=true`. Le paywall **ne s’allume jamais tout seul**. Même sans démo, la carte n’est pas vide : le **profil horaire King-Kinshasa** colorie les axes.

## Mise en ligne

`localhost` et le Preview Cursor **ne sont pas** testables depuis un téléphone 4G : le GPS Chrome exige **HTTPS** public, et `127.0.0.1` sur Android désigne le téléphone lui-même.

Guide pas à pas (hébergeur, Docker, PWA, APK) :

`/cursor/stores/bc-82853373-28a2-4ec8-918f-55fb9b1128cd/docs/mise-en-ligne.md`

En résumé dans ce dépôt :

1. Copier `.env.example` → `.env`, changer `SECRET_KEY` et `ADMIN_PASSWORD`, passer `PUBLIC_ORIGIN` à `https://ton-domaine`, `ADMIN_TOTP_REQUIRED=true`.
2. **Railway, Render ou Fly.io** (Docker + Postgres/PostGIS géré) **ou** un VPS Ubuntu : `docker compose -f docker-compose.prod.yml --profile tls up -d` (Caddy termine le TLS ; uvicorn n’écoute que `127.0.0.1:8000`). PythonAnywhere n’est **pas** adapté (pas de PostGIS/Docker/veille).
3. Fichiers production : `Dockerfile`, `docker-compose.prod.yml`, `Caddyfile`.
4. Sur le téléphone : Chrome → URL HTTPS → CGU → **Me situer** (vrai GPS) ; installer la **PWA** (ajouter à l’écran d’accueil) **avant** de reconstruire l’APK.
5. L’APK démo demande l’URL au lancement (défaut `http://127.0.0.1:43147`). Reconstruire : `android-wrapper/` (`MainActivity.java`).

## Autonomie (baseline, veille, fusion)

Sans signalement manuel, KinTrafic Live n’affiche plus une ville « sans donnée ». Trois couches, dans cet ordre :

1. **Baseline King-Kinshasa** — table PostGIS `axis_traffic_profiles` (axe × jour de semaine 0–6 × heure 0–23, fuseau `Africa/Kinshasa`). Heuristique, pas du ML ni du Google Live : pointe **07:00–09:00** et **17:00–19:00** en **Saturé** sur Boulevard du 30 Juin, Route des Poids Lourds, Avenue Kasa-Vubu (et d’autres axes lourds) ; **Dense** sur le reste du réseau instrumenté ; **Fluide** hors pointe / week-end. Semé au démarrage (`create_all` + colonnes `ALTER` si la base existait déjà).
2. **Veille automatique** — job asynchrone au **startup** puis toutes les `VEILLE_INTERVAL_SEC` secondes (ticker 60 s, garde-fou `VEILLE_MIN_INTERVAL_SEC`). Sources publiques, User-Agent identifié, **aucun contournement de login** :
   - notes OSM ouvertes dans le BBOX Kinshasa (`https://api.openstreetmap.org/api/0.6/notes.json`) ;
   - flux RSS optionnels (`VEILLE_RSS_URLS`, URLs séparées par des virgules) ;
   - si le réseau est mort ou le flux vide : **échantillon local** `app/veille_sample.json` (`VEILLE_FALLBACK_SAMPLE=true`).
   Les items sont classés par mots-clés (accident, inondation, bouchon…), calés sur le segment PostGIS le plus proche (`VEILLE_SNAP_M`, défaut 120 m), stockés comme signalements `source=veille`, confiance basse, tag **« Source : Veille Automatique »**. Ce n’est **pas** un vote usager. L’échantillon n’est **pas** présenté comme un flux live vérifié. **Pas de couche Google traffic.**
3. **Fusion** — `GET /api/traffic/status-global` (JSON compact, sans session) :
   - un **signalement usager actif** sur l’axe remplace le profil de l’heure ;
   - sinon une **veille** active peut durcir Fluide→Dense/Saturé (toujours non vérifiée) ;
   - à l’expiration (TTL existant) → retour au profil, ou **Fluide** s’il n’y a pas de ligne.

Lancer le job à la main (même process / même base) :

```bash
cd /chemin/kintrafic-live
source .venv/bin/activate   # si tu as un venv
python3 -m app.veille
```

Variables d’environnement (voir `.env.example`) :

| Variable | Défaut | Rôle |
|---|---|---|
| `VEILLE_ENABLED` | `true` | Active le scheduler |
| `VEILLE_INTERVAL_SEC` | `900` | Intervalle cible (15 min) |
| `VEILLE_MIN_INTERVAL_SEC` | `120` | Plancher anti-spam API |
| `VEILLE_OSM_NOTES` | `true` | Notes OSM publiques |
| `VEILLE_RSS_URLS` | *(vide)* | RSS additionnels |
| `VEILLE_FALLBACK_SAMPLE` | `true` | Cache échantillon si feed KO |
| `VEILLE_SNAP_M` | `120` | Distance max de calage (m) |
| `VEILLE_USER_AGENT` | `KinTraficLive/1.0 …` | UA poli pour OSM |

Exemple de `GET /api/traffic/status-global` :

```json
{
  "tz": "Africa/Kinshasa",
  "t": "2026-09-21T08:12:03+0100",
  "city": {"c": "dense", "l": "Dense", "n": {"s": 3, "d": 9, "f": 6}, "src": {"user": 2, "veille": 1, "base": 15}},
  "axes": [{"i": 1, "n": "Boulevard du 30 Juin", "c": "sature", "s": "user", "x": 5400}],
  "tag": "Source : Veille Automatique",
  "d": "fusion: usager>veille>profil horaire; pas Google"
}
```

`c` = `fluide` \| `dense` \| `sature` ; `s` = `user` \| `veille` \| `base` ; `x` = secondes restantes avant expiration du signalement (absent sur le profil). La PWA lit cet objet à chaque poll (20 s) pour colorier les axes.

### Tuiles

Les clients parlent à `/tiles/{z}/{x}/{y}.png` (cache disque `data/tiles/` + cache PWA). L’amont par défaut est le fond HOT d’OSM-France (données OSM), proxifié. Carto Voyager renvoie désormais un PNG « API KEY REQUIRED » : ne plus l’utiliser sans clé. En production, pointe `TILE_UPSTREAM` vers un fond auto-hébergé.

### Paiements

`MOCK_PAYMENTS=true`. Initiation réelle seulement si un admin active la monétisation (écran dédié, confirmation `CONFIRMER`). Webhook de test :

```bash
curl -X POST http://127.0.0.1:43147/api/v1/webhooks/mock \
  -H "x-mock-secret: change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{"event_id":"t1","type":"success","external_ref":"KT-XXXX"}'
```

OTP mock : le code est renvoyé dans la réponse JSON (`123456`).

## Tests

```bash
pytest -q
```

## APK démo (sideload)

Un APK debug signé (WebView autour de la PWA) se construit avec le SDK Android :

```bash
export ANDROID_HOME=/chemin/sdk
cd android-wrapper
gradle assembleDebug
```

Fichier produit : `android-wrapper/app/build/outputs/apk/debug/app-debug.apk`.

Sur le téléphone : **Réglages → Sécurité → sources inconnues / installer des apps inconnues** (autorise le fichier / Chrome / Files), puis ouvre l’APK. Au premier lancement, saisis l’URL du serveur (`https://ton-domaine` une fois en ligne, ou `http://IP-LAN:43147` en Wi-Fi local — `127.0.0.1` sur le téléphone n’est pas le serveur). Accepte la permission Localisation quand tu tapes **Me situer**. Détail : section **Mise en ligne** ci-dessus et le guide store.

Navigation, vocal, GPS fond, Play Store, agrégateur Mobile Money réel, pack PMTiles 25–40 Mo (bouton prévu plus tard), 2e admin.
