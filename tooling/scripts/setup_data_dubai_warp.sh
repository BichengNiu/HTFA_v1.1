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
sudo apt-get -o Dir::Etc::sourcelist=sources.list.d/cloudflare-client.list \
    -o Dir::Etc::sourceparts=- -o APT::Get::List-Cleanup=0 \
    -o Acquire::Retries=2 -o Acquire::https::Timeout=20 update -qq

# The official package also contains the desktop UI. Extract its CLI/daemon
# rather than installing WebKit, multimedia and other unused GUI dependencies.
# apt verifies the package checksum against the signed repository metadata.
warp_workdir="$RUNNER_TEMP/data-dubai-warp"
mkdir -p "$warp_workdir"
(
    cd "$warp_workdir"
    apt-get -o Acquire::Retries=2 -o Acquire::https::Timeout=20 download cloudflare-warp
)
packages=("$warp_workdir"/cloudflare-warp_*.deb)
if [[ ${#packages[@]} != 1 || ! -f "${packages[0]}" ]]; then
    printf 'Expected exactly one verified WARP package.\n' >&2
    exit 1
fi
dpkg-deb --extract "${packages[0]}" "$warp_workdir/root"
warp_svc=$(find "$warp_workdir/root" -type f -name warp-svc -print -quit)
warp_cli=$(find "$warp_workdir/root" -type f -name warp-cli -print -quit)
if [[ -z "$warp_svc" || -z "$warp_cli" ]]; then
    printf 'Official WARP CLI or daemon is missing.\n' >&2
    exit 1
fi
if ldd "$warp_svc" "$warp_cli" | grep 'not found'; then
    printf 'Headless WARP runtime dependency missing.\n' >&2
    exit 1
fi
getent group warp >/dev/null || sudo groupadd --system warp
sudo install -d -m 700 /var/lib/cloudflare-warp
nohup sudo "$warp_svc" > "$RUNNER_TEMP/data-dubai-warp-daemon.log" 2>&1 &
sleep 3

sudo timeout 60 "$warp_cli" --accept-tos registration new
sudo timeout 30 "$warp_cli" --accept-tos mode proxy
sudo timeout 30 "$warp_cli" --accept-tos proxy port 40000
sudo timeout 30 "$warp_cli" --accept-tos connect

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
sudo timeout 15 "$warp_cli" --accept-tos status
exit 1
