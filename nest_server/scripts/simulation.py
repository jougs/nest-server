import datetime
import nest
import nest.topology as tp
import numpy as np

from . import serialize

__all__ = [
    'run',
]


def getNodes(collection, meta):
  if 'spatial' in meta:
    nodes = nest.GetNodes(collection)[0]
  else:
    nodes = collection
  return nodes


def log(message):
  # print(message)
  return (str(datetime.datetime.now()), 'server', message)


def run(data):
  # print(data)
  logs = []

  logs.append(log('Get request'))
  simtime = data.get('time', 1000.0)
  kernel = data.get('kernel', {})
  models = data['models']
  collections = data['collections']
  connectomes = data['connectomes']
  records = []
  collections_obj = []

  logs.append(log('Reset kernel'))
  nest.ResetKernel()

  logs.append(log('Set seed in numpy random'))
  np.random.seed(int(data.get('random_seed', 0)))

  logs.append(log('Set kernel status'))
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

  logs.append(log('Collect all recordables for multimeter'))
  for idx, collection in enumerate(collections):
    model = models[collection['model']]
    if model['existing'] != 'multimeter':
      continue

    if 'record_from' in model['params']:
      continue

    recs = list(filter(lambda conn: conn['source'] == idx, connectomes))
    if len(recs) == 0:
      continue

    recordable_models = []
    for conn in recs:
      recordable_model = models[collections[conn['target']]['model']]
      recordable_models.append(recordable_model['existing'])
    recordable_models_set = list(set(recordable_models))
    assert len(recordable_models_set) == 1

    recordables = nest.GetDefaults(recordable_models_set[0], 'recordables')
    model['params']['record_from'] = list(map(str, recordables))

  logs.append(log('Copy models'))
  for new, model in models.items():
    params_serialized = serialize.model_params(model['existing'], model['params'])
    nest.CopyModel(model['existing'], new, params_serialized)

  logs.append(log('Create collections'))
  for idx, collection in enumerate(collections):
    collections[idx]['idx'] = idx
    if 'spatial' in collection:
      specs = collection['spatial']
      specs['elements'] = collection['model']
      obj = tp.CreateLayer(serialize.layer(specs))
      if 'positions' in specs:
        positions = specs['positions']
      else:
        positions = tp.GetPosition(nest.GetNodes(obj)[0])
      positions = np.round(positions, decimals=2).astype(float)
      collections[idx]['spatial']['positions'] = positions.tolist()
      collections[idx]['n'] = positions.shape[0]
      collections[idx]['ndim'] = positions.ndim
      collections[idx]['global_ids'] = nest.GetNodes(obj)[0]
    else:
      n = int(collection.get('n', 1))
      obj = nest.Create(collection['model'], n)
      collections[idx]['global_ids'] = list(obj)
      if collection['element_type'] == 'recorder':
        model = models[collection['model']]
        record = {
            'recorder': {
                'global_ids': list(obj),
                'idx': idx,
                'model': model['existing']
            }
        }
        if 'record_from' in model['params']:
          record['record_from'] = model['params']['record_from']
        records.append(record)
    collections_obj.append(obj)

  logs.append(log('Connect collections'))
  for connectome in connectomes:
    source = collections[connectome['source']]
    target = collections[connectome['target']]
    source_obj = collections_obj[connectome['source']]
    target_obj = collections_obj[connectome['target']]
    if ('spatial' in source) and ('spatial' in target):
      projections = connectome['projections']
      tp.ConnectLayers(source_obj, target_obj, serialize.projections(projections))
    else:
      conn_spec = connectome.get('conn_spec', 'all_to_all')
      syn_spec = connectome.get('syn_spec', 'static_synapse')
      # NEST 2.18
      source_nodes = getNodes(source_obj, source)
      target_nodes = getNodes(target_obj, target)
      if 'tgt_idx' in connectome:
        tgt_idx = connectome['tgt_idx']
        if len(tgt_idx) > 0:
          if isinstance(tgt_idx[0], int):
            source = source_nodes
            target = np.array(target_nodes)[tgt_idx].tolist()
            nest.Connect(source_nodes, target, serialize.conn(conn_spec), serialize.syn(syn_spec))
          else:
            for idx in range(len(tgt_idx)):
              target = np.array(target_nodes)[tgt_idx[idx]].tolist()
              if 'src_idx' in connectome:
                src_idx = connectome['src_idx']
                source = np.array(source_nodes)[src_idx[idx]].tolist()
              else:
                source = [source_nodes[idx]]
              nest.Connect(source, target, serialize.conn(conn_spec), serialize.syn(syn_spec))
      else:
        nest.Connect(source_nodes, target_nodes, serialize.conn(conn_spec), serialize.syn(syn_spec))
      # NEST 3
      # nest.Connect(source_obj, target_obj, serialize.conn(conn_spec), serialize.syn(syn_spec))

  logs.append(log('Start simulation'))
  nest.Simulate(float(simtime))

  logs.append(log('End simulation'))
  data['kernel']['time'] = nest.GetKernelStatus('time')

  logs.append(log('Serialize recording data'))
  ndigits = int(-1 * np.log10(resolution))
  for idx, record in enumerate(records):
    records[idx]['idx'] = idx
    if record['recorder']['model'] == 'spike_detector':
      neuron, rec = 'source', 'target'
    else:
      rec, neuron = 'source', 'target'
    global_ids = []
    for connectome in connectomes:
      if connectome[rec] == record['recorder']['idx']:
        collection = collections[connectome[neuron]]
        global_ids.extend(collection['global_ids'])
      records[idx]['global_ids'] = global_ids
      recorder_obj = collections_obj[record['recorder']['idx']]
      events = serialize.events(recorder_obj, ndigits)
      records[idx]['events'] = events
      records[idx]['senders'] = list(set(events['senders']))
  data['records'] = records

  return {'data': data, 'logs': logs}
