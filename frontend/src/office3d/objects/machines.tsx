// Cafe procedural machines (Phase 5a). Self-contained Three.js geometry — no
// Claw3D business coupling (skill installs, kanban, etc.). Selected from the
// Claw3D machines.tsx/kitchen.tsx/Jukebox.tsx ideas but retuned to cafe use:
// register ATM (self-checkout), vending (coffee/snacks), jukebox (background
// music with a spinning vinyl). Each takes a FurnitureItem + editor highlight.
import { Billboard, Text } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";
import { SCALE } from "../core/constants";
import {
  getItemBaseSize,
  getItemRotationRadians,
  toWorld,
} from "../core/geometry";
import type { FurnitureItem } from "../core/types";

type MachineProps = {
  item: FurnitureItem;
  isSelected?: boolean;
  isHovered?: boolean;
  onClick?: () => void;
};

// Register / self-checkout kiosk. Tall box with a screen, card slot, and a
// green status stripe; glow ring when selected.
export function AtmMachineModel({ item, isSelected = false, isHovered = false, onClick }: MachineProps) {
  const [wx, , wz] = toWorld(item.x, item.y);
  const { width, height } = getItemBaseSize(item);
  const rotY = getItemRotationRadians(item);
  const scaleX = (width * SCALE) / 0.9;
  const scaleZ = (height * SCALE) / 0.7;
  const highlight = isSelected || isHovered;
  return (
    <group position={[wx, 0, wz]} rotation={[0, rotY, 0]} scale={[scaleX, 1, scaleZ]} onClick={(e) => { e.stopPropagation(); onClick?.(); }}>
      <mesh position={[0, 1.0, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.8, 2.0, 0.6]} />
        <meshStandardMaterial color={highlight ? "#3a4a5a" : "#2c3a48"} roughness={0.6} metalness={0.2} />
      </mesh>
      <mesh position={[0, 1.45, 0.31]}>
        <planeGeometry args={[0.55, 0.4]} />
        <meshStandardMaterial color="#0a2a3a" emissive="#1aa3ff" emissiveIntensity={highlight ? 0.6 : 0.3} />
      </mesh>
      <Billboard position={[0, 1.45, 0.33]} follow={false}>
        <Text fontSize={0.07} color="#bfe6ff" anchorX="center" anchorY="middle" maxWidth={0.5} textAlign="center">
          自助点单
        </Text>
      </Billboard>
      <mesh position={[0, 0.9, 0.31]}>
        <boxGeometry args={[0.5, 0.04, 0.02]} />
        <meshStandardMaterial color="#1a1a1a" roughness={0.4} metalness={0.5} />
      </mesh>
      <mesh position={[0.3, 0.75, 0.31]}>
        <boxGeometry args={[0.12, 0.03, 0.03]} />
        <meshStandardMaterial color="#0a0a0a" />
      </mesh>
      <mesh position={[0, 0.3, 0.31]}>
        <boxGeometry args={[0.4, 0.02, 0.02]} />
        <meshStandardMaterial color="#1aa35a" emissive="#1aa35a" emissiveIntensity={0.4} />
      </mesh>
      {isSelected && (
        <mesh position={[0, 1.0, 0]}>
          <torusGeometry args={[0.5, 0.03, 12, 48]} />
          <meshStandardMaterial color="#fbbf24" emissive="#fbbf24" emissiveIntensity={1} />
        </mesh>
      )}
    </group>
  );
}

// Vending machine for coffee beans / snacks. Glass front with glowing product
// rows + a dispense slot at the bottom.
export function VendingMachineModel({ item, isSelected = false, isHovered = false, onClick }: MachineProps) {
  const [wx, , wz] = toWorld(item.x, item.y);
  const { width, height } = getItemBaseSize(item);
  const rotY = getItemRotationRadians(item);
  const scaleX = (width * SCALE) / 0.9;
  const scaleZ = (height * SCALE) / 0.7;
  const highlight = isSelected || isHovered;
  const productColors = ["#c97b3a", "#e0c060", "#8a5a2a", "#b5651d", "#d9a06b", "#a0522d"];
  return (
    <group position={[wx, 0, wz]} rotation={[0, rotY, 0]} scale={[scaleX, 1, scaleZ]} onClick={(e) => { e.stopPropagation(); onClick?.(); }}>
      <mesh position={[0, 1.1, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.9, 2.2, 0.65]} />
        <meshStandardMaterial color={highlight ? "#3a3f48" : "#2a2f38"} roughness={0.55} metalness={0.25} />
      </mesh>
      <mesh position={[0, 1.3, 0.33]}>
        <planeGeometry args={[0.7, 1.4]} />
        <meshStandardMaterial color="#10202a" roughness={0.1} metalness={0.2} transparent opacity={0.85} />
      </mesh>
      {[0, 1, 2].map((row) =>
        [0, 1].map((col) => (
          <mesh key={`${row}-${col}`} position={[-0.22 + col * 0.44, 0.9 + row * 0.4, 0.34]}>
            <boxGeometry args={[0.3, 0.22, 0.05]} />
            <meshStandardMaterial
              color={productColors[(row * 2 + col) % productColors.length]}
              emissive={productColors[(row * 2 + col) % productColors.length]}
              emissiveIntensity={0.25}
            />
          </mesh>
        )),
      )}
      <mesh position={[0, 0.35, 0.34]}>
        <boxGeometry args={[0.6, 0.18, 0.04]} />
        <meshStandardMaterial color="#050505" />
      </mesh>
      {isSelected && (
        <mesh position={[0, 1.1, 0]}>
          <torusGeometry args={[0.55, 0.03, 12, 48]} />
          <meshStandardMaterial color="#fbbf24" emissive="#fbbf24" emissiveIntensity={1} />
        </mesh>
      )}
    </group>
  );
}

// Cafe jukebox: teak cabinet with a spinning vinyl, neon display, and a pulsing
// point light when "playing". Adapted from Claw3D's Jukebox (decoupled from the
// soundclaw skill + InteractiveFurnitureModelProps).
const JUKEBOX_BUTTONS = ["#FF0000", "#FFFF00", "#00FF00", "#00FFFF", "#FF00FF"];
export function JukeboxModel({ item, isSelected = false, isHovered = false, onClick }: MachineProps) {
  const recordRef = useRef<THREE.Mesh>(null);
  const glowRef = useRef<THREE.PointLight>(null);
  const [wx, , wz] = toWorld(item.x, item.y);
  const { width, height } = getItemBaseSize(item);
  const rotY = getItemRotationRadians(item);
  const scaleX = (width * SCALE) / 0.9;
  const scaleZ = (height * SCALE) / 0.7;
  const highlight = isSelected || isHovered;

  useFrame((state, delta) => {
    if (recordRef.current) recordRef.current.rotation.y += delta * 2;
    if (glowRef.current) {
      const pulse = Math.sin(state.clock.elapsedTime * 4) * 0.3 + 0.7;
      glowRef.current.intensity = pulse * 2;
    }
  });

  return (
    <group position={[wx, 0, wz]} rotation={[0, rotY, 0]} scale={[scaleX, 1, scaleZ]} onClick={(e) => { e.stopPropagation(); onClick?.(); }}>
      <mesh position={[0, 0.75, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.8, 1.2, 0.6]} />
        <meshStandardMaterial color={highlight ? "#0f9a8e" : "#0d9488"} roughness={0.6} metalness={0.1} />
      </mesh>
      <mesh position={[0, 1.4, 0]} castShadow>
        <cylinderGeometry args={[0.45, 0.5, 0.2, 32]} />
        <meshStandardMaterial color="#0f766e" roughness={0.5} metalness={0.2} />
      </mesh>
      <mesh position={[0, 1.55, 0]} castShadow>
        <sphereGeometry args={[0.15, 16, 16, 0, Math.PI * 2, 0, Math.PI / 2]} />
        <meshStandardMaterial color="#e2e8f0" roughness={0.3} metalness={0.8} />
      </mesh>
      <mesh position={[0, 1.1, 0.31]}>
        <planeGeometry args={[0.6, 0.35]} />
        <meshStandardMaterial color="#042f2e" emissive="#FF1493" emissiveIntensity={highlight ? 0.5 : 0.2} />
      </mesh>
      <Billboard position={[0, 1.1, 0.32]} follow={false}>
        <Text fontSize={0.07} color="#00FF00" anchorX="center" anchorY="middle" maxWidth={0.55} textAlign="center">
          ♪ NOW PLAYING
        </Text>
      </Billboard>
      <mesh position={[0, 0.7, 0.31]}>
        <planeGeometry args={[0.52, 0.38]} />
        <meshStandardMaterial color="#042f2e" roughness={0.9} metalness={0.1} />
      </mesh>
      {[-0.14, -0.07, 0, 0.07, 0.14].map((y) => (
        <mesh key={y} position={[0, 0.7 + y, 0.315]}>
          <boxGeometry args={[0.48, 0.01, 0.005]} />
          <meshStandardMaterial color="#94a3b8" metalness={0.6} roughness={0.4} />
        </mesh>
      ))}
      <mesh ref={recordRef} position={[0, 0.75, 0.315]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.1, 0.1, 0.008, 32]} />
        <meshStandardMaterial color="#0a0a0a" roughness={0.6} metalness={0.3} />
      </mesh>
      <mesh position={[0, 0.75, 0.32]} rotation={[Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.04, 32]} />
        <meshStandardMaterial color="#FF1493" emissive="#FF1493" emissiveIntensity={0.6} />
      </mesh>
      <group position={[0, 0.5, 0.31]}>
        {JUKEBOX_BUTTONS.map((color, i) => (
          <mesh key={i} position={[-0.15 + i * 0.075, 0, 0.01]}>
            <cylinderGeometry args={[0.025, 0.025, 0.02, 16]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.5} />
          </mesh>
        ))}
      </group>
      <mesh position={[0, 0.05, 0]} receiveShadow>
        <boxGeometry args={[0.9, 0.1, 0.7]} />
        <meshStandardMaterial color="#0f766e" roughness={0.7} metalness={0.1} />
      </mesh>
      <pointLight ref={glowRef} position={[0, 1.2, 0.5]} color="#00FF00" intensity={1} distance={3} />
      {isSelected && (
        <mesh position={[0, 0.75, 0]}>
          <torusGeometry args={[0.52, 0.03, 12, 48]} />
          <meshStandardMaterial color="#fbbf24" emissive="#fbbf24" emissiveIntensity={1} />
        </mesh>
      )}
    </group>
  );
}

// Resolver: map a furniture type to its procedural machine, or null if it should
// fall back to the standard GLB FurnitureModel.
export const MACHINE_TYPES = new Set(["atm", "vending", "jukebox"]);
export function resolveMachine(item: FurnitureItem) {
  switch (item.type) {
    case "atm":
      return AtmMachineModel;
    case "vending":
      return VendingMachineModel;
    case "jukebox":
      return JukeboxModel;
    default:
      return null;
  }
}
