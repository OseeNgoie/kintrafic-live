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
- Dès l’ouverture : overlay des axes instrumentés (signalé / vérifié / pas de donnée). Types **nids-de-poule** et **travaux**. Toucher un axe ou un point pour le nom de voie et l’état connu.
- Admin : [http://127.0.0.1:43147/admin/login](http://127.0.0.1:43147/admin/login) — identifiant `osee`, mot de passe `KinTrafic-Local-2026!` (haché Argon2, pas une URL secrète). TOTP off en local (`ADMIN_TOTP_REQUIRED=false`).
- Santé : `GET /health`.

Les signalements de démo (30 Juin, Lumumba, Masina, Matadi, Ndjili…) et 14 jours de métriques sont semés au premier démarrage. Le paywall **ne s’allume jamais tout seul**.

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

Sur le téléphone : **Réglages → Sécurité → sources inconnues / installer des apps inconnues** (autorise le fichier / Chrome / Files), puis ouvre l’APK. Au premier lancement, saisis l’URL du serveur (`http://IP-LAN:43147` — `127.0.0.1` sur le téléphone n’est pas le VPS). Accepte la permission Localisation quand tu tapes **Me situer**.

Navigation, vocal, GPS fond, Play Store, agrégateur Mobile Money réel, pack PMTiles 25–40 Mo (bouton prévu plus tard), 2e admin.
