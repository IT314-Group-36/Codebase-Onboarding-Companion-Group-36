import { memo } from 'react';
import './CosmicBackground.css';

/**
 * Dark Aurora Ambient Lighting Backdrop
 *
 * Provides deep-space black (#02060F) with layered, diffused
 * electric-blue (#1F6FEB), midnight-blue (#0E2E66), and warm amber (#F5A524)
 * ambient illumination spreading through the dark environment.
 *
 * @param {'full'|'medium'|'subtle'} intensity
 */
function CosmicBackground({ intensity = 'medium' }) {
  return (
    <div className={`cv-aurora-backdrop cv-aurora-backdrop--${intensity}`} aria-hidden="true">
      {/* Base deep-space black layer */}
      <div className="cv-aurora-base" />

      {/* Layer 1: Diffuse Midnight Blue top ambient source */}
      <div className="cv-aurora-light cv-aurora-light--top" />

      {/* Layer 2: Electric Blue side glow */}
      <div className="cv-aurora-light cv-aurora-light--electric" />

      {/* Layer 3: Restrained Warm Amber ambient accent */}
      <div className="cv-aurora-light cv-aurora-light--amber" />

      {/* Layer 4: Deep lower-left blue atmosphere */}
      <div className="cv-aurora-light cv-aurora-light--bottom" />

      {/* Soft gradient sheen overlay */}
      <div className="cv-aurora-overlay" />
    </div>
  );
}

export default memo(CosmicBackground);
export { CosmicBackground as AuroraBackground };
