// Simplified port of Claw3D retro-office scene/environment.tsx.
// Single local office floor + walls only (no remote-office district, no city path).
import { memo, useMemo, useRef } from "react";
import { Text } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { CANVAS_H, CANVAS_W, SCALE } from "../core/constants";
import { toWorld } from "../core/geometry";

export const FloorAndWalls = memo(function FloorAndWalls() {
  const width = CANVAS_W * SCALE;
  const height = CANVAS_H * SCALE;
  const [cx, , cz] = toWorld(CANVAS_W / 2, CANVAS_H / 2);
  const northZ = cz - height / 2;
  const southZ = cz + height / 2;
  const westX = cx - width / 2;
  const eastX = cx + width / 2;
  const wallColor = "#795548";
  const wallEmissive = "#4e342e";

  return (
    <group>
      <mesh position={[cx, -0.015, cz]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[width, height, 24, 14]} />
        <meshStandardMaterial color="#263238" roughness={0.98} metalness={0.02} />
      </mesh>
      <mesh position={[cx, -0.012, cz]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[width * 0.95, height * 0.9]} />
        <meshStandardMaterial color="#1b232a" roughness={0.96} metalness={0.04} />
      </mesh>
      <mesh position={[cx, 0, cz]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[width, height, 22, 14]} />
        <meshLambertMaterial color="#c8a97e" />
      </mesh>
      {Array.from({ length: 18 }).map((_, index) => {
        const z = northZ + (index + 1) * (height / 18);
        return (
          <mesh key={`floor-line-${index}`} position={[cx, 0.001, z]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[width, 0.008]} />
            <meshBasicMaterial color="#a07850" transparent opacity={0.25} />
          </mesh>
        );
      })}
      <mesh position={[cx, 0.5, northZ]} receiveShadow>
        <boxGeometry args={[width, 1, 0.12]} />
        <meshStandardMaterial color={wallColor} emissive={wallEmissive} emissiveIntensity={0.5} roughness={0.9} />
      </mesh>
      <mesh position={[cx, 0.5, southZ]} receiveShadow>
        <boxGeometry args={[width, 1, 0.12]} />
        <meshStandardMaterial color={wallColor} emissive={wallEmissive} emissiveIntensity={0.5} roughness={0.9} />
      </mesh>
      <mesh position={[westX, 0.5, cz]} receiveShadow>
        <boxGeometry args={[0.12, 1, height]} />
        <meshStandardMaterial color={wallColor} emissive={wallEmissive} emissiveIntensity={0.5} roughness={0.9} />
      </mesh>
      <mesh position={[eastX, 0.5, cz]} receiveShadow>
        <boxGeometry args={[0.12, 1, height]} />
        <meshStandardMaterial color={wallColor} emissive={wallEmissive} emissiveIntensity={0.5} roughness={0.9} />
      </mesh>
    </group>
  );
});

const EVOMAP_NODE_POINTS = [
  { x: 250, y: 120, color: "#22d3ee" },
  { x: 520, y: 255, color: "#34d399" },
  { x: 840, y: 145, color: "#60a5fa" },
  { x: 1120, y: 320, color: "#a78bfa" },
  { x: 1390, y: 210, color: "#22d3ee" },
  { x: 1580, y: 470, color: "#34d399" },
  { x: 1125, y: 560, color: "#60a5fa" },
  { x: 760, y: 480, color: "#22d3ee" },
  { x: 420, y: 585, color: "#a78bfa" },
];

const EVOMAP_NODE_LINKS = [
  [0, 1],
  [1, 2],
  [2, 3],
  [3, 4],
  [4, 5],
  [5, 6],
  [6, 7],
  [7, 8],
  [1, 7],
  [2, 6],
  [3, 7],
];

function EvoMapNode({
  x,
  z,
  color,
  delay,
}: {
  x: number;
  z: number;
  color: string;
  delay: number;
}) {
  const ref = useRef<THREE.Group>(null);

  useFrame(({ clock }) => {
    if (!ref.current) return;
    const pulse = 1 + Math.sin(clock.elapsedTime * 1.6 + delay) * 0.12;
    ref.current.scale.setScalar(pulse);
  });

  return (
    <group ref={ref} position={[x, 0.032, z]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.075, 24]} />
        <meshBasicMaterial color={color} transparent opacity={0.35} depthWrite={false} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.1, 0.125, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.5} depthWrite={false} />
      </mesh>
      <pointLight color={color} intensity={0.22} distance={1.35} />
    </group>
  );
}

function EvoMapLink({
  from,
  to,
}: {
  from: THREE.Vector3;
  to: THREE.Vector3;
}) {
  const dx = to.x - from.x;
  const dz = to.z - from.z;
  const length = Math.hypot(dx, dz);
  const angle = -Math.atan2(dz, dx);

  return (
    <group position={[(from.x + to.x) / 2, 0.018, (from.z + to.z) / 2]} rotation={[0, angle, 0]}>
      <mesh>
        <boxGeometry args={[length, 0.006, 0.018]} />
        <meshBasicMaterial color="#4dd8ff" transparent opacity={0.22} depthWrite={false} />
      </mesh>
    </group>
  );
}

function EvoMapWallPlaque() {
  const [cx, , cz] = toWorld(CANVAS_W / 2, CANVAS_H / 2);
  const northZ = cz - (CANVAS_H * SCALE) / 2;

  return (
    <group position={[cx, 1.42, northZ + 0.08]}>
      <mesh>
        <planeGeometry args={[2.35, 0.72]} />
        <meshStandardMaterial
          color="#07111a"
          emissive="#0c2f45"
          emissiveIntensity={0.7}
          roughness={0.55}
          metalness={0.18}
          transparent
          opacity={0.92}
        />
      </mesh>
      <Text position={[0, 0.09, 0.012]} fontSize={0.15} color="#f8fbff" anchorX="center" anchorY="middle">
        Crossroads Agent Café
      </Text>
      <Text position={[0, -0.25, 0.012]} fontSize={0.085} color="#8be9ff" anchorX="center" anchorY="middle">
        Experience Network · Cafe Runtime
      </Text>
      <mesh position={[-1.06, 0, 0.018]} rotation={[0, 0, Math.PI / 4]}>
        <ringGeometry args={[0.08, 0.11, 4]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.85} />
      </mesh>
      <mesh position={[1.06, 0, 0.018]} rotation={[0, 0, Math.PI / 4]}>
        <ringGeometry args={[0.08, 0.11, 4]} />
        <meshBasicMaterial color="#34d399" transparent opacity={0.85} />
      </mesh>
    </group>
  );
}

// EvoMap-inspired material layer: ambient network graph, slow rotating rings,
// and a wall terminal. This mirrors the collected EvoMap site language without
// copying blog artwork into the product scene.
export function EvoMapAmbientLayer() {
  const ringRef = useRef<THREE.Group>(null);
  const nodeWorld = useMemo(
    () =>
      EVOMAP_NODE_POINTS.map((point) => {
        const [x, , z] = toWorld(point.x, point.y);
        return { ...point, world: new THREE.Vector3(x, 0, z) };
      }),
    [],
  );

  useFrame(({ clock }) => {
    if (!ringRef.current) return;
    ringRef.current.rotation.y = -clock.elapsedTime * 0.035;
  });

  return (
    <group>
      {EVOMAP_NODE_LINKS.map(([from, to], index) => (
        <EvoMapLink key={`evomap-link-${index}`} from={nodeWorld[from].world} to={nodeWorld[to].world} />
      ))}
      {nodeWorld.map((node, index) => (
        <EvoMapNode
          key={`evomap-node-${index}`}
          x={node.world.x}
          z={node.world.z}
          color={node.color}
          delay={index * 0.65}
        />
      ))}
      <group ref={ringRef} position={[0, 0.026, 0]}>
        {[1.85, 2.65, 3.45].map((radius, index) => (
          <mesh key={radius} rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[radius, 0.006 + index * 0.002, 8, 128]} />
            <meshBasicMaterial
              color={index === 1 ? "#34d399" : "#22d3ee"}
              transparent
              opacity={index === 1 ? 0.16 : 0.11}
              depthWrite={false}
            />
          </mesh>
        ))}
      </group>
      <EvoMapWallPlaque />
    </group>
  );
}

// Cafe wall menu board (Phase 5c). A framed chalkboard-style panel with the
// coffee menu drawn procedurally — adapted from Claw3D's FramedPicture concept
// but retuned to cafe content (no flags / VSCode art).
const MENU_ITEMS = [
  { name: "Espresso", price: "¥18" },
  { name: "Latte", price: "¥25" },
  { name: "Cappuccino", price: "¥24" },
  { name: "Mocha", price: "¥28" },
  { name: "Cold Brew", price: "¥26" },
];

export function MenuBoardArt({
  position,
  rotation = [0, 0, 0],
}: {
  position: [number, number, number];
  rotation?: [number, number, number];
}) {
  return (
    <group position={position} rotation={rotation}>
      <mesh castShadow>
        <boxGeometry args={[1.8, 1.1, 0.06]} />
        <meshStandardMaterial color="#5d3a1a" roughness={0.6} metalness={0.1} />
      </mesh>
      <mesh position={[0, 0, 0.035]}>
        <planeGeometry args={[1.6, 0.92]} />
        <meshStandardMaterial color="#1f2a24" roughness={0.95} />
      </mesh>
      <Text position={[0, 0.34, 0.04]} fontSize={0.12} color="#f0c060" anchorX="center" anchorY="middle">
        ☕ MENU
      </Text>
      {MENU_ITEMS.map((item, i) => (
        <Text
          key={item.name}
          position={[-0.2, 0.16 - i * 0.14, 0.04]}
          fontSize={0.08}
          color="#e8dfc0"
          anchorX="center"
          anchorY="middle"
        >
          {item.name}
        </Text>
      ))}
      {MENU_ITEMS.map((item, i) => (
        <Text
          key={`${item.name}-price`}
          position={[0.5, 0.16 - i * 0.14, 0.04]}
          fontSize={0.08}
          color="#f0c060"
          anchorX="center"
          anchorY="middle"
        >
          {item.price}
        </Text>
      ))}
    </group>
  );
}

// Hanging warm-glow pendant lights strung across the cafe ceiling for ambience
// (Phase 5c). Small emissive spheres on a thin cable — cheap, no shadow cost.
export function CafePendantLights() {
  const [, , cz] = toWorld(CANVAS_W / 2, CANVAS_H / 2);
  const spacing = (CANVAS_W * SCALE) / 5;
  const startX = -((CANVAS_W * SCALE) / 2) + spacing * 0.5;
  return (
    <group>
      {Array.from({ length: 5 }).map((_, i) => {
        const x = startX + i * spacing;
        return (
          <group key={i} position={[x, 2.4, cz - 1]}>
            <mesh position={[0, -0.25, 0]}>
              <cylinderGeometry args={[0.005, 0.005, 0.5, 6]} />
              <meshStandardMaterial color="#222" />
            </mesh>
            <mesh position={[0, -0.5, 0]}>
              <coneGeometry args={[0.12, 0.16, 16, 1, true]} />
              <meshStandardMaterial color="#3a2a1a" roughness={0.6} side={2} />
            </mesh>
            <mesh position={[0, -0.52, 0]}>
              <sphereGeometry args={[0.07, 12, 12]} />
              <meshStandardMaterial color="#fff0c0" emissive="#ffcf6a" emissiveIntensity={1.6} />
            </mesh>
            <pointLight position={[0, -0.6, 0]} color="#ffcf6a" intensity={0.5} distance={3.5} />
          </group>
        );
      })}
    </group>
  );
}
