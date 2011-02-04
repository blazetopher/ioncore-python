#!/usr/bin/env python
"""
@file ion/core/object/gpb_wrapper.py
@brief Wrapper for Google Protocol Buffer Message Classes.
These classes are the lowest level of the object management stack
@author David Stuebe
TODO:
Finish test of new Invalid methods using weakrefs - make sure it is deleted!
"""

from ion.util import procutils as pu

from ion.core.object.object_utils import get_type_from_obj, sha1bin, sha1hex, sha1_to_hex, ObjectUtilException, create_type_identifier

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)

import struct

from google.protobuf import message
from google.protobuf.internal import containers
    
from net.ooici.core.container import container_pb2
from net.ooici.core.link import link_pb2
from net.ooici.core.type import type_pb2
from ion.util.cache import memoize

import hashlib

class OOIObjectError(Exception):
    """
    An exception class for errors that occur in the Object Wrapper class
    """
    
class Wrapper(object):
    '''
    A Wrapper class for intercepting access to protocol buffers message fields.
    For instance, in the example below I can create a wrapper which is
    read-only.
    
    To make the wrapper general - apply to more than one kind of protobuffer -
    we can not use descriptors (properties) to transparently intercept a get or
    set request because they are class attributes - shared between all instances
    of the wrapper class. If we add properties each time we create a wrapper
    instance for a new kind of protobuf, new properties will be added to all
    wrapper instances.
    
    The solution I can up with is clunky! Override the __getattribute__ and
    _setattr__ method to preemptively check a list of fields to get from the
    protocol buffer message. If the key is in the list get/set the deligated
    protocol buffer rather than the wrapper class. The problem is that now we
    can not use the default get/set to initialize our own class or get the list
    of fields!
    
    Organization:
    The meat of the class is at the top - Init and class methods are at the top
    along with overrides for __getattribute__ and __setattr__ which are the heart
    of the wrapper.
    
    Below that are all of the methods of protobuffers exposed by the wrapper.
    
    TODO:
    What about name conflicts between wrapper methods and GPB Fields?
    
    
    '''
        
    LinkClassType = create_type_identifier(object_id=3, version=1)
        
    def __init__(self, gpbMessage):
        """
        Initialize the Wrapper class and set up it message type.
        
        """
        
        object.__setattr__(self,'_gpbFields',[])
        """
        A list of fields names empty for now... so that we can use getter/setters
        on the data elements of the wrapped proto buffer
        """
        
        object.__setattr__(self,'_invalid',False)
        """
        Use this field to invalidate a message wrapper when it should be deleted.
        This ensures that any references which have not gone out of scope can not
        cause trouble!
        """
        
        # Set the deligated message and its machinary
        if not isinstance(gpbMessage, message.Message):
            raise OOIObjectError('Wrapper init argument must be an instance of a GPB message')
        
        self._gpbMessage = gpbMessage
        self._GPBClass = gpbMessage.__class__
        # Get the GPB Field Names
        field_names = self._GPBClass.DESCRIPTOR.fields_by_name.keys()
        # Get the GPB Enum Names
        for enum_type in self._GPBClass.DESCRIPTOR.enum_types:
            for enum_value in enum_type.values:
                field_names.append(enum_value.name)
        
        try:
            self._gpb_type = get_type_from_obj(gpbMessage)
        except ObjectUtilException, re:
            self._gpb_type = None
            
            
        self._root=None
        """
        A reference to the root object wrapper for this protobuffer
        A composit protobuffer object may return 
        """
        
        self._bytes = None
        """
        Used in _load_element to create a proxy object. The bytes are not loaded
        parsed until the object is needed!
        """
        
        self._parent_links=None
        """
        A list of all the other wrapper objects which link to me
        """
        
        self._child_links=None
        """
        A list of my child link wrappers
        """
        
        self._derived_wrappers=None
        """
        A container for all the wrapper objects which are rewrapped, derived
        from a root object wrapper
        """
        
        self._myid = None # only exists in the root object
        """
        The name for this object - the SHA1 if it is already hashed or the object
        counter value if it is still in the workspace.
        """
        
        self._modified =  None # only exists in the root object
        """
        Is this wrapper object modified or commited
        """
        
        self._read_only = None # only exists in the root object
        """
        Set this to be a read only wrapper!
        Used for commit objects and a history checkout... it is only set in the root object
        """
        
        self._repository = None # only exists in the root object
        """
        Need to cary a reference to the repository I am in.
        """
        
        # Now set the fields from that GPB to preempt getter/setter!
        self._gpbFields = field_names
                
        
    @property
    def Invalid(self):
        return object.__getattribute__(self,'_invalid')
    
    def Invalidate(self):
        if self.IsRoot:
            for item in self.DerivedWrappers.values():
                item.Invalidate()
            
        self._derived_wrappers = None
        self._gpbMessage = None
        self._parent_links = None
        self._child_links = None
        self._myid = None
        self._repository = None
        self._bytes = None
        self._root = None
        object.__setattr__(self,'_gpbFields',[])
        
        self._invalid = True
        
    @property
    def ObjectClass(self):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        
        #return self._GPBClass
        return object.__getattribute__(self,'_GPBClass')
    
    @property
    def DESCRIPTOR(self):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        
        #return self._gpbMessage.DESCRIPTOR
        return object.__getattribute__(self,'_gpbMessage').DESCRIPTOR
        
    @property
    def Root(self):
        """
        Access to the root object of the nested GPB object structure
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        #return self._root
        return object.__getattribute__(self,'_root')
    
    @property
    def IsRoot(self):
        """
        Is this wrapped object the root of a GPB Message?
        GPBs are also tree structures and each element must be wrapped
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        return self is object.__getattribute__(self,'_root')
    
    @property
    def ObjectType(self):
        """
        Could just replace the attribute with the capital name?
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        #return self._gpb_type
        return object.__getattribute__(self,'_gpb_type')
    
    @property
    def GPBMessage(self):
        """
        Could just replace the attribute with the capital name?
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        # If this is a proxy object which references its serialized value load it!
        
        #bytes = self._bytes
        bytes = object.__getattribute__(self,'_bytes')
        if  bytes != None:
            #self.ParseFromString(bytes)
            pfs = object.__getattribute__(self,'ParseFromString')
            pfs(bytes)
            #self._bytes = None
            object.__setattr__(self,'_bytes', None)
            
        #return self._gpbMessage
        return object.__getattribute__(self,'_gpbMessage')
        
    @property
    def Repository(self):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        root = object.__getattribute__(self,'Root')
        return object.__getattribute__(root,'_repository')
    
    @property
    def DerivedWrappers(self):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        root = object.__getattribute__(self,'Root')
        return object.__getattribute__(root,'_derived_wrappers')
    
    def _get_myid(self):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        root = object.__getattribute__(self,'Root')
        return object.__getattribute__(root,'_myid')
    
    def _set_myid(self,value):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        assert isinstance(value, str), 'myid is a string property'
        root = object.__getattribute__(self,'Root')
        object.__setattr__(root,'_myid', value)

    MyId = property(_get_myid, _set_myid)
    
    
    def _get_parent_links(self):
        """
        A list of all the wrappers which link to me
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        root = object.__getattribute__(self,'Root')
        return object.__getattribute__(root,'_parent_links')
        
    def _set_parent_links(self,value):
        """
        A list of all the wrappers which link to me
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        root = object.__getattribute__(self,'Root')
        object.__setattr__(root,'_parent_links', value)

    ParentLinks = property(_get_parent_links, _set_parent_links)
        
    def _get_child_links(self):
        """
        A list of all the wrappers which I link to
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        root = object.__getattribute__(self,'Root')
        return object.__getattribute__(root,'_child_links')
        
    def _set_child_links(self, value):
        """
        A list of all the wrappers which I link to
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        root = object.__getattribute__(self,'Root')
        object.__setattr__(root,'_child_links', value)
        
    ChildLinks = property(_get_child_links, _set_child_links)
        
    def _get_readonly(self):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        root = object.__getattribute__(self,'Root')
        return object.__getattribute__(root,'_read_only')
        
    def _set_readonly(self,value):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        assert isinstance(value, bool), 'readonly is a boolen property'
        root = object.__getattribute__(self,'Root')
        object.__setattr__(root,'_read_only', value)

    ReadOnly = property(_get_readonly, _set_readonly)
    
    def _get_modified(self):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        root = object.__getattribute__(self,'Root')
        return object.__getattribute__(root,'_modified')

    def _set_modified(self,value):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        assert isinstance(value, bool), 'modified is a boolen property'
        root = object.__getattribute__(self,'Root')
        object.__setattr__(root,'_modified',value)

    Modified = property(_get_modified, _set_modified)
    
    
    def SetLink(self,value):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        if not self.ObjectType == self.LinkClassType:
            raise OOIObjectError('Can not set link for non link type!')
            
        object.__getattribute__(self,'Repository').set_linked_object(self,value)
        if not object.__getattribute__(self,'Modified'):
            #self._set_parents_modified()
            object.__getattribute__(self,'_set_parents_modified')()
            
        
    def SetLinkByName(self,linkname,value):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        #link = self.GetLink(linkname)
        link = object.__getattribute__(self,'GetLink')(linkname)
        #link.SetLink(value)
        object.__getattribute__(link,'SetLink')(value)
        
    def GetLink(self,linkname):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        
        gpb = object.__getattribute__(self,'GPBMessage')
        link = getattr(gpb,linkname)
        #link = self._rewrap(link)
        link = object.__getattribute__(self,'_rewrap')(link)
        
        if not object.__getattribute__(link,'ObjectType') == object.__getattribute__(self,'LinkClassType'):
            raise OOIObjectError('The field "%s" is not a link!' % linkname)
        return link
         
    def InParents(self,value):
        '''
        Check recursively to make sure the object is not already its own parent!
        '''
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        for item in object.__getattribute__(self,'ParentLinks'):
            if object.__getattribute__(item,'Root') is value:
                return True
            # if item.InParents(value):
            if object.__getattribute__(item, 'InParents')(value):
                return True
        return False
    
    def SetStructureReadOnly(self):
        """
        Set these objects to be read only
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        object.__setattr__(self, 'read_only',True)
        for link in object.__getattribute__(self, 'ChildLinks'):
            child = object.__getattribute__(self,'Repository').get_linked_object(link)
            child.SetStructureReadOnly()
            object.__getattribute__(child,'SetStructureReadOnly')()
        
    def SetStructureReadWrite(self):
        """
        Set these object to be read write!
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        object.__setattr__(self, 'read_only',False)
        for link in object.__getattribute__(self, 'ChildLinks'):
            child = object.__getattribute__(self,'Repository').get_linked_object(link)
            #child.SetStructureReadWrite()
            object.__getattribute__(child,'SetStructureReadWrite')()

    def RecurseCommit(self,structure):
        """
        Recursively build up the serialized structure elements which are needed
        to commit this wrapper and reset all the links using its CAS name.
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        if not  object.__getattribute__(self,'Modified'):
            # This object is already committed!
            return
        
        # Create the Structure Element in which the binary blob will be stored
        se = StructureElement()        
        repo = object.__getattribute__(self,'Repository')
        for link in  object.__getattribute__(self,'ChildLinks'):
                        
            # Test to see if it is already serialized!
            
            if  repo._hashed_elements.has_key(link.key):
                child_se = repo._hashed_elements.get(link.key)

                # Set the links is leaf property
                link.isleaf = child_se.isleaf
                
            else:
                child = repo.get_linked_object(link)
                
                # Determine whether this is a leaf node
                if len(object.__getattribute__(child,'ChildLinks'))==0:
                    link.isleaf = True
                else:
                    link.isleaf = False
            
                child.RecurseCommit(structure)
            
            # Save the link info as a convience for sending!
            se.ChildLinks.add(link.key)
                    
        se.value = self.SerializeToString()
        #se.key = sha1hex(se.value)

        # Structure element wrapper provides for setting type!
        se.type = object.__getattribute__(self,'ObjectType')
        
        # Calculate the sha1 from the serialized value and type!
        # Sha1 is a property - not a method...
        se.key = se.sha1
        
        # Determine whether I am a leaf
        if len(object.__getattribute__(self,'ChildLinks'))==0:
            se.isleaf=True
        else:
            se.isleaf = False
            
        
        if repo._workspace.has_key(self.MyId):
            
            del repo._workspace[self.MyId]
            repo._workspace[se.key] = self

        object.__setattr__(self,'MyId',se.key)
        
        object.__setattr__(self,'Modified',False)
       
        # Set the key value for parent links!
        for link in object.__getattribute__(self,'ParentLinks'):
            # Can not use object.__setattr__ on gpb fields!
            link.key = object.__getattribute__(self,'MyId')
            
        structure[se.key] = se
        
        

    def FindChildLinks(self):
        """
        Find all of the links in this composit structure
        All of the objects worked on in this method are raw proto buffers messages!
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        gpb = object.__getattribute__(self,'GPBMessage')
        # For each field in the protobuffer message
        for field in gpb.DESCRIPTOR.fields:
            # if the field is a composite - another message
            if field.message_type:
                
                # Get the field of type message
                gpb_field = getattr(gpb,field.name)
                                
                
                # If it is a repeated container type
                if isinstance(gpb_field, containers.RepeatedCompositeFieldContainer):
                    
                    for item in gpb_field:
                        
                        wrapped_item = self._rewrap(item)
                        if wrapped_item.ObjectType == wrapped_item.LinkClassType:
                            object.__getattribute__(self,'ChildLinks').add(wrapped_item)
                        else:
                            wrapped_item.FindChildLinks()
                                
                # IF it is a standard message field
                else:
                    if not gpb_field.IsInitialized():
                        # if it is an optional field which is not initialized
                        # it can not hold any links!
                        continue
                    
                    rr= object.__getattribute__(self,'_rewrap')
                    item = rr(gpb_field)
                    if object.__getattribute__(item,'ObjectType') == object.__getattribute__(item,'LinkClassType'):
                        object.__getattribute__(self,'ChildLinks').add(item)
                    else:
                        fcl = object.__getattribute__(item,'FindChildLinks')
                        fcl()
    
    def AddParentLink(self, link):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        for parent in object.__getattribute__(self,'ParentLinks'):
            
            if parent.GPBMessage is link.GPBMessage:
                break
        else:
            self.ParentLinks.add(link)
        
    def _rewrap(self, gpbMessage):
        '''
        Factory method to return a new instance of wrapper for a gpbMessage
        from self - used for access to composite structures, it has all the same
        shared variables as the parent wrapper
        '''
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        # Check the root wrapper objects list of derived wrappers
        objhash = gpbMessage.__hash__()
        dw = object.__getattribute__(self,'DerivedWrappers')
        if objhash in dw:
            return dw[objhash]
        
        # Else make a new one...
        inst = Wrapper(gpbMessage)        
        inst._root = self._root
        
        # Add it to the list of objects which derive from the root wrapper
        dw[objhash] = inst
        
        return inst

    def __getattribute__(self, key):
        
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            if key == 'Invalid':
                return True
            else:
                raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
                
        # Because we have over-riden the default getattribute we must be extremely
        # careful about how we use it!
        gpbfields = object.__getattribute__(self,'_gpbFields')
        
        if key in gpbfields:
            
            # If it is a Field defined by the gpb...
            gpb = object.__getattribute__(self,'GPBMessage')
            
            # This may be the result we were looking for, in the case of a simple
            # scalar field
            field = getattr(gpb,key)
            
            # Or it may be something more complex that we need to operate on...        
            if isinstance(field, containers.RepeatedScalarFieldContainer):
                result = ScalarContainerWrapper.factory(self, field)
                
            elif isinstance(field, containers.RepeatedCompositeFieldContainer):
                result = ContainerWrapper.factory(self, field)
                
            elif isinstance(field, message.Message):
                result = self._rewrap(field)
                
                if object.__getattribute__(result,'ObjectType') == object.__getattribute__(self,'LinkClassType'):
                    result = object.__getattribute__(self,'Repository').get_linked_object(result)
            else:
                # Probably bad that the common case comes last!
                result = field
                
        else:
            # If it is a attribute of this class, use the base class's getattr
            try:
                result = object.__getattribute__(self, key)
            except AttributeError, ex:                
                raise OOIObjectError(
                '''"Wrapper" object for GPB class "%s"; has no attribute "%s"''' 
                % (self._GPBClass, key))
        
        return result

    def __setattr__(self,key,value):

        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        gpbfields = object.__getattribute__(self,'_gpbFields')
        
        if key in gpbfields:
            # If it is a Field defined by the gpb...
            if object.__getattribute__(self,'ReadOnly'):
                raise OOIObjectError('This object wrapper is read only!')
                        
            gpb = object.__getattribute__(self,'GPBMessage')

            # If the value we are setting is a Wrapper Object
            if isinstance(value, Wrapper):
                    
                if object.__getattribute__(value,'_invalid'):
                    raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
                    
                # get the callable and call it!
                #self.SetLinkByName(key,value)
                object.__getattribute__(self,'SetLinkByName')(key,value)
                    
            else:
                
                setattr(gpb, key, value)
                
            # Set this object and it parents to be modified
            #self._set_parents_modified()
            object.__getattribute__(self,'_set_parents_modified')()
                
        else:
            try:
                v = object.__setattr__(self, key, value)
            except AttributeError, ex:
                
                raise OOIObjectError(
                '''"Wrapper" object for GPB class "%s"; has no attribute "%s"''' 
                % (self._GPBClass, key))
        
    def _set_parents_modified(self):
        """
        This method recursively changes an objects parents to a modified state
        All links are reset as they are no longer hashed values
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        if object.__getattribute__(self,'Modified'):
            # Be clear about what we are doing here!
            return
        else:
            
            object.__setattr__(self,'Modified', True)
            
            # Get the repository            
            repo = object.__getattribute__(self,'Repository')
            
            new_id = repo.new_id()
            repo._workspace[new_id] = self.Root
            
            if repo._workspace.has_key(self.MyId):
                del repo._workspace[self.MyId]
            object.__setattr__(self,'MyId', new_id)
              
            # When you hit the commit ref - stop!                   
            if object.__getattribute__(self,'Root') is repo._workspace_root:
                # The commit is no longer really your parent!
                object.__setattr__(self,'ParentLinks',set())
                
            else:
                
                for link in object.__getattribute__(self,'ParentLinks'):
                    # Tricky - set the message directly and call modified!
                    #link.GPBMessage.key = self.MyId
                    object.__getattribute__(link,'GPBMessage').key = self.MyId
                    #link._set_parents_modified()
                    object.__getattribute__(link,'_set_parents_modified')()
            
    def __eq__(self, other):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        if not isinstance(other, Wrapper):
            return False
        
        if self is other:
            return True
        
        return object.__getattribute__(self,'GPBMessage') == object.__getattribute__(other,'GPBMessage')
    
    def __ne__(self, other):
        # Can't just say self != other_msg, since that would infinitely recurse. :)
        return not self == other
    
    def __str__(self):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        if self.ObjectType == self.LinkClassType:
            msg = '\nkey: %s \ntype { %s }' % (sha1_to_hex(self.GPBMessage.key), self.GPBMessage.type)
        else:
            msg = '\n' +self.GPBMessage.__str__()
            
        return msg
        
    def Debug(self):
        output  = '================== Wrapper (Modified = %s)====================\n' % self.Modified
        output += 'Wrapper ID: %s \n' % self.MyId
        output += 'Wrapper IsRoot: %s \n' % self.IsRoot
        output += 'Wrapper ParentLinks: %s \n' % str(self.ParentLinks)
        output += 'Wrapper ChildLinks: %s \n' % str(self.ChildLinks)
        output += 'Wrapper current value:\n'
        output += str(self) + '\n'
        output += '================== Wrapper Complete ========================='
        return output

    def IsInitialized(self):
        """Checks if the message is initialized.
        
        Returns:
            The method returns True if the message is initialized (i.e. all of its
        required fields are set).
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        #return self.GPBMessage.IsInitialized()
        return object.__getattribute__(self,'GPBMessage').IsInitialized()
        
    def SerializeToString(self):
        """Serializes the protocol message to a binary string.
        
        Returns:
          A binary string representation of the message if all of the required
        fields in the message are set (i.e. the message is initialized).
        
        Raises:
          message.EncodeError if the message isn't initialized.
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        #return self.GPBMessage.SerializeToString()
        return object.__getattribute__(self,'GPBMessage').SerializeToString()
    
    def ParseFromString(self, serialized):
        """Clear the message and read from serialized."""
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')

        # Do not use the GPBMessage method - it will recurse!
        #self._gpbMessage.ParseFromString(serialized)
        object.__getattribute__(self,'_gpbMessage').ParseFromString(serialized)
        
    def ListSetFields(self):
        """Returns a list of (FieldDescriptor, value) tuples for all
        fields in the message which are not empty.  A singular field is non-empty
        if IsFieldSet() would return true, and a repeated field is non-empty if
        it contains at least one element.  The fields are ordered by field
        number"""
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        #return self.GPBMessage.ListFields()
        
        field_list = object.__getattribute__(self,'GPBMessage').ListFields()
        fnames=[]
        for desc, val in field_list:
            fnames.append(desc.name)
        return fnames

    def IsFieldSet(self, field_name):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        try:
            #result = self.GPBMessage.HasField(field_name)
            result = object.__getattribute__(self,'GPBMessage').HasField(field_name)
        except ValueError, ex:
            raise OOIObjectError('The "%s" object definition does not have a field named "%s"' % \
                    (str(self.ObjectClass), field_name))
            
        return result

    def HasField(self, field_name):
        log.warn('HasField is depricated because the name is confusing. Use IsFieldSet')
        #return self.IsFieldSet(field_name)
        return object.__getattribute__(self,'IsFieldSet')(field_name)
    
    def ClearField(self, field_name):
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        GPBMessage = object.__getattribute__(self,'GPBMessage')
            
        #if not GPBMessage.IsFieldSet(field_name):
        #    # Nothing to clear
        #    return
            
        # Get the raw GPB field
        try: 
            GPBField = getattr(GPBMessage, field_name)
        except AttributeError, ex:
            raise OOIObjectError('The "%s" object definition does not have a field named "%s"' % \
                    (str(self.ObjectClass), field_name))
            
        if isinstance(GPBField, containers.RepeatedScalarFieldContainer):
            objhash = GPBField.__hash__()
            del self.DerivedWrappers[objhash]
            # Nothing to do - just clear the field. It can not contain a link            

        elif isinstance(GPBField, containers.RepeatedCompositeFieldContainer):
            for item in GPBField:
                wrapped_field = self._rewrap(item)
                wrapped_field._clear_derived_message()
                
                item_hash = item.__hash__()
                del self.DerivedWrappers[item_hash]
                
            objhash = GPBField.__hash__()
            del self.DerivedWrappers[objhash]            

        elif isinstance(GPBField, message.Message):
            wrapped_field = self._rewrap(GPBField)
            wrapped_field._clear_derived_message()
            
            objhash = GPBField.__hash__()
            del self.DerivedWrappers[objhash]
        
        #Now clear the field
        self.GPBMessage.ClearField(field_name)
        # Set this object and it parents to be modified
        self._set_parents_modified()
            
    def _clear_derived_message(self):
        """
        Helper method for ClearField
        """
        if object.__getattribute__(self,'ObjectType') == object.__getattribute__(self,'LinkClassType'):
            child_obj = object.__getattribute__(self,'Repository').get_linked_object(self)
            # Remove this link from the list of parents
            object.__getattribute__(child_obj,'ParentLinks').remove(self)
                
            # This is the only one, remove it as a child
            object.__getattribute__(self,'ChildLinks').remove(self)
            
        for field_name in object.__getattribute__(self,'DESCRIPTOR').fields_by_name.keys():
            # Recursively remove all 
            object.__getattribute__(self,'ClearField')(field_name)
        
    #def HasExtension(self, extension_handle):
    #    return self.GPBMessage.HasExtension(extension_handle)
    
    #def ClearExtension(self, extension_handle):
    #    return self.GPBMessage.ClearExtension(extension_handle)
    
    def ByteSize(self):
        """Returns the serialized size of this message.
        Recursively calls ByteSize() on all contained messages.
        """
        #if self.Invalid:
        if object.__getattribute__(self,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        return object.__getattribute__(self,'GPBMessage').ByteSize()
    
    
    
class ContainerWrapper(object):
    """
    This class is only for use with containers.RepeatedCompositeFieldContainer
    It is not needed for repeated scalars!
    """
    
    LinkClassType = create_type_identifier(object_id=3, version=1)
    
    def __init__(self, wrapper, gpbcontainer):
        # Be careful - this is a hard link
        self._wrapper = wrapper
        if not isinstance(gpbcontainer, containers.RepeatedCompositeFieldContainer):
            raise OOIObjectError('The Container Wrapper is only for use with Repeated Composit Field Containers')
        self._gpbcontainer = gpbcontainer
        self.Repository = object.__getattribute__(wrapper,'Repository')

    @classmethod
    def factory(cls, wrapper, gpbcontainer):
        
        # Check the root wrapper objects list of derived wrappers before making a new one
        if object.__getattribute__(wrapper,'_invalid'):
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        objhash = gpbcontainer.__hash__()
        dw = object.__getattribute__(wrapper,'DerivedWrappers')
        if dw.has_key(objhash):
            return dw[objhash]
        
        inst = cls(wrapper, gpbcontainer)
            
        # Add it to the list of objects which derive from the root wrapper
        dw[objhash] = inst
        return inst
        

    @property
    def Root(self):
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')

        return object.__getattribute__(self._wrapper,'Root')

    @property
    def Invalid(self):
        if not self._wrapper:
            return True
        return object.__getattribute__(self._wrapper,'_invalid')
    
    def Invalidate(self):
        self._gpbcontainer = None
        self._wrapper = None
        self.Repository = None
    
    def __setitem__(self, key, value):
        """Sets the item on the specified position.
        Depricated"""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        
        if not isinstance(value, Wrapper):
            raise OOIObjectError('To set an item in a repeated field container, the value must be a Wrapper')
        
        item = self._gpbcontainer.__getitem__(key)
        item = object.__getattribute__(self._wrapper,'_rewrap')(item)
        if object.__getattribute__(item,'ObjectType') == self.LinkClassType:
            self.Repository.set_linked_object(item, value)
        else:
            raise OOIObjectError('It is illegal to set a value of a repeated composit field unless it is a CASRef - Link')
         
        object.__getattribute__(self._wrapper,'_set_parents_modified')()
         
        
    def SetLink(self,key,value):
        
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        
        if not isinstance(value, Wrapper):
            raise OOIObjectError('To set an item in a repeated field container, the value must be a Wrapper')
        
        item = self._gpbcontainer.__getitem__(key)
        item = object.__getattribute__(self._wrapper,'_rewrap')(item)
        if object.__getattribute__(item,'ObjectType') == self.LinkClassType:
            self.Repository.set_linked_object(item, value)
        else:
            raise OOIObjectError('It is illegal to set a value of a repeated composit field unless it is a CASRef - Link')
         
        object.__getattribute__(self._wrapper,'_set_parents_modified')()
         
            
    def __getitem__(self, key):
        """Retrieves item by the specified key."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        value = self._gpbcontainer.__getitem__(key)
        value = object.__getattribute__(self._wrapper,'_rewrap')(value)
        if object.__getattribute__(value,'ObjectType') == self.LinkClassType:
            value = self.Repository.get_linked_object(value)
        return value
    
    def GetLink(self,key):
            
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        link = self._gpbcontainer.__getitem__(key)
        link = object.__getattribute__(self._wrapper,'_rewrap')(link)
        assert object.__getattribute__(link,'ObjectType') == self.LinkClassType, 'The field "%s" is not a link!' % linkname
        return link
        
    def GetLinks(self):
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        wrapper_list=[]            
        links = self._gpbcontainer[:] # Get all the links!
        for link in links:
            link = object.__getattribute__(self._wrapper,'_rewrap')(link)
            assert object.__getattribute__(link,'ObjectType') == self.LinkClassType, 'The field "%s" is not a link!' % linkname
            wrapper_list.append(link)
        return wrapper_list
    
    def __len__(self):
        """Returns the number of elements in the container."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        return self._gpbcontainer.__len__()
        
    def __ne__(self, other):
        """Checks if another instance isn't equal to this one."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')

        if not isinstance(other, self.__class__):
            raise OOIObjectError('Can only compare repeated composite fields against other repeated composite fields.')
        # The concrete classes should define __eq__.
        return not self._gpbcontainer == other._gpbcontainer

    def __eq__(self, other):
        """Compares the current instance with another one."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        
        if self is other:
            return True
        
        if not isinstance(other, self.__class__):
            raise OOIObjectError('Can only compare repeated composite fields against other repeated composite fields.')
        return self._gpbcontainer == other._gpbcontainer

    def __repr__(self):
        """Need to improve this!"""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        return self._gpbcontainer.__repr__()
        
        
    # Composite specific methods:
    def add(self):
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        new_element = self._gpbcontainer.add()
        
        object.__getattribute__(self._wrapper,'_set_parents_modified')()
        return object.__getattribute__(self._wrapper,'_rewrap')(new_element)
        
    def __getslice__(self, start, stop):
        """Retrieves the subset of items from between the specified indices."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        wrapper_list=[]
        for index in range(0, len(self))[start:stop]:
            wrapper_list.append(self.__getitem__(index))
            
        # Does it make sense to return a list?
        return wrapper_list
    
    def __delitem__(self, key):
        """Deletes the item at the specified position."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        object.__getattribute__(self._wrapper,'_set_parents_modified')()
            
        item = self._gpbcontainer.__getitem__(key)
        item = object.__getattribute__(self._wrapper,'_rewrap')(item)
            
        object.__getattribute__(item,'_clear_derived_message')()
            
        self._gpbcontainer.__delitem__(key)
        
    def __delslice__(self, start, stop):
        """Deletes the subset of items from between the specified indices."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        i_range = range(0, len(self))[start:stop]
        for index in reversed(i_range):
            self.__delitem__(index)
    
    
    
class ScalarContainerWrapper(object):
    """
    This class is only for use with containers.RepeatedCompositeFieldContainer
    It is not needed for repeated scalars!
    """
        
    def __init__(self, wrapper, gpbcontainer):
        # Be careful - this is a hard link
        self._wrapper = wrapper
        if not isinstance(gpbcontainer, containers.RepeatedScalarFieldContainer):
            raise OOIObjectError('The Container Wrapper is only for use with Repeated Composit Field Containers')
        self._gpbcontainer = gpbcontainer
        self.Repository = wrapper.Repository 

    @classmethod
    def factory(cls, wrapper, gpbcontainer):
        
        # Check the root wrapper objects list of derived wrappers before making a new one
        objhash = gpbcontainer.__hash__()
        dw = object.__getattribute__(wrapper,'DerivedWrappers')
        if dw.has_key(objhash):
            return dw[objhash]
        
        inst = cls(wrapper, gpbcontainer)
            
        # Add it to the list of objects which derive from the root wrapper
        dw[objhash] = inst
        return inst

    @property
    def Invalid(self):
        if not self._wrapper:
            return True
        return object.__getattribute__(self._wrapper,'_invalid')
    
    def Invalidate(self):
        self._gpbcontainer = None
        self._wrapper = None
        self.Repository = None
    
    def append(self, value):
        """Appends an item to the list. Similar to list.append()."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
           
        self._gpbcontainer.append(value)
        object.__getattribute__(self._wrapper,'_set_parents_modified')()

    def insert(self, key, value):
        """Inserts the item at the specified position. Similar to list.insert()."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
           
        self._gpbcontainer.insert(key, value)
        object.__getattribute__(self._wrapper,'_set_parents_modified')()

    def extend(self, elem_seq):
        """Extends by appending the given sequence. Similar to list.extend()."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
           
        self._gpbcontainer.extend(elem_seq)
        object.__getattribute__(self._wrapper,'_set_parents_modified')()

    def remove(self, elem):
        """Removes an item from the list. Similar to list.remove()."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
           
        self._gpbcontainer.remove(elem)
        object.__getattribute__(self._wrapper,'_set_parents_modified')()

    
    def __getslice__(self, start, stop):
        """Retrieves the subset of items from between the specified indices."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        return self._gpbcontainer._values[start:stop]

    def __len__(self):
        """Returns the number of elements in the container."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        return len(self._gpbcontainer._values)

    def __getitem__(self, key):
        """Retrieves the subset of items from between the specified indices."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        return self._gpbcontainer._values[key]

    def __setitem__(self, key, value):
        """Sets the item on the specified position."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
           
        self._gpbcontainer.__setitem__(key, value)
        object.__getattribute__(self._wrapper,'_set_parents_modified')()

    def __setslice__(self, start, stop, values):
        """Sets the subset of items from between the specified indices."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
           
        self._gpbcontainer.__setslice__(start, stop, values)
        object.__getattribute__(self._wrapper,'_set_parents_modified')()

    def __delitem__(self, key):
        """Deletes the item at the specified position."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
           
        del self._gpbcontainer._values[key]
        self._gpbcontainer._message_listener.Modified()
        object.__getattribute__(self._wrapper,'_set_parents_modified')()

    def __delslice__(self, start, stop):
        """Deletes the subset of items from between the specified indices."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
            
        self._gpbcontainer._values.__delslice__(start,stop)
        self._gpbcontainer._message_listener.Modified()
        object.__getattribute__(self._wrapper,'_set_parents_modified')()

    def __eq__(self, other):
        """Compares the current instance with another one."""
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        
        if self is other:
            return True
        # Special case for the same type which should be common and fast.
        if isinstance(other, self.__class__):
            return other._gpbcontainer._values == self._gpbcontainer._values
        # We are presumably comparing against some other sequence type.
        return other == self._gpbcontainer._values

    def __ne__(self, other):
        """Checks if another instance isn't equal to this one."""
        # The concrete classes should define __eq__.
        return not self == other

    def __repr__(self):
        if self.Invalid:
            raise OOIObjectError('Can not access Invalidated Object which may be left behind after a checkout or reset.')
        return repr(self._gpbcontainer._values)
    
    
class StructureElement(object):
    """
    @brief Wrapper for the container structure element. These are the objects
    stored in the hashed elements table. Mostly convience methods are provided
    here. A set provides references to the child objects so that the content
    need not be decoded to find them.
    """
    def __init__(self):
            
        self._element = container_pb2.StructureElement()
        self.ChildLinks = set()
        
    @classmethod
    def wrap_structure_element(cls,se):
        inst = cls()
        inst._element = se
        return inst
        
    @property
    def sha1(self):
        """
        Make the sha1 safe for empty contents but also type safe.
        Take use the sha twice so that we don't need to concatinate long strings!
        """
        #################
        ## This is the method that you can compare in Java
        #################
        ## Get the length of the binary arrays
        #sha_len = 20
        #type_len = self.type.ByteSize()
        #
        ## Convert to signed integer bytes
        #fmt = '!%db' % type_len
        #type_bytes = struct.unpack('!%db' % type_len , self.type.SerializeToString())
        #
        ## Convert the sha1 of the content to signed integer bytes
        #c_sha_bytes = struct.unpack('!20b', sha1bin(self.value))
        #
        ## Concatinate the the byte arrays as integers
        #cat_bytes = list(c_sha_bytes) + list(type_bytes)
        #
        ## Get the length of the concatination and convert to byte array
        #fmt = '!%db' % (type_len+sha_len)
        #sha_cat = struct.pack(fmt, *cat_bytes)
        #
        ##print 'sha1hex(sha_cat):',sha1hex(sha_cat)
        ##print 'sha1hex(sha1bin(self.value) + self.type.SerializeToString()):',sha1hex(sha1bin(self.value) + self.type.SerializeToString())
        #
        ## Return the sha1 of the byte array
        #return sha1bin(sha_cat)
        #################
        # This does the same thing much faster and shorter!
        #################
        return sha1bin(sha1bin(self.value) + self.type.SerializeToString())
        
    #@property
    def _get_type(self):
        return self._element.type
        
    #@type.setter
    def _set_type(self,obj_type):
        self._element.type.object_id = obj_type.object_id
        self._element.type.version = obj_type.version
     
    type = property(_get_type, _set_type)
     
    #@property
    def _get_value(self):
        return self._element.value
        
    #@value.setter
    def _set_value(self,value):
        self._element.value = value

    value = property(_get_value, _set_value)
        
    #@property
    def _get_key(self):
        #return sha1_to_hex(self._element.key)
        return self._element.key
        
    #@key.setter
    def _set_key(self,value):
        self._element.key = value

    key = property(_get_key, _set_key)
    
    def _set_isleaf(self,value):
        self._element.isleaf = value
        
    def _get_isleaf(self):
        return self._element.isleaf
    
    isleaf = property(_get_isleaf, _set_isleaf)
    
    def __str__(self):
        msg = ''
        if len(self._element.key)==20:
            msg  = 'Hexkey: "'+sha1_to_hex(self._element.key) +'"\n'
        return msg + self._element.__str__()
        
