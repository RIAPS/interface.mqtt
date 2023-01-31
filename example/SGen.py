# import riaps
from riaps.run.comp import Component
import logging
import math

class SGen(Component):
    def __init__(self):
        super(SGen, self).__init__()
        self.logger.info("SGen() starting")
        self.cnt = 0
        self.lim = 16
        self.stp = 2*math.pi/self.lim
        self.amp = 0.0
        
    def on_tick(self):
        now = self.tick.recv_pyobj()   # Receive time.time() as float
        val = self.cnt * self.stp
        self.cnt = (self.cnt + 1) % self.lim
        msg = math.sin(val) * self.amp
        # self.logger.info('on_tick(): @ %s -> %r' % (str(now),msg))
        self.sine.send_pyobj(msg)
    
    def on_ampl(self):
        msg = self.ampl.recv_pyobj()
        self.amp = msg
        self.logger.info("on_ampl():%r" % self.amp)



