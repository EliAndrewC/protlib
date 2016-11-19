from math import sqrt

from common import *

class Handler(TCPHandler):
    LOG_TO_SCREEN = True
    
    def vector(self, v):
        """returns the mid-point of the line segment"""
        return Point(x = (v.p1.x + v.p2.x) / 2,
                     y = (v.p1.y + v.p2.y) / 2)
    
    def rectangle(self, r):
        """returns the endpoint closest to the origin"""
        dists = [(sqrt(p.x**2 + p.y**2), p) for p in r.points]
        return min(dists)[1]
    
    def point_group(self, pg):
        """returns a rectangle which encompasses all points in the group"""
        xmin = min(p.x for p in pg.points)
        xmax = max(p.x for p in pg.points)
        ymin = min(p.y for p in pg.points)
        ymax = max(p.y for p in pg.points)
        return Rectangle(points=[
            Point(x=xmin, y=ymin), Point(x=xmin, y=ymax),
            Point(x=xmax, y=ymin), Point(x=xmax, y=ymax)
        ])

if __name__ == "__main__":
    LoggingTCPServer(SERVER_ADDR, Handler).serve_forever()
