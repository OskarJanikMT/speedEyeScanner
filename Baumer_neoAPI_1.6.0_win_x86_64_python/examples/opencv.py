#!/usr/bin/env python3

''' A simple Program for grabing video from baumer camera and converting it to opencv img.
'''

import sys
import cv2
import neoapi

# get image and display (opencv)
result = 0
try:
    camera = neoapi.Cam()
    camera.Connect()
    camera.f.ExposureTime.Set(10000)

    save_image = True
    for cnt in range(0, 200):
        img = camera.GetImage()
        if not img.IsEmpty():
            imgarray = img.GetNPArray()
            title = 'Press [ESC] to exit ..'
            cv2.namedWindow(title, cv2.WINDOW_NORMAL)
            cv2.imshow(title, imgarray)
            if save_image:
                save_image = False
                cv2.imwrite('opencv_python.bmp', imgarray)
        if cv2.waitKey(1) == 27:
            break
    cv2.destroyAllWindows()

except (neoapi.NeoException, Exception) as exc:
    print('error: ', exc)
    result = 1

sys.exit(result)
