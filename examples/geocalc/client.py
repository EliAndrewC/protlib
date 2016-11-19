import socket
from random import randrange

from common import *

def rand_point():
    return Point(x=randrange(100), y=randrange(100))

logger = Logger(also_print = True)
parser = Parser(logger)
sock = socket.create_connection(SERVER_ADDR)
f = sock.makefile("rwb", 0)

vec = Vector(p1=rand_point(), p2=rand_point())
logger.log_and_write(f, vec)
pt = parser.parse(f)
assert vec.p1.x < pt.x < vec.p2.x or vec.p1.x > pt.x > vec.p2.x
assert vec.p1.y < pt.y < vec.p2.y or vec.p1.y > pt.y > vec.p2.y

rect = Rectangle(points=[Point(x=1, y=1),
                         Point(x=1, y=5),
                         Point(x=5, y=1),
                         Point(x=5, y=5)])
logger.log_and_write(f, rect)
pt = parser.parse(f)
assert pt.x == pt.y == 1

points = [rand_point() for i in range(10)]
logger.log_and_write(f, PointGroup(count=10, points=points))
rect = parser.parse(f)
assert rect.code == Rectangle.code.always

sock.close()
