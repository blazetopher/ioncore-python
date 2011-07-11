#!/usr/bin/env python

"""
@file ion/services/dm/ingestion/test/test_ingestion.py
@author David Stuebe
@brief test for eoi ingestion demo
"""
from ion.core.exception import ReceivedApplicationError
from ion.services.coi.resource_registry.resource_client import ResourceClient
from ion.services.dm.distribution.publisher_subscriber import Subscriber, Publisher

import ion.util.ionlog
from ion.util.iontime import IonTime

log = ion.util.ionlog.getLogger(__name__)
from twisted.internet import defer
from twisted.trial import unittest
import random

from ion.core import ioninit
from ion.util import procutils as pu
from ion.services.coi.datastore_bootstrap.ion_preload_config import PRELOAD_CFG, ION_DATASETS_CFG, SAMPLE_PROFILE_DATASET_ID, SAMPLE_PROFILE_DATA_SOURCE_ID, TYPE_CFG, NAME_CFG, DESCRIPTION_CFG, CONTENT_CFG, CONTENT_ARGS_CFG, ID_CFG

from ion.services.dm.distribution.events import DatasourceUnavailableEventSubscriber, DatasetSupplementAddedEventSubscriber, DATASET_STREAMING_EVENT_ID, get_events_exchange_point

from ion.core.process import process
from ion.services.dm.ingestion.ingestion import IngestionClient, SUPPLEMENT_MSG_TYPE, CDM_DATASET_TYPE, DAQ_COMPLETE_MSG_TYPE, PERFORM_INGEST_MSG_TYPE, CREATE_DATASET_TOPICS_MSG_TYPE, EM_URL, EM_ERROR, EM_TITLE, EM_DATASET, EM_END_DATE, EM_START_DATE, EM_TIMESTEPS, EM_DATA_SOURCE
from ion.test.iontest import IonTestCase

from ion.services.coi.datastore_bootstrap.dataset_bootstrap import bootstrap_profile_dataset, BOUNDED_ARRAY_TYPE, FLOAT32ARRAY_TYPE, bootstrap_byte_array_dataset

from ion.services.dm.ingestion.ingestion import CREATE_DATASET_TOPICS_MSG_TYPE

from ion.core.object.object_utils import create_type_identifier, ARRAY_STRUCTURE_TYPE


DATASET_TYPE = create_type_identifier(object_id=10001, version=1)
DATASOURCE_TYPE = create_type_identifier(object_id=4503, version=1)
GROUP_TYPE = create_type_identifier(object_id=10020, version=1)


CONF = ioninit.config(__name__)


class FakeDelayedCall(object):

    def active(self):
        return True

    def cancel(self):
        pass

    def delay(self, int):
        pass

class IngestionTest(IonTestCase):
    """
    Testing service operations of the ingestion service.
    """

    @defer.inlineCallbacks
    def setUp(self):
        yield self._start_container()
        services = [
            {   'name':'ds1',
                'module':'ion.services.coi.datastore',
                'class':'DataStoreService',
                'spawnargs':
                        {PRELOAD_CFG:
                                 {ION_DATASETS_CFG:True}
                        }
            },

            {
                'name':'resource_registry1',
                'module':'ion.services.coi.resource_registry.resource_registry',
                'class':'ResourceRegistryService',
                    'spawnargs':{'datastore_service':'datastore'}
            },

            {
                'name':'exchange_management',
                'module':'ion.services.coi.exchange.exchange_management',
                'class':'ExchangeManagementService',
            },

            {
                'name':'association_service',
                'module':'ion.services.dm.inventory.association_service',
                'class':'AssociationService'
            },
            {
                'name':'pubsub_service',
                'module':'ion.services.dm.distribution.pubsub_service',
                'class':'PubSubService'
            },

            {   'name':'ingestion1',
                'module':'ion.services.dm.ingestion.ingestion',
                'class':'IngestionService'
            },

            ]

        # ADD PUBSUB AND EMS

        self.sup = yield self._spawn_processes(services)

        self.proc = process.Process(spawnargs={'proc-name':'test_ingestion_proc'})
        yield self.proc.spawn()

        self._ic = IngestionClient(proc=self.proc)

        ingestion1 = yield self.sup.get_child_id('ingestion1')
        log.debug('Process ID:' + str(ingestion1))
        self.ingest= self._get_procinstance(ingestion1)

        ds1 = yield self.sup.get_child_id('ds1')
        log.debug('Process ID:' + str(ds1))
        self.datastore= self._get_procinstance(ds1)

        self.rc = ResourceClient(proc=self.proc)


    class fake_msg(object):

        def ack(self):
            return True


    @defer.inlineCallbacks
    def tearDown(self):
        # You must explicitly clear the registry in case cassandra is used as a back end!
        yield self._stop_container()


    @defer.inlineCallbacks
    def test_create_dataset_topics(self):
        """
        """

        msg = yield self.proc.message_client.create_instance(CREATE_DATASET_TOPICS_MSG_TYPE)

        msg.dataset_id = 'ABC'

        result = yield self._ic.create_dataset_topics(msg)

        result.MessageResponseCode = result.ResponseCodes.OK


    @defer.inlineCallbacks
    def test_recv_dataset(self):
        """
        This is a test method for the recv dataset operation of the ingestion service
        """
        #print '\n\n\n Starting Test \n\n\n\n'
        # Reach into the ingestion service and fake the receipt of a perform ingest method - so we can test recv_dataset

        content = yield self.ingest.mc.create_instance(PERFORM_INGEST_MSG_TYPE)
        content.dataset_id = SAMPLE_PROFILE_DATASET_ID
        content.datasource_id = SAMPLE_PROFILE_DATA_SOURCE_ID



        yield self.ingest._prepare_ingest(content)

        self.ingest.timeoutcb = FakeDelayedCall()

        #print '\n\n\n Got Dataset in Ingest \n\n\n\n'

        # Now fake the receipt of the dataset message
        cdm_dset_msg = yield self.ingest.mc.create_instance(CDM_DATASET_TYPE)
        yield bootstrap_profile_dataset(cdm_dset_msg, supplement_number=1, random_initialization=True)

        #print '\n\n\n Filled out message with a dataset \n\n\n\n'

        # Call the op of the ingest process directly
        yield self.ingest._ingest_op_recv_dataset(cdm_dset_msg, '', self.fake_msg())

        # ==========
        # Can't use messaging and client because the send returns before the op is complete so the result is untestable.
        #yield self._ic.send_dataset(SAMPLE_PROFILE_DATASET_ID,cdm_dset_msg)
        #yield pu.asleep(1)
        # ==========

        self.assertEqual(self.ingest.dataset.ResourceLifeCycleState, self.ingest.dataset.UPDATE)



    @defer.inlineCallbacks
    def test_recv_chunk(self):
        """
        This is a test method for the recv dataset operation of the ingestion service
        """

        #print '\n\n\n Starting Test \n\n\n\n'
        # Reach into the ingestion service and fake the receipt of a perform ingest method - so we can test recv_dataset

        content = yield self.ingest.mc.create_instance(PERFORM_INGEST_MSG_TYPE)
        content.dataset_id = SAMPLE_PROFILE_DATASET_ID
        content.datasource_id = SAMPLE_PROFILE_DATA_SOURCE_ID

        yield self.ingest._prepare_ingest(content)

        self.ingest.timeoutcb = FakeDelayedCall()

        self.ingest.dataset.CreateUpdateBranch()

        #print '\n\n\n Got Dataset in Ingest \n\n\n\n'

        # Pick a few variables to 'update'
        var_list = ['time', 'depth', 'lat', 'lon', 'salinity']

        for var in var_list:

            yield self.create_and_test_variable_chunk(var)


    @defer.inlineCallbacks
    def create_and_test_variable_chunk(self, var_name):

        group = self.ingest.dataset.root_group
        var = group.FindVariableByName(var_name)
        starting_bounded_arrays  = var.content.bounded_arrays[:]

        supplement_msg = yield self.ingest.mc.create_instance(SUPPLEMENT_MSG_TYPE)
        supplement_msg.dataset_id = SAMPLE_PROFILE_DATASET_ID
        supplement_msg.variable_name = var_name

        self.create_chunk(supplement_msg)

        # Call the op of the ingest process directly
        yield self.ingest._ingest_op_recv_chunk(supplement_msg, '', self.fake_msg())

        updated_bounded_arrays = var.content.bounded_arrays[:]

        # This is all we really need to do - make sure that the bounded array has been added.
        self.assertEqual(len(updated_bounded_arrays), len(starting_bounded_arrays)+1)

        # The bounded array but not the ndarray should be in the ingestion service dataset
        self.assertIn(supplement_msg.bounded_array.MyId, self.ingest.dataset.Repository.index_hash)
        self.assertNotIn(supplement_msg.bounded_array.ndarray.MyId, self.ingest.dataset.Repository.index_hash)

        # The datastore should now have this ndarray
        self.failUnless(self.datastore.b_store.has_key(supplement_msg.bounded_array.ndarray.MyId))


    def create_chunk(self, supplement_msg):
        """
        This method is specialized to create bounded arrays for the Sample profile dataset.
        """



        supplement_msg.bounded_array = supplement_msg.CreateObject(BOUNDED_ARRAY_TYPE)
        supplement_msg.bounded_array.ndarray = supplement_msg.CreateObject(FLOAT32ARRAY_TYPE)

        if supplement_msg.variable_name == 'time':

            tsteps = 3
            tstart = 1280106120
            delt = 3600
            supplement_msg.bounded_array.ndarray.value.extend([tstart + delt*n for n in range(tsteps)])

            supplement_msg.bounded_array.bounds.add()
            supplement_msg.bounded_array.bounds[0].origin = 0
            supplement_msg.bounded_array.bounds[0].size = tsteps

        elif supplement_msg.variable_name == 'depth':
            supplement_msg.bounded_array.ndarray.value.extend([0.0, 0.1, 0.2])
            supplement_msg.bounded_array.bounds.add()
            supplement_msg.bounded_array.bounds[0].origin = 0
            supplement_msg.bounded_array.bounds[0].size = 3

        elif supplement_msg.variable_name == 'salinity':
            supplement_msg.bounded_array.ndarray.value.extend([29.84, 29.76, 29.87, 30.16, 30.55, 30.87])
            supplement_msg.bounded_array.bounds.add()
            supplement_msg.bounded_array.bounds[0].origin = 0
            supplement_msg.bounded_array.bounds[0].size = 2
            supplement_msg.bounded_array.bounds.add()
            supplement_msg.bounded_array.bounds[1].origin = 0
            supplement_msg.bounded_array.bounds[1].size = 3


        supplement_msg.Repository.commit('Commit before fake send...')


    @defer.inlineCallbacks
    def test_recv_done(self):
        """
        This is a test method for the recv dataset operation of the ingestion service
        """

        # Receive a dataset to get setup...
        content = yield self.ingest.mc.create_instance(PERFORM_INGEST_MSG_TYPE)
        content.dataset_id = SAMPLE_PROFILE_DATASET_ID
        content.datasource_id = SAMPLE_PROFILE_DATA_SOURCE_ID

        yield self.ingest._prepare_ingest(content)

        self.ingest.timeoutcb = FakeDelayedCall()

        # Now fake the receipt of the dataset message
        cdm_dset_msg = yield self.ingest.mc.create_instance(CDM_DATASET_TYPE)
        yield bootstrap_profile_dataset(cdm_dset_msg, supplement_number=1, random_initialization=True)

        # Call the op of the ingest process directly
        yield self.ingest._ingest_op_recv_dataset(cdm_dset_msg, '', self.fake_msg())


        complete_msg = yield self.ingest.mc.create_instance(DAQ_COMPLETE_MSG_TYPE)

        complete_msg.status = complete_msg.StatusCode.OK
        yield self.ingest._ingest_op_recv_done(complete_msg, '', self.fake_msg())

    @defer.inlineCallbacks
    def _create_datasource_and_set(self, new_dataset_id, new_datasource_id):

        def create_dataset(dataset, *args, **kwargs):
            """
            Create an empty dataset
            """
            group = dataset.CreateObject(GROUP_TYPE)
            dataset.root_group = group
            return True

        data_set_description = {ID_CFG:new_dataset_id,
                      TYPE_CFG:DATASET_TYPE,
                      NAME_CFG:'Blank dataset for testing ingestion',
                      DESCRIPTION_CFG:'An example of a station dataset',
                      CONTENT_CFG:create_dataset,
                      }

        self.datastore._create_resource(data_set_description)

        dset_res = self.datastore.workbench.get_repository(new_dataset_id)

        log.info('Created Dataset Resource for test.')

        def create_datasource(datasource, *args, **kwargs):
            """
            Create an empty dataset
            """
            datasource.source_type = datasource.SourceType.NETCDF_S
            datasource.request_type = datasource.RequestType.DAP

            datasource.base_url = "http://not_a_real_url.edu"

            datasource.max_ingest_millis = 6000

            datasource.registration_datetime_millis = IonTime().time_ms

            datasource.ion_title = "NTAS1 Data Source"
            datasource.ion_description = "Data NTAS1"

            datasource.aggregation_rule = datasource.AggregationRule.OVERLAP

            return True


        data_source_description = {ID_CFG:new_datasource_id,
                      TYPE_CFG:DATASOURCE_TYPE,
                      NAME_CFG:'datasource for testing ingestion',
                      DESCRIPTION_CFG:'An example of a station datasource',
                      CONTENT_CFG:create_datasource,
                      }

        self.datastore._create_resource(data_source_description)

        dsource_res = self.datastore.workbench.get_repository(new_datasource_id)

        log.info('Created Datasource Resource for test.')

        yield self.datastore.workbench.flush_repo_to_backend(dset_res)
        yield self.datastore.workbench.flush_repo_to_backend(dsource_res)

        log.info('Data resources flushed to backend')
        defer.returnValue((dset_res, dsource_res))


    @defer.inlineCallbacks
    def test_ingest_on_new_dataset(self):
        """
        This is a test method for the recv dataset operation of the ingestion service
        """

        new_dataset_id = 'C37A2796-E44C-47BF-BBFB-637339CE81D0'
        new_datasource_id = '0B1B4D49-6C64-452F-989A-2CDB02561BBE'
        yield self._create_datasource_and_set(new_dataset_id, new_datasource_id)

        # Receive a dataset to get setup...
        content = yield self.ingest.mc.create_instance(PERFORM_INGEST_MSG_TYPE)
        content.dataset_id = new_dataset_id
        content.datasource_id = new_datasource_id

        yield self.ingest._prepare_ingest(content)

        self.ingest.timeoutcb = FakeDelayedCall()

        # Now fake the receipt of the dataset message
        cdm_dset_msg = yield self.ingest.mc.create_instance(CDM_DATASET_TYPE)
        yield bootstrap_profile_dataset(cdm_dset_msg, supplement_number=1, random_initialization=True)

        log.info('Calling Receive Dataset')

        # Call the op of the ingest process directly
        yield self.ingest._ingest_op_recv_dataset(cdm_dset_msg, '', self.fake_msg())

        log.info('Calling Receive Dataset: Complete')

        complete_msg = yield self.ingest.mc.create_instance(DAQ_COMPLETE_MSG_TYPE)

        log.info('Calling Receive Done')

        complete_msg.status = complete_msg.StatusCode.OK
        yield self.ingest._ingest_op_recv_done(complete_msg, '', self.fake_msg())

        log.info('Calling Receive Done: Complete!')





    @defer.inlineCallbacks
    def test_notify(self):

        ### Test the unavailable notification
        sub_unavailable = DatasourceUnavailableEventSubscriber(process=self.proc, origin=SAMPLE_PROFILE_DATA_SOURCE_ID)
        yield sub_unavailable.initialize()
        yield sub_unavailable.activate()

        test_deferred = defer.Deferred()

        sub_unavailable.ondata = lambda msg: test_deferred.callback( msg['content'].additional_data.error_explanation)

        data_details = {EM_TITLE:'title',
                       EM_URL:'references',
                       EM_DATA_SOURCE:SAMPLE_PROFILE_DATA_SOURCE_ID,
                       EM_DATASET:SAMPLE_PROFILE_DATASET_ID,
                       EM_ERROR:'ERROR # 1',
                       }
        yield self.ingest._notify_ingest(data_details)
        errors_received = yield test_deferred

        self.assertEqual(errors_received, 'ERROR # 1')


        test_deferred = defer.Deferred()

        data_details = {EM_TITLE:'title',
                       EM_URL:'references',
                       EM_DATA_SOURCE:SAMPLE_PROFILE_DATA_SOURCE_ID,
                       EM_DATASET:SAMPLE_PROFILE_DATASET_ID,
                       EM_ERROR:'ERROR # 2',
                       }
        yield self.ingest._notify_ingest(data_details)
        errors_received = yield test_deferred

        self.assertEqual(errors_received, 'ERROR # 2')


        ### Test the Data Supplement notification
        sub_added = DatasetSupplementAddedEventSubscriber(process=self.proc, origin=SAMPLE_PROFILE_DATASET_ID)
        yield sub_added.initialize()
        yield sub_added.activate()

        sub_added.ondata = lambda msg: test_deferred.callback( msg['content'].additional_data.number_of_timesteps)

        test_deferred = defer.Deferred()

        data_details = {EM_TITLE:'title',
                        EM_URL:'references',
                        EM_DATA_SOURCE:SAMPLE_PROFILE_DATA_SOURCE_ID,
                        EM_DATASET:SAMPLE_PROFILE_DATASET_ID,
                        EM_START_DATE:59,
                        EM_END_DATE:69,
                        EM_TIMESTEPS:7
                        }
        yield self.ingest._notify_ingest(data_details)
        nsteps = yield test_deferred

        self.assertEqual(nsteps, 7)

    @defer.inlineCallbacks
    def test_error_in_ingest(self):
        """
        Attempts to raise an error during the ingestion process to ensure they are trapped and
        reported properly.  We are simulating JAW/DatasetAgent interaction and do a simple "incorrect message type"
        to the first sub-ingestion method.
        """

        new_dataset_id = 'C37A2796-E44C-47BF-BBFB-637339CE81D0'
        new_datasource_id = '0B1B4D49-6C64-452F-989A-2CDB02561BBE'
        yield self._create_datasource_and_set(new_dataset_id, new_datasource_id)

        # now, start ingestion on this fake dataset
        msg = yield self.proc.message_client.create_instance(PERFORM_INGEST_MSG_TYPE)
        msg.dataset_id = new_dataset_id
        msg.reply_to = "fake.respond"
        msg.ingest_service_timeout = 45
        msg.datasource_id = new_datasource_id

        # get a subscriber going for the ingestion ready message
        def_ready = defer.Deferred()
        def readyrecv(data):
            def_ready.callback(True)

        readysub = Subscriber(xp_name="magnet.topic",
                              binding_key="fake.respond",
                              process=self.proc)
        readysub.ondata = readyrecv
        yield readysub.initialize()
        yield readysub.activate()

        # start ingestion, hold its deferred as we need to do something with it in a bit
        ingestdef = self._ic.ingest(msg)

        # wait for ready response from ingestion
        yield def_ready

        log.info("Ready response from ingestion, proceeding to give it an incorrect message type to recv_chunk")

        # now send it an incorrect message, make sure we get an error back
        badmsg = yield self.proc.message_client.create_instance(SUPPLEMENT_MSG_TYPE)

        pub = Publisher(process=self.proc,
                        xp_name=get_events_exchange_point(),
                        routing_key="%s.%s" % (str(DATASET_STREAMING_EVENT_ID), new_dataset_id))

        yield pub.initialize()
        yield pub.activate()

        # yuck, can't use pub.publish, it won't let us set an op
        kwargs = { 'recipient' : pub._routing_key,
                   'content'   : badmsg,
                   'headers'   : {'sender-name' : self.proc.proc_name },
                   'operation' : 'recv_dataset',
                   'sender'    : self.proc.id.full }

        yield pub._recv.send(**kwargs)

        yield self.failUnlessFailure(ingestdef, ReceivedApplicationError)

        # check called back thing
        self.failUnless("Expected message type" in ingestdef.result.msg_content.MessageResponseBody)
        self.failUnless(ingestdef.result.msg_content.MessageResponseCode, msg.ResponseCodes.BAD_REQUEST)

    @defer.inlineCallbacks
    def test_recv_random_order(self):
        """
        Tests a variable in a dataset can be sent in many chunks in any order and it assembles properly.
        """
        new_dataset_id = 'C37A2796-E44C-47BF-BBFB-637339CE81D0'
        new_datasource_id = '0B1B4D49-6C64-452F-989A-2CDB02561BBE'
        yield self._create_datasource_and_set(new_dataset_id, new_datasource_id)

        dataset = yield self.rc.get_instance(new_dataset_id)
        #datasource = yield self.rc.get_instance(content.datasource_id)

        # add our variable
        var_name = "depth"
        float_type = dataset.root_group.DataType.FLOAT
        ddim = dataset.root_group.AddDimension(var_name, 100, False)
        var = dataset.root_group.AddVariable(var_name, float_type, [ddim])
        var.content = dataset.CreateObject(ARRAY_STRUCTURE_TYPE)

        # push this back
        yield self.rc.put_instance(dataset, "Added depth variable")

        # boilerplate for starting ingestion
        content = yield self.ingest.mc.create_instance(PERFORM_INGEST_MSG_TYPE)
        content.dataset_id = new_dataset_id
        content.datasource_id = new_datasource_id

        yield self.ingest._prepare_ingest(content)

        self.ingest.timeoutcb = FakeDelayedCall()

        self.ingest.dataset.CreateUpdateBranch()

        # swap out our reference to var to be the one ingest is working with (so we don't have to pull again)
        group = self.ingest.dataset.root_group
        var = group.FindVariableByName(var_name)

        # start creating chunks of the same variable!
        starting_bounded_arrays  = var.content.bounded_arrays[:]

        log.debug("num bas %d" % len(starting_bounded_arrays))

        shuflist = [x for x in xrange(10)]
        random.shuffle(shuflist)
        for x in shuflist:
            log.debug("Creating depth chunk %d" % x)
            supplement_msg = yield self.ingest.mc.create_instance(SUPPLEMENT_MSG_TYPE)
            supplement_msg.dataset_id = SAMPLE_PROFILE_DATASET_ID
            supplement_msg.variable_name = var_name

            supplement_msg.bounded_array = supplement_msg.CreateObject(BOUNDED_ARRAY_TYPE)
            supplement_msg.bounded_array.ndarray = supplement_msg.CreateObject(FLOAT32ARRAY_TYPE)

            # set bounds
            supplement_msg.bounded_array.bounds.add()
            supplement_msg.bounded_array.bounds[0].origin = x * 10
            supplement_msg.bounded_array.bounds[0].size = 10

            # set data
            supplement_msg.bounded_array.ndarray.value.extend([y/10.0 for y in range(x*10, x*10+10)])

            # commit!
            supplement_msg.Repository.commit("committing round %d" % x)

            # Call the op of the ingest process directly
            yield self.ingest._ingest_op_recv_chunk(supplement_msg, '', self.fake_msg())

        updated_bounded_arrays = var.content.bounded_arrays[:]

        # should add 10 bounded arrays
        self.failUnlessEqual(len(updated_bounded_arrays), len(starting_bounded_arrays)+10)

        # should be able to iterate linearly using GetValue
        for x in xrange(100):
            self.failUnlessApproximates(x/10.0, var.GetValue(x), 0.01)  # precision may be an issue here?
            log.debug("Value %d: %f" % (x, var.GetValue(x)))
