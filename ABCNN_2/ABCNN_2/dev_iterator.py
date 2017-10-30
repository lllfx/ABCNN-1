# -*- coding: utf-8 -*-
import sys
import numpy as np
import chainer
from chainer import cuda, Function, gradient_check, Variable, optimizers, serializers, utils
from chainer import Link, Chain
import chainer.functions as F
import chainer.links as L
from chainer.iterators import SerialIterator

class DevIterator(SerialIterator):
    """
    This iterator is for validation.
    In order to compute MAP and MRR, this iterator
    yields minibatch which contains one question, all answer candidates
    """
    def __init__(self, dataset, n_pair):
        self.dataset = dataset
        self._order = None
        self.current_position = 0
        self.epoch = 0
        self.is_new_epoch = False
        self.n_pair = n_pair # number of answers contained in each question
        self.n = 0

    def next(self):
        if self.epoch > 0:
            raise StopIteration

        i = self.current_position
        i_end = i + self.n_pair[self.n]
        self.n += 1
        N = len(self.dataset)

        batch = self.dataset[i:i_end]

        if i_end >= N:
            self.current_position = N
            self.epoch += 1
            self.is_new_epoch = True
        else:
            self.is_new_epoch = False
            self.current_position = i_end

        return batch
