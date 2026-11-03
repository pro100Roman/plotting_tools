
import math

class OneEuroFilter:
    def __init__(self, sample_freq, mincutoff=1.0, beta=0.0, dcutoff=1.0):
        self.freq = sample_freq
        self.mincutoff = mincutoff
        self.beta = beta
        self.dcutoff = dcutoff
        self.x_prev = None
        self.dx_prev = 0.0

    def alpha(self, cutoff):
        tau = 1.0 / (2 * math.pi * cutoff)
        te = 1.0 / self.freq
        return 1.0 / (1.0 + tau / te)

    def filter(self, x):
        if self.x_prev is None:
            self.x_prev = x
            return x
        dx = (x - self.x_prev) * self.freq
        dx_hat = self.dx_prev + self.alpha(self.dcutoff) * (dx - self.dx_prev)
        cutoff = self.mincutoff + self.beta * abs(dx_hat)
        x_hat = self.x_prev + self.alpha(cutoff) * (x - self.x_prev)
        self.x_prev = x_hat
        self.dx_prev = dx_hat
        return x_hat