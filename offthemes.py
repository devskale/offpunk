#!/bin/python
colors = {
                "bold"   : ["1","22"],
                "faint"  : ["2","22"],
                "italic" : ["3","23"],
                "underline": ["4","24"],
                "black"   : ["30","39"],
                "red"    : ["31","39"],
                "green"    : ["32","39"],
                "yellow" : ["33","39"],
                "blue"   : ["34","39"],
                "purple"   : ["35","39"],
                "cyan"   : ["36","39"],
                "white"   : ["37","39"],
                "background_black"   : ["40","49"],
                "background_red"    : ["41","49"],
                "background_green"    : ["42","49"],
                "background_yellow" : ["43","49"],
                "background_blue"   : ["44","49"],
                "background_purple"   : ["45","49"],
                "background_cyan"   : ["46","49"],
                "background_white"   : ["47","49"],
                "bright_black"   : ["90","39"],
                "bright_red"    : ["91","39"],
                "bright_green"    : ["92","39"],
                "bright_yellow" : ["93","39"],
                "bright_blue"   : ["94","39"],
                "bright_purple"   : ["95","39"],
                "bright_cyan"   : ["96","39"],
                "bright_white"   : ["97","39"],
           }

offpunk1 = {
                "window_title" :    ["red","bold"],
                "window_subtitle" : ["red","faint"],
                "title" :           ["blue","bold","underline"],
                "subtitle" :        ["blue"],
                "subsubtitle" :     ["blue","faint"], #fallback to subtitle if none
                "link"  :           ["blue","faint"],
                "new_link":         ["bold"],
                "oneline_link":     [],     #for gopher/gemini. fallback to link if none
                "image_link" :      ["yellow","faint"],
                "preformatted":     ["faint"],
                "blockquote" :      ["italic"],
                "prompt_on" :       ["green"],
                "prompt_off" :      ["green"],
             }  

default = offpunk1
