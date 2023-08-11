#!/bin/python
#opnk stand for "Open like a PuNK".
#It will open any file or URL and display it nicely in less.
#If not possible, it will fallback to xdg-open
#URL are retrieved through netcache
import os
import sys
import tempfile
import argparse
import netcache
import ansirenderer
import offutils
import shutil
from offutils import run,term_width

_HAS_XDGOPEN = shutil.which('xdg-open')

less_version = 0
if not shutil.which("less"):
    print("Please install the pager \"less\" to run Offpunk.")
    print("If you wish to use another pager, send me an email !")
    print("(I’m really curious to hear about people not having \"less\" on their system.)")
    sys.exit()
output = run("less --version")
# We get less Version (which is the only integer on the first line)
words = output.split("\n")[0].split()
less_version = 0
for w in words:
    if w.isdigit():
        less_version = int(w)
# restoring position only works for version of less > 572
if less_version >= 572:
    _LESS_RESTORE_POSITION = True
else:
    _LESS_RESTORE_POSITION = False
#_DEFAULT_LESS = "less -EXFRfM -PMurl\ lines\ \%lt-\%lb/\%L\ \%Pb\%$ %s"
# -E : quit when reaching end of file (to behave like "cat")
# -F : quit if content fits the screen (behave like "cat")
# -X : does not clear the screen
# -R : interpret ANSI colors correctly
# -f : suppress warning for some contents
# -M : long prompt (to have info about where you are in the file)
# -W : hilite the new first line after a page skip (space)
# -i : ignore case in search
# -S : do not wrap long lines. Wrapping is done by offpunk, longlines
# are there on purpose (surch in asciiart)
#--incsearch : incremental search starting rev581
if less_version >= 581:
    less_base = "less --incsearch --save-marks -~ -XRfMWiS"
elif less_version >= 572:
    less_base = "less --save-marks -XRfMWiS"
else:
    less_base = "less -XRfMWiS"
_DEFAULT_LESS = less_base + " \"+''\" %s"
_DEFAULT_CAT = less_base + " -EF %s"

def less_cmd(file, histfile=None,cat=False,grep=None):
    if histfile:
        env = {"LESSHISTFILE": histfile}
    else:
        env = {}
    if cat:
        cmd_str = _DEFAULT_CAT
    elif grep:
        grep_cmd = _GREP
        #case insensitive for lowercase search
        if grep.islower():
            grep_cmd += " -i"
        cmd_str = _DEFAULT_CAT + "|" + grep_cmd + " %s"%grep
    else:
        cmd_str = _DEFAULT_LESS
    run(cmd_str, parameter=file, direct_output=True, env=env)

class opencache():
    def __init__(self):
        self.temp_files = {}
        # This dictionary contains an url -> ansirenderer mapping. This allows 
        # to reuse a renderer when visiting several times the same URL during
        # the same session
        self.rendererdic = {}
        self.less_histfile = {}
        self.mime_handlers = {}

    def _get_handler_cmd(self, mimetype):
        # Now look for a handler for this mimetype
        # Consider exact matches before wildcard matches
        exact_matches = []
        wildcard_matches = []
        for handled_mime, cmd_str in self.mime_handlers.items():
            if "*" in handled_mime:
                wildcard_matches.append((handled_mime, cmd_str))
            else:
                exact_matches.append((handled_mime, cmd_str))
        for handled_mime, cmd_str in exact_matches + wildcard_matches:
            if fnmatch.fnmatch(mimetype, handled_mime):
                break
        else:
            # Use "xdg-open" as a last resort.
            if _HAS_XDGOPEN:
                cmd_str = "xdg-open %s"
            else:
                cmd_str = "echo \"Can’t find how to open \"%s"
                print("Please install xdg-open (usually from xdg-util package)")
        return cmd_str

    # Return the handler for a specific mimetype.
    # Return the whole dic if no specific mime provided
    def get_handlers(self,mime=None):
        if mime and mime in self.mime_handlers.keys():
            return self.mime_handlers[mime]
        elif mime:
            return None
        else:
            return self.mime_handlers

    def set_handler(self,mime,handler):
        previous = None
        if mime in self.mime_handlers.keys():
            previous = self.mime_handlers[mime]
        self.mime_handlers[mime] = handler
        if "%s" not in handler:
            print("WARNING: this handler has no %%s, no filename will be provided to the command")
            if previous:
                print("Previous handler was %s"%previous)

    def get_renderer(self,inpath,mode=None):
        renderer = None
        # We remove the ##offpunk_mode= from the URL
        # If mode is already set, we don’t use the part from the URL
        findmode = inpath.split("##offpunk_mode=")
        if len(findmode) > 1:
            inpath = findmode[0]
            if not mode:
                if findmode[1] in ["full"] or findmode[1].isnumeric():
                    mode = findmode[1]
        path = netcache.get_cache_path(inpath)
        if path:
            if inpath not in self.rendererdic.keys():
                renderer = ansirenderer.renderer_from_file(path,inpath)
                if renderer:
                    self.rendererdic[inpath] = renderer
            else:
                renderer = self.rendererdic[inpath]
        if renderer and mode:
            renderer.set_mode(mode)
        return renderer

    def grep(self,inpath,searchterm):
        print("TODO: implement grep")

    def opnk(self,inpath,mode=None,terminal=True):
        #Return True if inpath opened in Terminal
        # False otherwise
        #if terminal = False, we don’t try to open in the terminal,
        #we immediately fallback to xdg-open.
        #netcache currently provide the path if it’s a file.
        #may this should be migrated here.
        renderer = self.get_renderer(inpath,mode=mode)
        if terminal and renderer:
            wtitle = renderer.get_formatted_title()
            body = wtitle + "\n" + renderer.get_body(mode=mode)
            # We actually put the body in a tmpfile before giving it to less
            if mode not in self.temp_files:
                tmpf = tempfile.NamedTemporaryFile("w", encoding="UTF-8", delete=False)
                self.temp_files[mode] = tmpf.name
                tmpf.write(body)
                tmpf.close()
            if mode not in self.less_histfile:
                firsttime = True
                tmpf = tempfile.NamedTemporaryFile("w", encoding="UTF-8", delete=False)
                self.less_histfile[mode] = tmpf.name
            else:
                firsttime = False
            grep=None
            less_cmd(self.temp_files[mode], histfile=self.less_histfile[mode],cat=firsttime,grep=grep)
            return True
        #maybe, we have no renderer. Or we want to skip it.
        else:
            cmd_str = self._get_handler_cmd(ansirenderer.get_mime(inpath))
            try:
                run(cmd_str, parameter=netcache.get_cache_path(inpath), direct_output=True)
            except FileNotFoundError:
                print("Handler program %s not found!" % shlex.split(cmd_str)[0])
                print("You can use the ! command to specify another handler program or pipeline.")
            return False
        

    def get_temp_file(self,mode=None):
        if not mode: mode = self.last_mode
        if mode in self.temp_files:
            return self.temp_files[mode]
        else:
            return None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("content",metavar="INPUT", nargs="*", 
                         default=sys.stdin, help="Path to the file or URL to open")
    args = parser.parse_args()
    cache = opencache()
    for f in args.content:
        cache.opnk(f)

if __name__ == "__main__":
    main()
