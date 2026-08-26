# example user_buffer.py
# This example describes the use of buffers allocated by the user or other frameworks.
# The given source code applies to handle one camera and image acquisition.
#

import sys
use_numpy = False
try:
    import numpy
    use_numpy = True
except ImportError:
    pass
import neoapi
import ctypes

class MyBuffer(neoapi.BufferBase):
    """implementation for user buffer mode"""
    def __init__(self, size):
        neoapi.BufferBase.__init__(self)
        self._buf = numpy.zeros(size, numpy.uint8) if use_numpy else bytearray(size)
        self._size = size
        self.RegisterMemory(self._buf, self._size)

    def CalcVar(self):
        var = -1
        if use_numpy: # buf contains the image data and can be used with numpy
            var = self._buf.var()
        elif self._size > 0:
            sum = 0.0
            for i in range(0, self._size):
                sum += self._buf[i]
            avg = sum / self._size

            sum = 0.0
            for i in range(0, self._size):
                sum += (self._buf[i] - avg) ** 2
            var = sum / self._size
        return var


result = 0
try:
    camera = neoapi.Cam()
    camera.Connect()

    payloadsize = camera.f.PayloadSize.Get()
    buf = MyBuffer(payloadsize)
    camera.AddUserBuffer(buf)

    camera.f.ExposureTime.Set(10000)
    camera.SetUserBufferMode(True)

    image = camera.GetImage()
    image.Save('user_buffer.bmp')
    print("Image variance:", image.GetUserBuffer().CalcVar())

except (neoapi.NeoException, Exception) as exc:
    print('error: ', exc)
    result = 1

sys.exit(result)
