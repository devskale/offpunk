#!/usr/bin/env python3
#opnk stand for "Open like a PuNK".
#It will open any file or URL and display it nicely in less.
#If not possible, it will fallback to xdg-open
#URL are retrieved through netcache
import os
import sys
import tempfile
import argparse
import netcache
import ansicat
import offutils
import shutil
import time
import fnmatch
from offutils import run,term_width,mode_url,unmode_url,is_local

_HAS_XDGOPEN = shutil.which('xdg-open')
_GREP = "grep --color=auto"

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
    # On macOS the version can be something like 581.2 not just an int:
    if all(_.isdigit() for _ in w.split(".")):
        less_version = int(w.split(".", 1)[0])
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
def less_cmd(file, histfile=None,cat=False,grep=None):
    less_prompt = "page %%d/%%D- lines %%lb/%%L - %%Pb\\%%"
    if less_version >= 581:
        less_base = "less --incsearch --save-marks -~ -XRfWiS -P \"%s\""%less_prompt
    elif less_version >= 572:
        less_base = "less --save-marks -XRfMWiS"
    else:
        less_base = "less -XRfMWiS"
    _DEFAULT_LESS = less_base + " \"+''\" %s"
    _DEFAULT_CAT = less_base + " -EF %s"
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
        # We have a cache of the rendering of file and, for each one,
        # a less_histfile containing the current position in the file
        self.temp_files = {}
        self.less_histfile = {}
        # This dictionary contains an url -> ansirenderer mapping. This allows 
        # to reuse a renderer when visiting several times the same URL during
        # the same session
        # We save the time at which the renderer was created in renderer_time
        # This way, we can invalidate the renderer if a new version of the source
        # has been downloaded
        self.rendererdic = {}
        self.renderer_time = {}
        self.mime_handlers = {}
        self.last_mode = {}
        self.last_width = term_width(absolute=True)

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

    def get_renderer(self,inpath,mode=None,theme=None):
        # We remove the ##offpunk_mode= from the URL
        # If mode is already set, we don’t use the part from the URL
        inpath,newmode = unmode_url(inpath)
        if not mode: mode = newmode
        # If we still doesn’t have a mode, we see if we used one before
        if not mode and inpath in self.last_mode.keys():
            mode = self.last_mode[inpath]
        elif not mode:
            #default mode is readable
            mode = "readable"
        renderer = None
        path = netcache.get_cache_path(inpath)
        if path:
            usecache = inpath in self.rendererdic.keys() and not is_local(inpath)
            #Screen size may have changed
            width = term_width(absolute=True)
            if usecache and self.last_width != width:
                self.cleanup()
                usecache = False
                self.last_width = width
            if usecache:
                if inpath in self.renderer_time.keys():
                    last_downloaded = netcache.cache_last_modified(inpath)
                    last_cached = self.renderer_time[inpath]
                    if last_cached and last_downloaded:
                        usecache = last_cached > last_downloaded
                    else:
                        usecache = False
                else:
                    usecache = False
            if not usecache:
                renderer = ansicat.renderer_from_file(path,url=inpath,theme=theme)
                if renderer:
                    self.rendererdic[inpath] = renderer
                    self.renderer_time[inpath] = int(time.time())
            else:
                renderer = self.rendererdic[inpath]
        return renderer

    def get_temp_filename(self,url):
        if url in self.temp_files.keys():
            return self.temp_files[url]
        else:
            return None

    def opnk(self,inpath,mode=None,terminal=True,grep=None,theme=None,**kwargs):
        #Return True if inpath opened in Terminal
        # False otherwise
        # also returns the url in case it has been modified
        #if terminal = False, we don’t try to open in the terminal,
        #we immediately fallback to xdg-open.
        #netcache currently provide the path if it’s a file.
        if not offutils.is_local(inpath):
            kwargs["images_mode"] = mode
            cachepath,inpath = netcache.fetch(inpath,**kwargs)
            if not cachepath:
                return False, inpath
        # folowing line is for :// which are locals (file,list)
        elif "://" in inpath:
            cachepath,inpath = netcache.fetch(inpath,**kwargs)
        elif inpath.startswith("mailto:"):
            cachepath = inpath
        elif os.path.exists(inpath):
            cachepath = inpath
        else:
            print("%s does not exist"%inpath)
            return False, inpath
        renderer = self.get_renderer(inpath,mode=mode,theme=theme)
        if renderer and mode:
            renderer.set_mode(mode)
            self.last_mode[inpath] = mode
        if not mode and inpath in self.last_mode.keys():
            mode = self.last_mode[inpath]
            renderer.set_mode(mode)
        #we use the full moded url as key for the dictionary
        key = mode_url(inpath,mode)
        if terminal and renderer:
            #If this is an image and we have chafa/timg, we
            #don’t use less, we call it directly
            if renderer.has_direct_display():
                renderer.display(mode=mode,directdisplay=True)
                return True, inpath
            else:
                body = renderer.display(mode=mode)
                #Should we use the cache ? only if it is not local and there’s a cache
                usecache = key in self.temp_files and not is_local(inpath)
                if usecache:
                    #and the cache is still valid!
                    last_downloaded = netcache.cache_last_modified(inpath)
                    last_cached = os.path.getmtime(self.temp_files[key])
                    if last_downloaded > last_cached:
                        usecache = False
                        self.temp_files.pop(key)
                        self.less_histfile.pop(key)
                # We actually put the body in a tmpfile before giving it to less
                if not usecache:
                    tmpf = tempfile.NamedTemporaryFile("w", encoding="UTF-8", delete=False)
                    self.temp_files[key] = tmpf.name
                    tmpf.write(body)
                    tmpf.close()
                if key not in self.less_histfile:
                    firsttime = True
                    tmpf = tempfile.NamedTemporaryFile("w", encoding="UTF-8", delete=False)
                    self.less_histfile[key] = tmpf.name
                else:
                    #We don’t want to restore positions in lists
                    firsttime = is_local(inpath)
                less_cmd(self.temp_files[key], histfile=self.less_histfile[key],cat=firsttime,grep=grep)
                return True, inpath
        #maybe, we have no renderer. Or we want to skip it.
        else:
            mimetype = ansicat.get_mime(cachepath)
            if mimetype == "mailto":
                mail = inpath[7:]
                resp = input("Send an email to %s Y/N? " %mail)
                if resp.strip().lower() in ("y", "yes"):
                    if _HAS_XDGOPEN :
                        run("xdg-open mailto:%s", parameter=mail,direct_output=True)
                    else:
                         print("Cannot find a mail client to send mail to %s" %inpath)
                         print("Please install xdg-open (usually from xdg-util package)")
                return False, inpath
            else:
                cmd_str = self._get_handler_cmd(mimetype)
            try:
                run(cmd_str, parameter=netcache.get_cache_path(inpath), direct_output=True)
            except FileNotFoundError:
                print("Handler program %s not found!" % shlex.split(cmd_str)[0])
                print("You can use the ! command to specify another handler program or pipeline.")
            return False, inpath

    #We remove the renderers from the cache and we also delete temp files
    def cleanup(self):
        while len(self.temp_files) > 0:
            os.remove(self.temp_files.popitem()[1])
        while len(self.less_histfile) > 0:
            os.remove(self.less_histfile.popitem()[1])
        self.last_width = None
        self.rendererdic = {}
        self.renderer_time = {}
        self.last_mode = {}
        
def main():
    descri = "opnk is an universal open command tool that will try to display any file \
             in the pager less after rendering its content with ansicat. If that fails, \
             opnk will fallback to opening the file with xdg-open. If given an URL as input \
             instead of a path, opnk will rely on netcache to get the networked content."
    parser = argparse.ArgumentParser(prog="opnk",description=descri)
    parser.add_argument("--mode", metavar="MODE",
                        help="Which mode should be used to render: normal (default), full or source.\
                                With HTML, the normal mode try to extract the article.")
    parser.add_argument("content",metavar="INPUT", nargs="*", 
                         default=sys.stdin, help="Path to the file or URL to open")
    parser.add_argument("--cache-validity",type=int, default=0,
                        help="maximum age, in second, of the cached version before \
                                redownloading a new version")
    args = parser.parse_args()
    cache = opencache()
    for f in args.content:
        cache.opnk(f,mode=args.mode,validity=args.cache_validity)

if __name__ == "__main__":
    main()
