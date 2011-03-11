#!/usr/bin/env python

"""
@file ion/agents/instrumentagents/instrument_agent.py
@author Steve Foley
@brief Instrument Agent, Driver, and Client class definitions
"""
import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)

from twisted.internet import defer

from ion.agents.resource_agent import ResourceAgent
from ion.agents.resource_agent import ResourceAgentClient
from ion.agents.instrumentagents.phrase import Phrase, GetPhrase, SetPhrase, ExecutePhrase
from ion.agents.instrumentagents.phrase import GetAction, SetAction, ExecuteAction
from ion.core.exception import ReceivedError
from ion.services.dm.distribution.pubsub_service import PubSubClient
from ion.data.dataobject import ResourceReference, DataObject
from ion.core.process.process import Process, ProcessClient
from ion.resources.ipaa_resource_descriptions import InstrumentAgentResourceInstance
from ion.resources.dm_resource_descriptions import PublisherResource
from uuid import uuid4


"""
Constants/Enumerations for tags in capabilities dict structures.
"""
ci_commands                     = 'ci_commands'
ci_parameters                   = 'ci_parameters'
instrument_commands             = 'instrument_commands'
instrument_parameters           = 'instrument_parameters'

"""
CI parameter key constant.
"""
driver_address = 'DriverAddress'

"""
Parameter names for all instrument agents.
"""
ci_param_list = {
    'DataTopics'                :'DataTopics',
    'EventTopics'               :'EventTopics',
    'StateTopics'               :'StateTopics',
    'DriverAddress'             :'DriverAddress',
    'ResourceID'                :'ResourceID',
    #'DataCorrectionMode'        : 'DataCorrectionMode',
    'TimeSource'                : 'TimeSource',
    'ConnectionMethod'          : 'ConnectionMethod',
    'DefaultTransactionTimeout' : 'DefaultTransactionTimeout',
    'MaxTransactionTimeout'     : 'MaxTransactionTimeout',
    'TransactionExpireTimeout'  : 'TransactionExpireTimeout'
}

"""
Publish message types.
"""
publish_msg_type = {
    'Error'                     :'Error',
    'StateChange'               :'StateChange',
    'ConfigChange'              :'ConfigChange',
    'Data'                      :'Data',
    'Event'                     :'Event'
}

"""
Agent errors.
"""
errors = {
    'InvalidDestnation'     : ['ERROR','InvalidDestination','Intended destination for a message or operation is not valid.'],
    'Timeout'	            : ['ERROR','Timeout','The message or operation timed out.'],
    'NetworkFailure'        : ['ERROR','NetworkFailure','A network failure has been detected.'],
    'NetworkCorruption'     : ['ERROR','NetworkCorruption','A message passing through the network has been determined to be corrupt.'],
    'OutofMemory'	    : ['ERROR','OutofMemory','There is no more free memory to complete the operation.'],
    'LockedResource'	    : ['ERROR','LockedResource','The resource being accessed is in use by another exclusive operation.'],
    'ResourceUnavailable'   : ['ERROR','ResourceUnavailable','The resource being accessed is unavailable.'],
    'UnknownError'          : ['ERROR','UnknownError','An unknown error has been encountered.'],
    'PermissionError'       : ['ERROR','PermissionError','The user does not have the correct permission to access the resource in the desired way.'],
    'InvalidTransition'     : ['ERROR','InvalidTransition','The transition being requested does not apply for the current state.'],
    'IncorrectState'        : ['ERROR','IncorrectState','The operation being requested does not apply to the current state.'],
    'CannotPublish'	    : ['ERROR','CannotPublish','An attempt to publish has failed.'],
    'InstrumentUnreachable' : ['ERROR','InstrumentUnreachable','The agent cannot communicate with the device.'],
    'MessagingError'        : ['ERROR','MessagingError','An error has been encountered during a messaging operation.'],
    'HardwareError'         : ['ERROR','HardwareError','An error has been encountered with a hardware element.'],
    'PhrasePending'         : ['ERROR','PhrasePending','A phrase is currently pending.'],
    'WrongType'             : ['ERROR','WrongType','The type of operation is not valid in the current state.'],
    'InvalidCommand'        : ['ERROR','InvalidCommand','The command is not valid in the given context.'],    
    'UnknownCommand'        : ['ERROR','UnknownCommand','The command is not recognized.'],
    'NotImplemented'        : ['ERROR','NotImplemented','The command is not implemented.'],
    'InvalidTransactionID'  : ['ERROR','InvalidTransactionID','The transaction ID is not a valid value.']
}


class InstrumentDriver(Process):
    """
    A base driver class. This is intended to provide the common parts of
    the interface that instrument drivers should follow in order to use
    common InstrumentAgent methods. This should never really be instantiated.
    """
    def op_fetch_params(self, content, headers, msg):
        """
        Using the instrument protocol, fetch a parameter from the instrument
        @param content A list of parameters to fetch
        @retval A dictionary with the parameter and value of the requested
            parameter
        """

    def op_set_params(self, content, headers, msg):
        """
        Using the instrument protocol, set a parameter on the instrument
        @param content A dictionary with the parameters and values to set
        @retval A small dict of parameter and value on success, empty dict on
            failure
        """

    def op_execute(self, content, headers, msg):
        """
        Using the instrument protocol, execute the requested command
        @param command A list where the command name is the
            first item in the sub-list, and the arguments are the rest of
            the items in the sublists. For example:
            ['command1', 'arg1', 'arg2']
        @retval Result code of some sort
        """

    def op_configure_driver(self, content, headers, msg):
        """
        This method takes a dict of settings that the driver understands as
        configuration of the driver itself (ie 'target_ip', 'port', etc.). This
        is the bootstrap information for the driver and includes enough
        information for the driver to start communicating with the instrument.
        @param content A dict with parameters for the driver
        """

    def op_disconnect(self, content, headers, msg):
        """
        Disconnect from the instrument
        @param none
        """

class InstrumentDriverClient(ProcessClient):
    """
    The base class for the instrument driver client interface. This interface
    is designed to be used by the instrument agent to work with the driver.
    """

    @defer.inlineCallbacks
    def fetch_params(self, param_list):
        """
        Using the instrument protocol, fetch a parameter from the instrument
        @param param_list A list or tuple of parameters to fetch
        @retval A dictionary with the parameter and value of the requested
            parameter
        """
        assert(isinstance(param_list, (list, tuple)))
        (content, headers, message) = yield self.rpc_send('fetch_params',
                                                          param_list)
        assert(isinstance(content, dict))
        defer.returnValue(content)

    @defer.inlineCallbacks
    def set_params(self, param_dict):
        """
        Using the instrument protocol, set a parameter on the instrument
        @param param_dict A dictionary with the parameters and values to set
        @retval A small dict of parameter and value on success, empty dict on
            failure
        """
        assert(isinstance(param_dict, dict))
        (content, headers, message) = yield self.rpc_send('set_params',
                                                          param_dict)
        assert(isinstance(content, dict))
        defer.returnValue(content)

    @defer.inlineCallbacks
    def execute(self, command):
        """
        Using the instrument protocol, execute the requested command
        @param command An ordered list of lists where the command name is the
            first item in the sub-list, and the arguments are the rest of
            the items in the sublists. For example:
            ['command1', 'arg1', 'arg2']
        @retval Result code of some sort
        """
        log.debug("Driver client executing command: %s", command)
        assert(isinstance(command, (list, tuple))), "Bad Driver client execute type"
        (content, headers, message) = yield self.rpc_send('execute',
                                                          command)
        defer.returnValue(content)

    @defer.inlineCallbacks
    def get_status(self, arg):
        """
        Using the instrument protocol, gather status from the instrument
        @param arg The argument needed for gathering status
        @retval Result message of some sort
        """
        (content, headers, message) = yield self.rpc_send('get_status', arg)
        defer.returnValue(content)

    @defer.inlineCallbacks
    def configure_driver(self, config_vals):
        """
        This method takes a dict of settings that the driver understands as
        configuration of the driver itself (ie 'target_ip', 'port', etc.). This
        is the bootstrap information for the driver and includes enough
        information for the driver to start communicating with the instrument.
        @param config_vals A dict with parameters for the driver
        """
        assert(isinstance(config_vals, dict))
        (content, headers, message) = yield self.rpc_send('configure_driver',
                                                          config_vals)
        defer.returnValue(content)

    @defer.inlineCallbacks
    def initialize(self, arg):
        """
        Disconnect from the instrument
        @param none
        @retval Result code of some sort
        """
        #assert(isinstance(command, dict))
        log.debug("DHE: in initialize!")
        (content, headers, message) = yield self.rpc_send('initialize',
                                                          arg)
        defer.returnValue(content)

    @defer.inlineCallbacks
    def disconnect(self, command):
        """
        Disconnect from the instrument
        @param none
        @retval Result code of some sort
        """
        #assert(isinstance(command, dict))
        log.debug("DHE: in IDC disconnect!")
        (content, headers, message) = yield self.rpc_send('disconnect',
                                                          command)
        defer.returnValue(content)

class InstrumentAgent(ResourceAgent):
    """
    The base class for developing Instrument Agents. This defines
    the interface to use for an instrument agent and some boiler plate
    function implementations that may be good enough for most agents.
    Child instrument agents should supply instrument-specific routines such as
    getCapabilities.
    """
    
    """
    The driver client to communicate with the child driver
    """
    driver_client = None
    
    """
    A dictionary of the topics where data is published, indexed by transducer
    name or "Device" for the whole device. Gets set initially by
    subclass, then at runtime by user as needed.
    """
    output_topics = None

    """
    A dictionary of the topics where events are published, indexed by
    transducer name or "Device" for the whole device. Gets set initially by
    subclass, then at runtime by user as needed.
    """
    event_topics = None

    """
    A dictionary of the topics where state changes are published, indexed by
    transducer name or "Device" for the whole device. Gets set initially by
    subclass, then at runtime by user as needed.
    """
    state_topics = None

    """
    A UUID specifying the current transaction. None
    indicates no current transaction.
    """
    transaction_id = None
    
    """
    An integer in seconds for how long to wait to acquire a new transaction.
    """
    default_transaction_timeout = 10   
    
    """
    An integer in seconds for the maximum allowable timeout to wait for a new transaction.
    """
    max_transaction_timeout = 120

    """
    An integer in seconds for the maximum time a transaction may be open.
    """
    transaction_expire_timeout = 300

    """
    A finite state machine to track and manage agent state according to the general
    instrument state model.
    """
    agent_fsm = None

    """
    String indicating the source of time being used for the instrument.
    'PTPDirect'             - IEEE 1588 PTP connection directly supported by the instrument
    'NTPUnicast'            - NTP unicast to the instrument
    'LocalOscillator'       - NTP broadcast to the instrument
    'LocalOscillator'       - The device has its own clock
    'DriverSetInterval'     - Driver sets the clock at an interval
    """
    TimeSource = None

    """
    String describing how the device is connected to the observatory.
    'Offline'               - Device is offline.
    'CabledObservatory'     - Accessible through cabled, full time observatory.
    'ShortNetwork'          - Accessible through full time shore connection.
    'PartTimeScheduled'     - Comes online on scheduled basis. Outages normal.
    'PartTimeRandom'        - Comes online as needed. Outages normal.
    """
    ConnectionMethod = None
    
    
    def plc_init(self):
        ResourceAgent.plc_init(self)
        self.pubsub_client = PubSubClient(proc=self)
        
    @defer.inlineCallbacks
    def _register_publisher(self):
        publisher = PublisherResource.create("IA publisher", self,
            self.output_topics.values() + self.event_topics.values() + self.state_topics.values(),
            'DataObject')
        publisher = yield self.pubsub_client.define_publisher(publisher)

    def _is_child_process(self, name):
        """
        Determine if a process with the given name is a child process
        @param name The name to test for subprocess-ness
        @retval True if the name matches a child process name, False otherwise
        """
        log.debug("__is_child_process looking for process '%s' in %s",
                  name, self.child_procs)
        found = False
        for proc in self.child_procs:
            if proc.proc_name == name:
                found = True
                break
        return found



    ############################################################################
    #   Transaction Management
    ############################################################################


    @defer.inlineCallbacks
    def op_start_transaction(self,content,headers,msg):
        """
        Begin an exclusive transaction with the agent.
        @param content An integer specifying the time to wait in seconds for the
            transaction.
        @retval Transaction ID UUID string.
        """
        
        result = yield self._start_transaction(timeout)                
        yield self.reply_ok(msg,result)
        
    
    def _start_transaction(timeout):
        """
        Begin an exclusive transaction with the agent.
        @param timeout An integer specifying time to wait in seconds for the transaction.
        @retval Transaction ID UUID string.
        """
        
        assert(isinstance(timeout,int)), 'Expected an integer timeout.'
        
        if timeout < 0:
            timeout = default_transaction_timeout
        
        if timeout > max_transaction_timeout:
            timeout = max_transaction_timeout
            
        if timeout == 0:
            if transaction_id == '':
                transaction_id = uuid4()
                return ['OK',transaction_id]
            else:
                return errors['LockedResource']
        
        #todo add the timeout callback code here
        
        
    
    @defer.inlineCallbacks
    def op_end_transaction(tid):
        """
        End the current transaction.
        @param tid A uuid specifying the current transaction to end.
        """        
        
        result = _end_transaction(tid)
        yield self.reply_ok(result)
                
    

    @defer.inlineCallbacks
    def _end_transaction(tid):
        """
        End the current transaction.
        @param tid A uuid specifying the current transaction to end.
        """        
        
        if tid == transaction_id:
            transaction_id = None
            self.reply_ok(['OK'])
        else:
            self.reply_ok(errors['LockedResource'])
            
        

    
    def _verify_transaction(tid,optype):
        """
        Verify the passed transaction ID is currently open, or open an implicit transaction.
        @param tid 'create' to create an implicit transaction, 'none' to perform the operation without
            a transaction, or a UUID to test against the current transaction ID.
        @param optype 'get' 'set' or 'execute'
        @retval True if the transaction is valid or if one was successfully created, False otherwise.
        """

        assert(isinstance(tid,(str,uuid4))), 'Expected uuid4 or str transaction ID.'
        assert(isinstance(optype,str,uuid4)), 'Expected str optype.'


        # Try to start an implicit transaction if tid is 'create'
        if tid == 'create':
            result = self._start_transaction(default_transaction_timeout)
            if result[0]=='OK':
                return True
            else:
                return False
        
        # Allow only gets without a current or created transaction.
        if tid == 'none' and transaction_id == None and optype == 'get':
            return true
        
        # Otherwise, the given ID must match the outstanding one
        if tid == transaction_id:
            return True
        
        return False
    
    
    ############################################################################
    #   Observatory Facing Interface
    ############################################################################
    


    @defer.inlineCallbacks
    def op_execute_observatory(self, content, headers, msg):
        """
        Execute infrastructure commands related to the Instrument Agent
        instance. This includes commands for messaging, resource management
        processes, etc.
        @param content A dict {'command':[command,arg, ,arg],'transaction_id':transaction_id)}
        @retval ACK message containing a dict
            {'success':success,'result':command-specific,'transaction_id':transaction_id}.
        """
        
        assert(isinstance(content,dict)), 'Expected a dict content.'
        assert(content.has_key('command')), 'Expected a command.'
        assert(content.has_key('transaction_id')), 'Expected a transaction_id.'
        
        cmd = content['command']
        tid = content['transaction_id']

        assert(isinstance(cmd,list)), 'Expected a command list.'
        assert(isinstance(tid,(uuid4,str))), 'Expected a transaction_id str or uuid4.'
    
        if isinstance(tid,str):
            if tid != 'create' and tid != 'none':
                yield self.reply_ok(errors['InvalidTransactionID'])
                return


        # Set up the transaction
        result = yield self._verify_transaction(tid,'get')
        if not result:
            result = errors['LockedResource']
            yield self.reply_ok(msg,result)
            return
                    
        if  cmd[0] == 'StateTransition':
            result = self.agent_fsm.state_transition(cmd[1])
            result = (result,transaction_id)
        elif cmd[0] == 'TransmitData':
            result = errors['NotImplemented']            
        else:
            result = errors['UnknownCommand']
        
        # End implicit transactions.
        if tid == 'create':
            end_transaction(transaction_id)
        
        yield self.reply_ok(msg,result)
            
        
    @defer.inlineCallbacks
    def op_get_observatory(self, content, headers, msg):
        """
        Get data from the cyberinfrastructure side of the agent (registry info,
        topic locations, messaging parameters, process parameters, etc.)
        @param content A dict {'params':[param_arg, ,param_arg],'transaction_id':transaction_id}.
        @retval A reply message containing a dict
            {'success':success,'params':{param_arg:(success,val),...,param_arg:(success,val)},
            'transaction_id':transaction_id)
        """

        assert(isinstance(content,dict)), 'Expected a dict content.'
        assert(content.has_key('params')), 'Expected params.'
        assert(content.has_key('transaction_id')), 'Expected a transaction_id.'
        
        params = content['params']
        tid = content['transaction_id']
        
        assert(isinstance(params,list)), 'Expected a parameter list.'
        assert(isinstance(tid,(uuid4,str))), 'Expected a transaction_id str or uuid4.'

        if isinstance(tid,str):
            if tid != 'create' and tid != 'none':
                yield self.reply_ok(errors['InvalidTransactionID'])
                return


        # Set up the transaction
        result = yield self._verify_transaction(tid,'get')
        if not result:
            result = errors['LockedResource']
            yield self.reply_ok(msg,result)
            return
                    
        # Do the work here.
        # Set up the result message.

        # Do the work.
        #response = {}
        ## get data somewhere, or just punt this lower in the class hierarchy
        #if (ci_param_list[driver_address] in content):
        #    response[ci_param_list[driver_address]] = str(self.driver_client.target)
        #
        #if (ci_param_list['DataTopics'] in content):
        #    response[ci_param_list['DataTopics']] = {}
        #    for i in self.output_topics.keys():
        #        response[ci_param_list['DataTopics']][i] = self.output_topics[i].encode()
        #if (ci_param_list['StateTopics'] in content):
        #    response[ci_param_list['StateTopics']] = {}
        #    for i in self.state_topics.keys():
        #        response[ci_param_list['StateTopics']][i] = self.state_topics[i].encode()
        #if (ci_param_list['EventTopics'] in content):
        #    response[ci_param_list['EventTopics']] = {}
        #    for i in self.event_topics.keys():
        #        response[ci_param_list['EventTopics']][i] = self.event_topics[i].encode()

        
        # End implicit transactions.
        if tid == 'create':
            end_transaction(transaction_id)
                    
        yield self.reply_ok(msg,result)
        


    @defer.inlineCallbacks
    def op_set_observatory(self, content, headers, msg):
        """
        Set parameters related to the infrastructure side of the agent
        (registration information, location, network addresses, etc.)
        @param content A dict {'params':{param_arg:val,..., param_arg:val},
            'transaction_id':transaction_id}.
        @retval Reply message with dict
            {'success':success,'params':{param_arg:success,...,param_arg:success},'transaction_id':transaction_id}.
        """
        
        assert(isinstance(content,dict)), 'Expected a dict content.'
        assert(content.has_key('params')), 'Expected params.'
        assert(content.has_key('transaction_id')), 'Expected a transaction_id.'
        
        params = content['params']
        tid = content['transaction_id']
        
        assert(isinstance(params,dict)), 'Expected a parameter dict.'
        assert(isinstance(tid,(uuid4,str))), 'Expected a transaction_id str or uuid4.'
        
        if isinstance(tid,str):
            if tid != 'create' and tid != 'none':
                yield self.reply_ok(errors['InvalidTransactionID'])
                return
        

        # Set up the transaction
        result = yield self._verify_transaction(tid,'get')
        if not result:
            result = errors['LockedResource']
            yield self.reply_ok(msg,result)
            return
                    
        # Do the work here.
        # Set up the result message.
        
        # End implicit transactions.
        if tid == 'create':
            end_transaction(transaction_id)
                    
        yield self.reply_ok(msg,result)
 
 
    @defer.inlineCallbacks
    def op_get_observatory_metadata(self,content,headers,msg):
        """
        Retrieve metadata about the observatory configuration parameters.
        @param content A dict
            {'params':[(param_arg,meta_arg),...,param_arg,meta_arg)],'transaction_id':transaction_id}
        @retval A reply message with a dict {'success':success,'params':{(param_arg,meta_arg):(success,val),...,
            param_arg,meta_arg):(success,val)},'transaction_id':transaction_id}.
        """
        
        assert(isinstance(content,dict)), 'Expected a dict content.'
        assert(content.has_key('params')), 'Expected params.'
        assert(content.has_key('transaction_id')), 'Expected a transaction_id.'
        
        params = content['params']
        tid = content['transaction_id']
        
        assert(isinstance(params,list)), 'Expected a parameter list.'
        assert(isinstance(tid,(uuid4,str))), 'Expected a transaction_id str or uuid4.'

        if isinstance(tid,str):
            if tid != 'create' and tid != 'none':
                yield self.reply_ok(errors['InvalidTransactionID'])
                return


        # Set up the transaction
        result = yield self._verify_transaction(tid,'get')
        if not result:
            result = errors['LockedResource']
            yield self.reply_ok(msg,result)
            return
                    
        # Do the work here.
        # Set up the result message.
        
        # End implicit transactions.
        if tid == 'create':
            end_transaction(transaction_id)
                    
        yield self.reply_ok(msg,result)


    @defer.inlineCallbacks
    def op_get_observatory_status(self,content,headers,msg):
        """
        Retrieve the observatory status values, including lifecycle state and other
        dynamic observatory status values indexed by status keys.
        @param content A dict {'params':[status_arg,...,status_arg],'transaction_id':transaction_id}.
        @retval Reply message with a dict
            {'success':success,'params':{status_arg:(success,val),..., status_arg:(success,val)},
            'transaction_id':transaction_id}
        """
        
        assert(isinstance(content,dict)), 'Expected a dict content.'
        assert(content.has_key('params')), 'Expected params.'
        assert(content.has_key('transaction_id')), 'Expected a transaction_id.'
        
        params = content['params']
        tid = content['transaction_id']
        
        assert(isinstance(params,list)), 'Expected a parameter list.'
        assert(isinstance(tid,(uuid4,str))), 'Expected a transaction_id str or uuid4.'

        if isinstance(tid,str):
            if tid != 'create' and tid != 'none':
                yield self.reply_ok(errors['InvalidTransactionID'])
                return


        # Set up the transaction
        result = yield self._verify_transaction(tid,'get')
        if not result:
            result = errors['LockedResource']
            yield self.reply_ok(msg,result)
            return
                    
        # Do the work here.
        # Set up the result message.
        
        # End implicit transactions.
        if tid == 'create':
            end_transaction(transaction_id)
                    
        yield self.reply_ok(msg,result)
        


    @defer.inlineCallbacks
    def op_get_capabilities(self,content,headers,msg):
        """
        Retrieve the agent capabilities, including observatory and device values,
        both common and specific to the agent / device.
        @param content A dict {'params':[cap_arg,...,cap_arg],'transaction_id':transaction_id} 
            Valid capabilities arguments are: 'all','ObservatoryCommands,' 'ObservatoryParameters,'
            'ObservatoryStatuses,' 'ObservatoryMetadata,' 'DeviceCommands,', DeviceParameters,'
            'DeviceStatuses,' 'DeviceMetadata'
        @retval Reply message with a dict {'success':success,'params':{cap_arg:(success,[cap_val,...,cap_val]),...,
            cap_arg:(success,[cap_val,...,cap_val])}, 'transaction_id':transaction_id}
        """
        
        assert(isinstance(content,dict)), 'Expected a dict content.'
        assert(content.has_key('params')), 'Expected params.'
        assert(content.has_key('transaction_id')), 'Expected a transaction_id.'
        
        params = content['params']
        tid = content['transaction_id']
        
        assert(isinstance(params,list)), 'Expected a parameter list.'
        assert(isinstance(tid,(uuid4,str))), 'Expected a transaction_id str or uuid4.'

        if isinstance(tid,str):
            if tid != 'create' and tid != 'none':
                yield self.reply_ok(errors['InvalidTransactionID'])
                return


        # Set up the transaction
        result = yield self._verify_transaction(tid,'get')
        if not result:
            result = errors['LockedResource']
            yield self.reply_ok(msg,result)
            return
                    
        # Do the work here.
        # Set up the result message.
        
        # End implicit transactions.
        if tid == 'create':
            end_transaction(transaction_id)
                    
        yield self.reply_ok(msg,result)
        


    ############################################################################
    #   Instrument Facing Interface
    ############################################################################


    @defer.inlineCallbacks
    def op_execute_device(self, content, headers, msg):
        """
        Execute a command on the device fronted by the agent. Commands may be
        common or specific to the device, with specific commands known through
        knowledge of the device or a previous get_capabilities query.
        @param content A dict
            {'channels':[chan_arg,...,chan_arg],'command':[command,arg,...,argN]),'transaction_id':transaction_id)
       @retval A reply message with a dict
            {'success':success,'result':{chan_arg:(success,command_specific_values),...,chan_arg:(success,command_specific_values)},
            'transaction_id':transaction_id}. 
        """
        
        

        assert(isinstance(content,dict)), 'Expected a dict content.'
        assert(content.has_key('channels')), 'Expected channels.'
        assert(content.has_key('command')), 'Expected command.'
        assert(content.has_key('transaction_id')), 'Expected a transaction_id.'
        
        channels = content['channels']
        command = content['command']
        tid = content['transaction_id']
        
        assert(isinstance(channels,list)), 'Expected a channels list.'
        assert(isinstance(command,list)), 'Expected a command list.'
        assert(isinstance(tid,(uuid4,str))), 'Expected a transaction_id str or uuid4.'

        if isinstance(tid,str):
            if tid != 'create' and tid != 'none':
                yield self.reply_ok(errors['InvalidTransactionID'])
                return


        # Set up the transaction
        result = yield self._verify_transaction(tid,'get')
        if not result:
            result = errors['LockedResource']
            yield self.reply_ok(msg,result)
            return
                    
        # Do the work here.
        # Set up the result message.
        
        # End implicit transactions.
        if tid == 'create':
            end_transaction(transaction_id)
                    
        yield self.reply_ok(msg,result)


    @defer.inlineCallbacks
    def op_get_device(self, content, headers, msg):
        """
        Get configuration parameters from the instrument. 
        @param content A dict {'params':[(chan_arg,param_arg),...,(chan_arg,param_arg)],'transaction_id':transaction_id}
        @retval A reply message with a dict
            {'success':success,'params':{(chan_arg,param_arg):(success,val),...,(chan_arg,param_arg):(success,val)},
            'transaction_id':transaction_id}
        """
        assert(isinstance(content,dict)), 'Expected a dict content.'
        assert(content.has_key('params')), 'Expected params.'
        assert(content.has_key('transaction_id')), 'Expected a transaction_id.'
        
        params = content['params']
        tid = content['transaction_id']
        
        assert(isinstance(params,list)), 'Expected a parameter list.'
        assert(isinstance(tid,(uuid4,str))), 'Expected a transaction_id str or uuid4.'
        
        if isinstance(tid,str):
            if tid != 'create' and tid != 'none':
                yield self.reply_ok(errors['InvalidTransactionID'])
                return
        

        # Set up the transaction
        result = yield self._verify_transaction(tid,'get')
        if not result:
            result = errors['LockedResource']
            yield self.reply_ok(msg,result)
            return
                    
        # Do the work here.
        # Set up the result message.
        
        # End implicit transactions.
        if tid == 'create':
            end_transaction(transaction_id)
                    
        yield self.reply_ok(msg,result)



    @defer.inlineCallbacks
    def op_set_device(self, content, headers, msg):
        """
        Set parameters to the instrument side of of the agent. 
        @param content A dict {'params':{(chan_arg,param_arg):val,...,(chan_arg,param_arg):val},
            'transaction_id':transaction_id}.
        @retval Reply message with a dict
            {'success':success,'params':{(chan_arg,param_arg):success,...,chan_arg,param_arg):success},
            'transaction_id':transaction_id}.
        """
        assert(isinstance(content,dict)), 'Expected a dict content.'
        assert(content.has_key('params')), 'Expected params.'
        assert(content.has_key('transaction_id')), 'Expected a transaction_id.'
        
        params = content['params']
        tid = content['transaction_id']
        
        assert(isinstance(params,dict)), 'Expected a parameter dict.'
        assert(isinstance(tid,(uuid4,str))), 'Expected a transaction_id str or uuid4.'
        
        if isinstance(tid,str):
            if tid != 'create' and tid != 'none':
                yield self.reply_ok(errors['InvalidTransactionID'])
                return

        # Set up the transaction
        result = yield self._verify_transaction(tid,'get')
        if not result:
            result = errors['LockedResource']
            yield self.reply_ok(msg,result)
            return
                    
        # Do the work here.
        # Set up the result message.
        
        # End implicit transactions.
        if tid == 'create':
            end_transaction(transaction_id)
                    
        yield self.reply_ok(msg,result)



    @defer.inlineCallbacks
    def op_get_device_metadata(self, content, headers, msg):
        """
        Retrieve metadata for the device, its transducers and parameters.
        @param content A dict {'params':[(chan_arg,param_arg,meta_arg),...,(chan_arg,param_arg,meta_arg)],
            'transaction_id':transaction_id}
        @retval Reply message with a dict
            {'success':success,'params':{(chan_arg,param_arg,meta_arg):(success,val),...,
            chan_arg,param_arg,meta_arg):(success,val)}, 'transaction_id':transaction_id}.
        """
        assert(isinstance(content,dict)), 'Expected a dict content.'
        assert(content.has_key('params')), 'Expected params.'
        assert(content.has_key('transaction_id')), 'Expected a transaction_id.'
        
        params = content['params']
        tid = content['transaction_id']
        
        assert(isinstance(params,list)), 'Expected a parameter list.'
        assert(isinstance(tid,(uuid4,str))), 'Expected a transaction_id str or uuid4.'
        
        if isinstance(tid,str):
            if tid != 'create' and tid != 'none':
                yield self.reply_ok(errors['InvalidTransactionID'])
                return

        # Set up the transaction
        result = yield self._verify_transaction(tid,'get')
        if not result:
            result = errors['LockedResource']
            yield self.reply_ok(msg,result)
            return
                    
        # Do the work here.
        # Set up the result message.
        
        # End implicit transactions.
        if tid == 'create':
            end_transaction(transaction_id)
                    
        yield self.reply_ok(msg,result)



    @defer.inlineCallbacks
    def op_get_device_status(self, content, headers, msg):
        """
        Obtain the status of an instrument. This includes non-parameter
        and non-lifecycle state of the instrument.
        @param content A dict {'params':[(chan_arg,status_arg),...,chan_arg,status_arg)],
            'transaction_id':transaction_id}.
        @retval A reply message with a dict
            {'success':success,'params':{(chan_arg,status_arg):(success,val),...,
            chan_arg,status_arg):(success,val)}, 'transaction_id':transaction_id}.
        """
        
        assert(isinstance(content,dict)), 'Expected a dict content.'
        assert(content.has_key('params')), 'Expected params.'
        assert(content.has_key('transaction_id')), 'Expected a transaction_id.'
        
        params = content['params']
        tid = content['transaction_id']
        
        assert(isinstance(params,list)), 'Expected a parameter list.'
        assert(isinstance(tid,(uuid4,str))), 'Expected a transaction_id str or uuid4.'
        
        if isinstance(tid,str):
            if tid != 'create' and tid != 'none':
                yield self.reply_ok(errors['InvalidTransactionID'])
                return

        # Set up the transaction
        result = yield self._verify_transaction(tid,'get')
        if not result:
            result = errors['LockedResource']
            yield self.reply_ok(msg,result)
            return
                    
        # Do the work here.
        # Set up the result message.
        
        # End implicit transactions.
        if tid == 'create':
            end_transaction(transaction_id)
                    
        yield self.reply_ok(msg,result)


    @defer.inlineCallbacks
    def op_execute_direct(self,content,headers,msg):
        """
        Execute untranslated byte data commands on the device.
        Must be in direct access mode and possess the correct transaction_id key
        for the direct access session.
        @param content A dict {'bytes':block_of_data,'transaction_id':transaction_id}
        @retval A dict {'success':success}.
        """
        
        assert(isinstance(content,dict)), 'Expected a dict content.'
        assert(content.has_key('bytes')), 'Expected bytes.'
        assert(content.has_key('transaction_id')), 'Expected a transaction_id.'
        
        bytes = content['bytes']
        tid = content['transaction_id']

        assert(isinstance(tid,(uuid4,str))), 'Expected a transaction_id str or uuid4.'

        
        if isinstance(tid,str):
            if tid != 'create' and tid != 'none':
                yield self.reply_ok(errors['InvalidTransactionID'])
                return
        
        # get agent state
        if state != 'DirectAccessMode':
            yield self.reply_ok(msg,errors['IncorrectState'])
            return
        
        if tid != transaction_id:
            yield self.reply_ok(msg,errors['LockedResource'])
            return
        
        # Everything OK, send the data to the device
        # success = yield driver_client.execute_direct(command)
        # Results are published rather than replied?

        yield self.reply_ok(msg,['OK'])
            




    ############################################################################
    #   Publishing Methods
    ############################################################################



                
    @defer.inlineCallbacks
    def op_publish(self, content, headers, msg):
        """
        Collect data from a subprocess (usually the driver) to publish to the
        correct topic, specific to the hardware device, not the agent.
        @param content A dict including: a Type string of "StateChange",
          "ConfigChange", "Error", or "Data", and a Value string with the
          data or message that is to be published. Must also have "Transducer"
          to specify the transducer doing the chagne.
        """
        assert isinstance(content, dict), "InstrumentAgent op_publish argument error"
        log.debug("Agent is publishing with sender: %s, child_procs: %s, content: %s",
                  headers["sender-name"], self.child_procs, content)
        if (self._is_child_process(headers["sender-name"])):
            if (content["Type"] == publish_msg_type["Data"]):
                yield self.pubsub_client.publish(self,
                            self.output_topics[content["Transducer"]].reference(),
                            content["Value"])
            elif ((content["Type"] == publish_msg_type["Error"])
                or (content["Value"] == "ConfigChange")):
                yield self.pubsub_client.publish(self,
                            self.event_topics[content["Transducer"]].reference(),
                            content["Value"])
            elif (content["Type"] == publish_msg_type["StateChange"]):
                yield self.pubsub_client.publish(self,
                            self.state_topics[content["Transducer"]].reference(),
                            content["Value"])
        else:
            # Really should be handled better...what if there isnt a reply
            # expected?
            yield self.reply_err(msg,
                                 "publish invoked from non-child process")
        # return something...like maybe result?
    
    @defer.inlineCallbacks
    def _self_publish(self, type, value):
        """
        Publish a message from the instrument agent to one of the agent
        pubsub topics. Possibly an event or a state change. Probably not data
        @param type The type of information to publish (should be "Error",
            "StateChange", "ConfigChange", "Event")
        @todo Actually write a test case for this!
        """
        assert ((type == publish_msg_type["Error"]) or \
            (type == publish_msg_type["Event"]) or \
        (type == publish_msg_type["StateChange"]) or \
        (type == publish_msg_type["ConfigChange"])), "Bad IA publish type"
        
        if (type == publish_msg_type["Error"]) or \
            (type == publish_msg_type["Event"]) or \
            (type == publish_msg_type["ConfigChange"]):
                yield self.pubsub_client.publish(self.sup,
                            self.event_topics["Agent"].reference(),value)
        if (type == publish_msg_type["StateChange"]):
                yield self.pubsub_client.publish(self.sup,
                            self.state_topics["Agent"].reference(),value)
    

        
class InstrumentAgentClient(ResourceAgentClient):
    """
    The base class for an Instrument Agent Client. It is a service
    that allows for RPC messaging
    """

    @defer.inlineCallbacks
    def get_from_instrument(self, paramList):
        """
        Obtain a list of parameter names from the instrument
        @param paramList A list of the values to fetch
        @retval A dict of the names and values requested
        """
        assert(isinstance(paramList, list))
        (content, headers, message) = yield self.rpc_send('get_from_instrument',
                                                          paramList)
        assert(isinstance(content, dict))
        defer.returnValue(content)

    @defer.inlineCallbacks
    def get_observatory(self, paramList):
        """
        Obtain a list of parameter names from the instrument, decode some
        values as needed.
        @param paramList A list of the values to fetch
        @retval A dict of the names and values requested
        """
        assert(isinstance(paramList, list))
        (content, headers, message) = yield self.rpc_send('get_observatory',
                                                          paramList)
        assert(isinstance(content, dict))
        for key in content.keys():
            if (key == ci_param_list['DataTopics']) or \
                (key == ci_param_list['EventTopics']) or \
                       (key == ci_param_list['StateTopics']):
                for entry in content[key].keys():
                    content[key][entry] = DataObject.decode(content[key][entry])
        defer.returnValue(content)

    @defer.inlineCallbacks
    def set_to_instrument(self, paramDict):
        """
        Set a collection of values on an instrument
        @param paramDict A dict of parameter names and the values they are
            being set to
        @retval A dict of the successful set operations that were performed
        @todo Add exceptions for error conditions
        """
        assert(isinstance(paramDict, dict))
        (content, headers, message) = yield self.rpc_send('set_to_instrument',
                                                          paramDict)
        assert(isinstance(content, dict))
        defer.returnValue(content)

    @defer.inlineCallbacks
    def set_to_CI(self, paramDict):
        """
        Set a collection of values on an instrument
        @param paramDict A dict of parameter names and the values they are
            being set to
        @retval A dict of the successful set operations that were performed
        @todo Add exceptions for error conditions
        """
        assert(isinstance(paramDict, dict))
        (content, headers, message) = yield self.rpc_send('set_to_CI',
                                                          paramDict)
        assert(isinstance(content, dict))
        defer.returnValue(content)

    @defer.inlineCallbacks
    def disconnect(self, argList):
        """
        Disconnect from the instrument
        """
        log.debug("DHE: IAC in op_disconnect!")
        assert(isinstance(argList, list))
        (content, headers, message) = yield self.rpc_send('disconnect',
                                                              argList)
        assert(isinstance(content, dict))
        defer.returnValue(content)

    @defer.inlineCallbacks
    def execute_device(self, command):
        """
        Execute the instrument commands in the order of the list.
        Processing will cease when a command fails, but will not roll back.
        For instrument calls, use executeInstrument()
        @see executeInstrument()
        @param command A list where the command name is the
            first item in the sub-list, and the arguments are the rest of
            the items in the sublists. For example:
            ['command1', 'arg1', 'arg2']
        @retval Dictionary of responses to each execute command
        @todo Alter semantics of this call as needed...maybe a list?
        @todo Add exceptions as needed
        """
        assert(isinstance(command, list))
        (content, headers, message) = yield self.rpc_send('execute_device',
                                                          command)
        log.debug("message = " + str(message))
        defer.returnValue(content)

    @defer.inlineCallbacks
    def execute_observatory(self, command):
        """
        Execute the instrument commands in the order of the list.
        Processing will cease when a command fails, but will not roll back.
        For instrument calls, use execute_device()
        @see execute_device()
        @param command A list where the command name is the
            first item in the sub-list, and the arguments are the rest of
            the items in the sublists. For example:
            ['command1', 'arg1', 'arg2']
        @retval Dictionary of responses to each execute command
        @todo Alter semantics of this call as needed...maybe a command list?
        @todo Add exceptions as needed
        """
        assert(isinstance(command, list))
        (content, headers, message) = yield self.rpc_send('execute_observatory',
                                                          command)
        assert(isinstance(content, dict))
        defer.returnValue(content)

    @defer.inlineCallbacks
    def get_status(self, argList):
        """
        Obtain the non-parameter and non-lifecycle status of the instrument
        @param argList A list of arguments to pass for status
        """
        assert(isinstance(argList, list))
        (content, headers, message) = yield self.rpc_send('get_status',
                                                              argList)
        defer.returnValue(content)

    @defer.inlineCallbacks
    def start_phrase(self, timeout=0):
        """
        Start a phrase. Must not already have a phrase started or ended
            pending application.
        @param timeout An optional timeout in time duration format
        @retval Success with a phrase ID or failure with an explanation
        """
        (content, headers, message) = yield self.rpc_send('start_phrase',
                                                          timeout)
        defer.returnValue(content)

    @defer.inlineCallbacks
    def end_phrase(self):
        """
        End a phrase. Must have a phrase started and not ended
            pending application.
        @retval Success or failure with an explanation
        """
        (content, headers, message) = yield self.rpc_send('end_phrase', None)
        defer.returnValue(content)

    @defer.inlineCallbacks
    def cancel_phrase(self):
        """
        Cancel a phrase. Must have a phrase started.
        @retval Success or failure with an explanation
        """
        (content, headers, message) = yield self.rpc_send('cancel_phrase', None)
        defer.returnValue(content)
        
    @defer.inlineCallbacks
    def get_capabilities(self):
        """
        Obtain a list of capabilities from the instrument
        @retval A dict with commands and
        parameter lists that are supported
            such as {'commands':(), 'parameters':()}
        """
        (content, headers, message) = yield self.rpc_send('get_capabilities',
                                                          ())
        assert(isinstance(content, dict))
        assert(ci_commands in content.keys())
        assert(ci_parameters in content.keys())
        assert(isinstance(content[ci_commands], (tuple, list)))
        assert(isinstance(content[ci_parameters], (tuple, list)))
        assert(instrument_commands in content.keys())
        assert(instrument_parameters in content.keys())
        assert(isinstance(content[instrument_commands], (tuple, list)))
        assert(isinstance(content[instrument_parameters], (tuple, list)))

        listified = {}
        for listing in content.keys():
            listified[listing] = list(content[listing])

        # Add in the special stuff that all instruments know
        listified[ci_parameters].append(driver_address)

        defer.returnValue(listified)

    @defer.inlineCallbacks
    def register_resource(self, instrument_id):
        """
        Register the resource. Since this is a subclass, make the appropriate
        resource description for the registry and pass that into the
        registration call.
        """
        ia_instance = InstrumentAgentResourceInstance()
        ci_params = yield self.get_observatory([driver_address])
        ia_instance.driver_process_id = ci_params[driver_address]
        ia_instance.instrument_ref = ResourceReference(
            RegistryIdentity=instrument_id, RegistryBranch='master')
        result = yield ResourceAgentClient.register_resource(self,
                                                             ia_instance)
        defer.returnValue(result)
