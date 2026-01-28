#!/usr/bin/env python3
import sys
import argparse
import gettext
import random

import netcache
import opnk
from offutils import _LOCALE_DIR

gettext.bindtextdomain('offpunk', _LOCALE_DIR)
gettext.textdomain('offpunk')
_ = gettext.gettext

def get_latest(name="xkcd"):
    if name == "xkcd":
        rss = "https://xkcd.com/atom.xml"
        latest_link = 2
    cache = opnk.opencache()
    r = cache.get_renderer(rss)
    print(r.get_links())
    link = r.get_link(latest_link)
    return link

# TODO : online/offline ?
# TODO : if offline, mark to fetch ! (will require list refactoring)
# TODO : add XKCD to the packaging and documentation
# BUG : wtitle red is misaligned

def main():
    descri = _("xkcd is a tool to display a given XKCD comic in your terminal")
    parser = argparse.ArgumentParser(prog="xkcd", description=descri)
    parser.add_argument(
            "number",
            nargs="*",
            help=_("XKCD comic number")
            )
    parser.add_argument(
            "--offline", action="store_true", help=_("Only access cached comics")
            )
    args = parser.parse_args()
    cache = opnk.opencache()
    url = "https://xkcd.com/"
    for n in args.number:
        u = None
        if n.isdigit():
            u = url + str(n) + "/"
        elif n == "random":
            # for the random, we simply take the biggest known xkcd comic
            # and find a number between 1 and latest
            last_url = get_latest()
            last = last_url.strip("/").split("/")[-1]
            if last.isdigit():
                value = random.randrange(2,int(last))
                u = url + str(value) + "/"
                if args.offline:
                    # If offline, we check for a valid netcache version
                    # We introduce a max counter to not search infinitely
                    max_counter = 0
                    while not netcache.is_cache_valid(u) and max_counter < 1000:
                        value = random.randrange(2,int(last))
                        u = url + str(value) + "/"
                        max_counter += 1
        elif n == "latest":
            u = get_latest()
        if u:
            cache.opnk(u)


if __name__ == "__main__":
    main()
