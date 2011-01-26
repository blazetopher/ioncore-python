#!/usr/bin/env python


"""
@file ion/services/dm/preservation/cassandra_manager_agent.py
@author David Stuebe
@author Matt Rodriguez
@brief agent controlling preservation of OOI Data
"""

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)
from twisted.internet import defer

from ion.core.process.process import ProcessFactory
from ion.core.process.service_process import ServiceProcess, ServiceClient
from ion.core.object import object_utils
from ion.core.data.cassandra import CassandraDataManager, CassandraStorageResource

from ion.core.object import workbench


host_list_type = object_utils.create_type_identifier(object_id=2501, version=1)
simple_password_type = object_utils.create_type_identifier(object_id=2502, version=1)
cassandra_credential_type =  object_utils.create_type_identifier(object_id=2503, version=1)
column_def_type =  object_utils.create_type_identifier(object_id=2508, version=1)

# Persistent Technology Resource:
cassandra_cluster_type =  object_utils.create_type_identifier(object_id=2504, version=1)

# Persistent Archive Resource:
cassandra_keySpace_type =  object_utils.create_type_identifier(object_id=2506, version=1)

# Cache Resource:
column_family_type =  object_utils.create_type_identifier(object_id=2507, version=1)


class CassandraManagerService(ServiceProcess):
    """
    @brief Cassandra Manager Agent interface
    @TODO change to inherit from agent process
    The agent uses a single manager client connection to cassandra to configure
    cassandra persistent archive and cache resources. 
    
    Resources can be created by the agent
    Resources can be modified by the agent
    Resources can be deleted by the agent
    
    The agent is also used during a boot strap procedure...
    """

    # Declaration of service
    declare = ServiceProcess.service_declare(name='cassandra_manager_agent', version='0.1.0', dependencies=[])

    def __init__(self, *args, **kwargs):
        # Service class initializer. Basic config, but no yields allowed.
        ServiceProcess.__init__(self, *args, **kwargs)
        
        # Bootstrap args is a dictionary containing a host list and credentials
        #self.spawn_args['bootstrap_args'] = self.spawn_args.get('bootstrap_args', CONF.getValue('bootstrap_args', default=None))
        
        # Create a Resource Client 
        #self.rc = ResourceClient(proc=self)        
        log.info('CassandraManagerAgent.__init__()')


        
        
    @defer.inlineCallbacks
    def slc_activate(self, *args):
        """
        Activation can be automatic when the process is spawned or triggered by
        a message from the client.
        
        First, default to bootstrapping from the spawn args. Create all resources
        by describing the cluster!
        
        Second, add hooks to override the spawn args and take the storage resource
        reference from a message in op_activate - connecting to an already active
        system!
        
        """
        
        """
        if self.spawn_args.get('bootstrap_args', None):
            
            # Build a storage resource from the spawn_args dictionary 
            #self.spawn_args.get(...)
            storage_resource = yield self.rc.create_instance(...)
            #Fill in vals here...
            yield self.rc.put_instance(storage_resource)
        else:
            # Load the state of the service from the resource registry
            
            #Pass a storage resource ID?
            # Lets put it in the spawn args for now...
            #self.spawn_args.get(...)
            storage_resource = yield self.rc.get_instance(storage_resource_ref)
        """
        #Hard code the storage resource for now. Eventually pass all this into spawn_args
        # The cassandra client manager
        self.wb = workbench.WorkBench("I need this make ION resources")
                ### Create a persistence_technology resource - for cassandra a CassandraCluster object
        persistent_technology_repository, cassandra_cluster  = self.wb.init_repository(cassandra_cluster_type)
        
        # Set only one host and port in the host list for now
        cas_host = cassandra_cluster.hosts.add()
        cas_host.host = 'ec2-204-236-159-249.us-west-1.compute.amazonaws.com'
        cas_host.port = 9160
        
        ### Create a Credentials resource - for cassandra a SimplePassword object
        cache_repository, simple_password  = self.wb.init_repository(simple_password_type)
        simple_password.username = 'ooiuser'
        simple_password.password = 'oceans11'
        
        storage_resource = CassandraStorageResource(cassandra_cluster, credentials=simple_password)
        manager = CassandraDataManager(storage_resource)
        
        #@TODO Need update the register method using Dave F's new code!
        #yield self.register_life_cycle_object(manager)
        
        self.manager = manager
        
        # Now query the cluster to create persistence resources 
        if self.spawn_args.get('bootstrap_args', None):
            yield self._bootstrap()
            pass
        
        
        
    @defer.inlineCallbacks
    def _bootstrap(self):
        yield 1
        #Implement this later
        """
        for keyspace in cassandracluster:
            cassandra_keyspace = yield self.rc.create_instance(...)
            yield self.manager.describe_keyspace(cassandra_keyspace)            
            yield self.rc.put_instance(cassandra_keyspace)
        
        for cf in keyspace
            cassandra_cf = yield self.rc.create_instance(...)
            # ...
            # ...
            
        """
    @defer.inlineCallbacks
    def op_create_persistent_archive(self, persistent_archive, headers, msg):
        """
        Service operation: define a new archive object
        """
        log.info("Called CassandraManagerService.op_create_persistent_archive")
        #cassandra_keyspace = yield self.rc.create_instance(...)
        yield self.manager.create_persistent_archive(persistent_archive)
        #yield self.rc.put_instance(cassandra_keyspace)
        yield self.reply_ok(msg)

    @defer.inlineCallbacks
    def op_update_persistent_archive(self, persistent_archive, headers, msg):
        """
        Service operation: update the persistent_archive
        
        """
        #cassandra_keyspace = yield self.rc.get_instance(pa_ref
        # update cassandra
        yield self.manager.update_persistent_archive(persistent_archive)
        # update the resource
        #yield self.rc.put_instance(cassandra_keyspace)
        yield self.reply_ok(msg)

    @defer.inlineCallbacks
    def op_delete_persistent_archive(self, persistent_archive, headers, msg):
        """
        Service operation: define a new archive object
        
        What should the args be?
        What happens with credentials for a new keyspace?
        """
       # cassandra_keyspace = yield self.rc.create_instance(...)
        yield self.manager.delete_persistent_archive(persistent_archive)
        #yield self.rc.put_instance(cassandra_keyspace)
        yield self.reply_ok(msg)
   
   

# Spawn of the process using the module name
factory = ProcessFactory(CassandraManagerService)


class CassandraManagerClient(ServiceClient):
    def __init__(self, proc=None, **kwargs):
        if not 'targetname' in kwargs:
            kwargs['targetname'] = 'cassandra_manager_agent'
        ServiceClient.__init__(self, proc, **kwargs)
    
    @defer.inlineCallbacks
    def create_persistent_archive(self, persistent_archive):
        """
        @brief create a new archive
        @param persistent_archive is an ion resource which defines the properties of a Keyspace
        """
        log.info("Called CassandraManagerClient.create_persistent_archive")
        (content, headers, msg) = yield self.rpc_send('create_persistent_archive', persistent_archive)
        defer.returnValue(msg)
      
    @defer.inlineCallbacks    
    def update_persistent_archive(self, persistent_archive):
        """
        @brief update an archive
        @param persistent_archive is an ion resource which defines the properties of a Keyspace
        """
        (content, headers, msg) = yield self.rpc_send('update_persistent_archive', persistent_archive)
        defer.returnValue(msg)
    
    @defer.inlineCallbacks
    def delete_presistent_archive(self, persistent_archive):
        """
        @brief remove an archive
        @param persistent_archive is an ion resource which defines the properties of a Keyspace
        """
        (content, headers, msg) = yield self.rpc_send('delete_persistent_archive', persistent_archive)
        defer.returnValue(msg)
