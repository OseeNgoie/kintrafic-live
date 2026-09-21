package cd.kintrafic.live;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.view.View;
import android.webkit.GeolocationPermissions;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

public class MainActivity extends Activity {
    private static final int REQ_LOC = 41;
    private static final String PREFS = "kintrafic";
    private static final String KEY_URL = "server_url";

    private WebView web;
    private View gate;
    private EditText urlField;
    private String pendingOrigin;
    private GeolocationPermissions.Callback pendingGeo;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        web = findViewById(R.id.webview);
        gate = findViewById(R.id.gate);
        urlField = findViewById(R.id.url);
        Button go = findViewById(R.id.go);
        TextView hint = findViewById(R.id.hint);

        hint.setText(
            "APK démo : enveloppe la PWA. Entre l’adresse du serveur KinTrafic (HTTP autorisé). "
                + "Sur le téléphone, 127.0.0.1 est le téléphone lui-même — utilise l’IP LAN ou l’URL publique. "
                + "Le GPS est celui de cet appareil, jamais une fausse position à Gombe."
        );

        SharedPreferences p = getSharedPreferences(PREFS, MODE_PRIVATE);
        String saved = p.getString(KEY_URL, "http://127.0.0.1:43147");
        urlField.setText(saved);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setGeolocationEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        web.setWebViewClient(new WebViewClient());
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback callback) {
                pendingOrigin = origin;
                pendingGeo = callback;
                ensureLocationThenGrant();
            }

            @Override
            public void onPermissionRequest(PermissionRequest request) {
                request.grant(request.getResources());
            }
        });

        go.setOnClickListener(v -> {
            String url = urlField.getText().toString().trim();
            if (url.isEmpty()) {
                Toast.makeText(this, "Indique l’URL du serveur.", Toast.LENGTH_SHORT).show();
                return;
            }
            if (!url.startsWith("http://") && !url.startsWith("https://")) {
                url = "http://" + url;
            }
            p.edit().putString(KEY_URL, url).apply();
            openPwa(url);
        });
    }

    private void openPwa(String url) {
        gate.setVisibility(View.GONE);
        web.setVisibility(View.VISIBLE);
        web.loadUrl(url);
    }

    private void ensureLocationThenGrant() {
        boolean fine = checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)
            == PackageManager.PERMISSION_GRANTED;
        if (!fine) {
            requestPermissions(
                new String[]{Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION},
                REQ_LOC
            );
            return;
        }
        grantGeo(true);
    }

    private void grantGeo(boolean allow) {
        if (pendingGeo != null && pendingOrigin != null) {
            pendingGeo.invoke(pendingOrigin, allow, false);
        }
        pendingGeo = null;
        pendingOrigin = null;
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQ_LOC) {
            boolean ok = grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED;
            grantGeo(ok);
            if (!ok) {
                Toast.makeText(
                    this,
                    "Permission GPS refusée. La carte Kinshasa reste utilisable sans te placer.",
                    Toast.LENGTH_LONG
                ).show();
            }
        }
    }

    @Override
    public void onBackPressed() {
        if (web.getVisibility() == View.VISIBLE && web.canGoBack()) {
            web.goBack();
            return;
        }
        if (web.getVisibility() == View.VISIBLE) {
            web.setVisibility(View.GONE);
            gate.setVisibility(View.VISIBLE);
            return;
        }
        super.onBackPressed();
    }
}
