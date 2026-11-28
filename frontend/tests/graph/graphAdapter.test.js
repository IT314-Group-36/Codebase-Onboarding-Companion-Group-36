import { describe, it, expect } from 'vitest';
import {
  normalizeGraphData, computeVisibleGraph, normalizeNodeType, getNodeLayerTitle,
} from '../../src/components/graph/graphAdapter';
import { getLayoutedElements } from '../../src/components/graph/graphLayout';

const diamond = {
  nodes: ['root', 'a', 'b', 'shared'].map((id) => ({ id, type: id === 'root' ? 'root' : 'module' })),
  edges: [
    { source: 'root', target: 'a' }, { source: 'root', target: 'b' },
    { source: 'a', target: 'shared' }, { source: 'b', target: 'shared' },
  ],
};

describe('dependency graph — white-box traversal and normalization paths', () => {
  it.each([
    ['entry', '', '', 'entrypoint'], ['', '', 'App.jsx', 'entrypoint'],
    ['repository', '', '', 'root'], ['', 'src/pages/Home.jsx', '', 'page'],
    ['', 'src/components/Card.jsx', '', 'component'], ['', '', 'useAuth', 'hook'],
    ['service', '', '', 'api'], ['helper', '', '', 'util'],
    ['method', '', '', 'function'], ['package', '', '', 'module'],
    ['unrecognized', '', '', 'component'],
  ])('selects the node-type condition for %j/%j/%j', (type, path, name, expected) => {
    expect(normalizeNodeType(type, path, name)).toBe(expected);
  });

  it.each([
    ['entrypoint', 'Starting point'], ['root', 'Project root'], ['page', 'Page'],
    ['component', 'Screen piece'], ['hook', 'Shared logic'], ['api', 'Server & data'],
    ['util', 'Helper'], ['function', 'Function Symbol'], ['module', 'Directory Module'],
    ['unknown', 'Module'],
  ])('selects the %s layer switch branch', (type, label) => {
    expect(getNodeLayerTitle(type)).toBe(label);
  });

  it('takes the nested-data fallback and synthesizes a missing source node', () => {
    const model = normalizeGraphData({ data: {
      modules: [null, { _id: 2, label: 'Database', filePath: 'db.py', loc: '12', meta: { stable: true } }],
      dependencies: [{ parent: 'src/api.py', child: 2, relationship: 'calls', id: 'edge1' }, { source: '' }],
      stats: { maxDepth: 5, circularDependencies: 1 },
    } });
    expect(model.nodesMap.get('2')).toMatchObject({
      name: 'Database', path: 'db.py', lines: 12, metadata: { stable: true },
    });
    expect(model.nodesMap.has('src/api.py')).toBe(true);
    expect(model.rawEdges).toEqual([expect.objectContaining({ id: 'edge1', label: 'calls' })]);
    expect(model.stats).toEqual({ totalNodes: 2, totalEdges: 1, maxDepth: 5, circularDependencies: 1 });
  });

  it('handles an empty graph', () => {
    const model = normalizeGraphData(null);
    expect(computeVisibleGraph({ graphModel: model }).visibleNodes).toEqual([]);
    expect(getLayoutedElements([], [])).toEqual({ nodes: [], edges: [] });
  });

  it('normalizes backend src/dst edges and synthesizes missing endpoints', () => {
    const model = normalizeGraphData({ graph: {
      nodes: [{ id: 'api', path: 'src/services/api.js' }],
      edges: [{ src: 'api', dst: 'db', kind: 'imports' }, { src: 'api', dst: 'api' }, null],
    } });
    expect(model.nodesMap.get('api').type).toBe('api');
    expect(model.nodesMap.has('db')).toBe(true);
    expect(model.rawEdges).toHaveLength(1);
    expect(model.inDegree.get('db')).toBe(1);
    expect(model.outDegree.get('api')).toBe(1);
    expect(model.rootNodeIds).toEqual(['api']);
  });

  it('keeps shared dependencies visible when another expanded branch still reaches them', () => {
    const model = normalizeGraphData(diamond);
    const visible = (expanded) => computeVisibleGraph({ graphModel: model, expandedNodeIds: new Set(expanded) });
    expect([...visible([]).visibleNodeIds]).toEqual(['root']);
    expect(visible(['root', 'a', 'b']).visibleNodeIds.has('shared')).toBe(true);
    const oneCollapsed = visible(['root', 'b']);
    expect(oneCollapsed.visibleNodeIds.has('shared')).toBe(true);
    expect(oneCollapsed.visibleEdges).toHaveLength(4);
    expect(visible(['root']).visibleNodeIds.has('shared')).toBe(false);
    expect(visible([]).visibleEdges).toEqual([]);
  });

  it('terminates expansion on cycles and still chooses a root', () => {
    const model = normalizeGraphData({
      nodes: [{ id: 'a' }, { id: 'b' }],
      edges: [{ source: 'a', target: 'b' }, { source: 'b', target: 'a' }],
    });
    expect(model.rootNodeIds).toHaveLength(1);
    const result = computeVisibleGraph({ graphModel: model, expandedNodeIds: new Set(['a', 'b']) });
    expect(result.visibleNodes).toHaveLength(2);
    expect(result.visibleEdges).toHaveLength(2);
  });

  it('marks search/layer matches without removing the dependency context', () => {
    const model = normalizeGraphData({ nodes: [
      { id: 'app', type: 'entrypoint' }, { id: 'db', path: 'src/services/database.js', name: 'Database' },
    ], edges: [{ source: 'app', target: 'db' }] });
    const result = computeVisibleGraph({
      graphModel: model, expandedNodeIds: new Set(['app']), searchQuery: ' DATABASE ', selectedLayer: 'api',
    });
    expect(result.visibleNodes).toHaveLength(2);
    expect(result.visibleNodes.find((n) => n.id === 'db').data).toMatchObject({ isSearchMatch: true, matchesLayer: true });
    expect(result.visibleNodes.find((n) => n.id === 'app').data.matchesLayer).toBe(false);
  });

  it.each(['LR', 'TB'])('lays out directed nodes in %s order without mutating input', (direction) => {
    const nodes = [{ id: 'a', position: { x: 0, y: 0 } }, { id: 'b', position: { x: 0, y: 0 } }];
    const edges = [{ id: 'ab', source: 'a', target: 'b' }];
    const result = getLayoutedElements(nodes, edges, { direction });
    const axis = direction === 'LR' ? 'x' : 'y';
    expect(result.nodes[1].position[axis]).toBeGreaterThan(result.nodes[0].position[axis]);
    expect(nodes[0].position).toEqual({ x: 0, y: 0 });
    expect(result.edges).toEqual(edges);
    for (const node of result.nodes) {
      expect(Number.isFinite(node.position.x)).toBe(true);
      expect(Number.isFinite(node.position.y)).toBe(true);
    }
  });
});
