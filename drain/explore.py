from tempfile import NamedTemporaryFile
from pprint import pformat
from itertools import product, chain

from sklearn.externals import joblib
from sklearn import tree
import pandas as pd
import numpy as np
from collections import Counter

import matplotlib.colors
from matplotlib import cm

from drain import model, util, metrics, step

def expand(self, prefix=False, index=True, diff=True, existence=True):
    """
    This function is a member of StepFrame and StepSeries. It is used to 
    expand the kwargs of the steps either into the index (index=True) or 
    as columns (index=False). By default (diff=True) only the kwargs which 
    differ among steps are expanded.

    Note that index objects in pandas must be hashable so any unhashable 
    argument values are converted to string representations (using pprint) 
    when index=True.

    If "inputs" is an argument those steps' kwargs are also expanded (and 
    their inputs recursively). If there are multiple steps with the same 
    argument names they are prefixed by their names or if those are not set 
    then by their class names. To enable prefixing for all args set
    prefix=True.

    Sometimes the difference between pipelines is that a step exists or it
    doesn't. When diff=True and existence=True, instead of expanding all 
    the kwargs for that step, we expand a single column whose name is the
    step name and whose value is a boolean indicating whether the step exists
    in the given tree.

    Args: 
        prefix: whether to always use step name prefix for kwarg name.
            Default False, which uses prefixes when necessary, i.e. for 
            keywords that are shared by multiple step names.
        index: If True expand args into index. Otherwise expand into
            columns
        diff: whether to only expand keywords whose values that are 
            non-constant
        existence: whether to check for existence of a step in the tree
            instead of a full diff. Only applicable when diff=True. See
            note above.

    Returns: a DatFrame with the arguments of the steps expanded.
    """
    # collect kwargs resulting in a list of {name: kwargs} dicts
    dicts = [step._collect_kwargs(s) for s in self.index]
    # if any of the kwargs are themselves dicts, expand them
    dicts = [{k: util.dict_expand(v) for k,v in s.items()} for s in dicts]

    if diff:
        diff_dicts = [{} for d in dicts] # the desired list of dicts

        names = util.union([set(d.keys()) for d in dicts]) # all names among these steps
        for name in names:
            if existence:
                ndicts = [d[name] for d in dicts if name in d.keys()] # all dicts for this name
            else:
                ndicts = [d[name] if name in d.keys() else {} for d in dicts]

            ndiffs = util.dict_diff(ndicts) # diffs for this name
          
            if sum(map(len, ndiffs)) == 0: # if they're all the same 
                # but not all had the key and existence=True
                if existence and len(ndicts) < len(self): 
                    for m, d in zip(diff_dicts, dicts):
                        m[name] = {tuple(): name in d.keys()}
            else: # if there was a diff
                diff_iter = iter(ndiffs)
                for m, d in zip(diff_dicts, dicts):
                    if name in d.keys() or not existence:
                        m[name] = diff_iter.next() # get the corresponding diff

        dicts = diff_dicts

    # restructure so name is in the key
    merged_dicts = []
    for dd in dicts:
        merged_dicts.append(util.dict_merge(*({tuple([name] + list(util.make_tuple(k))) : v 
                            for k,v in d.items()} for name, d in dd.items())))

    # prefix_keys are the keys that will keep their prefix
    keys = list(chain(*(d.keys() for d in merged_dicts)))
    if not prefix:
        key_count = Counter((k[1:] for k  in keys))
        prefix_keys = {a for a in key_count if key_count[a] > 1}
    else:
        prefix_keys = set(keys)

    # prefix non-unique arguments with step name
    # otherwise use argument alone
    merged_dicts = [{str.join('_', map(str, k if k[1:] in prefix_keys else k[1:])):v 
              for k,v in d.items()} for d in merged_dicts]

    df2 = pd.DataFrame(merged_dicts, index=self.index)
    columns = list(df2.columns) # remember columns for index below

    expanded = pd.concat((df2, self), axis=1)

    if index:
        try:
            expanded.set_index(columns, inplace=True)
        except TypeError:
            _print_unhashable(expanded, columns)
            expanded.set_index(columns, inplace=True)

    return expanded

def dapply(self, fn, **kwargs):
    """
    Apply function to each step object in the index

    Args:
        fn: function to apply. If a list then each function is applied
        kwargs: a keyword arguments to pass to each function. Arguments
            with list value are grid searched using util.dict_product.
    
    Returns: a StepFrame or StepSeries 
    """
    search_keys = [k for k,v in kwargs.items() if isinstance(v, list) and len(v) > 1]
    functions = util.make_list(fn)
    search = list(product(functions, util.dict_product(kwargs)))
    
    results = []
    for fn,kw in search:
        r = self.index.to_series().apply(lambda step: fn(step, **kw))
        
        name = [] if len(functions) == 1 else [fn.__name__]
        name += util.dict_subset(kw, search_keys).values()
            
        if isinstance(r, pd.DataFrame):
            columns = pd.MultiIndex.from_tuples([tuple(name + util.make_list(c)) for c in r.columns])
            r.columns = columns
        else:
            r.name = tuple(name)
        results.append(r)

    if len(results) > 1:
        result = pd.concat(results, axis=1)
        # get subset of parameters that were searched over
        column_names = [] if len(functions) == 1 else [None]
        column_names += search_keys
        column_names += [None]*(len(result.columns.names)-len(column_names))
        result.columns.names = column_names

        return StepFrame(result)
    else:
        result = results[0]
        if isinstance(result, pd.DataFrame):
            return StepFrame(result)
        else:
            result.name = functions[0].__name__
            return StepSeries(result)

class StepFrame(pd.DataFrame):
    expand = expand
    dapply = dapply

    @property
    def _constructor(self):
        return StepFrame

    @property
    def _contructor_sliced(self):
        return pd.Series

class StepSeries(pd.Series):
    expand = expand
    dapply = dapply

    @property
    def _constructor(self):
        return StepSeries

    @property
    def _contructor_expanddim(self):
        return StepFrame

def _print_unhashable(df, columns=None):
    """
    Replace unhashable values in a DataFrame with their string repr
    Args:
        df: DataFrame
        columns: columns to replace, if necessary. Default None replaces all columns.
    """
    for c in df.columns if columns is None else columns:
        if df.dtypes[c] == object:
            try:
                df[c].apply(hash)
            except TypeError:
                df[c] = df[c].dropna().apply(pformat).ix[df.index]

    return df

def intersection(df, pairwise=False, **subset_args):
    """
    Counts the size of intersections of subsets of predicted examples.
    E.g. count the overlap between the top k of two different models
    Args:
        df: the result of to_dataframe(), Predict steps of length n_steps
        pairwise: when False, returns the mutual intersection between 
            all subsets. Otherwise returns an n_steps x n_steps matrix 
            whose i,j entry is the number of examples in the 
            intersection between the i and j step subsets.
        **subset_args: arguments to be passed to model.y_subset()
            for each predict step
    Returns: the intersection, either an integer, if pairwise is False, 
        or a DataFrame, otherwise.
    """
    indexes = map(lambda row: set(model.y_subset(row[1].step.get_result()['y'], **subset_args).index), df.iterrows())

    if not pairwise:
        return len(util.intersect(indexes))
    else:
        r = pd.DataFrame(index=df.index, columns=xrange(len(df)))

        for i in xrange(len(df)):
            r.values[i][i] = len(indexes[i])
            for j in xrange(i+1, len(df)):
                r.values[i][j] = len(indexes[i] & indexes[j])
        return r

def apply_y(df, fn, **kwargs):
    return apply(df, lambda s: fn(model.y_subset(s.get_result()['y'], **kwargs)))

def show_tree(tree, feature_names,max_depth=None):
    import wand.image

    filename = NamedTemporaryFile(delete=False).name
    export_tree(tree, filename, [c.encode('ascii') for c in feature_names],max_depth)
    img = wand.image.Image(filename=filename)
    return img

def export_tree(clf, filename, feature_names=None, max_depth=None):
    from sklearn.externals.six import StringIO
    import pydot

    dot_data = StringIO()
    tree.export_graphviz(clf, out_file=dot_data, feature_names=feature_names, max_depth=max_depth)
    graph = pydot.graph_from_dot_data(dot_data.getvalue())
    graph.write_pdf(filename)