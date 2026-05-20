/**
 * Three.js 3D Background Animation
 * Colorful orbs, glowing rings, and cursor-following particles for gourmai
 */
import * as THREE from 'three';

let scene, camera, renderer;
let particleSystems = [];
let orbs = [];
let rings = [];
let cursorLight;
let mouseX = 0, mouseY = 0;
let targetMouseX = 0, targetMouseY = 0;
let mouseWorld = new THREE.Vector3(0, 0, 0);
let animationId;

// Vibrant color palette
const PALETTE = [
    0xff416c, // rose
    0xff4b2b, // coral
    0xf857a6, // pink
    0xff5858, // salmon
    0xfb8c00, // amber
    0xffd54f, // gold
    0x8e24aa, // purple
    0x651fff, // violet
    0x00bcd4, // cyan
    0x00e676, // emerald
    0xff6e40, // deep orange
    0xea80fc, // lavender
];

export function initThreeBackground() {
    const canvas = document.getElementById('three-canvas');
    if (!canvas) return;

    // Scene
    scene = new THREE.Scene();

    // Camera
    camera = new THREE.PerspectiveCamera(65, window.innerWidth / window.innerHeight, 0.1, 200);
    camera.position.z = 40;

    // Renderer
    renderer = new THREE.WebGLRenderer({
        canvas,
        alpha: true,
        antialias: true,
    });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);

    // Ambient light
    const ambient = new THREE.AmbientLight(0x111133, 0.3);
    scene.add(ambient);

    // Cursor-following point light
    cursorLight = new THREE.PointLight(0xff416c, 3, 40);
    cursorLight.position.set(0, 0, 15);
    scene.add(cursorLight);

    // Additional atmosphere lights
    const backLight1 = new THREE.PointLight(0x651fff, 1.5, 60);
    backLight1.position.set(-20, 15, -10);
    scene.add(backLight1);

    const backLight2 = new THREE.PointLight(0x00bcd4, 1, 60);
    backLight2.position.set(20, -10, -10);
    scene.add(backLight2);

    // Create objects
    createStarField();
    createColorfulOrbs();
    createGlowRings();
    createTrailingParticles();

    // Events
    window.addEventListener('resize', onWindowResize);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('touchmove', onTouchMove, { passive: true });

    animate();
}

// === Star field background ===
function createStarField() {
    const count = 500;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
        positions[i * 3] = (Math.random() - 0.5) * 120;
        positions[i * 3 + 1] = (Math.random() - 0.5) * 120;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 80 - 20;

        // Warm white to warm gold
        const warmth = Math.random();
        colors[i * 3] = 0.9 + warmth * 0.1;
        colors[i * 3 + 1] = 0.8 + warmth * 0.15;
        colors[i * 3 + 2] = 0.6 + warmth * 0.3;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    const material = new THREE.PointsMaterial({
        size: 0.08,
        vertexColors: true,
        transparent: true,
        opacity: 0.7,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
    });

    const stars = new THREE.Points(geometry, material);
    scene.add(stars);
    particleSystems.push({ mesh: stars, type: 'stars' });
}

// === Colorful glowing orbs ===
function createColorfulOrbs() {
    for (let i = 0; i < 18; i++) {
        const radius = Math.random() * 0.9 + 0.4;
        const color = PALETTE[Math.floor(Math.random() * PALETTE.length)];

        // Outer glow sphere
        const glowGeo = new THREE.SphereGeometry(radius * 3.5, 16, 16);
        const glowMat = new THREE.MeshBasicMaterial({
            color: color,
            transparent: true,
            opacity: 0.12,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        });
        const glowMesh = new THREE.Mesh(glowGeo, glowMat);

        // Inner core
        const coreGeo = new THREE.SphereGeometry(radius, 24, 24);
        const coreMat = new THREE.MeshPhongMaterial({
            color: color,
            emissive: color,
            emissiveIntensity: 1.0,
            transparent: true,
            opacity: 0.75,
            shininess: 150,
        });
        const core = new THREE.Mesh(coreGeo, coreMat);

        const group = new THREE.Group();
        group.add(glowMesh);
        group.add(core);

        // Attached point light (soft)
        const orbLight = new THREE.PointLight(color, 0.8, 18);
        group.add(orbLight);

        const spreadX = 55;
        const spreadY = 40;
        const spreadZ = 30;

        group.position.set(
            (Math.random() - 0.5) * spreadX,
            (Math.random() - 0.5) * spreadY,
            (Math.random() - 0.5) * spreadZ - 10
        );

        group.userData = {
            basePos: group.position.clone(),
            speed: Math.random() * 0.4 + 0.2,
            amplitude: Math.random() * 3 + 1.5,
            phase: Math.random() * Math.PI * 2,
            orbitRadius: Math.random() * 2 + 1,
            color: color,
            // cursor attraction strength
            attractStrength: Math.random() * 0.3 + 0.05,
        };

        scene.add(group);
        orbs.push(group);
    }
}

// === Glowing rings ===
function createGlowRings() {
    for (let i = 0; i < 6; i++) {
        const ringRadius = Math.random() * 1.5 + 0.8;
        const tubeRadius = 0.03 + Math.random() * 0.04;
        const color = PALETTE[Math.floor(Math.random() * PALETTE.length)];

        const ringGeo = new THREE.TorusGeometry(ringRadius, tubeRadius, 16, 60);
        const ringMat = new THREE.MeshBasicMaterial({
            color: color,
            transparent: true,
            opacity: 0.35,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);

        ring.position.set(
            (Math.random() - 0.5) * 50,
            (Math.random() - 0.5) * 35,
            (Math.random() - 0.5) * 20 - 10
        );

        ring.rotation.set(
            Math.random() * Math.PI,
            Math.random() * Math.PI,
            0
        );

        ring.userData = {
            rotSpeed: (Math.random() - 0.5) * 0.008,
            wobbleSpeed: Math.random() * 0.3 + 0.1,
            wobbleAmplitude: Math.random() * 2 + 0.5,
            phase: Math.random() * Math.PI * 2,
            basePos: ring.position.clone(),
        };

        scene.add(ring);
        rings.push(ring);
    }
}

// === Trailing particles that swarm toward cursor (custom shader for high-res glow) ===
let trailingParticles = null;
let trailingVelocities = null;

// Vertex shader: passes color and size to fragment
const trailVertexShader = `
  attribute float aSize;
  varying vec3 vColor;
  void main() {
    vColor = color;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = aSize * (300.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

// Fragment shader: smooth radial gradient glow
const trailFragmentShader = `
  varying vec3 vColor;
  void main() {
    float dist = length(gl_PointCoord - vec2(0.5));
    if (dist > 0.5) discard;
    float strength = 1.0 - (dist * 2.0);
    strength = pow(strength, 1.5);
    float glow = exp(-dist * 4.0) * 0.6;
    float alpha = strength * 0.7 + glow;
    gl_FragColor = vec4(vColor * (1.0 + glow * 0.5), alpha);
  }
`;

function createTrailingParticles() {
    const count = 200;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const sizes = new Float32Array(count);
    const velocities = new Float32Array(count * 3);

    for (let i = 0; i < count; i++) {
        positions[i * 3] = (Math.random() - 0.5) * 40;
        positions[i * 3 + 1] = (Math.random() - 0.5) * 40;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 20;

        velocities[i * 3] = 0;
        velocities[i * 3 + 1] = 0;
        velocities[i * 3 + 2] = 0;

        sizes[i] = Math.random() * 1.5 + 0.5;

        const c = new THREE.Color(PALETTE[Math.floor(Math.random() * PALETTE.length)]);
        colors[i * 3] = c.r;
        colors[i * 3 + 1] = c.g;
        colors[i * 3 + 2] = c.b;
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1));

    const material = new THREE.ShaderMaterial({
        vertexShader: trailVertexShader,
        fragmentShader: trailFragmentShader,
        vertexColors: true,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
    });

    trailingParticles = new THREE.Points(geometry, material);
    trailingVelocities = velocities;
    scene.add(trailingParticles);
}

function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

function onMouseMove(event) {
    targetMouseX = (event.clientX / window.innerWidth) * 2 - 1;
    targetMouseY = -(event.clientY / window.innerHeight) * 2 + 1;

    // Project mouse to 3D world
    mouseWorld.set(targetMouseX * 25, targetMouseY * 18, 5);
}

function onTouchMove(event) {
    if (event.touches.length > 0) {
        targetMouseX = (event.touches[0].clientX / window.innerWidth) * 2 - 1;
        targetMouseY = -(event.touches[0].clientY / window.innerHeight) * 2 + 1;
        mouseWorld.set(targetMouseX * 25, targetMouseY * 18, 5);
    }
}

function animate() {
    animationId = requestAnimationFrame(animate);
    const time = Date.now() * 0.001;

    // Smooth mouse
    mouseX += (targetMouseX - mouseX) * 0.08;
    mouseY += (targetMouseY - mouseY) * 0.08;

    // Camera gently follows cursor
    camera.position.x += (mouseX * 4 - camera.position.x) * 0.015;
    camera.position.y += (mouseY * 3 - camera.position.y) * 0.015;
    camera.lookAt(0, 0, 0);

    // Move cursor light to follow mouse
    cursorLight.position.x += (mouseWorld.x - cursorLight.position.x) * 0.1;
    cursorLight.position.y += (mouseWorld.y - cursorLight.position.y) * 0.1;
    // Pulse cursor light color
    const hue = (time * 0.05) % 1;
    cursorLight.color.setHSL(hue, 0.9, 0.6);

    // Animate star field
    particleSystems.forEach(ps => {
        ps.mesh.rotation.y += 0.0002;
        ps.mesh.rotation.x += 0.0001;
    });

    // Animate orbs - attracted toward cursor
    orbs.forEach(orb => {
        const d = orb.userData;

        // Organic float
        const floatX = Math.sin(time * d.speed + d.phase) * d.amplitude;
        const floatY = Math.cos(time * d.speed * 0.7 + d.phase) * d.amplitude;
        const floatZ = Math.sin(time * d.speed * 0.5 + d.phase * 2) * d.amplitude * 0.3;

        // Cursor attraction
        const dx = mouseWorld.x - d.basePos.x;
        const dy = mouseWorld.y - d.basePos.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const attract = d.attractStrength / (1 + dist * 0.05);

        orb.position.x = d.basePos.x + floatX + dx * attract;
        orb.position.y = d.basePos.y + floatY + dy * attract;
        orb.position.z = d.basePos.z + floatZ;

        // Pulse glow
        if (orb.children[0]) {
            orb.children[0].material.opacity = 0.04 + Math.sin(time * 1.5 + d.phase) * 0.03;
        }
        if (orb.children[1]) {
            orb.children[1].material.opacity = 0.35 + Math.sin(time * 2 + d.phase) * 0.15;
        }
        if (orb.children[2]) {
            orb.children[2].intensity = 0.3 + Math.sin(time * 1.5 + d.phase) * 0.2;
        }
    });

    // Animate rings
    rings.forEach(ring => {
        const d = ring.userData;
        ring.rotation.x += d.rotSpeed;
        ring.rotation.y += d.rotSpeed * 0.7;
        ring.position.y = d.basePos.y + Math.sin(time * d.wobbleSpeed + d.phase) * d.wobbleAmplitude;
        ring.material.opacity = 0.2 + Math.sin(time + d.phase) * 0.15;
    });

    // Animate trailing particles - swarm toward cursor
    if (trailingParticles) {
        const pos = trailingParticles.geometry.attributes.position.array;
        const count = pos.length / 3;

        for (let i = 0; i < count; i++) {
            const ix = i * 3;
            const iy = i * 3 + 1;
            const iz = i * 3 + 2;

            // Direction toward cursor
            const dx = mouseWorld.x - pos[ix];
            const dy = mouseWorld.y - pos[iy];
            const dz = mouseWorld.z - pos[iz];
            const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);

            // Attract with falloff
            const force = 0.015;
            trailingVelocities[ix] += dx * force;
            trailingVelocities[iy] += dy * force;
            trailingVelocities[iz] += dz * force;

            // Add some swirl
            const swirlForce = 0.002;
            trailingVelocities[ix] += -dy * swirlForce;
            trailingVelocities[iy] += dx * swirlForce;

            // Damping
            trailingVelocities[ix] *= 0.94;
            trailingVelocities[iy] *= 0.94;
            trailingVelocities[iz] *= 0.94;

            // Apply
            pos[ix] += trailingVelocities[ix];
            pos[iy] += trailingVelocities[iy];
            pos[iz] += trailingVelocities[iz];

            // If too close, scatter slightly
            if (dist < 2) {
                pos[ix] += (Math.random() - 0.5) * 0.5;
                pos[iy] += (Math.random() - 0.5) * 0.5;
            }
        }

        trailingParticles.geometry.attributes.position.needsUpdate = true;
    }

    renderer.render(scene, camera);
}

export function disposeThreeBackground() {
    if (animationId) cancelAnimationFrame(animationId);
    window.removeEventListener('resize', onWindowResize);
    document.removeEventListener('mousemove', onMouseMove);
    if (renderer) renderer.dispose();
}
