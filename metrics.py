import numpy as np
import pandas as pd
import sklearn.metrics
from drain import util,model
from drain.util import to_float

def count_notnull(series):
    return (~np.isnan(to_float(series))).sum()

def baseline(run, **subset_args):
    y_true,y_score = model.true_score(run.y, **subset_args)

    if len(y_true) > 0:
        return np.nansum(y_true)/count_notnull(y_true)
    else:
        return 0.0

# return size of dataset
# if dropna=True, only count rows where outcome is not nan
def count(run, **subset_args):
    y_true,y_score = model.true_score(run.y, **subset_args)
    return len(y_true)

def auc(run, **subset_args):
    y_true, y_score = model.true_score(run.y, **subset_args)
    fpr, tpr, thresholds = sklearn.metrics.roc_curve(y_true, y_score)
    return sklearn.metrics.auc(fpr, tpr)

def precision(run, dropna=True, **subset_args):
    y_true, y_score = model.true_score(run.y, **subset_args)

    return precision_at_k(y_true, y_score, len(y_true), extrapolate=~dropna)

def top_k(y_true, y_score, k, extrapolate=False):
    if len(y_true) != len(y_score):
        raise ValueError('Labels and scores must have same lengths: %s != %s' 
                 % (len(y_true), len(y_score)))
    if k == 0:
        return (0,0)

    y_true, y_score = to_float(y_true, y_score)

    labeled = ~np.isnan(y_true)
    n = len(y_true) if extrapolate else labeled.sum()
    if not extrapolate and k > n:
        raise ValueError('Cannot calculate precision at %d > %d'% (k,n))

    if extrapolate:
        ranks = y_score.argsort()
        top = ranks[-k:]
        labeled_top = ~np.isnan(y_true[top])

        return y_true[top][labeled_top].sum(), labeled_top.sum()

    else:
        y_true = y_true[labeled]
        y_score = y_score[labeled]
        ranks = y_score.argsort()
        top = ranks[-k:]

        return y_true[top].sum(), k

# when extrapolate is True, return a triple
# first element is lower bound (assuming unlabeled examples are all False)
# second is precision of labeled examples only
# third is upper bound (assuming unlabeled examples are all True) 
def precision_at_k(y_true, y_score, k, extrapolate=False, return_bounds=True):
    n,d = top_k(y_true, y_score, k, extrapolate)
    p = n*1./d if d != 0 else np.nan

    if extrapolate:
        bounds = (n/k, (n+k-d)/k) if k != 0 else (np.nan, np.nan)
        if return_bounds:
            return p, d, bounds
        else:
            return p
    else:
        return p

# TODO extrapolate here
def precision_series(y_true, y_score, k=None):
    y_true, y_score = to_float(y_true, y_score)
    ranks = y_score.argsort()

    if k is None:
        k = len(y_true)

    top_k = ranks[::-1][0:k]

    n = np.nan_to_num(y_true[top_k]).cumsum() # fill missing labels with 0
    d = (~np.isnan(y_true[top_k])).cumsum()     # count number of labelsa
    return pd.Series(n/d, index=np.arange(1,k+1))

# TODO: should recall be proportion or absolute?
# value is True or False, the label to recall
def recall_series(y_true, y_score, k=None, value=True):
    y_true, y_score = to_float(y_true, y_score)
    ranks = y_score.argsort()
    
    if k is None:
        k = len(y_true)
    top_k = ranks[::-1][0:k]

    if not value:
        y_true = 1-y_true

    return pd.Series(np.nan_to_num(y_true[top_k]).cumsum(), index=np.arange(1,k+1))
