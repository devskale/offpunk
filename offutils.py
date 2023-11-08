#!/bin/python

#This file contains some utilities common to offpunk, ansirenderer and netcache.
#Currently, there are the following utilities:
#
# run : run a shell command and get the results with some security
# term_width : get or set the width to display on the terminal

import os
import io
import subprocess
import shutil
import shlex
import urllib.parse
import urllib.parse
import netcache_migration

CACHE_VERSION = 1

## Config directories
## We implement our own python-xdg to avoid conflict with existing libraries.
_home = os.path.expanduser('~')
data_home = os.environ.get('XDG_DATA_HOME') or \
            os.path.join(_home,'.local','share')
config_home = os.environ.get('XDG_CONFIG_HOME') or \
                os.path.join(_home,'.config')
_CONFIG_DIR = os.path.join(os.path.expanduser(config_home),"offpunk/")
_DATA_DIR = os.path.join(os.path.expanduser(data_home),"offpunk/")
_old_config = os.path.expanduser("~/.offpunk/")
## Look for pre-existing config directory, if any
if os.path.exists(_old_config):
    _CONFIG_DIR = _old_config
#if no XDG .local/share and not XDG .config, we use the old config
if not os.path.exists(data_home) and os.path.exists(_old_config):
    _DATA_DIR = _CONFIG_DIR
cache_home = os.environ.get('XDG_CACHE_HOME') or\
                os.path.join(_home,'.cache')
_CACHE_PATH = os.path.join(os.path.expanduser(cache_home),"offpunk/")
os.makedirs(_CACHE_PATH,exist_ok=True)

#Let’s read current version of the cache
version_path = _CACHE_PATH + ".version"
current_version = 0
if os.path.exists(version_path):
    current_str = None
    with open(version_path) as f:
        current_str = f.read()
        f.close()
    try:
        current_version = int(current_str)
    except:
        current_version = 0

#Now, let’s upgrade the cache if needed
while current_version < CACHE_VERSION:
    current_version += 1
    upgrade_func = getattr(netcache_migration,"upgrade_to_"+str(current_version))
    upgrade_func(_CACHE_PATH)
    with open(version_path,"w") as f:
        f.write(str(current_version))
        f.close()



## Those two functions add/remove the mode to the
# URLs. This is a gross hack to remember the mode
def mode_url(url,mode):
    if mode and mode!= "readable" and "##offpunk=" not in url:
        url += "##offpunk_mode=" + mode
    return url

def unmode_url(url):
    mode = None
    splitted = url.split("##offpunk_mode=")
    if len(splitted) > 1:
        url = splitted[0]
        mode = splitted[1]
    return [url,mode]

# In terms of arguments, this can take an input file/string to be passed to
# stdin, a parameter to do (well-escaped) "%" replacement on the command, a
# flag requesting that the output go directly to the stdout, and a list of
# additional environment variables to set.
def run(cmd, *, input=None, parameter=None, direct_output=False, env={}):
    if parameter:
        cmd = cmd % shlex.quote(parameter)
    e = os.environ
    e.update(env)
    if isinstance(input, io.IOBase):
        stdin = input
        input = None
    else:
        if input:
            input = input.encode()
        stdin = None
    if not direct_output:
        # subprocess.check_output() wouldn't allow us to pass stdin.
        result = subprocess.run(cmd, check=True, env=e, input=input,
                                shell=True, stdin=stdin, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        return result.stdout.decode()
    else:
        subprocess.run(cmd, env=e, input=input, shell=True, stdin=stdin)


global TERM_WIDTH
TERM_WIDTH = 72

#if absolute, returns the real terminal width, not the text width
def term_width(new_width=None,absolute=False):
    if new_width:
        global TERM_WIDTH
        TERM_WIDTH = new_width
    cur = shutil.get_terminal_size()[0]
    if absolute:
        return cur
    width = TERM_WIDTH
    if cur < width:
        width = cur
    return width

def is_local(url):
    if not url: return True
    elif "://" in url:
        scheme,path = url.split("://",maxsplit=1)
        return scheme in ["file","mail","list","mailto"]
    else:
        return True


# This method return the image URL or invent it if it’s a base64 inline image
# It returns [url,image_data] where image_data is None for normal image
def looks_like_base64(src,baseurl):
    imgdata = None
    imgname = src
    if src and src.startswith("data:image/"):
        if ";base64," in src:
            splitted = src.split(";base64,")
            #splitted[0] is something like data:image/jpg
            if "/" in splitted[0]:
                extension = splitted[0].split("/")[1]
            else:
                extension = "data"
            imgdata = splitted[1]
            imgname = imgdata[:20] + "." + extension
            imgurl = urllib.parse.urljoin(baseurl, imgname)
        else:
            #We can’t handle other data:image such as svg for now
            imgurl = None
    else:
        imgurl = urllib.parse.urljoin(baseurl, imgname)
    return imgurl,imgdata
