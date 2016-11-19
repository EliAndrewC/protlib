from common import *

def credit_card_lookup(ssn):
    if ssn != [0] * 9:
        return [randrange(10) for i in range(12)]

def zip_lookup(ssn):
    if ssn != [0] * 9:
        return [randrange(10) for i in range(5)]

class Handler(TCPHandler):
    LOG_TO_SCREEN = True
    
    def cc_request(self, ccr):
        """return the credit card number of the person with the given SSN"""
        ssn = ccr.params[:9]
        cc_num = credit_card_lookup(ssn)
        if cc_num:
            return CCResponse(params = cc_num)
        else:
            return ErrorMessage(params=ssn, comment="No matching SSN")
    
    def zip_request(self, zr):
        """return the zip code of the person with the given SSN"""
        ssn = zr.params[:9]
        zip_code = zip_lookup(ssn)
        if zip_code:
            return ZipResponse(params = zip_code)
        else:
            return ErrorMessage(params=ssn, comment="No matching SSN")

if __name__ == "__main__":
    LoggingTCPServer(SERVER_ADDR, Handler).serve_forever()
