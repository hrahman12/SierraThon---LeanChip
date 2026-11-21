import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const mm = (nm) => nm / 1e6;
const verdicts = { GREEN: 0x54b789, YELLOW: 0xf2bc62, RED: 0xf5717e };
const flash = 'SOIC-8_5.23x5.23mm_P1.27mm';

function modelName(part) {
  if (!part.body) return null;
  if (part.lib === flash) return 'UL_W25Q128JVSIQ_SOIC_208MIL';
  return part.lib.replace(/_(?:Pad.*HandSolder|HandSoldering|Handsoldering|ThermalVias)$/, '');
}

function footprintDetails(protocol) {
  const footprints = new Map();
  let pads;
  for (const line of protocol.split('\n')) {
    const [type, first, , ...values] = line.split('\t');
    if (type === 'F') {
      pads = [];
      footprints.set(first, { pads, drill: 0 });
    } else if (type === 'P' && pads) {
      pads.push(values.map(Number));
    } else if (type === 'T') {
      const fp = footprints.get(first);
      if (fp) fp.drill = mm(Number(values.at(-1)));
    }
  }
  return footprints;
}

export async function createBoardViewer(canvas, onSelect) {
  const { scene: catalogScene } = await new GLTFLoader().loadAsync(
    new URL('./assets/component-models.glb', import.meta.url).href,
  );
  const catalog = new Map();
  catalogScene.traverse((node) => {
    if (node.userData.stepModel) catalog.set(node.userData.stepModel, node);
  });

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.shadowMap.autoUpdate = false;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 800);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.86;
  controls.minDistance = 5;
  controls.maxDistance = 350;

  scene.add(new THREE.HemisphereLight(0xeaf3ff, 0x626c7f, 2.0));
  const keyLight = new THREE.DirectionalLight(0xfff3da, 2.6);
  keyLight.position.set(24, 65, -33);
  keyLight.castShadow = true;
  keyLight.shadow.mapSize.set(1024, 1024);
  keyLight.shadow.normalBias = 0.035;
  const rimLight = new THREE.DirectionalLight(0xb4cbff, 1.7);
  rimLight.position.set(-35, 15, 40);
  scene.add(keyLight, rimLight);

  const board = new THREE.Group();
  scene.add(board);
  const boardTop = new THREE.MeshStandardMaterial({ color: 0x155446, roughness: 0.74 });
  const boardEdge = new THREE.MeshStandardMaterial({ color: 0x766348, roughness: 0.85 });
  const padMaterial = new THREE.MeshStandardMaterial({ color: 0xba9e60, roughness: 0.28, metalness: 0.35 });
  const padBox = new THREE.BoxGeometry(1, 0.035, 1);
  const highlight = new THREE.LineBasicMaterial({ color: 0xe6f5ff });
  const missingOutline = new THREE.LineDashedMaterial({ color: 0xf1ca85, dashSize: 0.32, gapSize: 0.2 });
  const findings = Object.fromEntries(['YELLOW', 'RED'].map((color) => [color,
    new THREE.LineBasicMaterial({ color: verdicts[color], transparent: true, opacity: 0.5 }),
  ]));
  const finishes = new Map();
  const size = new THREE.Vector2();
  let parts = new Map();
  let selection;
  let owned = [];
  let boardSize = 54;
  let needsRender = true;
  controls.addEventListener('change', () => { needsRender = true; });

  function frame() {
    const vertical = THREE.MathUtils.degToRad(camera.fov / 2);
    const angle = Math.min(vertical, Math.atan(Math.tan(vertical) * camera.aspect));
    const distance = boardSize * 0.58 / Math.tan(angle);
    controls.target.set(0, 0, 0);
    camera.position.set(0.38, 0.84, -0.64).normalize().multiplyScalar(distance);
    controls.update();
  }

  const observer = new ResizeObserver(() => {
    const { clientWidth: width, clientHeight: height } = canvas;
    if (!width || !height) return;
    const firstFrame = !size.x;
    size.set(width, height);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    needsRender = true;
    if (firstFrame) frame();
  });
  observer.observe(canvas);
  frame();
  renderer.setAnimationLoop(() => {
    if (canvas.hidden || !size.x) return;
    controls.update();
    if (needsRender) {
      renderer.render(scene, camera);
      needsRender = false;
    }
  });

  function finish(source, part) {
    const led = /^LED_/.test(part.lib);
    const chip = /^(?:QFN|SOIC|SOT)-/.test(part.lib);
    const key = `${source.uuid}/${part.color}/${led}/${chip}`;
    if (finishes.has(key)) return finishes.get(key);
    const material = source.clone();
    const { r, g, b } = material.color;
    const metal = Math.min(r, g, b) > 0.54 && Math.max(r, g, b) - Math.min(r, g, b) < 0.15;
    if (chip && Math.max(r, g, b) < 0.25) material.color.multiplyScalar(0.24);
    if (led && g > r * 1.35 && g > b * 1.35) material.color.setHex(0xa82533);
    const tint = new THREE.Color(verdicts[part.color]);
    const brightness = Math.max(material.color.r, material.color.g, material.color.b, 0.07);
    tint.multiplyScalar(brightness / Math.max(tint.r, tint.g, tint.b));
    material.color.lerp(tint, metal ? 0.12 : 0.27);
    material.metalness = metal ? 0.45 : 0.08;
    material.roughness = metal ? 0.31 : 0.55;
    finishes.set(key, material);
    return material;
  }

  function outline(box, origin, material) {
    const [left, top, right, bottom] = box.map((n, i) => mm(n) - origin[i % 2]);
    const geometry = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(left, 0.075, top), new THREE.Vector3(right, 0.075, top),
      new THREE.Vector3(right, 0.075, bottom), new THREE.Vector3(left, 0.075, bottom),
      new THREE.Vector3(left, 0.075, top),
    ]);
    owned.push(geometry);
    const line = new THREE.Line(geometry, material);
    line.computeLineDistances();
    return line;
  }

  function select(ref) {
    needsRender = true;
    if (selection) {
      selection.geometry.dispose();
      selection.removeFromParent();
      owned = owned.filter((geometry) => geometry !== selection.geometry);
      selection = undefined;
    }
    const part = parts.get(ref);
    if (part) {
      selection = outline(part.court, part.origin, highlight);
      board.add(selection);
    }
  }

  function render(report, protocol, selectedRef) {
    needsRender = true;
    board.clear();
    owned.forEach((geometry) => geometry.dispose());
    owned = [];
    selection = undefined;
    parts = new Map();
    const footprints = footprintDetails(protocol);
    const xs = report.outline.map(([x]) => mm(x));
    const zs = report.outline.map(([, z]) => mm(z));
    if (xs.length < 3) return [];
    const origin = [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...zs) + Math.max(...zs)) / 2];
    const nextSize = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...zs) - Math.min(...zs));
    if (!(nextSize > 0)) return [];

    const shape = new THREE.Shape(report.outline.map(([x, z]) => new THREE.Vector2(mm(x) - origin[0], origin[1] - mm(z))));
    const holes = report.components.filter((part) => part.pads && /^MH\d+$/.test(part.ref) && footprints.get(part.ref)?.drill);
    for (const { ref, pads } of holes) {
      const cutout = new THREE.Path();
      cutout.absarc(mm((pads[0] + pads[2]) / 2) - origin[0], origin[1] - mm((pads[1] + pads[3]) / 2),
        footprints.get(ref).drill / 2, 0, 2 * Math.PI, true);
      shape.holes.push(cutout);
    }
    const depth = Math.max(0.15, mm(report.envelope.thickness_nm));
    const substrate = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false, curveSegments: 16 });
    owned.push(substrate);
    const slab = new THREE.Mesh(substrate, [boardTop, boardEdge]);
    slab.rotation.x = -Math.PI / 2;
    slab.position.y = -depth;
    slab.receiveShadow = true;
    board.add(slab);

    const missing = [];
    for (const part of report.components) {
      if (!part.court) continue;
      parts.set(part.ref, { court: part.court, origin });
      const group = new THREE.Group();
      group.userData.ref = part.ref;
      board.add(group);

      const placement = new THREE.Group();
      placement.position.set(mm(part.x) - origin[0], 0, mm(part.y) - origin[1]);
      placement.rotation.y = THREE.MathUtils.degToRad(part.rot);
      group.add(placement);
      for (const [x, y, width, height] of footprints.get(part.ref)?.pads ?? []) {
        if (!(width > 0 && height > 0)) continue;
        const pad = new THREE.Mesh(padBox, padMaterial);
        pad.position.set(mm(x), 0.015, mm(y));
        pad.scale.set(mm(width), 1, mm(height));
        placement.add(pad);
      }
      if (!part.fitted || holes.includes(part)) continue;
      const source = catalog.get(modelName(part));
      if (!source) {
        missing.push(part.ref);
        group.add(outline(part.court, origin, missingOutline));
        continue;
      }
      const model = source.clone();
      model.rotation.x = -Math.PI / 2;
      model.position.y = 0.035;
      model.traverse((node) => {
        if (!node.isMesh) return;
        node.material = finish(node.material, part);
        node.castShadow = true;
      });
      placement.add(model);
      if (findings[part.color]) group.add(outline(part.court, origin, findings[part.color]));
    }
    const resizeView = Math.abs(boardSize - nextSize) > 1;
    boardSize = nextSize;
    const shadowCamera = keyLight.shadow.camera;
    shadowCamera.left = shadowCamera.bottom = -boardSize * 0.66;
    shadowCamera.right = shadowCamera.top = boardSize * 0.66;
    shadowCamera.updateProjectionMatrix();
    renderer.shadowMap.needsUpdate = true;
    if (resizeView) frame();
    select(selectedRef);
    return missing;
  }

  const ray = new THREE.Raycaster();
  ray.params.Line.threshold = 0.12;
  let pointerStart;
  canvas.addEventListener('pointerdown', (event) => {
    pointerStart = [event.clientX, event.clientY];
  });
  canvas.addEventListener('pointerup', (event) => {
    if (!pointerStart || Math.hypot(event.clientX - pointerStart[0], event.clientY - pointerStart[1]) > 5) return;
    const rect = canvas.getBoundingClientRect();
    ray.setFromCamera(new THREE.Vector2(2 * (event.clientX - rect.left) / rect.width - 1,
      1 - 2 * (event.clientY - rect.top) / rect.height), camera);
    for (const { object } of ray.intersectObject(board, true)) {
      for (let node = object; node !== board; node = node.parent) {
        if (node.userData.ref) {
          onSelect(node.userData.ref);
          return;
        }
      }
    }
    onSelect(null);
  });

  return { render, select, frame };
}
