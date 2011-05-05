#!/usr/bin/env python

"""
@file ion/agents/instrumentagents/instrument_agent.py
@author Edward Hunter
@brief Simple state mahcine for driver and agent classes.
"""

from twisted.internet import defer



class InstrumentFSM():
    """
    Simple state mahcine for driver and agent classes.
    """


    def __init__(self, states, events, state_handlers,enter_event,exit_event):
        """
        Initialize states, events, handlers.
        """
        self.states = states
        self.events = events
        self.state_handlers = state_handlers
        self.current_state = None
        self.previous_state = None
        self.enter_event = enter_event
        self.exit_event = exit_event

    def get_current_state(self):
        """
        Return current state.
        """
        return self.current_state


    def start(self,state,params=None):
        """
        Start the state machine. Initializes current state and fires the
        EVENT_ENTER event.
        """
        
        #if state not in self.states:
        #    return False
        
        if not self.states.has(state):
            return False
        
        self.current_state = state
        self.state_handlers[self.current_state](self.enter_event,params)
        return True

    def on_event(self,event,params=None):
        """
        Handle an event. Call the current state handler passing the event
        and paramters.
        @param event A string indicating the event that has occurred.
        @param params Optional parameters to be sent with the event to the
            handler.
        @retval Success/fail if the event was handled by the current state.
        """
        
        (success,next_state) = self.state_handlers[self.current_state](event,params)
        
        
        #if next_state in self.states:
        if self.states.has(next_state):
            self._on_transition(next_state,params)
                
        return success

    @defer.inlineCallbacks
    def on_event_async(self,event,params=None):
        """
        Handle an event. Call the current state handler passing the event
        and paramters.
        @param event A string indicating the event that has occurred.
        @param params Optional parameters to be sent with the event to the
            handler.
        @retval Success/fail if the event was handled by the current state.
        """
        
        (success,next_state) = yield self.state_handlers[self.current_state](event,params)
        
        
        #if next_state in self.states:
        if self.states.has(next_state):
            yield self._on_transition_async(next_state,params)
                
        defer.returnValue(success)

            
    def _on_transition(self,next_state,params):
        """
        Call the sequence of events to cause a state transition. Called from
        on_event if the handler causes a transition.
        @param next_state The state to transition to.
        @param params Opional parameters passed from on_event
        """
        
        self.state_handlers[self.current_state](self.exit_event,params)
        self.previous_state = self.current_state
        self.current_state = next_state
        self.state_handlers[self.current_state](self.enter_event,params)


    @defer.inlineCallbacks
    def _on_transition_async(self,next_state,params):
        """
        Call the sequence of events to cause a state transition. Called from
        on_event if the handler causes a transition.
        @param next_state The state to transition to.
        @param params Opional parameters passed from on_event
        """
        
        yield self.state_handlers[self.current_state](self.exit_event,params)
        self.previous_state = self.current_state
        self.current_state = next_state
        yield self.state_handlers[self.current_state](self.enter_event,params)
        






    
    
    
    