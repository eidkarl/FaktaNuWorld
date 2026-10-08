#!/usr/bin/env bash
# Non-root Debian install using signed repository metadata and verified package downloads.
set -euo pipefail
if command -v espeak-ng >/dev/null; then
  espeak-ng --voices=sv
  exit 0
fi
faktanu_tools="${FAKTANU_TOOLS_DIR:-/workspace/.faktanu-tools}"
mkdir -p "$faktanu_tools/apt/lists/partial" "$faktanu_tools/apt/cache/archives/partial" "$faktanu_tools/apt/parts" "$faktanu_tools/debs" "$faktanu_tools/runtime"
if test -x "$faktanu_tools/runtime/usr/bin/espeak-ng"; then
  LD_LIBRARY_PATH="$faktanu_tools/runtime/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$faktanu_tools/runtime/usr/bin/espeak-ng" --path="$faktanu_tools/runtime/usr/lib/x86_64-linux-gnu" --voices=sv
  exit 0
fi
. /etc/os-release
if test "$ID" != debian || test "$VERSION_CODENAME" != trixie || test "$(dpkg --print-architecture)" != amd64; then
  echo 'Install espeak-ng with your OS package manager; local bootstrap supports Debian trixie amd64.' >&2
  exit 1
fi
cat > "$faktanu_tools/apt/config" <<CONFIG
Dir::Etc::parts "$faktanu_tools/apt/parts";
Dir::Etc::main "/dev/null";
Dir::Etc::sourcelist "$faktanu_tools/apt/sources.list";
Dir::Etc::sourceparts "$faktanu_tools/apt/parts";
Dir::State::lists "$faktanu_tools/apt/lists";
Dir::Cache "$faktanu_tools/apt/cache";
Dir::Cache::archives "$faktanu_tools/apt/cache/archives";
APT::Get::List-Cleanup "false";
CONFIG
cat > "$faktanu_tools/apt/sources.list" <<'SOURCES'
deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian trixie main
SOURCES
APT_CONFIG="$faktanu_tools/apt/config" /usr/bin/apt-get update
cd "$faktanu_tools/debs"
APT_CONFIG="$faktanu_tools/apt/config" /usr/bin/apt-get download espeak-ng espeak-ng-data libespeak-ng1 libpcaudio0 libsonic0
for package in ./*.deb; do
  dpkg-deb -x "$package" "$faktanu_tools/runtime"
done
LD_LIBRARY_PATH="$faktanu_tools/runtime/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$faktanu_tools/runtime/usr/bin/espeak-ng" --path="$faktanu_tools/runtime/usr/lib/x86_64-linux-gnu" --voices=sv
