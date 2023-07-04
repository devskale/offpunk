#!/bin/python
import os

cache_home = os.environ.get('XDG_CACHE_HOME') or\
                os.path.join(_home,'.cache')
_CACHE_PATH = os.path.join(cache_home,"offpunk/")

if not os.path.exists(_CACHE_PATH):
    print("Creating cache directory {}".format(_CACHE_PATH))
    os.makedirs(_CACHE_PATH)


def get_cache_path(url):

def is_cache_valid(url,validity=0):


