import React, { useEffect, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

import { BORDER, FAINT, INK, PANEL, ROLES, mono } from "./theme.jsx";

const COLORS = {
  wall: "#e8e0d1", trim: "#b99b73", wood: "#c5a47b", floor: "#ede5d7",
  sage: "#799077", slate: "#637d8d", wine: "#8a3646", dark: "#424b45",
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

export default function StudioScene({ seats, selectedId, onSelect }) {
  const hostRef = useRef(null);
  const labelRefs = useRef([]);
  const sceneApi = useRef(null);
  const seatsRef = useRef(seats);
  const selectRef = useRef(onSelect);
  const selectedRef = useRef(selectedId);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  seatsRef.current = seats;
  selectRef.current = onSelect;
  selectedRef.current = selectedId;

  useEffect(() => { sceneApi.current?.sync(seats); }, [seats]);
  useEffect(() => { sceneApi.current?.select(selectedId); }, [selectedId]);

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
    renderer.domElement.setAttribute("aria-label", "Interactive 3D studio showing real Taskuary agents at their tasks");
    renderer.domElement.tabIndex = 0;
    host.prepend(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-7, 7, 5, -5, 0.1, 100);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = false;
    controls.minZoom = 0.76;
    controls.maxZoom = 1.8;
    controls.minAzimuthAngle = -0.7;
    controls.maxAzimuthAngle = 1.15;
    controls.minPolarAngle = 0.72;
    controls.maxPolarAngle = 1.2;
    controls.touches.ONE = THREE.TOUCH.ROTATE;

    const resetCamera = () => {
      camera.position.set(11, 10, 15);
      camera.zoom = 1;
      controls.target.set(0, 1, 0.35);
      camera.updateProjectionMatrix();
      controls.update();
    };
    resetCamera();

    scene.add(new THREE.HemisphereLight(0xfffbef, 0xb4bab1, 2));
    const sunlight = new THREE.DirectionalLight(0xffe8c8, 3.15);
    sunlight.position.set(-4, 11, 6);
    sunlight.castShadow = true;
    sunlight.shadow.mapSize.set(2048, 2048);
    Object.assign(sunlight.shadow.camera, { left: -9, right: 9, top: 9, bottom: -9, near: 0.1, far: 35 });
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
      const mesh = new THREE.Mesh(rounded(w, h, d, radius), material(color));
      mesh.position.set(x, y, z);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      parent.add(mesh);
      return mesh;
    };
    const sphereGeometry = new THREE.SphereGeometry(1, 20, 14);
    geometries.set("sphere", sphereGeometry);
    const ball = (parent, sx, sy, sz, color, x = 0, y = 0, z = 0) => {
      const mesh = new THREE.Mesh(sphereGeometry, material(color));
      mesh.scale.set(sx, sy, sz);
      mesh.position.set(x, y, z);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      parent.add(mesh);
      return mesh;
    };
    const cylinder = (parent, rt, rb, h, color, x = 0, y = 0, z = 0) => {
      const geometry = new THREE.CylinderGeometry(rt, rb, h, 18);
      geometries.set(`cylinder:${geometries.size}`, geometry);
      const mesh = new THREE.Mesh(geometry, material(color));
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

    const room = group(scene);
    const shadow = canvasTexture((ctx, canvas) => {
      const gradient = ctx.createRadialGradient(256, 128, 28, 256, 128, 230);
      gradient.addColorStop(0, "rgba(70,60,45,.23)");
      gradient.addColorStop(1, "rgba(70,60,45,0)");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    });
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(15, 12), new THREE.MeshBasicMaterial({
      map: shadow.texture, transparent: true, depthWrite: false,
    }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.315;
    scene.add(ground);

    box(room, 10.3, 0.35, 8.25, "#ddd3c2", 0, -0.13, 0, 0.15);
    box(room, 10.08, 0.08, 8.05, COLORS.floor, 0, 0.08, 0, 0.06);
    for (let index = 0; index < 17; index += 1) box(room, 0.012, 0.003, 7.9, "#d9cfbd", -4.8 + index * 0.6, 0.123, 0, 0.001);

    // The same warm shell, arched glass, open door and lived-in details as the site animation.
    box(room, 0.8, 3.95, 0.19, COLORS.wall, -4.6, 2.04, -3.95);
    box(room, 0.8, 3.95, 0.19, COLORS.wall, -2.05, 2.04, -3.95);
    box(room, 1.75, 0.65, 0.19, COLORS.wall, -3.33, 3.69, -3.95);
    box(room, 2.05, 3.95, 0.19, COLORS.wall, 3.95, 2.04, -3.95);
    box(room, 4, 1, 0.19, COLORS.wall, 0.7, 0.64, -3.95);
    box(room, 0.17, 0.8, 3.3, COLORS.wall, -5, 0.54, 2.25);
    box(room, 0.17, 1.5, 1.8, COLORS.wall, 5, 0.89, -3.1);

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
    const plants = [createPlant(-4.45, 2.95, 1.45), createPlant(4.45, -3.05, 1.55)];
    box(room, 6.8, 0.014, 3.8, "#c7c4af", 0.25, 0.139, 0.65, 0.12);
    for (let index = 0; index < 38; index += 1) box(room, 0.023, 0.005, 3.6, "#d6d1bd", -3.05 + index * 0.175, 0.15, 0.65, 0.001);

    function character(parent, colors) {
      const root = group(parent, 0, 0, 0.78);
      root.rotation.y = Math.PI;
      const torso = group(root, 0, 0.72, 0);
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
        leg.rotation.x = -Math.PI / 2;
        shin.rotation.x = Math.PI / 2;
        legs.push({ leg, shin });
      }
      box(torso, 0.07, 0.08, 0.013, "#dadfd3", -0.1, 0.36, 0.169, 0.01);
      return { root, torso, head, arms, legs, baseY: 0.72, pose: "sit" };
    }

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
      return { group: desk, person, anchor, ring, screen, descriptor: null, previousId: null,
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
        seat.screen.draw(descriptor);
      });
    };
    let hovered = -1;
    const select = (taskId) => { selectedRef.current = taskId; };
    sceneApi.current = { sync, select, reset: resetCamera };
    sync(seatsRef.current);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const down = { x: 0, y: 0, active: false };
    const hitSeat = (clientX, clientY) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set((clientX - rect.left) / rect.width * 2 - 1, -(clientY - rect.top) / rect.height * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      for (const hit of raycaster.intersectObject(room, true)) {
        let object = hit.object;
        while (object && object !== room) {
          if (Number.isInteger(object.userData.seatIndex)) return object.userData.seatIndex;
          object = object.parent;
        }
      }
      return -1;
    };
    const onPointerDown = (event) => { down.x = event.clientX; down.y = event.clientY; down.active = true; };
    const onPointerMove = (event) => {
      if (down.active) return;
      hovered = hitSeat(event.clientX, event.clientY);
      renderer.domElement.style.cursor = hovered >= 0 && workstations[hovered].descriptor ? "pointer" : "grab";
    };
    const onPointerUp = (event) => {
      if (down.active && Math.hypot(event.clientX - down.x, event.clientY - down.y) < 6) {
        const index = hitSeat(event.clientX, event.clientY);
        const descriptor = workstations[index]?.descriptor;
        if (descriptor) selectRef.current?.(descriptor.task.TaskId);
      }
      down.active = false;
    };
    const onPointerLeave = () => { down.active = false; hovered = -1; renderer.domElement.style.cursor = "grab"; };
    const onDoubleClick = () => resetCamera();
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
      const span = aspect < 1 ? 13.4 / aspect : 11.5;
      camera.left = -span * aspect / 2;
      camera.right = span * aspect / 2;
      camera.top = span / 2;
      camera.bottom = -span / 2;
      camera.updateProjectionMatrix();
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);
    resize();

    const clock = new THREE.Clock();
    const startedAt = performance.now() / 1000;
    const projected = new THREE.Vector3();
    let animationFrame = 0;
    const animate = () => {
      animationFrame = requestAnimationFrame(animate);
      const delta = Math.min(clock.getDelta(), 0.05);
      const now = performance.now() / 1000;
      const intro = reduced ? 1 : smooth((now - startedAt) / 1.25);
      room.scale.setScalar(0.9 + intro * 0.1);
      room.position.y = (1 - intro) * -0.45;
      room.rotation.y = (1 - intro) * -0.08;
      controls.update();
      scene.updateMatrixWorld();

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
        const active = descriptor && (descriptor.task.TaskId === selectedRef.current || index === hovered);
        seat.ring.visible = !!active;
        seat.ring.material.color.set(descriptor?.state?.tone === "waiting" ? COLORS.wine : COLORS.sage);
        if (active) seat.ring.scale.setScalar(1 + Math.sin(now * 3) * 0.035);

        const node = labelRefs.current[index];
        if (node) {
          seat.anchor.getWorldPosition(projected);
          projected.project(camera);
          const x = (projected.x * 0.5 + 0.5) * host.clientWidth;
          const y = (-projected.y * 0.5 + 0.5) * host.clientHeight;
          const visible = descriptor && projected.z < 1 && x > -80 && x < host.clientWidth + 80 && y > -50 && y < host.clientHeight + 50;
          node.style.display = visible ? "block" : "none";
          node.style.left = `${x}px`;
          node.style.top = `${y}px`;
        }
      });
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
  }, []);

  return (
    <Box ref={hostRef} data-studio-scene="three" sx={{ position: "absolute", inset: 0, overflow: "hidden",
      "& canvas": { display: "block", width: "100%", height: "100%", outline: "none", cursor: "grab" } }}>
      {!ready && !failed && (
        <Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: FAINT, fontSize: 12 }}>
          Opening the studio…
        </Box>
      )}
      {failed && (
        <Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: FAINT, fontSize: 12 }}>
          The 3D studio needs WebGL enabled.
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
      <Box sx={{ position: "absolute", left: "50%", bottom: 12, transform: "translateX(-50%)", zIndex: 4,
        display: "flex", alignItems: "center", gap: 1, px: 1.2, py: 0.65, borderRadius: "8px",
        bgcolor: "rgba(255,253,249,.86)", border: `1px solid ${BORDER}`, backdropFilter: "blur(7px)" }}>
        <Typography sx={{ fontSize: 10.5, color: FAINT }}>drag to turn · scroll to zoom · click an agent</Typography>
        <Box component="button" type="button" onClick={() => sceneApi.current?.reset()}
          sx={{ border: 0, bgcolor: "transparent", color: "#536b59", fontSize: 10.5, fontWeight: 700,
            cursor: "pointer", p: 0, "&:hover": { textDecoration: "underline" } }}>Reset</Box>
      </Box>
    </Box>
  );
}
