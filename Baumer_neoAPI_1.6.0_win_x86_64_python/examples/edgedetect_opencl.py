# \example edgedetect_opencl.py
# This example describes the use of buffers allocated by the user or other frameworks.
# The given source code applies to handle one camera and image acquisition.
#

import sys
import threading
import time
import neoapi
import cv2
import numpy

class MemoryMode:
    cpu = cv2.USAGE_ALLOCATE_HOST_MEMORY
    gpu = cv2.USAGE_ALLOCATE_DEVICE_MEMORY
    shared = cv2.USAGE_ALLOCATE_SHARED_MEMORY

class CamBuffer(neoapi.BufferBase):
    """implementation for user buffer mode"""
    def __init__(self, width, height, memtype):
        neoapi.BufferBase.__init__(self)
        self.memtype = memtype
        if memtype == MemoryMode.cpu:
            self.cpu_mat = numpy.ndarray((height, width, 1), numpy.uint8)
        else:
            self.gpu_mat = cv2.UMat(height, width, cv2.CV_8UC1)
            self.cpu_mat = self.gpu_mat.get()
        self.RegisterSegment(self.cpu_mat, width * height * 1)

    def __del__(self):
        self.UnregisterMemory()

class EdgeDetector:
    def __init__(self, serialnumber):
        self._camera = neoapi.Cam()
        self._camera.Connect(serialnumber)
        self._camera.f.ExposureTime.Set(2500)
        self._camera.DisableChunk()
        try:
            self._camera.f.PixelFormat.Set(neoapi.PixelFormat_BayerRG8)
        except neoapi.FeatureAccessException:
            self._camera.f.PixelFormat.Set(neoapi.PixelFormat_Mono8)
        self._pixelformat = self._camera.f.PixelFormat.Get()
        self._identifier = serialnumber
        self._buffers = []
        self._grey_mat = cv2.UMat()
        self._gauss_mat = cv2.UMat()
        self._sobel_mat = cv2.UMat()
        self._detect_thread = threading.Thread()
        self._frames = 0
        self._run = False

    def Setup(self, memtype):
        cv2.ocl.setUseOpenCL(MemoryMode.cpu != memtype)
        # if cv2.ocl.Device.getDefault().hostUnifiedMemory():
        #     cv2.ocl.Context.getDefault().setUseSVM(MemoryMode.shared != memtype)
        self._SetupBuffers(3, memtype)
        self._camera.SetUserBufferMode()

    def Detect(self, image, show_image):
        cambuf = image.GetUserBuffer()
        img_mat = cambuf.cpu_mat if cambuf.memtype == MemoryMode.cpu else cv2.UMat(cambuf.cpu_mat)
        if neoapi.PixelFormat_BayerRG8 == self._pixelformat:
            self._grey_mat = cv2.cvtColor(img_mat, cv2.COLOR_BayerRG2GRAY)
        else:
            self._grey_mat = img_mat
        self._gauss_mat = cv2.GaussianBlur(self._grey_mat, (5, 5), 0)
        self._sobel_mat = cv2.Sobel(self._gauss_mat, 0, 1, 1, ksize=5)
        if show_image:
            cv2.imshow(self._identifier, self._sobel_mat)
            cv2.pollKey()
        self._frames += 1

    def ProcessedFrames(self):
        frames = self._frames
        self._frames = 0
        return frames

    def GetIdentifier(self):
        return self._identifier

    def Start(self, show_images):
        self._run = True
        self._detect_thread = threading.Thread(target=self._Detect, args=(show_images,))
        self._detect_thread.start()

    def Stop(self):
        self._run = False
        if self._detect_thread.is_alive():
            self._detect_thread.join()

    def FreeCamBuffers(self):
        while self._buffers:
            self._camera.RevokeUserBuffer(self._buffers.pop())

    def _SetupBuffers(self, count, memtype):
        width = self._camera.f.Width.Get()
        height = self._camera.f.Height.Get()
        self.FreeCamBuffers()
        for _ in range(count):
            self._buffers.append(CamBuffer(width, height, memtype))
            self._camera.AddUserBuffer(self._buffers[-1])
        self._grey_mat = cv2.UMat(height, width, cv2.CV_8UC1, memtype)
        self._gauss_mat = cv2.UMat(height, width, cv2.CV_8UC1, memtype)
        self._sobel_mat = cv2.UMat(height, width, cv2.CV_8UC1, memtype)

    def _Detect(self, show_images):
        try:
            if show_images:
                cv2.namedWindow(self._identifier, cv2.WINDOW_NORMAL)
            while self._run:
                image = self._camera.GetImage()
                if image.IsEmpty():
                    print("%s Error during acquisition!" % self._identifier)
                    break
                self.Detect(image, show_images)
            if show_images:
                cv2.destroyWindow(self._identifier)
        except neoapi.NeoException as exc:
            print("%s error %s" % (self._identifier, exc.GetDescription()))
        except cv2.error as exc:
            print("%s cv error %s" % (self._identifier, exc))


def GetGpuCapalities():
    memtypes = {MemoryMode.cpu: "cpu"}
    if cv2.ocl.haveOpenCL():
        memtypes[MemoryMode.gpu] = "gpu"
    #     if cv2.ocl.Device.getDefault().hostUnifiedMemory():
    #         memtypes[MemoryMode.shared] = "shared"
    return memtypes

def FindDevices():
    devices = []
    for device in neoapi.CamInfoList.Get():
        try:
            devices.append(EdgeDetector(device.GetSerialNumber()))
        except neoapi.NeoException as exc:
            print('error: ', exc)
    print(len(devices), "device(s) connected!")
    return devices

def PrintMetrics(devices, duration):
    for _ in range(duration):
        time.sleep(1.0)
        for device in devices:
            print("%s fps: %s" % (device.GetIdentifier(), device.ProcessedFrames()))

def RunDetection(devices, memtypes, show_images):
    if devices:
        for val, text  in memtypes.items():
            print("Next run will be processed on", text)
            for device in devices:
                device.Setup(val)
            for device in devices:
                device.Start(show_images)
            PrintMetrics(devices, 5)
            for device in devices:
                device.Stop()

def FreeDevices(devices):
    while devices:
        devices.pop().FreeCamBuffers()
    neoapi.CamInfoList.Get().Cleanup()

result = 0

# Showing the images have a high impact on processing speed.
# For better comparision show_images should be disabled.
show_images = len(sys.argv) > 1

# look if the gpu supports opencl and shared memory
memtypes = GetGpuCapalities()

# find all connected cameras
devices = FindDevices()

# edge detection processing on all connected cameras
RunDetection(devices, memtypes, show_images)

# cleanup
FreeDevices(devices)

sys.exit(result)
