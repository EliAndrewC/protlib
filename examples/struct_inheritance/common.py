from random import randrange
from datetime import datetime

from protlib import *

SERVER_ADDR = ("127.0.0.1", 5665)

class Message(CStruct):
    code      = CInt()
    timestamp = CString(length=20, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    comment   = CString(length=100, default="")
    params    = CArray(20, CInt(default=0))

class ErrorMessage(Message): code = CInt(always = 0)
class CCRequest(Message):    code = CInt(always = 1)
class CCResponse(Message):   code = CInt(always = 2)
class ZipRequest(Message):   code = CInt(always = 3)
class ZipResponse(Message):  code = CInt(always = 4)
