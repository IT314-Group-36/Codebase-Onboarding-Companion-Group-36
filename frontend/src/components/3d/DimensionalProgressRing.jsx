import { useMemo } from 'react';
import './DimensionalProgressRing.css';

/**
 * DimensionalProgressRing — 3D Layered Milestone & Readiness Progress Visual
 *
 * Renders a dimensional progress ring with concentric metallic depth,
 * true milestone node indicators, liquid amber active arc, and precision readout.
 *
 * @param {Object} props
 * @param {number} props.progressPercent - Current progress 0..100
 * @param {number} props.totalTasks - Total number of onboarding milestones
 * @param {number} props.completedCount - Number of completed tasks
 * @param {number} [props.size=120] - Diameter in pixels
 */
export default function DimensionalProgressRing({
  progressPercent = 0,
  totalTasks = 6,
  completedCount = 0,
  size = 124,
}) {
  const strokeWidth = 10;
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (Math.max(0, Math.min(100, progressPercent)) / 100) * circumference;

  // Calculate 3D milestone node bead coordinates along the ring perimeter
  const milestoneBeads = useMemo(() => {
    if (totalTasks <= 0) return [];
    const beads = [];
    const center = size / 2;

    for (let i = 0; i < totalTasks; i++) {
      // Start from -90 degrees (12 o'clock)
      const angleDeg = -90 + (i / totalTasks) * 360;
      const angleRad = (angleDeg * Math.PI) / 180;
      const bx = center + radius * Math.cos(angleRad);
      const by = center + radius * Math.sin(angleRad);
      const isCompleted = i < completedCount;

      beads.push({
        id: i,
        x: bx,
        y: by,
        isCompleted,
      });
    }
    return beads;
  }, [totalTasks, completedCount, size, radius]);

  return (
    <div
      className="cv-dim-ring-wrapper"
      style={{ width: size, height: size }}
      role="progressbar"
      aria-valuenow={progressPercent}
      aria-valuemin="0"
      aria-valuemax="100"
      aria-label={`Onboarding readiness: ${progressPercent}% (${completedCount} of ${totalTasks} completed)`}
    >
      {/* 3D Drop Shadow & Ambient Floor Reflection */}
      <div className="cv-dim-ring-ambient-shadow" aria-hidden="true" />

      {/* SVG Multi-Layer Depth Ring */}
      <svg
        className="cv-dim-ring-svg"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
      >
        <defs>
          {/* Warm Amber active gradient */}
          <linearGradient id="cv-ring-amber-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FFB84D" />
            <stop offset="60%" stopColor="#F5A524" />
            <stop offset="100%" stopColor="#E08A0B" />
          </linearGradient>

          {/* Deep Dark Aurora recessed track gradient */}
          <linearGradient id="cv-ring-track-gradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#0E2E66" />
            <stop offset="100%" stopColor="#071226" />
          </linearGradient>

          {/* Metallic bead gradients */}
          <radialGradient id="cv-bead-active" cx="35%" cy="35%" r="65%">
            <stop offset="0%" stopColor="#FFEAD8" />
            <stop offset="45%" stopColor="#F5A524" />
            <stop offset="100%" stopColor="#703E1C" />
          </radialGradient>

          <radialGradient id="cv-bead-inactive" cx="35%" cy="35%" r="65%">
            <stop offset="0%" stopColor="#4C9AFF" />
            <stop offset="50%" stopColor="#0E2E66" />
            <stop offset="100%" stopColor="#071226" />
          </radialGradient>

          {/* Outer bezel shadow */}
          <filter id="cv-ring-bevel" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#000000" floodOpacity="0.5" />
          </filter>
        </defs>

        {/* Outer Bezel Circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius + strokeWidth / 2 + 2}
          fill="none"
          stroke="rgba(76, 154, 255, 0.22)"
          strokeWidth="1.2"
        />

        {/* Recessed Track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="url(#cv-ring-track-gradient)"
          strokeWidth={strokeWidth}
        />

        {/* Inner Bezel Circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius - strokeWidth / 2 - 2}
          fill="none"
          stroke="rgba(76, 154, 255, 0.16)"
          strokeWidth="1.2"
        />

        {/* Active Amber Liquid Arc */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="url(#cv-ring-amber-gradient)"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="cv-dim-ring-arc"
          filter="url(#cv-ring-bevel)"
        />

        {/* 3D Milestone Beads along perimeter */}
        {milestoneBeads.map((bead) => (
          <g key={bead.id} className="cv-dim-bead-group">
            {/* Ambient drop shadow */}
            <circle
              cx={bead.x}
              cy={bead.y + 1}
              r={4}
              fill="rgba(0,0,0,0.4)"
            />
            {/* Metallic Bead Body */}
            <circle
              cx={bead.x}
              cy={bead.y}
              r={3.8}
              fill={bead.isCompleted ? 'url(#cv-bead-active)' : 'url(#cv-bead-inactive)'}
              stroke={bead.isCompleted ? '#FFB477' : '#3E434D'}
              strokeWidth="0.8"
            />
          </g>
        ))}
      </svg>

      {/* Center Readout */}
      <div className="cv-dim-ring-content">
        <span className="cv-dim-ring-val">{progressPercent}%</span>
        <span className="cv-dim-ring-sub">
          {completedCount}/{totalTasks}
        </span>
      </div>
    </div>
  );
}
