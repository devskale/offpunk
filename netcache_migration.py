#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2023 Sotiris Papatheodorou
# SPDX-License-Identifier: BSD-2-Clause

"""
A script to migrate the offpunk cache to the newest version.

For each new version of offpunk that requires changes to the cache a migration
function should be written. The name of the function should have the format
v<major-version>_<minor-version>_<patch-version> and it should accept the
offpunk cache directory as a string. The function should perform a migration
from the immediately previous cache format. All migration functions must be
called at the end of this script from oldest to newest.
"""

import os
import os.path


def upgrade_to_1(cache_dir: str) -> None:
    """
    Rename index.txt to gophermap in the Gopher protocol cache.
    """
    print("Upgrading cache to version 1: migrating index.txt to gophermap")
    for root, _, files in os.walk(os.path.join(cache_dir, "gopher")):
        for f in files:
            if f == "index.txt":
                src = os.path.join(root, f)
                dst = os.path.join(root, "gophermap")
                os.rename(src, dst)
