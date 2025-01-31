#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2024 Bert Livens
# SPDX-License-Identifier:  AGPL-3.0-only

"""
A script to migrate the offpunk certificate storage to the newest version.

For each new version of offpunk that requires changes to the certificate storage
a migration function should be written, performing a migration from the
immediately previous format.
"""


import datetime
import os
import sqlite3


def upgrade_to_1(data_dir: str, config_dir: str) -> None:
    print("moving from tofu.db to certificates as files")
    db_path = os.path.join(config_dir, "tofu.db")
    # We should check if there’s a db that exists.
    # Warning: the file might exists but be empty.
    if os.path.exists(db_path) and os.path.getsize(db_path) == 0:
        os.remove(db_path)
    if os.path.exists(db_path):
        db_conn = sqlite3.connect(db_path)
        db_cur = db_conn.cursor()
        db_cur.execute("""
                        SELECT hostname, address, fingerprint, count, first_seen, last_seen
                        FROM cert_cache""")
        certs = db_cur.fetchall()
        data_dir = os.path.join(data_dir, "certs")
        os.makedirs(data_dir, exist_ok=True)
        for hostname, address, fingerprint, count, first_seen, last_seen in certs:
            direc = os.path.join(data_dir, hostname)
            os.makedirs(direc, exist_ok=True)
            certdir = os.path.join(direc, address)
            os.makedirs(certdir, exist_ok=True)

            # filename is the fingerprint
            certfile = os.path.join(certdir, str(fingerprint))

            # write  count
            with open(certfile, 'w') as file:
                file.write(str(count))

            # change creation and modification date of file
            first_seen = datetime.datetime.strptime(first_seen, "%Y-%m-%d %H:%M:%S.%f")
            last_seen = datetime.datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S.%f")
            os.utime(certfile, (first_seen.timestamp(), last_seen.timestamp()))

        # remove tofu.db
        os.remove(db_path)
