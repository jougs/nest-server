#!/usr/bin/env python

import numpy as np
import nest
import nest.topology as tp

from . import serialize


def _getNodes(collection, connectome):
    if collection['element_type'] == 'structure':
        if 'mask' in connectome:
            mask_type, spec = connectome['mask'].item()
            mask_obj = tp.CreateMask(mask_type, spec)
            anchor = conn.get('anchor', [0.] * collection['ndim'])
            nodes = tp.SelectNodesByMask(collection, anchor, mask_obj)
        else:
            nodes = collection['obj'].get('nodes')
    else:
        nodes = collection['obj']
    return nodes


def simulate(data):
    print('Simulate %s (%s)' % (data.get('name', None), data['_id']))
    # print(data)

    # print('Get request')
    simulation = data.get('simulation', {'time': 1000.0})
    kernel = data.get('kernel', {'time': 0.0})
    models = data.get('models', [])
    collections = data['collections']
    connectomes = data.get('connectomes', [])
    records = []

    # print('Set kernel')
    nest.ResetKernel()
    np.random.seed(int(simulation.get('random_seed', 0)))
    local_num_threads = int(kernel.get('local_num_threads', 1))
    rng_seeds = np.random.randint(0, 1000, local_num_threads).tolist()
    resolution = float(kernel.get('resolution', 1.0))
    kernel_dict = {
        'local_num_threads': local_num_threads,
        'resolution': resolution,
        'rng_seeds': rng_seeds,
    }
    nest.SetKernelStatus(kernel_dict)
    data['kernel'] = kernel_dict

    # print('Copy models')
    for model in models:
        nest.CopyModel(**model)

    # print('Set all recordables of the source neuron for the multimeter')
    for idx, collection in enumerate(collections):
        if collection['element_type'] != 'recorder':
            continue
        if collection['model'] != 'multimeter':
            continue
        recs = filter(
            lambda rec_conn: rec_conn['target'] == idx, connections)
        if len(recs) == 0:
            continue

        models = []
        for conn in recs:
            model = collections[recs[0]['source']]['model']
            models.append(model)
        models_unique = list(set(models))
        assert len(models_unique) == 1

        recordables = nest.GetDefaults(models_unique[0], 'recordables')
        if 'params' in collection:
            collection['params']['record_from'] = recordables
        else:
            collection['params'] = {'record_from': recordables}
        collections[idx] = collection

    # print('Create collections')
    for idx, collection in enumerate(collections):
        assert idx == collection['idx']
        if collection.get('disabled', False):
            continue
        if collection['element_type'] == 'structure':
            obj = tp.CreateLayer(collection['specs'])
            collections[idx]['ndim'] = len(collection['specs']['positions'][0])
        else:
            model = collection['model']
            n = int(collection.get('n', 1))
            params = collection.get('params', {})
            obj = nest.Create(model, n, serialize.collection(model, params))
            if collection['element_type'] == 'recorder':
                records.append({'recorder': {'idx': idx, 'model': model}})
        collections[idx]['obj'] = obj
        collections[idx]['global_ids'] = tuple(obj)

    # print('Connect collection')
    for connectome in connectomes:
        pre_idx = connectome['pre']
        post_idx = connectome['post']
        pre_element_type = collections[pre_idx]['element_type']
        post_element_type = collections[post_idx]['element_type']
        if pre_element_type == 'structure' and post_element_type == 'structure':
            pre_layer = collections[pre_idx]['obj']
            post_layer = collections[post_idx]['obj']
            projections = connectome['projections']
            tp.ConnectLayers(pre_layer, post_layer, projections)
        else:
            pre_nodes = _getNodes(collections[pre_idx], connectome)
            post_nodes = _getNodes(collections[post_idx], connectome)
            conn_spec = connectome.get('conn_spec', 'all_to_all')
            syn_spec = connectome.get('syn_spec', 'static_synapse')
            if collections[post_idx]['model'] in ['multimeter', 'voltmeter']:
                pre_nodes, post_nodes = post_nodes, pre_nodes
                if type(conn_spec) == dict:
                    if conn_spec['rule'] == 'fixed_indegree':
                        conn_spec['rule'] = 'fixed_outdegree'
                        conn_spec['outdegree'] = conn_spec['indegree']
                        del conn_spec['indegree']
            nest.Connect(pre_nodes, post_nodes,
                         serialize.conn(conn_spec), serialize.syn(syn_spec))

    # print('Simulate')
    nest.Simulate(float(simulation['time']))
    data['kernel']['time'] = nest.GetKernelStatus('time')

    # print('Get records')
    ndigits = int(-1 * np.log10(resolution))
    for idx, record in enumerate(records):
        recorderObj = collections[record['recorder']['idx']]['obj']
        events = serialize.events(recorderObj, ndigits)
        records[idx]['idx'] = idx
        records[idx]['events'] = events
    data['records'] = records

    nest.ResetKernel()

    # print('Delete objects')
    for collection in collections:
        del collection['obj']

    return data
