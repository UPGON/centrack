import numpy as np
from spotipy.spotipy.model import Config, SpotNetData, SpotNet
from spotipy.spotipy.utils import points_to_prob

if __name__ == '__main__':
    config = Config(axes="YXC", n_channel_in=1, train_patch_size=(64, 64),
                    activation='elu', last_activation="sigmoid", backbone='unet')

    P = np.random.randint(10, 128 - 10, (5, 30, 2))
    Y = np.stack(tuple(points_to_prob(p, shape=(128, 128), sigma=1) for p in P))
    X = Y + .3 * np.random.normal(0, 1, Y.shape)

    model = SpotNet(config, name=None, basedir='/Users/buergy/Dropbox/epfl/projects/centrack/models/test_model')
    model.train(X, Y, validation_data=[X, Y], steps_per_epoch=10)
