#!/bin/bash
# =============================================================================
# WarPie Release Builder
# =============================================================================
# Creates a release tarball containing only runtime files needed for
# Raspberry Pi deployment. Excludes development tooling, tests, and CI files.
#
# Usage:
#   ./scripts/build-release.sh [version]
#
# If version is not provided, it will be read from pyproject.toml
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Get script directory and repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="${REPO_ROOT}/build"

# Get version from argument or pyproject.toml
get_version() {
    if [[ -n "${1:-}" ]]; then
        echo "$1"
    elif [[ -f "${REPO_ROOT}/pyproject.toml" ]]; then
        grep -E '^version\s*=' "${REPO_ROOT}/pyproject.toml" | head -1 | sed 's/.*=\s*"\(.*\)"/\1/'
    else
        log_error "Version not provided and pyproject.toml not found"
        exit 1
    fi
}

VERSION=$(get_version "${1:-}")
RELEASE_NAME="warpie-${VERSION}"
RELEASE_DIR="${BUILD_DIR}/${RELEASE_NAME}"
TARBALL="${BUILD_DIR}/${RELEASE_NAME}.tar.gz"
CHECKSUM="${BUILD_DIR}/${RELEASE_NAME}.sha256"

log_info "Building WarPie release v${VERSION}"
log_info "Output: ${TARBALL}"

# Clean and create build directory
rm -rf "${BUILD_DIR}"
mkdir -p "${RELEASE_DIR}"

# =============================================================================
# Copy runtime files
# =============================================================================

log_info "Copying runtime files..."

# bin/ - Executable scripts (exclude __pycache__)
mkdir -p "${RELEASE_DIR}/bin"
cp "${REPO_ROOT}/bin/wardrive.sh" "${RELEASE_DIR}/bin/"
cp "${REPO_ROOT}/bin/warpie-control" "${RELEASE_DIR}/bin/"
cp "${REPO_ROOT}/bin/warpie-network-manager.sh" "${RELEASE_DIR}/bin/"
cp "${REPO_ROOT}/bin/warpie-filter-manager.py" "${RELEASE_DIR}/bin/"
cp "${REPO_ROOT}/bin/warpie-filter-manager.sh" "${RELEASE_DIR}/bin/"
cp "${REPO_ROOT}/bin/warpie-filter-processor.py" "${RELEASE_DIR}/bin/"
cp "${REPO_ROOT}/bin/warpie-exclude-ssid.sh" "${RELEASE_DIR}/bin/"
cp "${REPO_ROOT}/bin/validate-warpie.sh" "${RELEASE_DIR}/bin/"
log_success "bin/ copied"

# install/ - Installation scripts
mkdir -p "${RELEASE_DIR}/install"
cp "${REPO_ROOT}/install/install.sh" "${RELEASE_DIR}/install/"
cp "${REPO_ROOT}/install/warpie_config.py" "${RELEASE_DIR}/install/"
log_success "install/ copied"

# systemd/ - Service files
mkdir -p "${RELEASE_DIR}/systemd"
cp "${REPO_ROOT}/systemd/"*.service "${RELEASE_DIR}/systemd/"
log_success "systemd/ copied"

# web/ - Web application (exclude __pycache__)
mkdir -p "${RELEASE_DIR}/web"
cp "${REPO_ROOT}/web/__init__.py" "${RELEASE_DIR}/web/"
cp "${REPO_ROOT}/web/app.py" "${RELEASE_DIR}/web/"
cp "${REPO_ROOT}/web/config.py" "${RELEASE_DIR}/web/"

mkdir -p "${RELEASE_DIR}/web/routes"
cp "${REPO_ROOT}/web/routes/__init__.py" "${RELEASE_DIR}/web/routes/"
find "${REPO_ROOT}/web/routes" -maxdepth 1 -name "*.py" ! -name "__init__.py" -exec cp {} "${RELEASE_DIR}/web/routes/" \;

mkdir -p "${RELEASE_DIR}/web/templates"
cp -r "${REPO_ROOT}/web/templates/"* "${RELEASE_DIR}/web/templates/" 2>/dev/null || true

mkdir -p "${RELEASE_DIR}/web/static"
cp -r "${REPO_ROOT}/web/static/"* "${RELEASE_DIR}/web/static/" 2>/dev/null || true
log_success "web/ copied"

# Root files
cp "${REPO_ROOT}/LICENSE" "${RELEASE_DIR}/"
cp "${REPO_ROOT}/README.md" "${RELEASE_DIR}/"
cp "${REPO_ROOT}/CHANGELOG.md" "${RELEASE_DIR}/"
log_success "Root files copied"

# =============================================================================
# Create version file
# =============================================================================

echo "${VERSION}" > "${RELEASE_DIR}/VERSION"
log_success "VERSION file created"

# =============================================================================
# Create tarball
# =============================================================================

log_info "Creating tarball..."
cd "${BUILD_DIR}"
tar -czf "${RELEASE_NAME}.tar.gz" "${RELEASE_NAME}"
log_success "Tarball created: ${TARBALL}"

# =============================================================================
# Generate checksum
# =============================================================================

log_info "Generating SHA256 checksum..."
cd "${BUILD_DIR}"
sha256sum "${RELEASE_NAME}.tar.gz" > "${RELEASE_NAME}.sha256"
log_success "Checksum: $(cat "${CHECKSUM}")"

# =============================================================================
# Summary
# =============================================================================

TARBALL_SIZE=$(du -h "${TARBALL}" | cut -f1)

echo ""
echo -e "${GREEN}==============================================================================${NC}"
echo -e "${GREEN}  Release Build Complete${NC}"
echo -e "${GREEN}==============================================================================${NC}"
echo ""
echo -e "  Version:  ${BLUE}${VERSION}${NC}"
echo -e "  Tarball:  ${TARBALL}"
echo -e "  Size:     ${TARBALL_SIZE}"
echo -e "  Checksum: ${CHECKSUM}"
echo ""
echo -e "  ${YELLOW}Files included:${NC}"
find "${RELEASE_DIR}" -type f | sed "s|${RELEASE_DIR}/|    |" | sort
echo ""
echo -e "${GREEN}==============================================================================${NC}"
