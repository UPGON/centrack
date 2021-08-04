import re
from pathlib import Path
import json
import re
import pdb

import cv2
import numpy as np
from matplotlib import pyplot as plt
import tifffile as tf


def channels_combine(stack, channels=(1, 2, 3)):
    if stack.shape != (4, 2048, 2048):
        raise ValueError(f'stack.shape')

    stack = stack[channels, :, :]
    stack = np.transpose(stack, (1, 2, 0))

    return cv2.convertScaleAbs(stack, alpha=255 / stack.max())


def filename_split(file_name):
    """
    Extract the info in the filename string
    e.g., RPE1wt_CEP152+GTU88+PCNT_1_MMStack_1-Pos_000_000.ome.tif
    or RPE1wt_CEP152+GTU88+PCNT_1_000_000_max.ome.tif
    :param file_name:
    :return:
    """
    if file_name.rfind('_max'):
        pattern = re.compile(r'([\w\d^_]+)_([A-Z0-9\+]+)_(\d+)_(\d+)_(\d+)_max.ome.tif')
    else:
        pattern = re.compile(r'([\w\d\+]+)_([\w\d\+]+)_MMStack_\d+-Pos_(\d+)_(\d+).ome.tif')

    return re.match(pattern, file_name)


def cnt_centre(contour):
    """
    Compute the centre of a contour
    :param contour:
    :return: the coordinates of the contour
    """
    moments = cv2.moments(contour)

    c_x = int(moments['m10'] / moments['m00'])
    c_y = int(moments['m01'] / moments['m00'])

    return c_x, c_y


def image_tint(image, tint):
    """
    Tint a gray-scale image with the given tint tuple
    :param image:
    :param tint:
    :return:
    """
    return (image * tint).astype(np.uint8)


def label_mask_write(dest, labels):
    """
    Write a visualisation of the labels.
    :param dest:
    :param labels:
    :return:
    """
    labels_vis = 255 * (labels / labels.max())
    cv2.imwrite(str(dest), labels_vis)


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


def label_coordinates(label):
    return label['point'].values()


def image_8bit_contrast(image):
    return cv2.convertScaleAbs(image, alpha=255 / image.max())


def markers_from(dataset_name, marker_sep='+'):
    """
    Extract the markers' name from the dataset string.
    The string must follows the structure `<genotype>_marker1+marker2`
    It append the DAPI at the beginning of the list.

    :param marker_sep:
    :param dataset_name:
    :return: a dictionary of markers
    """

    markers = dataset_name.split('_')[-2].split(marker_sep)

    if 'DAPI' not in markers:
        markers = ['DAPI'] + markers

    return {k: v for k, v in enumerate(markers)}


def channel_extract(stack, channel_id):
    """
    Extract a channel and apply a projection.
    :param stack: 3D array
    :return: 2D array for the channel
    """
    return stack[channel_id, :, :]


def coords2mask(foci_coords, shape, radius):
    mask = np.zeros(shape, np.uint8)
    for r, c in foci_coords:
        cv2.circle(mask, (r, c), radius, 255, thickness=-1)

    return mask


if __name__ == '__main__':
    path_root = Path('/Volumes/work/datasets/RPE1wt_CEP63+CETN2+PCNT_1')
    path_raw = path_root / 'raw'

    file = path_root / 'projected/RPE1wt_CEP63+CETN2+PCNT_1_000_000.png'
    labels = labelbox_annotation_load(path_root / 'annotation.json', file.name)
    print(0)

    # reshaped = fov_read(path_raw / file.name)
    # profile, projected = sharp_planes(reshaped, 1, 0)
    # projected_rgb = channels_combine(projected)
    # tf.imwrite('/Users/leoburgy/Desktop/test.png', projected[0, :, :])
    print(0)
