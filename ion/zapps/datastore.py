#!/usr/bin/env python

"""
@file ion/zapps/datastore.py
@author Matt Rodriguez
@brief Datastore App -- application the runs the versioning service
"""

from twisted.internet import defer

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)

from ion.core import ioninit

from ion.core.process.process import ProcessDesc
from ion.core.pack import app_supervisor


@defer.inlineCallbacks
def start(container, starttype, app_definition, *args, **kwargs):


    # Get the username for cassandra from the command line. If not present get username from the kwargs for the app.
    uname = ioninit.cont_args.get('cassandra_username', kwargs.get('cassandra_username', None))
    pword = ioninit.cont_args.get('cassandra_password', kwargs.get('cassandra_password', None))

    do_init = ioninit.cont_args.get('do-init', kwargs.get('do-init', None))

    if pword is None:
        print_pword = None
    else:
        print_pword = '****'
    log.info('Starting DataStore Service Instance: username: %s, password: %s, do-init: %s' % (uname, print_pword, do_init))

    ION_PREDICATES_CFG = 'ion_predicates'
    ION_RESOURCE_TYPES_CFG = 'ion_resource_types'
    ION_DATASETS_CFG = 'ion_datasets'
    ION_IDENTITIES_CFG = 'ion_identities'
    ION_AIS_RESOURCES_CFG = 'ion_ais_resources'

    PRELOAD_CFG = 'preload'



    spawnargs = {}
    if uname is not None:
        spawnargs['username']=uname
    if pword is not None:
        spawnargs['password']=pword


    if do_init is not None:

        if isinstance(do_init, (str, unicode)):
            if do_init == 'False':
                do_init = False
            elif do_init == 'True':
                do_init = True
            else:
                raise Exception("Invalid input to datastore app: argument 'do-init' is True or False" )
        elif not isinstance(do_init, bool):
            raise Exception("Invalid input to datastore app: argument 'do-init' is True or False" )



        init ={PRELOAD_CFG:
               {ION_PREDICATES_CFG:do_init,
               ION_RESOURCE_TYPES_CFG:do_init,
               ION_IDENTITIES_CFG:do_init},
               }


        spawnargs.update(init)

    services =[{ 'name':'datastore',
                     'module':'ion.services.coi.datastore',
                     'class':'DataStoreService',
                     'spawnargs':spawnargs
                     },
               ]

    app_sup_desc = ProcessDesc(name="app-supervisor-" + app_definition.name,
                               module=app_supervisor.__name__,
                               spawnargs={'spawn-procs':services,})

    supid = yield app_sup_desc.spawn()

    res = (supid.full, [app_sup_desc])
    log.info("Started DataStoreService")
    
    defer.returnValue(res)

@defer.inlineCallbacks
def stop(container, state):
    log.info("Stopping DataStoreService")
    supdesc = state[0]
    yield supdesc.terminate()

