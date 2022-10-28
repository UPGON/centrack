from typing import Tuple

import cv2
import numpy as np
from skimage.exposure import rescale_intensity
from skimage.feature import blob_log
from spotipy.utils import points_matching

from cenfind.core.data import Field
from cenfind.core.helpers import blob2point


def log_skimage(data: Field, channel: int, **kwargs) -> list:
    data = data.channel(channel)
    data = rescale_intensity(data, out_range=(0, 1))
    foci = blob_log(data, min_sigma=.5, max_sigma=5, num_sigma=10, threshold=.1)
    res = [(int(c), int(r)) for r, c, _ in foci]

    return res


def simpleblob_cv2(data: Field, channel: int, **kwargs) -> list:
    data = data.channel(channel)
    foci = rescale_intensity(data, out_range='uint8')
    params = cv2.SimpleBlobDetector_Params()

    params.blobColor = 255
    params.filterByArea = True
    params.minArea = 5
    params.maxArea = 100
    params.minDistBetweenBlobs = 1
    params.minThreshold = 0
    params.maxThreshold = 255

    detector = cv2.SimpleBlobDetector_create(params)
    keypoints = detector.detect(foci)

    res = [blob2point(kp) for kp in keypoints]

    return res


def run_detection(method, data: Field,
                  annotation: np.ndarray,
                  tolerance,
                  channel=None,
                  model_path=None) -> Tuple[np.ndarray, float]:
    foci = method(data, foci_model_file=model_path, channel=channel)
    if type(foci) == tuple:
        prob_map, foci = foci
    res = points_matching(annotation, foci, cutoff_distance=tolerance)
    f1 = np.round(res.f1, 3)
    return foci, f1