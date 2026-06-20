import { Canvas } from "@react-three/fiber";
import { OrbitControls, Text } from "@react-three/drei";
import { Suspense } from "react";
import { SceneLighting } from "../office3d/systems/cameraLighting";
import {
  CoffeeMachineCompactModel,
  CoffeeMachineGrinderModel,
  CoffeeMachineHeroModel,
} from "../office3d/objects/machines";
import type { FurnitureItem } from "../office3d/core/types";

const COMPACT_ITEM: FurnitureItem = {
  _uid: "machine_compact_showcase",
  type: "coffee_machine_compact",
  x: 760,
  y: 360,
  elevation: 0.18,
  facing: -4,
};

const HERO_ITEM: FurnitureItem = {
  _uid: "machine_hero_showcase",
  type: "coffee_machine",
  x: 900,
  y: 360,
  elevation: 0.18,
  facing: 0,
};

const HOPPER_ITEM: FurnitureItem = {
  _uid: "machine_hopper_showcase",
  type: "coffee_machine_grinder",
  x: 1040,
  y: 360,
  elevation: 0.18,
  facing: 5,
};

function ShowcaseStage() {
  return (
    <>
      <mesh position={[0, -0.08, 0]} receiveShadow rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[18, 12]} />
        <meshStandardMaterial color="#d8c59c" roughness={0.98} />
      </mesh>
      <mesh position={[0, 0.08, 0]} receiveShadow castShadow>
        <boxGeometry args={[7.2, 0.16, 2.4]} />
        <meshStandardMaterial color="#9a6033" roughness={0.72} metalness={0.06} />
      </mesh>
      <mesh position={[0, 0.64, -1.15]} castShadow receiveShadow>
        <boxGeometry args={[7.8, 1.16, 0.3]} />
        <meshStandardMaterial color="#7a4c2b" roughness={0.82} metalness={0.04} />
      </mesh>
      <mesh position={[0, 1.18, -1.28]}>
        <boxGeometry args={[2.8, 0.28, 0.05]} />
        <meshStandardMaterial color="#28160e" roughness={0.92} />
      </mesh>
    </>
  );
}

function ShowcaseLabels() {
  return (
    <>
      <Text position={[-1.45, 1.92, 0.32]} fontSize={0.16} color="#f4e2bf" anchorX="center" anchorY="middle">
        Compact
      </Text>
      <Text position={[0, 1.92, 0.32]} fontSize={0.16} color="#f4e2bf" anchorX="center" anchorY="middle">
        Hero
      </Text>
      <Text position={[1.45, 1.92, 0.32]} fontSize={0.16} color="#f4e2bf" anchorX="center" anchorY="middle">
        Hopper
      </Text>
      <Text position={[0, 2.22, 0.32]} fontSize={0.12} color="#dcc6a1" anchorX="center" anchorY="middle">
        First-pass coffee machine family
      </Text>
    </>
  );
}

export default function MachineShowcase() {
  return (
    <div style={{ width: "100vw", height: "100vh", background: "#18120d" }}>
      <Canvas
        shadows
        camera={{ position: [0, 2.2, 8.8], fov: 24, near: 0.1, far: 100 }}
        onCreated={({ camera }) => camera.lookAt(0, 0.88, 0)}
      >
        <Suspense fallback={null}>
          <SceneLighting />
          <ShowcaseStage />
          <CoffeeMachineCompactModel item={COMPACT_ITEM} />
          <CoffeeMachineHeroModel item={HERO_ITEM} />
          <CoffeeMachineGrinderModel item={HOPPER_ITEM} />
          <ShowcaseLabels />
        </Suspense>
        <OrbitControls
          target={[0, 0.88, 0]}
          minDistance={5.6}
          maxDistance={11.5}
          maxPolarAngle={Math.PI / 2.15}
        />
      </Canvas>
    </div>
  );
}
