# coding: utf-8
import os
import sys
import numpy as np
import copy
from chainer import reporter
import chainer.functions as F
from chainer.functions import sigmoid_cross_entropy, binary_accuracy
from chainer.training import extensions
from sklearn.svm import LinearSVC
from sklearn.svm import SVC
from collections import namedtuple
import random
import chainer
from chainer import cuda
from .util import compute_map_mrr
tc = cuda.to_cpu
# sys.setrecursionlimit(6000)

class WikiQAEvaluator(extensions.Evaluator):

    def __init__(self, iterator, target, device, converter):
        super(WikiQAEvaluator, self).__init__(
            iterator=iterator, target=target, device=device, converter=converter)

    def collect_prediction_for_train_data(self):
        """
        collect prediction scores from the model.
        this is needed for training SVM/LR
        """
        iterator = self._iterators['train']
        target = self._targets['main']
        it = copy.copy(iterator)

        train_X = []
        train_y = []
        for batch in it:
            x1s, x2s, wordcnt, wgt_wordcnt, x1s_len, x2s_len, y = self.converter(batch,device=-1)
            y_score, sim_scores = target(x1s, x2s, wordcnt, wgt_wordcnt, x1s_len, x2s_len)
            # exit()
            x = np.concatenate([tc(x.data) for x in sim_scores] + [wordcnt, wgt_wordcnt, x1s_len, x2s_len], axis=1)
            
            train_X.append(x)
            train_y.append(y)
            
        train_X = np.concatenate(train_X, axis=0)
        train_y = np.concatenate(train_y, axis=0)
        return train_X, train_y


    def evaluate(self):
        train_X, train_y = self.collect_prediction_for_train_data()
        model = LinearSVC()
        # model = LinearSVC(loss="hinge",tol=0.001,max_iter=6000)
        # model = SVC(C=1.0, kernel="linear")
        model.fit(X=train_X, y=train_y)

        iterator = self._iterators['dev']
        target = self._targets['main']
        # this is necessary for more-than-once-evaluation
        it = copy.copy(iterator)

        label_scores = []
        svm_label_scores = []
        summary = reporter.DictSummary()
        for n, batch in enumerate(it):
            observation = {}
            with reporter.report_scope(observation):
                x1s, x2s, wordcnt, wgt_wordcnt, x1s_len, x2s_len, y = self.converter(batch, device=-1)
                y_score, sim_scores = target(x1s, x2s, wordcnt, wgt_wordcnt, x1s_len, x2s_len)
                # batch分のy_score(feature vec を1次元に写像したもの)とsim_scoreが帰ってくる

                # 正解ラベルyを使ってloss計算
                loss = F.sigmoid_cross_entropy(x=y_score, t=y).data
                reporter.report({'loss': loss}, target)

                # We evaluate WikiQA by MAP and MRR
                # for direct evaluation
                label_score = np.c_[tc(y), tc(y_score.data)]
                label_scores.append(label_score)

                # for SVM/LR
                x = np.concatenate([tc(x.data) for x in sim_scores] + [wordcnt, wgt_wordcnt, x1s_len, x2s_len], axis=1)
                y_score = model.decision_function(x)
                svm_label_score = np.c_[y, y_score]
                svm_label_scores.append(svm_label_score)
            summary.add(observation)

        stats = compute_map_mrr(label_scores)
        svm_stats = compute_map_mrr(svm_label_scores)
        summary_dict = summary.compute_mean()
        summary_dict["validation/svm_map"] = svm_stats.map
        summary_dict["validation/svm_mrr"] = svm_stats.mrr
        summary_dict["validation/map"] = stats.map
        summary_dict["validation/mrr"] = stats.mrr
        return summary_dict
