import socket

from common import *

logger = Logger(also_print = True)
parser = Parser(logger)

def rand_ssn():
    return [randrange(10) for i in range(9)]

sock = socket.create_connection(SERVER_ADDR)
f = sock.makefile("rwb", 0)

logger.log_and_write(f, CCRequest(params=rand_ssn()))
ccresp = parser.parse(f)
assert ccresp.code == CCResponse.code.always

logger.log_and_write(f, ZipRequest(params=rand_ssn()))
zresp = parser.parse(f)
assert zresp.code == ZipResponse.code.always

logger.log_and_write(f, ZipRequest())
err = parser.parse(f)
assert err.code == ErrorMessage.code.always

sock.close()
