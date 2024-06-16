#!/usr/bin/env python3
import os
import sys
import urllib.parse
import argparse
import codecs
import getpass
import socket
import ssl
import glob
import datetime
import hashlib
from ssl import CertificateError
import ansicat
import offutils
from offutils import xdg
import time
try:
    import chardet
    _HAS_CHARDET = True
except ModuleNotFoundError:
    _HAS_CHARDET = False

try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    _HAS_CRYPTOGRAPHY = True
    _BACKEND = default_backend()
except(ModuleNotFoundError,ImportError):
    _HAS_CRYPTOGRAPHY = False
try:
    import requests
    _DO_HTTP = True
except (ModuleNotFoundError,ImportError):
    _DO_HTTP = False

# This list is also used as a list of supported protocols
standard_ports = {
        "gemini" : 1965,
        "gopher" : 70,
        "finger" : 79,
        "http"   : 80,
        "https"  : 443,
        "spartan": 300,
}
default_protocol = "gemini"

CRLF = '\r\n'
DEFAULT_TIMEOUT = 10
_MAX_REDIRECTS = 5

# monkey-patch Gemini support in urllib.parse
# see https://github.com/python/cpython/blob/master/Lib/urllib/parse.py
urllib.parse.uses_relative.append("gemini")
urllib.parse.uses_netloc.append("gemini")
urllib.parse.uses_relative.append("spartan")
urllib.parse.uses_netloc.append("spartan")


class UserAbortException(Exception):
    pass


def parse_mime(mime):
    options = {}
    if mime:
        if ";" in mime:
            splited = mime.split(";",maxsplit=1)
            mime = splited[0]
            if len(splited) >= 1:
                options_list = splited[1].split()
                for o in options_list:
                    spl = o.split("=",maxsplit=1)
                    if len(spl) > 0:
                        options[spl[0]] = spl[1]
    return mime, options

def normalize_url(url):
    if "://" not in url and ("./" not in url and url[0] != "/"):
        if not url.startswith("mailto:"):
            url = "gemini://" + url
    return url


def cache_last_modified(url):
    if not url:
        return None
    path = get_cache_path(url)
    if path and os.path.isfile(path):
        return os.path.getmtime(path)
    else:
        return None

def is_cache_valid(url,validity=0):
    # Validity is the acceptable time for
    # a cache to be valid  (in seconds)
    # If 0, then any cache is considered as valid
    # (use validity = 1 if you want to refresh everything)
    if offutils.is_local(url):
        return True
    cache = get_cache_path(url)
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

def get_cache_path(url,add_index=True):
    # Sometimes, cache_path became a folder! (which happens for index.html/index.gmi)
    # In that case, we need to reconstruct it
    # if add_index=False, we don’t add that "index.gmi" at the ends of the cache_path
    #First, we parse the URL
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    if url[0] == "/" or url.startswith("./") or os.path.exists(url):
        scheme = "file"
    elif parsed.scheme:
        scheme = parsed.scheme
    else:
        scheme = default_protocol
    if scheme in ["file","mailto","list"]:
        local = True
        host = ""
        port = None
        # file:// is 7 char
        if url.startswith("file://"):
            path = url[7:]
        elif scheme == "mailto":
            path = parsed.path
        elif url.startswith("list://"):
            listdir = os.path.join(xdg("data"),"lists")
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
        host = parsed.netloc #.encode("idna").decode()
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
            elif itemtype in ("9","g","I","s",";"):
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
    elif scheme and host:
        cache_path = os.path.expanduser(xdg("cache") + scheme + "/" + host + path)
        #There’s an OS limitation of 260 characters per path.
        #We will thus cut the path enough to add the index afterward
        cache_path = cache_path[:249]
        # this is a gross hack to give a name to
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
        if add_index and cache_path.endswith("/"):
            cache_path += index
        #sometimes, the index itself is a dir
        #like when folder/index.gmi?param has been created
        #and we try to access folder
        if add_index and os.path.isdir(cache_path):
            cache_path += "/" + index
    else:
        #URL is missing either a supported scheme or a valid host
        #print("Error: %s is not a supported url"%url)
        return None
    if len(cache_path) > 259:
        print("Path is too long. This is an OS limitation.\n\n")
        print(url)
        return None
    return cache_path

def write_body(url,body,mime=None):
    ## body is a copy of the raw gemtext
    ## Write_body() also create the cache !
    # DEFAULT GEMINI MIME
    mime, options = parse_mime(mime)
    cache_path = get_cache_path(url)
    if cache_path:
        if mime and mime.startswith("text/"):
            mode = "w"
        else:
            mode = "wb"
        cache_dir = os.path.dirname(cache_path)
        # If the subdirectory already exists as a file (not a folder)
        # We remove it (happens when accessing URL/subfolder before
        # URL/subfolder/file.gmi.
        # This causes loss of data in the cache
        # proper solution would be to save "sufolder" as "sufolder/index.gmi"
        # If the subdirectory doesn’t exist, we recursively try to find one
        # until it exists to avoid a file blocking the creation of folders
        root_dir = cache_dir
        while not os.path.exists(root_dir):
            root_dir = os.path.dirname(root_dir)
        if os.path.isfile(root_dir):
            os.remove(root_dir)
        os.makedirs(cache_dir,exist_ok=True)
        with open(cache_path, mode=mode) as f:
            f.write(body)
            f.close()
        return cache_path


def set_error(url,err):
# If we get an error, we want to keep an existing cache
# but we need to touch it or to create an empty one
# to avoid hitting the error at each refresh
    cache = get_cache_path(url)
    if is_cache_valid(url):
        os.utime(cache)
    elif cache:
        cache_dir = os.path.dirname(cache)
        root_dir = cache_dir
        while not os.path.exists(root_dir):
            root_dir = os.path.dirname(root_dir)
        if os.path.isfile(root_dir):
            os.remove(root_dir)
        os.makedirs(cache_dir,exist_ok=True)
        if os.path.isdir(cache_dir):
            with open(cache, "w") as c:
                c.write(str(datetime.datetime.now())+"\n")
                c.write("ERROR while caching %s\n\n" %url)
                c.write("*****\n\n")
                c.write(str(type(err)) + " = " + str(err))
                #cache.write("\n" + str(err.with_traceback(None)))
                c.write("\n*****\n\n")
                c.write("If you believe this error was temporary, type ""reload"".\n")
                c.write("The ressource will be tentatively fetched during next sync.\n")
                c.close()
    return cache

def _fetch_http(url,max_size=None,timeout=DEFAULT_TIMEOUT,accept_bad_ssl_certificates=False,**kwargs):
    if not _DO_HTTP: return None
    def too_large_error(url,length,max_size):
        err = "Size of %s is %s Mo\n"%(url,length)
        err += "Offpunk only download automatically content under %s Mo\n" %(max_size/1000000)
        err += "To retrieve this content anyway, type 'reload'."
        return set_error(url,err)
    if accept_bad_ssl_certificates:
        requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS = 'ALL:@SECLEVEL=1'
        requests.packages.urllib3.disable_warnings()
        verify=False
    else:
        requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS = 'ALL:@SECLEVEL=2'
        verify=True
    header = {}
    header["User-Agent"] = "Netcache"
    with requests.get(url,verify=verify,headers=header, stream=True,timeout=DEFAULT_TIMEOUT) as response:
        if "content-type" in response.headers:
            mime = response.headers['content-type']
        else:
            mime = None
        if "content-length" in response.headers:
            length = int(response.headers['content-length'])
        else:
            length = 0
        if max_size and length > max_size:
            response.close()
            return too_large_error(url,str(length/100),max_size)
        elif max_size and length == 0:
            body = b''
            downloaded = 0
            for r in response.iter_content():
                body += r
                #We divide max_size for streamed content
                #in order to catch them faster
                size = sys.getsizeof(body)
                max = max_size/2
                current = round(size*100/max,1)
                if current > downloaded:
                    downloaded = current
                    print("  -> Receiving stream: %s%% of allowed data"%downloaded,end='\r')
                #print("size: %s (%s\% of maxlenght)"%(size,size/max_size))
                if size > max_size/2:
                    response.close()
                    return too_large_error(url,"streaming",max_size)
            response.close()
        else:
            body = response.content
            response.close()
    if mime and "text/" in mime:
        body = body.decode("UTF-8","replace")
    cache = write_body(url,body,mime)
    return cache

def _fetch_gopher(url,timeout=DEFAULT_TIMEOUT,**kwargs):
    parsed =urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or 70
    if len(parsed.path) >= 2:
        itemtype = parsed.path[1]
        selector = parsed.path[2:]
    else:
        itemtype = "1"
        selector = ""
    addresses = socket.getaddrinfo(host, port, family=0,type=socket.SOCK_STREAM)
    s = socket.create_connection((host,port))
    for address in addresses:
        s = socket.socket(address[0], address[1])
        s.settimeout(timeout)
        try:
            s.connect(address[4])
            break
        except OSError as e:
            err = e
    if parsed.query:
        request = selector + "\t" + parsed.query
    else:
        request = selector
    request += "\r\n"
    s.sendall(request.encode("UTF-8"))
    response1 = s.makefile("rb")
    response = response1.read()
    # Transcode response into UTF-8
    #if itemtype in ("0","1","h"):
    if not itemtype in ("9","g","I","s",";"):
        # Try most common encodings
        for encoding in ("UTF-8", "ISO-8859-1"):
            try:
                response = response.decode("UTF-8")
                break
            except UnicodeDecodeError:
                pass
        else:
            # try to find encoding
            if _HAS_CHARDET:
                detected = chardet.detect(response)
                response = response.decode(detected["encoding"])
            else:
                raise UnicodeDecodeError
    if itemtype == "0":
        mime = "text/gemini"
    elif itemtype == "1":
        mime = "text/gopher"
    elif itemtype == "h":
        mime = "text/html"
    elif itemtype in ("9","g","I","s",";"):
        mime = None
    else:
        # by default, we should consider Gopher
        mime = "text/gopher"
    cache = write_body(url,response,mime)
    return cache

def _fetch_finger(url,timeout=DEFAULT_TIMEOUT,**kwargs):
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or standard_ports["finger"]
    query = parsed.path.lstrip("/") + "\r\n"
    with socket.create_connection((host,port)) as sock:
        sock.settimeout(timeout)
        sock.send(query.encode())
        response = sock.makefile("rb").read().decode("UTF-8")
        cache = write_body(response,"text/plain")
    return cache

# Originally copied from reference spartan client by Michael Lazar
def _fetch_spartan(url,**kwargs):
    cache = None
    url_parts = urllib.parse.urlparse(url)
    host = url_parts.hostname
    port = url_parts.port or standard_ports["spartan"]
    path = url_parts.path or "/"
    query = url_parts.query
    redirect_url = None
    with socket.create_connection((host,port)) as sock:
        if query:
            data = urllib.parse.unquote_to_bytes(query)
        else:
            data = b""
        encoded_host = host.encode("idna")
        ascii_path = urllib.parse.unquote_to_bytes(path)
        encoded_path = urllib.parse.quote_from_bytes(ascii_path).encode("ascii")
        sock.send(b"%s %s %d\r\n" % (encoded_host,encoded_path,len(data)))
        fp = sock.makefile("rb")
        response = fp.readline(4096).decode("ascii").strip("\r\n")
        parts = response.split(" ",maxsplit=1)
        code,meta = int(parts[0]),parts[1]
        if code == 2:
            body = fp.read()
            if meta.startswith("text"):
                body = body.decode("UTF-8")
            cache = write_body(url,body,meta)
        elif code == 3:
            redirect_url = url_parts._replace(path=meta).geturl()
        else:
            return set_error(url,"Spartan code %s: Error %s"%(code,meta))
    if redirect_url:
        cache = _fetch_spartan(redirect_url)
    return cache

def _validate_cert(address, host, cert,accept_bad_ssl=False,automatic_choice=None):
    """
    Validate a TLS certificate in TOFU mode.

    If the cryptography module is installed:
     - Check the certificate Common Name or SAN matches `host`
     - Check the certificate's not valid before date is in the past
     - Check the certificate's not valid after date is in the future

    Whether the cryptography module is installed or not, check the
    certificate's fingerprint against the TOFU database to see if we've
    previously encountered a different certificate for this IP address and
    hostname.
    """
    now = datetime.datetime.utcnow()
    if _HAS_CRYPTOGRAPHY:
        # Using the cryptography module we can get detailed access
        # to the properties of even self-signed certs, unlike in
        # the standard ssl library...
        c = x509.load_der_x509_certificate(cert, _BACKEND)
        # Check certificate validity dates
        if accept_bad_ssl:
            if c.not_valid_before >= now:
                raise CertificateError("Certificate not valid until: {}!".format(c.not_valid_before))
            elif c.not_valid_after <= now:
                raise CertificateError("Certificate expired as of: {})!".format(c.not_valid_after))

        # Check certificate hostnames
        names = []
        common_name = c.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
        if common_name:
            names.append(common_name[0].value)
        try:
            names.extend([alt.value for alt in c.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value])
        except x509.ExtensionNotFound:
            pass
        names = set(names)
        for name in names:
            try:
                ssl._dnsname_match(str(name), host)
                break
            except CertificateError:
                continue
        else:
            # If we didn't break out, none of the names were valid
            raise CertificateError("Hostname does not match certificate common name or any alternative names.")

    sha = hashlib.sha256()
    sha.update(cert)
    fingerprint = sha.hexdigest()

    # The directory of this host and IP-address, e.g.
    # ~/.local/share/offpunk/certs/srht.site/46.23.81.157/
    certdir = os.path.join(xdg("data"), "certs")
    hostdir = os.path.join(certdir, host)
    sitedir = os.path.join(hostdir, address)
    #1. We check through cached certificates do extract the 
    #most_frequent_cert  and to see if one is matching the current one.
    #2. If we have no match but one valid most_frequent_cert, we do the 
    #"throws warning" code.
    #3. If no certificate directory or no valid cached certificates, we do 
    #the "First-Use" routine.
    most_frequent_cert = None
    matching_fingerprint = False
    # 1. Have we been here before? (the directory exists)
    if os.path.isdir(sitedir):
        max_count = 0
        files = os.listdir(sitedir)
        count = 0
        certcache = os.path.join(xdg("config"), "cert_cache")

        for cached_fingerprint in files:
            filepath = os.path.join(sitedir, cached_fingerprint)
            certpath = os.path.join(certcache,cached_fingerprint+".crt")
            with open(filepath, 'r') as f:
                count = int(f.read())
            if os.path.exists(certpath):
                if count > max_count:
                    max_count = count
                    most_frequent_cert = cached_fingerprint
                if fingerprint == cached_fingerprint:
                    # Matched!
                    # Increase the counter for this certificate (this also updates
                    # the modification time of the file)
                    with open(filepath, 'w') as f:
                        f.write(str(count+1))
                    matching_fingerprint = True
                    break
    #2. Do we have some certificates but none of them is matching the current one?
    if most_frequent_cert and not matching_fingerprint:
        with open(os.path.join(certcache, most_frequent_cert+".crt"), "rb") as fp:
            previous_cert = fp.read()
        if _HAS_CRYPTOGRAPHY:
            # Load the most frequently seen certificate to see if it has
            # expired
            previous_cert = x509.load_der_x509_certificate(previous_cert, _BACKEND)
            previous_ttl = previous_cert.not_valid_after - now
            print(previous_ttl)

        print("****************************************")
        print("[SECURITY WARNING] Unrecognised certificate!")
        print("The certificate presented for {} ({}) has never been seen before.".format(host, address))
        print("This MIGHT be a Man-in-the-Middle attack.")
        print("A different certificate has previously been seen {} times.".format(max_count))
        if _HAS_CRYPTOGRAPHY:
            if previous_ttl < datetime.timedelta():
                print("That certificate has expired, which reduces suspicion somewhat.")
            else:
                print("That certificate is still valid for: {}".format(previous_ttl))
        print("****************************************")
        print("Attempt to verify the new certificate fingerprint out-of-band:")
        print(fingerprint)
        if automatic_choice:
            choice = automatic_choice
        else:
            choice = input("Accept this new certificate? Y/N ").strip().lower()
        if choice in ("y", "yes"):
            with open(os.path.join(sitedir, fingerprint), "w") as fp:
                fp.write("1")
            with open(os.path.join(certcache, fingerprint+".crt"), "wb") as fp:
                fp.write(cert)
        else:
            raise Exception("TOFU Failure!")

    #3. If no directory or no cert found in it, we cache it
    if not most_frequent_cert:
        if not os.path.exists(certdir): # XDG_DATA/offpunk/certs
            os.makedirs(certdir)
        if not os.path.exists(hostdir): # XDG_DATA/offpunk/certs/site.net
            os.makedirs(hostdir)
        if not os.path.exists(sitedir): # XDG_DATA/offpunk/certs/site.net/123.123.123.123
            os.makedirs(sitedir)

        with open(os.path.join(sitedir, fingerprint), "w") as fp:
            fp.write("1")
        certcache = os.path.join(xdg("config"), "cert_cache")
        if not os.path.exists(certcache):
            os.makedirs(certcache)
        with open(os.path.join(certcache, fingerprint+".crt"), "wb") as fp:
            fp.write(cert)

def _fetch_gemini(url,timeout=DEFAULT_TIMEOUT,interactive=True,accept_bad_ssl_certificates=False,\
                    **kwargs):
    cache = None
    newurl = url
    url_parts = urllib.parse.urlparse(url)
    host = url_parts.hostname
    port = url_parts.port or standard_ports["gemini"]
    path = url_parts.path or "/"
    query = url_parts.query
    # In AV-98, this was the _send_request method
    #Send a selector to a given host and port.
    #Returns the resolved address and binary file with the reply."""
    host = host.encode("idna").decode()
    # Do DNS resolution
    # DNS lookup - will get IPv4 and IPv6 records if IPv6 is enabled
    if ":" in host:
        # This is likely a literal IPv6 address, so we can *only* ask for
        # IPv6 addresses or getaddrinfo will complain
        family_mask = socket.AF_INET6
    elif socket.has_ipv6:
        # Accept either IPv4 or IPv6 addresses
        family_mask = 0
    else:
        # IPv4 only
        family_mask = socket.AF_INET
    addresses = socket.getaddrinfo(host, port, family=family_mask,
            type=socket.SOCK_STREAM)
    # Sort addresses so IPv6 ones come first
    addresses.sort(key=lambda add: add[0] == socket.AF_INET6, reverse=True)
    ## Continuation of send_request
    # Prepare TLS context
    protocol = ssl.PROTOCOL_TLS_CLIENT if sys.version_info.minor >=6 else ssl.PROTOCOL_TLSv1_2
    context = ssl.SSLContext(protocol)
    context.check_hostname=False
    context.verify_mode = ssl.CERT_NONE
    # Impose minimum TLS version
    ## In 3.7 and above, this is easy...
    if sys.version_info.minor >= 7:
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    ## Otherwise, it seems very hard...
    ## The below is less strict than it ought to be, but trying to disable
    ## TLS v1.1 here using ssl.OP_NO_TLSv1_1 produces unexpected failures
    ## with recent versions of OpenSSL.  What a mess...
    else:
        context.options |= ssl.OP_NO_SSLv3
        context.options |= ssl.OP_NO_SSLv2
    # Try to enforce sensible ciphers
    try:
        context.set_ciphers("AESGCM+ECDHE:AESGCM+DHE:CHACHA20+ECDHE:CHACHA20+DHE:!DSS:!SHA1:!MD5:@STRENGTH")
    except ssl.SSLError:
        # Rely on the server to only support sensible things, I guess...
        pass
        # Connect to remote host by any address possible
    err = None
    for address in addresses:
        try:
            s = socket.socket(address[0], address[1])
            s.settimeout(timeout)
            s = context.wrap_socket(s, server_hostname = host)
            s.connect(address[4])
            break
        except OSError as e:
            err = e
    else:
        # If we couldn't connect to *any* of the addresses, just
        # bubble up the exception from the last attempt and deny
        # knowledge of earlier failures.
        raise err

    # Do TOFU
    cert = s.getpeercert(binary_form=True)
    # Remember that we showed the current cert to this domain...
    #TODO : accept badssl and automatic choice
    _validate_cert(address[4][0], host, cert,automatic_choice="y")
    # Send request and wrap response in a file descriptor
    url = urllib.parse.urlparse(url)
    new_netloc = host
    #Handle IPV6 hostname
    if ":" in new_netloc:
        new_netloc = "[" + new_netloc + "]"
    if port != standard_ports["gemini"]:
        new_netloc += ":" + str(port)
    url = urllib.parse.urlunparse(url._replace(netloc=new_netloc))
    s.sendall((url + CRLF).encode("UTF-8"))
    f= s.makefile(mode = "rb")
    ## end of send_request in AV98
    # Spec dictates <META> should not exceed 1024 bytes,
    # so maximum valid header length is 1027 bytes.
    header = f.readline(1027)
    header = urllib.parse.unquote(header.decode("UTF-8"))
    if not header or header[-1] != '\n':
        raise RuntimeError("Received invalid header from server!")
    header = header.strip()
    # Validate header
    status, meta = header.split(maxsplit=1)
    if len(meta) > 1024 or len(status) != 2 or not status.isnumeric():
        f.close()
        raise RuntimeError("Received invalid header from server!")
    # Update redirect loop/maze escaping state
    if not status.startswith("3"):
        previous_redirectors = set()
    #TODO FIXME
    else:
        #we set a previous_redirectors anyway because refactoring in progress
        previous_redirectors = set()
    # Handle non-SUCCESS headers, which don't have a response body
    # Inputs
    if status.startswith("1"):
        if interactive:
            print(meta)
            if status == "11":
                user_input = getpass.getpass("> ")
            else:
                #TODO:FIXME we should not ask for user input while non-interactive
                user_input = input("> ")
            newurl = url.split("?")[0]
            return _fetch_gemini(newurl+"?"+user_input)
        else:
            return None,None
    # Redirects
    elif status.startswith("3"):
        newurl = urllib.parse.urljoin(url,meta)
        if newurl == url:
            raise RuntimeError("URL redirects to itself!")
        elif newurl in previous_redirectors:
            raise RuntimeError("Caught in redirect loop!")
        elif len(previous_redirectors) == _MAX_REDIRECTS:
            raise RuntimeError("Refusing to follow more than %d consecutive redirects!" % _MAX_REDIRECTS)
# TODO: redirections handling should be refactored
#        elif "interactive" in options and not options["interactive"]:
#            follow = self.automatic_choice
#        # Never follow cross-domain redirects without asking
#        elif new_gi.host.encode("idna") != gi.host.encode("idna"):
#            follow = input("Follow cross-domain redirect to %s? (y/n) " % new_gi.url)
#        # Never follow cross-protocol redirects without asking
#        elif new_gi.scheme != gi.scheme:
#            follow = input("Follow cross-protocol redirect to %s? (y/n) " % new_gi.url)
#        # Don't follow *any* redirect without asking if auto-follow is off
#        elif not self.options["auto_follow_redirects"]:
#            follow = input("Follow redirect to %s? (y/n) " % new_gi.url)
#        # Otherwise, follow away
        else:
            follow = "yes"
        if follow.strip().lower() not in ("y", "yes"):
            raise UserAbortException()
        previous_redirectors.add(url)
#        if status == "31":
#            # Permanent redirect
#            self.permanent_redirects[gi.url] = new_gi.url
        return _fetch_gemini(newurl)
    # Errors
    elif status.startswith("4") or status.startswith("5"):
        raise RuntimeError(meta)
    # Client cert
    elif status.startswith("6"):
        error = "Handling certificates for status 6X are not supported by offpunk\n"
        error += "See bug #31 for discussion about the problem"
        raise RuntimeError(error)
    # Invalid status
    elif not status.startswith("2"):
        raise RuntimeError("Server returned undefined status code %s!" % status)
    # If we're here, this must be a success and there's a response body
    assert status.startswith("2")
    mime = meta
    # Read the response body over the network
    fbody = f.read()
    # DEFAULT GEMINI MIME
    if mime == "":
        mime = "text/gemini; charset=utf-8"
    shortmime, mime_options = parse_mime(mime)
    if "charset" in mime_options:
        try:
            codecs.lookup(mime_options["charset"])
        except LookupError:
            #raise RuntimeError("Header declared unknown encoding %s" % mime_options)
            #If the encoding is wrong, there’s a high probably it’s UTF-8 with a bad header
            mime_options["charset"] = "UTF-8"
    if shortmime.startswith("text/"):
        #Get the charset and default to UTF-8 in none
        encoding = mime_options.get("charset", "UTF-8")
        try:
            body = fbody.decode(encoding)
        except UnicodeError:
            raise RuntimeError("Could not decode response body using %s\
                                encoding declared in header!" % encoding)
    else:
        body = fbody
    cache = write_body(url,body,mime)
    return cache,newurl


def fetch(url,offline=False,download_image_first=True,images_mode="readable",validity=0,**kwargs):
    url = normalize_url(url)
    newurl = url
    path=None
    print_error = "print_error" in kwargs.keys() and kwargs["print_error"]
    #Firt, we look if we have a valid cache, even if offline
    #If we are offline, any cache is better than nothing
    if is_cache_valid(url,validity=validity) or (offline and is_cache_valid(url,validity=0)):
        path = get_cache_path(url)
        #if the cache is a folder, we should add a "/" at the end of the URL
        if not url.endswith("/") and os.path.isdir(get_cache_path(url,add_index=False)) :
            newurl = url+"/"
    elif offline and is_cache_valid(url,validity=0):
        path = get_cache_path(url)
    elif "://" in url and not offline:
        try:
            scheme = url.split("://")[0]
            if scheme not in standard_ports:
                if print_error:
                    print("%s is not a supported protocol"%scheme)
                path = None
            elif scheme in ("http","https"):
                if _DO_HTTP:
                    path=_fetch_http(url,**kwargs)
                else:
                    print("HTTP requires python-requests")
            elif scheme == "gopher":
                path=_fetch_gopher(url,**kwargs)
            elif scheme == "finger":
                path=_fetch_finger(url,**kwargs)
            elif scheme == "gemini":
                path,newurl=_fetch_gemini(url,**kwargs)
            elif scheme == "spartan":
                path,newurl=_fetch_spartan(url,**kwargs)
            else:
                print("scheme %s not implemented yet"%scheme)
        except UserAbortException:
            return None, newurl
        except Exception as err:
            cache = set_error(url, err)
            # Print an error message
            # we fail silently when sync_only
            if isinstance(err, socket.gaierror):
                if print_error:
                    print("ERROR: DNS error!")
            elif isinstance(err, ConnectionRefusedError):
                if print_error:
                    print("ERROR1: Connection refused!")
            elif isinstance(err, ConnectionResetError):
                if print_error:
                    print("ERROR2: Connection reset!")
            elif isinstance(err, (TimeoutError, socket.timeout)):
                if print_error:
                    print("""ERROR3: Connection timed out!
    Slow internet connection?  Use 'set timeout' to be more patient.""")
            elif isinstance(err, FileExistsError):
                if print_error:
                    print("""ERROR5: Trying to create a directory which already exists
                        in the cache : """)
                print(err)
            elif _DO_HTTP and isinstance(err,requests.exceptions.SSLError):
                if print_error:
                    print("""ERROR6: Bad SSL certificate:\n""")
                    print(err)
                    print("""\n If you know what you are doing, you can try to accept bad certificates with the following command:\n""")
                    print("""set accept_bad_ssl_certificates True""")
            elif _DO_HTTP and isinstance(err,requests.exceptions.ConnectionError):
                if print_error:
                    print("""ERROR7: Cannot connect to URL:\n""")
                    print(str(err))
            else:
                if print_error:
                    import traceback
                    print("ERROR4: " + str(type(err)) + " : " + str(err))
                    #print("\n" + str(err.with_traceback(None)))
                    print(traceback.format_exc())
            return cache, newurl
        # We download images contained in the document (from full mode)
        if not offline and download_image_first and images_mode:
            renderer = ansicat.renderer_from_file(path,newurl)
            if renderer:
                for image in renderer.get_images(mode=images_mode):
                    #Image should exist, should be an url (not a data image)
                    #and should not be already cached
                    if image and not image.startswith("data:image/") and not is_cache_valid(image):
                        width = offutils.term_width() - 1
                        toprint = "Downloading %s" %image
                        toprint = toprint[:width]
                        toprint += " "*(width-len(toprint))
                        print(toprint,end="\r")
                        #d_i_f and images_mode are False/None to avoid recursive downloading 
                        #if that ever happen
                        fetch(image,offline=offline,download_image_first=False,\
                                images_mode=None,validity=0,**kwargs)
    return path, newurl


def main():
    
    descri="Netcache is a command-line tool to retrieve, cache and access networked content.\n\
            By default, netcache will returns a cached version of a given URL, downloading it \
            only if not existing. A validity duration, in seconds, can also be given so that \
            netcache downloads the content only if the existing cache is older than the validity."
    # Parse arguments
    parser = argparse.ArgumentParser(prog="netcache",description=descri)
    parser.add_argument("--path", action="store_true",
                        help="return path to the cache instead of the content of the cache")
    parser.add_argument("--offline", action="store_true",
                        help="Do not attempt to download, return cached version or error")
    parser.add_argument("--max-size", type=int,
                        help="Cancel download of items above that size (value in Mb).")
    parser.add_argument("--timeout", type=int,
                        help="Time to wait before cancelling connection (in second).")
    parser.add_argument("--cache-validity",type=int, default=0,
                        help="maximum age, in second, of the cached version before \
                                redownloading a new version")
    # No argument: write help
    parser.add_argument('url', metavar='URL', nargs='*',
                        help='download URL and returns the content or the path to a cached version')
    # --validity : returns the date of the cached version, Null if no version
    # --force-download : download and replace cache, even if valid
    args = parser.parse_args()

    param = {}
    
    for u in args.url:
        if args.offline:
            path = get_cache_path(u)
        else:
            path,url = fetch(u,max_size=args.max_size,timeout=args.timeout,\
                                validity=args.cache_validity)
        if args.path:
            print(path)
        else:
            with open(path,"r") as f:
                print(f.read())
                f.close()

        
if __name__== '__main__':
    main()
