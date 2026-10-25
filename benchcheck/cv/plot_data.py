"""Min/max plot decimation; full-resolution arrays remain available with full_resolution=true."""
from __future__ import annotations
import numpy as np


def decimate(result: dict, limit: int = 20000) -> dict:
    data = result['data']
    n = len(data['E'])
    keep = set()
    currents = np.asarray(data['i'])
    for segment in result['segments']:
        keep.update((segment['start'], segment['end']))
    for cycle in result['cycles']:
        for role in ('forward','return'):
            sweep=cycle.get(role)
            if sweep:
                keep.update(p['index'] for p in sweep['peaks'])
    for number in set(data['cycle']):
        indices = np.flatnonzero(np.asarray(data['cycle']) == number)
        if indices.size <= limit:
            keep.update(indices.tolist())
        else:
            # Reserve room for every detected peak and vertex before making extrema bins.
            reserved = len(keep.intersection(indices.tolist()))
            bins = max(1, (limit-reserved-2)//2)
            keep.update((int(indices[0]),int(indices[-1])))
            for chunk in np.array_split(indices, bins):
                values=currents[chunk]
                keep.update((int(chunk[np.argmin(values)]), int(chunk[np.argmax(values)])))
    indices=sorted(keep)
    if len(indices)==n:
        return result
    lookup={old:new for new,old in enumerate(indices)}
    for key,value in data.items():
        if value is not None:
            data[key]=[value[k] for k in indices]
    data['original_index']=indices
    seen=set()
    for cycle in result['cycles']+[result['selected']]:
        for role in ('forward','return'):
            sweep=cycle.get(role)
            if sweep and id(sweep) not in seen:
                seen.add(id(sweep))
                sweep['start_index']=lookup[sweep['start_index']]
                sweep['end_index']=lookup[sweep['end_index']]
                for peak in sweep['peaks']:
                    peak['original_index']=peak['index']
                    peak['index']=lookup[peak['index']]
    for segment in result['segments']:
        segment['start'],segment['end']=lookup[segment['start']],lookup[segment['end']]
    result['notices'].append(f'Plot reduced from {n} to {len(indices)} points using min/max bins; all calculations used the full data. Request full_resolution=true for all points.')
    return result
