#!/usr/bin/env python

"""
@author Dorian Raymer
@author Michael Meisinger
@brief Capability Container main class
@see http://www.oceanobservatories.org/spaces/display/syseng/CIAD+COI+SV+Python+Capability+Container

A container utilizes the messaging abstractions for AMQP.

"""

import os
import string
import sys

from twisted.internet import defer
from twisted.python import failure
from zope.interface import implements, Interface

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)

from ion.core import ioninit
from ion.core.cc.container_api import IContainer
from ion.core.id import Id
from ion.core.intercept.interceptor_system import InterceptorSystem
from ion.core.messaging.exchange import ExchangeManager
from ion.core.pack.application import AppLoader
from ion.core.pack.app_manager import AppManager
from ion.core.process.proc_manager import ProcessManager
from ion.util.state_object import BasicLifecycleObject
from ion.util.config import Config

CONF = ioninit.config(__name__)
CF_is_config = Config(CONF.getValue('interceptor_system')).getObject()

class Container(BasicLifecycleObject):
    """
    Represents an instance of the Capability Container. Typically, in one Twisted
    process (= one UNIX process), there is only one instance of a CC. In test cases,
    however, there might be more.
    """
    implements(IContainer)

    # Static variables
    # Generate unique container id (and process id prefix). Avoid . chars.
    id = '%s.%d' % (os.uname()[1], os.getpid())
    id = string.replace(id, ".", "_")

    args = None  # Startup arguments
    _started = False

    def __init__(self):
        BasicLifecycleObject.__init__(self)

        self._fatal_error_encountered = False

        # Config instance
        self.config = None

        # ExchangeManager instance
        self.exchange_manager = None

        # ProcessManager instance
        self.proc_manager = None

        # AppManager instance
        self.app_manager = None

        # InterceptorSystem
        self.interceptor_system = None

    @defer.inlineCallbacks
    def on_initialize(self, config, *args, **kwargs):
        """
        Initializes the instance of a container. Actions include
        - Receive and parse the configuration
        - Prepare some active objects
        """
        self.config = config

        # Set additional container args
        Container.args = self.config.get('args', None)

        self.exchange_manager = ExchangeManager(self)
        yield self.exchange_manager.initialize(config, *args, **kwargs)

        self.proc_manager = ProcessManager(self)
        yield self.proc_manager.initialize(config, *args, **kwargs)

        self.app_manager = AppManager(self)
        yield self.app_manager.initialize(config, *args, **kwargs)

        self.interceptor_system = InterceptorSystem()
        yield self.interceptor_system.initialize(CF_is_config)

    @defer.inlineCallbacks
    def on_activate(self, *args, **kwargs):
        """
        Activates the container. Actions include
        - Initiate broker connection
        - Start
        @retval Deferred
        """
        Container._started = True

        yield self.interceptor_system.activate()

        yield self.exchange_manager.activate()

        yield self.proc_manager.activate()

        yield self.app_manager.activate()

        # now that we've activated, can publish ContainerLifecycleEvents as we need the exchange_manager in place.
        # this is the first chance we have to construct this publisher though.

        # have to import here or we get cyclical problems
        from ion.services.dm.distribution.events import ContainerLifecycleEventPublisher
        from ion.core.process.process import Process

        p = Process(spawnargs={'proc-name': 'ContainerLCEPubProc'})
        yield p.spawn()

        self._lc_pub = ContainerLifecycleEventPublisher(origin=self.id, process=p)
        yield self._lc_pub.initialize()
        yield self._lc_pub.activate()

        # now publish the event
        yield self._lc_pub.create_and_publish_event(state=ContainerLifecycleEventPublisher.State.ACTIVE)

    def on_deactivate(self, *args, **kwargs):
        raise NotImplementedError("Not implemented")

    @defer.inlineCallbacks
    def on_terminate(self, *args, **kwargs):
        """
        Deactivates and terminates the container. Actions include
        - Stop and terminate all container applications
        - Close broker connection
        @retval Deferred
        """

        # technically this is not correct as we're still not quite TERMINATED, but for all intents and purposes..
        # we have to publish before we tear down the messaging framework
        yield self._lc_pub.create_and_publish_event(state=self._lc_pub.State.TERMINATED)
        yield self._lc_pub.terminate()
        yield self._lc_pub._process.terminate()

        yield self.app_manager.terminate()

        yield self.proc_manager.terminate()

        yield self.interceptor_system.terminate()

        yield self.exchange_manager.terminate()

        log.info("Container closed")
        Container._started = False

    def on_error(self, *args, **kwargs):
        """An error here is always fatal.
        """
        #raise RuntimeError("Illegal state change for container")
        self.fatalError()

    # --- Container API -----------

    # Process management, handled by ProcessManager
    def spawn_process(self, *args, **kwargs):
        return self.proc_manager.spawn_process(*args, **kwargs)
    def spawn_processes(self, *args, **kwargs):
        return self.proc_manager.spawn_processes(*args, **kwargs)
    def create_supervisor(self, *args, **kwargs):
        return self.proc_manager.create_supervisor(*args, **kwargs)
    def activate_process(self, *args, **kwargs):
        return self.proc_manager.activate_process(*args, **kwargs)
    def terminate_process(self, *args, **kwargs):
        return self.proc_manager.terminate_process(*args, **kwargs)

    # Exchange management, handled by ExchangeManager
    def configure_messaging(self, *args, **kwargs):
        return self.exchange_manager.configure_messaging(*args, **kwargs)
    def new_consumer(self, *args, **kwargs):
        return self.exchange_manager.new_consumer(*args, **kwargs)
    def send(self, *args, **kwargs):
        return self.exchange_manager.send(*args, **kwargs)

    # App management, handled by AppManager
    def start_app(self, *args, **kwargs):
        return self.app_manager.start_app(*args, **kwargs)
    # Release management, handled by AppManager
    def start_rel(self, *args, **kwargs):
        return self.app_manager.start_rel(*args, **kwargs)

    # Container Events

    def fatalError(self, ex=None):
        """
        Container event that componenets/processes can raise when something
        goes really wrong.
        The result of the fatalError can cause the whole container to
        shutdown by calling reactor.stop
        reactor.stop will call stopService on CapabilityContainer Service
        which, in turn, will terminate this container lifecycleobject,
        which then terminates its lifecycle objects.
        """
        log.warning('fatalError event')
        log.warning(str(ex))
        f = failure.Failure()
        log.warning(str(f.getTraceback()))
        f.printDetailedTraceback()
        log.info("The container suffered a fatal error event and is crashing.")
        log.info("The last traceback, in full detail, was written to stdout.")
        if not self._fatal_error_encountered:
            self._fatal_error_encountered = True
            from twisted.internet import reactor
            reactor.stop()


    def exchangeConnectionLost(self, reason):
        """
        The exchange manager notifies the container when the amqp
        connection closes by triggering this event.
        The connection closure could be expected (if the exchange manager
        is terminated) or unexpected, indicating an error situation.
        """
        log.info('exchangeConnectionLost %s' % (str(reason),))
        self.fatalError(reason)

    def __str__(self):
        return "CapabilityContainer(state=%s,%r)" % (
            self._get_state(),
            self.exchange_manager.message_space)

def create_new_container():
    """
    Factory for a container.
    This also makes sure that only one container is active at any time,
    currently.
    """
    if Container._started:
        raise RuntimeError('Already started')

    c = Container()
    ioninit.container_instance = c

    return c

Id.default_container_id = Container.id
