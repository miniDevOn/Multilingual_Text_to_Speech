import torch
from torch.nn import functional as F
from torch.nn import Sequential, ModuleList, ReLU, LSTM

from modules.layers import ConvBlock
from modules.generated import LSTMGenerated
from params.params import Params as hp


class Encoder(torch.nn.Module):
    """
    Encoder:
        stack of 3 conv. layers 5 × 1 with BN and ReLU, dropout
        output is passed into a Bi-LSTM layer

    Arguments:
        input_dim -- size of the input (supposed character embedding)
        output_dim -- number of channels of the convolutional blocks and last Bi-LSTM
        num_blocks -- number of the convolutional blocks (at least one)
        kernel_size -- kernel size of the encoder's convolutional blocks
        dropout -- dropout rate to be aplied after each convolutional block
        generated -- enables meta-learning approach which generates parameters of the internal layers
    """
    
    def __init__(self, input_dim, output_dim, num_blocks, kernel_size, dropout, generated=False):
        super(Encoder, self).__init__()
        assert num_blocks > 0, ('There must be at least one convolutional block in the encoder.')
        assert output_dim % 2 == 0, ('Bidirectional LSTM output dimension must be divisible by 2.')
        self._convs = Sequential(
            ConvBlock(input_dim, output_dim, kernel_size, dropout, 'relu', generated),
            *[ConvBlock(output_dim, output_dim, kernel_size, dropout, 'relu', generated)] * (num_blocks - 1)
        )
        if generated:
            self._lstm = LSTMGenerated(output_dim, output_dim // 2, batch_first=True, bidirectional=True)
        else:
            self._lstm = LSTM(output_dim, output_dim // 2, batch_first=True, bidirectional=True)

    def forward(self, x, x_lenghts, x_langs=None):  
        # x_langs argument is there just for convenience
        x = x.transpose(1, 2)
        x = self._convs(x)
        x = x.transpose(1, 2)
        ml = x.size(1)
        x = torch.nn.utils.rnn.pack_padded_sequence(x, x_lenghts, batch_first=True)
        self._lstm.flatten_parameters()
        x, _ = self._lstm(x)
        x, _ = torch.nn.utils.rnn.pad_packed_sequence(x, batch_first=True, total_length=ml) 
        return x


class ConditionalEncoder(torch.nn.Module):
    # TODO:
    pass


class MultiEncoder(torch.nn.Module):
    """
    Bunch of language-dependent encoders with output masking.

    Arguments:
        num_langs -- number of languages (and encoders to be instiantiated)
        encoder_args -- tuple or list of arguments for encoder
    """

    def __init__(self, num_langs, encoder_args):
        super(MultiEncoder, self).__init__()
        self._num_langs = num_langs
        self._encoders = ModuleList([Encoder(*encoder_args)] * num_langs)

    def forward(self, x, x_lenghts, x_langs):
        xs = None
        for l in range(self._num_langs):
            mask = (x_langs == l)
            if not mask.any(): continue
            ex = self._encoders[l](x, x_lenghts)
            if xs is None:
                xs = torch.zeros_like(ex)
            xs[mask] = ex[mask]
        return xs
