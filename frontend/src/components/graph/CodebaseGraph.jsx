import {
  useEffect,
  useMemo,
  useCallback,
  useRef,
  useImperativeHandle,
  forwardRef,
} from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  MiniMap,
  MarkerType,
  useNodesState,
  useEdgesState,
  useReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import CodebaseNode from './CodebaseNode';
import CodebaseEdge from './CodebaseEdge';
import { computeVisibleGraph } from './graphAdapter';
import { getLayoutedElements } from './graphLayout';
import './CodebaseGraph.css';

const nodeTypes = {
  codebaseNode: CodebaseNode,
};

const edgeTypes = {
  codebaseEdge: CodebaseEdge,
};

/**
 * Inner Flow component that has direct access to useReactFlow()
 */
const FlowInner = forwardRef(function FlowInner(
  {
    graphModel,
    expandedNodeIds,
    selectedNodeId,
    searchQuery,
    selectedLayer,
    onSelectNode,
    onToggleExpand,
  },
  ref
) {
  const { fitView, zoomIn, zoomOut, setCenter, getNodes } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const hasInitializedFit = useRef(false);

  // Expose viewport controls to parent via imperative handle
  useImperativeHandle(ref, () => ({
    zoomIn: () => zoomIn({ duration: 250 }),
    zoomOut: () => zoomOut({ duration: 250 }),
    fitView: () => fitView({ padding: 0.18, duration: 450 }),
    resetView: () => {
      fitView({ padding: 0.18, duration: 400 });
    },
    focusNode: (nodeId) => {
      const currentNodes = getNodes();
      const target = currentNodes.find((n) => n.id === nodeId);
      if (target && target.position) {
        setCenter(target.position.x + 120, target.position.y + 40, {
          duration: 500,
          zoom: 1.05,
        });
      }
    },
  }));

  // Recompute layout whenever graph model, expansion state, search, or layer changes
  useEffect(() => {
    if (!graphModel || graphModel.nodesMap.size === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const { visibleNodes, visibleEdges } = computeVisibleGraph({
      graphModel,
      expandedNodeIds,
      searchQuery,
      selectedLayer,
    });

    // Attach expand toggle callback to node data
    const nodesWithCallbacks = visibleNodes.map((node) => ({
      ...node,
      data: {
        ...node.data,
        onToggleExpand,
      },
    }));

    // Calculate hierarchical Dagre layout (Left-to-Right)
    const layouted = getLayoutedElements(nodesWithCallbacks, visibleEdges, {
      direction: 'LR',
      nodesep: 50,
      ranksep: 110,
    });

    setNodes(layouted.nodes);
    setEdges(layouted.edges);

    // Initial automatic camera fit on initial load
    if (!hasInitializedFit.current && layouted.nodes.length > 0) {
      hasInitializedFit.current = true;
      setTimeout(() => {
        fitView({ padding: 0.2, duration: 400 });
      }, 80);
    }
  }, [
    graphModel,
    expandedNodeIds,
    searchQuery,
    selectedLayer,
    onToggleExpand,
    fitView,
    setNodes,
    setEdges,
  ]);

  // Center on search match if query exists
  useEffect(() => {
    if (!searchQuery || !nodes.length) return;
    const match = nodes.find((n) => n.data.isSearchMatch);
    if (match && match.position) {
      setCenter(match.position.x + 120, match.position.y + 40, {
        duration: 400,
        zoom: 1.05,
      });
    }
  }, [searchQuery, nodes, setCenter]);

  // Transform edges dynamically with Dark Aurora (Warm Amber #F5A524 / Soft Blue #4C9AFF)
  const styledEdges = useMemo(() => {
    return edges.map((edge) => {
      const isOutgoing = edge.source === selectedNodeId;
      const isIncoming = edge.target === selectedNodeId;
      const isActive = isOutgoing || isIncoming;

      return {
        ...edge,
        animated: isActive,
        data: {
          ...edge.data,
          isOutgoing,
          isIncoming,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: isActive ? (isOutgoing ? '#F5A524' : '#4C9AFF') : 'rgba(76, 154, 255, 0.25)',
          width: isActive ? 15 : 12,
          height: isActive ? 15 : 12,
        },
        zIndex: isActive ? 10 : 1,
      };
    });
  }, [edges, selectedNodeId]);

  // Handle node selection
  const handleNodeClick = useCallback(
    (_, node) => {
      if (onSelectNode) {
        onSelectNode(node.id);
      }
    },
    [onSelectNode]
  );

  const handlePaneClick = useCallback(() => {
    if (onSelectNode) {
      onSelectNode(null);
    }
  }, [onSelectNode]);

  // MiniMap node color generator (Dark Aurora palette)
  const getMiniMapNodeColor = useCallback(
    (node) => {
      if (node.id === selectedNodeId) return '#F5A524';
      if (node.data?.isSearchMatch) return '#F5A524';
      if (node.data?.type === 'entrypoint' || node.data?.isRoot) return '#1F6FEB';
      return '#0B1A33';
    },
    [selectedNodeId]
  );

  return (
    <ReactFlow
      nodes={nodes}
      edges={styledEdges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={handleNodeClick}
      onPaneClick={handlePaneClick}
      minZoom={0.25}
      maxZoom={2.4}
      defaultViewport={{ x: 80, y: 60, zoom: 0.9 }}
      nodesDraggable={true}
      nodesConnectable={false}
      elementsSelectable={true}
      panOnScroll={false}
      selectionOnDrag={false}
      proOptions={{ hideAttribution: true }}
      className="cv-reactflow-instance"
    >
      {/* Subtle Dark Aurora grid pattern on Deep Background (#02060F) */}
      <Background
        variant="lines"
        gap={32}
        size={1}
        color="rgba(31, 111, 235, 0.16)"
        className="cv-graph-grid-bg"
      />

      {/* MiniMap in lower left */}
      <MiniMap
        nodeColor={getMiniMapNodeColor}
        nodeStrokeWidth={1}
        maskColor="rgba(2, 6, 15, 0.78)"
        className="cv-graph-minimap"
        pannable
        zoomable
      />
    </ReactFlow>
  );
});

/**
 * Main CodebaseGraph wrapper with ReactFlowProvider
 */
const CodebaseGraph = forwardRef(function CodebaseGraph(props, ref) {
  return (
    <div className="cv-graph-wrapper">
      <ReactFlowProvider>
        <FlowInner ref={ref} {...props} />
      </ReactFlowProvider>
    </div>
  );
});

export default CodebaseGraph;
