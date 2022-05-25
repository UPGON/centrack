import logging
import re
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np
import pytomlpp
import tifffile as tf
import xarray as xr

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(level=logging.DEBUG)

PATTERNS = {
    'hatzopoulos': re.compile(r'([\w\d]+)_(?:([\w\d-]+)_)?([A-Z0-9+]+)_(\d)'),
    'garcia': re.compile(
        r'^(?:\d{8})_([\w\d-]+)_([\w\d_-]+)_([\w\d+]+)_((?:R\d_)?\d+)?_MMStack_Default'),
}


@dataclass
class Marker:
    """Represents a marker."""
    protein: str = None
    channel: str = None
    position: int = None
    wave_length: int = None
    code: str = None

    @property
    def _code(self):
        if self.code is not None:
            return self.code
        else:
            return f'{self.channel}{self.protein}{self.wave_length}'

    @classmethod
    def from_code(cls, code, pattern=r'([rgbm])([\w\d]+)', position=None):
        if code is None:
            raise ValueError('Provide a code')
        if code == 'DAPI':
            return cls(protein='DNA',
                       channel='b',
                       position=0
                       )
        else:
            remainder, wave_length = code[:-3], code[-3:]
            res = re.match(pattern, remainder)
            if res is None:
                raise ValueError(f'Regex unsuccessful: {res=}')
            channel, protein = res.groups()
            return cls(protein=protein,
                       channel=channel,
                       position=position,
                       wave_length=wave_length)


@dataclass
class PixelSize:
    value: float
    units: str

    def in_cm(self):
        conversion_map = {
            'um': 10e4,
            'μm': 10e4,
            'nm': 10e7,
        }
        return self.value / conversion_map[self.units]


@dataclass
class Condition:
    genotype: str = 'wt'
    treatment: str = ''
    replicate: str = 1
    markers: list = ''
    pixel_size: PixelSize = 1

    @classmethod
    def from_filename(cls, file_name, pattern):
        """
        Extract parameters of dataset.
        :param file_name:
        :param pattern: must contain 4 groups, namely: genotype, treatment, markers, replicate
        :return: Condition object
        """

        pat = re.compile(pattern)
        matched = re.match(pat, file_name)
        if matched is None:
            raise re.error(f'{pattern} not found in {file_name}')
        else:
            genotype, treatment, markers, replicate = matched.groups()
        markers_list = get_markers(markers)
        return cls(genotype=genotype,
                   treatment=treatment,
                   markers=markers_list,
                   replicate=replicate,
                   pixel_size=PixelSize(.1025, 'um'))

    def to_toml(self, file: Path):
        with open(file, 'w') as f:
            logger.debug('Dump the toml.')
            pytomlpp.dump(asdict(self), f)


@dataclass
class DataSet:
    path: Path

    @property
    def conditions(self):
        return self.path / 'conditions.toml'

    @property
    def raw(self):
        """Define the path to raw folder."""
        return self.path / 'raw'

    @property
    def projections(self):
        """Define the path to projections folder."""
        return self.path / 'projections'

    @property
    def predictions(self):
        return self.path / 'predictions.csv'

    @property
    def annotations(self):
        return self.path / 'annotation.csv'

    @property
    def outlines(self):
        return self.path / 'outlines'

    def check_conditions(self,
                         conditions: Condition = None,
                         ):
        if self.conditions.exists():
            logger.info('%s exists', self.conditions)
            return
        if conditions:
            conditions.to_toml(self.conditions)
            return
        else:
            Condition().to_toml(self.conditions)
            logger.warning('Template conditions was generated; please fill it.')

    def _check_container(self, container_name: str, file_type: str):
        """
        Check if the folder `container_name` exists and whether it
        contains `file_type` files (recursively)
        :param name:
        :param file_type:
        :return: None
        """
        container_name = self.path / container_name

        if container_name.exists():
            files = [f for f in container_name.iterdir()]
            if len(files) == 0:
                return []
            else:
                recursive_files = fetch_files(container_name,
                                              file_type=file_type)
                return recursive_files
        else:
            container_name.mkdir()

    def check_raw(self):
        self._check_container('raw', '.ome.tif')

    def check_projections(self):
        self._check_container('projections', '_max.tif')

    def check_outlines(self):
        self._check_container('outlines', '.png')

    def check_predictions(self, force=False):
        """
        Check for a set of predictions.
        else if we want to compare the predictions with annotations,
        Compute the predictions.
        Upload the predictions to labelbox.
        Provide the url of the annotated dataset on Labelbox
        """
        for image in self.projections.iterdir():
            print(image)

    def check_annotations(self):
        """
        If there is no annotation present, we should fetch them from labelbox.
        If the dataset is not on labelbox, we should upload it with the predictions
        :return:
        """
        raise NotImplementedError


def load_projection(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(path)

    with tf.TiffFile(path) as file:
        data = file.asarray()
        result = np.squeeze(data)

    if len(result.shape) != 3:
        raise ValueError(f"File {path} has shape {data.shape}")

    return result


@dataclass
class Channel:
    data: xr.DataArray

    def __getitem__(self, item):
        return self.data.loc[item, :, :]


def is_tif(filename):
    _filename = str(filename)
    return _filename.endswith('.tif') and not _filename.startswith('.')


def build_name(path: Path, channel: int, projection_type='max') -> str:
    """
    Extract the file name, remove the suffixes and append the projection type.
    :param path:
    :param channel:
    :param projection_type: the type of projection, by default max
    :return: file name of the projection
    """
    file_name = path.name
    suffixes = ''.join(path.suffixes)
    file_name_no_suffix = file_name.removesuffix(suffixes)
    return file_name_no_suffix + f'_{projection_type}_C{channel}.tif'


def get_markers(markers: str, sep='+') -> List:
    """
    Convert a '+'-delimited string into a list and prepend the DAPI
    :param markers:
    :param sep: delimiter character
    :return: List of markers
    """
    markers_list = markers.split(sep)
    if 'DAPI' not in markers_list:
        markers_list.insert(0, 'DAPI')
    return markers_list


# TODO: Replace hard coded name mangling with extract_filename()
def extract_filename(file):
    file_name = file.name
    file_name = file_name.removesuffix(''.join(file.suffixes))
    file_name = file_name.replace('', '')
    file_name = re.sub(r'_(Default|MMStack)_\d-Pos', '', file_name)

    return file_name.replace('', '')


def fetch_files(path_source: Path, file_type):
    """
    Collect all ome.tif files in a list.
    :param file_type:
    :param path_source:
    :return: A list of Path to ome.tif files
    """
    if not path_source.exists():
        raise FileExistsError(path_source)
    pattern = f'*{file_type}'
    files_generator = path_source.rglob(pattern)

    return [file for file in files_generator if not file.name.startswith('.')]