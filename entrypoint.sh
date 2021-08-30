#!/bin/sh
# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved.

set -e

if [ $# -eq 0 ]; then
    # Default (if no args provided).
    sh -c "ptr"
else
    # Custom args.
    sh -c "ptr $*"
fi
