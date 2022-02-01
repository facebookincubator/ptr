#!/bin/sh
# Copyright © Meta Platforms, Inc. and affiliates

set -e

if [ $# -eq 0 ]; then
    # Default (if no args provided).
    sh -c "ptr"
else
    # Custom args.
    sh -c "ptr $*"
fi
