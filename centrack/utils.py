import argparse
import re
import json
import argparse
from pathlib import Path

from cv2 import cv2
import numpy as np

from centrack.annotation import Contour


def parse_args():
    parser = argparse.ArgumentParser(description='CCOUNT: Automatic centriole scoring')

    parser.add_argument('dataset', type=Path, help='path to the dataset')
    parser.add_argument('marker', type=str, help='marker to use for foci detection')
    parser.add_argument('coords', type=tuple, help='position, e.g., 0,2')
    parser.add_argument('-o', '--out', type=Path, help='path for output')

    return parser.parse_args()


def extract_filename(file):
    file_name = file.name
    file_name = file_name.removesuffix(''.join(file.suffixes))
    file_name = file_name.replace('', '')
    file_name = re.sub(r'_(Default|MMStack)_\d-Pos', '', file_name)

    return file_name.replace('', '')


def is_tif(filename):
    _filename = str(filename)
    return _filename.endswith('.tif') and not _filename.startswith('.')


def contrast(data):
    return cv2.convertScaleAbs(data, alpha=255 / data.max())


def image_tint(image, tint):
    """
    Tint a gray-scale image with the given tint tuple
    :param image:
    :param tint:
    :return:
    """
    return (image * tint).astype(np.uint8)


def channels_combine(stack, channels=(1, 2, 3)):
    if stack.shape != (4, 2048, 2048):
        raise ValueError(f'stack.shape')

    stack = stack[channels, :, :]
    stack = np.transpose(stack, (1, 2, 0))

    return cv2.convertScaleAbs(stack, alpha=255 / stack.max())


def nuclei_segment(image, threshold=None):
    """
    Extract the nuclei into contours.
    :param threshold: if specified, use it instead of the derived.
    :return: the list of contours detected
    """

    # Define a large blurring kernel (1/16 of the image width)
    _data = image.contrast().data
    image_w, image_h = _data.shape[-2:]
    kernel_size = image_w // 32
    if kernel_size % 2 == 0:
        kernel_size += 1

    nuclei_blurred = (_data
                      .blur_median(ks=kernel_size)
                      .blur_median(ks=kernel_size))

    if threshold:
        threshold_otsu = cv2.THRESH_BINARY + cv2.THRESH_OTSU
        ret, nuclei_thresh = cv2.threshold(nuclei_blurred, 0, 255, threshold_otsu)
    else:
        ret, nuclei_thresh = cv2.threshold(nuclei_blurred, threshold, 255, cv2.THRESH_BINARY)

    nuclei_contours, hierarchy = cv2.findContours(nuclei_thresh, cv2.RETR_TREE,
                                                  cv2.CHAIN_APPROX_SIMPLE)

    nuclei_contours = [Contour(c, idx=c_id, label='nucleus', confidence=-1)
                       for c_id, c in enumerate(nuclei_contours)]

    return nuclei_contours


def mask_create_from_contours(mask, contours):
    """
    Label each blob using connectedComponents.
    :param mask: the black image to draw the contours
    :param contours: the list of contours
    :return: the mask with each contour labelled with different numbers.
    """
    cv2.drawContours(mask, contours, -1, 255, -1)
    _, labels = cv2.connectedComponents(mask)
    return labels


def labelbox_annotation_load(path_annotation, image_name):
    with open(path_annotation, 'r') as file:
        annotation = json.load(file)
    image_labels = [image for image in annotation if image['External ID'] == image_name]

    return image_labels[0]['Label']['objects']
