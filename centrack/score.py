import argparse
import contextlib
import functools
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
from csbdeep.utils import normalize
from cv2 import cv2
from stardist.models import StarDist2D

from describe import condition_from_filename
from fetch import Channel, Field, DataSet
from outline import (
    Centre,
    Contour,
    prepare_background,
    draw_annotation
    )
from spotipy.spotipy.model import SpotNet
from spotipy.spotipy.utils import normalize_fast2d

logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)


@functools.lru_cache(maxsize=None)
def get_model(model):
    path = Path(model)
    if not path.is_dir():
        raise (FileNotFoundError(f"{path} is not a directory"))

    return SpotNet(None, name=path.name, basedir=str(path.parent))


def mat2gray(image):
    """Normalize to the unit interval and return a float image"""
    return cv2.normalize(image, None, alpha=0., beta=1.,
                         norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_32F)


class Detector(ABC):
    def __init__(self, plane, organelle):
        self.plane = plane
        self.organelle = organelle

    @abstractmethod
    def _mask(self):
        pass

    @abstractmethod
    def detect(self):
        pass


class FocusDetector(Detector):
    """Combine a preprocessing and a detection step and return a list of centres."""

    def _mask(self):
        transformed = self.plane
        return transformed

    def detect(self, interpeak_min=3):
        model = get_model(
            model='/Users/leoburgy/Dropbox/epfl/projects/centrack/models/leo3_multiscale_True_mae_aug_1_sigma_1.5_split_2_batch_2_n_300')
        image = self.plane
        x = normalize_fast2d(image)
        # n_tiles = (2, 2)
        prob_thresh = .5

        foci = model.predict(x,
                             # n_tiles=n_tiles,
                             prob_thresh=prob_thresh,
                             show_tile_progress=False)

        return [Centre((y, x), f_id, self.organelle, confidence=-1) for
                f_id, (x, y) in enumerate(foci[1])]


class NucleiDetector(Detector):
    """
    Threshold a DAPI image and run contour detection.
    """

    def _mask(self):
        image = self.plane
        image32f = image.astype(float)
        mu = cv2.GaussianBlur(image32f, (101, 101), 0)
        mu2 = cv2.GaussianBlur(mu * mu, (31, 31), 0)
        sigma = cv2.sqrt(mu2 - mu * mu)
        cv2.imwrite('./out/sigma.png', sigma)

        th, mask = cv2.threshold(sigma, 200, 255, 0)
        cv2.imwrite('./out/mask.png', mask)

        return mask

    def detect(self):
        transformed = self._mask()
        contours, hierarchy = cv2.findContours(transformed,
                                               cv2.RETR_EXTERNAL,
                                               cv2.CHAIN_APPROX_SIMPLE)

        return [Contour(c, self.organelle, c_id, confidence=-1) for c_id, c in
                enumerate(contours)]


class NucleiStardistDetector(Detector):
    """
    Resize a DAPI image and run StarDist
    """

    def _mask(self):
        return cv2.resize(self.plane, dsize=(256, 256),
                          fx=1, fy=1,
                          interpolation=cv2.INTER_NEAREST)

    def detect(self):
        model = StarDist2D.from_pretrained('2D_versatile_fluo')
        transformed = self._mask()

        transformed = transformed
        labels, coords = model.predict_instances(normalize(transformed))

        nuclei_detected = cv2.resize(labels, dsize=(2048, 2048),
                                     fx=1, fy=1,
                                     interpolation=cv2.INTER_NEAREST)

        labels_id = np.unique(nuclei_detected)
        cnts = []
        for nucleus_id in labels_id:
            if nucleus_id == 0:
                continue
            submask = np.zeros_like(nuclei_detected, dtype='uint8')
            submask[nuclei_detected == nucleus_id] = 255
            contour, hierarchy = cv2.findContours(submask,
                                                  cv2.RETR_EXTERNAL,
                                                  cv2.CHAIN_APPROX_SIMPLE)
            cnts.append(contour[0])
        contours = tuple(cnts)
        return [Contour(c, self.organelle, c_id, confidence=-1) for c_id, c in
                enumerate(contours)]


def extract_centrioles(data):
    """
    Extract the centrioles from the channel image.
    :param data:
    :return: List of Points
    """
    focus_detector = FocusDetector(data, 'Centriole')
    return focus_detector.detect()


def extract_nuclei(data):
    """
    Extract the nuclei from the nuclei image.
    :param data:
    :return: List of Contours.
    """
    nuclei_detector = NucleiStardistDetector(data, 'Nucleus')
    return nuclei_detector.detect()


def assign(foci_list, nuclei_list):
    """
    Assign detected centrioles to the nearest nucleus.
    1.
    :return: List[Tuple[Centre, Contour]]
    """
    if len(foci_list) == 0:
        raise ValueError('Empty foci list')
    if len(nuclei_list) == 0:
        raise ValueError('Empty nuclei list')

    assigned = []
    for c in foci_list:
        distances = [
            (n, cv2.pointPolygonTest(n.contour, c.centre, measureDist=True)) for
            n in nuclei_list]
        nucleus_nearest = max(distances, key=lambda x: x[1])
        assigned.append((c, nucleus_nearest[0]))

    return assigned


def parse_args():
    parser = argparse.ArgumentParser(
        description='CCOUNT: Automatic centriole scoring')

    parser.add_argument('dataset', type=Path, help='path to the dataset')
    parser.add_argument('marker', type=str,
                        help='marker to use for foci detection')
    parser.add_argument('-t', '--test', type=int,
                        help='test; only run on the ith image')
    parser.add_argument('-o', '--out', type=Path, help='path for output')

    return parser.parse_args()


def cli():
    logging.info('Starting Centrack...')

    filename_patterns = {
        'hatzopoulos': r'([\w\d]+)_(?:([\w\d-]+)_)?([\w\d\+]+)_(\d)',
        'garcia': r'^(?:\d{8})_([\w\d-]+)_([\w\d_-]+)_([\w\d\+]+)_((?:R\d_)?\d+)?_MMStack_Default'
        }

    args = parse_args()

    dataset_path = args.dataset
    logging.debug('Working at %s', dataset_path)

    dataset = DataSet(dataset_path)

    if not args.out:
        projections_path = dataset.projections
    else:
        projections_path = args.out
    projections_path.mkdir(exist_ok=True)

    fields = tuple(f for f in dataset.projections.glob('*.tif') if
                   not f.name.startswith('.'))
    logging.debug('%s files were found', len(fields))

    if args.test:
        logging.warning('Test mode enabled: only one field will be processed.')
        fields = [fields[0]]

    for path in fields:
        logging.info('Loading %s', path.name)
        condition = condition_from_filename(path.name,
                                            filename_patterns['hatzopoulos'])
        field = Field(path, condition, dataset)
        data = field.load()

        marker = args.marker
        if marker not in condition.markers:
            raise ValueError(
                f'Marker {marker} not in dataset ({condition.markers}).')

        logging.info('Detecting the objects...')
        foci = Channel(data)[marker].to_numpy()
        nuclei = Channel(data)['DAPI'].to_numpy()

        # This skips the print calls in spotipy
        with open(os.devnull, 'w') as f, contextlib.redirect_stdout(f):
            foci_detected = extract_centrioles(foci)
            nuclei_detected = extract_nuclei(nuclei)
        logging.info('%s: (%s foci, %s nuclei)', path.name, len(foci_detected),
                     len(nuclei_detected))

        logging.debug('Assigning foci to nuclei.')
        try:
            assigned = assign(foci_list=foci_detected,
                              nuclei_list=nuclei_detected)
        except ValueError:
            logging.warning('No foci/nuclei detected (%s)', path.name)
            continue

        if args.out:
            logging.debug('Creating annotation image.')
            background = prepare_background(nuclei, foci)
            annotation = draw_annotation(background, assigned, foci_detected,
                                         nuclei_detected)
            args.out.mkdir(exist_ok=True)
            destination_path = projections_path / f'{path.name.removesuffix(".ome.tif")}_annot.png'
            successful = cv2.imwrite(str(destination_path), annotation)

            if successful:
                logging.debug('Saved at %s', destination_path)

            # with open(args.out / 'dump.json', 'w') as fh:
            #     json.dump(foci_detected, fh)


if __name__ == '__main__':
    cli()
