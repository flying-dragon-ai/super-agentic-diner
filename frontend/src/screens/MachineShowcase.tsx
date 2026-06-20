import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { Suspense } from "react";
import type { ReactNode } from "react";
import { SceneLighting } from "../office3d/systems/cameraLighting";
import {
  CoffeeMachineCompactModel,
  CoffeeMachineGrinderModel,
  CoffeeMachineHeroModel,
} from "../office3d/objects/machines";
import type { FurnitureItem } from "../office3d/core/types";

const makeItem = (
  uid: string,
  type: FurnitureItem["type"],
  facing: number,
): FurnitureItem => ({
  _uid: uid,
  type,
  x: 900,
  y: 360,
  elevation: 0.18,
  facing,
});

const COMPACT_ITEM = makeItem("machine_compact_showcase", "coffee_machine_compact", 0);
const HERO_ITEM = makeItem("machine_hero_showcase", "coffee_machine", 0);
const HOPPER_ITEM = makeItem("machine_hopper_showcase", "coffee_machine_grinder", 0);

function ShowcasePedestal() {
  return (
    <>
      <mesh position={[0, -0.08, 0]} receiveShadow rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[7.2, 5.4]} />
        <meshStandardMaterial color="#d9c8a5" roughness={0.98} />
      </mesh>
      <mesh position={[0, 0.08, 0]} receiveShadow castShadow>
        <boxGeometry args={[3.35, 0.16, 1.8]} />
        <meshStandardMaterial color="#9b6032" roughness={0.72} metalness={0.05} />
      </mesh>
      <mesh position={[0, 0.62, -0.86]} castShadow receiveShadow>
        <boxGeometry args={[3.7, 1.06, 0.24]} />
        <meshStandardMaterial color="#7a4c2a" roughness={0.82} metalness={0.04} />
      </mesh>
    </>
  );
}

function CompactStage() {
  return (
    <>
      <ShowcasePedestal />
      <CoffeeMachineCompactModel item={COMPACT_ITEM} showLabel={false} />
    </>
  );
}

function HeroStage() {
  return (
    <>
      <ShowcasePedestal />
      <CoffeeMachineHeroModel item={HERO_ITEM} showLabel={false} />
    </>
  );
}

function HopperStage() {
  return (
    <>
      <ShowcasePedestal />
      <CoffeeMachineGrinderModel item={HOPPER_ITEM} showLabel={false} />
    </>
  );
}

function ShowcaseCard({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <div
      style={{
        position: "relative",
        minHeight: 0,
        borderRadius: 8,
        overflow: "hidden",
        background: "#18120d",
        boxShadow: "0 14px 34px rgba(0,0,0,0.34)",
      }}
    >
      {children}
    </div>
  );
}

function ShowcaseCanvas({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <Canvas
      shadows
      camera={{ position: [0, 1.8, 4.9], fov: 22, near: 0.1, far: 100 }}
      onCreated={({ camera }) => camera.lookAt(0, 0.76, 0)}
    >
      <Suspense fallback={null}>
        <SceneLighting />
        {children}
      </Suspense>
      <OrbitControls
        target={[0, 0.76, 0]}
        enablePan={false}
        minDistance={4}
        maxDistance={6.4}
        minAzimuthAngle={-0.35}
        maxAzimuthAngle={0.35}
        minPolarAngle={0.95}
        maxPolarAngle={1.38}
      />
    </Canvas>
  );
}

export default function MachineShowcase() {
  return (
    <div
      style={{
        width: "100vw",
        minHeight: "100vh",
        background: "#120d09",
        color: "#f4ead8",
        padding: "56px 28px 28px",
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          maxWidth: 1480,
          margin: "0 auto",
          display: "grid",
          gridTemplateRows: "auto 1fr",
          gap: 18,
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 34, lineHeight: 1.1 }}>Coffee Machine First Pass</div>
          <div style={{ marginTop: 8, fontSize: 14, color: "#cbb694" }}>
            Three procedural cafe-machine directions for style and proportion review
          </div>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
            gap: 18,
            minHeight: "calc(100vh - 170px)",
          }}
        >
          <ShowcaseCard>
            <div style={{ position: "absolute", inset: "18px 18px auto 18px", zIndex: 2, pointerEvents: "none" }}>
              <div style={{ fontSize: 28, lineHeight: 1.1, color: "#f0dfc1" }}>Compact</div>
              <div style={{ marginTop: 6, fontSize: 13, color: "#ceb894" }}>
                home-bar style, soft green body
              </div>
            </div>
            <ShowcaseCanvas>
              <CompactStage />
            </ShowcaseCanvas>
          </ShowcaseCard>
          <ShowcaseCard>
            <div style={{ position: "absolute", inset: "18px 18px auto 18px", zIndex: 2, pointerEvents: "none" }}>
              <div style={{ fontSize: 28, lineHeight: 1.1, color: "#f0dfc1" }}>Hero</div>
              <div style={{ marginTop: 6, fontSize: 13, color: "#ceb894" }}>
                main espresso machine for the cafe bar
              </div>
            </div>
            <ShowcaseCanvas>
              <HeroStage />
            </ShowcaseCanvas>
          </ShowcaseCard>
          <ShowcaseCard>
            <div style={{ position: "absolute", inset: "18px 18px auto 18px", zIndex: 2, pointerEvents: "none" }}>
              <div style={{ fontSize: 28, lineHeight: 1.1, color: "#f0dfc1" }}>Hopper</div>
              <div style={{ marginTop: 6, fontSize: 13, color: "#ceb894" }}>
                grinder companion with visible beans
              </div>
            </div>
            <ShowcaseCanvas>
              <HopperStage />
            </ShowcaseCanvas>
          </ShowcaseCard>
        </div>
      </div>
    </div>
  );
}
