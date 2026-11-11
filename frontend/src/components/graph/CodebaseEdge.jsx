import { memo } from 'react';
import { getBezierPath, EdgeLabelRenderer, BaseEdge } from '@xyflow/react';
import './CodebaseEdge.css';

/**
 * Custom React Flow Edge for Codebase Dependency Paths.
 * Visualizes active / inactive dependency paths using:
 * - Active: Power Orange (#FF4E08) animated flow
 * - Inactive: Muted Golden Pitch (#3D3A2B)
 */
function CodebaseEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data = {},
  selected,
  markerEnd,
}) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const { label, isOutgoing = false, isIncoming = false, isHighlighted = false } = data;
  const isActive = selected || isOutgoing || isIncoming || isHighlighted;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        className={`cv-graph-edge ${isActive ? 'cv-graph-edge--active' : 'cv-graph-edge--inactive'} ${
          isOutgoing ? 'cv-graph-edge--outgoing' : ''
        } ${isIncoming ? 'cv-graph-edge--incoming' : ''}`}
      />

      {label && isActive && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="cv-graph-edge-label"
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export default memo(CodebaseEdge);
