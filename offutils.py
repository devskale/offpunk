#!/bin/python

#This file contains some utilities common to offpunk, ansicat and netcache.
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
import netcache
import cert_migration

CACHE_VERSION = 1
CERT_VERSION = 1

#let’s find if grep supports --color=auto
try:
    test=subprocess.run(["grep","--color=auto","x"],input=b"x",check=True,\
                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    GREPCMD = "grep --color=auto"
except Exception as err:
    GREPCMD = "grep"

# We upgrade the cache only once at startup, hence the CACHE_UPGRADED variable
# This is only to avoid unnecessary checks each time the cache is accessed
CACHE_UPGRADED=False
def upgrade_cache(cache_folder):
    #Let’s read current version of the cache
    version_path = cache_folder + ".version"
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
        upgrade_func(cache_folder)
        with open(version_path,"w") as f:
            f.write(str(current_version))
            f.close()
    CACHE_UPGRADED=True

CERT_UPGRADED=False

def upgrade_cert(config_folder: str, data_folder: str) -> None:
    # read the current version
    certdata = os.path.join(data_folder, 'certs')
    if not os.path.exists(certdata):
        os.makedirs(certdata,exist_ok=True)
    version_path = os.path.join(certdata, ".version")
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
    else:
        current_version = 0
    #Now, let’s upgrade the certificate storage if needed
    while current_version < CERT_VERSION:
        current_version += 1
        upgrade_func = getattr(cert_migration,"upgrade_to_"+str(current_version))
        upgrade_func(data_folder, config_folder)
        with open(version_path,"w") as f:
            f.write(str(current_version))
            f.close()
    CERT_UPGRADED=True




#get xdg folder. Folder should be "cache", "data" or "config"
def xdg(folder="cache"):
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
    ## get _CACHE_PATH from OFFPUNK_CACHE_PATH environment variable
    #  if OFFPUNK_CACHE_PATH empty, set default to ~/.cache/offpunk
    cache_home = os.environ.get('XDG_CACHE_HOME') or\
                    os.path.join(_home,'.cache')
    _CACHE_PATH = os.environ.get('OFFPUNK_CACHE_PATH', \
        os.path.join(os.path.expanduser(cache_home),"offpunk/"))
    #Check that the cache path ends with "/"
    if not _CACHE_PATH.endswith("/"):
        _CACHE_PATH += "/"
    os.makedirs(_CACHE_PATH,exist_ok=True)
    if folder == "cache" and not CACHE_UPGRADED:
        upgrade_cache(_CACHE_PATH)
    if folder == "cache":
        return _CACHE_PATH
    elif folder == "config":
        return _CONFIG_DIR
    elif folder == "data":
        if not CERT_UPGRADED:
            upgrade_cert(_CONFIG_DIR, _DATA_DIR)
        return _DATA_DIR
    else:
        print("No XDG folder for %s. Check your code."%folder)
        return None



#An IPV6 URL should be put between []
#We try to detect them has location with more than 2 ":"
def fix_ipv6_url(url):
    if not url or url.startswith("mailto"):
        return url
    if "://" in url:
        schema, schemaless = url.split("://",maxsplit=1)
    else:
        schema, schemaless = None, url
    if "/" in schemaless:
        netloc, rest = schemaless.split("/",1)
        if netloc.count(":") > 2 and "[" not in netloc and "]" not in netloc:
            schemaless = "[" + netloc + "]" + "/" + rest
    elif schemaless.count(":") > 2 and "[" not in schemaless and "]" not in schemaless:
        schemaless = "[" + schemaless + "]/"
    if schema:
        return schema + "://" + schemaless
    return schemaless

# Cheap and cheerful URL detector
def looks_like_url(word):
    try:
        if not word.strip():
            return False
        url = fix_ipv6_url(word).strip()
        parsed = urllib.parse.urlparse(url)
        #sometimes, urllib crashed only when requesting the port
        port = parsed.port
        scheme = word.split("://")[0]
        mailto = word.startswith("mailto:")
        start = scheme in netcache.standard_ports
        local = scheme in ["file","list"]
        if mailto:
            return "@" in word
        elif not local:
            if start:
                #IPv4
                if "." in word or "localhost" in word:
                    return True
                #IPv6
                elif "[" in word and ":" in word and "]" in word:
                    return True
                else: return False
            else:   return False
            return start and ("." in word or "localhost" in word or ":" in word)
        else:
            return "/" in word
    except ValueError:
        return False

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
