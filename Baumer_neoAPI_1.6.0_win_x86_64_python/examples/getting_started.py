# \example getting_started.py
# This example describes the FIRST STEPS of handling NeoAPI Python SDK.
# The given source code applies to handle one camera and image acquisition
#

import sys
import neoapi

result = 0
try:
    camera = neoapi.Cam()
    camera.Connect()
    camera.f.ExposureTime.Set(10000)

    image = camera.GetImage()
    image.Save("getting_started.bmp")

except (neoapi.NeoException, Exception) as exc:
    print('error: ', exc)
    result = 1

sys.exit(result)
