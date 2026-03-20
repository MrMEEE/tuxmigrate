#!/usr/bin/env bash
# post-install.sh - executed by rpm after the package is installed/upgraded.
# Runs the tuxmigrate role on the local machine.
set -euo pipefail

SITE_YML="/usr/share/tuxmigrate/site.yml"

# Resolve the package name from this script's install path if customised.
# The site.yml embedded by fpm already has the correct role path hard-coded.

echo "[tuxmigrate] Running configuration changes..."

if ! command -v ansible-playbook &>/dev/null; then
    echo "[tuxmigrate] ERROR: ansible-playbook not found. Install Ansible and re-run:"
    echo "  ansible-playbook ${SITE_YML} -c local"
    exit 1
fi

ansible-playbook "${SITE_YML}" --connection=local

echo "[tuxmigrate] Done."
