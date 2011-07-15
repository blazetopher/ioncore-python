#!/usr/bin/env python

"""
@file ion/agents/instrumentagents/test/test_NMEA0183_agent.py
@brief Test cases for the InstrumentAgent and InstrumentAgentClient classes using
 an NMEA0813 driver against a live or simulated instrument.
@author Alon Yaari
"""

from twisted.internet import defer
from ion.test.iontest import IonTestCase

import ion.util.ionlog
import ion.agents.instrumentagents.instrument_agent as instrument_agent
from ion.agents.instrumentagents.instrument_constants import AgentCommand
from ion.agents.instrumentagents.instrument_constants import AgentParameter
from ion.agents.instrumentagents.instrument_constants import AgentEvent
from ion.agents.instrumentagents.instrument_constants import AgentStatus
from ion.agents.instrumentagents.instrument_constants import AgentState
from ion.agents.instrumentagents.instrument_constants import DriverChannel
from ion.agents.instrumentagents.instrument_constants import DriverParameter
from ion.agents.instrumentagents.instrument_constants import InstErrorCode
from ion.agents.instrumentagents.instrument_constants import InstrumentCapability
from ion.agents.instrumentagents.instrument_constants import MetadataParameter
from ion.agents.instrumentagents.driver_NMEA0183 import NMEADeviceChannel
from ion.agents.instrumentagents.driver_NMEA0183 import NMEADeviceCommand
from ion.agents.instrumentagents.driver_NMEA0183 import NMEADeviceParam
from ion.agents.instrumentagents.driver_NMEA0183 import NMEADeviceMetadataParameter
from ion.agents.instrumentagents.driver_NMEA0183 import NMEADeviceStatus
import ion.agents.instrumentagents.helper_NMEA0183 as NMEA

from ion.services.dm.distribution.events import InfoLoggingEventSubscriber

from ion.agents.instrumentagents.simulators.sim_NMEA0183_preplanned \
    import NMEA0183SimPrePlanned as sim
from ion.agents.instrumentagents.simulators.sim_NMEA0183 \
    import SERPORTSLAVE, OFF, ON

log = ion.util.ionlog.getLogger(__name__)

"""
    These tests requires that a simulator (or real NMEA GPS device!) is attached to:
            /dev/slave
"""

class TestNMEA0183Agent (IonTestCase):

    # Increase the timeout so we can handle longer instrument interactions.
    timeout = 10


    @defer.inlineCallbacks
    def setUp (self):

        log.info("TestNMEA0183Agent.setUp")
        
        self._sim = sim()
        yield self._sim.SetupSimulator()

        if self._sim.IsSimOK():
            log.info ('----- Simulator launched.')
        self.assertEqual (self._sim.IsSimulatorRunning(), 1)
        
        yield self._start_container()

        log.debug("*** started container")
        # Driver and agent configuration. Configuration data will ultimately be accessed via
        # some persistence mechanism: platform filesystem or a device registry.
        # For now, we pass all configuration data that would be read this way as process arguments.
        device_port             = SERPORTSLAVE
        device_baud             = 19200
        device_bytesize         = 8
        device_parity           = 'N'
        device_stopbits         = 1
        device_timeout          = 0
        device_xonxoff          = 0
        device_rtscts           = 0

        driver_config       = { 'port':         device_port,
                                'baudrate':     device_baud,
                                'bytesize':     device_bytesize,
                                'parity':       device_parity,
                                'stopbits':     device_stopbits,
                                'timeout':      device_timeout,
                                'xonxoff':      device_xonxoff,
                                'rtscts':       device_rtscts }
        agent_config        = {}
        
        # Process description for the instrument driver.
        driver_desc         = { 'name':         'NMEA0183_Driver',
                                'module':       'ion.agents.instrumentagents.driver_NMEA0183',
                                'class':        'NMEADeviceDriver',
                                'spawnargs':  { 'config': driver_config } }

        # Process description for the instrument driver client.
        driver_client_desc  = { 'name':         'NMEA0813_Client',
                                'module':       'ion.agents.instrumentagents.driver_NMEA0183',
                                'class':        'NMEADeviceDriverClient',
                                'spawnargs':    {} }

        # Spawnargs for the instrument agent.
        spawnargs           = { 'driver-desc':  driver_desc,
                                'client-desc':  driver_client_desc,
                                'driver-config':driver_config,
                                'agent-config': agent_config }

        # Process description for the instrument agent.
        agent_desc          = { 'name':         'instrument_agent',
                                'module':       'ion.agents.instrumentagents.instrument_agent',
                                'class':        'InstrumentAgent',
                                'spawnargs':    spawnargs }

        # Processes for the tests.
        processes           = [ agent_desc ]
        
        # Spawn agent and driver, create agent client.
        self.sup            = yield self._spawn_processes (processes)
        self.svc_id         = yield self.sup.get_child_id ('instrument_agent')
        self.ia_client      = instrument_agent.InstrumentAgentClient (proc = self.sup, target = self.svc_id)


    @defer.inlineCallbacks
    def tearDown (self):
        log.info("TestNMEA0183Agent.tearDown")

        yield self._sim.StopSimulator()
        yield self._stop_container()


    @defer.inlineCallbacks
    def test_state_transitions (self):
        """
        Test cases for executing device commands through the instrument agent.
        """
        # Check agent state upon creation. No transaction needed for get operation.
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status (params)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok (success))
        self.assert_(agent_state == AgentState.UNINITIALIZED)

        # Check that the driver and client descriptions were set by spawnargs, and save them for later restore.

        # Begin an explicit transaciton.
        reply = yield self.ia_client.start_transaction()
        success = reply['success']
        tid = reply['transaction_id']
        self.assert_(InstErrorCode.is_ok (success))
        self.assertEqual(type (tid), str)
        self.assertEqual(len (tid), 36)

        # Initialize with a bad client desc. value.
        # This should fail and leave us in the uninitialized state with null driver and client.

        # Restore the good process and client desc. values.

        # Initialize the agent to bring up the driver and client.
        cmd = [AgentCommand.TRANSITION, AgentEvent.INITIALIZE]
        reply = yield self.ia_client.execute_observatory (cmd, tid)
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok (success))

        # Check agent state.
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status (params, tid)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok (success))
        self.assert_(agent_state == AgentState.INACTIVE)

        # Connect to the driver.
        cmd = [AgentCommand.TRANSITION,AgentEvent.GO_ACTIVE]
        reply = yield self.ia_client.execute_observatory (cmd, tid)
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok (success))

        # Check agent state.
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status (params, tid)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok (success))
        self.assert_(agent_state == AgentState.IDLE)
        
        # Enter observatory mode.
        cmd = [AgentCommand.TRANSITION, AgentEvent.RUN]
        reply = yield self.ia_client.execute_observatory (cmd, tid)
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok (success))
    
        # Check agent state.
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status (params, tid)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok (success))
        self.assert_(agent_state == AgentState.OBSERVATORY_MODE)
        
        """
        # Discnnect from the driver.
        cmd = [AgentCommand.TRANSITION,AgentEvent.GO_INACTIVE]
        reply = yield self.ia_client.execute_observatory(cmd,tid) 
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok(success))
        
        # Check agent state.
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status(params,tid)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok(success))        
        self.assert_(agent_state == AgentState.INACTIVE)
        """
        
        # Reset the agent to disconnect and bring down the driver and client.
        cmd = [AgentCommand.TRANSITION, AgentEvent.RESET]
        reply = yield self.ia_client.execute_observatory (cmd, tid)
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok (success))

        # Check agent state.
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status (params, tid)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok (success))
        self.assert_(agent_state == AgentState.UNINITIALIZED)

        # End the transaction.
        reply = yield self.ia_client.end_transaction (tid)
        success = reply['success']
        self.assert_(InstErrorCode.is_ok (success))
        
        
    @defer.inlineCallbacks
    def test_execute_instrument (self):
        """
        Test cases for exectuing device commands through the instrument agent.
        """
        log.info("TestNMEA0183Agent.test_execute_instrument\n")

        # Check agent state upon creation. No transaction needed for get operation.
        log.debug('+++++ Check agent state upon creation.')
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status(params)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok(success))        
        self.assert_(agent_state == AgentState.UNINITIALIZED)

        # Begin an explicit transaciton.
        log.debug('+++++ Begin an explicit transaciton.')
        reply = yield self.ia_client.start_transaction(0)
        success = reply['success']
        tid = reply['transaction_id']
        self.assert_(InstErrorCode.is_ok(success))
        self.assertEqual(type(tid),str)
        self.assertEqual(len(tid),36)
        
        # Initialize the agent to bring up the driver and client.
        log.debug('+++++ Initialize the agent to bring up the driver and client.')
        cmd = [AgentCommand.TRANSITION,AgentEvent.INITIALIZE]
        reply = yield self.ia_client.execute_observatory(cmd,tid) 
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok(success))

        # Check agent state.
        log.debug('+++++ Check agent state.')
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status(params,tid)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok(success))        
        self.assert_(agent_state == AgentState.INACTIVE)

        # Connect to the driver.
        log.debug('+++++ Connect to the driver.')
        cmd = [AgentCommand.TRANSITION,AgentEvent.GO_ACTIVE]
        reply = yield self.ia_client.execute_observatory(cmd,tid) 
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok(success))

        # Check agent state.
        log.debug('+++++ Check agent state.')
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status(params,tid)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok(success))        
        self.assert_(agent_state == AgentState.IDLE)
        
        # Enter observatory mode.
        log.debug('+++++ Enter observatory mode.')
        cmd = [AgentCommand.TRANSITION,AgentEvent.RUN]
        reply = yield self.ia_client.execute_observatory(cmd,tid) 
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok(success))        
    
        # Check agent state.
        log.debug('+++++ Check agent state.')
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status(params,tid)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok(success))        
        self.assert_(agent_state == AgentState.OBSERVATORY_MODE)
        
        # Get driver parameters.
        log.debug('+++++ Get driver parameters.')
        params = [(DriverChannel.ALL,DriverParameter.ALL)]
        reply = yield self.ia_client.get_device(params,tid)
        success = reply['success']
        result = reply['result']

        # Strip off individual success vals to create a set params to
        # restore original config later.
        # orig_config = dict(map(lambda x : (x[0],x[1][1]),result.items()))

        self.assert_(InstErrorCode.is_ok(success))

        # Set a few parameters. This will test the device set functions
        # and set up the driver for sampling commands.
        log.debug('+++++ Set a few parameters.')
        chan = DriverChannel.GPS
        params = {}
        params[(chan, 'GPGGA')] = ON
        params[(chan, 'GPGLL')] = OFF
        params[(chan, 'GPRMC')] = OFF
        params[(chan, 'PGRMF')] = OFF
        params[(chan, 'ALT_MSL')] = 7.7
        params[(chan, 'DED_REC')] = 11
        
        reply = yield self.ia_client.set_device(params,tid)
        success = reply['success']
        result = reply['result']
        setparams = params
        self.assert_(InstErrorCode.is_ok(success))

        # Verify the set changes were made.
        log.debug('+++++ Verify the set changes were made.')
        params = [(DriverChannel.ALL,DriverParameter.ALL)]
        reply = yield self.ia_client.get_device(params, tid)
        success = reply['success']
        result = reply['result']

        self.assert_(InstErrorCode.is_ok(success))
        self.assertEqual(setparams[(chan, 'GPGGA')], result[(chan, 'GPGGA')][1])
        self.assertEqual(setparams[(chan, 'GPGLL')], result[(chan, 'GPGLL')][1])
        self.assertEqual(setparams[(chan, 'GPRMC')], result[(chan, 'GPRMC')][1])
        self.assertEqual(setparams[(chan, 'PGRMF')], result[(chan, 'PGRMF')][1])
        self.assertEqual(setparams[(chan, 'ALT_MSL')], result[(chan, 'ALT_MSL')][1])
        self.assertEqual(setparams[(chan, 'DED_REC')], result[(chan, 'DED_REC')][1])
        
        
        # Reset the agent to disconnect and bring down the driver and client.
        log.debug('+++++ Disconnect from serial port')
        cmd = [AgentCommand.TRANSITION, AgentEvent.RESET]
        reply = yield self.ia_client.execute_observatory (cmd, tid)
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok (success))
        """ TODO Needs more work!
        
        # Acquire sample.
        log.debug('+++++ Acquire sample.')
        chans = [DriverChannel.GPS]
        cmd = [DriverCommand.ACQUIRE_SAMPLE]
        reply = yield self.ia_client.execute_device(chans,cmd,tid)
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok(success))
        self.assertIsInstance(result[0].get('GPS_LAT', None), float)
        self.assertIsInstance(result[0].get('GPS_LON', None), float)
        self.assertIsInstance(result[0].get('NMEA_CD', None), str)
        
        # Start autosampling.
        log.debug('+++++ Start autosampling.')
        chans = [DriverChannel.GPS]
        cmd = [DriverCommand.START_AUTO_SAMPLING]
        reply = yield self.ia_client.execute_device(chans,cmd,tid)
        success = reply['success']
        result = reply['result']
        
        self.assert_(InstErrorCode.is_ok(success))
        
        # Wait for a few samples to arrive.
        #log.debug('+++++ Wait for a few samples to arrive.')
        #yield pu.asleep(3)
        
        # Stop autosampling.
        log.debug('+++++ Stop autosampling.')
        chans = [DriverChannel.GPS]
        cmd = [DriverCommand.STOP_AUTO_SAMPLING,'GETDATA']
        while True:
            reply = yield self.ia_client.execute_device(chans,cmd,tid)
            success = reply['success']
            result = reply['result']
            
            if InstErrorCode.is_ok(success):
                break

            elif InstErrorCode.is_equal(success,InstErrorCode.TIMEOUT):
                pass
            
            else:
                self.fail('Stop autosample failed with error: '+str(success))
        
        self.assert_(InstErrorCode.is_ok(success))
        log.debug('+++++ type: %s  %s' % (type(result), result))
        
        # Restore original configuration.
        log.debug('+++++ Restore original configuration.')
        reply = yield self.ia_client.set_device(orig_config,tid)
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok(success))
        """

    def test_NMEAParser (self):
        """
        Verify NMEA parsing routines.
        """
        # Verify parsing of known VALID GPGGA string
        log.debug('+++++ Verify parsing of known VALID GPGGA string')
        testNMEA = '$GPGGA,051950.00,3532.2080,N,12348.0348,W,1,09,07.9,0005.9,M,0042.9,M,0.0,0000*52'
        parseNMEA = NMEA.NMEAString (testNMEA)
        self.assertTrue (parseNMEA.IsValid())

        # Verify parsing of known INVALID GPGGA string (has bad checksum)
        log.debug('+++++ Verify parsing of known INVALID GPGGA string (has bad checksum)')
        testNMEA = '$GPGGA,051950.00,3532.2080,N,12348.0348,W,1,09,07.9,0005.9,M,0042.9,M,0.0,0000*F2'
        parseNMEA = NMEA.NMEAString (testNMEA)
        self.assertTrue (parseNMEA.IsValid())

        # Verify parsing of known VALID dummy string
        log.debug('+++++ Verify parsing of known VALID dummy string')
        testNMEA = '$XXXXX,0'
        parseNMEA = NMEA.NMEAString (testNMEA)
        self.assertTrue (parseNMEA.IsValid())

        # Verify line endings: <LF>, <CR>, <CR><LF>, and <LF><CR>
        log.debug('+++++ Verify line endings: <LF>, <CR>, <CR><LF>, and <LF><CR>')
        testNMEA = '$XXXXX,0\r'
        parseNMEA = NMEA.NMEAString (testNMEA)
        self.assertTrue (parseNMEA.IsValid())
        testNMEA = '$XXXXX,0\n'
        parseNMEA = NMEA.NMEAString (testNMEA)
        self.assertTrue (parseNMEA.IsValid())
        testNMEA = '$XXXXX,0\r\n'
        parseNMEA = NMEA.NMEAString (testNMEA)
        self.assertTrue (parseNMEA.IsValid())
        testNMEA = '$XXXXX,0\n\r'
        parseNMEA = NMEA.NMEAString (testNMEA)
        self.assertTrue (parseNMEA.IsValid())

        # Verify parsing of known VALID GPRMC string with checksum
        log.debug('+++++ Verify parsing of known VALID GPRMC string with checksum')
        testNMEA = '$GPRMC,225446,A,4916.45,N,12311.12,W,000.5,054.7,191194,020.3,E*68'
        parseNMEA = NMEA.NMEAString (testNMEA)
        self.assertTrue (parseNMEA.IsValid())

        # Verify parsing of known VALID GPRMC string without checksum
        log.debug('+++++ Verify parsing of known VALID GPRMC string without checksum')
        testNMEA = '$GPRMC,225446,A,4916.45,N,12311.12,W,000.5,054.7,191194,020.3,E'
        parseNMEA = NMEA.NMEAString (testNMEA)
        self.assertTrue (parseNMEA.IsValid())

        # Verify parsing of known INVALID GPRMC (not enough fields)
        log.debug('+++++ Verify parsing of known INVALID GPRMC (not enough fields)')
        testNMEA = '$GPRMC,225446,A,4916.45,N,12311.12,W,000.5'
        parseNMEA = NMEA.NMEAString (testNMEA)
        self.assertTrue (parseNMEA.IsValid())

        # Verify reporting of status (PGRMC command)
        log.debug('+++++ Verify reporting of status (PGRMC command)')
        testNMEA = '$PGRMC'
        parseNMEA = NMEA.NMEAString (testNMEA)
        self.assertTrue (parseNMEA.IsValid())

        log.debug ('test_NMEAParser complete')

    @defer.inlineCallbacks
    def test_get_capabilities(self):
        """
        Test cases for querying the device and observatory capabilities.
        """

        log.debug("+++++ TestNMEA0183Agent.test_get_capabilities")

        # Check agent state upon creation. No transaction needed for
        # get operation.
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status(params)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok(success))        
        self.assert_(agent_state == AgentState.UNINITIALIZED)

        # Begin an explicit transaciton.
        reply = yield self.ia_client.start_transaction(0)
        success = reply['success']
        tid = reply['transaction_id']
        self.assert_(InstErrorCode.is_ok(success))
        self.assertEqual(type(tid),str)
        self.assertEqual(len(tid),36)
        
        # Initialize the agent to bring up the driver and client.
        cmd = [AgentCommand.TRANSITION,AgentEvent.INITIALIZE]
        reply = yield self.ia_client.execute_observatory(cmd,tid) 
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok(success))

        # Check agent state.
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status(params,tid)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok(success))        
        self.assert_(agent_state == AgentState.INACTIVE)

        #
        params = [InstrumentCapability.ALL]
        reply = yield self.ia_client.get_capabilities(params,tid)
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok(success))
        
        self.assertEqual (list (result[InstrumentCapability.DEVICE_CHANNELS][1]).sort(), NMEADeviceChannel.list().sort())
        self.assertEqual (list (result[InstrumentCapability.DEVICE_COMMANDS][1]).sort(), NMEADeviceCommand.list().sort())
        self.assertEqual (list (result[InstrumentCapability.DEVICE_METADATA][1]).sort(), NMEADeviceMetadataParameter.list().sort())
        self.assertEqual (list (result[InstrumentCapability.DEVICE_PARAMS][1]).sort(),   NMEADeviceParam.list().sort())
        self.assertEqual (list (result[InstrumentCapability.DEVICE_STATUSES][1]).sort(), NMEADeviceStatus.list().sort())
        self.assertEqual (list (result[InstrumentCapability.OBSERVATORY_COMMANDS][1]).sort(), AgentCommand.list().sort())
        self.assertEqual (list (result[InstrumentCapability.OBSERVATORY_METADATA][1]).sort(), MetadataParameter.list().sort())
        self.assertEqual (list (result[InstrumentCapability.OBSERVATORY_PARAMS][1]).sort(), AgentParameter.list().sort())
        self.assertEqual (list (result[InstrumentCapability.OBSERVATORY_STATUSES][1]).sort(), AgentStatus.list().sort())

        # Reset the agent to disconnect and bring down the driver and client.
        cmd = [AgentCommand.TRANSITION,AgentEvent.RESET]
        reply = yield self.ia_client.execute_observatory(cmd,tid)
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok(success))

        # Check agent state.
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status(params,tid)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok(success))        
        self.assert_(agent_state == AgentState.UNINITIALIZED)        

        # End the transaction.
        reply = yield self.ia_client.end_transaction(tid)
        success = reply['success']
        self.assert_(InstErrorCode.is_ok(success))

    @defer.inlineCallbacks
    def test_publish_data (self):
        """
        Test cases for executing device commands through the instrument agent.
        """
        log.debug("*** starting test_publish_data")
        # Setup a subscriber to an event topic
        class TestEventSubscriber(InfoLoggingEventSubscriber):
            def __init__(self, *args, **kwargs):
                self.msgs = []
                InfoLoggingEventSubscriber.__init__(self, *args, **kwargs)
                
            def ondata(self, data):
                log.debug("TestEventSubscriber received a message with name: %s",
                          data['content'].name)
                self.msgs.append(data)
                
        log.debug("*** creating subproc of subscriber")    
        subproc = Process()
        yield subproc.spawn()
        testsub = TestEventSubscriber(origin=('agent.' + str(self.svc_id)),
                                      process=subproc)
        log.debug("*** found it")
        yield testsub.initialize()
        yield testsub.activate()
        
        # Check agent state upon creation. No transaction needed for get operation.
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status (params)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok (success))
        self.assert_(agent_state == AgentState.UNINITIALIZED)

        # Check that the driver and client descriptions were set by spawnargs, and save them for later restore.

        # Begin an explicit transaciton.
        reply = yield self.ia_client.start_transaction()
        success = reply['success']
        tid = reply['transaction_id']
        self.assert_(InstErrorCode.is_ok (success))
        self.assertEqual(type (tid), str)
        self.assertEqual(len (tid), 36)

        # Initialize the agent to bring up the driver and client.
        cmd = [AgentCommand.TRANSITION, AgentEvent.INITIALIZE]
        reply = yield self.ia_client.execute_observatory (cmd, tid)
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok (success))

        # Check agent state.
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status (params, tid)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok (success))
        self.assert_(agent_state == AgentState.INACTIVE)

        # Connect to the driver.
        cmd = [AgentCommand.TRANSITION,AgentEvent.GO_ACTIVE]
        reply = yield self.ia_client.execute_observatory (cmd, tid)
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok (success))

        # Check agent state.
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status (params, tid)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok (success))
        self.assert_(agent_state == AgentState.IDLE)
        
        # Enter observatory mode.
        cmd = [AgentCommand.TRANSITION, AgentEvent.RUN]
        reply = yield self.ia_client.execute_observatory (cmd, tid)
        success = reply['success']
        result = reply['result']
        self.assert_(InstErrorCode.is_ok (success))
    
        # Check agent state.
        params = [AgentStatus.AGENT_STATE]
        reply = yield self.ia_client.get_observatory_status (params, tid)
        success = reply['success']
        result = reply['result']
        agent_state = result[AgentStatus.AGENT_STATE][1]
        self.assert_(InstErrorCode.is_ok (success))
        self.assert_(agent_state == AgentState.OBSERVATORY_MODE)
    
        # check for a publish event
        yield pu.asleep(2.0)
        self.assertEqual(len(testsub.msgs), 2)
        
        # End the transaction.
        reply = yield self.ia_client.end_transaction (tid)
        success = reply['success']
        self.assert_(InstErrorCode.is_ok (success))
        
