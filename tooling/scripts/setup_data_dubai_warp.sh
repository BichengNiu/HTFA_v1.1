#!/usr/bin/env bash
# Ephemeral GitHub-hosted Linux setup; no account license or paid plan is used.
set -euo pipefail

if [[ "${RUNNER_OS:-}" != Linux || -z "${GITHUB_ENV:-}" ]]; then
    printf 'This setup is restricted to GitHub-hosted Linux jobs.\n' >&2
    exit 1
fi

curl --fail --silent --show-error --location \
    https://pkg.cloudflareclient.com/pubkey.gpg \
    --output "$RUNNER_TEMP/cloudflare-warp-pubkey.gpg"
sudo gpg --yes --dearmor \
    --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg \
    "$RUNNER_TEMP/cloudflare-warp-pubkey.gpg"
printf 'deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ %s main\n' \
    "$(lsb_release -cs)" | sudo tee /etc/apt/sources.list.d/cloudflare-client.list >/dev/null
sudo apt-get update -qq
sudo apt-get install -y cloudflare-warp
sudo systemctl start warp-svc

timeout 60 warp-cli --accept-tos registration new
warp-cli --accept-tos mode proxy
warp-cli --accept-tos proxy port 40000
warp-cli --accept-tos connect

for attempt in {1..18}; do
    if curl --fail --silent --show-error --max-time 8 \
        --proxy http://127.0.0.1:40000 \
        https://www.cloudflare.com/cdn-cgi/trace \
        --output "$RUNNER_TEMP/data-dubai-warp-trace.txt" \
        && grep -q '^warp=on$' "$RUNNER_TEMP/data-dubai-warp-trace.txt"; then
        grep -E '^(ip|loc|warp)=' "$RUNNER_TEMP/data-dubai-warp-trace.txt"
        printf 'HTFA_DATA_DUBAI_PROXY_URL=http://127.0.0.1:40000\n' >> "$GITHUB_ENV"
        exit 0
    fi
    sleep 2
done
printf 'The free WARP route did not become ready; no data-source success was reported.\n' >&2
warp-cli --accept-tos status
exit 1
