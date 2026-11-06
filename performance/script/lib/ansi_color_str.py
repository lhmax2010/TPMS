import os
import sys

code = {'reset': '0', 'bold': '1', 'faint': '2', 'italic': '3', 'underline': '4'}
ground = {'fore': '3', 'back': '4'}
color = {'black': '0', 'red': '1', 'green': '2', 'yellow': '3', 'blue': '4', 'magenta': '5', 'cyan': '6', 'white': '7'}


def coded(v):
    return '\033[' + v + 'm'

def coded_str(string, **kwargs):
    s = ""
    for k in code.keys():
        if k in kwargs and kwargs[k] == True:
            s += coded(code[k])

    for g in ground.keys():
        if g in kwargs:
            s += coded(ground[g] + color[kwargs[g]])

    return s + str(string) + coded(code['reset'])

