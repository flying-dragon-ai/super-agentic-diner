// Cafe primitives (Phase 5c). Adapted from Claw3D objects/primitives.tsx but
// decoupled from Claw3D's prop interfaces. DoorModel is an auto-opening cafe
// entrance door: the leaf swings open when any agent stands near it.
import { useFrame } from "@react-three/fiber";
import { useRef, type RefObject } from "react";
import * as THREE from "three";
import { DOOR_LENGTH, DOOR_THICKNESS, SCALE } from "../core/constants";
import { getItemRotationRadians, toWorld } from "../core/geometry";
import type { FurnitureItem, RenderAgent } from "../core/types";

export function DoorModel({
  item,
  agentsRef,
  isSelected = false,
  isHovered = false,
  editMode = false,
  onPointerDown,
  onPointerOver,
  onPointerOut,
}: {
  item: FurnitureItem;
  agentsRef: RefObject<RenderAgent[]>;
  isSelected?: boolean;
  isHovered?: boolean;
  editMode?: boolean;
  onPointerDown?: (event: THREE.Event) => void;
  onPointerOver?: (event: THREE.Event) => void;
  onPointerOut?: (event: THREE.Event) => void;
}) {
  const [wx, , wz] = toWorld(item.x, item.y);
  const width = (item.w ?? DOOR_LENGTH) * SCALE;
  const depth = Math.max((item.h ?? DOOR_THICKNESS) * SCALE, 0.04);
  const rotY = getItemRotationRadians(item);
  const active = isSelected || (editMode && isHovered);
  const handleX = width - 0.09;
  const handleZ = Math.max(depth * 0.28, 0.035);
  const leafPivotRef = useRef<THREE.Group>(null);
  const openAmountRef = useRef(0);

  useFrame(() => {
    if (!leafPivotRef.current) return;
    const centerX = wx + width / 2;
    const centerZ = wz + depth / 2;
    const cos = Math.cos(rotY);
    const sin = Math.sin(rotY);
    // Open when an agent is within a half-door-sized pad around the entrance.
    const touchPadX = width * 0.5 + 0.2;
    const touchPadZ = depth * 0.5 + 0.2;
    const shouldOpen = (agentsRef?.current ?? []).some((agent) => {
      const [ax, , az] = toWorld(agent.x, agent.y);
      const dx = ax - centerX;
      const dz = az - centerZ;
      const localX = dx * cos + dz * sin;
      const localZ = -dx * sin + dz * cos;
      return Math.abs(localX) <= touchPadX && Math.abs(localZ) <= touchPadZ;
    });
    const targetOpen = shouldOpen ? 1 : 0;
    openAmountRef.current = THREE.MathUtils.lerp(
      openAmountRef.current,
      targetOpen,
      0.14,
    );
    leafPivotRef.current.rotation.y = -openAmountRef.current * Math.PI * 0.55;
  });

  return (
    <group
      position={[wx, item.elevation ?? 0, wz]}
      onPointerDown={onPointerDown}
      onPointerOver={onPointerOver}
      onPointerOut={onPointerOut}
    >
      <group position={[width / 2, 0, depth / 2]} rotation={[0, rotY, 0]}>
        <mesh position={[0, 1.01, 0]}>
          <boxGeometry args={[width + 0.05, 0.08, depth + 0.04]} />
          <meshStandardMaterial color={active ? "#6b4b31" : "#4a3421"} roughness={0.88} />
        </mesh>
        <mesh position={[-width / 2 + 0.02, 0.5, 0]}>
          <boxGeometry args={[0.04, 1, depth + 0.03]} />
          <meshStandardMaterial color={active ? "#6b4b31" : "#4a3421"} roughness={0.88} />
        </mesh>
        <mesh position={[width / 2 - 0.02, 0.5, 0]}>
          <boxGeometry args={[0.04, 1, depth + 0.03]} />
          <meshStandardMaterial color={active ? "#6b4b31" : "#4a3421"} roughness={0.88} />
        </mesh>
        <group ref={leafPivotRef} position={[-width / 2 + 0.025, 0, 0]}>
          <mesh position={[width / 2 - 0.035, 0.5, 0]} receiveShadow>
            <boxGeometry args={[Math.max(width - 0.09, 0.08), 0.94, depth * 0.68]} />
            <meshStandardMaterial color={active ? "#a06d42" : "#7c5330"} roughness={0.74} />
          </mesh>
          <mesh position={[handleX, 0.52, 0]}>
            <cylinderGeometry args={[0.008, 0.008, handleZ * 2.1, 10]} />
            <meshStandardMaterial color="#9f8141" roughness={0.4} metalness={0.45} />
          </mesh>
          <mesh position={[handleX, 0.52, handleZ]}>
            <sphereGeometry args={[0.025, 12, 12]} />
            <meshStandardMaterial color="#d9bf72" roughness={0.36} metalness={0.35} />
          </mesh>
          <mesh position={[handleX, 0.52, -handleZ]}>
            <sphereGeometry args={[0.025, 12, 12]} />
            <meshStandardMaterial color="#d9bf72" roughness={0.36} metalness={0.35} />
          </mesh>
        </group>
      </group>
    </group>
  );
}
