import { useEffect, useRef, useState } from 'react';
import './LiquidChromeOrb.css';

/**
 * LiquidChromeOrb — Signature 3D Liquid-Metal Artifact
 *
 * Renders an abstract sculptural liquid-chrome object using high-performance
 * native WebGL raymarching.
 * Features:
 * - Fluid surface displacement with metallic reflection.
 * - Restrained warm amber fresnel rim highlights (#FF9B54).
 * - Gentle pointer tilt and slow, steady rotation (28s/revolution).
 * - Pauses automatically when tab is hidden or element is scrolled out of view.
 * - Detects `prefers-reduced-motion` and falls back gracefully.
 * - Full 2D/CSS fallback if WebGL is unsupported.
 */

// Vertex Shader: simple full-screen quad
const VS_SOURCE = `
  attribute vec2 a_position;
  varying vec2 v_uv;
  void main() {
    v_uv = a_position * 0.5 + 0.5;
    gl_Position = vec4(a_position, 0.0, 1.0);
  }
`;

// Fragment Shader: Raymarched liquid-metal sphere with dynamic surface ripple & amber specular fresnel
const FS_SOURCE = `
  precision mediump float;
  varying vec2 v_uv;
  uniform vec2 u_resolution;
  uniform float u_time;
  uniform vec2 u_mouse;
  uniform float u_reduced_motion;

  // Rotation matrix around Y axis
  mat3 rotateY(float angle) {
    float c = cos(angle);
    float s = sin(angle);
    return mat3(
      c, 0.0, s,
      0.0, 1.0, 0.0,
      -s, 0.0, c
    );
  }

  // Rotation matrix around X axis
  mat3 rotateX(float angle) {
    float c = cos(angle);
    float s = sin(angle);
    return mat3(
      1.0, 0.0, 0.0,
      0.0, c, -s,
      0.0, s, c
    );
  }

  // Signed distance field of a liquid displaced sphere
  float map(vec3 p) {
    float baseSphere = length(p) - 0.76;
    if (u_reduced_motion > 0.5) {
      return baseSphere;
    }

    // Fluid surface harmonics
    float t = u_time * 0.45;
    float disp = 0.045 * sin(p.x * 4.2 + t) * cos(p.y * 4.0 + t * 0.8) * sin(p.z * 4.5 + t * 1.2);
    disp += 0.02 * sin(p.x * 8.0 - t * 1.5) * sin(p.y * 7.5 + t);
    return baseSphere + disp;
  }

  // Calculate surface normal via central difference
  vec3 calcNormal(vec3 p) {
    float eps = 0.003;
    vec2 e = vec2(eps, 0.0);
    return normalize(vec3(
      map(p + e.xyy) - map(p - e.xyy),
      map(p + e.yxy) - map(p - e.yxy),
      map(p + e.yyx) - map(p - e.yyx)
    ));
  }

  void main() {
    // Normalize coordinates [-1, 1], aspect corrected
    vec2 p = (gl_FragCoord.xy * 2.0 - u_resolution.xy) / min(u_resolution.x, u_resolution.y);

    // Camera setup
    vec3 ro = vec3(0.0, 0.0, 2.2);
    vec3 rd = normalize(vec3(p, -1.6));

    // Pointer response & slow ambient rotation (approx 28s/rev)
    float rotY = (u_time * 0.22) + (u_mouse.x * 0.6);
    float rotX = (-u_mouse.y * 0.4);

    mat3 rot = rotateY(rotY) * rotateX(rotX);
    ro = rot * ro;
    rd = rot * rd;

    // Raymarching loop
    float t = 0.0;
    float maxDist = 3.5;
    float hit = 0.0;

    for (int i = 0; i < 48; i++) {
      vec3 pos = ro + rd * t;
      float d = map(pos);
      if (d < 0.001) {
        hit = 1.0;
        break;
      }
      t += d;
      if (t > maxDist) break;
    }

    if (hit > 0.5) {
      vec3 pos = ro + rd * t;
      vec3 normal = calcNormal(pos);
      vec3 viewDir = -rd;

      // Lights: Key light (cool silver) and warm amber fill/rim light
      vec3 keyLightDir = normalize(vec3(0.5, 0.9, 0.8));
      vec3 amberLightDir = normalize(vec3(-0.7, -0.4, 0.6));

      // Diffuse & Specular components
      float diff = max(dot(normal, keyLightDir), 0.0);
      vec3 halfVec = normalize(keyLightDir + viewDir);
      float spec = pow(max(dot(normal, halfVec), 0.0), 38.0);

      // Liquid chrome environment reflection approximation
      vec3 refl = reflect(rd, normal);
      float envReflection = pow(refl.y * 0.5 + 0.5, 2.0) * 0.6;

      // Fresnel rim reflection
      float fresnel = pow(1.0 - max(dot(normal, viewDir), 0.0), 3.0);

      // Base dark aurora liquid metal: Electric Blue key illumination (#1F6FEB), Soft Blue highlights
      vec3 baseMetal = vec3(0.40, 0.55, 0.75) * (diff * 0.5 + 0.28);
      baseMetal += vec3(0.85, 0.92, 1.0) * spec * 0.95;
      baseMetal += vec3(0.19, 0.37, 0.60) * envReflection;

      // Warm Amber glow on rim & secondary reflection (#F5A524)
      vec3 amberRimColor = vec3(0.65, 0.42, 0.26); // #F5A524
      float amberRimStrength = fresnel * 0.75 + max(dot(normal, amberLightDir), 0.0) * 0.25;

      vec3 finalColor = mix(baseMetal, amberRimColor, amberRimStrength * 0.65);
      finalColor += amberRimColor * (fresnel * 0.45);

      // Subtle ambient occlusion in valleys
      finalColor *= clamp(1.0 - (0.76 - length(pos)) * 4.0, 0.65, 1.0);

      gl_FragColor = vec4(finalColor, 1.0);
    } else {
      // Transparent background so graphite canvas breathes through
      gl_FragColor = vec4(0.0, 0.0, 0.0, 0.0);
    }
  }
`;

export default function LiquidChromeOrb({
  size = 140,
  className = '',
  label = 'Interactive Liquid Chrome Core',
}) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const [webglSupported, setWebglSupported] = useState(true);
  const mouseRef = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });
  const isHoveredRef = useRef(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Check prefers-reduced-motion
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    let reducedMotion = mediaQuery.matches ? 1.0 : 0.0;

    const handleMotionChange = (e) => {
      reducedMotion = e.matches ? 1.0 : 0.0;
    };
    mediaQuery.addEventListener('change', handleMotionChange);

    // Initialize WebGL
    const gl =
      canvas.getContext('webgl', { alpha: true, antialias: true, powerPreference: 'low-power' }) ||
      canvas.getContext('experimental-webgl', { alpha: true, antialias: true });

    if (!gl) {
      setWebglSupported(false);
      return;
    }

    // Helper: Compile Shader
    function compileShader(type, source) {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.warn('Shader compilation error:', gl.getShaderInfoLog(shader));
        gl.deleteShader(shader);
        return null;
      }
      return shader;
    }

    const vs = compileShader(gl.VERTEX_SHADER, VS_SOURCE);
    const fs = compileShader(gl.FRAGMENT_SHADER, FS_SOURCE);
    if (!vs || !fs) {
      setWebglSupported(false);
      return;
    }

    const program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);

    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.warn('Program link error:', gl.getProgramInfoLog(program));
      setWebglSupported(false);
      return;
    }

    gl.useProgram(program);

    // Quad geometry [-1, -1] to [1, 1]
    const quadVertices = new Float32Array([
      -1.0, -1.0,
       1.0, -1.0,
      -1.0,  1.0,
      -1.0,  1.0,
       1.0, -1.0,
       1.0,  1.0,
    ]);

    const vbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    gl.bufferData(gl.ARRAY_BUFFER, quadVertices, gl.STATIC_DRAW);

    const posAttr = gl.getAttribLocation(program, 'a_position');
    gl.enableVertexAttribArray(posAttr);
    gl.vertexAttribPointer(posAttr, 2, gl.FLOAT, false, 0, 0);

    // Uniform locations
    const uResolution = gl.getUniformLocation(program, 'u_resolution');
    const uTime = gl.getUniformLocation(program, 'u_time');
    const uMouse = gl.getUniformLocation(program, 'u_mouse');
    const uReducedMotion = gl.getUniformLocation(program, 'u_reduced_motion');

    let animId = null;
    let startTime = performance.now();
    let isVisible = true;

    // Resize handler
    const updateSize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = canvas.clientWidth || size;
      const height = canvas.clientHeight || size;
      const targetW = Math.round(width * dpr);
      const targetH = Math.round(height * dpr);

      if (canvas.width !== targetW || canvas.height !== targetH) {
        canvas.width = targetW;
        canvas.height = targetH;
        gl.viewport(0, 0, targetW, targetH);
      }
    };
    updateSize();

    // IntersectionObserver to pause rendering when offscreen
    const observer = new IntersectionObserver(
      ([entry]) => {
        isVisible = entry.isIntersecting && document.visibilityState === 'visible';
      },
      { threshold: 0.05 }
    );
    if (containerRef.current) {
      observer.observe(containerRef.current);
    }

    const handleVisibilityChange = () => {
      isVisible = document.visibilityState === 'visible';
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    // Render loop
    const render = (now) => {
      animId = requestAnimationFrame(render);

      if (!isVisible) return;

      const elapsed = (now - startTime) * 0.001;

      // Smooth mouse interpolation
      const mouse = mouseRef.current;
      mouse.x += (mouse.targetX - mouse.x) * 0.08;
      mouse.y += (mouse.targetY - mouse.y) * 0.08;

      gl.useProgram(program);
      gl.uniform2f(uResolution, canvas.width, canvas.height);
      gl.uniform1f(uTime, elapsed);
      gl.uniform2f(uMouse, mouse.x, mouse.y);
      gl.uniform1f(uReducedMotion, reducedMotion);

      gl.drawArrays(gl.TRIANGLES, 0, 6);
    };

    animId = requestAnimationFrame(render);

    // Cleanup
    return () => {
      if (animId) cancelAnimationFrame(animId);
      observer.disconnect();
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      mediaQuery.removeEventListener('change', handleMotionChange);

      if (gl) {
        gl.deleteBuffer(vbo);
        gl.deleteProgram(program);
        gl.deleteShader(vs);
        gl.deleteShader(fs);
      }
    };
  }, [size]);

  // Pointer tracking
  const handleMouseMove = (e) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width - 0.5;
    const y = (e.clientY - rect.top) / rect.height - 0.5;
    mouseRef.current.targetX = x * 2.0;
    mouseRef.current.targetY = y * 2.0;
  };

  const handleMouseEnter = () => {
    isHoveredRef.current = true;
  };

  const handleMouseLeave = () => {
    isHoveredRef.current = false;
    mouseRef.current.targetX = 0;
    mouseRef.current.targetY = 0;
  };

  return (
    <div
      ref={containerRef}
      className={`cv-liquid-chrome-container ${className}`}
      style={{ width: size, height: size }}
      onMouseMove={handleMouseMove}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      title={label}
      role="img"
      aria-label={label}
    >
      {webglSupported ? (
        <canvas
          ref={canvasRef}
          className="cv-liquid-chrome-canvas"
          style={{ width: size, height: size }}
        />
      ) : (
        /* Graceful CSS 3D metallic fallback */
        <div className="cv-liquid-chrome-fallback" style={{ width: size, height: size }}>
          <div className="cv-liquid-chrome-fallback__sphere" />
          <div className="cv-liquid-chrome-fallback__glow" />
        </div>
      )}
      <div className="cv-liquid-chrome-reflection" aria-hidden="true" />
    </div>
  );
}
