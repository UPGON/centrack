import argparse
import logging
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import tensorflow
import tifffile as tf
from stardist.models import StarDist2D
from tqdm import tqdm

from cenfind.core.data import Dataset
from cenfind.core.measure import field_score
from cenfind.core.measure import field_score_frequency
from cenfind.core.outline import Centre
from cenfind.core.outline import create_vignette

## GLOBAL SEED ##
tensorflow.random.set_seed(3)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.addHandler(ch)


def get_args():
    parser = argparse.ArgumentParser(
        description='CENFIND: Automatic centriole scoring')

    parser.add_argument('path',
                        type=Path,
                        help='path to the ds')

    parser.add_argument('model',
                        type=Path,
                        help='absolute path to the model folder')

    parser.add_argument('channel_nuclei',
                        type=int,
                        help='channel id for nuclei segmentation, e.g., 0 or 3')

    parser.add_argument('channels',
                        nargs='+',
                        type=int,
                        help='channels to analyse, e.g., 1 2 3')

    parser.add_argument('factor',
                        type=int,
                        help='factor to use: given a 2048x2048 image, if 63x: 256; if 20x: 2048')
    parser.add_argument('--vicinity',
                        type=int,
                        default=-50,
                        help='distance threshold in pixel')

    parser.add_argument('--projection_suffix',
                        type=str,
                        default='_max',
                        help='the suffix indicating projection, e.g., `_max` or `_Projected`, if not specified, set to _max')
    args = parser.parse_args()

    if args.channel_nuclei in set(args.channels):
        raise ValueError('Nuclei channel cannot present in channels')

    if not args.model.exists():
        raise FileNotFoundError(f"{args.model} does not exist")

    return args


def save_foci(foci_list: list[Centre], dst: str) -> None:
    if len(foci_list) == 0:
        array = np.array([])
        logger.info('No centriole detected')
    else:
        array = np.asarray(np.stack([c.to_numpy() for c in foci_list]))
    np.savetxt(dst, array[:, [1, 0]], delimiter=',', fmt='%u')


def main():
    args = get_args()
    visualisation = True

    dataset = Dataset(args.path, projection_suffix=args.projection_suffix)
    model_stardist = StarDist2D.from_pretrained('2D_versatile_fluo')

    scores = []
    pbar = tqdm(dataset.pairs())
    for field, _ in pbar:
        pbar.set_description(f"{field.name}")
        for ch in args.channels:
            foci, nuclei, assigned, score = field_score(field=field,
                                                        model_nuclei=model_stardist,
                                                        model_foci=args.model,
                                                        nuclei_channel=args.channel_nuclei,
                                                        factor=args.factor,
                                                        vicinity=-15,
                                                        channel=ch)
            predictions_path = dataset.predictions / 'centrioles' / f"{field.name}{args.projection_suffix}_C{ch}.txt"
            save_foci(foci, predictions_path)

            pbar.set_postfix({'nuclei': len(nuclei), 'foci': len(foci)})
            scores.append(score)

            if visualisation:
                background = create_vignette(field, marker_index=ch, nuclei_index=args.channel_nuclei)
                for focus in foci:
                    background = focus.draw(background, annotation=False)
                for nucleus in nuclei:
                    background = nucleus.draw(background, annotation=False)
                for n_pos, c_pos in assigned:
                    for sub_c in c_pos:
                        if sub_c:
                            cv2.arrowedLine(background, sub_c.to_cv2(), n_pos.centre.to_cv2(), color=(0, 255, 0),
                                            thickness=1)
                tf.imwrite(args.path / 'visualisations' / f"{field.name}_C{ch}_pred.png", background)

    flattened = [leaf for tree in scores for leaf in tree]

    scores_df = pd.DataFrame(flattened)
    scores_df.to_csv(dataset.statistics / f'scores_df.tsv', sep='\t', index=False)

    binned = field_score_frequency(scores_df)
    binned.to_csv(dataset.statistics / f'statistics.tsv', sep='\t', index=True)


if __name__ == '__main__':
    main()
