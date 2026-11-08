import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import {
  Compass,
  GitBranch,
  Boxes,
  Layers,
  Sparkles,
  Zap,
  Cpu,
  Code,
  FolderTree,
  ChevronRight,
  ChevronDown,
} from 'lucide-react';
import './CodebaseNode.css';

function getNodeIcon(type) {
  switch (type) {
    case 'entrypoint':
      return <Compass size={13} className="cv-node-type-icon" />;
    case 'root':
      return <GitBranch size={13} className="cv-node-type-icon" />;
    case 'page':
      return <Layers size={13} className="cv-node-type-icon" />;
    case 'component':
      return <Boxes size={13} className="cv-node-type-icon" />;
    case 'hook':
      return <Sparkles size={13} className="cv-node-type-icon" />;
    case 'api':
      return <Zap size={13} className="cv-node-type-icon" />;
    case 'util':
      return <Cpu size={13} className="cv-node-type-icon" />;
    case 'function':
      return <Code size={13} className="cv-node-type-icon" />;
    case 'module':
      return <FolderTree size={13} className="cv-node-type-icon" />;
    default:
      return <Boxes size={13} className="cv-node-type-icon" />;
  }
}

/**
 * Custom React Flow Node for Codebase Modules & Architecture.
 * Conforms strictly to CODEVERSE brand palette:
 * Classic Black (#000000), Golden Pitch (#3D3A2B), Power Orange (#FF4E08), Off White (#E6E5C7).
 */
function CodebaseNode({ data, selected }) {
  const {
    id,
    name,
    path,
    type,
    layer,
    lines,
    hasChildren,
    childCount,
    parentCount,
    isExpanded,
    isRoot,
    isSearchMatch,
    matchesLayer = true,
    onToggleExpand,
  } = data;

  const handleExpandClick = (e) => {
    e.stopPropagation();
    if (onToggleExpand) {
      onToggleExpand(id);
    }
  };

  return (
    <div
      className={`cv-node-card ${selected ? 'cv-node-card--selected' : ''} ${
        isSearchMatch ? 'cv-node-card--search-match' : ''
      } ${!matchesLayer ? 'cv-node-card--dimmed' : ''} ${
        isRoot ? 'cv-node-card--root' : ''
      }`}
      tabIndex={0}
      role="button"
      aria-label={`Module: ${name}, Layer: ${layer}`}
    >
      {/* React Flow Connection Handles */}
      <Handle
        type="target"
        position={Position.Left}
        className="cv-node-handle cv-node-handle--left"
        isConnectable={false}
      />
      <Handle
        type="source"
        position={Position.Right}
        className="cv-node-handle cv-node-handle--right"
        isConnectable={false}
      />

      {/* Top Header Row: Icon + Type + Name + Expand Button */}
      <div className="cv-node-card__header">
        <div className="cv-node-card__type-badge">
          {getNodeIcon(type)}
          <span className="cv-node-card__type-text">{layer}</span>
        </div>

        {hasChildren && (
          <button
            type="button"
            className={`cv-node-expand-btn ${
              isExpanded ? 'cv-node-expand-btn--expanded' : 'cv-node-expand-btn--collapsed'
            }`}
            onClick={handleExpandClick}
            title={isExpanded ? 'Collapse branch dependencies' : `Expand ${childCount} dependencies`}
            aria-label={isExpanded ? 'Collapse branch' : 'Expand branch'}
          >
            {isExpanded ? (
              <>
                <ChevronDown size={11} />
                <span>-</span>
              </>
            ) : (
              <>
                <ChevronRight size={11} />
                <span>+{childCount}</span>
              </>
            )}
          </button>
        )}
      </div>

      {/* Primary Module / File Name */}
      <div className="cv-node-card__name" title={name}>
        {name}
      </div>

      {/* Secondary File Path */}
      <div className="cv-node-card__path" title={path}>
        {path}
      </div>

      {/* Footer Metrics */}
      <div className="cv-node-card__footer">
        {lines > 0 && (
          <span className="cv-node-card__metric">
            {lines} LOC
          </span>
        )}
        <span className="cv-node-card__metric">
          {childCount} deps · {parentCount} in
        </span>
      </div>
    </div>
  );
}

export default memo(CodebaseNode);
