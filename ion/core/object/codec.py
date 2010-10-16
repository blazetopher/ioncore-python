#!/usr/bin/env python

"""
@file ion/core/object/codec.py
@author David Stuebe
@brief Interceptor for encoding and decoding ION messages
"""

from twisted.internet import defer

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)

from ion.core import ioninit
from ion.core.intercept.interceptor import EnvelopeInterceptor
import ion.util.procutils as pu

from ion.core.object import gpb_wrapper
from net.ooici.play import addressbook_pb2
ION_R1_GPB = 'ION R1 GPB'


class ObjectCodecInterceptor(EnvelopeInterceptor):
    """
    Interceptor that assembles the headers in the ION message format.
    """
    def before(self, invocation):
        print 'Hello from BEFORE Davids Codec!'
        print 'args', invocation.args
        print 'path', invocation.path
        print 'message', invocation.message
        print 'content', invocation.content
        print 'status', invocation.status
        print 'route', invocation.route
        print 'note', invocation.note
        print 'workbench', invocation.workbench
        
        if ION_R1_GPB == invocation.content['encoding']:
            content = invocation.content['content']
            invocation.content['content'] = invocation.workbench.unpack_structure(content)
            invocation.content['content'].ParseFromString(content)
        
        
        return invocation

    def after(self, invocation):
        print 'Hello from AFTER Davids Codec!'
        print 'args', invocation.args
        print 'path', invocation.path
        print 'message', invocation.message
        print 'content', invocation.content
        print 'status', invocation.status
        print 'route', invocation.route
        print 'note', invocation.note
        print 'workbench', invocation.workbench

        content = invocation.message['content']
        if isinstance(content, gpb_wrapper.Wrapper):
            invocation.message['content'] = invocation.workbench.pack_structure(content)
                     
            invocation.message['encoding'] = ION_R1_GPB        
        
        return invocation
