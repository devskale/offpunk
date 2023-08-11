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
TERM_WIDTH = 80

def term_width(new_width=None):
    if new_width:
        global TERM_WIDTH
        TERM_WIDTH = new_width
    width = TERM_WIDTH
    cur = shutil.get_terminal_size()[0]
    if cur < width:
        width = cur
    return width

def is_local(url):
    if "://" in url:
        scheme,path = url.split("://",maxsplit=1)
        return scheme in ["file","mail","list","mailto"]
    else:
        return True

