// Procedural cafe machines for the 3D scene. These avoid GLB unit drift and
// give us one coherent coffee-equipment family that can be iterated quickly in
// code before investing in final dedicated assets.
import { Billboard, Text } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
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
  showLabel?: boolean;
};

export const COFFEE_MACHINE_TYPES = new Set([
  "coffee_machine",
  "coffee_machine_compact",
  "coffee_machine_grinder",
]);

const CUP_FILL_MAIN = "#6a3a1b";
const CUP_FILL_LIGHT = "#8a562d";
const METAL = "#d6dadd";
const METAL_DARK = "#868b90";

function getMachineTransform(
  item: FurnitureItem,
  referenceWidth: number,
  referenceDepth: number,
) {
  const [wx, , wz] = toWorld(item.x, item.y);
  const { width, height } = getItemBaseSize(item);
  return {
    wx,
    wz,
    rotY: getItemRotationRadians(item),
    scaleX: (width * SCALE) / referenceWidth,
    scaleZ: (height * SCALE) / referenceDepth,
  };
}

function SelectionRing({ active, radius, y = 0.03 }: { active: boolean; radius: number; y?: number }) {
  if (!active) return null;
  return (
    <mesh position={[0, y, 0]} rotation={[Math.PI / 2, 0, 0]}>
      <torusGeometry args={[radius, 0.025, 12, 48]} />
      <meshStandardMaterial color="#fbbf24" emissive="#fbbf24" emissiveIntensity={1} />
    </mesh>
  );
}

function MachineLabel({
  text,
  position,
}: {
  text: string;
  position: [number, number, number];
}) {
  return (
    <Billboard position={position} follow={false}>
      <mesh position={[0, 0, -0.006]}>
        <planeGeometry args={[0.62, 0.16]} />
        <meshBasicMaterial color="#111827" transparent opacity={0.78} depthWrite={false} />
      </mesh>
      <Text
        fontSize={0.065}
        color="#f8f4e8"
        outlineColor="#4a2e1b"
        outlineWidth={0.008}
        anchorX="center"
        anchorY="middle"
        maxWidth={0.8}
        textAlign="center"
      >
        {text}
      </Text>
    </Billboard>
  );
}

function CupProp({
  position,
  scale = 1,
  fill = CUP_FILL_MAIN,
}: {
  position: [number, number, number];
  scale?: number;
  fill?: string;
}) {
  return (
    <group position={position} scale={[scale, scale, scale]}>
      <mesh position={[0, 0.045, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[0.05, 0.043, 0.09, 18]} />
        <meshStandardMaterial color="#fbfaf7" roughness={0.35} metalness={0.04} />
      </mesh>
      <mesh position={[0, 0.082, 0]}>
        <cylinderGeometry args={[0.043, 0.043, 0.012, 18]} />
        <meshStandardMaterial color={fill} roughness={0.6} />
      </mesh>
      <mesh position={[0.048, 0.048, 0]} rotation={[0, 0, Math.PI / 2]}>
        <torusGeometry args={[0.026, 0.008, 10, 20, Math.PI]} />
        <meshStandardMaterial color="#f6f1ea" roughness={0.35} metalness={0.02} />
      </mesh>
    </group>
  );
}

function IndicatorLights({
  positions,
  active,
}: {
  positions: Array<[number, number, number]>;
  active: boolean;
}) {
  return (
    <>
      {positions.map((position, index) => {
        const color = index === 0 ? "#ea8a39" : index === 1 ? "#8fcf7b" : "#7aa7d9";
        return (
          <mesh key={`${position.join(":")}-${index}`} position={position}>
            <boxGeometry args={[0.045, 0.045, 0.02]} />
            <meshStandardMaterial
              color={color}
              emissive={color}
              emissiveIntensity={active ? 0.85 : 0.4}
            />
          </mesh>
        );
      })}
    </>
  );
}

function Portafilter({
  position,
  rotation = [0, 0, 0] as [number, number, number],
  handleColor = "#5a3320",
}: {
  position: [number, number, number];
  rotation?: [number, number, number];
  handleColor?: string;
}) {
  return (
    <group position={position} rotation={rotation}>
      <mesh castShadow>
        <cylinderGeometry args={[0.045, 0.045, 0.08, 18]} />
        <meshStandardMaterial color={METAL} roughness={0.22} metalness={0.85} />
      </mesh>
      <mesh position={[0.13, -0.01, 0]} rotation={[0, 0, Math.PI / 2]} castShadow>
        <cylinderGeometry args={[0.028, 0.024, 0.23, 12]} />
        <meshStandardMaterial color={handleColor} roughness={0.65} metalness={0.08} />
      </mesh>
    </group>
  );
}

function SteamWand({
  position,
  rotation = [0.15, 0, 0.22] as [number, number, number],
}: {
  position: [number, number, number];
  rotation?: [number, number, number];
}) {
  return (
    <group position={position} rotation={rotation}>
      <mesh castShadow>
        <cylinderGeometry args={[0.014, 0.014, 0.33, 10]} />
        <meshStandardMaterial color={METAL_DARK} roughness={0.3} metalness={0.85} />
      </mesh>
      <mesh position={[0, -0.17, 0.01]}>
        <boxGeometry args={[0.03, 0.025, 0.03]} />
        <meshStandardMaterial color={METAL} roughness={0.25} metalness={0.8} />
      </mesh>
    </group>
  );
}

function BeanHopper({ position }: { position: [number, number, number] }) {
  const beans = useMemo(
    () => [
      [-0.06, -0.01, -0.05],
      [-0.01, 0.03, -0.03],
      [0.05, 0.01, -0.04],
      [-0.05, -0.04, 0.01],
      [0.02, -0.02, 0.03],
      [0.07, -0.03, 0.02],
      [-0.01, -0.05, -0.01],
      [0.04, 0.04, 0.04],
      [-0.07, 0.03, 0.02],
    ] as Array<[number, number, number]>,
    [],
  );

  return (
    <group position={position}>
      <mesh position={[0, 0.11, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.26, 0.22, 0.26]} />
        <meshStandardMaterial
          color="#f2f5f6"
          transparent
          opacity={0.35}
          roughness={0.12}
          metalness={0.1}
        />
      </mesh>
      <mesh position={[0, -0.02, 0]} castShadow>
        <cylinderGeometry args={[0.14, 0.11, 0.06, 18]} />
        <meshStandardMaterial color="#8f9c78" roughness={0.5} metalness={0.08} />
      </mesh>
      {beans.map((bean, index) => (
        <mesh
          key={`bean-${index}`}
          position={[bean[0], bean[1] + 0.07, bean[2]]}
          rotation={[0.45, 0.25 * index, 0.2]}
        >
          <sphereGeometry args={[0.025, 10, 10]} />
          <meshStandardMaterial color="#5b331b" roughness={0.85} />
        </mesh>
      ))}
    </group>
  );
}

export function CoffeeMachineHeroModel({
  item,
  isSelected = false,
  isHovered = false,
  onClick,
  showLabel = true,
}: MachineProps) {
  const { wx, wz, rotY, scaleX, scaleZ } = getMachineTransform(item, 0.72, 0.56);
  const active = isSelected || isHovered;
  const body = active ? "#f7edde" : "#efe1ce";
  const side = active ? "#d6a667" : "#b6793f";
  const trim = active ? "#eadbc2" : "#d7c6ad";

  return (
    <group
      position={[wx, 0, wz]}
      rotation={[0, rotY, 0]}
      scale={[scaleX, 1, scaleZ]}
      onClick={(event) => {
        event.stopPropagation();
        onClick?.();
      }}
    >
      <mesh position={[0, 0.08, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.96, 0.16, 0.74]} />
        <meshStandardMaterial color="#ece2d1" roughness={0.58} metalness={0.06} />
      </mesh>
      <mesh position={[0, 0.47, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.9, 0.58, 0.66]} />
        <meshStandardMaterial color={body} roughness={0.46} metalness={0.08} />
      </mesh>
      <mesh position={[0.29, 0.47, 0]} castShadow>
        <boxGeometry args={[0.18, 0.58, 0.68]} />
        <meshStandardMaterial color={side} roughness={0.58} metalness={0.1} />
      </mesh>
      <mesh position={[0, 0.79, 0]} castShadow>
        <boxGeometry args={[0.86, 0.07, 0.58]} />
        <meshStandardMaterial color={trim} roughness={0.38} metalness={0.08} />
      </mesh>
      <mesh position={[0, 0.57, 0.29]}>
        <boxGeometry args={[0.62, 0.22, 0.03]} />
        <meshStandardMaterial color="#f8f2e7" roughness={0.3} metalness={0.02} />
      </mesh>
      <mesh position={[0, 0.56, 0.3]}>
        <planeGeometry args={[0.22, 0.16]} />
        <meshStandardMaterial color="#0f1e26" emissive="#d6dbe0" emissiveIntensity={active ? 0.48 : 0.22} />
      </mesh>
      <mesh position={[0.32, 0.56, 0.31]}>
        <cylinderGeometry args={[0.09, 0.09, 0.035, 28]} />
        <meshStandardMaterial color="#a95e2a" roughness={0.45} metalness={0.12} />
      </mesh>
      <IndicatorLights
        active={active}
        positions={[
          [-0.31, 0.63, 0.31],
          [-0.31, 0.52, 0.31],
          [0.11, 0.68, 0.31],
        ]}
      />
      <mesh position={[0, 0.18, 0]} receiveShadow>
        <boxGeometry args={[0.78, 0.07, 0.62]} />
        <meshStandardMaterial color="#dfd6c8" roughness={0.7} metalness={0.05} />
      </mesh>
      <mesh position={[0, 0.22, 0.08]}>
        <boxGeometry args={[0.54, 0.015, 0.22]} />
        <meshStandardMaterial color="#5b5148" roughness={0.75} metalness={0.15} />
      </mesh>
      <mesh position={[-0.04, 0.39, 0.15]} castShadow>
        <boxGeometry args={[0.24, 0.12, 0.26]} />
        <meshStandardMaterial color={METAL} roughness={0.24} metalness={0.85} />
      </mesh>
      <mesh position={[-0.1, 0.29, 0.24]}>
        <cylinderGeometry args={[0.013, 0.013, 0.12, 10]} />
        <meshStandardMaterial color={METAL_DARK} roughness={0.3} metalness={0.88} />
      </mesh>
      <mesh position={[0.02, 0.29, 0.24]}>
        <cylinderGeometry args={[0.013, 0.013, 0.12, 10]} />
        <meshStandardMaterial color={METAL_DARK} roughness={0.3} metalness={0.88} />
      </mesh>
      <Portafilter position={[0.1, 0.34, 0.16]} rotation={[0, 0.12, -0.12]} />
      <SteamWand position={[0.33, 0.44, 0.16]} />
      <CupProp position={[-0.11, 0.19, 0.08]} scale={0.62} />
      <CupProp position={[0.11, 0.19, 0.08]} scale={0.62} fill={CUP_FILL_LIGHT} />
      {showLabel ? <MachineLabel text="制作系统" position={[0, 1.02, 0]} /> : null}
      <SelectionRing active={isSelected} radius={0.56} />
    </group>
  );
}

export function CoffeeMachineCompactModel({
  item,
  isSelected = false,
  isHovered = false,
  onClick,
  showLabel = true,
}: MachineProps) {
  const { wx, wz, rotY, scaleX, scaleZ } = getMachineTransform(item, 0.52, 0.42);
  const active = isSelected || isHovered;
  const body = active ? "#d5dfbd" : "#b7c48d";
  const dark = active ? "#51613e" : "#445237";

  return (
    <group
      position={[wx, 0, wz]}
      rotation={[0, rotY, 0]}
      scale={[scaleX, 1, scaleZ]}
      onClick={(event) => {
        event.stopPropagation();
        onClick?.();
      }}
    >
      <mesh position={[0, 0.08, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.72, 0.16, 0.56]} />
        <meshStandardMaterial color="#d9d1c3" roughness={0.62} metalness={0.04} />
      </mesh>
      <mesh position={[0, 0.42, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.68, 0.5, 0.54]} />
        <meshStandardMaterial color={body} roughness={0.5} metalness={0.06} />
      </mesh>
      <mesh position={[0, 0.7, 0]} castShadow>
        <boxGeometry args={[0.58, 0.06, 0.42]} />
        <meshStandardMaterial color="#dce4c8" roughness={0.4} metalness={0.04} />
      </mesh>
      <mesh position={[0, 0.5, 0.24]}>
        <planeGeometry args={[0.42, 0.18]} />
        <meshStandardMaterial color="#eef2d8" roughness={0.3} metalness={0.03} />
      </mesh>
      <mesh position={[0.18, 0.49, 0.25]}>
        <cylinderGeometry args={[0.08, 0.08, 0.035, 24]} />
        <meshStandardMaterial color={dark} roughness={0.55} metalness={0.1} />
      </mesh>
      <IndicatorLights
        active={active}
        positions={[
          [-0.2, 0.56, 0.25],
          [-0.2, 0.46, 0.25],
        ]}
      />
      <mesh position={[0, 0.18, 0]} receiveShadow>
        <boxGeometry args={[0.54, 0.06, 0.42]} />
        <meshStandardMaterial color="#ebe3d2" roughness={0.68} metalness={0.04} />
      </mesh>
      <mesh position={[-0.02, 0.34, 0.13]} castShadow>
        <boxGeometry args={[0.2, 0.11, 0.18]} />
        <meshStandardMaterial color={METAL} roughness={0.22} metalness={0.86} />
      </mesh>
      <Portafilter position={[0.06, 0.29, 0.12]} rotation={[0, 0.1, -0.05]} handleColor="#5f3523" />
      <SteamWand position={[0.24, 0.38, 0.12]} rotation={[0.2, 0, 0.24]} />
      <CupProp position={[0.02, 0.19, 0.04]} scale={0.56} fill={CUP_FILL_LIGHT} />
      {showLabel ? <MachineLabel text="库存终端" position={[0, 0.92, 0]} /> : null}
      <SelectionRing active={isSelected} radius={0.42} />
    </group>
  );
}

export function CoffeeMachineGrinderModel({
  item,
  isSelected = false,
  isHovered = false,
  onClick,
  showLabel = true,
}: MachineProps) {
  const { wx, wz, rotY, scaleX, scaleZ } = getMachineTransform(item, 0.56, 0.46);
  const active = isSelected || isHovered;
  const body = active ? "#f0e7d6" : "#e5dac7";
  const accent = active ? "#90a56b" : "#788b59";

  return (
    <group
      position={[wx, 0, wz]}
      rotation={[0, rotY, 0]}
      scale={[scaleX, 1, scaleZ]}
      onClick={(event) => {
        event.stopPropagation();
        onClick?.();
      }}
    >
      <mesh position={[0, 0.08, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.78, 0.16, 0.64]} />
        <meshStandardMaterial color="#dcd4c7" roughness={0.62} metalness={0.04} />
      </mesh>
      <mesh position={[0, 0.39, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.74, 0.46, 0.58]} />
        <meshStandardMaterial color={body} roughness={0.48} metalness={0.08} />
      </mesh>
      <mesh position={[0, 0.64, 0]} castShadow>
        <boxGeometry args={[0.58, 0.08, 0.42]} />
        <meshStandardMaterial color={accent} roughness={0.55} metalness={0.08} />
      </mesh>
      <BeanHopper position={[0, 0.66, -0.03]} />
      <mesh position={[0, 0.44, 0.3]}>
        <planeGeometry args={[0.36, 0.16]} />
        <meshStandardMaterial color="#eef0df" roughness={0.3} metalness={0.02} />
      </mesh>
      <mesh position={[-0.2, 0.45, 0.31]}>
        <cylinderGeometry args={[0.07, 0.07, 0.03, 22]} />
        <meshStandardMaterial color="#f4f1e8" roughness={0.32} metalness={0.05} />
      </mesh>
      <mesh position={[0.21, 0.45, 0.31]}>
        <boxGeometry args={[0.1, 0.1, 0.03]} />
        <meshStandardMaterial color="#c86f2f" roughness={0.45} metalness={0.08} />
      </mesh>
      <IndicatorLights
        active={active}
        positions={[
          [0.29, 0.57, 0.31],
          [0.29, 0.49, 0.31],
          [0.29, 0.41, 0.31],
        ]}
      />
      <mesh position={[0, 0.28, 0.14]} castShadow>
        <boxGeometry args={[0.14, 0.16, 0.16]} />
        <meshStandardMaterial color={METAL} roughness={0.24} metalness={0.84} />
      </mesh>
      <mesh position={[0, 0.18, 0.24]}>
        <cylinderGeometry args={[0.014, 0.014, 0.12, 10]} />
        <meshStandardMaterial color={METAL_DARK} roughness={0.3} metalness={0.9} />
      </mesh>
      <Portafilter position={[0.02, 0.15, 0.16]} rotation={[0, 0.06, 0]} handleColor="#6b422b" />
      <CupProp position={[0.02, 0.18, 0.02]} scale={0.52} fill={CUP_FILL_MAIN} />
      {showLabel ? <MachineLabel text="原料库存" position={[0, 1.06, 0]} /> : null}
      <SelectionRing active={isSelected} radius={0.46} />
    </group>
  );
}

export function CoffeeMachinePreviewCluster({
  item,
  isSelected = false,
  isHovered = false,
  onClick,
}: MachineProps) {
  const sharedElevation = item.elevation ?? 0.56;
  const compact: FurnitureItem = {
    ...item,
    _uid: `${item._uid}_compact`,
    type: "coffee_machine_compact",
    x: item.x - 50,
    y: item.y + 6,
    elevation: sharedElevation + 0.01,
    facing: item.facing,
  };
  const hero: FurnitureItem = {
    ...item,
    _uid: `${item._uid}_hero`,
    type: "coffee_machine",
    x: item.x,
    y: item.y,
    elevation: sharedElevation,
    facing: item.facing,
  };
  const grinder: FurnitureItem = {
    ...item,
    _uid: `${item._uid}_grinder`,
    type: "coffee_machine_grinder",
    x: item.x + 54,
    y: item.y + 4,
    elevation: sharedElevation + 0.015,
    facing: item.facing,
  };

  return (
    <>
      <CoffeeMachineCompactModel
        item={compact}
        isSelected={isSelected}
        isHovered={isHovered}
        onClick={onClick}
      />
      <CoffeeMachineHeroModel
        item={hero}
        isSelected={isSelected}
        isHovered={isHovered}
        onClick={onClick}
      />
      <CoffeeMachineGrinderModel
        item={grinder}
        isSelected={isSelected}
        isHovered={isHovered}
        onClick={onClick}
      />
    </>
  );
}

// Register / self-checkout kiosk. Tall box with a screen, card slot, and a
// green status stripe; glow ring when selected.
export function AtmMachineModel({
  item,
  isSelected = false,
  isHovered = false,
  onClick,
}: MachineProps) {
  const [wx, , wz] = toWorld(item.x, item.y);
  const { width, height } = getItemBaseSize(item);
  const rotY = getItemRotationRadians(item);
  const scaleX = (width * SCALE) / 0.9;
  const scaleZ = (height * SCALE) / 0.7;
  const highlight = isSelected || isHovered;
  return (
    <group
      position={[wx, 0, wz]}
      rotation={[0, rotY, 0]}
      scale={[scaleX, 1, scaleZ]}
      onClick={(event) => {
        event.stopPropagation();
        onClick?.();
      }}
    >
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
          SELF ORDER
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
      <SelectionRing active={isSelected} radius={0.5} y={1.0} />
    </group>
  );
}

// Vending machine for coffee beans / snacks. Glass front with glowing product
// rows + a dispense slot at the bottom.
export function VendingMachineModel({
  item,
  isSelected = false,
  isHovered = false,
  onClick,
}: MachineProps) {
  const [wx, , wz] = toWorld(item.x, item.y);
  const { width, height } = getItemBaseSize(item);
  const rotY = getItemRotationRadians(item);
  const scaleX = (width * SCALE) / 0.9;
  const scaleZ = (height * SCALE) / 0.7;
  const highlight = isSelected || isHovered;
  const productColors = ["#c97b3a", "#e0c060", "#8a5a2a", "#b5651d", "#d9a06b", "#a0522d"];
  return (
    <group
      position={[wx, 0, wz]}
      rotation={[0, rotY, 0]}
      scale={[scaleX, 1, scaleZ]}
      onClick={(event) => {
        event.stopPropagation();
        onClick?.();
      }}
    >
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
      <SelectionRing active={isSelected} radius={0.55} y={1.1} />
    </group>
  );
}

// Cafe jukebox: teak cabinet with a spinning vinyl, neon display, and a pulsing
// point light when "playing".
const JUKEBOX_BUTTONS = ["#ff0000", "#ffff00", "#00ff00", "#00ffff", "#ff00ff"];
export function JukeboxModel({
  item,
  isSelected = false,
  isHovered = false,
  onClick,
}: MachineProps) {
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
    <group
      position={[wx, 0, wz]}
      rotation={[0, rotY, 0]}
      scale={[scaleX, 1, scaleZ]}
      onClick={(event) => {
        event.stopPropagation();
        onClick?.();
      }}
    >
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
        <meshStandardMaterial color="#042f2e" emissive="#ff1493" emissiveIntensity={highlight ? 0.5 : 0.2} />
      </mesh>
      <Billboard position={[0, 1.1, 0.32]} follow={false}>
        <Text fontSize={0.07} color="#00ff00" anchorX="center" anchorY="middle" maxWidth={0.55} textAlign="center">
          NOW PLAYING
        </Text>
      </Billboard>
      <mesh position={[0, 0.7, 0.31]}>
        <planeGeometry args={[0.52, 0.38]} />
        <meshStandardMaterial color="#042f2e" roughness={0.9} metalness={0.1} />
      </mesh>
      {[-0.14, -0.07, 0, 0.07, 0.14].map((offset) => (
        <mesh key={offset} position={[0, 0.7 + offset, 0.315]}>
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
        <meshStandardMaterial color="#ff1493" emissive="#ff1493" emissiveIntensity={0.6} />
      </mesh>
      <group position={[0, 0.5, 0.31]}>
        {JUKEBOX_BUTTONS.map((color, index) => (
          <mesh key={index} position={[-0.15 + index * 0.075, 0, 0.01]}>
            <cylinderGeometry args={[0.025, 0.025, 0.02, 16]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.5} />
          </mesh>
        ))}
      </group>
      <mesh position={[0, 0.05, 0]} receiveShadow>
        <boxGeometry args={[0.9, 0.1, 0.7]} />
        <meshStandardMaterial color="#0f766e" roughness={0.7} metalness={0.1} />
      </mesh>
      <pointLight ref={glowRef} position={[0, 1.2, 0.5]} color="#00ff00" intensity={1} distance={3} />
      <SelectionRing active={isSelected} radius={0.52} y={0.75} />
    </group>
  );
}

// Resolver: map a furniture type to its procedural machine, or null if it should
// fall back to the standard GLB FurnitureModel.
export const MACHINE_TYPES = new Set([
  "atm",
  "vending",
  "jukebox",
  ...COFFEE_MACHINE_TYPES,
]);

export function resolveMachine(item: FurnitureItem) {
  switch (item.type) {
    case "coffee_machine":
      return CoffeeMachinePreviewCluster;
    case "coffee_machine_compact":
      return CoffeeMachineCompactModel;
    case "coffee_machine_grinder":
      return CoffeeMachineGrinderModel;
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
