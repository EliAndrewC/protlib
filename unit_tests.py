# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division
import os
import sys
import json
import math
import atexit
import socket
import logging
import warnings
from glob import glob
from time import sleep, time
from threading import Thread
from unittest import TestCase, main

import protlib
from protlib import *

if sys.version_info[0] == 2:
    from StringIO import StringIO as BytesIO
else:
    unicode = str
    from io import BytesIO

warnings.simplefilter("error", CWarning)

def assert_works_without_warnings(func, *args, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CWarning)
        func(*args, **kwargs)
        protlib.__warningregistry__.clear()

def delete_logs():
    if hasattr(atexit, "_clear"):
        atexit._clear()
    elif hasattr(atexit, "_exithandlers"):
        atexit._exithandlers[:] = []    # stop the logging module's exit handler
    
    for suffix in Logger.LEVELS:
        filename = Logger.DEFAULT_PREFIX + ".{0}_log".format(suffix)
        if os.path.exists(filename):
            handlers = logging.getLogger(Logger.DEFAULT_PREFIX + "." + suffix).handlers
            if handlers and handlers[0].stream:
                handlers[0].stream.close()
            os.remove(filename)

class NamedPoint(CStruct):
    code = CShort(always = 0x1234)
    x    = CInt()
    y    = CInt()
    name = CString(length=15, default=b"unnamed")
NP_BUF = b"\x124\0\0\0\x05\0\0\0\x06unnamed\0\0\0\0\0\0\0\0"

class RenamedPoint(NamedPoint):
    code = CShort(always = 0x4321)

class NamedOrigin(NamedPoint):
    y = CInt(always = 0)            # field order can be different in subclasses
    code = CShort(always = 0x2332)
    x = CInt(always = 0)

class PointGroup(CStruct):
    code   = CUChar(always = 255)
    count  = CShort()
    points = CArray("count", NamedPoint)

class Person(CStruct):
    code = CShort(always = 9)
    name = CString(length = AUTOSIZED)

class EvenPaddedCString(CString):
    def __init__(self, **params):
        CString.__init__(self, length=AUTOSIZED, **params)
    
    def parse(self, f, cstruct=None):
        s = CString.parse(self, f, cstruct)
        if len(s) % 2 == 0:
            f.read(1)
        return s
    
    def serialize(self, s, cstruct=None):
        s = CString.serialize(self, s, cstruct)
        if len(s) % 2:
            s += b"\0"
        return s

class JsonCString(CString):
    def parse(self, f, cstruct=None):
        return json.loads(CString.parse(self, f, cstruct).decode("utf8"))
    
    def serialize(self, s, cstruct=None):
        return CString.serialize(self, json.dumps(s).encode("utf8"), cstruct)
    
    def convert(self, x):
        return x

SERVER_ADDR = ("127.0.0.1", 7357)
CLIENT_ADDR = ("127.0.0.1", 5737)

class TestHandler(object):
    def named_point(self, np):
        return RenamedPoint(x=np.x, y=np.y)
    
    def renamed_point(self, rp):
        return b"Hello World!\n"
    
    def point_group(self, pg):
        pg.count *= 2
        pg.points *= 2
        return pg

class UDPTestHandler(UDPHandler, TestHandler): pass
class TCPTestHandler(TCPHandler, TestHandler): timeout = 0.1

class CTypeTests(TestCase):
    def test_valid_basic(self):
        for always in [None, 5]:
            for default in [None, 6]:
                for ctype in [CChar,  CShort,  CInt,  CLong,
                              CUChar, CUShort, CUInt, CULong,
                              CFloat, CDouble]:
                    ctype(always=always, default=default)
                CString(length=5, always=always, default=default)
                CUnicode(length=5, always=always, default=default, encoding="utf8")
    
    def test_invalid_basic(self):
        self.assertRaises(CError, CType)
        self.assertRaises(CWarning, CInt, length=5)
        self.assertRaises(CWarning, CInt, something=6)
        self.assertRaises(CWarning, CInt, full_string=True)
        self.assertRaises(TypeError, CInt, 5)
        self.assertRaises(TypeError, CString, 5)
        self.assertRaises(CError, CInt().parse, b"")
        self.assertRaises(CError, CArray(2,CInt).parse, b"1234")
    
    def test_integer_boundaries(self):
        for signed,unsigned,exp in [(CChar,CUChar,8), (CShort,CUShort,16), (CInt,CUInt,32), (CLong,CULong,64)]:
            unsigned().serialize(0)
            unsigned().serialize(2**exp - 1)
            self.assertRaises(CError, unsigned().serialize, -1)
            self.assertRaises(CError, unsigned().serialize, 2**exp)
            
            signed().serialize(-2**(exp-1))
            signed().serialize(2**(exp-1) - 1)
            self.assertRaises(CError, signed().serialize, 2**exp - 1)
            self.assertRaises(CError, signed().serialize, -2**(exp-1) - 1)
    
    def test_floating_point_boundaries(self):
        for ctype in [CFloat, CDouble]:
            self.assertTrue( math.isnan(ctype().parse(ctype().serialize(float("nan")))) )
            self.assertEqual(float("inf"), ctype().parse(ctype().serialize(float("inf"))))
            self.assertEqual(float("-inf"), ctype().parse(ctype().serialize(float("-inf"))))
        
        self.assertRaises(CError, CFloat().serialize, sys.float_info.max)
        self.assertRaises(CError, CFloat().serialize, -sys.float_info.max)
        self.assertEqual(0, CFloat().parse(CFloat().serialize(sys.float_info.min)))
        self.assertEqual(0, CFloat().parse(CFloat().serialize(-sys.float_info.min)))
        
        self.assertEqual(sys.float_info.min, CDouble().parse(CDouble().serialize(sys.float_info.min)))
        self.assertEqual(sys.float_info.max, CDouble().parse(CDouble().serialize(sys.float_info.max)))
        self.assertEqual(-sys.float_info.min, CDouble().parse(CDouble().serialize(-sys.float_info.min)))
        self.assertEqual(-sys.float_info.max, CDouble().parse(CDouble().serialize(-sys.float_info.max)))
    
    def test_valid_cstring(self):
        cs = CString(length = 20)
        self.assertEqual(20, len(cs.serialize(b"Hello World!")))
        self.assertEqual(b"Hello World!", cs.parse(b"Hello World!" + b"\0" * 8))
        self.assertEqual(b"Hello World!", cs.parse(b"Hello World!\x001234567"))
        
        cs = CString(length = 100)
        self.assertEqual(b"Hello World!", cs.parse(cs.serialize(b"Hello World!")))
        
        cs = CString(length=10, full_string=True)
        self.assertEqual(b"Hello\0\0\0\0\0", cs.parse(cs.serialize(b"Hello")))
    
    def test_invalid_cstring(self):
        self.assertRaises(CError, CString)
        self.assertRaises(CError, CString, length=-1)
        self.assertRaises(CError, CString, length=None)
        self.assertRaises(CWarning, CString(length=2).serialize, b"Hello")
    
    def test_array_instantiation(self):
        class Point(CStruct):
            x = CInt()
            y = CInt()
        
        CArray(10, CInt)
        CArray(10, CInt())
        CArray(10, Point)
        CArray(10, Point.get_type())
    
    def test_array_packing(self):
        xs = CArray(2, CInt, default=[0,6])
        buf = b"\0\0\0\x05\0\0\0\x06"
        self.assertEqual(xs.serialize([5,6]), buf)
        self.assertEqual(xs.serialize([5]), buf)
        self.assertEqual([5,6], xs.parse(buf))
        
        class Words(CStruct):
            message = CArray(2, CString(length=5))
            target = CString(length=6)
        
        self.assertRaises(CWarning, CArray(2,CInt).serialize, [5,6,11])
        self.assertRaises(CWarning, CArray(2, CString(length=5)).serialize, ["Hello","World!"])
        
        assert_works_without_warnings(lambda: self.assertEqual(buf, CArray(2,CInt).serialize([5,6,11])))
        assert_works_without_warnings(lambda:
            self.assertEqual(Words(message=["Bye","Cruel"],         target="Error!").serialize(),
                             Words(message=["Bye","Cruel","World"], target="Error!").serialize()))
        
        words = Words(message=["hello","world"], target="fair")
        words.message[1:] = []
        self.assertRaises(CError, words.serialize)
    
    def test_array_defaults(self):
        self.assertRaises(CError, CArray, 2, CChar, always=[0])
        self.assertRaises(CError, CArray, 2, CChar, default=[0])
        self.assertRaises(CError, CArray, 2, CChar, always=[0,0,0])
        self.assertRaises(CError, CArray, 2, CChar, default=[0,0,0])
        self.assertRaises(CError, CArray, 2, CChar, default=lambda: [0,0,0])
        
        assert_works_without_warnings(CArray, 2, CChar, always=[0,0,0])
        assert_works_without_warnings(CArray, 2, CChar, default=[0,0,0])
        assert_works_without_warnings(CArray, 2, CChar, default=lambda: [0,0,0])
        
        class Point(CStruct):
            xy = CArray(2, CInt, default=[5,6])
        self.assertEqual(Point().xy, [5,6])
        
        class Point(CStruct):
            xy = CArray(2, CInt(default=5))
        self.assertEqual(Point().xy, [5,5])
        
        class Point(CStruct):
            xy = CArray(2, CInt, default=lambda: [5,6])
        self.assertEqual(Point().xy, [5,6])
        
        class Point(CStruct):
            xy = CArray(2, CInt(default=6), default=[5])
        self.assertEqual(Point().xy, [5])
        self.assertEqual([5,6], Point.parse(Point().serialize()).xy)
    
    def test_invalid_arrays(self):
        self.assertRaises(CError, CArray, 10, int)
        self.assertRaises(CWarning, CArray, 10, NamedPoint())
        self.assertRaises(CWarning, CArray(2,CInt).serialize, [5,6,11])
    
    def test_nested_arrays(self):
        matrix = CArray(5, CArray(6, CInt(default=0)))
        self.assertEqual([[0]*6]*5, matrix.parse(matrix.serialize([])))
        
        class Matrix(CStruct):
            xs = CArray(2, CArray(2, CInt))
        
        Matrix(xs=[[5,6],[7,8]])
        self.assertRaises(CError, Matrix, xs=[])
        
        self.assertRaises(CError, Matrix, xs=[[0,0], [1,1], [0,1]])
        self.assertRaises(CError, Matrix, xs=[[0,0,0], [1,1,1]])
        
        assert_works_without_warnings(Matrix, xs=[[0,0], [1,1], [0,1]])
        assert_works_without_warnings(Matrix, xs=[[0,0,0], [1,1,1]])
    
    def test_valid_structs(self):
        np = NamedPoint(x=5, y=6)
        buf = np.serialize()
        pos = NamedPoint(0x1234, 5, 6)
        dup = NamedPoint(0x1234, 5, 6, x=5, y=6)
        parsed = NamedPoint.parse(buf)
        evaled = eval( repr(np) )
        from_file = NamedPoint.parse( BytesIO(NP_BUF) )
        
        self.assertEqual(buf, NP_BUF)
        self.assertEqual(np, pos)
        self.assertEqual(np, dup)
        self.assertEqual(np, parsed)
        self.assertEqual(np, evaled)
        self.assertEqual(np, from_file)
    
    def test_struct_equality(self):
        np   = NamedPoint(x=5, y=6)
        same = NamedPoint(x=5, y=6)
        diff = NamedPoint(x=0, y=0)
        
        self.assertTrue(np == same)
        self.assertFalse(np != same)
        self.assertEqual(hash(np), hash(same))
        self.assertEqual([np.code, np.name, np.x, np.y], [same.code, same.name, same.x, same.y])
        
        self.assertTrue(np != diff)
        self.assertFalse(np == diff)
        self.assertNotEqual(hash(np), hash(diff))
        self.assertEqual([np.code, np.name, np.x, np.y], [same.code, same.name, same.x, same.y])
    
    def test_nested_structs(self):
        class Segment(CStruct):
            p1 = NamedPoint.get_type()
            p2 = NamedPoint.get_type()
        Segment.parse(NP_BUF * 2)
        Segment.parse(NP_BUF * 2 + b"extra data in buffer")
        Segment(p1=NamedPoint(x=5,y=6), p2=NamedPoint(x=11,y=42))
    
    def test_struct_arrays(self):
        class Segment(CStruct):
            points = CArray(2, NamedPoint)
        Segment()
        Segment([NamedPoint(x=5,y=6), NamedPoint(x=7,y=11)]).serialize()
        seg = Segment([NamedPoint(x=5,y=6), NamedPoint(x=7,y=11)])
        seg.points[:] = []
        self.assertRaises(CError, seg.serialize)
        self.assertRaises(CError, Segment().serialize)
        self.assertRaises(CError, Segment, [NamedPoint(x=5,y=6)])
        self.assertRaises(CError, Segment, [NamedPoint(x=5,y=6)]*3)
    
    def test_invalid_struct_instances(self):
        self.assertRaises(CError, CStruct)
        self.assertRaises(CError, NamedPoint, x = ["wrong", "type"])
        self.assertRaises(CError, NamedPoint, x = 2 ** 33)
        self.assertRaises(CWarning, NamedPoint, x=5, y=6, z=12)
        self.assertRaises(CError, NamedPoint, 0x1234, 5, x=6)
        self.assertRaises(CError, NamedPoint(x=5).serialize)
        self.assertRaises(CWarning, NamedPoint, code=0x4321, x=5, y=6)
        self.assertRaises(CWarning, NamedPoint.parse, b"!C\0\0\0\x05\0\0\0\x06unnamed\0\0\0\0\0\0\0\0")
    
    def test_invalid_structs(self):
        self.assertRaises(CError, NamedPoint.parse, NP_BUF[:-1])
        
        class Point(CStruct):
            pass
        self.assertRaises(CError, Point)
        self.assertRaises(CError, Point.parse, b"\0\0\0\0")
        
        class Point(CStruct):
            x = CInt
        self.assertRaises(CError, Point)
        self.assertRaises(CError, Point.parse, b"\0\0\0\0")
        
        class Segment(CStruct):
            p1 = NamedPoint
            p2 = NamedPoint
        self.assertRaises(CError, Segment)
        self.assertRaises(CError, Segment.parse, NP_BUF * 2)
        
        class Segment(CStruct):
            p1 = NamedPoint()
            p2 = NamedPoint()
        self.assertRaises(CError, Segment)
        self.assertRaises(CError, Segment.parse, NP_BUF * 2)
        self.assertRaises(CError, Segment, p1 = "not a Segment instance")
    
    def test_unsubclassed_structs(self):
        self.assertRaises(CError, CStruct)
        self.assertRaises(CError, CStruct.sizeof)
        self.assertRaises(CError, CStruct.get_type)
        self.assertRaises(CError, CStruct.parse, "")
        self.assertRaises(CError, CStruct.struct_format)
    
    def test_duplicate_fields(self):
        class Point(CStruct):
            x = y = CInt()
        self.assertRaises(CWarning, Point)
        self.assertRaises(CWarning, Point.parse, "\0" * 8)
    
    def test_repr_eval(self):
        np = NamedPoint.parse(NP_BUF)
        pg = PointGroup(count=2, points=[np, np])
        self.assertEqual(pg, eval(repr(pg)))
    
    def test_valid_inheritance(self):
        class Origin(NamedPoint):
            x = y = CInt(always = 0)
        orig = Origin()
        self.assertEqual([orig.x, orig.y], [0, 0])
        self.assertRaises(CWarning, Origin.parse, NP_BUF)
    
    def test_invalid_inheritance(self):
        class Origin(NamedPoint):
            x = y = CChar(always = 0)
        self.assertRaises(CError, Origin)
        
        class Origin(NamedPoint):
            x = y = 0
        self.assertRaises(CError, Origin)
    
    def test_type_coercion(self):
        self.assertEqual(5, NamedPoint(x="5").x)
        self.assertEqual(b"6", NamedPoint(name=6).name)
        
        class Letter(CStruct):
            c = CChar()
        self.assertEqual(5, Letter(c=5).c)
        self.assertEqual(ord("A"), Letter(c="A").c)
        
        class Letters(CStruct):
            xs = CArray(2, CChar)
        self.assertEqual([5, ord("A")], Letters(xs=[5,"A"]).xs)
        
        class Point(CStruct):
            xy = CArray(2, CChar, default=[5,"\x06"])
        self.assertEqual(Point().xy, [5,6])
        self.assertEqual(Point(xy=[1]).serialize(), b"\x01\x06")
        
        class Point(CStruct):
            xy = CArray(2, CChar, default=lambda: [5,"\x06"])
        self.assertEqual(Point().xy, [5,6])
        self.assertEqual(Point(xy=[1]).serialize(), b"\x01\x06")
        
        self.assertRaises(CError, NamedPoint, x=5.6)
        self.assertRaises(CError, CArray, 2, CInt, always=[0, 1.2])
        self.assertRaises(CError, CArray, 2, CInt, default=[0, 1.2])
        self.assertRaises(CError, CArray, 2, CInt, default=lambda:[0, 1.2])
        
        assert_works_without_warnings(NamedPoint, x=5.6)
        assert_works_without_warnings(CArray, 2, CInt, always=[0, 1.2])
        assert_works_without_warnings(CArray, 2, CInt, default=[0, 1.2])
        assert_works_without_warnings(CArray, 2, CInt, default=lambda:[0, 1.2])
    
    def test_invalid_unicode_params(self):
        self.assertRaises(CError, CInt, encoding = "utf8")
        self.assertRaises(CError, CInt, enc_errors = "ignore")
        self.assertRaises(CError, CUnicode)
        self.assertRaises(CError, CUnicode, length=5)
        self.assertRaises(CError, CUnicode, encoding="utf8")
        self.assertRaises(CError, CUnicode, length=5, encoding=None)
        self.assertRaises(CError, CUnicode, length=5, encoding="invalid encoding")
    
    def test_valid_unicode_params(self):
        CUnicode(length=5, encoding="utf8")
        CUnicode(length=5, encoding="utf8", enc_errors="strict")
        CUnicode(length=5, encoding="utf8", enc_errors="ignore")
        CUnicode(length=5, encoding="utf8", enc_errors="replace")
        CUnicode(length=5, encoding="utf8", default="hello")
        CUnicode(length=5, encoding="utf8", default="hello")
    
    def test_unicode_integrity(self):
        andre = b"andr\xc3\xa9".decode('latin-1')
        
        cu = CUnicode(length=6, encoding="latin-1")
        self.assertEqual(andre, cu.parse(cu.serialize(andre)))
        
        class Person(CStruct):
            name = CUnicode(length=9, encoding="utf8")
        p = Person(andre)
        s = Person(andre).serialize()
        self.assertEqual(p, Person.parse(s))
        self.assertEqual(andre, p.name)
        self.assertEqual(p.name, Person.parse(s).name)
    
    def test_unicode_coercion(self):
        andre = "andré"
        class Name(CStruct):
            first = CString(length=9)
            last = CUnicode(length=9, encoding="utf8")
        
        if sys.version_info < (3, 0):
            self.assertRaises(CError, Name, first=andre)
        
        name = Name(first="andre", last="giant")
        self.assertTrue(isinstance(name.first, bytes))
        self.assertTrue(isinstance(name.last, unicode))
        
        name = Name(first=5, last=5)
        self.assertEqual(name.last, "5")
        self.assertEqual(name.first, b"5")
        self.assertTrue(isinstance(name.first, bytes))
        self.assertTrue(isinstance(name.last, unicode))
        
        s = CUnicode(length=6, encoding="utf8").serialize(andre)
        self.assertEqual(andre, Name(last=s).last)
    
    def test_encoding_errors(self):
        class Person(CStruct):
            name = CUnicode(length=9, encoding="utf8")
        self.assertRaises(CError, Person, name=b"\x80")
        self.assertRaises(CError, setattr, Person(), "name", b"\x80")
        
        class Person(CStruct):
            name = CUnicode(length=9, encoding="utf8", enc_errors="ignore")
        self.assertEqual("", Person(name=b"\x80").name)
        p = Person()
        p.name = b"\x80"
        self.assertEqual("", p.name)
        
        class Person(CStruct):
            name = CUnicode(length=9, encoding="utf8", enc_errors="replace")
        self.assertEqual("\ufffd", Person(name=b"\x80").name)
        p = Person()
        p.name = b"\x80"
        self.assertEqual("\ufffd", p.name)
    
    def test_length_problems(self):
        self.assertRaises(CWarning, CUnicode(length=5, encoding="utf8").serialize, "andré")
        
        class Person(CStruct):
            name = CString(length=5, default="marvin")
        self.assertRaises(CError, Person)
        assert_works_without_warnings(Person)
        
        class Person(CStruct):
            name = CString(length=5)
        p = Person()
        self.assertRaises(CError, setattr, p, "name", "marvin")
        assert_works_without_warnings(setattr, p, "name", "marvin")
        
        class Person(CStruct):
            name = CUnicode(length=5, encoding="utf8", default="andré")
        self.assertRaises(CError, Person)
        assert_works_without_warnings(Person)
        
        class Person(CStruct):
            name = CUnicode(length=5, encoding="utf8")
        p = Person()
        self.assertRaises(CError, setattr, p, "name", "andré")
        assert_works_without_warnings(setattr, p, "name", "andré")
        
        class Name(CStruct):
            first = CString(length=5)
            last = CUnicode(length=5, encoding="utf8")
        self.assertRaises(CError, Name, first="marvin")
        self.assertRaises(CError, Name, last="andré")
        assert_works_without_warnings(Name, first="marvin")
        assert_works_without_warnings(Name, last="andré")

class VarlengthTests(TestCase):
    def test_varlength_structs(self):
        buf = b"\xff\0\x02" + NP_BUF + NP_BUF
        pg = PointGroup(count=2, points=[NamedPoint(x=5,y=6), NamedPoint(x=5,y=6)])
        self.assertEqual(pg.serialize(), buf)
        self.assertEqual(pg, PointGroup.parse(buf))
    
    def test_nested_varlength(self):
        class GeoStuff(CStruct):
            code    = CShort(always = 255)
            pg      = PointGroup.get_type()
            message = CString(length=100, default=b"hw")
        
        buf = b"\0\xff\xff\0\x02" + NP_BUF + NP_BUF + b"hw" + b"\0" * 98
        pg = PointGroup(count=2, points=[NamedPoint(x=5,y=6), NamedPoint(x=5,y=6)])
        gs = GeoStuff(pg = pg)
        self.assertEqual(gs.message, b"hw")
        self.assertEqual(gs.serialize(), buf)
        self.assertEqual(gs, GeoStuff.parse(buf))
    
    def test_multi_varlength(self):
        class Messages(CStruct):
            glen     = CChar()
            greeting = CString(length = "glen")
            flen     = CChar()
            farewell = CString(length = "flen")
            version  = CChar(always = 9)
        
        buf = b"\x05hello\x07goodbye\x09"
        mess = Messages(greeting="hello", farewell="goodbye", glen=5, flen=7)
        self.assertEqual(mess.version, 9)
        self.assertEqual(mess.serialize(), buf)
        self.assertEqual(mess, Messages.parse(buf))
    
    def test_derived_varlength(self):
        class AnnoyingSizing(CStruct):
            size = CShort()
            arr  = CArray("real_size", CChar)
            
            @property
            def real_size(self):
                return self.size // 2
        
        buf = b"\0\x06\x01\x02\x03"
        ann = AnnoyingSizing(size=6, arr=[1,2,3])
        self.assertEqual(ann.serialize(), buf)
        self.assertEqual(ann, AnnoyingSizing.parse(buf))
        
        AnnoyingSizing.real_size = "not an integer"
        self.assertRaises(CError, AnnoyingSizing.parse, buf)
    
    def test_varlength_standalone(self):
        mock = type(type.__name__, (), {"foo": 15})
        
        cs = CString(length = "foo")
        buf = cs.serialize(b"Hello World!", cstruct=mock)
        s = cs.parse(buf, cstruct=mock)
        self.assertEqual(15, len(buf))
        self.assertEqual(s, b"Hello World!")
        
        ca = CArray("foo", CChar(default=0))
        buf = ca.serialize([1,2,3], cstruct=mock)
        xs = ca.parse(buf, cstruct=mock)
        self.assertEqual(15, len(buf))
        self.assertEqual(xs, [1,2,3] + [0]*12)
    
    def test_varlength_attrs(self):
        mock = type(type.__name__, (), {"foo": 3})
        pg = PointGroup(count=1, points=[NamedPoint(x=5,y=6)])
        self.assertEqual(28, PointGroup.sizeof(pg))
        self.assertEqual(b"Bh" + NamedPoint.struct_format(), PointGroup.struct_format(cstruct = pg))
        self.assertEqual(12, CArray("foo", CInt).sizeof(cstruct = mock))
        self.assertEqual(b"hhh", CArray("foo", CShort).struct_format(cstruct = mock))
    
    def test_varlength_missing_length(self):
        self.assertRaises(CError, CString(length="foo").sizeof)
        self.assertRaises(CError, CString(length="foo").struct_format)
        self.assertRaises(CError, PointGroup.sizeof)
        self.assertRaises(CError, PointGroup.struct_format)
    
    def test_varlength_bad_lengths(self):
        class VarLen(CStruct):
            size = CChar()
            arr  = CArray("size", CChar)
        
        vl = VarLen(size=2, arr=[1,2])
        vl.arr.pop()
        self.assertRaises(CError, vl.serialize)
        vl.arr.extend([5,6])
        self.assertRaises(CWarning, vl.serialize)
        
        self.assertRaises(CError, VarLen, arr=[1,2])
        self.assertRaises(CError, VarLen, size=2, arr=[1])
        self.assertRaises(CError, VarLen, size=2, arr=[1,2,3])
        self.assertRaises(CError, VarLen.parse, b"\x02\x05")
    
    def test_varlength_bad_order(self):
        class BadVarlength(CStruct):
            arr  = CArray("size", CChar)
            size = CChar()
        
        self.assertRaises(CError, BadVarlength)
        self.assertRaises(CError, BadVarlength, size=2, arr=[5,6])
        self.assertRaises(CError, BadVarlength.parse, b"\x05\x06\x02")
    
    def test_negative_varlength(self):
        class NegVarLength(CStruct):
            size = CChar()
            arr  = CArray("size", CInt(default=0))
        self.assertRaises(CError, NegVarLength, -1)
        self.assertRaises(CError, NegVarLength.parse, b"\xFF")
    
    def test_varlength_matrix(self):
        for outer_size in [2, "size"]:
            class Matrix(CStruct):
                size   = CChar()
                matrix = CArray(outer_size, CArray("size", CChar))
            
            buf = b"\x02\x05\x06\x07\x0b"
            mat = Matrix(size=2, matrix=[[5,6],[7,11]])
            self.assertEqual(mat.serialize(), buf)
            self.assertEqual(mat, Matrix.parse(buf))
    
    def test_varlength_defaults(self):
        class DefaultEmpty(CStruct):
            size   = CChar(default = 0)
            string = CString(length = "size")
        self.assertEqual(b"\0", DefaultEmpty.parse(b"\0").serialize())
        self.assertEqual(b"", DefaultEmpty.parse(b"\0").string)
        self.assertEqual(b"", DefaultEmpty().string)
        
        class DefaultEmpty(CStruct):
            size = CChar(default = 0)
            arr  = CArray("size", CInt)
        self.assertEqual(b"\0", DefaultEmpty.parse(b"\0").serialize())
        
        class DefaultConflict(CStruct):
            size = CChar(default = 2)
            arr = CArray("size", CInt, default=[])
        self.assertRaises(CError, DefaultConflict.parse, b"\0")
        self.assertRaises(CError, DefaultConflict)
        
        class DerivedDefault(CStruct):
            size = CChar(default = 2)
            arr = CArray("size", CInt(default=5))
        self.assertEqual(DerivedDefault().arr, [5,5])

class AutosizedTests(TestCase):
    def test_basic(self):
        self.assertEqual(b"hello", CString(length=AUTOSIZED).parse(b"hello\0world"))
        self.assertEqual(b"hello\0", CString(length=AUTOSIZED).serialize(b"hello"))
        self.assertEqual(b"hello\0", CString(length=AUTOSIZED).serialize(b"hello\0\0\0"))
    
    def test_structs(self):
        buf = b"\0\x01asher\0\0\x04"
        class Person(CStruct):
            code = CShort(always = 1)
            name = CString(length = AUTOSIZED)
            age = CShort()
        p = Person.parse(buf)
        self.assertEqual(p.code, 1)
        self.assertEqual(p.name, b"asher")
        self.assertEqual(p.age, 4)
        self.assertEqual(buf, p.serialize())
    
    def test_parsing(self):
        buf = Person(name="Eli").serialize()[:-1]
        self.assertRaises(CError, CString(length=AUTOSIZED).parse, b"Eli")
        self.assertRaises(CError, Person.parse, b"\0\x09Eli")
    
    def test_sizeof(self):
        class Person(CStruct):
            name = CString(length = AUTOSIZED)
        self.assertRaises(CError, Person.sizeof)
        self.assertRaises(CError, Person.sizeof, Person())
        self.assertEqual(4, Person.sizeof(Person(name="Eli")))
        
        class Person(CStruct):
            name = CString(length = AUTOSIZED)
            age = CShort()
        self.assertRaises(CError, Person.sizeof)
        self.assertEqual(6, Person.sizeof(Person(name="Eli")))
        
        class Person(CStruct):
            name = CString(length=AUTOSIZED, default="")
            age = CShort()
        self.assertEqual(3, Person.sizeof(Person()))
    
    def test_nested(self):
        class Person(CStruct):
            code = CChar(always = 1)
            name = CString(length = AUTOSIZED)
            age = CShort()
        
        class Department(CStruct):
            name = CString(length = AUTOSIZED)
            people = CArray(2, Person.get_type(default=Person(name="", age=0)))
        
        default_person = b"\x01\0\0\0"
        buf = b"foo\0" + default_person * 2
        self.assertEqual(buf, Department("foo").serialize())
        self.assertEqual(Department("foo"), Department.parse(buf))
        
        buf = b"foo\0\x01Eli\0\0\x1c\x01Asher\0\0\x04"
        dept = Department("foo", [Person(name="Eli", age=28), Person(name="Asher", age=4)])
        self.assertEqual(buf, dept.serialize())
        self.assertEqual(dept, Department.parse(buf))
    
    def test_unicode(self):
        andre = "andré"
        
        class Person(CStruct):
            code = CChar(always = 1)
            name = CUnicode(length=AUTOSIZED, encoding="utf8")
            age = CShort()
        
        class Department(CStruct):
            name = CUnicode(length=AUTOSIZED, encoding="utf8")
            people = CArray(2, Person.get_type(default=Person(name="", age=0)))
        
        default_person = b"\x01\0\0\0"
        buf = b"foo\0" + default_person * 2
        self.assertEqual(buf, Department("foo").serialize())
        self.assertEqual(Department(b"foo"), Department.parse(buf))
        
        buf = b"foo\0\x01andr\xc3\xa9\0\0\x1c\x01Asher\0\0\x04"
        dept = Department(b"foo", [Person(name=andre, age=28), Person(name=b"Asher", age=4)])
        self.assertEqual(buf, dept.serialize())
        self.assertEqual(dept, Department.parse(buf))
    
    def test_unicode_null_problem(self):
        s = "Hello World!".encode("utf-32")
        self.assertTrue(s.count(b"\0"))
        self.assertRaises(CError, CUnicode(length=AUTOSIZED, encoding="utf-32").parse, s)
        
        class Person(CStruct):
            name = CUnicode(length=AUTOSIZED, encoding="utf-32")
        self.assertRaises(CError, Person.parse, s)

class SubclassedCTypeTests(TestCase):
    def test_even_padded(self):
        class Person(CStruct):
            name = EvenPaddedCString()
            age = CShort()
        
        asher = Person(name="Asher", age=4)
        buf = asher.serialize()
        self.assertEqual(buf, b"Asher\0\0\x04")
        self.assertEqual(asher, Person.parse(buf))
        self.assertEqual(b"Asher", Person.parse(buf).name)
        
        liam = Person(name="Liam", age=1)
        buf = liam.serialize()
        self.assertEqual(buf, b"Liam\0\0\0\x01")
        self.assertEqual(liam, Person.parse(buf))
        self.assertEqual(b"Liam", Person.parse(buf).name)
    
    def test_json(self):
        class Person(CStruct):
            name = CString(length = AUTOSIZED)
            data = JsonCString(length = AUTOSIZED)
        
        asher = Person(name="Asher", data={"age": 4})
        buf = asher.serialize()
        self.assertEqual(asher, Person.parse(buf))
        self.assertEqual(buf, b'Asher\0{"age": 4}\0')
        self.assertEqual({"age": 4}, Person.parse(buf).data)
        
        person = Person()
        self.assertRaises(Exception, Person.parse, "Eli\0{\0")
        self.assertRaises(Exception, setattr, person, "data", {"unserializable": protlib})
    
    def test_sizeof(self):
        class Person(CStruct):
            name = EvenPaddedCString()
            data = JsonCString(length = AUTOSIZED)
        
        self.assertEqual(7, Person.sizeof(Person("Eli", {})))

class NonCPythonTests(TestCase):
    def setUp(self):
        if hasattr(sys, "_getframe"):
            self._getframe = sys._getframe
            del sys._getframe
    
    def tearDown(self):
        sys._getframe = self._getframe
    
    def test_parser(self):
        self.assertRaises(CError, Parser)
        Parser(module = __import__(__name__))
    
    def test_handler(self):
        class Handler(ProtHandler): pass
        self.assertRaises(CError, Handler)
        
        class Handler(ProtHandler):
            STRUCT_MOD = __import__(__name__)
        Handler()

class UnderscorizeTests(TestCase):
    def test_camelcase(self):
        self.assertEqual("some_struct",   underscorize("SomeStruct"))
        self.assertEqual("ssn_lookup",    underscorize("SSNLookup"))
        self.assertEqual("rs485_adaptor", underscorize("RS485Adaptor"))
        self.assertEqual("rot13_encoded", underscorize("Rot13Encoded"))
        self.assertEqual("request_q",     underscorize("RequestQ"))
        self.assertEqual("john316",       underscorize("John316"))
    
    def test_already_underscored(self):
        self.assertEqual("rs485adaptor",  underscorize("rs485adaptor"))
        self.assertEqual("rot13_encoded", underscorize("rot13_encoded"))

class BadHandlerTests(TestCase):
    def test_no_structs(self):
        class EmptyHandler(ProtHandler):
            class STRUCT_MOD:
                pass
        self.assertRaises(CError, EmptyHandler)
    
    def test_duplicate_starts(self):
        warnings.simplefilter("error", CWarning)
        class DupHandler(ProtHandler):
            class STRUCT_MOD:
                class Foo(CStruct):
                    code = CInt(always = 1)
                class Bar(CStruct):
                    code = CInt(always = 1)
        self.assertRaises(CWarning, DupHandler)
    
    def test_bad_struct_name(self):
        class BadNameHandler(ProtHandler):
            class STRUCT_MOD:
                class Handle(CStruct):
                    code = CInt(always = 1)
        self.assertRaises(CError, BadNameHandler)

class LoggerTests(TestCase):
    logfiles = ["logger_test.{0}_log".format(log) for log in Logger.LEVELS]
    
    def setUp(self):
        self.delete_logs()
    
    def tearDown(self):
        self.delete_logs()
    
    def delete_logs(self):
        for fname in self.logfiles:
            if os.path.exists(fname):
                os.remove(fname)
    
    def test_logfile_creation(self):
        Logger(prefix = "logger_test")
        for fname in self.logfiles:
            if sys.version_info[:3] >= (2, 6, 2):
                self.assertFalse(os.path.exists(fname))
            else:
                self.assertTrue(os.path.exists(fname))

class ServerTestBase:
    def setUp(self):
        self.reset_logs()
        self.server = self.ServerClass(SERVER_ADDR, self.HandlerClass)
        t = Thread(target=self.server.serve_forever)
        t.daemon = True
        t.start()
        
        self.client_setup()
        
        self.np = NamedPoint(x=5, y=6)
        self.rp = RenamedPoint(x=5, y=6)
    
    def tearDown(self):
        self.sock.close()
        self.server.server_close()
        self.server.shutdown()
        self.reset_logs()
    
    def send(self, data):
        self.f.write(data.serialize() if isinstance(data, CStruct) else data)
        self.f.flush()
    
    def client_setup(self):
        self.sock = socket.create_connection(SERVER_ADDR)
        self.f = self.sock.makefile("rwb", 0)
    
    def client_teardown(self):
        self.f.close()
        self.sock.close()
    
    def reset_logs(self):
        for suffix in Logger.LEVELS:
            handlers = logging.getLogger(Logger.DEFAULT_PREFIX + "." + suffix).handlers
            if handlers and handlers[0].stream:
                handlers[0].stream.truncate(0)
    
    def read_log(self, name):
        with open(Logger.DEFAULT_PREFIX + "." + name + "_log") as f:
            return f.read()

class ServerTests(ServerTestBase):
    def test_struct_response(self):
        self.send(self.np)
        s = self.f.read( RenamedPoint.sizeof() )
        rp = RenamedPoint.parse(s)
        self.assertEqual(rp, self.rp)
    
    def test_string_response(self):
        self.send(self.rp)
        self.assertEqual(self.f.readline(), b"Hello World!\n")
    
    def test_too_short(self):
        self.send( self.np.serialize()[:5] )
        sleep(0.2)
        self.assertTrue("struct received only" in self.read_log("error"))
    
    def test_no_handler(self):
        self.send( NamedOrigin() )
        sleep(0.2)
        self.assertTrue("handler not defined" in self.read_log("error"))
    
    def test_unknown(self):
        self.send(b"raw data")
        sleep(0.2)
        self.assertTrue("unable to resolve" in self.read_log("error"))
    
    def test_multiple_clients(self):
        self.test_struct_response()
        self.client_teardown()
        self.client_setup()
        self.test_struct_response()
    
    def test_varlength(self):
        pg1 = PointGroup(count=2, points=[NamedPoint(x=5,y=6), NamedPoint(x=7,y=11)])
        self.send(pg1)
        pg2 = PointGroup.parse( self.f.read(3 + 4 * NamedPoint.sizeof()) )
        self.assertEqual(pg2.count, 4)
        self.assertEqual(pg2.points[:2], pg2.points[2:])
    
    def test_varlength_too_short(self):
        pg = PointGroup(count=2, points=[NamedPoint(x=5,y=6), NamedPoint(x=7,y=11)])
        self.send( pg.serialize()[:-1] )
        sleep(0.2)
        self.assertTrue("struct received only" in self.read_log("error"))
    
    def test_autosized_too_short(self):
        self.send(Person(name = "Eli").serialize()[:-1])
        sleep(0.2)
        self.assertTrue("struct received only" in self.read_log("error"))

class TCPServerTests(ServerTests, TestCase):
    ServerClass = LoggingTCPServer
    HandlerClass = TCPTestHandler

class UDPServerTests(ServerTests, TestCase):
    ServerClass = LoggingUDPServer
    HandlerClass = UDPTestHandler
    
    def client_setup(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(CLIENT_ADDR)
        self.f = self.sock.makefile("rb")
    
    def send(self, data):
        self.sock.sendto(data.serialize() if isinstance(data, CStruct) else data, SERVER_ADDR)

class TCPTimeoutTests(ServerTestBase, TestCase):
    ServerClass = LoggingTCPServer
    class HandlerClass(TCPHandler):
        timeout = 2
    
    def test_immediate_timeout(self):
        sleep(0.1)
        before = time()
        self.server.server_close()
        self.server.shutdown()
        self.assertTrue(time() - before < 2)
    
    def test_full_timeout(self):
        before = time()
        self.server.shutdown()
        self.assertTrue(time() - before < 3)  # just because we have a 2 second timeout doesn't mean it'll take anywhere close to 2 seconds, but it should always take well under 3

class TCPReadRecvInteract(ServerTestBase, TestCase):
    ServerClass = LoggingTCPServer
    class HandlerClass(TCPHandler):
        def named_origin(self, no):
            self.log_struct( NamedOrigin.parse(self.rfile) )
            return NamedOrigin()
    
    def test_recv_read_interaction(self):
        for i in range(9):
            self.send(NamedOrigin())
            self.send(NamedOrigin())
            NamedOrigin.parse(self.f)

if __name__ == "__main__":
    logging.basicConfig(level = logging.DEBUG)
    delete_logs()
    atexit.register(delete_logs)
    main()
