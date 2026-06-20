// Simplified port of Claw3D retro-office scene/environment.tsx.
// Single local office floor + walls only (no remote-office district, no city path).
import { memo } from "react";
import { Text } from "@react-three/drei";
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
