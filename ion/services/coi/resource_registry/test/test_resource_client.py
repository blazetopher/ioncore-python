#!/usr/bin/env python

"""
@file ion/services/coi/resource_registry/test/test_resource_client.py
@author David Stuebe
@brief test service for registering resources and client classes
"""

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)
from twisted.internet import defer
from twisted.trial import unittest

from ion.core.exception import ReceivedApplicationError, ReceivedContainerError

from ion.core.process.process import Process

from ion.core.object import gpb_wrapper
from ion.core.object import workbench
from ion.core.object import object_utils

from ion.core.exception import ReceivedError

from ion.services.coi.resource_registry.resource_registry import ResourceRegistryClient, ResourceRegistryError
from ion.services.coi.resource_registry.resource_client import ResourceClient, ResourceInstance, RESOURCE_TYPE
from ion.services.coi.resource_registry.resource_client import ResourceClientError, ResourceInstanceError
from ion.test.iontest import IonTestCase
from ion.services.coi.datastore_bootstrap.ion_preload_config import ION_RESOURCE_TYPES, ION_IDENTITIES, ID_CFG, PRELOAD_CFG, ION_DATASETS_CFG, ION_DATASETS, NAME_CFG, DEFAULT_RESOURCE_TYPE_ID
from ion.services.coi.datastore_bootstrap.ion_preload_config import SAMPLE_PROFILE_DATASET_ID, ANONYMOUS_USER_ID


ADDRESSLINK_TYPE = object_utils.create_type_identifier(object_id=20003, version=1)
PERSON_TYPE = object_utils.create_type_identifier(object_id=20001, version=1)
INVALID_TYPE = object_utils.create_type_identifier(object_id=-1, version=1)
UPDATE_TYPE = object_utils.create_type_identifier(object_id=10, version=1)
INSTRUMENT_TYPE = object_utils.create_type_identifier(object_id=20024, version=1)

class ResourceClientTest(IonTestCase):
    """
    Testing service classes of resource registry
    """

    @defer.inlineCallbacks
    def setUp(self):

        yield self._start_container()
        services = [
            {'name':'ds1','module':'ion.services.coi.datastore','class':'DataStoreService',
             'spawnargs':{PRELOAD_CFG:{ION_DATASETS_CFG:True}}},
            {'name':'resource_registry1','module':'ion.services.coi.resource_registry.resource_registry','class':'ResourceRegistryService',
             'spawnargs':{'datastore_service':'datastore'}}]
        sup = yield self._spawn_processes(services)

        self.rrc = ResourceRegistryClient(proc=sup)
        self.rc = ResourceClient(proc=sup)
        self.sup = sup

    @defer.inlineCallbacks
    def tearDown(self):
        yield self._shutdown_processes()
        yield self._stop_container()


    @defer.inlineCallbacks
    def test_resource_client_in_proc_init(self):

        p = Process()
        yield p.initialize()

        rc = ResourceClient(proc=p)

        resource = yield rc.create_instance(ADDRESSLINK_TYPE, ResourceName='Test AddressLink Resource', ResourceDescription='A test resource')

        self.assertEqual(resource.ResourceName, 'Test AddressLink Resource')


    @defer.inlineCallbacks
    def test_create_resource(self):

        resource = yield self.rc.create_instance(ADDRESSLINK_TYPE, ResourceName='Test AddressLink Resource', ResourceDescription='A test resource')

        self.assertIsInstance(resource, ResourceInstance)
        self.assertEqual(resource.ResourceLifeCycleState, resource.NEW)
        self.assertEqual(resource.ResourceName, 'Test AddressLink Resource')
        self.assertEqual(resource.ResourceDescription, 'A test resource')

    @defer.inlineCallbacks
    def test_get_resource(self):

        resource = yield self.rc.create_instance(ADDRESSLINK_TYPE, ResourceName='Test AddressLink Resource', ResourceDescription='A test resource')

        res_id = resource.ResourceIdentity

        # Spawn a completely separate resource client and see if we can retrieve the resource...
        services = [
            {'name':'my_process','module':'ion.core.process.process','class':'Process'}]

        sup = yield self._spawn_processes(services)

        child_ps1 = yield self.sup.get_child_id('my_process')
        log.debug('Process ID:' + str(child_ps1))
        proc_ps1 = self._get_procinstance(child_ps1)

        my_rc = ResourceClient(proc=proc_ps1)

        my_resource = yield my_rc.get_instance(res_id)

        self.assertEqual(my_resource.ResourceName, 'Test AddressLink Resource')

    @defer.inlineCallbacks
    def test_resource_transaction(self):

        n = 6
        resource_list = []

        name_index = {}
        for i in range(n):

            name = 'Test AddressLink Resource: '
            resource = yield self.rc.create_instance(ADDRESSLINK_TYPE, ResourceName=name, ResourceDescription='A test resource')
            res_id = resource.ResourceIdentity

            resource.ResourceName = name + str(i)

            resource_list.append(resource)
            name_index[res_id] = resource.ResourceName

        yield self.rc.put_resource_transaction(resource_list)

        # Spawn a completely separate resource client and see if we can retrieve the resource...
        services = [
            {'name':'my_process','module':'ion.core.process.process','class':'Process'}]

        sup = yield self._spawn_processes(services)

        child_ps1 = yield self.sup.get_child_id('my_process')
        log.debug('Process ID:' + str(child_ps1))
        proc_ps1 = self._get_procinstance(child_ps1)

        my_rc = ResourceClient(proc=proc_ps1)

        for id, name in name_index.iteritems():

            my_resource = yield my_rc.get_instance(id)

            self.assertEqual(my_resource.ResourceName, name)



    @defer.inlineCallbacks
    def test_read_your_writes(self):

        resource = yield self.rc.create_instance(ADDRESSLINK_TYPE, ResourceName='Test AddressLink Resource', ResourceDescription='A test resource')

        self.assertEqual(resource.ResourceObjectType, ADDRESSLINK_TYPE)

        # Address link is not a real resource - so the Type ID is a default type...
        self.assertEqual(resource.ResourceTypeID.key, DEFAULT_RESOURCE_TYPE_ID)


        person = resource.CreateObject(PERSON_TYPE)
        resource.person.add()
        resource.person[0] = person

        resource.owner = person

        person.id=5
        person.name='David'

        self.assertEqual(resource.person[0].name, 'David')

        yield self.rc.put_instance(resource, 'Testing write...')

        res_id = resource.ResourceIdentity

        # Spawn a completely separate resource client and see if we can retrieve the resource...
        services = [
            {'name':'my_process','module':'ion.core.process.process','class':'Process'}]

        sup = yield self._spawn_processes(services)

        child_ps1 = yield self.sup.get_child_id('my_process')
        log.debug('Process ID:' + str(child_ps1))
        proc_ps1 = self._get_procinstance(child_ps1)

        my_rc = ResourceClient(proc=proc_ps1)

        my_resource = yield my_rc.get_instance(res_id)

        self.assertEqual(my_resource.ResourceName, 'Test AddressLink Resource')

        my_resource._repository.log_commits('master')

        self.assertEqual(my_resource.person[0].name, 'David')

        # Modify the metadata in the resource
        my_resource.person[0].name = 'Alan'
        yield my_rc.put_instance(my_resource)

        # Get the updated metadata in the original resource client
        other_resource = yield self.rc.get_instance(res_id)
        self.assertEqual(other_resource.person[0].name, 'Alan')





    @defer.inlineCallbacks
    def test_bad_branch(self):

        resource = yield self.rc.create_instance(ADDRESSLINK_TYPE, ResourceName='Test AddressLink Resource', ResourceDescription='A test resource')

        self.assertEqual(resource.ResourceObjectType, ADDRESSLINK_TYPE)


        person = resource.CreateObject(PERSON_TYPE)
        resource.person.add()
        resource.person[0] = person

        resource.owner = person

        person.id=5
        person.name='David'

        self.assertEqual(resource.person[0].name, 'David')

        yield self.rc.put_instance(resource, 'Testing write...')

        res_ref = self.rc.reference_instance(resource)

        # Spawn a completely separate resource client and see if we can retrieve the resource...
        services = [
            {'name':'my_process','module':'ion.core.process.process','class':'Process'}]

        sup = yield self._spawn_processes(services)

        child_ps1 = yield self.sup.get_child_id('my_process')
        log.debug('Process ID:' + str(child_ps1))
        proc_ps1 = self._get_procinstance(child_ps1)

        my_rc = ResourceClient(proc=proc_ps1)

        my_resource = yield my_rc.get_instance(res_ref)


        res_ref.branch = 'foobar!'
        # Fails
        yield self.failUnlessFailure(my_rc.get_instance(res_ref),ResourceClientError)



    @defer.inlineCallbacks
    def test_version_resource(self):


        # Create the resource object
        resource = yield self.rc.create_instance(ADDRESSLINK_TYPE, ResourceName='Test AddressLink Resource', ResourceDescription='A test resource')

        person = resource.CreateObject(PERSON_TYPE)

        resource.person.add()
        person.id=5
        person.name='David'

        resource.person[0] = person

        yield self.rc.put_instance(resource, 'Testing write...')

        first_version = self.rc.reference_instance(resource)

        resource.VersionResource()

        person.name = 'Paul'

        # The resource must be committed before it can be referenced
        self.assertRaises(workbench.WorkBenchError, self.rc.reference_instance, resource, current_state=True)

        yield self.rc.put_instance(resource, 'Testing version!')

        second_version = self.rc.reference_instance(resource)

        # Spawn a completely separate resource client and see if we can retrieve the resource...
        services = [
            {'name':'my_process','module':'ion.core.process.process','class':'Process'}]

        sup = yield self._spawn_processes(services)

        child_ps1 = yield self.sup.get_child_id('my_process')
        log.debug('Process ID:' + str(child_ps1))
        proc_ps1 = self._get_procinstance(child_ps1)

        my_rc = ResourceClient(proc=proc_ps1)

        my_resource_1 = yield my_rc.get_instance(first_version)

        self.assertEqual(my_resource_1.ResourceName, 'Test AddressLink Resource')

        self.assertEqual(my_resource_1.person[0].name, 'David')

        my_resource_2 = yield my_rc.get_instance(second_version)

        self.assertEqual(my_resource_2.ResourceName, 'Test AddressLink Resource')

        self.assertEqual(my_resource_2.person[0].name, 'Paul')



    @defer.inlineCallbacks
    def test_INVALID_TYPE(self):
        yield self.failUnlessFailure(self.rc.create_instance(INVALID_TYPE, ResourceName='Test AddressLink Resource', ResourceDescription='A test resource'), ResourceClientError)

    def test_get_invalid(self):

        yield self.failUnlessFailure(self.rc.get_instance('foobar'), ResourceClientError)



    @defer.inlineCallbacks
    def test_merge_update(self):

        # Create the resource object
        resource = yield self.rc.create_instance(ADDRESSLINK_TYPE, ResourceName='Test AddressLink Resource', ResourceDescription='A test resource')

        person = resource.CreateObject(PERSON_TYPE)

        resource.person.add()
        person.id=5
        person.name='David'

        resource.person[0] = person

        yield self.rc.put_instance(resource, 'Testing write...')
        # Get the branch key
        branch_key = resource.Repository._current_branch.branchkey
        cref = resource.Repository._current_branch.commitrefs[0]

        # Make sure that you the Merge method raises None when there is no merged stuff in the repository
        self.assertEqual(resource.Merge, None)

        # Create an update to merge into it...
        update_repo, ab = self.rc.workbench.init_repository(ADDRESSLINK_TYPE)

        p2 = update_repo.create_object(PERSON_TYPE)
        p2.name = 'John'
        p2.id = 5

        ab.person.add()
        ab.person[0] = p2
        ab.title = 'Revision'
        update_repo.commit('an update object')

        # Merge the update!
        yield resource.MergeResourceUpdate(resource.MERGE, ab)


        # Make sure the correct commit is at the head.
        self.assertEqual(branch_key, resource.Repository._current_branch.branchkey)
        self.assertEqual(cref, resource.Repository._current_branch.commitrefs[0])

        self.assertEqual(resource.person[0].name, 'David')

        # Try getting the merge objects resource...
        self.assertEqual(resource.Merge[0].person[0].name, 'John')

        self.assertRaises(AttributeError,setattr, resource.Merge[0], 'title', 'David')

        # Set the resource object equal to the updated addressbook
        resource.ResourceObject = resource.Merge[0].ResourceObject

        self.assertEqual(resource.person[0].name, 'John')

        yield self.rc.put_instance(resource, resource.RESOLVED)


        resource.Repository.log_commits()


    @defer.inlineCallbacks
    def test_checkout_defaults(self):

        defaults={}
        defaults.update(ION_RESOURCE_TYPES)
        defaults.update(ION_IDENTITIES)

        for key, value in defaults.items():

            resource = yield self.rc.get_instance(value[ID_CFG])
            self.assertEqual(resource.ResourceName, value[NAME_CFG])
            #print resource

    '''
    @defer.inlineCallbacks
    def test_get_associated(self):

        user_id = yield self.rc.get_instance(ANONYMOUS_USER_ID)

        associations = yield self.rc.get_associations(subject=user_id)
    '''






class ResourceInstanceTest(unittest.TestCase):
    '''
    Base clase for tests - do not actually put tests in this class!
    '''
    res_type = None

    def setUp(self):

        # Fake what the message client does to create a message
        self.wb = workbench.WorkBench('No Process')

        res_repo = self.wb.create_repository(RESOURCE_TYPE)
        res_object = res_repo.root_object
        res_object.identity = res_repo.repository_key

        res_object.resource_object = res_repo.create_object(self.res_type)

        res_repo.commit('Message object instantiated')

        self.res = ResourceInstance(res_repo)

class AddressbookMessageTest(ResourceInstanceTest):
    res_type = ADDRESSLINK_TYPE

    def test_listsetfields(self):
        """ Testing for this Method is more through in the wrapper test
        """


        self.res.title = 'foobar'

        flist = self.res.ListSetFields()
        self.assertIn('title',flist)

        self.res.owner = self.res.CreateObject(PERSON_TYPE)

        flist = self.res.ListSetFields()
        self.assertIn('title',flist)
        self.assertIn('owner',flist)

        self.res.person.add()
        self.res.person[0] = self.res.CreateObject(PERSON_TYPE)

        flist = self.res.ListSetFields()
        self.assertIn('title',flist)
        self.assertIn('owner',flist)
        self.assertIn('person',flist)

        self.assertEqual(len(flist),3)

    def test_isfieldset(self):
        """ Testing for this Method is more through in the wrapper test
        """
        self.assertEqual(self.res.IsFieldSet('title'),False)
        self.res.title = 'foobar'
        self.assertEqual(self.res.IsFieldSet('title'),True)

        self.assertEqual(self.res.IsFieldSet('owner'),False)
        self.res.owner = self.res.CreateObject(PERSON_TYPE)
        self.assertEqual(self.res.IsFieldSet('owner'),True)


        self.assertEqual(self.res.IsFieldSet('person'),False)
        self.res.person.add()
        self.assertEqual(self.res.IsFieldSet('person'),False)
        self.res.person[0] = self.res.CreateObject(PERSON_TYPE)
        self.assertEqual(self.res.IsFieldSet('person'),True)

    def test_field_props(self):
        """
        """

        self.failUnlessEqual(self.res._Properties['title'].field_type, "TYPE_STRING")
        self.failUnless(self.res._Properties['title'].field_enum is None)


    def test_str(self):
        '''
        should raise no exceptions!
        '''
        s = str(self.res)
        #print s

        self.res.Repository.purge_workspace()
        s = str(self.res)
        #print s

        self.res.Repository.purge_associations()
        s = str(self.res)
        #print s

        self.res.Repository.clear()
        s = str(self.res)
        #print s

class InstrumentMessageTest(ResourceInstanceTest):
    res_type = INSTRUMENT_TYPE

    def test_field_enum(self):
        """
        """
        print 'RTYPE',self.res_type
        print self.res._Properties
        self.failUnlessEqual(self.res._Properties['type'].field_type, "TYPE_ENUM")
        self.failIf(self.res._Properties['type'].field_enum is None)
        self.failUnless(hasattr(self.res._Properties['type'].field_enum, 'ADCP'))
        self.failUnless(self.res._Enums.has_key('InstrumentType'))
        self.failUnless(hasattr(self.res._Enums['InstrumentType'], 'ADCP'))
        self.failUnlessEqual(self.res._Enums['InstrumentType'].ADCP, 1)

