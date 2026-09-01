#!/usr/bin/env bash
# Installs the pinned LGPL-only, dynamically-linked FFmpeg build this
# project uses for video ingest -- see
# docs/licensing/LICENSE_DECISIONS.md D-006. Used by BOTH
# infra/docker/python.Dockerfile (the worker image, the real runtime) and
# .github/workflows/ci.yml (so CI validates the exact same build the
# product ships, not whatever ffmpeg happens to be preinstalled on the
# runner). One script, one pin, so the two never drift apart.
#
# Why not the distro package? Verified directly during this phase (not
# assumed): `apt-get install ffmpeg` on the current python:3.11-slim base
# image (Debian trixie) resolves to ffmpeg 7.1.5, built with
# `--enable-gpl --enable-libx264 --enable-libx265` -- a GPL build, not the
# LGPL-only build D-006 requires. This is exactly the kind of build-flag
# drift D-006 warned about ("this is a common *silent* violation vector").
#
# Source: BtbN/FFmpeg-Builds (github.com/BtbN/FFmpeg-Builds), a long-
# standing, widely used community build provider that publishes explicit
# gpl/lgpl x static/shared variants -- "lgpl-shared" matches D-006's
# requirement for dynamic linking with no GPL/nonfree components enabled.
#
# Pinned to a specific dated release tag (not the "latest" rolling alias)
# for reproducibility. Verified against BtbN's own published
# checksums.sha256 for this exact release at download time -- never a
# checksum hand-copied into this script (a 64-hex-digit string is itself a
# real transcription-error vector this avoids).
set -euo pipefail

FFMPEG_BUILD_TAG="autobuild-2026-08-29-13-12"
ASSET_NAME="ffmpeg-n8.1.2-50-g1a748fe2cd-linux64-lgpl-shared-8.1.tar.xz"
BASE_URL="https://github.com/BtbN/FFmpeg-Builds/releases/download/${FFMPEG_BUILD_TAG}"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
cd "$WORKDIR"

curl -fsSL -o "$ASSET_NAME" "${BASE_URL}/${ASSET_NAME}"
curl -fsSL -o checksums.sha256 "${BASE_URL}/checksums.sha256"

grep " ${ASSET_NAME}\$" checksums.sha256 > this-asset.sha256
sha256sum -c this-asset.sha256

tar -xf "$ASSET_NAME"
EXTRACTED_DIR="$(find . -maxdepth 1 -type d -name 'ffmpeg-*' | head -1)"
if [ -z "$EXTRACTED_DIR" ]; then
  echo "Could not find extracted ffmpeg directory" >&2
  exit 1
fi

$SUDO install -d /usr/local/lib /usr/local/bin /usr/local/include /usr/local/share/licenses/ffmpeg
$SUDO cp -a "${EXTRACTED_DIR}"/lib/. /usr/local/lib/
$SUDO cp -a "${EXTRACTED_DIR}"/bin/. /usr/local/bin/
$SUDO cp -a "${EXTRACTED_DIR}"/include/. /usr/local/include/
# The build is LGPL-3.0 (see docs/licensing/LICENSE_DECISIONS.md D-006's
# "Correction" section -- --enable-version3 is set, this is not LGPL-2.1+)
# -- an earlier version of this script discarded the tarball's own bundled
# LICENSE.txt, so the deployed image carried the binaries without their
# license text alongside them. Preserve it regardless of this project's
# current hosted-SaaS-only (non-distribution) deployment model, since
# that's cheap insurance if the model ever changes.
if [ -f "${EXTRACTED_DIR}/LICENSE.txt" ]; then
  $SUDO cp "${EXTRACTED_DIR}/LICENSE.txt" /usr/local/share/licenses/ffmpeg/LICENSE.txt
else
  echo "WARNING: no LICENSE.txt found in ${EXTRACTED_DIR} -- D-006 requires it be preserved" >&2
fi
$SUDO ldconfig

echo "Installed pinned LGPL ffmpeg build (tag ${FFMPEG_BUILD_TAG}):"
ffmpeg -version | head -2
