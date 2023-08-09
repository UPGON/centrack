from typing import Tuple

import cv2
import numpy as np
from attrs import define

from cenfind.core.data import Field
from cenfind.core.log import get_logger

logger = get_logger(__name__)


@define
class Centriole:
    """
    Represent a centriole as a 2d point associated with a Field and a channel index.
    """
    field: Field
    channel: int
    centre: Tuple[int, int]
    index: int = 0
    label: str = ""
    parent: 'Centriole' = None

    @property
    def centre_xy(self):
        y, x = self.centre
        return x, y

    def intensity(self, image: np.ndarray, k: int = 0, channel: int = None):
        r, c = self.centre
        max_r, max_c = image.shape[-2:]

        r_start = np.clip(r - k, 0, max_r)
        r_stop = np.clip(r + k, 0, max_r)
        c_start = np.clip(c - k, 0, max_c)
        c_stop = np.clip(c + k, 0, max_c)

        if image.ndim < 3:
            return np.sum(image[r_start:r_stop, c_start:c_stop])
        if channel is None:
            raise ValueError('Channel must be supplied when image has 3 dimensions')
        return np.sum(image[channel, r_start:r_stop, c_start:c_stop])


@define
class Nucleus:
    field: Field
    channel: int
    contour: np.ndarray
    index: int = 0
    label: str = ""

    @property
    def centre(self):
        moments = cv2.moments(self.contour)
        centre_x = int(moments["m10"] / (moments["m00"] + 1e-5))
        centre_y = int(moments["m01"] / (moments["m00"] + 1e-5))
        return centre_y, centre_x

    @property
    def centre_xy(self):
        y, x = self.centre
        return x, y

    @property
    def intensity(self):
        _data = self.field.data[self.channel, ...]
        mask = np.zeros_like(_data)
        cv2.drawContours(mask, [self.contour], 0, 255, -1)
        masked = cv2.bitwise_and(_data, mask)
        return np.sum(masked)

    @property
    def area(self):
        return cv2.contourArea(self.contour)
