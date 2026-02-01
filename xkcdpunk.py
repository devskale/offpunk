#!/usr/bin/env python3
import sys
import argparse
import gettext
import random

import netcache
import openk
from offutils import _LOCALE_DIR

gettext.bindtextdomain('offpunk', _LOCALE_DIR)
gettext.textdomain('offpunk')
_ = gettext.gettext

def get_latest(name="xkcd",offline=False):
    if name == "xkcd":
        rss = "https://xkcd.com/atom.xml"
        latest_link = 2
    #validity is 12h = 43200 seconds
    if offline: validity = 0
    else: validity = 43200
    cache = openk.opencache()
    netcache.fetch(rss,validity=validity,offline=offline)
    r = cache.get_renderer(rss)
    if not r:
        print("xkcdpunk needs to be run at least once online to fetch the rss feed")
        return None
    else:
        link = r.get_link(latest_link)
        return link

def main():
    descri = _("xkcdpunk is a tool to display a given XKCD comic in your terminal")
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
    cache = openk.opencache()
    url = "https://xkcd.com/"
    u = None
    for n in args.number:
        if n.isdigit():
            u = url + str(n) + "/"
        elif n == "random":
            # for the random, we simply take the biggest known xkcd comic
            # and find a number between 1 and latest
            last_url = get_latest(offline=args.offline)
            if last_url:
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
            u = get_latest(offline=args.offline)
    if not u:
        #By default, we get the latest
        u = get_latest(offline=args.offline)
    if u:
        cache.openk(u)
    else:
        print("No cached XKCD comics were found. Please run xkcdpunk online to build the cache")


if __name__ == "__main__":
    main()
