#!/usr/bin/env python3
import ast
import sys
f = open('../offpunk.py', "r") #filename input
module = ast.parse(f.read())

class_definitions = [node for node in module.body if isinstance(node, ast.ClassDef)]
for class_def in class_definitions:
        function_definitions = [node for node in class_def.body if isinstance(node, ast.FunctionDef)]
        for f in function_definitions:
            if f.name.startswith('do_'):
                docstring = ast.get_docstring(f)
                if docstring is not None:
                    print('_(\n"""'+docstring+'\"""\n)')

