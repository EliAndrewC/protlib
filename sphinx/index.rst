.. toctree::
   :maxdepth: 1


protlib - Easily implement binary network protocols
===================================================

protlib builds on the
`struct <http://docs.python.org/library/struct.html>`_
and
`SocketServer <http://docs.python.org/library/socketserver.html>`_
modules in the standard library to make it easy to implement binary 
network protocols. It provides support for default and constant struct 
fields, nested structs, arrays of structs, better handling for strings 
and arrays, struct inheritance, and convenient syntax for instantiating 
and using your custom structs.

Here's an example of defining, instantiating, writing, and reading a struct using file i/o:

.. code-block:: python

    from protlib import *

    class Point(CStruct):
        x = CInt()
        y = CInt()

    p1 = Point(5, 6)
    p2 = Point(x=5, y=6)
    p3 = Point(y=6, x=5)
    assert p1 == p2 == p3

    with open("point.dat", "wb") as f:
        f.write( p1.serialize() )
    
    with open("point.dat", "rb") as f:
        p4 = Point.parse(f)
    
    assert p1 == p4

You may use the
`socket.makefile <http://docs.python.org/library/socket.html#socket.socket.makefile>`_
method to use this file i/o approach for sockets.



Installation
============
protlib is free under the BSD license.  It requires Python 2.6 or later and has no other
dependencies.  Because protlib supports Python 3, the code snippets in this
documentation are copied from a Python 3 interpreter.

You may `download protlib <https://pypi.python.org/pypi/protlib/>`_ from the Python Package
Index.  You can also run ``easy_install protlib`` or ``pip install protlib`` if you have one
of those package managers installed.

You may also check out the development version of protlib with this command:

``git clone https://github.com/EliAndrewC/protlib``

You may download older versions of protlib and view older versions of the protlib documentation
`here <http://courtwright.org/protlib/old>`_.



Data Types
==========

.. class:: CType(**kwargs)
    
    This is the root class of all classes representing C data types
    in the protlib library.  It may not be directly instantiated; you
    must always use one of its subtypes instead.  There are six
    optional keyword arguments which you may pass to a CType:
    
    * ``length``: Only valid for the ``CString``, ``CUnicode``, and ``CArray`` data types, for which it is required.  This may be one of three things: an integer which represents the length of the string; the special value ``protlib.AUTOSIZED``, which indicates that the string is null-terminated and can be any size; or a string denoting the field where the actual length value may be found.  For example:

                  >>> from protlib import *
                  >>> class Person(CStruct):
                  ...     state    = CString(length = 2)
                  ...     name_len = CShort()
                  ...     name     = CString(length = "name_len")
                  ... 
                  >>> Person(state="VA", name_len=3, name="Eli")
                  Person(state=b'VA', name_len=3, name=b'Eli')
                  >>> 
                  >>> class Person(CStruct):
                  ...     state = CString(length = 2)
                  ...     name  = CString(length = AUTOSIZED)
                  ... 
                  >>> Person.parse(b"VAEli\0")
                  Person(state=b'VA', name=b'Eli')
                  >>> Person(state="VA", name="Eli").serialize()
                  b'VAEli\x00'
    
    * ``always``: Use this to set a constant value for a field.  You won't need to specify this value, and a CWarning will be triggered if this field is ever assigned a different value.  For example:

                  >>> import warnings
                  >>> warnings.simplefilter("always")
                  >>> 
                  >>> from protlib import *
                  >>> class OriginPoint(CStruct):
                  ...     x = CInt(always = 0)
                  ...     y = CInt(always = 0)                   
                  ... 
                  >>> 
                  >>> op1 = OriginPoint()
                  >>> op1
                  OriginPoint(x=0, y=0)
                  >>> op1.x = 5
                  /home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py:733: CWarning: OriginPoint.x should always be 0 but was given a value of 5
                    warn("{0}.{1} should always be {2!r} but was given a value of {3!r}".format(self.__class__.__name__, name, field.always, value), CWarning)
                  >>> 
                  >>> buf = op1.serialize()
                  >>> op2 = OriginPoint.parse(buf)
                  /home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py:733: CWarning: OriginPoint.x should always be 0 but was given a value of 5
                    warn("{0}.{1} should always be {2!r} but was given a value of {3!r}".format(self.__class__.__name__, name, field.always, value), CWarning)
                  >>> 
                  >>> assert op1 == op2

    * ``default``: Like the ``always`` parameter, except that no warnings are raised when a different value is parsed or serialized.  Also, a ``default`` parameter may be either a value or a callable object.  For example:
 
                   >>> from protlib import *
                   >>> class Point(CStruct):
                   ...     x = CInt(default = 0)
                   ...     y = CInt(default = lambda: 5)
                   ...
                   >>> p = Point()
                   >>> p
                   Point(x=0, y=5)
    
    * ``full_string``: Unlike the struct module, protlib right-strips strings when they're parsed, starting with the first null byte.  This default behavior can be overridden by setting this parameter to ``True``.  For example:
        
                       >>> raw = b"foo\0\0"
                       >>> import struct
                       >>> s = struct.unpack(b"5s", raw)[0]
                       >>> assert s == b"foo\0\0"
                       >>> 
                       >>> from protlib import *
                       >>> s = CString(length = 5).parse(raw)
                       >>> assert s == b"foo"
                       >>> 
                       >>> raw = b"foo\0!"
                       >>> s = CString(length = 5).parse(raw)
                       >>> assert s == b"foo"
                       >>> 
                       >>> raw = b"foo\0!"
                       >>> s = CString(length = 5, full_string = True).parse(raw)
                       >>> assert s == b"foo\0!"
    
    * ``encoding``: This is required for ``CUnicode`` objects but invalid for all other types.  It specifies the encoding to use when translating to and from unicode and raw bytes.  For example:
                    
                    >>> from protlib import *
                    >>> CUnicode(length=6, encoding="utf8").serialize("andré")
                    b'andr\xc3\xa9'
                    >>> assert "andré" == CUnicode(length=6, encoding="utf8").parse(b"andr\xc3\xa9")

    * ``enc_errors``: This optional parameter is only valid for ``CUnicode`` objects.  It defined how errors are handled, e.g. by being passed as the ``errors`` argument to the `errors <http://docs.python.org/library/functions.html#unicode>`_ argument to the `unicode` builtin.  If omitted, it defaults to `"strict"`. For example:
                      
                      >>> CUnicode(length=3, encoding="utf8", enc_errors="ignore").serialize(b"\x80")
                      b'\x00\x00\x00'
                      >>> CUnicode(length=3, encoding="utf8", enc_errors="replace").serialize(b"\x80")
                      b'\xef\xbf\xbd'
                      >>> CUnicode(length=3, encoding="utf8", enc_errors="strict").serialize(b"\x80")
                      Traceback (most recent call last):
                        File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 374, in serialize
                          encoded = self.convert(val).encode(self.encoding, self.enc_errors)
                        File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 274, in convert
                          return x if isinstance(x, str) else str(_to_bytes(x), self.encoding, self.enc_errors)
                        File "/home/eli/protlib/examples/../env3/lib/python3.1/encodings/utf_8.py", line 16, in decode
                          return codecs.utf_8_decode(input, errors, True)
                      UnicodeDecodeError: 'utf8' codec can't decode byte 0x80 in position 0: unexpected code byte
                      During handling of the above exception, another exception occurred:
                      Traceback (most recent call last):
                        File "<stdin>", line 1, in <module>
                        File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 378, in serialize
                          raise CError(cerror).with_traceback(tb)
                        File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 374, in serialize
                          encoded = self.convert(val).encode(self.encoding, self.enc_errors)
                        File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 274, in convert
                          return x if isinstance(x, str) else str(_to_bytes(x), self.encoding, self.enc_errors)
                        File "/home/eli/protlib/examples/../env3/lib/python3.1/encodings/utf_8.py", line 16, in decode
                          return codecs.utf_8_decode(input, errors, True)
                      protlib.CError: unicode error serializing b'\x80': 'utf8' codec can't decode byte 0x80 in position 0: unexpected code byte
    
    .. warning::

        The ``length`` parameter of the ``CUnicode`` class indicates the max length
        of the raw serialized bytes of the CUnicode field.  It does **not** indicate
        the number of unicode characters.  For example, a 5-character unicode string
        might serialize to more than 5 bytes:
        
        >>> from __future__ import unicode_literals
        >>> from protlib import *
        >>> CUnicode(length=5, encoding="utf8").serialize("andré")
        /home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py:384: CWarning: CUnicode value has length 5 and was told to serialize an encoded string of length 6 b'andr\xc3\xa9'
          warn("CUnicode value has length {0} and was told to serialize an encoded string of length {1} {2!r}".format(self.real_length(cstruct), len(encoded), encoded), CWarning)
        b'andr\xc3'

    .. warning::

        Some unicode character encodings commonly contain null bytes, which makes it
        inadvisable to use those encodings with an ``AUTOSIZED`` string.  For example:
        
        >>> from protlib import *
        >>> s = "Hello World".encode("utf-32")
        >>> s.count(b"\0")
        35
        >>> CUnicode(length=AUTOSIZED, encoding="utf-32").parse(s)
        Traceback (most recent call last):
          File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 366, in parse
            return s.decode(self.encoding, self.enc_errors)
        UnicodeDecodeError: 'utf32' codec can't decode bytes in position 0-1: truncated data
        During handling of the above exception, another exception occurred:
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
          File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 370, in parse
            raise CError(cerror).with_traceback(tb)
          File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 366, in parse
            return s.decode(self.encoding, self.enc_errors)
        protlib.CError: unicode error parsing b'\xff\xfe': 'utf32' codec can't decode bytes in position 0-1: truncated data


    .. attribute:: sizeof

        The size of the packed binary data representing this ``CType``.
        Note that this is a ``classmethod`` for subclasses of ``CStruct``.

    .. attribute:: struct_format

        The format string used by the underying
        `struct module <http://docs.python.org/library/struct.html>`_
        to represent the packed binary data format.
        Note that this is a ``classmethod`` for subclasses of ``CStruct``.

    .. method:: parse(f)

        Accepts either a string or a file-like object (anything with a ``read`` method)
        and returns a Python object with the appropriate value.

        >>> raw = b"\x00\x00\x00\x05"
        >>> i = CInt().parse(raw)
        >>> assert i == 5
        
        Note that this is a ``classmethod`` on subclasses of ``CStruct``.

    .. method:: serialize(x)
    
        Serializes the value according to the specific ``CType`` class.
        Note that this takes no argument when called on a ``CStruct``
        instance.



Basic Data Types
----------------

Because protlib is built on top of struct module, each basic data type
in protlib uses a struct format string.  The list of struct format strings 
`is here <http://docs.python.org/library/struct.html#struct.calcsize>`_
and the protlib types which use them are listed below.  These sizes are
constant on all processor architectures by default, but this will change
if you change the value of `protlib.BYTE_ORDER <#BYTE_ORDER>`_

+----------------+---------------+--------------------------+---------------+
| C data type    | protlib class | struct format string     | size in bytes |
+================+===============+==========================+===============+
| char           | CChar         | b                        | 1             |
+----------------+---------------+--------------------------+---------------+
| unsigned char  | CUChar        | B                        | 1             |
+----------------+---------------+--------------------------+---------------+
| short          | CShort        | h                        | 2             |
+----------------+---------------+--------------------------+---------------+
| unsigned short | CUShort       | H                        | 2             |
+----------------+---------------+--------------------------+---------------+
| int            | CInt          | i                        | 4             |
+----------------+---------------+--------------------------+---------------+
| unsigned int   | CUInt         | I                        | 4             |
+----------------+---------------+--------------------------+---------------+
| long           | CLong         | q                        | 8             |
+----------------+---------------+--------------------------+---------------+
| unsigned long  | CULong        | Q                        | 8             |
+----------------+---------------+--------------------------+---------------+
| float          | CFloat        | f                        | 4             |
+----------------+---------------+--------------------------+---------------+
| double         | CDouble       | d                        | 8             |
+----------------+---------------+--------------------------+---------------+
| char[]         | CString       | Xs (e.g. 5s for char[5]) | 1 * length    |
+----------------+---------------+--------------------------+---------------+
| char[]         | CUnicode      | Xs (e.g. 5s for char[5]) | 1 * length    |
+----------------+---------------+--------------------------+---------------+



Creating Custom CTypes
----------------------

Some projects might require you to write custom parsing and serializing code;
protlib makes this easy by allowing you to subclass CType classes.  Here's
an example, which you can find in ``examples/ctype_subclassing/testing.py``:

.. literalinclude:: ../examples/ctype_subclassing/testing.py

This code works in both Python 2 and Python 3 and demonstrates the three methods
you can override to define your custom parsing and serialization:

* The ``parse`` method calls `json.loads <http://docs.python.org/library/json.html#json.loads>`_, which requires a unicode string in Python 3 but can take either a unicode a regular byte string in Python 2.  Since ``CString.parse`` returns a byte string, we make sure to encode it before passing it to ``json.loads``.

* The ``serialize`` method calls `json.dumps <http://docs.python.org/library/json.html#json.dumps>`_, which returns a unicode string in Python 3 and returns a byte string in Python 2.  Because the ``serialize`` method must return a byte string, we always encode our result; on Python 3 this will encode as we exect and when called on a regular byte string in Python 2 the original string is returned.

* The ``convert`` method defines what happens when we assign a value to our struct field.  As mentioned in the `CStruct.__setattr__ <#CStruct.__setattr__>`_ documentation below, protlib automatically does type coercion, so if you assign ``5`` to a ``CString`` field it will be converted to ``"5"``, etc.  This behavior is defined by the ``convert`` method, and in our case if someone assigns a value to a ``JsonCString`` field we don't want that value to be converted to a string as it would for a regular ``CString``, so we simply return the object unchanged.



Arrays
------

.. class:: CArray(length, ctype)

    You can make an array of any ``CType``.  Arrays pack and unpack to and
    from Python lists.  For example:
    
    >>> ca = CArray(5, CInt)
    >>> raw = ca.serialize( [5,6,7,8,9] )
    >>> xs = ca.parse(raw)
    >>> assert xs == [5,6,7,8,9]
    
    Arrays may either be given default/always values themselves or use the
    default/always values of the ``CType`` they are given.  For example:
    
    >>> class Triangle(CStruct):
    ...     xcoords = CArray(3, CInt(default=0))
    ...     ycoords = CArray(3, CInt, default=[0,0,0])
    ...
    >>> tri = Triangle()
    >>> assert tri.xcoords == tri.ycoords == [0,0,0]
    
    Nested arrays work as you might expect:
    
    >>> class Matrix(CStruct):
    ...     xs = CArray(3, CArray(2, CInt(default=0)))
    ...
    >>> assert Matrix().xs == [[0,0], [0,0], [0,0]]



Custom Structs
--------------

.. class:: CStruct

    This should never be instantiated directly.  Instead, you should subclass
    this when defining a custom struct.  Your subclass will be given a
    constructor which takes the fields of your struct as positional and/or
    keyword arguments.  However, you don't have to provide values for your
    fields at this time.  For example:
    
    >>> class Point(CStruct):
    ...     x = CInt()
    ...     y = CInt()
    ...
    >>> p1 = Point(5, 6)
    >>> p2 = Point()
    >>> p2.x = 5
    >>> p2.y = 6
    >>> assert p1 == p2
    
    .. classmethod:: sizeof(cstruct = None)
    
        Returns the size of the packed binary data needed to hold this
        ``CStruct``.  This method takes no arguments on a fixed-size
        struct, but if any of this struct's fields has a variable length,
        this method will throw an exception if called with no arguments.
        You can pass an instance of this CStruct to get the size of that
        particular instance, for example:
        
        >>> from protlib import *
        >>> 
        >>> class Person(CStruct):
        ...     name = CString(length = 5)
        ... 
        >>> Person.sizeof()
        5
        >>> 
        >>> class Person(CStruct):
        ...     name = CString(length = AUTOSIZED)
        ... 
        >>> Person.sizeof()
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
          File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 654, in sizeof
            return cls.get_type(cached=True).sizeof(cstruct)
          File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 254, in sizeof
            return struct.calcsize(BYTE_ORDER + self.struct_format(cstruct))
          File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 486, in struct_format
            return b"".join(ctype.struct_format(cstruct) for name,ctype in self.subclass.get_fields())
          File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 486, in <genexpr>
            return b"".join(ctype.struct_format(cstruct) for name,ctype in self.subclass.get_fields())
          File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 245, in struct_format
            CString:  _to_bytes("{0}s".format(self.real_length(cstruct))),
          File "/home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py", line 210, in real_length
            raise CError("cstruct not provided to resolve variable-length field with length attribute {0!r}".format(self.length))
        protlib.CError: cstruct not provided to resolve variable-length field with length attribute 'AUTOSIZED'
        >>> 
        >>> eli = Person(name = "Eli")
        >>> Person.sizeof(eli)
        4
    
    .. classmethod:: parse(f)
        
        Accepts a string or file-like object and returns an instance of
        this ``CStruct`` drawn from that data source.
    
    .. method:: serialize()
    
        Returns the packed binary data representing this ``CStruct``.
        This is what should be written to files and sockets.
    
    .. method:: __str__()
    
        Alias for ``__repr__``
    
    .. method:: __repr__()
    
        Returns a literal representation of the ``CStruct``.  For example:
        
        >>> class Point(CStruct):
        ...     x = CInt()
        ...     y = CInt()
        ...
        >>> p = Point(x=5, y=6)
        >>> p
        Point(x=5, y=6)

    .. method:: __setattr__(self, name, val)
        
        When you assign a value to one of a struct's fields, protlib converts
        the value to the proper data type, according to the data type.
        For example:
        
        >>> class Point(CStruct):
        ...     code = CChar()
        ...     x = CInt()
        ...     y = CInt()
        ... 
        >>> p = Point(code="A", x="5")
        >>> assert p.code == ord("A") == 65
        >>> assert p.x == 5
        >>> 
        >>> p.y = 6.25
        /home/eli/protlib/env3/lib/python3.1/site-packages/protlib-1.4-py3.1.egg/protlib.py:746: CWarning: Loss of precision when converting a float (6.25) to an integer field
          warn("Loss of precision when converting a float ({0}) to an integer field".format(x), CWarning)
        >>> assert p.y == 6
    
    .. classmethod:: get_type(**kwargs)
    
        Returns an objects which may be used to declare a ``CStruct`` as a
        field in another ``CStruct``.  This accepts the same ``default``
        and ``always`` parameters as the ``CType`` constructor.  For example:
        
        >>> class Point(CStruct):
        ...     x = CInt()
        ...     y = CInt()
        ...
        >>> class Vector(CStruct):
        ...     p1 = Point.get_type()
        ...     p2 = Point.get_type(default = Point(0,0))
        ...
        >>> v = Vector(p1 = Point(5,6))
    
    .. classmethod:: get_fields()
    
        Returns a list of the ``CType`` objects which define the fields of 
        this struct in the order in which they were declared.

.. warning::

    The order of struct fields is defined by the order in which the ``CType``
    subclasses for those fields were instantiated.  In other words, if you say

    .. code-block:: python

       from protlib import *

       y_field = CInt()
       x_field = CInt()

       class Point(CStruct):
           x = x_field
           y = y_field

    then when you serialize your struct, the ``y`` field will come **before**
    the ``x`` field because its ``CInt`` value was instantiated first.  Similarly,
    if you say

    .. code-block:: python

        from protlib import *

        class Point(CStruct):
            x = y = CInt()

    then the order of the x and y fields is undefined since they share the same
    ``CInt`` instance.  In this second case, a CWarning will be triggered,
    but the first case is not automatically detected by the protlib library.



Protocol Handlers
=================

protlib also provides a convenient framework for implementing servers which receive and 
send ``CStruct`` objects.  This makes it easy to implement custom binary protocols in 
which structs are passed back and forth over socket connections.  This is based on
`the SocketServer module <http://docs.python.org/library/socketserver.html>`_
in the Python standard library.

In order to use these examples, you must do only two things.

* First, make sure that each struct which represents a message begins with a constant 
  value which uniquely identifies that struct.
* Second, define a subclass of the appropriate handler class, either ``TCPHandler`` or
  ``UDPHandler``, and define a handler method for each message type you wish to respond to.



An example client/server
------------------------

Let's walk through a simple example.  We'll define several structs to represent geometric 
concepts: a Point, a Vector, and a Rectangle.  Each of these structs is a message which 
can be sent between the client and server.  We'll also define a variable-length message 
called PointGroup, which demonstrates using variable-length arrays.

Note that first field in each of these messages is a constant value that uniquely 
identifies the message.

This entire example can be found in the ``examples/geocalc`` directory.  Here's the 
``common.py`` file, which is imported by both the ``server.py`` and ``client.py`` programs:

.. literalinclude:: ../examples/geocalc/common.py

For our server, we define a handler class with a handler method for each message we wish 
to accept.  The name of each handler method should be the name of the message class in 
lower case with the words separated by underscores.  For example, the ``Vector`` class 
is handled by the ``vector`` method, and the ``PointGroup`` class is handled by the 
``point_group`` method.  Each of these handler methods takes a single parameter other 
than ``self`` which is the actual message read and parsed from the socket.

Here's the ``server.py`` file which uses our subclasses of
`the SocketServer module <http://docs.python.org/library/socketserver.html>`_
classes to accept and handle incoming messages:

.. literalinclude:: ../examples/geocalc/server.py

To test this server, we have a simple client which sends a series of messages to the 
server and then reads back the responses, logging everything with our ``protlib.Logger`` 
class.  Here's our ``client.py`` script:

.. literalinclude:: ../examples/geocalc/client.py

Our server does all of our logging automatically, but we need to manually invoke the 
logger on the client.  The logs created and their format are explained below.



Logging
-------

protlib uses `the logging module <http://docs.python.org/library/logging.html>`_ to
provide 5 different logs, each with their own suffix: hex, raw, struct, error, and stack.
By default, the prefix of these logs will be the name of the current script.
A `RotatingFileHandler <http://docs.python.org/library/logging.html#rotating-file-handler>`_
is created for each of these logs if no handlers already exist when the logs are first
accessed by protlib.

For example, if you're running the script ``server.py`` then these will be the log names,
log file names, `logging level <http://docs.python.org/library/logging.html#logging-levels>`_
used for the log messages, and type of messages written to each log:

+---------------+-------------------+--------------+-----------------------------------------------------------------+
| log name      | default filename  | level        | messages                                                        |
+===============+===================+==============+=================================================================+
| server.hex    | server.hex_log    | ``DEBUG``    | nicely formatted hex dumps of the binary data sent and received |
+---------------+-------------------+--------------+-----------------------------------------------------------------+
| server.raw    | server.raw_log    | ``INFO``     | Python string literals of the binary data sent and received     |
+---------------+-------------------+--------------+-----------------------------------------------------------------+
| server.struct | server.struct_log | ``WARNING``  | literal representations of each struct sent and received        |
+---------------+-------------------+--------------+-----------------------------------------------------------------+
| server.error  | server.error_log  | ``ERROR``    | error messages                                                  |
+---------------+-------------------+--------------+-----------------------------------------------------------------+
| server.stack  | server.stack_log  | ``CRITICAL`` | stack traces of uncaught exceptions thrown by handler methods   |
+---------------+-------------------+--------------+-----------------------------------------------------------------+

Each log message generated by one of our protocol handlers contains a unique identifier
which indicates the binary protocol message received.  This makes it easy to match the
log messages in the different files to one another, since this unique message identifier
will be present in each of the 5 logs.



Log examples
^^^^^^^^^^^^

Here's a description of each log:

.. attribute:: struct
    
    This contains the literal representation of each request and response, for example:
    
    .. code-block:: none
        
        2010-03-15 18:54:07,664: (1268693647_0) received Vector(code=2, p1=Point(code=1, x=39.0, y=41.0), p2=Point(code=1, x=93.0, y=13.0))
        2010-03-15 18:54:07,664: (1268693647_0) sending Point(code=1, x=66.0, y=27.0)
    
    This is convenient because the structs are logged with the Python code which represents 
    them.  Therefore we can paste them directly into a Python command prompt to inspect and 
    play around with them:
    
    >>> from common import *
    >>> p = Point(code=1, x=66.0, y=27.0)
    >>> p
    Point(code=1, x=66.0, y=27.0)

.. attribute:: raw
    
    This contains the raw data in the form of a Python string of each request and response, for example:
    
    .. code-block:: none
        
        2010-03-15 18:54:07,664: (1268693647_0) sending b'\x00\x01B\x84\x00\x00A\xd8\x00\x00'
        2010-03-15 18:54:07,667: (1268693647_1) received b'\x00\x04\x00\x01?\x80\x00\x00?\x80\x00\x00\x00\x01?\x80\x00\x00@\xa0\x00\x00\x00\x01@\xa0\x00\x00?\x80\x00\x00\x00\x01@\xa0\x00\x00@\xa0\x00\x00'
        
    This is convenient because we can paste these strings into a Python command prompt 
    and play around with them.  If they are valid then we can parse them into structs, and 
    if they aren't then we can examine exactly why; this log will always contain what
    we receive even in the case of unparsable binary data:
    
    >>> from common import *
    >>> s = b'\x00\x01B\x84\x00\x00A\xd8\x00\x00'
    >>> p = Point.parse(s)
    >>> p
    Point(code=1, x=66.0, y=27.0)
    >>> 
    >>> s = b"bad"
    >>> p = Point.parse(s)
    >>> Point.parse(s)
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "protlib.py", line 230, in parse
        return cls.get_type(cached=True).parse(f)
      File "protlib.py", line 141, in parse
        raise CError("{0} requires {1} bytes and was only given {2} ({3!r})".format(self.subclass.__name__, self.sizeof, len(buf), buf))
    protlib.CError: Point requires 10 bytes and was only given 3 ('bad')
    >>> 
    >>> s = b"invalid but with enough data"
    >>> p = Point.parse(s)
    ../../protlib.py:526: CWarning: Point.code should always be 1 but was given a value of 26990
      warn("{0}.{1} should always be {2!r} but was given a value of {3!r}".format(self.__class__.__name__, name, field.always, value), CWarning)
    >>> p
    Point(code=26990, x=1.1430328245747994e+33, y=1.1834294514326081e+22)

.. attribute:: hex
    
    This contains nicely-formatted tables of the binary data sent and received in hexadecimal notation.  For example:
    
    .. code-block:: none
        
        2010-03-15 18:38:50,978: (1268692730_0) received
             0  1  2  3  4  5  6  7
          0  00 02 00 01 42 30 00 00
          8  42 74 00 00 00 01 42 aa
         16  00 00 42 18 00 00

.. attribute:: error

    This contains messages for common errors, such as when a message is too short, or 
    when we have no handler to match a message we've received, etc.  These messages 
    contain as much information as possible to help reconstruct the problem, which 
    usually includes the raw data involved (also present in the ``raw`` log).

.. attribute:: stack

    This contains stack traces from exceptions thrown in your handler methods.



Logger objects
^^^^^^^^^^^^^^

Although logging is performed automatically when using ``SocketServer`` classes,
you may find it useful to instantiate your own logger objects, then manually make use
of the 5 logs listed above.  Use this object to do that; note that this class uses but
does not inherit from the
`logging.Logger <http://docs.python.org/library/logging.html#loggers>`_ class.

.. class:: Logger([prefix[, also_print=False]])

    A logging object which uses the 5 logs listed above.
    
    :param prefix: Pass a string as this parameter to replace the default prefix (which
                   is the name of the script being executed).  For example, if you pass
                   the string ``"foo"`` as this parameter, then your logs will be named
                   ``foo.hex``, ``foo.raw``, etc.
    :param also_print: whether to also print log messages to the screen

    .. method:: log_struct(inst[, trans_type="received"])
    
        Logs the ``repr`` of an instance of a ``CStruct`` subclass to the ``struct`` log.
        
        :param inst: the instance of the struct to be logged
        :param trans_type: a prefix to the log message, generally this should be either
                           ``"sending"`` or ``"received"``
    
    .. method:: log_binary(data[, trans_type="received"])
    
        Logs the ``repr`` of the packed binary data to the ``raw`` log, then logs a
        nicely formatted table of thje data to the ``hex`` log.
        
        :param data: the packed binary data, such as what's produced by calling
                     ``s.serialize()`` on an instance of a ``CStruct`` subclass
        :param trans_type: a prefix to the log message, generally this should be either
                           ``"sending"`` or ``"received"``
    
    .. method:: log_error(message, *args, **kwargs)
    
        Logs the message to the ``error`` log.  The ``message`` parameter should be
        a string, and the ``*args`` and ``**kwargs`` to this method are used as the
        parameters to `str.format <http://docs.python.org/library/stdtypes.html#str.format>`_

    .. method:: log_stacktrace()
    
        Logs the value of `traceback.format_exc() <http://docs.python.org/library/traceback.html#traceback.format_exc>`_
        to the ``stack`` log.
    
    .. method:: log_and_write(f, data)
        
        Logs a string or CStruct instance to the appropriate logs, then writes it to a file.
        
        :param f: a file object to which data will be written
        :param message: a string or CStruct instance



Advanced logging
^^^^^^^^^^^^^^^^

As mentioned above, protlib automatically sets up a ``RotatingFileHandler`` when
you instantiate ``protlib.Logger`` on each of the 5 logs for which no
other logging handlers are defined.  Because protlib uses the ``logging`` module
from the standard library, you can use your own configuration, handlers, formatters,
etc.  This is demonstated by the following example, which is included as the file
``examples/custom_logging/testing.py``, although you'll need to replace the string
``"smtp.example.com"`` with a valid outgoing mail server for the code to run properly.

.. literalinclude:: ../examples/custom_logging/testing.py

Here's an explanation of the customizations made to our logging:

* The logging level is set to ``logging.DEBUG``, which differs from the default value of ``logging.WARNING``.
* We use a `TimedRotatingFileHandler <http://docs.python.org/library/logging.html#timedrotatingfilehandler>`_ for our ``hex`` log.  Because we add this handler **before** instantiating ``protlib.Logger``, this handler is used **instead of** the default ``RotatingFileHandler``.
* We use a `SMTPHandler <http://docs.python.org/library/logging.html#smtphandler>`_ for our ``stack`` log.  Because we add this handler **after** instantiating ``protlib.Logger``, this is used **in addition to** the default ``RotatingFileHandler``.



Protocol Handler Classes
------------------------

As mentioned above, you should always have your protocol classes extend either
the ``TCPHandler`` or ``UDPHandler`` class, depending on what type of ``SocketServer``
you're using.  Each of these classes inherits from ``ProtHandler``, and you may use
these methods and fields to affect the behavior of your custom protocol handlers:

.. class:: ProtHandler

    The user does not instantiate this class or any of its subclasses directly.  Instead, 
    you declare your own handler class which subclasses either ``TCPHandler`` or
    ``UDPHandler``, which are themselves subclasses of ``ProtHandler``.  They also extend
    `the StreamRequestHandler and DatagramRequestHandler classes <http://docs.python.org/library/socketserver.html#requesthandler-objects>`_
    of the SocketServer module, respectively.
    
    This class also inherits from the ``protlib.Logger`` class, so you can call the log
    functions listed above from your handler methods by simply calling ``self.log_stack()``,
    ``self.log_error("Boo!")``, etc.
    
    .. attribute:: STRUCT_MOD
    
        By default, your handler will detect all messages present in the same module 
        where the handler class itself is defined.  So you can either define your handler 
        in the same module where your structs are  defined, or you can import those 
        structs into the handler's module.  This is the recommended way to integrate your 
        handlers with your struct definitions.
        
        However, you may instead set the STRUCT_MOD field to the module where the structs 
        are declared. (Technically this can be anything with ``__dict__`` and 
        ``__name__`` fields.)  You may also set this to a string which is the name of 
        the module where they are declared.  For example:
        
        .. code-block:: python
        
            import module_with_structs
            
            class SomeHandler(TCPHandler):
                STRUCT_MOD = module_with_structs
                
                # handler methods would go here
            
            class AnotherHandler(UDPHandler):
                STRUCT_MOD = "module_with_structs"
                
                # handler methods would go here
    
    .. attribute:: LOG_TO_SCREEN
    
        This is ``False`` by default, but if set to ``True``, every log message will be 
        printed to the screen in addition to being written to the appropriate log.
    
    .. attribute:: LOG_PREFIX
        
        Changes the prefix of each log from the name of the current script to whatever is specified.
        For example, if you set the ``LOG_PREFIX`` to ``"foo"``, then your logs will be
        ``foo.hex``, ``foo.raw``, etc.
        
        These attributes are best set where your custom handler class is defined, for example:
        
        .. code-block:: python
        
            class Handler(TCPHandler):
                LOG_TO_SCREEN = True
                LOG_PREFIX = "unified"
                
                # handler methods would go here
    
    .. method:: raw_data(data)
    
        This is the default handler for any message for which no struct has been 
        defined.  By default this logs an error message and sends no reply.  Override 
        this if you wish to have your own handler for unclassified binary messages; 
        the ``data`` parameter is a string containing the binary data of the message.
    
    .. method:: reply(data)
    
        Anything you return a handler method is sent back to the client, whether it's 
        a struct or just binary data in a string.  However, sometimes you may need to 
        send multiple messages back to the client.  You can manually concatenate the 
        binary data strings, or you can use the ``reply`` method, for example:
        
        .. code-block:: python
            
            class RepeatRequest(CStruct):
                code = CShort(always = 1)
                name = CString(length = 25)
                repititions = CInt()
            
            class Handler(TCPHandler):
                def repeat_request(self, rr):
                    for i in range(rr.repititions):
                        self.reply(b"Hello " + sm.name + b"!\n")



.. class:: LoggingTCPServer(addr, handler_class)
.. class:: LoggingUDPServer(addr, handler_class)

    These classes extend the 
    `TCPServer <http://docs.python.org/library/socketserver.html#socketserver-tcpserver-example>`_
    and the
    `UDPServer <http://docs.python.org/library/socketserver.html#socketserver-udpserver-example>`_
    classes from the SocketServer module, respectively.  There are only two differences between
    these and their parent classes:
    
    * The `allow_reuse_address <http://docs.python.org/library/socketserver.html#SocketServer.BaseServer.allow_reuse_address>`_ field is set to True for these classes.
    * When your protocol handler is used with one of these classes, the logging level of the default ``RotatingFileHandler`` objects is set to ``INFO``.  When it's used with other classes, it's set to ``CRITICAL + 1``.  Note that this is the level of the handlers, which is independent of the level of the loggers themselves, `as explained here <http://docs.python.org/howto/logging.html#handlers>`_.
    
    So basically, using these classes simply provides sensible default settings for your logs and sockets.



.. class:: Parser([logger[, module]])

    If you know what struct you want, then you can use the ``CStruct.parse`` classmethod
    to read an instance of that struct from a file, e.g. ``p = Point.parse(f)``.  However, 
    in some cases you want to read some data from a file or socket but aren't sure what 
    message is coming across.  This class's ``parse`` method figures out which message 
    is being read and returns an instance of the correct struct.
    
    :param module: This is exactly the same as the ``ProtHandler.STRUCT_MOD`` field;
                   if present then it indicates which module contains the struct classes
                   you want to use.  If omitted, then the module where this class is
                   instantiated is used.
    :param logger: The instance of the ``Logger`` class to use to perform logging.  If
                   omitted, the logging level of each default ``RotatingFileHandler``
                   will be ``CRITICAL + 1``.
    
    .. method:: parse(f)
    
        This method accepts a string or file and returns an instance of the struct
        it reads from that string/file.  If the data it finds cannot be parsed into
        a struct, then it just returns all of the data it is able to read.  This
        may be an empty string if no data is available.  Any data returned will be
        written to the appropriate logs.
        
        ``None`` will be returned in the case of an incomplete message.  In this case
        a message will be written to the ``error`` log.



Struct Inheritance
------------------

Many binary protocols have many message types, but every message has exactly the same
fields, even if those fields have different constant values.  It would be annoying if you had
to write a bunch of mostly-identical struct definitions, so protlib lets you subclass
your custom structs and only override the fields which are different in some way,
such as having a default value in some subclasses but not others, etc.

Let's walk through a simple example, which is available in the ``examples/struct_inheritance``
directory.  First, we define our messages in ``common.py``:

.. literalinclude:: ../examples/struct_inheritance/common.py

In this case we have a standard message format, and the only thing that varies is
the value of the ``code`` field, so we need only specify that field in our subclasses.
If we needed to override other fields, we could do so in any order; the order of
fields would remain as however they were declared in the parent class.

Since these messages all have different constant values in their first field, we can
write a normal handler class in our ``server.py``:

.. literalinclude:: ../examples/struct_inheritance/server.py

Since our handler can return different types of messages depending on whether our lookup
was successful, our ``client.py`` uses the ``Parser`` class to parse all incoming messages:

.. literalinclude:: ../examples/struct_inheritance/client.py



Miscellaneous classes, methods, and constants
=============================================

.. class:: CError
    
    All exceptions raised by the protlib module will be instances of this class, which extends ``BaseException``.
    
.. class:: CWarning

    All warnings triggered by the protlib module will be instances of this class, which extends ``UserWarning``.
 
.. function:: underscorize(name)

    This is the function used to convert between ``camelCased`` and 
    ``separated_with_underscores`` names.  Pass it a string and it returns an 
    all-lower-case string with underscores inserted in the appropriate places.  You 
    never have to call this method yourself, but you can use it as a test if you're 
    unsure of the correct handler method name for one of your ``CStruct`` class.
    If your struct names are already lower case then this function will just return the
    original string, whether or not you are already using underscores. To make
    things even clearer, here are some examples:
    
    .. code-block:: none
    
        SomeStruct    -> some_struct
        SSNLookup     -> ssn_lookup
        RS485Adaptor  -> rs485_adaptor
        Rot13Encoded  -> rot13_encoded
        RequestQ      -> request_q
        John316       -> john316
        rs485adaptor  -> rs485adaptor
        rot13_encoded -> rot13_encoded
    
.. function:: hexdump(data)

    Takes a string and returns a string containing a nicely formatted table of the 
    hexadecimal values of the data in that string.  For example:

    >>> from protlib import *
    >>> print(hexdump(b"Hello World!"))
         0  1  2  3  4  5  6  7
      0  48 65 6c 6c 6f 20 57 6f
      8  72 6c 64 21

.. attribute:: BYTE_ORDER

    The first character of the format string passed to
    `the struct module <http://docs.python.org/library/struct.html>`_
    which determines the byte order used to parse and serialize our structs.  By default
    this is set to ``"!"``, which indicates network byte order.  You may change it to
    any of the options available in the struct module.

.. attribute:: AUTOSIZED

    Special constant value which can be passed to the `length <#CType>`_ attribute of a
    ``CString`` or ``CUnicode`` object to indicate that the string is null-terminated
    and may have any length.
