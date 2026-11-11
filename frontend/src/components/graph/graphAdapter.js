/**
 * CODEVERSE — Dynamic Codebase Graph Adapter
 *
 * Normalizes dynamic, unpredictable backend dependency graph payloads
 * into strongly-typed graph models for @xyflow/react.
 *
 * Handles:
 * - Flexible payloads ({ graph: { nodes, edges } }, { nodes, edges }, { modules, dependencies })
 * - Module IDs, file paths, node types, layer categorization
 * - Directed adjacency indexing (in/out edges, in/out degrees)
 * - Dynamic branch expansion and collapse with shared dependency preservation
 * - Unlimited dependency hierarchy depth
 */

export function normalizeNodeType(rawType = '', path = '', name = '') {
  const t = String(rawType).toLowerCase();
  const p = String(path).toLowerCase();
  const n = String(name).toLowerCase();

  if (t === 'entrypoint' || t === 'entry' || n === 'app.jsx' || n === 'main.jsx' || n === 'index.jsx') {
    return 'entrypoint';
  }
  if (t === 'root' || t === 'repository') {
    return 'root';
  }
  if (t === 'page' || p.includes('/pages/') || p.includes('/routes/')) {
    return 'page';
  }
  if (t === 'component' || p.includes('/components/')) {
    return 'component';
  }
  if (t === 'hook' || p.includes('/hooks/') || n.startsWith('use')) {
    return 'hook';
  }
  if (t === 'api' || t === 'service' || p.includes('/services/') || p.includes('/api/')) {
    return 'api';
  }
  if (t === 'util' || t === 'utility' || t === 'helper' || p.includes('/utils/') || p.includes('/helpers/')) {
    return 'util';
  }
  if (t === 'function' || t === 'method') {
    return 'function';
  }
  if (t === 'module' || t === 'folder' || t === 'package') {
    return 'module';
  }
  return 'component';
}

export function getNodeLayerTitle(type) {
  switch (type) {
    case 'entrypoint':
      return 'Entrypoint';
    case 'root':
      return 'Repository Root';
    case 'page':
      return 'Page View';
    case 'component':
      return 'UI Component';
    case 'hook':
      return 'Hook / Context';
    case 'api':
      return 'Service / API';
    case 'util':
      return 'Utility / Helper';
    case 'function':
      return 'Function Symbol';
    case 'module':
      return 'Directory Module';
    default:
      return 'Module';
  }
}

/**
 * Normalizes raw backend graph response into structured maps and indices.
 */
export function normalizeGraphData(raw) {
  if (!raw) {
    return {
      rawNodes: [],
      rawEdges: [],
      nodesMap: new Map(),
      outEdgesMap: new Map(),
      inEdgesMap: new Map(),
      inDegree: new Map(),
      outDegree: new Map(),
      rootNodeIds: [],
      stats: { totalNodes: 0, totalEdges: 0, circularDependencies: 0, maxDepth: 0 },
    };
  }

  // Detect root payload container
  let rawNodes;
  let rawEdges;
  let rawStats;

  if (Array.isArray(raw)) {
    rawNodes = raw;
  } else if (raw.graph && typeof raw.graph === 'object') {
    rawNodes = raw.graph.nodes || raw.graph.modules || [];
    rawEdges = raw.graph.edges || raw.graph.dependencies || raw.graph.relationships || [];
    rawStats = raw.graph.stats || {};
  } else if (raw.data && typeof raw.data === 'object') {
    rawNodes = raw.data.nodes || raw.data.modules || [];
    rawEdges = raw.data.edges || raw.data.dependencies || [];
    rawStats = raw.data.stats || {};
  } else {
    rawNodes = raw.nodes || raw.modules || raw.vertices || [];
    rawEdges = raw.edges || raw.dependencies || raw.relationships || raw.links || [];
    rawStats = raw.stats || {};
  }

  const nodesMap = new Map();
  const outEdgesMap = new Map(); // sourceId -> array of { target, label, edgeId }
  const inEdgesMap = new Map();  // targetId -> array of { source, label, edgeId }
  const inDegree = new Map();    // id -> count of incoming edges
  const outDegree = new Map();   // id -> count of outgoing edges

  // 1. Process Nodes
  rawNodes.forEach((node, idx) => {
    if (!node) return;
    const id = String(
      node.id ?? node._id ?? node.moduleId ?? node.name ?? node.path ?? `node-${idx}`
    );
    const name = String(
      node.name ?? node.label ?? node.title ?? id.split('/').pop()
    );
    const path = String(
      node.path ?? node.filePath ?? node.file ?? `src/${name}`
    );
    const type = normalizeNodeType(node.type || node.kind, path, name);
    const layer = node.layer || getNodeLayerTitle(type);
    const lines = Number(node.lines ?? node.loc ?? node.lineCount ?? node.size ?? 0);
    const purpose = node.purpose ?? node.description ?? node.summary ?? '';

    const normalizedNode = {
      id,
      name,
      path,
      type,
      layer,
      lines,
      purpose,
      metadata: node.metadata || node.meta || {},
      raw: node,
    };

    nodesMap.set(id, normalizedNode);
    outEdgesMap.set(id, []);
    inEdgesMap.set(id, []);
    inDegree.set(id, 0);
    outDegree.set(id, 0);
  });

  // 2. Process Edges
  const validEdges = [];
  rawEdges.forEach((edge, idx) => {
    if (!edge) return;
    const source = String(
      edge.from ?? edge.source ?? edge.src ?? edge.caller ?? edge.importer ?? edge.parent ?? ''
    );
    const target = String(
      edge.to ?? edge.target ?? edge.dst ?? edge.callee ?? edge.imported ?? edge.child ?? ''
    );

    if (!source || !target || source === target) return;
    // Ensure both endpoints exist in our nodes map; if not, synthesize a placeholder node
    if (!nodesMap.has(source)) {
      const sType = normalizeNodeType('', source, source);
      nodesMap.set(source, {
        id: source,
        name: source.split('/').pop(),
        path: source,
        type: sType,
        layer: getNodeLayerTitle(sType),
        lines: 0,
        purpose: '',
        metadata: {},
      });
      outEdgesMap.set(source, []);
      inEdgesMap.set(source, []);
      inDegree.set(source, 0);
      outDegree.set(source, 0);
    }

    if (!nodesMap.has(target)) {
      const tType = normalizeNodeType('', target, target);
      nodesMap.set(target, {
        id: target,
        name: target.split('/').pop(),
        path: target,
        type: tType,
        layer: getNodeLayerTitle(tType),
        lines: 0,
        purpose: '',
        metadata: {},
      });
      outEdgesMap.set(target, []);
      inEdgesMap.set(target, []);
      inDegree.set(target, 0);
      outDegree.set(target, 0);
    }

    const label = String(
      edge.label ?? edge.relationship ?? edge.type ?? edge.kind ?? 'imports'
    );
    const edgeId = edge.id ? String(edge.id) : `edge-${source}->${target}-${idx}`;

    const edgeObj = {
      id: edgeId,
      source,
      target,
      label,
      raw: edge,
    };

    validEdges.push(edgeObj);

    outEdgesMap.get(source).push({ target, label, edgeId });
    inEdgesMap.get(target).push({ source, label, edgeId });
    outDegree.set(source, (outDegree.get(source) || 0) + 1);
    inDegree.set(target, (inDegree.get(target) || 0) + 1);
  });

  // 3. Identify Root Seed Nodes
  // Nodes with in-degree 0 (no callers/importers) or explicitly marked as entrypoint/root
  const rootNodeIds = [];
  for (const [id] of nodesMap.entries()) {
    const inCount = inDegree.get(id) || 0;
    const node = nodesMap.get(id);
    if (inCount === 0 || node.type === 'entrypoint' || node.type === 'root') {
      rootNodeIds.push(id);
    }
  }

  // Fallback: If circular dependencies lead to no in-degree 0, pick the node with lowest in-degree
  if (rootNodeIds.length === 0 && nodesMap.size > 0) {
    let minIn = Infinity;
    let bestId = null;
    for (const [id, count] of inDegree.entries()) {
      if (count < minIn) {
        minIn = count;
        bestId = id;
      }
    }
    if (bestId) rootNodeIds.push(bestId);
  }

  const stats = {
    totalNodes: nodesMap.size,
    totalEdges: validEdges.length,
    circularDependencies: rawStats.circularDependencies ?? 0,
    maxDepth: rawStats.maxDepth ?? 3,
  };

  return {
    rawNodes: Array.from(nodesMap.values()),
    rawEdges: validEdges,
    nodesMap,
    outEdgesMap,
    inEdgesMap,
    inDegree,
    outDegree,
    rootNodeIds,
    stats,
  };
}

/**
 * Computes visible nodes and edges based on dynamic user expansion states.
 *
 * CRITICAL RULE:
 * Handles shared dependencies correctly. A node is visible if it is a root seed,
 * OR if it is reachable as a child of ANY currently expanded node along an active path.
 * If branch A collapses but branch B is still expanded and connects to node C,
 * node C remains visible.
 */
export function computeVisibleGraph({
  graphModel,
  expandedNodeIds = new Set(),
  searchQuery = '',
  selectedLayer = 'ALL',
}) {
  const { nodesMap, outEdgesMap, inEdgesMap, rootNodeIds, rawEdges } = graphModel;

  if (nodesMap.size === 0) {
    return { visibleNodes: [], visibleEdges: [], visibleNodeIds: new Set() };
  }

  // 1. Determine Visible Nodes
  // All root seeds are initially visible
  const visibleNodeIds = new Set(rootNodeIds);

  // Traverse BFS queue of visible nodes: if node is in expandedNodeIds, uncover all its children
  const queue = [...rootNodeIds];
  const visitedForExpansion = new Set();

  while (queue.length > 0) {
    const currentId = queue.shift();
    if (visitedForExpansion.has(currentId)) continue;
    visitedForExpansion.add(currentId);

    // If current node is expanded, reveal its direct child dependencies
    if (expandedNodeIds.has(currentId)) {
      const children = outEdgesMap.get(currentId) || [];
      for (const child of children) {
        const childId = child.target;
        if (!visibleNodeIds.has(childId)) {
          visibleNodeIds.add(childId);
          queue.push(childId);
        } else if (!visitedForExpansion.has(childId)) {
          // If child was already visible (e.g. from another branch), still queue to check if it's expanded
          queue.push(childId);
        }
      }
    }
  }

  // 2. Build React Flow Node Objects for all visible nodes
  const q = searchQuery.trim().toLowerCase();

  const visibleNodes = [];
  for (const nodeId of visibleNodeIds) {
    const node = nodesMap.get(nodeId);
    if (!node) continue;

    const childEdges = outEdgesMap.get(nodeId) || [];
    const parentEdges = inEdgesMap.get(nodeId) || [];
    const hasChildren = childEdges.length > 0;
    const isExpanded = expandedNodeIds.has(nodeId);

    const isSearchMatch = Boolean(
      q &&
      (node.name.toLowerCase().includes(q) ||
       node.path.toLowerCase().includes(q) ||
       node.layer.toLowerCase().includes(q))
    );

    const matchesLayer =
      selectedLayer === 'ALL' ||
      (selectedLayer === 'entrypoint' && (node.type === 'entrypoint' || node.type === 'root')) ||
      (selectedLayer === 'component' && (node.type === 'component' || node.type === 'page')) ||
      (selectedLayer === 'hook' && node.type === 'hook') ||
      (selectedLayer === 'util' && (node.type === 'util' || node.type === 'function')) ||
      (selectedLayer === 'api' && node.type === 'api');

    visibleNodes.push({
      id: node.id,
      type: 'codebaseNode',
      data: {
        id: node.id,
        name: node.name,
        path: node.path,
        type: node.type,
        layer: node.layer,
        lines: node.lines,
        purpose: node.purpose,
        hasChildren,
        childCount: childEdges.length,
        parentCount: parentEdges.length,
        isExpanded,
        isRoot: rootNodeIds.includes(node.id),
        isSearchMatch,
        matchesLayer,
        metadata: node.metadata,
      },
      position: { x: 0, y: 0 }, // Populated by Dagre layout
    });
  }

  // 3. Build React Flow Edges for connections where both endpoints are visible
  const visibleEdges = [];
  for (const edge of rawEdges) {
    if (visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)) {
      visibleEdges.push({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: 'codebaseEdge',
        label: edge.label,
        data: {
          label: edge.label,
          source: edge.source,
          target: edge.target,
        },
      });
    }
  }

  return {
    visibleNodes,
    visibleEdges,
    visibleNodeIds,
  };
}
