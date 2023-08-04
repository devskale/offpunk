#!/bin/python
#opnk stand for "Open like a PuNK".
#It will open any file or URL and display it nicely in less.
#If not possible, it will fallback to xdg-open
#URL are retrieved through netcache
import netcache
import offutils

class opencache():
    def __init__(self):
        self.temp_files = {}
        self.rendererdic = {}

    def opnk(inpath,terminal=True):
        #if terminal = False, we don’t try to open in the terminal,
        #we immediately fallback to xdg-open.
        #netcache currently provide the path if it’s a file.
        #may this should be migrated here.
        path = netcache.get_cache_path(inpath)

        #TODO: migrate here  ansirenderer display
        1. À partir du path, tenter le ansirenderer
        2. Sauver le rendu dans self.temp_files[mode] (donc le mode doit être passé à opnk)
        3. Sauver le renderer dans self.rendererdic
        3. Donner à less
        4. sinon, donner à xdg-open


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("content",metavar="INPUT", nargs="*", type=argparse.FileType("r"), 
                         default=sys.stdin, help="Path to the file or URL to open")
    args = parser.parse_args()
    cache = opencache()
    for f in args.content:
        cache.opnk(f)

if __name__ == "__main__":
    main()
