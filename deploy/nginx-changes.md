# Nginx changes for zero-downtime deploys

Apply these changes to `/home/ryan/server/nginx.conf`.

## 1. Add global settings to http{} block

After the existing `resolver 127.0.0.11 valid=10s ipv6=off;` line, add:

```nginx
# ── Global proxy retry / timeout settings ─────────────────────────────────
# These apply to all upstream proxy_pass directives that use upstream{} blocks.
# proxy_next_upstream retries on transient errors during container restarts.
proxy_next_upstream error timeout http_502 http_503 http_504;
proxy_next_upstream_tries 3;
proxy_next_upstream_timeout 15s;
proxy_connect_timeout 5s;
proxy_read_timeout 60s;
proxy_send_timeout 60s;
```

## 2. Add upstream blocks (before the first server{} block)

```nginx
# ── Upstream blocks (enables proxy_next_upstream retry) ───────────────────
# Docker DNS (127.0.0.11) re-resolves container IPs after restarts.

upstream audio_llm_frontend {
    server audio-llm-test-frontend-1:5173;
    keepalive 16;
}

upstream audio_llm_backend {
    server audio-llm-test-backend-1:8000;
    keepalive 16;
}

# Add more upstreams here for other apps as needed.
# Template:
# upstream <app>_app {
#     server <container-name>:<port>;
#     keepalive 16;
# }
```

## 3. Update the Audio LLM Test server block

Replace the current `# ── Audio LLM Test ─────` server block with:

```nginx
# ── Audio LLM Test ─────────────────────────────────────────────────────────
server {
    listen 80;
    server_name llmtest.ryanmihelich.com;

    # Larger body for audio file uploads
    client_max_body_size 200M;

    location /internal/authelia/authz {
        internal;
        set $upstream http://authelia:9091/api/authz/auth-request;
        proxy_pass $upstream;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header X-Original-Method $request_method;
        proxy_set_header X-Original-URL https://$http_host$request_uri;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Pipeline Studio dev server (WebSocket)
    location /pipeline-studio/ {
        auth_request /internal/authelia/authz;
        auth_request_set $target_url https://$http_host$request_uri;
        auth_request_set $user $upstream_http_remote_user;
        auth_request_set $groups $upstream_http_remote_groups;
        auth_request_set $name $upstream_http_remote_name;
        proxy_set_header Remote-User $user;
        proxy_set_header Remote-Groups $groups;
        proxy_set_header Remote-Name $name;
        error_page 401 =302 https://auth.ryanmihelich.com/?rd=$target_url;

        set $pipeline_studio http://audio-llm-test-pipeline-studio-1:5174;
        proxy_pass $pipeline_studio$request_uri;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        proxy_cache off;
    }

    # API — proxy directly to backend with retry on 502
    location /api/ {
        auth_request /internal/authelia/authz;
        auth_request_set $target_url https://$http_host$request_uri;
        auth_request_set $user $upstream_http_remote_user;
        auth_request_set $groups $upstream_http_remote_groups;
        auth_request_set $name $upstream_http_remote_name;
        proxy_set_header Remote-User $user;
        proxy_set_header Remote-Groups $groups;
        proxy_set_header Remote-Name $name;
        error_page 401 =302 https://auth.ryanmihelich.com/?rd=$target_url;

        proxy_pass http://audio_llm_backend$request_uri;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;  # long timeout for LLM inference
    }

    # Frontend — proxy to Vite dev server with retry on 502
    location / {
        auth_request /internal/authelia/authz;
        auth_request_set $target_url https://$http_host$request_uri;
        auth_request_set $user $upstream_http_remote_user;
        auth_request_set $groups $upstream_http_remote_groups;
        auth_request_set $name $upstream_http_remote_name;
        proxy_set_header Remote-User $user;
        proxy_set_header Remote-Groups $groups;
        proxy_set_header Remote-Name $name;
        error_page 401 =302 https://auth.ryanmihelich.com/?rd=$target_url;

        proxy_pass http://audio_llm_frontend$request_uri;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
    }

    # Custom 502/503 page shown during deploys
    error_page 502 503 504 /deploying.html;
    location = /deploying.html {
        root /usr/share/nginx/html/www;
        internal;
        add_header Retry-After 15 always;
        add_header Cache-Control "no-store" always;
    }
}
```

## 4. Add the 502 maintenance page

Create `/home/ryan/server/www/deploying.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="10">
  <title>Deploying — LLM Test</title>
  <style>
    body { font-family: system-ui, sans-serif; display: flex; align-items: center;
           justify-content: center; height: 100vh; margin: 0; background: #0f172a; color: #e2e8f0; }
    .card { text-align: center; padding: 2rem; }
    h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
    p { color: #94a3b8; margin: 0.25rem 0; }
    .spinner { width: 2rem; height: 2rem; border: 3px solid #334155;
               border-top-color: #60a5fa; border-radius: 50%;
               animation: spin 1s linear infinite; margin: 1rem auto; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="card">
    <div class="spinner"></div>
    <h1>Deploying…</h1>
    <p>New version is starting up. This page refreshes automatically.</p>
    <p style="font-size:0.8rem;margin-top:1rem;color:#475569">Usually ready in 30–60 seconds</p>
  </div>
</body>
</html>
```

## 5. Apply changes

```bash
# Validate config
docker exec server-nginx-1 nginx -t

# Reload (zero-downtime — no restart needed)
docker exec server-nginx-1 nginx -s reload
```

## Notes on proxy_next_upstream with single backends

`proxy_next_upstream` retries to the **next** server in an upstream group.
With a single backend there's no next server, so it won't buffer the entire
restart window. The real fix is the deploy script (which waits for the container
to report healthy before exiting), combined with:

- A fast `start_period` in the healthcheck so docker knows when the app is ready
- Upstream blocks so nginx at least retries on connection errors (first ~500ms
  of a restart attempt will refuse connections; `proxy_next_upstream error` gives
  the request one more chance after that brief window)
- The `deploying.html` auto-refresh page so users aren't stuck on a raw 502

To get truly zero-downtime (no gap at all), you'd need two container replicas
behind a load balancer — out of scope for this single-host setup.
