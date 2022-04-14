from __future__ import print_function, unicode_literals
# -*- coding: utf8 -*-
"""
protlib builds on the struct and SocketServer modules in the standard
library to make it easy to implement binary network protocols. It provides 
support for default and constant struct fields, nested structs, arrays of
structs, better handling for strings and arrays, struct inheritance, and
convenient syntax for instantiating and using your custom structs.
"""
import sys
import codecs
import struct
import socket
import logging
import warnings
import traceback
from copy import deepcopy
from select import select
from warnings import warn
from StringIO import StringIO
from time import mktime, time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from logging import getLogger, Formatter, NOTSET, DEBUG, INFO, WARNING, ERROR, CRITICAL
from SocketServer import TCPServer, UDPServer, StreamRequestHandler, DatagramRequestHandler

StringTypes = (type(b""), type(""))
if sys.version_info[0] == 2:
    BytesIO = StringIO
    bytes = lambda x: str(bytearray(x))
else:
    from io import BytesIO

__all__ = ["CError", "CWarning",
           "CType", "CStruct", "CStructType", "CArray",
           "CChar", "CUChar", "CShort", "CUShort", "CInt", "CUInt", "CLong", "CULong", "CFloat", "CDouble", "CString", "CUnicode",
           "Parser", "Logger", "ProtHandler", "TCPHandler", "UDPHandler", "LoggingTCPServer", "LoggingUDPServer",
           "underscorize", "hexdump",
           "BYTE_ORDER", "AUTOSIZED"]

class CError(ValueError):
    """the only exception class raised directly by protlib"""

class CWarning(UserWarning):
    """the only warning class directly used by protlib (except DeprecationWarning)"""

__version_info__ = (1, 5, 0, "final", 0)
__version__ = "{0}.{1}.{2}".format(*__version_info__)

BYTE_ORDER = b"!"
AUTOSIZED = "AUTOSIZED"

def _to_bytes(x):
    s = x if isinstance(x, type(b"")) else x.__str__()
    return s.encode("utf8") if isinstance(s, unicode) else s

def _get_default(val):
    return val() if hasattr(val, "__call__") else deepcopy(val)

def _fileize(x):
    if isinstance(x, type("")):
        return StringIO(x)
    elif isinstance(x, type(b"")):
        return BytesIO(x)
    else:
        return x

def _no_codec(name):
    try:
        codecs.lookup(name)
    except:
        return True

def _is_open(sock):
    try:
        return isinstance(sock.fileno(), int) and sock.fileno() >= 0
    except:
        return False

def _inherit_docstrings(klass):
    for name,field in klass.__dict__.iteritems():
        parent = getattr(klass.__bases__[0], name, None)
        if hasattr(field, "__call__") and not field.__doc__ and parent:
            field.__doc__ = parent.__doc__
    return klass

def _read_until_null(f):
    s = b""
    f = _fileize(f)
    while True:
        c = f.read(1)
        if not c:
            raise CError("end of file reached with no null byte found")
        elif c == b"\0":
            break
        else:
            s += c      # shlemiel the painter
    return s

class _chained:
    def __init__(self, s, f):
        self.s, self.f = s, f
        self.has_read = b""
    
    def read(self, n):
        pos = len(self.has_read)
        if pos < len(self.s):
            data = self.s[pos : pos + n]
        else:
            data = self.f.read(n)
        self.has_read += data
        return data

class CType(object):
    """
    This is the root class of all classes representing C data types in the
    protlib library. It may not be directly instantiated; you must always
    use one of its subtypes instead.
    
    Whenever any CType is instantiated, it is appended to the
    CType.instances list. This is used internally to define the order of 
    fields in a CStruct. However, CStructs themselves are not added to this
    list unless CStruct.get_type() is called.
    
    Users of the protlib library don't need to know or care about this list,
    but they may find it useful for advanced usage.  Theoretically this list
    may cause your program's memory usage to grow if you continually
    instantiate CTypes as your program runs.  In this case you may need to 
    manually remove the CTypes from the end of this list after creating
    them.
    """
    instances = []
    
    def __init__(self, **settings):
        """
        CTypes have five optional keyword arguments:
        
        always -- Use this to set a constant value for a field. You won't
                  need to specify this value, and a warning will be raised
                  if the value ever differs from this parameter.
        
        default -- Like the always parameter, except that no warnings are
                   raised when a different value is assigned, parsed, or 
                   serialized. Also, unlike an always parameter, a default 
                   parameter may be either a value or a callable object.
        
        length -- required for CString, CUnicode, and CArray,
                  invalid for everything else
        
        encoding -- required for CUnicode, invalid for everything else
        
        enc_errors -- Only valid (but not required) for CUnicode, see the
                      unicode "errors" parameter for details.  This defaults
                      to "strict" but may be set to "ignore", "replace", etc
        
        full_string -- Only valid (but not required) for CString, set this
                       to True to prevent parsed string values frome being
                       truncated at the first null byte.
        """
        self.always = self.default = self.length = self.encoding = self.enc_errors = self.full_string = None
        extra = [name for name,val in settings.iteritems() if not hasattr(self, name)]
        if extra:
            warn("{0} settings do not include {1}".format(self.__class__.__name__, ", ".join(extra)), CWarning)
        
        self.__dict__.update(settings)
        if self.__class__ is CType:
            raise CError("CType may not be directly instantiated; use a subclass such as CInt, CString, etc")
        if self.length is not None and not isinstance(self, (CString, CUnicode, CArray)):
            warn("length has no meaning for {0} objects".format(self.__class__.__name__), CWarning)
        if isinstance(self, (CString, CUnicode, CArray)):
            if not isinstance(self.length, int) and not isinstance(self.length, StringTypes):
                raise CError("{0} objects require a string or integer length attribute".format(self.__class__.__name__))
            elif isinstance(self.length, int) and self.length < 0:
                raise CError("length integer value must be positive")
        if "full_string" in settings and not isinstance(self, CString):
            warn("full_string parameter has no meaning for {0} objects".format(self.__class__.__name__), CWarning)
        
        if isinstance(self, CUnicode):
            self.enc_errors = "strict" if self.enc_errors is None else self.enc_errors
            if not self.encoding:
                raise CError("CUnicode objects require an encoding parameter")
            elif _no_codec(self.encoding):
                raise CError("no codec exists for specified encoding {0!r}".format(self.encoding))
        else:
            for attr in ["encoding","enc_errors"]:
                if getattr(self, attr):
                    raise CError("{0} parameter is not valid for {0} objects".format(attr, self.__class__.__name__))
        
        self.instances.append(self)
    
    @property
    def maybe(self):
        """either the always or default value as appropriate"""
        return self.always if self.always is not None else _get_default(self.default)
    
    def real_length(self, cstruct):
        """
        CArray and CString fields may be given variable lengths by setting
        their length field to a string representing the name of the other field
        in the containing CStruct subclass whose value is their length.  This
        method returns the integer length value of any CType (which is None
        for types other than CString and CArray), computing it if necessary
        by extracting the actual value from the given cstruct instance.  This
        method raises an error if the computed length is negative.
        """
        if isinstance(self.length, (int, type(None))):
            return self.length
        
        if cstruct is None:
            raise CError("cstruct not provided to resolve variable-length field with length attribute {0!r}".format(self.length))
        
        if self.length is AUTOSIZED:
            field_name = dict((v,k) for k,v in cstruct.__class__.__dict__.iteritems() if getattr(v, "__hash__", None))[self]
            field_val = getattr(cstruct, field_name)
            try:
                return len(self.serialize(field_val, cstruct))
            except:
                raise CError("{0}.{1} is set to a non-string value: {2!r}".format(cstruct.__class__.__name__, field_name, field_val))
            return len(serialized)
        else:
            length = getattr(cstruct, self.length, None)
            if isinstance(length, (CType, type(None))):
                raise CError("{0}.{1} not set and is needed for use as a length attribute".format(cstruct.__class__.__name__, self.length))
            elif not isinstance(length, int):
                raise CError("{0}.{1} must be an integer for use as a length attribute and was actually {2}".format(cstruct.__class__.__name__, self.length, length.__class__.__name__))
            elif length < 0:
                raise CError("length field {0}.{1} may not be negative".format(cstruct.__class__.__name__, self.length))
            return length
    
    def struct_format(self, cstruct=None):
        """the format string used to represent this CType in the struct module"""
        formats = {
            CChar:    b"b",
            CUChar:   b"B",
            CShort:   b"h",
            CUShort:  b"H",
            CInt:     b"i",
            CUInt:    b"I",
            CLong:    b"q",
            CULong:   b"Q",
            CFloat:   b"f",
            CDouble:  b"d",
            CString:  _to_bytes("{0}s".format(self.real_length(cstruct))),
            CUnicode: _to_bytes("{0}s".format(self.real_length(cstruct)))
        }
        for ctype,format in formats.iteritems():
            if isinstance(self, ctype):
                return format
    
    def sizeof(self, cstruct=None):
        """the number of bytes of binary data needed to represent this CType"""
        return struct.calcsize(BYTE_ORDER + self.struct_format(cstruct))
    
    def convert(self, x):
        """
        When a value is assigned to a struct field, this function
        is converts the value appropriately, for example:
        
        >>> class Point(CStruct):
        ...     x = CInt()
        ...     y = CInt()
        ... 
        >>> Point(x = "5", y = 6.0)
        Point(x=5, y=6)
        
        If you subclass one of the CType classes, you may need to
        override this method.
        """
        for klass,converter in _converters.iteritems():
            if isinstance(self, klass):
                return converter(x)
        raise CError("no converter found for {0}".format(self.__class__.__name__))
    
    def parse(self, f, cstruct=None):
        r"""
        Accepts either a string or a file and returns a Python object with 
        the appropriate value.  For example, CInt().parse will return a 
        Python int, etc.  This raises CError if not given enough data.
        
        CString parsing returns the string up to the first null byte, e.g.
        
        CString(length=10).parse(b"foo\0barbaz") -> b"foo"
        """
        buf = _fileize(f).read( self.sizeof(cstruct) )
        if len(buf) < self.sizeof(cstruct):
            raise CError("{0} requires {1} bytes and was given {2}".format(self.__class__.__name__, self.sizeof(cstruct), len(buf)))
        return struct.unpack(BYTE_ORDER + self.struct_format(cstruct), buf)[0]
    
    def serialize(self, val, cstruct=None):
        r"""
        Serializes the given value into binary data using the struct module.
        
        Unserializable problems with the value will raise a CError, e.g.
            CShort().serialize( 2 ** 17 )       # value too large
            CLong().serialize("hello")          # wrong data type
            CArray(5, CInt).serialize([2,3])    # not enough elements
        
        Passing a too-short list to a CArray is okay if a default value
        was provided:
            CArray(2, CChar(default=0)).serialize([1]) -> b"\x01\0"
        
        Passing too much data to a CArray or CString will trigger a
        CWarning, e.g.
            CArray(2, CInt).serialize([5,6,7])
            CString(length=3).serialize(b"Hello")
        
        Passing a too-short string to a CString is always okay:
            CString(length=4).serialize(b"Hi") -> b"Hi\0\0"
        """
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", DeprecationWarning)
                return struct.pack(BYTE_ORDER + self.struct_format(cstruct), val)
        except Exception as exc:
            raise CError("{0!r} is not serializable as a {1}: {2}".format(val, self.__class__.__name__, exc))

class CChar(CType): pass
class CUChar(CType): pass
class CShort(CType): pass
class CUShort(CType): pass
class CInt(CType): pass
class CUInt(CType): pass
class CLong(CType): pass
class CULong(CType): pass
class CFloat(CType): pass
class CDouble(CType): pass

@_inherit_docstrings
class CString(CType):
    def parse(self, f, cstruct=None):
        if self.length is AUTOSIZED:
            return _read_until_null(f)
        else:
            s = CType.parse(self, f, cstruct)
            if not self.full_string:
                s = s.split(b"\0")[0]
            return s
    
    def serialize(self, val, cstruct=None):
        if self.length is AUTOSIZED:
            return val.split(b"\0", 1)[0] + b"\0"
        else:
            if len(val) > self.real_length(cstruct):
                warn("CString has length {0} and was told to serialize a string of length {1}".format(self.real_length(cstruct), len(val)), CWarning)
            return CType.serialize(self, val, cstruct)

@_inherit_docstrings
class CUnicode(CType):
    def parse(self, f, cstruct=None):
        if self.length is not AUTOSIZED:
            return CType.parse(self, f, cstruct).split(b"\0")[0].decode(self.encoding, self.enc_errors)
        else:
            s = _read_until_null(f)
            try:
                return s.decode(self.encoding, self.enc_errors)
            except Exception as exc:
                raise CError("unicode error parsing {0!r}: {1}".format(s, exc))
    
    def serialize(self, val, cstruct=None):
        try:
            encoded = self.convert(val).encode(self.encoding, self.enc_errors)
        except Exception as exc:
            raise CError("unicode error serializing {0!r}: {1}".format(val, exc))
        
        if self.length is AUTOSIZED:
            return encoded + b"\0"
        else:
            if len(encoded) > self.real_length(cstruct):
                warn("CUnicode value has length {0} and was told to serialize an encoded string of length {1} {2!r}".format(self.real_length(cstruct), len(encoded), encoded), CWarning)
            return CType.serialize(self, encoded, cstruct)
    
    def convert(self, x):
        return x if isinstance(x, unicode) else unicode(_to_bytes(x), self.encoding, self.enc_errors)

@_inherit_docstrings
class CArray(CType):
    def __init__(self, length, ctype, **params):
        """
        You can make an array of any CType, including other arrays. Arrays
        pack and unpack to and from Python lists.  Arrays may either be
        given default/always values themselves or use the default/always
        values of  the CType they are given.  Here are some example CArray
        declarations:

        CArray(5, CInt)
        CArray(5, CString(length=4))
        CArray(8, CLong(default=0))
        CArray(3, CInt, always=[0,0,0])
        CArray(5, CArray(4, CShort))
        """
        if type(ctype) is type and issubclass(ctype, CType):    # CArray(10, CInt) and CArray(10, CInt()) are both allowed
            if issubclass(ctype, CStruct):                      # CArray(10, MyStruct) and CArray(10, MyStruct.get_type()) are both allowed
                ctype = ctype.get_type()
            else:
                ctype = ctype()
        
        if not isinstance(ctype, CType):
            raise CError("Second argument to CArray must be a CType e.g. CInt, CFloat, etc")
        elif isinstance(ctype, CStruct):
            ctype = ctype.__class__
            warn("Second argument to CArray should just be the class {0} rather than an instance of that class".format(ctype.__name__), CWarning)
        
        self.ctype = ctype
        
        for param in ["default","always"]:
            if isinstance(length, int) and param not in params and getattr(self.ctype, param) is not None:
                params[param] = [_get_default(getattr(self.ctype, param)) for i in xrange(length)]
        
        CType.__init__(self, length=length, **params)
        
        for param,value in [("always",self.always), ("default",self.default)]:
            if value is not None and not isinstance(self.length, StringTypes):
                try:
                    value = _get_default(value) if param == "default" else value
                    self.serialize( self.convert(value) )
                except Exception as exc:
                    raise CError("{0!r} is not a valid {1} CArray value: {2}".format(value, param, exc))
    
    def struct_format(self, cstruct=None):
        return self.ctype.struct_format() * self.real_length(cstruct)
    
    def parse(self, f, cstruct=None):
        f = _fileize(f)
        return [self.ctype.parse(f, cstruct) for i in xrange(self.real_length(cstruct))]
    
    def serialize(self, xs, cstruct=None):
        length = self.real_length(cstruct)
        if len(xs) > length:
            warn("CArray has length {0} and was given {1} elements".format(length, len(xs)), CWarning)
            xs = xs[:length]
        elif len(xs) < length:
            if self.maybe is not None or self.ctype.maybe is not None:
                default = self.maybe or []
                if self.ctype.maybe is not None:
                    default += [self.ctype.maybe for i in xrange(length - len(default))]
                xs = xs + default[len(xs):]     # avoid += to not mutate the original list
            if len(xs) < length:
                raise CError("CArray has length {0} and was only given {1} elements".format(length, len(xs)))
        
        return b"".join(self.ctype.serialize(x, cstruct) for x in self.convert(xs))
    
    def convert(self, x):
        return [self.ctype.convert(e) for e in x]

@_inherit_docstrings
class CStructType(CType):
    """
    When defining your own struct, you subclass CStruct and give it the
    proper fields:
    
    class Point(CStruct):
        x = CInt()
        y = CInt()
    
    This type is used to include one struct inside another:
    
    class Segment(CStruct):
        p1 = Point.get_type()
        p2 = Point.get_type()
    
    Each call to get_type() returns a CStructType instance, which is used
    to represent the struct type being used.  Other than calling get_type(),
    protlib users should probably never need to interact with this class
    directly.
    """
    def __init__(self, subclass, **params):
        """
        In addition to the usual keyword arguments accepted by CTypes,
        this constructor takes the CStruct subclass being represented.
        """
        self.subclass = subclass
        CType.__init__(self, **params)
    
    def struct_format(self, cstruct=None):
        return b"".join(ctype.struct_format(cstruct) for name,ctype in self.subclass.get_fields())
    
    def parse(self, f, cstruct=None):
        f = _fileize(f)
        inst = self.subclass()
        for name,ctype in self.subclass.get_fields():
            val = ctype.parse(f, cstruct=inst)
            setattr(inst, name, val)
        return inst
    
    def serialize(self, inst, cstruct=None):
        serialized = b""
        for name,ctype in self.subclass.get_fields():
            val = inst.__dict__.get(name)
            if val is None:
                if isinstance(ctype, CArray):
                    if ctype.real_length(inst) == 0:
                        val = []
                    else:
                        for maybe in [ctype.default, ctype.always, ctype.ctype.default, ctype.ctype.always]:
                            if maybe is not None:
                                val = []
                elif isinstance(ctype, (CString, CUnicode)) and ctype.real_length(inst) == 0:
                    val = b""
            if val is None:
                raise CError(name + " not set")
            serialized += ctype.serialize(val, cstruct=inst)
        return serialized
    
    def convert(self, x):
        return x

class CStruct(CType):
    def __init__(self, *args, **values):
        """
        CStruct should never be instantiated directly. Instead, you should
        subclass it when defining a custom struct. Your subclass will be
        given a constructor which takes the fields of your struct as
        positional and/or keyword arguments. However, you don't have to
        provide values for your fields at this time; you can leave struct
        fields unset, although a CError will be raised if you call the 
        serialize method on a CStruct with unset fields.
        """
        if self.__class__ is CStruct:
            raise CError("CStruct may not be instantiated directly; define a subclass instead")
        
        fields = self.get_fields()
        if not fields:
            raise CError("{0} struct contains no CType fields".format(self.__class__.__name__))
        
        field_names = list(zip(*fields))[0]
        for i,arg in enumerate(args):
            name = field_names[i]
            if name in values and values[name] != arg:
                raise CError("{0} was given a value of {1!r} as a positional argument and {2!r} as a keyword argument".format(name, arg, values[name]))
            values[name] = arg
        
        non_fields = [name for name,value in values.iteritems() if name not in field_names]
        if non_fields:
            warn("{0} fields ({1}) do not include {2}".format(self.__class__.__name__, ", ".join(field_names), ", ".join(non_fields)), CWarning)
        
        for name,ctype in fields:
            if ctype.maybe is not None:
                setattr(self, name, _get_default(ctype.maybe))
            elif isinstance(ctype, (CString, CUnicode)) and isinstance(ctype.length, StringTypes) \
                    and ctype.length is not AUTOSIZED \
                    and not isinstance(getattr(self, ctype.length), CType) \
                    and ctype.real_length(self) == 0:
                setattr(self, name, b"")
            elif isinstance(ctype, CArray) and isinstance(ctype.length, StringTypes) and ctype.ctype.maybe is not None \
                    and not isinstance(getattr(self, ctype.length), CType):
                setattr(self, name, [_get_default(ctype.ctype.maybe) for i in xrange(ctype.real_length(self))])
            
            if name in values:
                setattr(self, name, values[name])   # set after setting default values to detect invalid defaults
    
    @classmethod
    def get_fields(cls):
        """
        Returns a list of name/value pairs representing this struct's
        fields.  Each pair is the name of the field and the CType instance
        which defines that field.  The list is sorted according to the
        order in which the fields appear in the struct.
        
        Users probably don't need to call this method unless they need to
        introspect their own CStruct subclasses.
        """
        if cls is CStruct:
            raise CError("CStruct classmethods may only be called on subclasses of CStruct")
        
        if "_fields" not in cls.__dict__:   # avoid hasattr because of subclasses
            uninstantiated = [ctype for name,ctype in cls.__dict__.iteritems()
                                    if type(ctype) is type and issubclass(ctype,CType)]
            if uninstantiated:
                raise CError("Use {0}{2} instead of {0} when declaring a field in your {1} struct".format(uninstantiated[0].__name__, cls.__name__, ".get_type()" if issubclass(uninstantiated[0],CStruct) else "()"))
            
            directly = [cstruct for name,cstruct in cls.__dict__.iteritems() if isinstance(cstruct, CStruct)]
            if directly:
                raise CError("Use {0}.get_type() instead of {0}() when declaring a field in your {1} struct".format(directly[0].__class__.__name__, cls.__name__))
            
            top = cls
            while CStruct not in top.__bases__:
                for base in top.__bases__:
                    if issubclass(top, CStruct):
                        top = base
                    break
            
            if top is cls:
                fields = [[name,ctype] for name,ctype in cls.__dict__.iteritems() if isinstance(ctype, CType)]
                fields.sort(key = lambda pair: CType.instances.index(pair[1]))
                
                positions = [(CType.instances.index(ctype),name,ctype) for name,ctype in fields]
                for i in xrange(1, len(positions)):
                    if positions[i][0] == positions[i-1][0]:
                        warn("{0} and {1} were declared with the same {2} object; the order of such fields is undefined".format(positions[i-1][1], positions[i][1], positions[i][2].__class__.__name__), CWarning)
                        break
            else:
                fields = deepcopy( top.get_fields() )
                for pair in fields:
                    final = getattr(cls, pair[0])
                    if not isinstance(final, CType):
                        raise CError("{0} field overridden by non-CType {1!r}".format(pair[0], final))
                    elif type(final.length) is not type(pair[1].length) \
                            or not isinstance(final.length, StringTypes) and final.sizeof() != pair[1].sizeof():
                        raise CError("{0[0]} field of type {0[1]} was overridden by differently-sized type {1}".format(pair, final.__class__.__name__))
                    pair[1] = final
            
            names = [name for name,ctype in fields]
            for (i,(name,ctype)) in enumerate(fields):
                if isinstance(ctype.length, StringTypes) and ctype.length in names[i+1:]:      # shlemeil the painter
                    raise CError("{0}.{1} is the length field for {0}.{2} but appears after it in the struct".format(cls.__name__, ctype.length, name))
            
            cls._fields = fields
        return cls._fields
    
    @classmethod
    def get_type(cls, cached=False, **params):
        """
        Returns a CStructType instance representing this struct; see the
        CStructType class for details.
        
        cached -- Indicates whether it's acceptable to return a cached
                  CStructType instance, or whether a new CStructType should
                  be created.  This should never be set to True when using
                  this method to include one struct inside another struct, 
                  which is probably the only time that users will ever call
                  this method.  In other words, if you're not sure whether
                  you should include this parameter, then you shouldn't.
        """
        if cls is CStruct:
            raise CError("CStruct classmethods may only be called on subclasses of CStruct")
        
        if not ("_type" in cls.__dict__ and cached):    # avoid hasattr because of subclasses
            cls._type = [CStructType(cls, **params)]    # stored in a list so that isinstance(self._type, CType) will evaluate to false
        return cls._type[0]
    
    @classmethod
    def parse(cls, f):
        """
        Returns an instance of this CStruct by parsing the input from the
        string or file given as a parameter.  This raises a CError if not
        enough data is provided.
        """
        return cls.get_type(cached=True).parse(f)
    
    @classmethod
    def sizeof(cls, cstruct=None):
        """
        Returns the number of bytes needed to represent this CStruct as
        packed binary data.
        """
        return cls.get_type(cached=True).sizeof(cstruct)
    
    @classmethod
    def struct_format(cls, cstruct=None):
        """
        Returns the struct format string used by the struct module to pack
        and unpack this CStruct.
        """
        return cls.get_type(cached=True).struct_format(cstruct)
    
    def serialize(self):
        """
        Returns packed binary data which represents this CStruct instance.
        This raises a CError if any of the fields have not been set.
        """
        return self.get_type(cached=True).serialize(self)
    
    def __repr__(self):
        """
        Returns a literal representation of this struct.  This may be
        copy/pasted into a Python file or interpreter as valid code.  For
        example:
        
        repr(Point(x=5, y=6)) == str(Point(x=5, y=6)) == "Point(x=5, y=6)"
        """
        params = ["{0}={1!r}".format(name, getattr(self,name))
                  for name,ctype in self.get_fields() if name in self.__dict__]
        return "{0}({1})".format(self.__class__.__name__, ", ".join(params))
    
    __str__ = __repr__
    
    @property
    def hashable(self):
        if not hasattr(self, "_hashable"):
            xs = [getattr(self, name, None) for name,ctype in self.get_fields()]
            self._hashable = tuple(tuple(x) if isinstance(x, list) else x for x in xs)
        return self._hashable
    def __hash__(self):
        return hash(self.hashable)
    def __eq__(self, other):
        return self.hashable == getattr(other, "hashable", None)
    def __ne__(self, other):
        return not (self == other)          # Python is stupid for making me do this
    
    def __setattr__(self, name, value):
        """
        Whenever you assign a value to a struct field, that value is
        converted to the appropriate data type.  So if you assign the
        string "5" to a CInt field, it will be converted to the int 5.
        This triggers a CWarning if data is truncated, such as when a
        float is assigned to an integer field, or when a string or list
        is too long.
        
        CChar and CUChar fields may either be assigned an integer or a
        single-character string.  Such strings are converted to integers
        with the builtin ord function.  Thus, while assigning a CInt field
        the value of "5" converts to the int 5, assigning the value "5" to
        a CChar converts to the int 53.
        """
        field = getattr(self.__class__, name, None)
        if isinstance(field, CStructType):
            if not isinstance(value, field.subclass):
                raise CError("{0} assigned to the {1} field {2}.{3}".format(value.__class__.__name__, field.subclass.__name__, self.__class__.__name__, name))
        elif isinstance(field, CType):
            try:
                value = field.convert(value)
            except Exception as exc:
                raise CError("Conversion error: you provided the {0} value {1!r} to the {2} field {3}.{4}: {5}".format(value.__class__.__name__, value, field.__class__.__name__, self.__class__.__name__, name, exc))
            
            try:
                field.serialize(value, cstruct=self)
            except Exception as exc:
                raise CError("{0!r} is an invalid value for the {1} field {2}.{3}: {4}".format(value, field.__class__.__name__, self.__class__.__name__, name, exc))
            
            if field.always is not None and value != field.always:
                warn("{0}.{1} should always be {2!r} but was given a value of {3!r}".format(self.__class__.__name__, name, field.always, value), CWarning)
        
        object.__setattr__(self, name, value)

_converters = {
    CFloat:   float,
    CDouble:  float,
    CString:  _to_bytes,
    CChar:    lambda c: ord(c) if isinstance(c, StringTypes) else int(c),
    CUChar:   lambda c: ord(c) if isinstance(c, StringTypes) else int(c)
}
def _to_int(x):
    if isinstance(x, float) and x != int(x):
        warn("Loss of precision when converting a float ({0}) to an integer field".format(x), CWarning)
    return int(x)
_converters.update((ctype, _to_int) for ctype in [CShort, CUShort, CInt, CUInt, CLong, CULong])

_formatter = Formatter("%(asctime)s: %(message)s")

class _AlsoPrint(logging.Handler):
    def emit(self, record):
        print(_formatter.format(record))

class _NullHandler(logging.Handler):
    def emit(self, record):
        pass

def underscorize(camelcased):
    """
    Takes a CamelCase string and returns a separated_with_underscores
    version of that name in all lower case.  If the name is already all in
    lower case and/or separated with underscores, then the returned string
    is identical to the original.  This function is used to take CStruct
    class names and determine the names of their handler methods.
    
    Here are some example conversions:
        underscorize("SomeStruct")   == "some_struct"
        underscorize("SSNLookup")    == "ssn_lookup"
        underscorize("RS485Adaptor") == "rs485_adaptor"
        underscorize("Rot13Encoded") == "rot13_encoded"
        underscorize("RequestQ")     == "request_q"
        underscorize("John316")      == "john316"
    """
    underscored, prev = "", ""
    for i,c in enumerate(camelcased):
        if (prev and not c.islower() and c != "_"
                 and (prev.islower() and not c.isdigit()
                      or c.isupper() and camelcased[i+1:i+2].islower())):
            underscored += "_"
        underscored += c.lower()
        prev = c
    return underscored

def hexdump(data):
    """
    Returns a multi-line string containing a nicely formatted table of the
    hexadecimal representation of the ordinal values of each character in
    the string passed as a parameter.
    """
    pad = b"0" if isinstance(hex(0), type(b"")) else "0"
    hexed = [hex(byte if isinstance(byte, int) else ord(byte))[2:].rjust(2, pad) for byte in data]
    lines = ["     0  1  2  3  4  5  6  7"]
    for i in xrange(0, len(hexed), 8):
        lines.append("%3i  " % i + " ".join(hexed[i:i+8]))
    return "\n".join(lines)

class Parser(object):
    """
    The classmethod CStruct.parse may be used to read struct objects from
    strings or files, such as by saying "p = Point.parse(f)", but this
    requires that you know the type of struct you need to parse.  This
    class exists to check the data being parsed to see which struct is being
    read with error checking and logging as appropriate.
    """
    def __init__(self, logger=None, module=None):
        """
        Arguments:
        
        logger - The instance of the Logger class to use to perform logging.
                 If omitted, a Logger will be created with a handler whose
                 level is 1 + logging.CRITICAL
        
        module - This is exactly the same as the ProtHandler.STRUCT_MOD
                 field; if present then it indicates which module contains
                 the struct classes you want to use. If omitted, then the
                 module where this class is instantiated is used.
                 
                 CError is raised if no CStruct subclasses exist in this
                 module, and a CWarning is triggered if multiple CStruct
                 subclasses are found which begin with the same constant
                 values.
                 
                 This class only detects structs which were defined when
                 it was instantiated.  Structs defined afterwards will not
                 be detected.
        """
        self.logger = logger or Logger(rfh_level=CRITICAL+1)
        
        if not module and hasattr(sys, "_getframe"):
            globs = sys._getframe().f_back.f_globals
        elif not module:
            raise CError("module argument is required for non-CPython interpreters")
        else:
            if isinstance(module, str):
                module = __import__(module)
            globs = module.__dict__
        
        self.structs = [cstruct for name,cstruct in globs.iteritems()
                        if type(cstruct) is type and issubclass(cstruct,CStruct) and cstruct is not CStruct]
        self.codes = []
        for cstruct in self.structs:
            first = cstruct.get_fields()[0][1]
            if first.always is not None:
                self.codes.append( (first.serialize(first.always), cstruct) )
        self.codes.sort(key = lambda code: len(code[0]))
        if not self.codes:
            raise CError("No structs which begin with constant values were defined in the module " + (module.__name__ if module else "where you instantiated Parser"))
        
        bufs = list(zip(*self.codes))[0]
        while bufs:
            matches = [b for b in bufs if bufs[0] == b[:len(bufs[0])]]
            if len(matches) > 1:
                structs = ", ".join(cstruct.__name__ for buf,cstruct in self.codes if buf in matches)
                warn("{0} structs exist which always begin with {1!r}: {2}".format(len(matches), bufs[0], structs), CWarning)
            bufs = [b for b in bufs if b not in matches]
    
    def parse(self, f):
        """
        Accepts a string or file object and returns a string or CStruct
        according to these rules:
         - If a CStruct can be successfully parsed, then it's logged
           and returned.
         - If the data does not correspond to any CStruct, then all
           available data is logged and returned.
         - If the data represents a certain CStruct, but is too short,
           then an error is logged and None is returned.
        """
        f = _fileize(f)
        buf = b""
        for code,cstruct in self.codes:
            diff = len(code) - len(buf)
            if diff:
                buf += f.read(diff)
                if len(buf) < len(code):
                    break
            
            if code == buf:
                chained = _chained(buf, f)
                try:
                    inst = cstruct.parse(chained)
                    self.logger.log_struct(inst, "received")
                    return inst
                except CError as ce:
                    self.logger.log_error("{0} struct received only {1} bytes".format(cstruct.__name__, len(chained.has_read)))
                    return
                finally:
                    self.logger.log_binary(chained.has_read, "received")
        else:
            buf += f.read()
        
        if buf:
            self.logger.log_binary(buf, "received")
        return buf

class Logger(object):
    """
    This class is used by the ProtHandler subclasses to log the messages
    sent and received by the LoggingTCPServer and LoggingUDPServer classes.
    The protlib handler classes inherit from this class, so you won't need
    to instantiate this class directly when writing server programs, but
    you may find this class useful when writing client programs.
    
    Internally this class uses the logging module from the standard library.
    Each log name has a prefix, which by default is the name of the script
    being executed, and a suffix.  There are 5 logs, each with their own
    suffix: hex, raw, struct, error, and stack.  For example, if you're
    running the script "server.py" then these will be the log names and the
    logging levels of their messages:
    
    server.hex - DEBUG level, contains nicely formatted hex dump of the
                 binary data sent and received
    
    server.raw - INFO level, contains Python string literals of the binary
                 data sent and received
    
    server.struct - WARNING level, contains literal representations of each
                    struct sent and received
    
    server.error - ERROR level, contains error messages
    
    server.stack - CRITICAL level, contains stack traces of exceptions
                   thrown by handler methods
    
    For each log, if no handlers already exist, then a RotatingFileHandler
    with a Formatter is instantiated, using the MAX_BYTES and BACKUP_COUNT
    fields for the maxBytes and backupCount parameter, and creating a log
    file in the current directory.  If you'd like to use different handlers
    for your logging, you can simply your own handler(s) and formatter(s)
    for any or all of these logs, and then they will be used instead.  You
    must do this before this class is instantiated, or else your handler(s)
    will simply be used in addition to the default RotatingFileHander.
    
    By default, each of these loggers has its propagate field set to False.
    """
    BACKUP_COUNT = 1
    MAX_BYTES = 1024 ** 2
    DEFAULT_PREFIX = sys.argv[0].split(".")[0] or "__main__"
    LEVELS = {"hex":DEBUG, "raw":INFO, "struct":WARNING, "error":ERROR, "stack":CRITICAL}
    
    def __init__(self, prefix=None, also_print=False, rfh_level=NOTSET, hex_logging=None, log_dir=None):
        """
        Arguments (hex_logging and log_dir are deprecated):
        
        prefix - overrides the default prefix for the log names
        
        also_print - if True, log messages will be printed to the screen
                     in addition to whatever else happens to them
        
        rfh_level - used internally to set the the logging level of the
                    default RotatingFileHandler
        """
        if log_dir:
            warn("log_dir parameter is deprecated and ignored, you should use the logging.handler classes to affect log locations and properties", DeprecationWarning)
        if hex_logging:
            warn("hex_logging parameter is deprecated and ignored, hex dumps are now written to their own separate log", DeprecationWarning)
        
        self.__prefix = prefix or self.DEFAULT_PREFIX
        for suffix in self.LEVELS:
            logger = getLogger(self.__prefix + "." + suffix)
            logger.propagate = False
            
            if not logger.handlers:
                try:
                    delay = sys.version_info[:3] >= (2, 6, 2)
                    handler = RotatingFileHandler(logger.name+"_log", maxBytes=self.MAX_BYTES, backupCount=self.BACKUP_COUNT, delay=delay)
                    handler.setFormatter(_formatter)
                    handler.setLevel(rfh_level)
                except IOError:
                    handler = _NullHandler()    # directory not writable
                
                logger.addHandler(handler)
            
            if also_print:
                logger.addHandler( _AlsoPrint() )
    
    def log_binary(self, data, trans_type="received"):
        """
        Writes the data string to the raw and hex logs.  The trans_type is
        prepended to each log message and indicates whether this data was
        just received or is about to be sent.
        """
        self.log("hex", trans_type + "\n" + hexdump(data))
        self.log("raw", trans_type + " " + repr(data))
    
    def log_raw(self, data, trans_type="received"):
        """deprecated alias for log_binary"""
        warn("log_raw is deprecated, use log_binary instead", DeprecationWarning)
        self.log_binary(data, trans_type)
    
    def log_struct(self, inst, trans_type="received"):
        """
        Writes a CStruct instance to the struct log.  The trans_type is
        prepended to each log message and indicates whether this data was
        just received or is about to be sent.  
        """
        self.log("struct", trans_type + " " + repr(inst))
    
    def log_error(self, message, *args, **kwargs):
        """
        Writes a message to the error log, calling str.format with the
        extra positional and keyword arguments passed to this function.
        """
        self.log("error", message.format(*args, **kwargs))

    def log_stacktrace(self):
        """writes a stacktrace from the last thrown exception to the stack log"""
        self.log("stack", traceback.format_exc())
    
    def log_and_write(self, f, data):
        """
        Given a file object and a string or CStruct object, log it to
        the appropriate logs, then write it to the file.
        """
        if isinstance(data, CStruct):
            self.log_struct(data, "sending")
            data = data.serialize()
        self.log_binary(data, "sending")
        f.write(data)
    
    def log(self, suffix, message):
        """
        Write a message to the specified log; the suffix parameter should be
        one of "hex", "raw", "struct", "error", or "stack".
        """
        getLogger(self.__prefix + "." + suffix).log(self.LEVELS[suffix], message)

class ProtHandler(Logger):
    """
    Root class for protocol handerls, which itself inherits from Logger for
    ease of providing informative logging for handler methods.  Do not
    subclass this class directly; instead you should subclass either the
    TCPHandler or UDPHandler class, as appropriate.
    """
    LOG_PREFIX = LOG_TO_SCREEN = STRUCT_MOD = False
    
    def __init__(self, server=None):
        """you'll probably never need to instantiate this class directly"""
        if hasattr(self, "LOG_DIR"):
            warn("LOG_DIR field is deprecated and ignored, you should use the logging.handler classes to affect log locations and properties", DeprecationWarning)
        if hasattr(self, "HEX_LOGGING"):
            warn("HEX_LOGGING field is deprecated and ignored, hex dumps are now written to their own separate log", DeprecationWarning)
        if not self.STRUCT_MOD and not hasattr(sys, "_getframe"):
            raise CError("STRUCT_MOD must be defined for non-CPython interpreters")
        
        Logger.__init__(self, prefix = self.LOG_PREFIX, also_print = self.LOG_TO_SCREEN,
                              rfh_level = INFO if isinstance(server, (LoggingTCPServer, LoggingUDPServer, type(None))) else 1+CRITICAL)
        self.__parser = Parser(logger=self, module=self.STRUCT_MOD or self.__class__.__module__)
        
        for buf,cstruct in self.__parser.codes:
            if underscorize(cstruct.__name__) in dir(TCPHandler):
                raise CError("You can't name your struct {0} because that's also the name of a standard handler method".format(cstruct.__name__))
        
        self.__handled = 0
        self.__prefix = int(mktime( datetime.now().timetuple() ))
    
    def log(self, suffix, message):
        """
        Overrides Logger.log to add a prefix to every log message which
        uniquely identifies the binary data being sent/received.
        """
        message = "({0}_{1}) {2}".format(self.__prefix, self.__handled, message)
        Logger.log(self, suffix, message)
    
    def dispatch(self, data):
        """
        Given a string or cstruct, this calls the appropriate handler method
        and returns the result.  If no handler method exists for a cstruct,
        an error is logged.
        """
        if isinstance(data, StringTypes):
            return self.raw_data(data)
        
        codename = underscorize(data.__class__.__name__)
        if not hasattr(self, codename):
            self.log_error("{0} handler not defined", codename)
        else:
            return getattr(self, codename)(data)
    
    def reply(self, data):
        """given a string or cstruct, log the data and write it to self.wfile"""
        if isinstance(data, CStruct):
            self.log_struct(data, "sending")
            data = data.serialize()
        self.log_binary(data, "sending")
        self.wfile.write(data)
        self.wfile.flush()
    
    def raw_data(self, data):
        """
        Default handler for raw data.  Override this method if you want to
        actually respond to data which is not parsable into a cstruct.  By
        default this method simply logs an error.
        """
        if data:
            self.log_error("unable to resolve {0!r} to a struct", data)
    
    def handle(self):
        """
        Continually reads data from self.rfile and calls the appropriate
        handler method until no more data is available.
        """
        try:
            data = self.__parser.parse(self)
            while data:
                response = self.dispatch(data)
                if response:
                    self.reply(response)
                
                self.__handled += 1
                data = self.__parser.parse(self)
        except:
            self.log_stacktrace()

class TCPHandler(ProtHandler, StreamRequestHandler):
    """
    Subclass this class for use with the SocketServer.TCPServer class or any
    of its subclasses, such as protlib.LoggingTCPServer
    
    This class overrides the rbufsize field of StreamRequestHandler, setting
    it to 0.  This allows calls to self.rfile.read to not interfere with
    calls to self.socket.recv, at the cost of being less efficient.
    """
    rbufsize = 0
    timeout = None
    
    def __init__(self, request, client_addr, server):
        """you'll probably never need to instantiate this class directly"""
        ProtHandler.__init__(self, server)
        StreamRequestHandler.__init__(self, request, client_addr, server)
    
    def read(self, n=None):
        """
        Repeatedly calls select on self.request and returns the next n bytes,
        or however much data is available before a timeout. The value of
        this handler's self.timeout or self.server.timeout is used to
        determine the timeout; both are None by default, which indicates
        an indefinite block.
        
        This method returns quickly if this handler's server's socket has
        been closed.
        """
        buf = b""
        timeout = self.timeout or self.server.timeout
        until = timeout and (time() + timeout)
        wait = min(1, timeout or 1)
        while _is_open(self.server.socket) and (not until or time() < until):
            r,_,_ = select([self.request], [], [], wait)
            if r:
                c = self.request.recv(4096 if n is None else (n - len(buf)))
                buf += c
                if not c or n is not None and len(buf) >= n:
                    break
        return buf

class UDPHandler(ProtHandler, DatagramRequestHandler):
    """
    Subclass this class for use with the SocketServer.UDPServer class or any
    of its subclasses, such as protlib.LoggingUDPServer
    """
    def __init__(self, request, client_addr, server):
        """you'll probably never need to instantiate this class directly"""
        ProtHandler.__init__(self, server)
        DatagramRequestHandler.__init__(self, request, client_addr, server)
    
    def read(self, n=-1):
        """returns the result of calling read on self.rfile"""
        return self.rfile.read(n)

class LoggingUDPServer(UDPServer):
    """
    When using a ProtHandler subclass with any other SocketServer class,
    the level of the RotatingFileHandler is set to 1 + logging.CRITICAL;
    with this class it's instead set to logging.INFO.
    
    Also, the allow_reuse_address field is set to True for this class.
    """
    allow_reuse_address = True

class LoggingTCPServer(TCPServer):
    """
    When using a ProtHandler subclass with any other SocketServer class,
    the level of the RotatingFileHandler is set to 1 + logging.CRITICAL;
    with this class it's instead set to logging.INFO.
    
    Also, the allow_reuse_address field is set to True for this class.
    """
    allow_reuse_address = True
