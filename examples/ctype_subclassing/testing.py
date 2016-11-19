import json
from protlib import *

class JsonCString(CString):
    def parse(self, f, cstruct=None):
        return json.loads(CString.parse(self, f, cstruct).decode("utf8"))
    
    def serialize(self, s, cstruct=None):
        return CString.serialize(self, json.dumps(s).encode("utf8"), cstruct)
    
    def convert(self, x):
        return x

class Person(CStruct):
    name = CUnicode(encoding = "utf8", length = 6)
    data = JsonCString(length = AUTOSIZED)

eli = Person("Eli", {"age": 28})
assert eli.data == {"age": 28}
assert eli.serialize() == b'Eli\0\0\0{"age": 28}\0'
