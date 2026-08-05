#!/bin/env bash

# This script creates an appimage of minigalaxy by amending an already existing manylinux-python appimage as base.
#
# Basic steps:
# 1. Download the image, utils and dependencies
# 2. Unpack the base image
# 3. Build a wheel for MG
# 4. Install carefully picked, compatible versions of 'requests' and 'PyGObject' + minigalaxy
# 5. add/patch/override appimage specific files
# 6. Repack
# 7. Enjoy
#
# This procedure is the result of weeks of trial and error with different ways to utilize 
# 'python_appimage', 'auditwheel', the gtk-plugin for linuxdeploy and some others

# vorgehensweise:
# yum
# basis-appimage extrahieren
# runtime as extract als basis nutzen
# deps installieren
# MG bauen
# mg installieren mit --force-install --no-deps
# requirements installieren (mit festgenagelten versionen)
# AppRun patchen: LD_LIBRARY_PATH+=APPDIR/usr/lib
# verpacken mit linuxdeploy

# when not in docker, check if docker command exists
if ! [ -e /mnt/minigalaxy ]; then
  if ! which docker; then
    echo "'docker' is required" >&2
    exit 1
  fi
fi

set -e

export SCRIPT_DIR=$(dirname "$(realpath "${BASH_SOURCE[0]}")")
export REPO_ROOT=$(realpath "${SCRIPT_DIR}/..")

WORK_DIR="${REPO_ROOT}/build-appimage"
OUTPUT_DIR="${WORK_DIR}/output"
APPIMAGE_SOURCES="${REPO_ROOT}/appimage-recipe"

# This is a convenience helper for self-bootstrapping the build file in a local environment
if ! [ -e /mnt/minigalaxy ]; then
  sudo docker run \
    --rm --name build-mg \
    -v "${REPO_ROOT}:/mnt/minigalaxy" \
    -it quay.io/pypa/manylinux_2_28_x86_64 \
    "/mnt/minigalaxy/scripts/$(basename "${BASH_SOURCE[0]}")"
  sudo docker container wait /build-mg
  exit $?
fi

cd /mnt/minigalaxy
mkdir -p "${WORK_DIR}" "${OUTPUT_DIR}"
rm -rf "${WORK_DIR}"/*

# pass a variable whose name matches '(.*)_URL', which points to a file to download
# 1. Extract filename from URL
# 2. Download the the file into $WORK_DIR, if it doesn't exist'
# 3. The absolute path to the downloaded file is placed in another variable, named like the input,
#    But without _URL.
# Example: 
#   PYTHON_URL=https://some.domain/sub/pythonabc-3.48.tgz
#   download_if_required PYTHON_URL
#   -> download: $WORK_DIR/pythonabc-3.48.tgz
#   -> define: PYTHON=$WORK_DIR/pythonabc-3.48.tgz
function download_if_required {
  local -n url="$1"
  local filename="${WORK_DIR}/$(basename "${url}")"
  if ! [ -f "${filename}" ]; then
    wget "${url}" -O "${filename}"
  fi
  declare -g "${1%_URL}=${filename}"
}

yum update -y
yum -y install \
  wget \
  cairo-gobject-devel \
  gobject-introspection-devel \
  cairo-devel \
  webkitgtk4 \
  gtk3-devel \
  python3-gobject

LINUXDEPLOY_URL="https://github.com/linuxdeploy/linuxdeploy/releases/download/1-alpha-20250213-2/linuxdeploy-x86_64.AppImage"
download_if_required LINUXDEPLOY_URL

# Define a batch of helper functions for easier python commands to manipulate the AppDir's instance.'
PYEXE="${WORK_DIR}/AppDir/AppRun"
function python { "${PYEXE}" "$@"; }
function py-m { python -m "$@"; }
function pip { py-m pip "$@"; }

cd "${WORK_DIR}"
chmod +x *.AppImage

# build a python appimage
# Reason: The prepackaged does not have a fixed version URL to wget 
# It shifts all the time when the docker container is updated.
# Since we're already running in a manylinux docker, we can as well just extract the runtime directly
python3.12 -m pip install python_appimage
python3.12 -m python_appimage build local
mv python*AppImage python.AppImage
BASEIMG="$(pwd)/python.AppImage"
"${BASEIMG}" --appimage-extract
mv squashfs-root AppDir

### Build and install MG + deps

# Install dependencies
pip install -r "${APPIMAGE_SOURCES}/requirements.txt"
# Build MG wheel against the dependencies.
# Theoretically, we could just use 'pip install' directly.
# But building the wheel first allows us to publish this independently as well
py-m build --no-isolation --wheel --outdir "${OUTPUT_DIR}" ..

# Now install the wheel of MG
pip install --no-build-isolation --no-deps "${OUTPUT_DIR}/"minigalaxy*.whl

### Patch/adjust the AppImage

# The 'AppRun'' in the image should be a link to AppDir/usr/bin/python... which is a wrapper script.
# we will copy and patch this to add LD_LIBRARY_PATH and change the python command line to MG instead
# Reason: This gives access to any variable and logic the script prepares for the AppImage already,
# without having to maintain duplications of that for ourselves
mv AppDir/AppRun AppDir/python.sh
# keep the path to the previous, real python exe because it might be needed after tampering with AppRun
PYEXE=$(realpath AppDir/python.sh)
cp -f "${APPIMAGE_SOURCES}/AppRun" AppDir/

# some logging for error debugging
echo "Diff python/AppRun <> mg/AppRun"
sdiff AppDir/python.sh AppDir/AppRun || true

# Desktop files and icons for MG
dfile="io.github.sharkwouter.Minigalaxy.desktop"
cp \
  "${REPO_ROOT}/data/${dfile}" \
  "${REPO_ROOT}/data/icons/192x192/io.github.sharkwouter.Minigalaxy.png" \
  AppDir/
rm AppDir/.DirIcon || true

echo \
"X-AppImage-Version=$(pip list | grep minigalaxy | cut -d' ' -s --output-delimiter='' -f2-)
X-AppImage-Arch=x86_64" \
  >>"AppDir/${dfile}"

# remove desktop, png and sh files for python itself
rm AppDir/python* AppDir/Python* || true

# Final step: Package it up again
# need to extract the AppImage in docker - fuse doesnt work there for various reasons
"${LINUXDEPLOY}" --appimage-extract-and-run \
  --appdir AppDir \
  --desktop-file "AppDir/${dfile}" \
  --icon-file "${REPO_ROOT}/data/icons/128x128/io.github.sharkwouter.Minigalaxy.png" \
  --output appimage

mv Minigalaxy*AppImage "${OUTPUT_DIR}/"
