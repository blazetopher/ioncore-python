#!/usr/bin/env python

"""
@file ion/integration/ais/validate_data_resource/parse_url_tester.py
@author Ian Katz
@brief Parse a url for its metadata and spit it to the command line
"""

import sys

import urllib


from ply.lex import lex
from ply.yacc import yacc

from data_resource_parser import Lexer, Parser, ParseException

def parseText(text):

    #prepare to parse!
    lexer = lex(module=Lexer())
    parser = yacc(module=Parser(), write_tables=0, debug=False)
        
    #crunch it!
    return parser.parse(text, lexer=lexer)


def parseUrl(das_resource_url):
    """
    @brief validate a data resource
    @retval big table
    """


    #fetch file
    fullurl = das_resource_url
    webfile = urllib.urlopen(fullurl)
    dasfile = webfile.read()
    webfile.close()

    return parseText(dasfile)


def validateUrl(data_resource_url):
    """
    @brief validate a data resource
    @retval helpful output
    """

    try:

        parsed_das = parseUrl(data_resource_url)


    #url doesn't exist
    except IOError:
        print "Couldn't fetch '%s'" % data_resource_url
        return {}
        
    #bad data
    except ParseException:
        print "Content of '%s' didn't parse" % data_resource_url
        return {}

    print "\n\nResults of parsing this URL:\n%s" % data_resource_url
    print "\n  Found these sections:"
    for k in parsed_das.keys():
        printSection(k, parsed_das[k], 1)

    print "\n"

    return parsed_das


def printSection(name, values, depth):
    d1 = "    " + (depth * "  ")
    d2 = "    " + ((depth + 1) * "  ")

    print  (d1 + name)
    
    for k, v in values.iteritems():
        if v.has_key("TYPE"):
            print d2 + "%s (%s): %s" % (k, v['TYPE'], str(v['VALUE']))
        else:
            printSection(k, v, depth + 1)
    print 
    

if __name__ == "__main__":
    validateUrl(sys.argv[1])
