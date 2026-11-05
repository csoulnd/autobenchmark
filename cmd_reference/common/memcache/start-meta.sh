#!/usr/bin/env bash
# Replace {INSTALL_PATH} with the actual installation path before running.
export MMC_META_CONFIG_PATH="{INSTALL_PATH}/memcache_hybrid/config/mmc-meta.conf"

python -c "from memcache_hybrid import MetaService; MetaService.main()"
