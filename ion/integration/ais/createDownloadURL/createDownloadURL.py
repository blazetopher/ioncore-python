#!/usr/bin/env python

"""
@file ion/integration/ais/createDownloadURL/createDownloadURL.py
@author David Everett
@brief Worker class to construct the download URL for given data resource
"""

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)
from twisted.internet import defer

from ion.services.coi.resource_registry_beta.resource_client import ResourceClient, ResourceInstance
#from ion.services.dm.inventory.dataset_controller import DatasetControllerClient
# DHE Temporarily pulling DatasetControllerClient from scaffolding
from ion.integration.ais.findDataResources.resourceStubs import DatasetControllerClient

# import GPB type identifiers for AIS
from ion.integration.ais.ais_object_identifiers import AIS_REQUEST_MSG_TYPE, AIS_RESPONSE_MSG_TYPE
from ion.integration.ais.ais_object_identifiers import FIND_DATA_RESOURCES_REQ_MSG_TYPE
from ion.integration.ais.ais_object_identifiers import FIND_DATA_RESOURCES_RSP_MSG_TYPE

from ion.core.object import object_utils

class CreateDownloadURL(object):
    
    def __init__(self, ais):
        log.info('CreateDownloadURL.__init__()')
        self.rc = ResourceClient()
        self.mc = ais.mc
        self.dscc = DatasetControllerClient()

        
    @defer.inlineCallbacks
    def createDownloadURL(self, msg):
        log.debug('createDownloadURL Worker Class got GPB: \n' + str(msg))

        rspMsg = yield self.mc.create_instance(AIS_RESPONSE_MSG_TYPE)
        rspMsg.message_parameters_reference.add()
        #rspMsg.message_parameters_reference[0].data_resource_id.add()

        defer.returnValue(rspMsg)


