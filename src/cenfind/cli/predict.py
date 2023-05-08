import contextlib
import os
from pathlib import Path
import argparse

import tifffile as tf

from cenfind.core.data import Dataset
from cenfind.core.outline import visualisation, Centriole
from cenfind.core.log import get_logger


def register_parser(parent_subparsers):
    parser = parent_subparsers.add_parser(
        "predict",
        help="Predict centrioles on new dataset and save under visualisations/runs/<model_name>",
    )
    parser.add_argument("dataset", type=Path, help="Path to the dataset folder")
    parser.add_argument("model", type=Path, help="Path to the model")
    parser.add_argument(
        "--channel_nuclei", type=int, required=True, help="Index of nuclei channel"
    )

    return parser


def run(args):
    dataset = Dataset(args.dataset)
    dataset.setup()
    logger = get_logger(__name__, file=dataset.logs / 'cenfind.log')

    model_predictions = dataset.visualisation / "runs"
    model_predictions.mkdir(exist_ok=True)

    model_run = model_predictions / args.model.name
    model_run.mkdir(exist_ok=True)

    from stardist.models import StarDist2D

    with open(os.devnull, "w") as f, contextlib.redirect_stdout(f):
        model_stardist = StarDist2D.from_pretrained("2D_versatile_fluo")

    from cenfind.core.detectors import extract_foci, extract_nuclei

    for field, channel in dataset.pairs("test"):
        nuclei = extract_nuclei(field=field, channel=args.channel_nuclei, factor=256, model=model_stardist)
        foci = extract_foci(field, args.model, channel, prob_threshold=0.5)
        logger.info(
            "Writing visualisations for field: %s, channel: %s, %s foci detected"
            % (field.name, channel, len(foci))
        )
        vis = visualisation(field, foci, channel, nuclei, channel_nuclei=args.channel_nuclei)
        tf.imwrite(model_run / f"{field.name}_C{channel}_pred.png", vis)


if __name__ == "__main__":
    args = argparse.Namespace(dataset=Path('data/dataset_test'),
                              model=Path('models/master'),
                              channel_nuclei=0,
                              factor=256)
    run(args)
