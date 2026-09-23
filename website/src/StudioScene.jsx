import React, { useEffect, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

import { BORDER, FAINT, INK, PANEL, ROLES, mono } from "./theme.jsx";

// The office. The studio room in the middle is the Agent Floor it always was (one desk per agent
// that can run at once); around it sit the spaces the Assistant Game walks you through - the Lobby
// where people wait on you, the Coffee Room of fyi's, the Memory Archive's filing cabinets (the Hub)
// haunted by threads that slipped, and the Assistant Core. Every figure is backed by a real item.

const COLORS = {
  wall: "#e8e0d1", trim: "#b99b73", wood: "#c5a47b", floor: "#ede5d7",
  sage: "#799077", slate: "#637d8d", wine: "#8a3646", dark: "#424b45", gold: "#d9a441",
};

const SKINS = [
  { shirt: "#799077", skin: "#bc8d6d", hair: "#49433a" },
  { shirt: "#637d8d", skin: "#d6a985", hair: "#544b3e" },
  { shirt: "#8a6a5c", skin: "#e0b793", hair: "#765442" },
  { shirt: "#6a6480", skin: "#c99372", hair: "#3f3b35" },
  { shirt: "#74888b", skin: "#e7c3a1", hair: "#5a4437" },
  { shirt: "#8d7968", skin: "#b98262", hair: "#332f2a" },
  { shirt: "#6d8568", skin: "#d9aa80", hair: "#625140" },
  { shirt: "#596f80", skin: "#efcfad", hair: "#40352f" },
];
const YOU = { shirt: "#2c3140", skin: "#d2a07c", hair: "#2a2622" };

// where each space sits, and where the camera goes when you jump into it
export const ZONE_VIEW = {
  all: { target: [0, 1, 2.3], zoom: 0.92 },
  floor: { target: [0, 1, 0.2], zoom: 1.4 },
  lobby: { target: [0, 0.8, 6.4], zoom: 1.55 },
  coffee: { target: [8.3, 0.8, -1], zoom: 1.6 },
  hq: { target: [8.3, 0.8, 6.4], zoom: 1.7 },
  archive: { target: [-8.3, 1, 2.3], zoom: 1.3 },
};
const YOU_SPOT = { all: [4.4, 4.3], floor: [3.9, 3.4], lobby: [2.6, 5.9], coffee: [6.3, 0.6], hq: [6.4, 7.6], archive: [-6.2, 2.6] };
const LOBBY_SPOTS = [[-3.4, 7.7], [-2.1, 7.7], [-0.8, 7.7], [0.5, 7.7], [-2.75, 6.6], [-1.45, 6.6]];
const COFFEE_SPOTS = [[7.3, -2.2], [9.2, -2.2], [6.6, -0.6], [10, -0.6], [7.6, 0.9], [9.4, 0.9]];
const GHOST_SPOTS = [[-9.5, 0.4], [-7, -1.4], [-9.2, 4.6], [-6.8, 6.4], [-8.2, 2.6]];
const CABINET_SPOTS = Array.from({ length: 8 }, (_, i) => [-10.35 + (i % 4) * 1.18, i < 4 ? -3.2 : 7.8]);

const clamp01 = (value) => Math.max(0, Math.min(1, value));
const smooth = (value) => { const x = clamp01(value); return x * x * (3 - 2 * x); };

function positionsFor(count) {
  const cols = count <= 4 ? Math.min(2, count) : count <= 6 ? 3 : 4;
  const rows = Math.ceil(count / cols);
  const xGap = cols === 4 ? 2.25 : 2.75;
  const zGap = 2.65;
  const out = [];
  for (let index = 0; index < count; index += 1) {
    const row = Math.floor(index / cols);
    const inRow = Math.min(cols, count - row * cols);
    const column = index - row * cols;
    const x = (column - (inRow - 1) / 2) * xGap;
    const z = rows === 1 ? 0.25 : (row - (rows - 1) / 2) * zGap + 0.2;
    out.push({ x, z, angle: (column - (inRow - 1) / 2) * -0.07 });
  }
  return out;
}

function shortLine(value, length = 34) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

const MARK_COLORS = { need: "#d9a441", send: "#6f9a6e", info: "#6d8fa6", bad: "#b04a5c", ask: "#c76a79" };

export default function StudioScene({ seats, selectedId, onSelect, focus = "all", onZone, npcs = [], cabinets = [],
  picked = null, onPick, onCabinet, onCore, zoneCounts = {}, inset = { left: 0, right: 0 } }) {
  const hostRef = useRef(null);
  const labelRefs = useRef([]);
  const tagRefs = useRef(new Map());     // id -> DOM node of an NPC / zone / cabinet tag
  const sceneApi = useRef(null);
  const seatsRef = useRef(seats);
  const props = useRef({});
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [hoverKey, setHoverKey] = useState(null);

  seatsRef.current = seats;
  props.current = { onSelect, onZone, onPick, onCabinet, onCore, selectedId, focus, picked, npcs, cabinets, zoneCounts, inset };

  useEffect(() => { sceneApi.current?.sync(seats); }, [seats]);
  useEffect(() => { sceneApi.current?.syncNpcs(npcs); }, [npcs]);
  useEffect(() => { sceneApi.current?.syncCabinets(cabinets); }, [cabinets]);
  useEffect(() => { sceneApi.current?.fly(focus); }, [focus]);
  useEffect(() => { sceneApi.current?.resize(); }, [inset.left, inset.right]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    } catch (_) {
      setFailed(true);
      return undefined;
    }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.7));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.domElement.setAttribute("aria-label", "Interactive 3D office: the agents at their desks, people waiting in the lobby, fyi's in the coffee room, the memory archive and the assistant core");
    renderer.domElement.tabIndex = 0;
    host.prepend(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-7, 7, 5, -5, 0.1, 140);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = false;
    controls.minZoom = 0.7;
    controls.maxZoom = 3.4;
    controls.minAzimuthAngle = -0.7;
    controls.maxAzimuthAngle = 1.15;
    controls.minPolarAngle = 0.72;
    controls.maxPolarAngle = 1.2;
    controls.touches.ONE = THREE.TOUCH.ROTATE;

    // a flight moves the target and carries the camera with it, so a turn you made survives a jump
    const flight = { from: new THREE.Vector3(), target: new THREE.Vector3(...ZONE_VIEW.all.target), zoom0: 1, zoom: ZONE_VIEW.all.zoom, at: 0, active: false };
    const offset0 = new THREE.Vector3(11, 9, 12.8);
    const resetCamera = () => {
      const v = ZONE_VIEW[props.current.focus] || ZONE_VIEW.all;
      controls.target.set(...v.target);
      camera.position.copy(controls.target).add(offset0);
      camera.zoom = v.zoom;
      camera.updateProjectionMatrix();
      controls.update();
      flight.active = false;
    };
    const fly = (zone) => {
      const v = ZONE_VIEW[zone] || ZONE_VIEW.all;
      flight.from.copy(controls.target);
      flight.target.set(...v.target);
      flight.zoom0 = camera.zoom;
      flight.zoom = v.zoom;
      flight.at = performance.now() / 1000;
      flight.active = !reduced;
      if (reduced) resetCamera();
      const [x, z] = YOU_SPOT[zone] || YOU_SPOT.all;
      you.goal.set(x, 0, z);
    };
    controls.addEventListener("start", () => { flight.active = false; });

    scene.add(new THREE.HemisphereLight(0xfffbef, 0xb4bab1, 2));
    const sunlight = new THREE.DirectionalLight(0xffe8c8, 3.15);
    sunlight.position.set(-4, 13, 8);
    sunlight.castShadow = true;
    sunlight.shadow.mapSize.set(2048, 2048);
    Object.assign(sunlight.shadow.camera, { left: -14, right: 14, top: 12, bottom: -12, near: 0.1, far: 45 });
    sunlight.shadow.bias = -0.0005;
    sunlight.shadow.normalBias = 0.035;
    sunlight.shadow.radius = 4;
    scene.add(sunlight);
    const fill = new THREE.DirectionalLight(0xe4edff, 1);
    fill.position.set(6, 5, -4);
    scene.add(fill);

    const materials = new Map();
    const geometries = new Map();
    const textures = [];
    const material = (color, roughness = 0.85) => {
      const key = `${color}:${roughness}`;
      if (!materials.has(key)) materials.set(key, new THREE.MeshStandardMaterial({ color, roughness }));
      return materials.get(key);
    };
    const rounded = (w, h, d, radius) => {
      const safeRadius = Math.min(radius, w / 3, h / 3, d / 3);
      const key = `${w}:${h}:${d}:${safeRadius}`;
      if (!geometries.has(key)) geometries.set(key, new RoundedBoxGeometry(w, h, d, 2, safeRadius));
      return geometries.get(key);
    };
    const box = (parent, w, h, d, color, x = 0, y = 0, z = 0, radius = 0.04) => {
      const mesh = new THREE.Mesh(rounded(w, h, d, radius), typeof color === "string" ? material(color) : color);
      mesh.position.set(x, y, z);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      parent.add(mesh);
      return mesh;
    };
    const sphereGeometry = new THREE.SphereGeometry(1, 20, 14);
    geometries.set("sphere", sphereGeometry);
    const ball = (parent, sx, sy, sz, color, x = 0, y = 0, z = 0) => {
      const mesh = new THREE.Mesh(sphereGeometry, typeof color === "string" ? material(color) : color);
      mesh.scale.set(sx, sy, sz);
      mesh.position.set(x, y, z);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      parent.add(mesh);
      return mesh;
    };
    const cylinder = (parent, rt, rb, h, color, x = 0, y = 0, z = 0, segments = 18) => {
      const geometry = new THREE.CylinderGeometry(rt, rb, h, segments);
      geometries.set(`cylinder:${geometries.size}`, geometry);
      const mesh = new THREE.Mesh(geometry, typeof color === "string" ? material(color) : color);
      mesh.position.set(x, y, z);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      parent.add(mesh);
      return mesh;
    };
    const group = (parent, x = 0, y = 0, z = 0) => {
      const value = new THREE.Group();
      value.position.set(x, y, z);
      parent.add(value);
      return value;
    };
    const canvasTexture = (draw, width = 512, height = 256) => {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      textures.push(texture);
      draw(canvas.getContext("2d"), canvas);
      return { canvas, texture };
    };
    const tag = (object, data) => { object.traverse((o) => { Object.assign(o.userData, data); }); return object; };

    const room = group(scene);
    const shadow = canvasTexture((ctx, canvas) => {
      const gradient = ctx.createRadialGradient(256, 128, 28, 256, 128, 230);
      gradient.addColorStop(0, "rgba(70,60,45,.23)");
      gradient.addColorStop(1, "rgba(70,60,45,0)");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    });
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(30, 20), new THREE.MeshBasicMaterial({
      map: shadow.texture, transparent: true, depthWrite: false,
    }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(0, -0.315, 2.2);
    scene.add(ground);

    // ── the Agent Floor: the studio room exactly as it was ──────────────────────────────────────
    const floorPad = box(room, 10.3, 0.35, 8.25, "#ddd3c2", 0, -0.13, 0, 0.15);
    box(room, 10.08, 0.08, 8.05, COLORS.floor, 0, 0.08, 0, 0.06);
    tag(floorPad, { zoneKey: "floor" });
    for (let index = 0; index < 17; index += 1) box(room, 0.012, 0.003, 7.9, "#d9cfbd", -4.8 + index * 0.6, 0.123, 0, 0.001);

    box(room, 0.8, 3.95, 0.19, COLORS.wall, -4.6, 2.04, -3.95);
    box(room, 0.8, 3.95, 0.19, COLORS.wall, -2.05, 2.04, -3.95);
    box(room, 1.75, 0.65, 0.19, COLORS.wall, -3.33, 3.69, -3.95);
    box(room, 2.05, 3.95, 0.19, COLORS.wall, 3.95, 2.04, -3.95);
    box(room, 4, 1, 0.19, COLORS.wall, 0.7, 0.64, -3.95);

    const arch = new THREE.Shape();
    arch.moveTo(-1.65, 4.02); arch.lineTo(3, 4.02); arch.lineTo(3, 1.14); arch.lineTo(2.45, 1.14);
    arch.lineTo(2.45, 2.55); arch.absarc(0.7, 2.55, 1.75, 0, Math.PI, false);
    arch.lineTo(-1.05, 1.14); arch.lineTo(-1.65, 1.14); arch.closePath();
    const archGeometry = new THREE.ExtrudeGeometry(arch, { depth: 0.19, bevelEnabled: false });
    geometries.set("arch", archGeometry);
    const archMesh = new THREE.Mesh(archGeometry, material(COLORS.wall));
    archMesh.position.z = -4.045;
    archMesh.castShadow = true;
    archMesh.receiveShadow = true;
    room.add(archMesh);

    const glassShape = new THREE.Shape();
    glassShape.moveTo(-1.03, 1.14); glassShape.lineTo(2.43, 1.14); glassShape.lineTo(2.43, 2.55);
    glassShape.absarc(0.7, 2.55, 1.73, 0, Math.PI, false); glassShape.closePath();
    const glassGeometry = new THREE.ShapeGeometry(glassShape);
    geometries.set("glass", glassGeometry);
    const glassMaterial = new THREE.MeshStandardMaterial({ color: "#cddcda", roughness: 0.3, metalness: 0.03 });
    materials.set("glass", glassMaterial);
    const glass = new THREE.Mesh(glassGeometry, glassMaterial);
    glass.position.z = -3.94;
    room.add(glass);
    const arcPoints = [];
    for (let index = 0; index <= 48; index += 1) {
      const angle = index / 48 * Math.PI;
      arcPoints.push(new THREE.Vector3(0.7 + 1.75 * Math.cos(angle), 2.55 + 1.75 * Math.sin(angle), -3.79));
    }
    const archTrimGeometry = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(arcPoints), 48, 0.047, 8, false);
    geometries.set("arch-trim", archTrimGeometry);
    room.add(new THREE.Mesh(archTrimGeometry, material(COLORS.trim)));
    for (const x of [-1.05, 0.7, 2.45]) box(room, 0.075, x === 0.7 ? 3.1 : 1.5, 0.15, COLORS.trim, x, x === 0.7 ? 2.68 : 1.85, -3.8);
    box(room, 3.58, 0.075, 0.15, COLORS.trim, 0.7, 2.55, -3.8);
    box(room, 3.8, 0.12, 0.42, "#d3b68e", 0.7, 1.18, -3.78);

    const door = group(room, -4.15, 0.16, -3.88);
    door.rotation.y = -1.02;
    box(door, 1.57, 3.03, 0.13, "#b99468", 0.79, 1.51, 0, 0.045);
    box(door, 1.23, 1.7, 0.035, "#c5a67d", 0.79, 1.91, 0.078);
    box(door, 1.23, 0.7, 0.035, "#c5a67d", 0.79, 0.58, 0.078);
    ball(door, 0.055, 0.055, 0.055, "#72664b", 1.35, 1.45, 0.13);

    const sign = canvasTexture((ctx, canvas) => {
      ctx.fillStyle = "#f4eee3"; ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#53685a"; ctx.textAlign = "center";
      ctx.font = "700 44px Segoe UI, sans-serif"; ctx.fillText("TASKUARY", 256, 112);
      ctx.fillStyle = "#8c8a7e"; ctx.font = "500 22px Segoe UI, sans-serif"; ctx.fillText("THE STUDIO", 256, 158);
    });
    box(room, 1.72, 1.02, 0.09, COLORS.trim, 4.13, 2.47, -3.81);
    const signGeometry = new THREE.PlaneGeometry(1.6, 0.9);
    geometries.set("studio-sign", signGeometry);
    const signPlane = new THREE.Mesh(signGeometry, new THREE.MeshStandardMaterial({ map: sign.texture, roughness: 1 }));
    signPlane.position.set(4.13, 2.47, -3.75);
    room.add(signPlane);

    const createPlant = (x, z, scale = 1) => {
      const plant = group(room, x, 0.14, z);
      plant.scale.setScalar(scale);
      cylinder(plant, 0.24, 0.17, 0.43, "#d5d2c0", 0, 0.23, 0);
      cylinder(plant, 0.205, 0.205, 0.018, "#6b5e47", 0, 0.452, 0);
      for (let index = 0; index < 8; index += 1) {
        const angle = index * 2.4;
        const y = 0.67 + (index % 3) * 0.18;
        const leaf = ball(plant, 0.13, 0.34, 0.065, index % 2 ? "#879569" : "#657d59",
          Math.cos(angle) * 0.22, y, Math.sin(angle) * 0.22);
        leaf.rotation.set(Math.sin(angle) * 0.65, angle, Math.cos(angle) * 0.65);
      }
      return plant;
    };
    const plants = [createPlant(-4.45, 2.95, 1.45), createPlant(4.45, -3.05, 1.55), createPlant(4.6, 7.9, 1.2), createPlant(10.5, 8, 1.1)];
    box(room, 6.8, 0.014, 3.8, "#c7c4af", 0.25, 0.139, 0.65, 0.12);
    for (let index = 0; index < 38; index += 1) box(room, 0.023, 0.005, 3.6, "#d6d1bd", -3.05 + index * 0.175, 0.15, 0.65, 0.001);

    // ── the other spaces: one raised pad each, so the office reads as rooms at a glance ─────────
    const pad = (zoneKey, w, d, x, z, base, top) => {
      tag(box(room, w, 0.35, d, base, x, -0.13, z, 0.15), { zoneKey });
      tag(box(room, w - 0.22, 0.08, d - 0.2, top, x, 0.08, z, 0.06), { zoneKey });
    };
    pad("lobby", 10.3, 4.5, 0, 6.6, "#d6cdbb", "#e9e3d7");
    pad("coffee", 6, 6.2, 8.3, -0.95, "#d8c7b1", "#ead8c2");
    pad("hq", 6, 4.5, 8.3, 6.6, "#2c323b", "#39414c");
    pad("archive", 6, 12.75, -8.3, 2.25, "#cbc2b2", "#ddd5c6");

    // lobby: reception desk, a sofa, a rug, the queue line people wait on
    box(room, 6.2, 0.012, 2.4, "#cfd6c8", -1.4, 0.135, 7.1, 0.1);
    box(room, 2.4, 0.95, 0.7, "#8a6a5c", 3.1, 0.6, 5.2, 0.08);
    box(room, 2.6, 0.08, 0.86, "#d9c3a3", 3.1, 1.1, 5.2, 0.04);
    box(room, 0.36, 0.26, 0.05, "#435357", 3.1, 1.28, 5.05, 0.02);
    box(room, 2.2, 0.42, 0.8, "#637d8d", -3.9, 0.35, 5.1, 0.14);
    box(room, 2.2, 0.62, 0.22, "#637d8d", -3.9, 0.66, 4.78, 0.1);
    for (let i = 0; i < 6; i += 1) box(room, 0.06, 0.012, 0.3, "#b99b73", -3.8 + i * 1.1, 0.145, 8.35, 0.004);

    // coffee room: counter, the machine, a fridge, two round tables
    box(room, 5.2, 1, 0.8, "#b28b6a", 8.3, 0.6, -3.55, 0.06);
    box(room, 5.3, 0.08, 0.9, "#efe6d6", 8.3, 1.14, -3.55, 0.03);
    const machine = group(room, 7.1, 1.18, -3.6);
    box(machine, 0.72, 0.9, 0.55, "#3b3f45", 0, 0.45, 0, 0.06);
    box(machine, 0.5, 0.18, 0.1, "#1f2328", 0, 0.62, 0.28, 0.02);
    const steamMat = new THREE.MeshBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0.4, depthWrite: false });
    materials.set("steam", steamMat);
    const steam = [0, 1, 2].map((i) => ball(machine, 0.07, 0.07, 0.07, steamMat, 0, 0.95 + i * 0.2, 0.15));
    const machineLight = ball(machine, 0.04, 0.04, 0.04, new THREE.MeshBasicMaterial({ color: "#91d19b" }), 0.22, 0.8, 0.28);
    box(room, 0.9, 2.1, 0.8, "#e6e3dc", 10.5, 1.2, -3.5, 0.08);
    box(room, 0.04, 0.5, 0.04, "#9aa0a6", 10.15, 1.5, -3.08, 0.01);
    for (const [x, z] of [[8.3, -1.4], [8.5, 0.2]]) {
      cylinder(room, 0.62, 0.62, 0.06, "#efe6d6", x, 0.9, z, 28);
      cylinder(room, 0.06, 0.08, 0.72, "#6b5e47", x, 0.5, z);
      cylinder(room, 0.08, 0.08, 0.14, "#f4f1ea", x - 0.2, 1, z + 0.1);
    }

    // hq: the Assistant Core - a pedestal, a spinning lattice, a pulse ring
    const core = group(room, 8.3, 0.12, 6.4);
    cylinder(core, 1.05, 1.2, 0.3, "#20252c", 0, 0.15, 0, 40);
    const glowMat = new THREE.MeshBasicMaterial({ color: "#7fd1c6", transparent: true, opacity: 0.85 });
    materials.set("glow", glowMat);
    const coreRingGeometry = new THREE.TorusGeometry(0.95, 0.03, 8, 64);
    geometries.set("core-ring", coreRingGeometry);
    const coreRing = new THREE.Mesh(coreRingGeometry, glowMat);
    coreRing.rotation.x = Math.PI / 2; coreRing.position.y = 0.32;
    core.add(coreRing);
    const latticeGeometry = new THREE.IcosahedronGeometry(0.62, 1);
    geometries.set("lattice", latticeGeometry);
    const latticeMat = new THREE.MeshBasicMaterial({ color: "#9be7dc", wireframe: true, transparent: true, opacity: 0.75 });
    materials.set("lattice", latticeMat);
    const lattice = new THREE.Mesh(latticeGeometry, latticeMat);
    lattice.position.y = 1.55;
    core.add(lattice);
    const orbMat = new THREE.MeshStandardMaterial({ color: "#bff3ea", emissive: "#4fb3a6", emissiveIntensity: 1.4, roughness: 0.2 });
    materials.set("orb", orbMat);
    const orb = ball(core, 0.3, 0.3, 0.3, orbMat, 0, 1.55, 0);
    const pulseGeometry = new THREE.RingGeometry(0.9, 1, 64);
    geometries.set("pulse", pulseGeometry);
    const pulseMat = new THREE.MeshBasicMaterial({ color: "#7fd1c6", transparent: true, opacity: 0.5, side: THREE.DoubleSide, depthWrite: false });
    materials.set("pulse", pulseMat);
    const pulse = new THREE.Mesh(pulseGeometry, pulseMat);
    pulse.rotation.x = -Math.PI / 2; pulse.position.y = 0.33;
    core.add(pulse);
    tag(core, { core: true });
    for (let i = 0; i < 12; i += 1) box(room, 0.02, 0.004, 4.2, "#4b6b72", 5.7 + i * 0.47, 0.125, 6.6, 0.001);
    const coreLight = new THREE.PointLight("#7fd1c6", 6, 6, 1.6);
    coreLight.position.set(8.3, 2, 6.4);
    scene.add(coreLight);

    // archive: two walls of filing cabinets (one per Hub topic), a reading table in the middle
    box(room, 0.17, 1.6, 12.4, "#d9d0bf", -11.2, 0.9, 2.25, 0.05);
    box(room, 1.8, 0.08, 1.1, "#a98d6b", -8.3, 0.9, 2.3, 0.04);
    for (const [x, z] of [[-9.05, 1.9], [-7.55, 1.9], [-9.05, 2.7], [-7.55, 2.7]]) box(room, 0.08, 0.8, 0.08, "#8f7657", x, 0.5, z);
    const lampMat = new THREE.MeshStandardMaterial({ color: "#f3d48a", emissive: "#d9a441", emissiveIntensity: 0.9 });
    materials.set("lamp", lampMat);
    ball(room, 0.14, 0.1, 0.14, lampMat, -8.3, 1.25, 2.3);
    const cabinetMeshes = CABINET_SPOTS.map(([x, z], i) => {
      const cab = group(room, x, 0.12, z);
      const body = box(cab, 1.02, 2.05, 0.72, "#7d8a8f", 0, 1.03, 0, 0.05);
      const drawers = [0, 1, 2, 3].map((d) => {
        const drawer = box(cab, 0.9, 0.44, 0.06, "#95a2a7", 0, 0.3 + d * 0.49, i < 4 ? 0.38 : -0.38, 0.03);
        box(drawer, 0.28, 0.05, 0.04, "#d0d6d8", 0, 0.08, i < 4 ? 0.04 : -0.04, 0.02);
        return drawer;
      });
      const anchor = group(cab, 0, 2.3 + (i % 2) * 0.45, 0);
      return { cab, body, drawers, anchor, topic: null, open: 0 };
    });

    // ── people ──────────────────────────────────────────────────────────────────────────────────
    function character(parent, colors, standing = false) {
      const root = group(parent, 0, 0, standing ? 0 : 0.78);
      root.rotation.y = Math.PI;
      const baseY = standing ? 0.79 : 0.72;
      const torso = group(root, 0, baseY, 0);
      ball(torso, 0.245, 0.34, 0.18, colors.shirt, 0, 0.31, 0);
      box(torso, 0.33, 0.16, 0.29, "#5d655f", 0, -0.01, 0, 0.07);
      cylinder(torso, 0.082, 0.09, 0.15, colors.skin, 0, 0.64, 0);
      const head = group(torso, 0, 0.86, 0);
      ball(head, 0.245, 0.28, 0.22, colors.skin);
      ball(head, 0.253, 0.19, 0.222, colors.hair, 0, 0.14, -0.025);
      for (let index = 0; index < 5; index += 1) ball(head, 0.092, 0.08, 0.08, colors.hair,
        -0.17 + index * 0.078, 0.18 + Math.sin(index) * 0.025, 0.16);
      for (const x of [-0.083, 0.083]) ball(head, 0.019, 0.025, 0.012, "#333c35", x, 0.01, 0.208);
      const arms = [];
      for (const signValue of [-1, 1]) {
        const arm = group(torso, signValue * 0.225, 0.5, 0);
        ball(arm, 0.09, 0.18, 0.105, colors.shirt, signValue * 0.035, -0.14, 0);
        ball(arm, 0.072, 0.14, 0.072, colors.skin, signValue * 0.045, -0.37, 0);
        ball(arm, 0.065, 0.075, 0.044, colors.skin, signValue * 0.045, -0.5, 0);
        arms.push(arm);
      }
      const legs = [];
      for (const signValue of [-1, 1]) {
        const leg = group(torso, signValue * 0.115, -0.02, 0);
        ball(leg, 0.095, 0.22, 0.1, "#5d655f", 0, -0.19, 0);
        const shin = group(leg, 0, -0.37, 0);
        ball(shin, 0.083, 0.19, 0.083, "#5d655f", 0, -0.14, 0);
        box(shin, 0.17, 0.11, 0.27, "#e5ddcc", 0, -0.33, 0.055, 0.05);
        if (!standing) { leg.rotation.x = -Math.PI / 2; shin.rotation.x = Math.PI / 2; }
        legs.push({ leg, shin });
      }
      box(torso, 0.07, 0.08, 0.013, "#dadfd3", -0.1, 0.36, 0.169, 0.01);
      return { root, torso, head, arms, legs, baseY, pose: standing ? "stand" : "sit" };
    }

    // a floating quest mark: a canvas sprite that always faces you
    const markTextures = new Map();
    const markTexture = (glyph, color) => {
      const key = `${glyph}:${color}`;
      if (!markTextures.has(key)) {
        markTextures.set(key, canvasTexture((ctx) => {
          ctx.fillStyle = color; ctx.beginPath(); ctx.arc(64, 64, 54, 0, Math.PI * 2); ctx.fill();
          ctx.strokeStyle = "rgba(255,255,255,.9)"; ctx.lineWidth = 7; ctx.stroke();
          ctx.fillStyle = "#fff"; ctx.font = "800 70px Segoe UI, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
          ctx.fillText(glyph, 64, 69);
        }, 128, 128).texture);
      }
      return markTextures.get(key);
    };
    const makeMark = (parent, y) => {
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: markTexture("!", MARK_COLORS.need), depthTest: false }));
      sprite.scale.set(0.42, 0.42, 1);
      sprite.position.y = y;
      sprite.renderOrder = 10;
      sprite.visible = false;
      parent.add(sprite);
      return sprite;
    };
    const setMark = (sprite, glyph, color) => {
      if (!glyph) { sprite.visible = false; return; }
      sprite.material.map = markTexture(glyph, color);
      sprite.material.needsUpdate = true;
      sprite.visible = true;
    };

    // ── the player: you walk to whichever space you jump into ──────────────────────────────────
    const youRoot = group(room, ...[YOU_SPOT.all[0], 0.12, YOU_SPOT.all[1]]);
    const youBody = character(youRoot, YOU, true);
    youBody.root.rotation.y = 0;
    const gemGeometry = new THREE.OctahedronGeometry(0.16, 0);
    geometries.set("gem", gemGeometry);
    const gemMat = new THREE.MeshStandardMaterial({ color: "#f0c05a", emissive: "#d9a441", emissiveIntensity: 1.1, roughness: 0.3 });
    materials.set("gem", gemMat);
    const gem = new THREE.Mesh(gemGeometry, gemMat);
    gem.position.y = 2.2;
    youRoot.add(gem);
    const you = { root: youRoot, body: youBody, goal: new THREE.Vector3(YOU_SPOT.all[0], 0, YOU_SPOT.all[1]), anchor: group(youRoot, 0, 2.5, 0) };

    // standing figures for the lobby and the coffee room, ghosts for the archive - pooled, a real
    // item fills one or it is hidden
    const standing = (spots, zone, offset) => spots.map(([x, z], i) => {
      const holder = group(room, x, 0.12, z);
      const body = character(holder, SKINS[(i + offset) % SKINS.length], true);
      body.root.rotation.y = zone === "lobby" ? Math.PI * 0.95 : Math.atan2(8.4 - x, -0.6 - z);
      const mug = zone === "coffee" ? cylinder(body.arms[1], 0.06, 0.05, 0.12, "#f4f1ea", 0.05, -0.55, 0.06) : null;
      const mark = makeMark(holder, 2.2);
      const anchor = group(holder, 0, 2.5, 0);
      holder.visible = false;
      return { holder, body, mug, mark, anchor, zone, item: null, arrivalAt: -100, phase: i * 1.7 };
    });
    const lobbyPool = standing(LOBBY_SPOTS, "lobby", 3);
    const coffeePool = standing(COFFEE_SPOTS, "coffee", 5);
    const ghostMat = new THREE.MeshStandardMaterial({ color: "#f5f7ff", emissive: "#aab7ff", emissiveIntensity: 0.35, transparent: true, opacity: 0.78, roughness: 0.4 });
    materials.set("ghost", ghostMat);
    const ghostPool = GHOST_SPOTS.map(([x, z], i) => {
      const holder = group(room, x, 0.5, z);
      ball(holder, 0.34, 0.4, 0.34, ghostMat, 0, 0.9, 0);
      const tail = cylinder(holder, 0.33, 0.12, 0.6, ghostMat, 0, 0.45, 0);
      tail.castShadow = false;
      for (const ex of [-0.11, 0.11]) ball(holder, 0.05, 0.075, 0.03, "#262a3a", ex, 0.98, 0.31);
      ball(holder, 0.06, 0.04, 0.03, "#262a3a", 0, 0.8, 0.33);
      const mark = makeMark(holder, 1.72);
      const anchor = group(holder, 0, 2, 0);
      holder.visible = false;
      return { holder, mark, anchor, zone: "archive", item: null, arrivalAt: -100, phase: i * 2.1, home: new THREE.Vector3(x, 0.5, z) };
    });
    const npcPools = { lobby: lobbyPool, coffee: coffeePool, archive: ghostPool };

    // ── desks (the Agent Floor) ────────────────────────────────────────────────────────────────
    function makeScreen() {
      const surface = canvasTexture((ctx, canvas) => {
        ctx.fillStyle = "#d5d0c3"; ctx.fillRect(0, 0, canvas.width, canvas.height);
      }, 512, 320);
      const draw = (descriptor) => {
        const { canvas } = surface;
        const ctx = canvas.getContext("2d");
        const occupied = !!descriptor;
        ctx.fillStyle = occupied ? "#293c42" : "#d5d0c3";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = occupied ? "#42575b" : "#c6c0b2";
        ctx.fillRect(0, 0, canvas.width, 38);
        if (!occupied) {
          ctx.fillStyle = "#aaa394"; ctx.font = "500 22px Segoe UI, sans-serif";
          ctx.fillText("free desk", 28, 182);
          surface.texture.needsUpdate = true;
          return;
        }
        const tone = descriptor.state.tone;
        ctx.fillStyle = tone === "waiting" ? "#c76a79" : "#91b99b";
        ctx.beginPath(); ctx.arc(24, 19, 6, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "#e8eee5"; ctx.font = "600 22px Segoe UI, sans-serif";
        ctx.fillText(shortLine(`${descriptor.state.agent} / ${descriptor.task.ref}`, 31), 27, 78);
        ctx.fillStyle = tone === "waiting" ? "#efb3bd" : "#a7c79a";
        ctx.font = "500 19px Segoe UI, sans-serif"; ctx.fillText(descriptor.state.label, 27, 112);
        ctx.fillStyle = "#dce3d8"; ctx.font = "500 20px Segoe UI, sans-serif";
        ctx.fillText(shortLine(descriptor.task.Title, 38), 27, 158);
        const tail = (descriptor.liveRow?.tail || []).slice(-3);
        ctx.fillStyle = "#91aaa7"; ctx.font = "500 16px Consolas, monospace";
        (tail.length ? tail : [descriptor.state.pose === "paper" ? "working through the task…" : "agent session active…"])
          .forEach((line, index) => ctx.fillText(shortLine(line, 48), 27, 210 + index * 27));
        surface.texture.needsUpdate = true;
      };
      return { ...surface, draw };
    }

    function workstation(index) {
      const desk = group(room);
      box(desk, 1.82, 0.13, 0.94, COLORS.wood, 0, 1.07, 0, 0.06);
      for (const x of [-0.76, 0.76]) for (const z of [-0.33, 0.33]) box(desk, 0.09, 0.94, 0.09, "#a98d6b", x, 0.57, z);
      box(desk, 0.36, 0.62, 0.66, "#c1a37b", 0.61, 0.72, 0);
      box(desk, 0.38, 0.04, 0.25, "#697572", -0.08, 1.16, -0.18);
      box(desk, 0.065, 0.25, 0.065, "#697572", -0.08, 1.31, -0.24);
      box(desk, 0.91, 0.6, 0.065, "#435357", -0.08, 1.64, -0.24, 0.035);
      const screen = makeScreen();
      const screenMaterial = new THREE.MeshBasicMaterial({ map: screen.texture });
      materials.set(`screen:${index}`, screenMaterial);
      const screenMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.82, 0.5), screenMaterial);
      geometries.set(`screen:${index}`, screenMesh.geometry);
      screenMesh.position.set(-0.08, 1.64, -0.204);
      desk.add(screenMesh);
      box(desk, 0.58, 0.035, 0.21, "#d9dbd1", -0.12, 1.17, 0.22, 0.024);
      for (let row = 0; row < 3; row += 1) for (let key = 0; key < 8; key += 1) {
        box(desk, 0.04, 0.008, 0.034, "#b5bdb2", -0.36 + key * 0.065, 1.192, 0.16 + row * 0.055, 0.005);
      }
      cylinder(desk, 0.042, 0.042, 0.43, "#72776b", 0, 0.42, 0.78);
      box(desk, 0.61, 0.15, 0.58, "#c8c6b4", 0, 0.7, 0.78, 0.12);
      box(desk, 0.61, 0.66, 0.13, "#c8c6b4", 0, 1.03, 1.06, 0.12);
      const person = character(desk, SKINS[index % SKINS.length]);
      const anchor = group(desk, 0, 2.46, 0.2);
      const mark = makeMark(desk, 2.95);
      mark.position.z = 0.78;
      const ringGeometry = new THREE.RingGeometry(0.42, 0.48, 48);
      geometries.set(`ring:${index}`, ringGeometry);
      const ringMaterial = new THREE.MeshBasicMaterial({ color: COLORS.sage, transparent: true, opacity: 0.72,
        side: THREE.DoubleSide, depthWrite: false });
      materials.set(`ring:${index}`, ringMaterial);
      const ring = new THREE.Mesh(ringGeometry, ringMaterial);
      ring.rotation.x = -Math.PI / 2;
      ring.position.set(0, 0.17, 0.78);
      ring.visible = false;
      desk.add(ring);
      desk.traverse((object) => { object.userData.seatIndex = index; });
      return { group: desk, person, anchor, ring, mark, screen, descriptor: null, previousId: null,
        arrivalAt: -100, target: new THREE.Vector3() };
    }

    const workstations = Array.from({ length: 8 }, (_, index) => workstation(index));
    const sync = (nextSeats) => {
      const layout = positionsFor(nextSeats.length);
      workstations.forEach((seat, index) => {
        const descriptor = nextSeats[index] || null;
        const nextId = descriptor?.task?.TaskId || null;
        seat.group.visible = index < nextSeats.length;
        if (layout[index]) {
          seat.target.set(layout[index].x, 0, layout[index].z);
          seat.group.rotation.y = layout[index].angle;
          if (!seat.group.userData.placed) {
            seat.group.position.copy(seat.target);
            seat.group.userData.placed = true;
          }
        }
        if (nextId && nextId !== seat.previousId) seat.arrivalAt = performance.now() / 1000;
        seat.previousId = nextId;
        seat.descriptor = descriptor;
        seat.person.root.visible = !!descriptor;
        seat.person.pose = descriptor?.state?.pose || "free";
        setMark(seat.mark, descriptor?.state?.tone === "waiting" ? "?" : null, MARK_COLORS.ask);
        seat.screen.draw(descriptor);
      });
    };
    const markFor = (item) => item.mark ? [item.mark.glyph, MARK_COLORS[item.mark.tone] || MARK_COLORS.need] : [null];
    const syncNpcs = (list) => {
      for (const [zone, pool] of Object.entries(npcPools)) {
        const mine = list.filter((n) => n.zone === zone);
        pool.forEach((slot, i) => {
          const item = mine[i] || null;
          if (item && item.key !== slot.item?.key) slot.arrivalAt = performance.now() / 1000;
          slot.item = item;
          slot.holder.visible = !!item;
          tag(slot.holder, { npcKey: item?.key || null });
          setMark(slot.mark, ...(item ? markFor(item) : [null]));
        });
      }
    };
    const syncCabinets = (list) => {
      cabinetMeshes.forEach((c, i) => {
        c.topic = list[i] || null;
        c.cab.visible = true;
        c.body.material = material(c.topic ? "#7d8a8f" : "#aab1b3");
        tag(c.cab, { cabinet: c.topic?.Topic || null });
      });
    };
    let hovered = -1, hoverNpc = null, hoverCab = null, hoverZone = null, hoverCore = false;
    const select = () => {};
    sceneApi.current = { sync, syncNpcs, syncCabinets, select, fly, reset: resetCamera, resize: () => resize() };
    sync(seatsRef.current);
    syncNpcs(props.current.npcs || []);
    syncCabinets(props.current.cabinets || []);
    fly(props.current.focus);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const down = { x: 0, y: 0, active: false };
    // the nearest thing under the pointer that means something: a desk, a person, a cabinet, the core, a room
    const hit = (clientX, clientY) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set((clientX - rect.left) / rect.width * 2 - 1, -(clientY - rect.top) / rect.height * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      for (const h of raycaster.intersectObject(room, true)) {
        if (!h.object.visible) continue;
        let o = h.object, visible = true;
        for (let p = o; p && p !== room; p = p.parent) if (!p.visible) visible = false;
        if (!visible) continue;
        const d = o.userData;
        if (Number.isInteger(d.seatIndex)) return { seat: d.seatIndex };
        if (d.npcKey) return { npc: d.npcKey };
        if (d.cabinet !== undefined && d.cabinet !== null) return { cabinet: d.cabinet };
        if (d.core) return { core: true };
        if (d.zoneKey) return { zone: d.zoneKey };
      }
      return {};
    };
    const onPointerDown = (event) => { down.x = event.clientX; down.y = event.clientY; down.active = true; };
    const onPointerMove = (event) => {
      if (down.active) return;
      const h = hit(event.clientX, event.clientY);
      hovered = h.seat ?? -1; hoverNpc = h.npc || null; hoverCab = h.cabinet ?? null; hoverCore = !!h.core; hoverZone = h.zone || null;
      setHoverKey(hoverNpc);
      const live = (hovered >= 0 && workstations[hovered].descriptor) || hoverNpc || hoverCab || hoverCore || hoverZone;
      renderer.domElement.style.cursor = live ? "pointer" : "grab";
    };
    const onPointerUp = (event) => {
      if (down.active && Math.hypot(event.clientX - down.x, event.clientY - down.y) < 6) {
        const h = hit(event.clientX, event.clientY), p = props.current;
        const descriptor = workstations[h.seat]?.descriptor;
        if (descriptor) { p.onZone?.("floor"); p.onSelect?.(descriptor.task.TaskId); }
        else if (h.npc) p.onPick?.(h.npc);
        else if (h.cabinet) p.onCabinet?.(h.cabinet);
        else if (h.core) p.onCore?.();
        else if (h.zone) p.onZone?.(h.zone);
      }
      down.active = false;
    };
    const onPointerLeave = () => { down.active = false; hovered = -1; hoverNpc = null; setHoverKey(null); renderer.domElement.style.cursor = "grab"; };
    const onDoubleClick = () => props.current.onZone?.("all");
    const onKeyDown = (event) => { if (event.key === "Home") { event.preventDefault(); resetCamera(); } };
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerup", onPointerUp);
    renderer.domElement.addEventListener("pointerleave", onPointerLeave);
    renderer.domElement.addEventListener("dblclick", onDoubleClick);
    renderer.domElement.addEventListener("keydown", onKeyDown);

    const resize = () => {
      const width = Math.max(1, host.clientWidth);
      const height = Math.max(1, host.clientHeight);
      renderer.setSize(width, height, false);
      const aspect = width / height;
      const span = aspect < 1 ? 24 / aspect : 17;
      // the map and the space panel cover the sides: centre the room in what is left between them
      const { left = 0, right = 0 } = props.current.inset || {};
      const shift = ((right - left) / 2) * (span * aspect / width);
      camera.left = -span * aspect / 2 + shift;
      camera.right = span * aspect / 2 + shift;
      camera.top = span / 2;
      camera.bottom = -span / 2;
      camera.updateProjectionMatrix();
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);
    resize();
    resetCamera();
    you.root.position.set(you.goal.x, 0.12, you.goal.z);

    const clock = new THREE.Clock();
    const startedAt = performance.now() / 1000;
    const projected = new THREE.Vector3();
    const step = new THREE.Vector3();
    const place = (node, object, show) => {
      if (!node) return;
      if (!show) { node.style.display = "none"; return; }
      object.getWorldPosition(projected);
      projected.project(camera);
      const x = (projected.x * 0.5 + 0.5) * host.clientWidth;
      const y = (-projected.y * 0.5 + 0.5) * host.clientHeight;
      const inside = projected.z < 1 && x > -80 && x < host.clientWidth + 80 && y > -50 && y < host.clientHeight + 50;
      node.style.display = inside ? "block" : "none";
      node.style.left = `${x}px`;
      node.style.top = `${y}px`;
    };
    const zoneAnchors = {
      floor: group(room, -3.6, 4.4, -3.6), lobby: group(room, -4, 1.6, 8.6), coffee: group(room, 8.3, 2.9, -2.6),
      hq: group(room, 8.3, 3.1, 6.4), archive: group(room, -8.3, 2.8, -3.9),
    };
    let animationFrame = 0;
    const animate = () => {
      animationFrame = requestAnimationFrame(animate);
      const raw = clock.getDelta(), delta = Math.min(raw, 0.05);
      const now = performance.now() / 1000;
      const p = props.current;
      const intro = reduced ? 1 : smooth((now - startedAt) / 1.25);
      room.scale.setScalar(0.9 + intro * 0.1);
      room.position.y = (1 - intro) * -0.45;
      room.rotation.y = (1 - intro) * -0.08;

      if (flight.active) {
        const t = smooth((now - flight.at) / 0.85);
        step.copy(flight.from).lerp(flight.target, t).sub(controls.target);
        controls.target.add(step);
        camera.position.add(step);
        camera.zoom = flight.zoom0 + (flight.zoom - flight.zoom0) * t;
        camera.updateProjectionMatrix();
        if (t >= 1) flight.active = false;
      }
      controls.update();
      scene.updateMatrixWorld();

      // you: walk to the spot, face the way you go, swing your legs while you do
      const to = step.copy(you.goal).sub(you.root.position).setY(0);
      const dist = to.length();
      const walking = dist > 0.05 && !reduced;
      if (reduced) you.root.position.set(you.goal.x, 0.12, you.goal.z);
      else if (walking) {
        you.root.position.addScaledVector(to.normalize(), Math.min(dist, Math.min(raw, 0.25) * 6));
        you.root.rotation.y += (Math.atan2(to.x, to.z) - you.root.rotation.y) * Math.min(1, delta * 10);
      }
      you.body.legs.forEach(({ leg }, i) => { leg.rotation.x = walking ? Math.sin(now * 12 + i * Math.PI) * 0.55 : 0; });
      you.body.arms.forEach((arm, i) => { arm.rotation.x = walking ? Math.sin(now * 12 + i * Math.PI + Math.PI) * 0.45 : 0; });
      you.body.torso.position.y = you.body.baseY + (walking ? Math.abs(Math.sin(now * 12)) * 0.05 : Math.sin(now * 2) * 0.01);
      gem.rotation.y = now * 2; gem.position.y = 2.2 + Math.sin(now * 3) * 0.06;

      workstations.forEach((seat, index) => {
        if (!seat.group.visible) {
          const node = labelRefs.current[index];
          if (node) node.style.display = "none";
          return;
        }
        seat.group.position.lerp(seat.target, reduced ? 1 : Math.min(1, delta * 8));
        const descriptor = seat.descriptor;
        const person = seat.person;
        if (descriptor) {
          const arrival = reduced ? 1 : smooth((now - seat.arrivalAt) / 0.8);
          person.root.scale.setScalar(0.72 + arrival * 0.28);
          person.root.position.z = 1.5 - arrival * 0.72;
          person.torso.position.y = person.baseY + Math.sin(now * 2 + index) * 0.012;
          person.head.rotation.y = Math.sin(now * 0.72 + index) * 0.075;
          person.arms.forEach((arm, armIndex) => {
            arm.position.y = 0.5;
            arm.scale.y = 1;
            arm.rotation.z = 0;
            arm.rotation.x = -1.1 + (person.pose === "type" ? Math.sin(now * 8 + armIndex * 2) * 0.07 : 0);
          });
          if (person.pose === "paper") {
            person.arms[0].rotation.x = -1.28;
            person.arms[1].rotation.x = -0.92;
          } else if (person.pose === "hand") {
            person.arms[0].rotation.x = -0.12;
            person.arms[0].rotation.z = -2.65 + Math.sin(now * 2.6) * 0.07;
            person.arms[0].scale.y = 1.35;
            person.arms[0].position.y = 0.65;
          }
        }
        if (seat.mark.visible) seat.mark.position.y = 2.95 + Math.sin(now * 3 + index) * 0.08;
        const active = descriptor && (descriptor.task.TaskId === p.selectedId || index === hovered);
        seat.ring.visible = !!active;
        seat.ring.material.color.set(descriptor?.state?.tone === "waiting" ? COLORS.wine : COLORS.sage);
        if (active) seat.ring.scale.setScalar(1 + Math.sin(now * 3) * 0.035);
        const node = labelRefs.current[index];
        place(node, seat.anchor, !!descriptor && (p.focus === "floor" || p.focus === "all"));
      });

      for (const pool of Object.values(npcPools)) pool.forEach((slot, i) => {
        if (!slot.item) { place(tagRefs.current.get(`npc:${i}:${slot.zone}`), slot.anchor, false); return; }
        const arrival = reduced ? 1 : smooth((now - slot.arrivalAt) / 0.7);
        const lit = slot.item.key === p.picked || slot.item.key === hoverNpc;
        if (slot.zone === "archive") {
          slot.holder.position.set(slot.home.x + Math.sin(now * 0.5 + slot.phase) * 0.35, slot.home.y + Math.sin(now * 1.6 + slot.phase) * 0.14,
            slot.home.z + Math.cos(now * 0.4 + slot.phase) * 0.3);
          slot.holder.rotation.y = Math.sin(now * 0.7 + slot.phase) * 0.5;
          slot.holder.scale.setScalar((0.4 + arrival * 0.6) * (lit ? 1.12 : 1));
        } else {
          slot.holder.scale.setScalar((0.6 + arrival * 0.4) * (lit ? 1.08 : 1));
          const b = slot.body;
          b.torso.position.y = b.baseY + Math.sin(now * 1.7 + slot.phase) * 0.012;
          b.head.rotation.y = Math.sin(now * 0.6 + slot.phase) * 0.25;
          if (slot.zone === "coffee") { b.arms[1].rotation.x = -1.2 + Math.max(0, Math.sin(now * 0.8 + slot.phase)) * -0.5; }
          else if (slot.item.mark?.tone === "need") { b.arms[0].rotation.z = -2.5 + Math.sin(now * 3 + slot.phase) * 0.25; b.arms[0].position.y = 0.62; }
          else { b.arms[0].rotation.z = 0; b.arms[0].position.y = 0.5; }
        }
        if (slot.mark.visible) slot.mark.position.y = (slot.zone === "archive" ? 1.72 : 2.2) + Math.sin(now * 3 + slot.phase) * 0.08;
        place(tagRefs.current.get(`npc:${i}:${slot.zone}`), slot.anchor, lit || p.focus === slot.zone);
      });

      cabinetMeshes.forEach((c, i) => {
        const want = c.topic && (c.topic.Topic === p.picked || c.topic.Topic === hoverCab) ? 1 : 0;
        c.open += (want - c.open) * Math.min(1, delta * 8);
        c.drawers[2].position.z = (i < 4 ? 0.38 : -0.38) + c.open * (i < 4 ? 0.42 : -0.42);
        place(tagRefs.current.get(`cab:${i}`), c.anchor, !!c.topic && (p.focus === "archive" || c.topic.Topic === hoverCab));
      });

      for (const [zone, anchor] of Object.entries(zoneAnchors)) place(tagRefs.current.get(`zone:${zone}`), anchor, p.focus === "all" || p.focus === zone || hoverZone === zone);
      place(tagRefs.current.get("you"), you.anchor, true);

      lattice.rotation.y = now * 0.6; lattice.rotation.x = now * 0.25;
      orb.scale.setScalar(0.3 + Math.sin(now * 2.4) * 0.025 + (hoverCore ? 0.05 : 0));
      const pulseT = (now * 0.6) % 1;
      pulse.scale.setScalar(1 + pulseT * 1.4); pulseMat.opacity = 0.55 * (1 - pulseT);
      coreRing.rotation.z = now * 0.8;
      steam.forEach((s, i) => { const t = (now * 0.5 + i / 3) % 1; s.position.y = 0.95 + t * 0.7; s.material.opacity = 0.45 * (1 - t); s.scale.setScalar(0.05 + t * 0.09); });
      machineLight.material.color.set(p.zoneCounts?.coffee ? "#f0c05a" : "#91d19b");
      plants.forEach((plant, index) => { plant.rotation.z = reduced ? 0 : Math.sin(now * 0.65 + index) * 0.008; });
      door.rotation.y += ((hovered >= 0 ? -1.12 : -1.02) - door.rotation.y) * Math.min(1, delta * 3);
      renderer.render(scene, camera);
    };
    animate();
    setReady(true);

    return () => {
      cancelAnimationFrame(animationFrame);
      resizeObserver.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      renderer.domElement.removeEventListener("pointerleave", onPointerLeave);
      renderer.domElement.removeEventListener("dblclick", onDoubleClick);
      renderer.domElement.removeEventListener("keydown", onKeyDown);
      scene.traverse((o) => { if (o.isSprite) o.material.dispose(); });
      geometries.forEach((geometry) => geometry.dispose());
      materials.forEach((value) => value.dispose());
      textures.forEach((texture) => texture.dispose());
      ground.geometry.dispose();
      ground.material.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
      sceneApi.current = null;
    };
    // the scene is built once; everything that changes reaches it through sceneApi or props.current
  }, []);

  const tagRef = (id) => (node) => { if (node) tagRefs.current.set(id, node); else tagRefs.current.delete(id); };
  const pinned = { position: "absolute", display: "none", transform: "translate(-50%, -100%)", zIndex: 3 };
  const slotsFor = (zone, n) => npcs.filter((x) => x.zone === zone).slice(0, n);

  return (
    <Box ref={hostRef} data-studio-scene="three" sx={{ position: "absolute", inset: 0, overflow: "hidden",
      "& canvas": { display: "block", width: "100%", height: "100%", outline: "none", cursor: "grab" } }}>
      {!ready && !failed && (
        <Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: FAINT, fontSize: 12 }}>
          Opening the office…
        </Box>
      )}
      {failed && (
        <Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: FAINT, fontSize: 12 }}>
          The 3D office needs WebGL enabled.
        </Box>
      )}
      {seats.map((descriptor, index) => (
        <Box key={descriptor?.task?.TaskId || `free-${index}`} ref={(node) => { labelRefs.current[index] = node; }}
          onClick={() => descriptor && onSelect?.(descriptor.task.TaskId)}
          sx={{ position: "absolute", zIndex: 3, transform: "translate(-50%, -100%)", minWidth: 118,
            maxWidth: 175, display: "none", px: 1.05, py: 0.7, borderRadius: "8px",
            bgcolor: "rgba(255,253,249,.92)", border: `1px solid ${BORDER}`,
            boxShadow: "0 8px 24px rgba(48,52,43,.12)", backdropFilter: "blur(7px)",
            cursor: descriptor ? "pointer" : "default", pointerEvents: descriptor ? "auto" : "none",
            textAlign: "left", "&:hover": { borderColor: "#9eaa98", bgcolor: PANEL } }}>
          {descriptor && <>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.6 }}>
              <Box sx={{ width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                bgcolor: descriptor.state.tone === "waiting" ? ROLES.you.solid : ROLES.working.solid }} />
              <Typography noWrap sx={{ fontSize: 10.5, fontWeight: 700, color: INK }}>{descriptor.state.agent}</Typography>
              <Typography sx={{ ...mono, ml: "auto", fontSize: 9.5, color: FAINT }}>{descriptor.task.ref}</Typography>
            </Box>
            <Typography noWrap sx={{ fontSize: 10.5, color: descriptor.state.tone === "waiting" ? ROLES.you.solid : FAINT,
              pt: 0.2 }}>{descriptor.state.label}</Typography>
          </>}
        </Box>
      ))}

      {/* speech bubbles: who is standing there, and what they came about */}
      {[["lobby", 6], ["coffee", 6], ["archive", 5]].flatMap(([zone, n]) => slotsFor(zone, n).map((item, i) => (
        <Box key={`npc:${i}:${zone}`} ref={tagRef(`npc:${i}:${zone}`)} onClick={() => onPick?.(item.key)}
          sx={{ ...pinned, maxWidth: 190, px: 1, py: 0.55, borderRadius: "10px 10px 10px 2px", cursor: "pointer",
            bgcolor: item.key === picked ? "#1f242c" : zone === "archive" ? "rgba(236,240,255,.94)" : "rgba(255,253,249,.94)",
            color: item.key === picked ? "#fff" : INK, border: `1px solid ${item.key === picked ? "#1f242c" : BORDER}`,
            boxShadow: "0 8px 22px rgba(30,34,40,.16)", outline: hoverKey === item.key ? "2px solid #d9a441" : "none" }}>
          <Typography noWrap sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 0.3, opacity: 0.8 }}>{item.who}</Typography>
          <Typography noWrap sx={{ fontSize: 11, fontWeight: 600 }}>{item.title}</Typography>
        </Box>
      )))}

      {cabinets.slice(0, 8).map((c, i) => (
        <Box key={`cab:${c.Topic}`} ref={tagRef(`cab:${i}`)} onClick={() => onCabinet?.(c.Topic)}
          sx={{ ...pinned, px: 0.9, py: 0.35, borderRadius: "6px", cursor: "pointer", bgcolor: c.Topic === picked ? "#1f242c" : "#f3efe6",
            color: c.Topic === picked ? "#fff" : INK, border: "1px solid #b9b2a3", boxShadow: "0 4px 12px rgba(30,34,40,.12)" }}>
          <Typography noWrap sx={{ ...mono, fontSize: 10.5, fontWeight: 700 }}>🗄 {c.Topic} · {c.n}</Typography>
        </Box>
      ))}

      {[["floor", "🖥 Agent Floor"], ["lobby", "🛋 The Lobby"], ["coffee", "☕ Coffee Room"], ["hq", "✦ Assistant Core"], ["archive", "🗄 Memory Archive"]].map(([zone, name]) => (
        <Box key={zone} ref={tagRef(`zone:${zone}`)} onClick={() => onZone?.(zone)}
          sx={{ ...pinned, px: 1.2, py: 0.45, borderRadius: 99, cursor: "pointer", whiteSpace: "nowrap",
            bgcolor: focus === zone ? "#f0c05a" : "rgba(24,28,34,.82)", color: focus === zone ? "#1c1f24" : "#fff",
            fontSize: 11.5, fontWeight: 800, letterSpacing: 0.3, boxShadow: "0 6px 18px rgba(0,0,0,.2)",
            "&:hover": { bgcolor: "#f0c05a", color: "#1c1f24" } }}>
          {name}{zoneCounts[zone] ? <Box component="span" sx={{ ml: 0.75, px: 0.6, borderRadius: 99, bgcolor: "#b04a5c", color: "#fff", fontSize: 10.5 }}>{zoneCounts[zone]}</Box> : null}
        </Box>
      ))}

      <Box ref={tagRef("you")} sx={{ ...pinned, pointerEvents: "none", px: 0.8, py: 0.15, borderRadius: 99, bgcolor: "#f0c05a",
        color: "#1c1f24", fontSize: 10, fontWeight: 900, letterSpacing: 1 }}>YOU</Box>

      <Box sx={{ position: "absolute", left: "50%", bottom: 12, transform: "translateX(-50%)", zIndex: 4,
        display: { xs: "none", sm: "flex" }, alignItems: "center", gap: 1, px: 1.2, py: 0.65, borderRadius: "8px",
        bgcolor: "rgba(24,28,34,.78)", backdropFilter: "blur(7px)" }}>
        <Typography sx={{ fontSize: 10.5, color: "#cfd5dc" }}>1-5 jump · Esc back out · drag to turn · scroll to zoom · click anyone</Typography>
        <Box component="button" type="button" onClick={() => sceneApi.current?.reset()}
          sx={{ border: 0, bgcolor: "transparent", color: "#f0c05a", fontSize: 10.5, fontWeight: 700,
            cursor: "pointer", p: 0, "&:hover": { textDecoration: "underline" } }}>Reset view</Box>
      </Box>
    </Box>
  );
}
