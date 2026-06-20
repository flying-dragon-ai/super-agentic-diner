// Adapted from Claw3D retro-office systems/cameraLighting.tsx.
// Keeps DayNightCycle (lights) and a fixed overview camera rig; drops the
// remote-office district camera constants in favor of local world-derived ones.
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";
import { WORLD_H, WORLD_W, DISTRICT_CAMERA_POSITION, DISTRICT_CAMERA_TARGET, DISTRICT_CAMERA_ZOOM } from "../core/constants";

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const parseHex = (color: string) => {
  const value = parseInt(color.slice(1), 16);
  return [(value >> 16) & 0xff, (value >> 8) & 0xff, value & 0xff];
};
const lerpColor = (fromColor: string, toColor: string, t: number) => {
  const [r1, g1, b1] = parseHex(fromColor);
  const [r2, g2, b2] = parseHex(toColor);
  return `rgb(${Math.round(lerp(r1, r2, t))},${Math.round(lerp(g1, g2, t))},${Math.round(lerp(b1, b2, t))})`;
};

const DAY_NIGHT_PERIOD = 300;
const DAY_NIGHT_POSITIONS = [0, 0.2, 0.45, 0.65, 0.8, 0.95];
const DAY_NIGHT_KEYFRAMES = [
  { ambient: "#c8a870", sun: "#ffe8b0", sunIntensity: 0.8, ambientIntensity: 0.55 },
  { ambient: "#c8d0e0", sun: "#f0f4ff", sunIntensity: 1.3, ambientIntensity: 0.75 },
  { ambient: "#c8d0e0", sun: "#f0f4ff", sunIntensity: 1.3, ambientIntensity: 0.75 },
  { ambient: "#c87840", sun: "#ff9050", sunIntensity: 0.9, ambientIntensity: 0.5 },
  { ambient: "#1a2040", sun: "#2040a0", sunIntensity: 0.3, ambientIntensity: 0.25 },
  { ambient: "#101828", sun: "#182038", sunIntensity: 0.2, ambientIntensity: 0.2 },
];

export function DayNightCycle() {
  const ambientRef = useRef<THREE.AmbientLight>(null);
  const sunRef = useRef<THREE.DirectionalLight>(null);
  const timeRef = useRef(0.25);

  useFrame((_, delta) => {
    timeRef.current = (timeRef.current + delta / DAY_NIGHT_PERIOD) % 1;
    const time = timeRef.current;
    let indexA = 0;
    for (let index = 0; index < DAY_NIGHT_POSITIONS.length - 1; index += 1) {
      if (time >= DAY_NIGHT_POSITIONS[index] && time < DAY_NIGHT_POSITIONS[index + 1]) {
        indexA = index;
        break;
      }
      if (time >= DAY_NIGHT_POSITIONS[DAY_NIGHT_POSITIONS.length - 1]) {
        indexA = DAY_NIGHT_POSITIONS.length - 1;
      }
    }
    const indexB = (indexA + 1) % DAY_NIGHT_KEYFRAMES.length;
    const positionA = DAY_NIGHT_POSITIONS[indexA];
    const positionB = indexB === 0 ? 1 : DAY_NIGHT_POSITIONS[indexB];
    const span = positionB - positionA;
    const localT = span > 0 ? (time - positionA) / span : 0;
    const a = DAY_NIGHT_KEYFRAMES[indexA];
    const b = DAY_NIGHT_KEYFRAMES[indexB];
    if (ambientRef.current) {
      ambientRef.current.color.set(lerpColor(a.ambient, b.ambient, localT));
      ambientRef.current.intensity = lerp(a.ambientIntensity, b.ambientIntensity, localT);
    }
    if (sunRef.current) {
      sunRef.current.color.set(lerpColor(a.sun, b.sun, localT));
      sunRef.current.intensity = lerp(a.sunIntensity, b.sunIntensity, localT);
    }
  });

  return (
    <>
      <ambientLight ref={ambientRef} intensity={0.75} color="#c8d0e0" />
      <directionalLight
        ref={sunRef}
        position={[8, 14, 6]}
        intensity={1.3}
        color="#f0f4ff"
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-bias={-0.0002}
        shadow-normalBias={0.02}
        shadow-camera-left={-WORLD_W * 0.7}
        shadow-camera-right={WORLD_W * 0.7}
        shadow-camera-top={WORLD_H * 0.7}
        shadow-camera-bottom={-WORLD_H * 0.7}
      />
    </>
  );
}

// Overview camera positioned to frame the whole office floor.
export const OVERVIEW_CAMERA = DISTRICT_CAMERA_POSITION;
export const OVERVIEW_TARGET = DISTRICT_CAMERA_TARGET;
export const OVERVIEW_ZOOM = DISTRICT_CAMERA_ZOOM;
