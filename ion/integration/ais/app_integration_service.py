#!/usr/bin/env python

"""
@file ion/integration/app_integration_service.py
@author David Everett
@brief Core service frontend for Application Integration Services
@note The Application Integration Service is presently written to use a special
error response GPB (AIS_RESPONSE_ERROR_TYPE) and not the standard error response
that is generated by the ApplicationError class via the ION exception model. Also
since the client calling this service is likely to not be written in python the
input GPB validating must take place in the service code, not the python client.
"""

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)
import logging
from twisted.internet import defer

from ion.core.object import object_utils
from ion.core.process.process import ProcessFactory
from ion.core.process.service_process import ServiceProcess, ServiceClient
from ion.services.coi.resource_registry.resource_client import ResourceClient
from ion.core.messaging.message_client import MessageClient
from ion.services.dm.inventory.association_service import AssociationServiceClient
from ion.services.coi.identity_registry import IdentityRegistryClient, get_broadcast_receiver
from ion.core.intercept.policy import load_roles_from_associations, map_ooi_id_to_role, unmap_ooi_id_from_role

from ion.core.process.process import Process

# import working classes for AIS
from ion.integration.ais.common.metadata_cache import  MetadataCache
from ion.integration.ais.common.ais_utils import AIS_Mixin

from ion.integration.ais.findDataResources.findDataResources import FindDataResources, \
                                                                    DatasetUpdateEventSubscriber, \
                                                                    DatasourceUpdateEventSubscriber
from ion.integration.ais.getDataResourceDetail.getDataResourceDetail import GetDataResourceDetail
from ion.integration.ais.createDownloadURL.createDownloadURL import CreateDownloadURL
from ion.integration.ais.RegisterUser.RegisterUser import RegisterUser
from ion.integration.ais.ManageResources.ManageResources import ManageResources
from ion.integration.ais.manage_data_resource.manage_data_resource import ManageDataResource
from ion.integration.ais.validate_data_resource.validate_data_resource import ValidateDataResource
from ion.integration.ais.manage_data_resource_subscription.manage_data_resource_subscription import ManageDataResourceSubscription


class AppIntegrationService(ServiceProcess, AIS_Mixin):
    """
    Service to provide clients access to backend data
    """
    # Declaration of service
    declare = ServiceProcess.service_declare(name='app_integration',
                                             version='0.1.0',
                                             dependencies=[])


    def __init__(self, *args, **kwargs):

        ServiceProcess.__init__(self, *args, **kwargs)

        self.rc = ResourceClient(proc = self)
        self.mc = MessageClient(proc = self)
        self.asc = AssociationServiceClient(proc = self)
    
        log.debug('AppIntegrationService.__init__()')

    @defer.inlineCallbacks
    def spawn_worker(self,name):
        """
        For now - keep it simple and use register life cycle object to control the workers.

        Consider changing to use spanw child - but we need to get the actual instance object not just the id...

        """

        class AIS_Worker_Process(Process, AIS_Mixin):
            """
            Worker process for the AIS service
            """

        worker = AIS_Worker_Process(spawnargs={'proc-name':name})

        worker.mc = worker.message_client
        worker.rc = ResourceClient(worker)

        worker.asc = AssociationServiceClient(proc = worker)

        yield worker.spawn()

        yield self.register_life_cycle_object(worker)

        defer.returnValue(worker)


    @defer.inlineCallbacks
    def slc_init(self):

        #== Create a process for the metadata cache and data resource workers
        data_resource_worker = yield self.spawn_worker('resource_cache_worker')
        self._data_resource_worker = data_resource_worker

        metadataCache = MetadataCache(data_resource_worker)
        data_resource_worker.metadataCache = metadataCache
        log.debug('Instantiated AIS Metadata Cache Object')
        yield data_resource_worker.metadataCache.loadDataSets()
        yield data_resource_worker.metadataCache.loadDataSources()

        log.info('instantiating DatasetUpdateEventSubscriber')
        data_resource_worker.dataset_subscriber = DatasetUpdateEventSubscriber(process = data_resource_worker)
        yield data_resource_worker.register_life_cycle_object(data_resource_worker.dataset_subscriber)
        
        log.info('instantiating DatasourceUpdateEventSubscriber')
        data_resource_worker.datasource_subscriber = DatasourceUpdateEventSubscriber(process = data_resource_worker)
        yield data_resource_worker.register_life_cycle_object(data_resource_worker.datasource_subscriber)


        data_resource_worker.workbench.manage_workbench_cache('Default Context')

        self.FindDataResourcesWorker = FindDataResources(self, metadataCache)
        self.GetDataResourceDetailWorker = GetDataResourceDetail(self, metadataCache)

        self.ManageDataResourceSubscriptionWorker = ManageDataResourceSubscription(self, metadataCache)

        self.ManageResourcesWorker = ManageResources(self,metadataCache)

        self.ManageDataResourceWorker = ManageDataResource(self)

        self.CreateDownloadURLWorker = CreateDownloadURL(self)
        self.RegisterUserWorker = RegisterUser(self)
        self.ValidateDataResourceWorker = ValidateDataResource(self)

    @defer.inlineCallbacks
    def slc_activate(self):
        # Setup broadcast channel (for policy reloading)
        self.bc_receiver = yield get_broadcast_receiver(self.receive, self.receive_error)

        # Load current role associations
        yield load_roles_from_associations(self.asc)

    def op_broadcast(self, content, headers, msg):
        """
        Service operation: communication amongst identity registry containers
        """
        log.info('op_broadcast(): Received identity registry broadcast in AppIntegrationService')

        if 'op' in content:
            op = content['op']
            log.info('doing op_broadcast operation %s' % (op))
            if op == 'set_user_role':
                map_ooi_id_to_role(content['user-id'], content['role'])
            elif op == 'unset_user_role':
                unmap_ooi_id_from_role(content['user-id'], content['role'])


    @defer.inlineCallbacks
    def op_findDataResources(self, content, headers, msg):
        """
        @brief Find data resources that have been published, regardless
        of owner.
        @param GPB optional spatial and temporal bounds.
        @retval GPB with list of resource IDs.
        """

        log.debug('op_findDataResources service method.')
        returnValue = yield self.FindDataResourcesWorker.findDataResources(content)
        yield self.reply_ok(msg, returnValue)

    @defer.inlineCallbacks
    def op_findDataResourcesByUser(self, content, headers, msg):
        """
        @brief Find data resources associated with given userID,
        regardless of life cycle state.
        @param GPB containing OOID user ID, and option spatial and temporal
        bounds.
        @retval GPB with list of resource IDs.
        """

        log.debug('op_findDataResourcesByUser service method.')
        returnValue = yield self.FindDataResourcesWorker.findDataResourcesByUser(content)
        yield self.reply_ok(msg, returnValue)

    @defer.inlineCallbacks
    def op_getDataResourceDetail(self, content, headers, msg):
        """
        @brief Get detailed metadata for a given resource ID.
        @param GPB containing resource ID.
        @retval GPB containing detailed metadata.
        """

        log.info('op_getDataResourceDetail service method')
        returnValue = yield self.GetDataResourceDetailWorker.getDataResourceDetail(content)
        yield self.reply_ok(msg, returnValue)


    @defer.inlineCallbacks
    def op_createDownloadURL(self, content, headers, msg):
        """
        @brief Create download URL for given resource ID.
        @param GPB containing resource ID.
        @retval GPB containing download URL.
        """

        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_createDownloadURL: '+str(content))
        returnValue = yield self.CreateDownloadURLWorker.createDownloadURL(content)
        yield self.reply_ok(msg, returnValue)   

    @defer.inlineCallbacks
    def op_registerUser(self, content, headers, msg):
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_registerUser: \n'+str(content))
        response = yield self.RegisterUserWorker.registerUser(content);
        yield self.reply_ok(msg, response)
        
    @defer.inlineCallbacks
    def op_updateUserProfile(self, content, headers, msg):
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_updateUserProfile: \n'+str(content))
        response = yield self.RegisterUserWorker.updateUserProfile(content);
        yield self.reply_ok(msg, response)
        
    @defer.inlineCallbacks
    def op_getUser(self, content, headers, msg):
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_getUser: \n'+str(content))
        response = yield self.RegisterUserWorker.getUser(content);
        yield self.reply_ok(msg, response)

    @defer.inlineCallbacks
    def op_setUserRole(self, content, headers, msg):
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_setUserRole: \n'+str(content))
        response = yield self.RegisterUserWorker.setUserRole(content)
        yield self.reply_ok(msg, response)
        
    def getTestDatasetID(self):
        return self.dsID
                         
    @defer.inlineCallbacks
    def op_getResourceTypes(self, content, headers, msg):
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_getResourceTypes: \n'+str(content))
        response = yield self.ManageResourcesWorker.getResourceTypes(content);
        yield self.reply_ok(msg, response)

    @defer.inlineCallbacks
    def op_getResourcesOfType(self, content, headers, msg):
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_getResourcesOfType: \n'+str(content))
        response = yield self.ManageResourcesWorker.getResourcesOfType(content);
        yield self.reply_ok(msg, response)


    @defer.inlineCallbacks
    def op_getResource(self, content, headers, msg):
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_getResource: \n'+str(content))
        response = yield self.ManageResourcesWorker.getResource(content);
        yield self.reply_ok(msg, response)


    @defer.inlineCallbacks
    def op_createDataResource(self, content, headers, msg):
        """
        @brief create a new data resource
        """
        log.debug('op_createDataResource: \n'+str(content))
        response = yield self.ManageDataResourceWorker.create(content);
        yield self.reply_ok(msg, response)

    @defer.inlineCallbacks
    def op_updateDataResource(self, content, headers, msg):
        """
        @brief create a new data resource
        """
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_updateDataResource: \n'+str(content))
        response = yield self.ManageDataResourceWorker.update(content);
        yield self.reply_ok(msg, response)

    @defer.inlineCallbacks
    def op_deleteDataResource(self, content, headers, msg):
        """
        @brief create a new data resource
        """
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_deleteDataResource: \n'+str(content))
        response = yield self.ManageDataResourceWorker.delete(content);
        yield self.reply_ok(msg, response)

    @defer.inlineCallbacks
    def op_validateDataResource(self, content, headers, msg):
        """
        @brief validate a data resource URL
        """
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_validateDataResource: \n'+str(content))
        response = yield self.ValidateDataResourceWorker.validate(content);
        yield self.reply_ok(msg, response)


    @defer.inlineCallbacks
    def op_createDataResourceSubscription(self, content, headers, msg):
        """
        @brief subscribe to a data resource
        """
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_createDataResourceSubscription: \n'+str(content))
        response = yield self.ManageDataResourceSubscriptionWorker.create(content);
        yield self.reply_ok(msg, response)

    @defer.inlineCallbacks
    def op_findDataResourceSubscriptions(self, content, headers, msg):
        """
        @brief find subscriptions to a data resource
        """
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_findDataResourceSubscriptions: \n'+str(content))
        response = yield self.ManageDataResourceSubscriptionWorker.find(content);
        yield self.reply_ok(msg, response)

    @defer.inlineCallbacks
    def op_deleteDataResourceSubscription(self, content, headers, msg):
        """
        @brief delete subscription to a data resource
        """
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_deleteDataResourceSubscription: \n'+str(content))
        response = yield self.ManageDataResourceSubscriptionWorker.delete(content);
        yield self.reply_ok(msg, response)

    @defer.inlineCallbacks
    def op_updateDataResourceSubscription(self, content, headers, msg):
        """
        @brief update subscription to a data resource
        """
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('op_updateDataResourceSubscription: \n'+str(content))
        response = yield self.ManageDataResourceSubscriptionWorker.update(content);
        yield self.reply_ok(msg, response)



class AppIntegrationServiceClient(ServiceClient):
    """
    This is a service client for AppIntegrationServices.
    """
    def __init__(self, proc=None, **kwargs):
        if not 'targetname' in kwargs:
            kwargs['targetname'] = "app_integration"
        ServiceClient.__init__(self, proc, **kwargs)
        self.mc = MessageClient(proc=proc)
        
    @defer.inlineCallbacks
    def findDataResources(self, message, user_ooi_id):
        yield self._check_init()
        log.debug("AppIntegrationServiceClient: findDataResources(): sending msg to AppIntegrationService.")
        (content, headers, payload) = yield self.rpc_send_protected('findDataResources',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.info('Service reply: ' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def findDataResourcesByUser(self, message, user_ooi_id):
        yield self._check_init()
        log.debug("AppIntegrationServiceClient: findDataResourcesByUser(): sending msg to AppIntegrationService.")
        (content, headers, payload) = yield self.rpc_send_protected('findDataResourcesByUser',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.info('Service reply: ' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def getDataResourceDetail(self, message, user_ooi_id):
        yield self._check_init()
        log.debug("AppIntegrationServiceClient: getDataResourceDetail(): sending msg to AppIntegrationService.")
        (content, headers, payload) = yield self.rpc_send_protected('getDataResourceDetail',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.info('Service reply: ' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def createDownloadURL(self, message, user_ooi_id):
        yield self._check_init()
        log.debug("AppIntegrationServiceClient: createDownloadURL(): sending msg to AppIntegrationService.")
        (content, headers, payload) = yield self.rpc_send_protected('createDownloadURL',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.info('Service reply: ' + str(content))
        defer.returnValue(content)
 
    @defer.inlineCallbacks
    def registerUser(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.registerUser: sending following message to registerUser:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('registerUser',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.registerUser: IR Service reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def updateUserProfile(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.updateUserProfile: sending following message to updateUserProfile:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('updateUserProfile',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.updateUserProfile: IR Service reply:\n' + str(content))
        defer.returnValue(content)
              
    @defer.inlineCallbacks
    def getUser(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.getUser: sending following message to getUser:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('getUser',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.getUser: IR Service reply:\n' + str(content))
        defer.returnValue(content)

    @defer.inlineCallbacks
    def setUserRole(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.setUserRole: sending following message to setUserRole:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('setUserRole',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.setUserRole: IR Service reply:\n' + str(content))
        defer.returnValue(content)
              
    @defer.inlineCallbacks
    def getResourceTypes(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.getResourceTypes: sending following message to getResourceTypes:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('getResourceTypes',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.getResourceTypes: AIS reply:\n' + str(content))
        defer.returnValue(content)
 
    @defer.inlineCallbacks
    def getResourcesOfType(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.getResourcesOfType: sending following message to getResourcesOfType:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('getResourcesOfType',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.getResourcesOfType: AIS reply:\n' + str(content))
        defer.returnValue(content)
 
    @defer.inlineCallbacks
    def getResource(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.getResource: sending following message to getResource:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('getResource',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.getResource: AIS reply:\n' + str(content))
        defer.returnValue(content)
 
    @defer.inlineCallbacks
    def createDataResource(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.createDataResource: sending following message to createDataResource:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('createDataResource',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0",
                                                                    timeout=30)
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.createDataResource: AIS reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def updateDataResource(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.updateDataResource: sending following message to updateDataResource:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('updateDataResource',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0",
                                                                    timeout=30)
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.updateDataResource: AIS reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def deleteDataResource(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.deleteDataResource: sending following message to deleteDataResource:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('deleteDataResource',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0",
                                                                    timeout=30)
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.deleteDataResource: AIS reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def validateDataResource(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.validateDataResource: sending following message to validateDataResource:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('validateDataResource',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0",
                                                                    timeout=120)
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.validateDataResource: AIS reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def createDataResourceSubscription(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.createDataResourceSubscription: sending following message:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('createDataResourceSubscription',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.createDataResourceSubscription: AIS reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def findDataResourceSubscriptions(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.findDataResourceSubscriptions: sending following message:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('findDataResourceSubscriptions',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.findDataResourceSubscriptions: AIS reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def deleteDataResourceSubscription(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.deleteDataResourceSubscription: sending following message:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('deleteDataResourceSubscription',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.deleteDataResourceSubscription: AIS reply:\n' + str(content))
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def updateDataResourceSubscription(self, message, user_ooi_id):
        yield self._check_init()
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("AIS_client.updateDataResourceSubscription: sending following message:\n%s" % str(message))
        (content, headers, payload) = yield self.rpc_send_protected('updateDataResourceSubscription',
                                                                    message,
                                                                    user_ooi_id,
                                                                    "0")
        if log.getEffectiveLevel() <= logging.DEBUG:
            log.debug('AIS_client.updateDataResourceSubscription: AIS reply:\n' + str(content))
        defer.returnValue(content)
        
# Spawn of the process using the module name
factory = ProcessFactory(AppIntegrationService)

