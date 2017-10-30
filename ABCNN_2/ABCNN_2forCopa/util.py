# coding: utf-8
import sys
import numpy as np
import numpy
import six
from collections import namedtuple

import chainer
from chainer import cuda, Function, Variable, optimizers, serializers, utils
from chainer import Link, Chain, variable
import chainer.functions as F
import chainer.links as L


# basically this is same as the one on chainer's repo.
# I added padding option (padding=0) to be always true
def concat_examples(batch, device=None, padding=0):
    if len(batch) == 0:
        raise ValueError('batch is empty')

    if device is None:
        def to_device(x):
            return x
    elif device < 0:
        to_device = cuda.to_cpu
    else:
        def to_device(x):
            return cuda.to_gpu(x, device, cuda.Stream.null)

    first_elem = batch[0]

    if isinstance(first_elem, tuple):
        result = []
        if not isinstance(padding, tuple):
            padding = [padding] * len(first_elem)

        for i in six.moves.range(len(first_elem)):
            result.append(to_device(_concat_arrays(
                [example[i] for example in batch], padding[i])))

        return tuple(result)
    elif isinstance(first_elem, dict):
        result = {}
        if not isinstance(padding, dict):
            padding = {key: padding for key in first_elem}

        for key in first_elem:
            result[key] = to_device(_concat_arrays(
                [example[key] for example in batch], padding[key]))

        return result


def _concat_arrays(arrays, padding):
    if padding is not None:
        return _concat_arrays_with_padding(arrays, padding)

    xp = cuda.get_array_module(arrays[0])
    with cuda.get_device(arrays[0]):
        return xp.concatenate([array[None] for array in arrays])


def _concat_arrays_with_padding(arrays, padding):
    shape = numpy.array(arrays[0].shape, dtype=int)
    for array in arrays[1:]:
        if numpy.any(shape != array.shape):
            numpy.maximum(shape, array.shape, shape)
    shape = tuple(numpy.insert(shape, 0, len(arrays)))

    xp = cuda.get_array_module(arrays[0])
    with cuda.get_device(arrays[0]):
        result = xp.full(shape, padding, dtype=arrays[0].dtype)
        for i in six.moves.range(len(arrays)):
            src = arrays[i]
            slices = tuple(slice(dim) for dim in src.shape)
            result[(i,) + slices] = src
    return result

def cos_sim(x, y):
    # batchsize = 1のときsqueezeでエラー
    if len(x.shape) > 2:
        norm_x = F.normalize(F.squeeze(F.squeeze(x,axis=(2,)),axis=(2,)))
        norm_y = F.normalize(F.squeeze(F.squeeze(y,axis=(2,)),axis=(2,)))
    else:
        norm_x = F.normalize(x)
        norm_y = F.normalize(y)
    return F.batch_matmul(norm_x, norm_y, transa=True)

def debug_print(v):
    """
    print out chainer variable
    """
    try:
        assert isinstance(v, variable.Variable)
    except:
        raise AssertionError
    else:
        print(v.data)
        print(v.shape)

class SelectiveWeightDecay(object):
    name = 'SelectiveWeightDecay'

    def __init__(self, rate, decay_params):
        self.rate = rate
        self.decay_params = decay_params

    def kernel(self):
        return cuda.elementwise(
            'T p, T decay', 'T g', 'g += decay * p', 'weight_decay')

    def __call__(self, opt):
        rate = self.rate
        for name, param in opt.target.namedparams():
            if name in self.decay_params:
                p, g = param.data, param.grad
                with cuda.get_device(p) as dev:
                    if int(dev) == -1:
                        g += rate * p
                    else:
                        self.kernel()(p, rate, g)

def compute_map_mrr(label_scores):
    """
    compute map and mrr
    argument is: numpy array with true label and predicted score
    """
    ap_list = []
    rr_list = []
    for label_score in label_scores:
        sort_order = label_score[:,1].argsort()[::-1]  #sort (label, score) array, following score from the model
        sorted_labels = label_score[sort_order][:,0]  # split
        sorted_scores = label_score[sort_order][:,1]  # split

        # compute map
        precision = 0
        correct_label = 0
        for n, (score, true) in enumerate(zip(sorted_scores, sorted_labels), start=1):
            if true == 1:
                correct_label += 1
                precision += (correct_label * 1.0 / n)
        ap = precision / correct_label
        ap_list.append(ap)

        # compute mrr
        ranks = [n for n, array in enumerate(label_score[sort_order], start=1) if int(array[0]) == 1]
        rr = (1.0 / ranks[0]) if ranks else 0.0
        rr_list.append(rr)

    Stats = namedtuple("Stats", ["map", "mrr"])
    return Stats(map=np.mean(ap_list), mrr=np.mean(rr_list))

def compute_copa_acc(label_scores):
    dev_correct_count, test_correct_count = 0, 0
    for i,label_score in enumerate(label_scores):
        max_score = 0
        max_score_label = None
        if label_score[0][1] > label_score[1][1]:
            sys_ans = label_score[0][0]
        else:
            sys_ans = label_score[1][0]
        if i < 500:
            if sys_ans == 1:
                dev_correct_count += 1
        else:
            if sys_ans == 1:
                test_correct_count += 1
    dev_acc = dev_correct_count / 500.0
    test_acc = test_correct_count / 500.0
    return dev_acc, test_acc




