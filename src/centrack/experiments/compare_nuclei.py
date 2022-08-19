import logging
import os

import pandas as pd
from stardist.models import StarDist2D
from tqdm import tqdm

import numpy as np
from spotipy.utils import points_matching

from centrack.data.base import Dataset, Projection, Channel
from centrack.experiments.constants import datasets, PREFIX_REMOTE

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(asctime)s: %(message)s")


def main():
    path_dataset = PREFIX_REMOTE / datasets[0]
    dataset = Dataset(path_dataset)
    model = StarDist2D.from_pretrained('2D_versatile_fluo')
    accuracies = []
    for field in tqdm(dataset.fields('_max.tif')):
        projection = Projection(dataset, field)
        nuclei = Channel(projection, 0)
        nuclei_mask = nuclei.mask(0)
        centres_preds, nuclei_preds = nuclei.extract_nuclei(model=model)
        centres_actual, nuclei_actual = nuclei.extract_nuclei(annotation=nuclei_mask)
        logging.info("Found %d nuclei instead of %d" % (len(centres_preds), len(centres_actual)))
        preds = [p.position for p in centres_preds]
        actual = [p.position for p in centres_actual]
        res = points_matching(preds, actual, cutoff_distance=50)
        accuracies.append({'field': field.name,
                           'f1': np.round(res.f1, 3)})
        acc_df = pd.DataFrame(accuracies)
        acc_df.to_csv('out/nuclei_acc.csv')


if __name__ == '__main__':
    main()
