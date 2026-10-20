#!/usr/bin/env bash
set -Eeuo pipefail
RICE_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$RICE_ROOT/installer/common.sh"
rice_main arch "$@"
