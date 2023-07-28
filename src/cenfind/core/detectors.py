import contextlib
import functools
import logging
import os
from pathlib import Path
from typing import List

import cv2
import numpy as np
import tensorflow as tf
from csbdeep.utils import normalize
from matplotlib import pyplot as plt
from skimage import measure
from skimage.exposure import rescale_intensity
from skimage.feature import hessian_matrix, hessian_matrix_eigvals
from skimage.filters.thresholding import threshold_otsu
from spotipy.model import SpotNet
from spotipy.utils import normalize_fast2d
from stardist.models import StarDist2D

from cenfind.core.data import Field
from cenfind.core.log import get_logger
from cenfind.core.outline import Point, Contour, draw_foci, resize_image

np.random.seed(1)
tf.random.set_seed(2)
tf.get_logger().setLevel(logging.ERROR)

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

logger = get_logger(__name__)


@functools.lru_cache(maxsize=None)
def get_model(model):
    path = Path(model)
    if not path.is_dir():
        raise (FileNotFoundError(f"{path} is not a directory"))

    return SpotNet(None, name=path.name, basedir=str(path.parent))


def extract_foci(
        field: Field,
        foci_model_file: Path,
        channel: int,
        prob_threshold=0.5,
        min_distance=2,
) -> List[Point]:
    """
    Detect centrioles as row, col, row major
    :param field:
    :param foci_model_file:
    :param channel:
    :param prob_threshold:
    :param min_distance:
    :return:
    """
    logger.info("Processing %s / %d" % (field.name, channel))
    data = field.data[channel, ...]
    with open(os.devnull, "w") as f, contextlib.redirect_stdout(f):
        data = normalize_fast2d(data)
        model = get_model(foci_model_file)
        _, points_preds = model.predict(
            data, prob_thresh=prob_threshold, min_distance=min_distance, verbose=False
        )
    foci = [
        Point((r, c), channel, f_id, "Centriole") for f_id, (r, c) in enumerate(points_preds)
    ]

    centrosomes_mask = np.zeros(data.shape, dtype="uint8")
    centrosomes_mask = draw_foci(centrosomes_mask, foci, radius=min_distance * 2)

    centrosomes_map = measure.label(centrosomes_mask)
    centrosomes_centroids = measure.regionprops(centrosomes_map)

    for f in foci:
        foci_index = centrosomes_map[f.centre]
        centrosome_centroid = centrosomes_centroids[foci_index - 1].centroid
        centrosome_centroid = tuple(int(c) for c in centrosome_centroid)
        f.parent = Point(centrosome_centroid, channel, label="Centrosome")

    if len(foci) == 0:
        logger.warning("No centrioles (channel: %s) has been detected in %s" % (channel, field.name))

    logger.info("(%s), channel %s: foci: %s" % (field.name, channel, len(foci)))
    return foci


def extract_nuclei(
        field: Field, channel: int, model: StarDist2D = None
) -> List[Contour]:
    """
    Extract the nuclei from the nuclei image
    :param field:
    :param channel:
    :param model:
    :param annotation: a mask with pixels labelled for each centre

    :return: List of Contours.

    """
    if model is None:
        from stardist.models import StarDist2D
        with open(os.devnull, "w") as f, contextlib.redirect_stdout(f):
            model = StarDist2D.from_pretrained("2D_versatile_fluo")

    data = field.data[channel, ...]

    data_resized = resize_image(data)
    with open(os.devnull, "w") as f, contextlib.redirect_stdout(f):
        labels, _ = model.predict_instances(normalize(data_resized))
    labels = cv2.resize(
        labels, dsize=data.shape, fx=1, fy=1, interpolation=cv2.INTER_NEAREST
    )

    if len(labels) == 0:
        logger.warning("No nucleus has been detected in %s" % field.name)
        return []
    labels_id = np.unique(labels)

    nuclei = []
    for nucleus_index, nucleus_label in enumerate(labels_id):
        if nucleus_label == 0:
            continue
        sub_mask = np.zeros_like(labels, dtype="uint8")
        sub_mask[labels == nucleus_label] = 1
        contour, _ = cv2.findContours(
            sub_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        nucleus = Contour(contour[0], channel, "Nucleus", nucleus_index - 1)
        nuclei.append(nucleus)

    logger.info("(%s), channel %s: foci: %s" % (field.name, channel, len(nuclei)))

    return nuclei


def extract_cilia(field: Field, channel, dst) -> List[Point]:
    data = field.data[channel, ...]
    resc = rescale_intensity(data, out_range='uint8')

    def _detect_ridges(gray, sigma=1.0):
        h_elems = hessian_matrix(gray, sigma=sigma, order='rc')
        maxima_ridges, minima_ridges = hessian_matrix_eigvals(h_elems)
        return maxima_ridges, minima_ridges

    a, b = _detect_ridges(resc, sigma=5.0)
    threshold = threshold_otsu(b)
    contours = []

    mask = b < threshold
    labels = measure.label(mask)
    props = measure.regionprops(labels, mask)

    if len(props) == 0:
        logger.warning("No cilium (channel: %s) has been detected in %s" % (channel, field.name))

    fig, axs = plt.subplots(1, 2, figsize=(18, 9))

    ax_mask = axs[0]
    ax_annotated = axs[1]
    ax_mask.imshow(mask)
    ax_annotated.imshow(data, cmap='gray_r')

    for prop in props:
        if prop.eccentricity > .9 and prop.area > 200:
            r, c = prop.centroid
            contours.append(Point((c, r), -1, label='Cilium'))
            color = 'green'
            c = plt.Circle((c, r), 30, color=color, linewidth=2, fill=False)
            ax_annotated.add_patch(c)
    ax_annotated.set_axis_off()
    ax_mask.set_axis_off()

    plt.tight_layout()
    fig.savefig(dst / f'{field.name}.png')
    return contours
