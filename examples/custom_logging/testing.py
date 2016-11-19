import sys
import time
import logging
from logging.handlers import SMTPHandler, TimedRotatingFileHandler

from protlib import *

class Point(CStruct):
    code = CShort(always = 0x1234)
    x = CInt()
    y = CInt()

logging.basicConfig(level = logging.DEBUG)

trfh = TimedRotatingFileHandler("testing.rotating_log", "s", 1)
logging.getLogger("testing.hex").addHandler(trfh)

logger = Logger()
parser = Parser(logger)

smtp = SMTPHandler("smtp.example.com", "bugs@example.com", ["eli@example.com"], "Stack Trace")
logging.getLogger("testing.stack").addHandler(smtp)

if __name__ == "__main__":
    with open("point.dat","w") as f:
        p1 = Point(x=5, y=6)
        logger.log_and_write(f, p1)
    
    time.sleep(2)
    
    with open("point.dat") as f:
        p2 = parser.parse(f)
    
    try:
        Point(x = "not an integer")
    except CError:
        logger.log_stacktrace()
