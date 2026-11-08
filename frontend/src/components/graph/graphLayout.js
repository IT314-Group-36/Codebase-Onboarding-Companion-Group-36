/**
 * CODEVERSE — Dagre Hierarchical Layout Engine
 *
 * Automatically arranges codebase dependency nodes in a clean,
 * readable Left-to-Right (LR) hierarchical flow with stable positioning.
 */

import dagre from 'dagre';

const NODE_WIDTH = 240;
const NODE_HEIGHT = 80;

export function getLayoutedElements(nodes, edges, options = {}) {
  const {
    direction = 'LR',
    nodesep = 55,
    ranksep = 110,
    marginx = 80,
    marginy = 60,
  } = options;

  if (!nodes || nodes.length === 0) {
    return { nodes: [], edges: [] };
  }

  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  dagreGraph.setGraph({
    rankdir: direction,
    nodesep,
    ranksep,
    marginx,
    marginy,
    ranker: 'network-simplex', // Cleanest hierarchical alignment for software architectures
  });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);

    // Shift Dagre center coordinates (x, y) to top-left for React Flow
    const x = nodeWithPosition
      ? nodeWithPosition.x - NODE_WIDTH / 2
      : node.position?.x || 0;
    const y = nodeWithPosition
      ? nodeWithPosition.y - NODE_HEIGHT / 2
      : node.position?.y || 0;

    return {
      ...node,
      position: { x, y },
      style: {
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      },
    };
  });

  return {
    nodes: layoutedNodes,
    edges,
  };
}
