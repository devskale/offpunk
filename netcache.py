#!/bin/python
import os
import urllib

_home = os.path.expanduser('~')
cache_home = os.environ.get('XDG_CACHE_HOME') or\
                os.path.join(_home,'.cache')
_CACHE_PATH = os.path.join(cache_home,"offpunk/")

if not os.path.exists(_CACHE_PATH):
    print("Creating cache directory {}".format(_CACHE_PATH))
    os.makedirs(_CACHE_PATH)


#def get(url,max_size_download=None,timeout=None):

def cache_last_modified(url):
    path = get_cache_path(url)
    if path:
        return os.path.getmtime(path)
    elif self.local:
        return 0
    else:
        print("ERROR : NO CACHE in cache_last_modified")
        return None

def is_cache_valid(url,validity=0):
    # Validity is the acceptable time for
    # a cache to be valid  (in seconds)
    # If 0, then any cache is considered as valid
    # (use validity = 1 if you want to refresh everything)
    cache = get_cache_path(url)
    # TODO FIXME : detect if we are local
    #if self.local:
    #    return os.path.exists(cache)
    if cache :
        # If path is too long, we always return True to avoid
        # fetching it.
        if len(cache) > 259:
            print("We return False because path is too long")
            return False
        if os.path.exists(cache) and not os.path.isdir(cache):
            if validity > 0 :
                last_modification = cache_last_modified(url)
                now = time.time()
                age = now - last_modification
                return age < validity
            else:
                return True
        else:
            #Cache has not been build
            return False
    else:
        #There’s not even a cache!
        return False



def get_cache_path(url):
    #First, we parse the URL
    parsed = urllib.parse.urlparse(url)
    if url[0] == "/" or url.startswith("./"):
        scheme = "file"
    else:
        scheme = parsed.scheme
    if scheme in ["file","mailto","list"]:
        local = True
        host = ""
        port = None
        # file:// is 7 char
        if url.startswith("file://"):
            path = self.url[7:]
        elif scheme == "mailto":
            path = parsed.path
        elif url.startswith("list://"):
            listdir = os.path.join(_DATA_DIR,"lists")
            listname = url[7:].lstrip("/")
            if listname in [""]:
                name = "My Lists"
                path = listdir
            else:
                name = listname
                path = os.path.join(listdir, "%s.gmi"%listname)
        else:
            path = url
    else:
        local = False
        # Convert unicode hostname to punycode using idna RFC3490
        host = parsed.hostname #.encode("idna").decode()
        port = parsed.port or standard_ports.get(scheme, 0)
        # special gopher selector case
        if scheme == "gopher":
            if len(parsed.path) >= 2:
                itemtype = parsed.path[1]
                path = parsed.path[2:]
            else:
                itemtype = "1"
                path = ""
            if itemtype == "0":
                mime = "text/gemini"
            elif itemtype == "1":
                mime = "text/gopher"
            elif itemtype == "h":
                mime = "text/html"
            elif itemtype in ("9","g","I","s"):
                mime = "binary"
            else:
                mime = "text/gopher"
        else:
            path = parsed.path
        if parsed.query:
            # we don’t add the query if path is too long because path above 260 char
            # are not supported and crash python.
            # Also, very long query are usually useless stuff
            if len(path+parsed.query) < 258:
                path += "/" + parsed.query

    # Now, we have a partial path. Let’s make it full path.
    if local:
        cache_path = path
    else:
        cache_path = os.path.expanduser(_CACHE_PATH + scheme + "/" + host + path)
        #There’s an OS limitation of 260 characters per path.
        #We will thus cut the path enough to add the index afterward
        cache_path = cache_path[:249]
        # FIXME : this is a gross hack to give a name to
        # index files. This will break if the index is not
        # index.gmi. I don’t know how to know the real name
        # of the file. But first, we need to ensure that the domain name
        # finish by "/". Else, the cache will create a file, not a folder.
        if scheme.startswith("http"):
            index = "index.html"
        elif scheme == "finger":
            index = "index.txt"
        elif scheme == "gopher":
            index = "gophermap"
        else:
            index = "index.gmi"
        if path == "" or os.path.isdir(cache_path):
            if not cache_path.endswith("/"):
                cache_path += "/"
            if not url.endswith("/"):
                url += "/"
        if cache_path.endswith("/"):
            cache_path += index
        #sometimes, the index itself is a dir
        #like when folder/index.gmi?param has been created
        #and we try to access folder
        if os.path.isdir(cache_path):
            cache_path += "/" + index
    return cache_path
